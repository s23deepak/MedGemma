"""
VLLMModelManager - Manages FunctionGemma, MedGemma, and MedASR with vLLM sleep mode.

Uses vLLM's sleep(level=2) to offload model weights + KV cache to CPU when idle,
so all three models coexist on a single GPU by keeping only one active at a time.

  FunctionGemma (270M)  ─┐
  MedGemma      (4B)    ─┤── VLLMModelManager  ──  GPU (one at a time)
  MedASR        (seq2seq)─┘      sleep / wake

Sleep levels:
  level=1  Free KV cache blocks only (weights remain on GPU)
  level=2  Free KV cache + offload model weights to CPU (full GPU free)
"""

import asyncio
import logging
from pathlib import Path
from typing import Literal

import numpy as np
import torch

logger = logging.getLogger(__name__)

try:
    from vllm import LLM, SamplingParams
    VLLM_AVAILABLE = True
except ImportError:
    VLLM_AVAILABLE = False
    logger.warning("vLLM not installed. Run: uv pip install vllm")

# Import vLLM configuration
try:
    from src.config.vllm_config import get_vllm_config, customize_config
except ImportError:
    logger.warning("vllm_config not found; using inline defaults")
    get_vllm_config = lambda mode="local": {
        "tensor_parallel_size": 1,
        "gpu_memory_utilization": 0.85,
        "max_model_len": 2048,
        "max_num_batched_tokens": 256,
        "max_num_seqs": 1,
        "dtype": "bfloat16",
        "quantization": "bitsandbytes",
        "enforce_eager": True,
        "enable_vision": True,
        "enable_chunked_prefill": True,
        "enable_prefix_caching": True,
    }
    customize_config = lambda base="local", **kw: {**get_vllm_config(base), **kw}

ModelName = Literal["medgemma", "functiongemma", "medasr"]


class VLLMModelManager:
    """
    Unified model manager for FunctionGemma, MedGemma, and MedASR.

    - FunctionGemma + MedGemma use vLLM with sleep(level=2) for weights offloading.
    - MedASR (HuggingFace Transformers) uses .to("cpu") / .to("cuda") offloading.
    - Only one model is resident in GPU memory at any time.
    - An asyncio.Lock serialises concurrent wake/sleep transitions.

    Memory guide (single 8 GB GPU):
      Weights:   MedGemma 4B @ 4-bit ≈ 3.5 GB (quantization="bitsandbytes")
      Profiling: encoder forward pass for max_num_batched_tokens / 256 images
                   8192 (default) → 32 images → ~3.4 GB  ← OOM
                   1024 (tuned)   →  4 images → ~0.4 GB  ← fits
      KV cache:  ~0.6 GB available at max_num_batched_tokens=1024
      Vision:    enable_vision=True works at max_num_batched_tokens=1024
                 enable_vision=False skips encoder entirely (no profiling at all)
    """

    MEDGEMMA_ID = "google/medgemma-1.5-4b-it"
    FUNCTIONGEMMA_ID = "google/functiongemma-270m-it"

    def __init__(
        self,
        config: str | dict | None = None,
        load_functiongemma: bool = True,
        load_medasr: bool = True,
    ):
        """
        Initialize VLLMModelManager with flexible configuration.

        Args:
            config: Configuration mode or dict
                - "local" (default): RTX 5060, batch_size=1, optimized for development
                - "production": Higher throughput, batching, multi-concurrent requests
                - dict: Custom configuration dict with vLLM parameters
                - None: Uses VLLM_ENV env var (default: "local")
            load_functiongemma: Load FunctionGemma model
            load_medasr: Load MedASR model
        """
        if not VLLM_AVAILABLE:
            raise ImportError("vLLM is not installed. Run: uv pip install vllm")

        # Load configuration
        if isinstance(config, dict):
            cfg = config
            config_mode = "custom"
        else:
            cfg = get_vllm_config(config)
            config_mode = config or "local"

        logger.info(f"Using vLLM configuration: {config_mode}")

        # Store config parameters
        self.gpu_memory_utilization = cfg.get("gpu_memory_utilization", 0.85)
        self.max_model_len = cfg.get("max_model_len", 2048)
        self.max_num_batched_tokens = cfg.get("max_num_batched_tokens", 256)
        self.max_num_seqs = cfg.get("max_num_seqs", 1)
        self.quantization = cfg.get("quantization", "bitsandbytes")
        self.enforce_eager = cfg.get("enforce_eager", True)
        self.enable_vision = cfg.get("enable_vision", True)
        self.enable_chunked_prefill = cfg.get("enable_chunked_prefill", True)
        self.enable_prefix_caching = cfg.get("enable_prefix_caching", True)
        self.tensor_parallel_size = cfg.get("tensor_parallel_size", 1)

        self._vllm_engines: dict[str, LLM] = {}
        self._medasr = None
        self._active: ModelName | None = None
        self._status: dict[str, str] = {}  # "unloaded" | "asleep" | "awake"
        self._lock = asyncio.Lock()

        # Load models sequentially. Each sleeps immediately after init so that
        # the next model can use the freed GPU memory.
        self._init_medgemma()
        if load_functiongemma:
            self._init_functiongemma()
        if load_medasr:
            self._init_medasr()

    # ── Model initialisation ──────────────────────────────────────────────────

    def _init_medgemma(self):
        logger.info(f"Loading MedGemma ({self.MEDGEMMA_ID}) into vLLM…")
        logger.info(f"  max_num_batched_tokens={self.max_num_batched_tokens}, max_num_seqs={self.max_num_seqs}")

        # Encoder profiling images = max_num_batched_tokens / tokens_per_image (256).
        # Default 8192 → 32 images → ~3.4 GB activation OOM on 8 GB GPU.
        # Setting max_num_batched_tokens=256 → 1 image → ~0.1 GB → fits easily on RTX 5060.
        # limit_mm_per_prompt={"image": 0} skips encoder entirely (no vision) — fallback if OOM.
        mm_limit = {"image": 1} if self.enable_vision else {"image": 0}
        if not self.enable_vision:
            logger.info("Vision encoder disabled (enable_vision=False). Image inputs will use text-only path.")

        engine = LLM(
            model=self.MEDGEMMA_ID,
            gpu_memory_utilization=self.gpu_memory_utilization,
            max_model_len=self.max_model_len,
            max_num_batched_tokens=self.max_num_batched_tokens,
            max_num_seqs=self.max_num_seqs,
            trust_remote_code=True,
            enforce_eager=self.enforce_eager,
            quantization=self.quantization,
            limit_mm_per_prompt=mm_limit,
            dtype="bfloat16",
            enable_chunked_prefill=self.enable_chunked_prefill,
            enable_prefix_caching=self.enable_prefix_caching,
        )
        engine.sleep(level=2)
        self._vllm_engines["medgemma"] = engine
        self._status["medgemma"] = "asleep"
        logger.info("MedGemma loaded and sleeping (chunked prefill + prefix caching enabled)")

    def _init_functiongemma(self):
        logger.info(f"Loading FunctionGemma ({self.FUNCTIONGEMMA_ID}) into vLLM…")
        logger.info(f"  max_num_seqs={self.max_num_seqs}")

        engine = LLM(
            model=self.FUNCTIONGEMMA_ID,
            gpu_memory_utilization=0.30,  # 270M needs much less headroom
            max_model_len=2048,
            max_num_seqs=self.max_num_seqs,
            trust_remote_code=True,
            enforce_eager=self.enforce_eager,
            dtype="bfloat16",
            enable_chunked_prefill=self.enable_chunked_prefill,
            enable_prefix_caching=self.enable_prefix_caching,
        )
        engine.sleep(level=2)
        self._vllm_engines["functiongemma"] = engine
        self._status["functiongemma"] = "asleep"
        logger.info("FunctionGemma loaded and sleeping (chunked prefill + prefix caching enabled)")

    def _init_medasr(self):
        try:
            from src.asr.medasr_streaming import MedASRStreaming
            logger.info("Loading MedASR…")
            self._medasr = MedASRStreaming(device="cuda")
            self._medasr.sleep()   # Immediately offload weights to CPU
            self._status["medasr"] = "asleep"
            logger.info("MedASR loaded and sleeping")
        except Exception as exc:
            logger.warning(f"MedASR load failed ({exc}); falling back to SimulatedMedASR")
            from src.asr.medasr_streaming import SimulatedMedASR
            self._medasr = SimulatedMedASR()
            self._status["medasr"] = "awake"  # Simulated stays in memory (no GPU)

    # ── Sleep / wake helpers ──────────────────────────────────────────────────

    def _sleep_model(self, name: ModelName):
        if name in self._vllm_engines:
            logger.info(f"Sleeping {name}…")
            self._vllm_engines[name].sleep(level=2)
            self._status[name] = "asleep"
        elif name == "medasr" and self._medasr is not None:
            logger.info("Sleeping MedASR…")
            if hasattr(self._medasr, "sleep"):
                self._medasr.sleep()
            self._status["medasr"] = "asleep"

    def _wake_model(self, name: ModelName):
        if name in self._vllm_engines:
            logger.info(f"Waking {name}…")
            self._vllm_engines[name].wake_up()
            self._status[name] = "awake"
        elif name == "medasr" and self._medasr is not None:
            logger.info("Waking MedASR…")
            if hasattr(self._medasr, "wake_up"):
                self._medasr.wake_up()
            self._status["medasr"] = "awake"

    def _ensure_awake(self, name: ModelName):
        """Sleep the active model and wake the requested one (sync version)."""
        if self._active == name:
            return
        if self._active is not None:
            self._sleep_model(self._active)
        self._wake_model(name)
        self._active = name

    async def _ensure_awake_async(self, name: ModelName):
        """Async-safe version of _ensure_awake using asyncio.Lock."""
        async with self._lock:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._ensure_awake, name)

    # ── Public inference API ──────────────────────────────────────────────────

    def generate_medgemma(
        self,
        prompt: str,
        image=None,
        temperature: float = 0.4,
        max_tokens: int = 2048,
        stop: list[str] | None = None,
    ) -> str:
        """Generate text with MedGemma (wakes up, then remains active).

        Supports analysis of any medical image type (XRay, MRI, CT, pathology, ultrasound, etc.)
        when enable_vision=True. Gracefully falls back to text-only analysis if vision fails.

        For multimodal inputs:
        - Accepts PIL Image objects (any format/modality)
        - Converts to temp file (vLLM requirement)
        - Passes to vLLM with proper multimodal format
        """
        self._ensure_awake("medgemma")

        sampling_params = SamplingParams(
            temperature=temperature,
            top_p=0.9,
            max_tokens=max_tokens,
            stop=stop or ["<|end|>", "<|eot_id|>"],
        )

        if image is not None and self.enable_vision:
            try:
                # vLLM multimodal: pass PIL image directly in multi_modal_data
                outputs = self._vllm_engines["medgemma"].generate(
                    [
                        {
                            "prompt": prompt,
                            "multi_modal_data": {"image": image}
                        }
                    ],
                    sampling_params
                )
                result = outputs[0].outputs[0].text
                # FILTER: Detect and truncate infinite repetitions (model stuck in loop)
                result = self._truncate_infinite_repetition(result)
                logger.debug(f"Vision analysis completed ({len(result)} chars)")
                return result

            except Exception as e:
                logger.warning(f"Multimodal analysis failed ({type(e).__name__}: {e}), falling back to text-only")
                # Strip image-analysis instructions from prompt for text-only fallback
                import re
                prompt = re.sub(
                    r'Analyze this \w+ image[\.,]?\s*',
                    '',
                    prompt
                )
                prompt = re.sub(
                    r'focusing on the annotated region\(s\)[\.,]?\s*',
                    '',
                    prompt
                )
                # Fallback: analyze based on prompt context only (no image)
                outputs = self._vllm_engines["medgemma"].generate([prompt], sampling_params)
                result = outputs[0].outputs[0].text
                # FILTER: Detect and truncate infinite repetitions (model stuck in loop)
                result = self._truncate_infinite_repetition(result)
                return result

        else:
            if image is not None and not self.enable_vision:
                logger.warning(
                    "Image provided but enable_vision=False. Processing as text-only analysis. "
                    "Enable vision in vllm_config.py or pass enable_vision=True to VLLMModelManager()."
                )
            outputs = self._vllm_engines["medgemma"].generate([prompt], sampling_params)
            return outputs[0].outputs[0].text

    def _truncate_infinite_repetition(self, response: str) -> str:
        """Detect and truncate infinite repetition patterns (model stuck in loop)."""
        lines = response.split('\n')
        if len(lines) < 5:
            return response

        # Pattern 1: Same line repeated 5+ times consecutively
        line_counts = {}
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and len(stripped) > 10:
                if i > 0 and lines[i-1].strip() == stripped:
                    if stripped not in line_counts:
                        line_counts[stripped] = 0
                    line_counts[stripped] += 1

        for repeated_line, count in line_counts.items():
            if count >= 5:
                for i, line in enumerate(lines):
                    if line.strip() == repeated_line and i > 0:
                        is_repetition = all(
                            lines[i+j].strip() == repeated_line
                            for j in range(1, min(4, len(lines)-i))
                        )
                        if is_repetition:
                            return '\n'.join(lines[:i])

        # Pattern 2: Two lines alternating 4+ times (A, B, A, B, A, B, A, B)
        for i in range(len(lines) - 7):
            stripped_i = lines[i].strip()
            if not stripped_i or len(stripped_i) <= 10:
                continue
            for j in range(i + 1, min(i + 4, len(lines))):
                stripped_j = lines[j].strip()
                if not stripped_j or len(stripped_j) <= 10:
                    continue
                alternation_count = 0
                expect_i = True
                for k in range(i, min(i + 8, len(lines))):
                    curr = lines[k].strip()
                    if expect_i:
                        if curr == stripped_i:
                            alternation_count += 1
                            expect_i = False
                        else:
                            break
                    else:
                        if curr == stripped_j:
                            alternation_count += 1
                            expect_i = True
                        else:
                            break
                if alternation_count >= 8:
                    return '\n'.join(lines[:i])

        # Pattern 3: Multi-line block repeated 3+ times
        # Join non-empty lines into blocks separated by blank lines, detect repeating blocks
        text = response.strip()
        for block_size in range(2, 6):  # check 2-5 line blocks
            for start in range(len(lines) - block_size * 3):
                block = '\n'.join(line.strip() for line in lines[start:start + block_size])
                if len(block.strip()) < 20:
                    continue
                repeat_count = 1
                pos = start + block_size
                while pos + block_size <= len(lines):
                    candidate = '\n'.join(line.strip() for line in lines[pos:pos + block_size])
                    if candidate == block:
                        repeat_count += 1
                        pos += block_size
                    else:
                        # Allow skipping one blank line between blocks
                        if pos < len(lines) and lines[pos].strip() == '':
                            candidate2 = '\n'.join(line.strip() for line in lines[pos + 1:pos + 1 + block_size])
                            if candidate2 == block:
                                repeat_count += 1
                                pos += 1 + block_size
                                continue
                        break
                if repeat_count >= 3:
                    # Keep up to first occurrence + one repeat
                    cut = start + block_size * 2
                    return '\n'.join(lines[:min(cut, len(lines))])

        return response

    def generate_functiongemma(
        self,
        prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 512,
        stop: list[str] | None = None,
    ) -> str:
        """Route / function-call with FunctionGemma (270M)."""
        self._ensure_awake("functiongemma")

        sampling_params = SamplingParams(
            temperature=temperature,
            top_p=0.95,
            max_tokens=max_tokens,
            stop=stop or ["User:", "\n\n"],
        )

        outputs = self._vllm_engines["functiongemma"].generate([prompt], sampling_params)
        return outputs[0].outputs[0].text.strip()

    def chat(self, message: str, history: list[dict] | None = None) -> str:
        """
        Simple chat interface compatible with MedGemmaAgent.chat().
        Used by the Diagnostic Council and other text-only callers.
        """
        system_prompt = (
            "You are a clinical decision support assistant powered by MedGemma. "
            "Assist physicians with diagnosis, documentation, and clinical reasoning. "
            "Always present findings as suggestions, not definitive diagnoses."
        )
        conversation = system_prompt + "\n\n"
        if history:
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                conversation += f"{'User' if role == 'user' else 'Assistant'}: {content}\n"
        conversation += f"User: {message}\nAssistant:"
        return self.generate_medgemma(
            prompt=conversation,
            temperature=0.4,
            max_tokens=1536,
            stop=["User:", "<|end|>", "<|eot_id|>"],
        )

    def get_medasr(self):
        """Return the MedASR instance, woken up and ready."""
        self._ensure_awake("medasr")
        return self._medasr

    def transcribe_audio_file(self, audio_path: str) -> str:
        """Transcribe an audio file using MedASR."""
        self._ensure_awake("medasr")
        return self._medasr.transcribe_file(audio_path)

    def transcribe_audio_bytes(
        self, audio_bytes: bytes, sample_rate: int = 16000
    ) -> str:
        """Transcribe raw PCM bytes (Int16) using MedASR."""
        self._ensure_awake("medasr")
        audio_data = (
            np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        )
        if sample_rate != 16000:
            ratio = 16000 / sample_rate
            new_len = int(len(audio_data) * ratio)
            audio_data = np.interp(
                np.linspace(0, len(audio_data), new_len),
                np.arange(len(audio_data)),
                audio_data,
            )
        return self._medasr._transcribe_chunk(audio_data)

    # ── Status ────────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Return current status of all managed models."""
        return {
            "active": self._active,
            "vision_enabled": self.enable_vision,
            "models": {
                k: {"status": v} for k, v in self._status.items()
            },
        }

    # ── Convenience wrappers matching MedGemmaVLLMAgent interface ─────────────

    def analyze_image(
        self,
        image_path,
        clinical_context: str = "",
        modality: str = "xray",
        patient_symptoms: list[str] | None = None,
        chief_complaint: str = "",
        body_region: str = "",
    ) -> dict:
        """
        Analyze any medical image with MedGemma.
        Supports all medical image types: XRay, MRI, CT, Ultrasound, Pathology, etc.
        API-compatible with MedGemmaVLLMAgent.analyze_image().

        When enable_vision=False (default on 8 GB GPUs), the image file is not
        passed to the model; instead a clinical-context-only differential is
        generated from the text inputs.

        Args:
            image_path: Path to medical image (JPEG, PNG, etc.)
            clinical_context: Clinical context (findings, symptoms, history)
            modality: Image type (xray, mri, ct, ultrasound, pathology, etc.)
            patient_symptoms: List of patient symptoms
            chief_complaint: Primary reason for imaging
            body_region: Body region being imaged

        Returns:
            Dict with analysis, modality, context, and vision_enabled flag
        """
        from PIL import Image as PILImage

        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        symptoms_str = ", ".join(patient_symptoms) if patient_symptoms else "Not provided"
        complaint_str = chief_complaint or "Not provided"

        if self.enable_vision:
            image = PILImage.open(image_path).convert("RGB")

            # Map modality to appropriate specialist
            specialist_map = {
                "xray": "radiologist",
                "ct": "radiologist",
                "mri": "radiologist",
                "ultrasound": "sonographer",
                "pathology": "pathologist",
                "microscopy": "pathologist",
                "endoscopy": "gastroenterologist",
                "ecg": "cardiologist",
                "eeg": "neurologist",
            }
            specialist = specialist_map.get(modality.lower(), "medical imaging specialist")

            prompt = f"""You are an expert {specialist}. Analyze this {modality.upper()} image and provide a detailed clinical report.

CLINICAL CONTEXT:
- Chief Complaint: {complaint_str}
- Patient Symptoms: {symptoms_str}
- Body Region: {body_region or 'Not specified'}
- Additional Context: {clinical_context or 'None provided'}

ANALYSIS INSTRUCTIONS:
1. Assess image quality and any artifacts
2. Describe all visible findings
3. Correlate findings with the clinical context
4. List differential diagnoses in order of likelihood
5. Provide recommendations for next steps
6. Flag any urgent/critical findings clearly

Provide a structured clinical report. Be specific and concrete - do not use placeholder text or generic templates."""
        else:
            # Text-only mode: reason from clinical context without the actual image.
            # This happens when enable_vision=False (8 GB GPU — encoder disabled to save VRAM).
            image = None
            prompt = f"""A {modality.upper()} image has been ordered for clinical evaluation.

CLINICAL CONTEXT:
- Chief Complaint: {complaint_str}
- Patient Symptoms: {symptoms_str}
- Body Region: {body_region or 'Not specified'}
- Additional Context: {clinical_context or 'None provided'}

Based on this clinical context alone, provide:
1. Key clinical findings that should be evaluated on imaging
2. Likely diagnoses to consider
3. What a radiologist should specifically assess
4. Recommended follow-up actions

Note: This analysis is based on clinical context only, not direct image interpretation.
Actual radiological review is required for definitive diagnosis."""

        response = self.generate_medgemma(prompt, image=image, temperature=0.3, max_tokens=1536)

        return {
            "modality": modality,
            "image_path": str(image_path),
            "analysis": response,
            "clinical_context": clinical_context,
            "chief_complaint": chief_complaint,
            "patient_symptoms": patient_symptoms or [],
            "vision_enabled": self.enable_vision,
        }

    def process_encounter(
        self,
        transcription: str,
        patient_context: dict | None = None,
        image_path: str | None = None,
        image_modality: str = "xray",
    ) -> dict:
        """
        Process a complete clinical encounter.
        API-compatible with MedGemmaVLLMAgent.process_encounter().
        """
        import json

        results: dict = {
            "transcription": transcription,
            "patient_context": patient_context,
            "image_analysis": None,
            "soap_note": None,
            "alerts": [],
        }

        # Analyse image first (if provided)
        if image_path:
            results["image_analysis"] = self.analyze_image(
                image_path,
                clinical_context=transcription,
                modality=image_modality,
            )

        # Build SOAP prompt
        parts = [f"**Physician Dictation:**\n{transcription}"]
        if patient_context:
            parts.append(f"\n**Patient EHR Context:**\n{json.dumps(patient_context, indent=2)}")
        if results["image_analysis"]:
            parts.append(
                f"\n**Image Analysis ({image_modality.upper()}):**\n"
                f"{results['image_analysis']['analysis']}"
            )

        prompt = f"""Based on the following clinical encounter, generate a complete SOAP note.

{chr(10).join(parts)}

## Subjective
[Patient's reported symptoms and history]

## Objective
[Physical examination findings, vital signs, and imaging results]

## Assessment
[Clinical impression, differential diagnoses, and reasoning]

## Plan
[Treatment plan, follow-up, and any referrals]

---

Additionally identify:
1. **Potential Missed Diagnoses**: Conditions suggested by data not explicitly considered
2. **Critical Alerts**: Urgent findings requiring immediate attention
3. **Inconsistencies**: Discrepancies between reported symptoms and objective findings"""

        response = self.generate_medgemma(prompt, temperature=0.4, max_tokens=2048)
        results["soap_note"] = response

        if "CRITICAL" in response.upper() or "URGENT" in response.upper():
            results["alerts"].append({
                "level": "critical",
                "message": "Critical finding detected — please review immediately",
            })

        return results


# ── Singleton ─────────────────────────────────────────────────────────────────

_manager: VLLMModelManager | None = None


def get_vllm_manager(**kwargs) -> VLLMModelManager:
    global _manager
    if _manager is None:
        _manager = VLLMModelManager(**kwargs)
    return _manager


def is_vllm_manager_available() -> bool:
    return VLLM_AVAILABLE
