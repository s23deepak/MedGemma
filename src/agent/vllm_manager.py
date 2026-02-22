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

ModelName = Literal["medgemma", "functiongemma", "medasr"]


class VLLMModelManager:
    """
    Unified model manager for FunctionGemma, MedGemma, and MedASR.

    - FunctionGemma + MedGemma use vLLM with sleep(level=2) for weights offloading.
    - MedASR (HuggingFace Transformers) uses .to("cpu") / .to("cuda") offloading.
    - Only one model is resident in GPU memory at any time.
    - An asyncio.Lock serialises concurrent wake/sleep transitions.
    """

    MEDGEMMA_ID = "google/medgemma-1.5-4b-it"
    FUNCTIONGEMMA_ID = "google/functiongemma-3-270m"

    def __init__(
        self,
        gpu_memory_utilization: float = 0.85,
        max_model_len: int = 8192,
        load_medasr: bool = True,
    ):
        if not VLLM_AVAILABLE:
            raise ImportError("vLLM is not installed. Run: uv pip install vllm")

        self.gpu_memory_utilization = gpu_memory_utilization
        self.max_model_len = max_model_len

        self._vllm_engines: dict[str, LLM] = {}
        self._medasr = None
        self._active: ModelName | None = None
        self._status: dict[str, str] = {}  # "unloaded" | "asleep" | "awake"
        self._lock = asyncio.Lock()

        # Load models sequentially. Each sleeps immediately after init so that
        # the next model can use the freed GPU memory.
        self._init_medgemma()
        self._init_functiongemma()
        if load_medasr:
            self._init_medasr()

    # ── Model initialisation ──────────────────────────────────────────────────

    def _init_medgemma(self):
        logger.info(f"Loading MedGemma ({self.MEDGEMMA_ID}) into vLLM…")
        engine = LLM(
            model=self.MEDGEMMA_ID,
            gpu_memory_utilization=self.gpu_memory_utilization,
            max_model_len=self.max_model_len,
            trust_remote_code=True,
            limit_mm_per_prompt={"image": 1},
        )
        engine.sleep(level=2)
        self._vllm_engines["medgemma"] = engine
        self._status["medgemma"] = "asleep"
        logger.info("MedGemma loaded and sleeping")

    def _init_functiongemma(self):
        logger.info(f"Loading FunctionGemma ({self.FUNCTIONGEMMA_ID}) into vLLM…")
        engine = LLM(
            model=self.FUNCTIONGEMMA_ID,
            gpu_memory_utilization=0.30,  # 270M needs much less headroom
            max_model_len=2048,
            trust_remote_code=True,
        )
        engine.sleep(level=2)
        self._vllm_engines["functiongemma"] = engine
        self._status["functiongemma"] = "asleep"
        logger.info("FunctionGemma loaded and sleeping")

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
        """Generate text with MedGemma (wakes up, then remains active)."""
        self._ensure_awake("medgemma")

        sampling_params = SamplingParams(
            temperature=temperature,
            top_p=0.9,
            max_tokens=max_tokens,
            stop=stop or ["<|end|>", "<|eot_id|>"],
        )

        if image is not None:
            input_data = [{"prompt": prompt, "multi_modal_data": {"image": image}}]
        else:
            input_data = [prompt]

        outputs = self._vllm_engines["medgemma"].generate(input_data, sampling_params)
        return outputs[0].outputs[0].text

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
        Analyze a medical image with MedGemma.
        API-compatible with MedGemmaVLLMAgent.analyze_image().
        """
        from PIL import Image as PILImage

        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        image = PILImage.open(image_path).convert("RGB")

        symptoms_str = ", ".join(patient_symptoms) if patient_symptoms else "Not provided"
        complaint_str = chief_complaint or "Not provided"

        prompt = f"""Analyze this {modality.upper()} image for a clinical encounter.

Clinical Context: {clinical_context or 'Not provided'}
Patient's Chief Complaint: {complaint_str}
Patient's Reported Symptoms: {symptoms_str}
Body Region: {body_region or 'Not specified'}

Please provide a structured analysis:

## 1. IMAGE QUALITY & ARTIFACTS
- Overall Quality: [diagnostic / acceptable / degraded / non-diagnostic]
- Artifacts Found: List any artifacts found (or "None significant")
- Impact on Interpretation: [none / limited / significant]

## 2. KEY FINDINGS
List all observable findings by clinical significance.

## 3. CLINICAL CORRELATION
Classify each finding as CLINICALLY CORRELATED or INCIDENTAL.
Note: Degenerative changes common in asymptomatic populations must be correlated with symptoms.

## 4. DIFFERENTIAL CONSIDERATIONS
Possible diagnoses prioritised by clinical correlation.

## 5. RECOMMENDATIONS
Next steps for correlated findings; follow-up for incidental findings.

Flag urgent findings with ⚠️."""

        response = self.generate_medgemma(prompt, image=image, temperature=0.3, max_tokens=1536)

        return {
            "modality": modality,
            "image_path": str(image_path),
            "analysis": response,
            "clinical_context": clinical_context,
            "chief_complaint": chief_complaint,
            "patient_symptoms": patient_symptoms or [],
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
