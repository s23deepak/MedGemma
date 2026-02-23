"""
MedASR Streaming Integration
Real-time medical speech recognition using Google's MedASR model.

Backend selection (tried in this order):
  1. HF Space (Gradio) — set MEDASR_SPACE_ID (e.g. "your-username/medasr").
                         Free CPU tier sufficient for 105M model (~$0/hr, sleeps when idle).
                         Uses Gradio 4.x event API: POST /gradio_api/call/transcribe.
                         Optional ZeroGPU for faster inference (HF PRO required).

  2. Cloud endpoint    — set MEDASR_ENDPOINT_URL (HF Inference Endpoint or compatible
                         REST API).  Set HF_TOKEN for authenticated endpoints.
                         Sends raw WAV bytes; expects {"text": "..."} JSON response.
                         ~$0.033/hr on HF CPU instance (pausable).

  3. Local CTC         — google/medasr via AutoModelForCTC (requires transformers >= 5.0.0).
                         vLLM 0.15.x pins transformers < 5 so this will fail when vLLM
                         is installed alongside.

  4. Local Whisper     — openai/whisper-medium via pipeline (transformers 4.x compatible,
                         ~1.5 GB RAM).  Used automatically when the above three fail.

Environment variables:
  MEDASR_SPACE_ID       HuggingFace Space ID, e.g. "your-username/medasr"
                        Space repo: spaces/medasr/ in this project
  MEDASR_ENDPOINT_URL   URL of a deployed HF Inference Endpoint (or any compatible API)
  HF_TOKEN              HuggingFace access token (for private spaces/endpoints)
"""

import asyncio
import io
import logging
import os
import queue
import threading
from typing import Callable

import numpy as np
import torch

logger = logging.getLogger(__name__)


class MedASRStreaming:
    """
    Real-time medical speech recognition using MedASR.
    Handles streaming audio input and provides transcription callbacks.
    """
    
    MODEL_ID = "google/medasr"
    SAMPLE_RATE = 16000
    CHUNK_DURATION = 3.0  # Process 3-second chunks
    
    def __init__(self, device: str = "cuda"):
        """
        Initialize MedASR for streaming transcription.
        
        Args:
            device: Device to run inference on
        """
        self.device = device
        self.model = None
        self.processor = None
        self.is_listening = False
        self.audio_buffer = []
        self.transcription_callback: Callable[[str], None] | None = None
        self._processing_thread: threading.Thread | None = None
        self._audio_queue: queue.Queue = queue.Queue()
        
        self._load_model()
    
    def _load_model(self):
        """Select and initialise the ASR backend.

        Priority: HF Space → cloud endpoint → local CTC (medasr) → local Whisper fallback.
        """
        # ── Priority 1: HF Space via MEDASR_SPACE_ID ─────────────────────────
        space_id = os.environ.get("MEDASR_SPACE_ID", "").strip()
        if space_id:
            # Convert "owner/space-name" → "https://owner-space-name.hf.space"
            owner, _, space_name = space_id.partition("/")
            slug = f"{owner}-{space_name}".lower()
            self._endpoint_url = f"https://{slug}.hf.space"
            self._hf_token = (
                os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN") or ""
            )
            self._backend = "gradio"
            logger.info(f"MedASR using HF Space: {self._endpoint_url}")
            return

        # ── Priority 2: cloud endpoint via MEDASR_ENDPOINT_URL ───────────────
        endpoint_url = os.environ.get("MEDASR_ENDPOINT_URL", "").strip()
        if endpoint_url:
            self._endpoint_url = endpoint_url
            self._hf_token = (
                os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN") or ""
            )
            self._backend = "cloud"
            logger.info(f"MedASR using cloud endpoint: {endpoint_url}")
            return

        # ── Priority 3: google/medasr local CTC (requires transformers >= 5) ──
        try:
            from transformers import AutoModelForCTC, AutoProcessor  # type: ignore

            logger.info(f"Loading MedASR model: {self.MODEL_ID}")
            self.processor = AutoProcessor.from_pretrained(
                self.MODEL_ID, trust_remote_code=True
            )
            self.model = AutoModelForCTC.from_pretrained(
                self.MODEL_ID,
                torch_dtype=torch.float16,
                trust_remote_code=True,
            ).to(self.device)
            self._backend = "ctc"
            logger.info("google/medasr (CTC) loaded successfully")
            return
        except Exception as e:
            logger.warning(
                f"Could not load google/medasr with AutoModelForCTC: {e}\n"
                "This is expected when transformers < 5.0.0 is installed "
                "(vLLM 0.15.x pins transformers<5). Falling back to Whisper.\n"
                "To use google/medasr set MEDASR_SPACE_ID to a deployed "
                "HuggingFace Space (see spaces/medasr/ in this project)."
            )

        # ── Priority 4: openai/whisper-medium (works with transformers 4.x, ~1.5 GB) ──
        try:
            from transformers import pipeline  # type: ignore

            WHISPER_ID = "openai/whisper-medium"
            logger.info(f"Loading Whisper fallback: {WHISPER_ID}")
            self._pipeline = pipeline(
                "automatic-speech-recognition",
                model=WHISPER_ID,
                torch_dtype=torch.float16,
                device=self.device,
                model_kwargs={"use_safetensors": True},
            )
            self._backend = "whisper"
            self.model = self._pipeline.model      # expose for sleep/wake_up
            self.processor = self._pipeline.tokenizer
            logger.info(f"Whisper fallback ({WHISPER_ID}) loaded successfully")
            return
        except Exception as e:
            logger.error(f"Failed to load Whisper fallback: {e}")
            raise RuntimeError(
                "No ASR backend could be loaded. Options:\n"
                "  • Set MEDASR_SPACE_ID to your HF Space (see spaces/medasr/)\n"
                "  • Set MEDASR_ENDPOINT_URL to a HuggingFace Inference Endpoint\n"
                "  • Install transformers >= 5.0.0 for local google/medasr\n"
                "  • Ensure openai/whisper-medium can be downloaded"
            ) from e

    def sleep(self):
        """Offload model weights to CPU to free GPU memory (mirrors vLLM sleep).
        No-op when using a cloud or Gradio Space backend."""
        if self._backend in ("cloud", "gradio") or self.model is None:
            return
        current_device = next(self.model.parameters()).device
        if current_device.type != "cpu":
            logger.info("MedASR sleeping (moving weights to CPU)")
            self.model = self.model.to("cpu")
            torch.cuda.empty_cache()

    def wake_up(self):
        """Move model weights back to GPU (mirrors vLLM wake_up).
        No-op when using a cloud or Gradio Space backend."""
        if self._backend in ("cloud", "gradio") or self.model is None:
            return
        current_device = next(self.model.parameters()).device
        if current_device.type == "cpu":
            logger.info(f"MedASR waking up (moving weights to {self.device})")
            self.model = self.model.to(self.device)
    
    def start_listening(self, callback: Callable[[str], None]):
        """
        Start listening for audio input.
        
        Args:
            callback: Function to call with transcription results
        """
        self.transcription_callback = callback
        self.is_listening = True
        self.audio_buffer = []
        
        # Start background processing thread
        self._processing_thread = threading.Thread(
            target=self._process_audio_loop,
            daemon=True
        )
        self._processing_thread.start()
        
        logger.info("MedASR listening started")
    
    def stop_listening(self) -> str:
        """
        Stop listening and return final transcription.
        
        Returns:
            Complete transcription of the session
        """
        self.is_listening = False
        
        # Process any remaining audio
        if self.audio_buffer:
            final_text = self._transcribe_buffer()
            return final_text
        
        return ""
    
    def add_audio_chunk(self, audio_data: np.ndarray):
        """
        Add an audio chunk to the processing queue.
        
        Args:
            audio_data: Audio samples as numpy array (16kHz, mono)
        """
        if self.is_listening:
            self._audio_queue.put(audio_data)
    
    def add_audio_bytes(self, audio_bytes: bytes, sample_rate: int = 16000):
        """
        Add raw audio bytes to the processing queue.
        
        Args:
            audio_bytes: Raw audio data (16-bit PCM)
            sample_rate: Sample rate of the audio
        """
        # Convert bytes to numpy array
        audio_data = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        
        # Resample if necessary
        if sample_rate != self.SAMPLE_RATE:
            # Simple resampling (for production, use librosa or scipy)
            ratio = self.SAMPLE_RATE / sample_rate
            new_length = int(len(audio_data) * ratio)
            audio_data = np.interp(
                np.linspace(0, len(audio_data), new_length),
                np.arange(len(audio_data)),
                audio_data
            )
        
        self.add_audio_chunk(audio_data)
    
    def _process_audio_loop(self):
        """Background thread for processing audio chunks."""
        samples_per_chunk = int(self.SAMPLE_RATE * self.CHUNK_DURATION)
        
        while self.is_listening:
            try:
                # Get audio data with timeout
                audio_chunk = self._audio_queue.get(timeout=0.1)
                self.audio_buffer.extend(audio_chunk)
                
                # Process when we have enough samples
                while len(self.audio_buffer) >= samples_per_chunk:
                    chunk = np.array(self.audio_buffer[:samples_per_chunk])
                    self.audio_buffer = self.audio_buffer[samples_per_chunk:]
                    
                    # Transcribe chunk
                    text = self._transcribe_chunk(chunk)
                    
                    if text and self.transcription_callback:
                        self.transcription_callback(text)
                        
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing audio: {e}")
    
    def _transcribe_chunk(self, audio_data: np.ndarray) -> str:
        """
        Transcribe a single audio chunk.

        Args:
            audio_data: Audio samples as numpy array (float32, 16 kHz mono)

        Returns:
            Transcribed text
        """
        try:
            if self._backend == "gradio":
                return self._transcribe_gradio(audio_data)
            elif self._backend == "cloud":
                return self._transcribe_cloud(audio_data)
            elif self._backend == "ctc":
                return self._transcribe_ctc(audio_data)
            else:
                return self._transcribe_whisper(audio_data)
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return ""

    def _transcribe_gradio(self, audio_data: np.ndarray) -> str:
        """Call the HF Space Gradio API using the event-based endpoint.

        Gradio 4.x flow:
          1. POST /gradio_api/call/transcribe  → {"event_id": "abc"}
          2. GET  /gradio_api/call/transcribe/{event_id}  → SSE stream
             Reads until a "process_completed" event and extracts data[0].
        """
        import base64
        import json
        import struct
        import urllib.request

        # Build WAV bytes
        pcm = (audio_data * 32767).clip(-32768, 32767).astype(np.int16)
        pcm_bytes = pcm.tobytes()
        data_size = len(pcm_bytes)
        wav_header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF", 36 + data_size, b"WAVE",
            b"fmt ", 16, 1, 1, self.SAMPLE_RATE,
            self.SAMPLE_RATE * 2, 2, 16,
            b"data", data_size,
        )
        wav_b64 = base64.b64encode(wav_header + pcm_bytes).decode()
        audio_payload = {
            "name": "audio.wav",
            "data": f"data:audio/wav;base64,{wav_b64}",
            "is_file": False,
        }

        base_url = self._endpoint_url.rstrip("/")
        headers: dict = {"Content-Type": "application/json"}
        if self._hf_token:
            headers["Authorization"] = f"Bearer {self._hf_token}"

        # Step 1: submit job
        submit_payload = json.dumps({"data": [audio_payload]}).encode()
        req = urllib.request.Request(
            f"{base_url}/gradio_api/call/transcribe",
            data=submit_payload, headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            event_id = json.loads(resp.read().decode())["event_id"]

        # Step 2: poll SSE stream for result
        result_req = urllib.request.Request(
            f"{base_url}/gradio_api/call/transcribe/{event_id}",
            headers=headers, method="GET"
        )
        with urllib.request.urlopen(result_req, timeout=120) as stream:
            for raw_line in stream:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
                if line.startswith("data:"):
                    payload_str = line[len("data:"):].strip()
                    if not payload_str:
                        continue
                    try:
                        payload = json.loads(payload_str)
                    except json.JSONDecodeError:
                        continue
                    # Gradio sends {"msg": "process_completed", "output": {"data": [...]}}
                    if isinstance(payload, dict) and payload.get("msg") == "process_completed":
                        return payload["output"]["data"][0].strip()
                    # Older SSE format: {"data": ["text"]}
                    if isinstance(payload, dict) and "data" in payload:
                        return payload["data"][0].strip()

        return ""

    def _transcribe_cloud(self, audio_data: np.ndarray) -> str:
        """Send audio to the HuggingFace Inference Endpoint and return the transcript.

        The endpoint receives raw WAV bytes and returns {"text": "..."}.
        Uses the stdlib urllib so no extra dependencies are required.
        """
        import struct
        import urllib.request

        # Build a minimal WAV file in memory (PCM 16-bit, 16 kHz, mono)
        pcm = (audio_data * 32767).clip(-32768, 32767).astype(np.int16)
        pcm_bytes = pcm.tobytes()
        num_channels = 1
        bits_per_sample = 16
        byte_rate = self.SAMPLE_RATE * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        data_size = len(pcm_bytes)
        # 44-byte standard WAV header
        wav_header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF", 36 + data_size, b"WAVE",
            b"fmt ", 16, 1, num_channels, self.SAMPLE_RATE,
            byte_rate, block_align, bits_per_sample,
            b"data", data_size,
        )
        wav_bytes = wav_header + pcm_bytes

        headers = {"Content-Type": "audio/wav"}
        if self._hf_token:
            headers["Authorization"] = f"Bearer {self._hf_token}"

        req = urllib.request.Request(
            self._endpoint_url, data=wav_bytes, headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            import json
            result = json.loads(resp.read().decode())

        # HF Inference Endpoints return {"text": "..."} for ASR models
        return result.get("text", "").strip()

    def _transcribe_ctc(self, audio_data: np.ndarray) -> str:
        """CTC inference for google/medasr (transformers >= 5)."""
        model_device = next(self.model.parameters()).device
        inputs = self.processor(
            audio_data,
            sampling_rate=self.SAMPLE_RATE,
            return_tensors="pt",
        ).to(model_device)

        with torch.inference_mode():
            logits = self.model(**inputs).logits

        # CTC decoding: argmax over vocabulary dimension
        predicted_ids = torch.argmax(logits, dim=-1)
        text = self.processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]
        return text.strip()

    def _transcribe_whisper(self, audio_data: np.ndarray) -> str:
        """Whisper pipeline inference for the transformers 4.x fallback."""
        result = self._pipeline(
            {"array": audio_data, "sampling_rate": self.SAMPLE_RATE},
            return_timestamps=False,
        )
        return result["text"].strip()
    
    def _transcribe_buffer(self) -> str:
        """Transcribe all remaining audio in buffer."""
        if not self.audio_buffer:
            return ""
        
        audio_data = np.array(self.audio_buffer)
        return self._transcribe_chunk(audio_data)
    
    def transcribe_file(self, audio_path: str) -> str:
        """
        Transcribe an audio file (WAV only — browser sends 16-bit mono WAV).

        Uses the stdlib `wave` module (no extra dependencies).
        Resamples to 16 kHz via scipy if the file sample rate differs.

        Args:
            audio_path: Path to a WAV file

        Returns:
            Complete transcription
        """
        import wave

        with wave.open(audio_path, "rb") as wf:
            sample_rate = wf.getframerate()
            n_channels  = wf.getnchannels()
            raw_bytes   = wf.readframes(wf.getnframes())

        audio_data = np.frombuffer(raw_bytes, dtype=np.int16)

        # Downmix to mono if needed
        if n_channels > 1:
            audio_data = (
                audio_data.reshape(-1, n_channels).mean(axis=1).astype(np.int16)
            )

        audio_float = audio_data.astype(np.float32) / 32768.0

        # Resample to target rate if needed
        if sample_rate != self.SAMPLE_RATE:
            from scipy import signal as scipy_signal
            audio_float = scipy_signal.resample(
                audio_float,
                int(len(audio_float) * self.SAMPLE_RATE / sample_rate),
            )

        return self._transcribe_chunk(audio_float.astype(np.float32))


class SimulatedMedASR:
    """
    Simulated MedASR for demo/testing without loading the actual model.
    Useful for UI development and when MedASR is not available.
    """
    
    def __init__(self):
        self.is_listening = False
        self.transcription_callback = None
        self._demo_text_queue = []
    
    def start_listening(self, callback: Callable[[str], None]):
        """Start simulated listening."""
        self.transcription_callback = callback
        self.is_listening = True
        logger.info("Simulated MedASR listening started")
    
    def stop_listening(self) -> str:
        """Stop simulated listening."""
        self.is_listening = False
        return ""
    
    def simulate_dictation(self, text: str, chunk_size: int = 20):
        """
        Simulate dictation by feeding text in chunks.
        
        Args:
            text: Full dictation text
            chunk_size: Approximate words per chunk
        """
        words = text.split()
        chunks = []
        
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i + chunk_size])
            chunks.append(chunk)
        
        self._demo_text_queue = chunks
    
    async def feed_demo_chunks(self, delay: float = 2.0):
        """Async generator to feed demo chunks with delay."""
        for chunk in self._demo_text_queue:
            if self.transcription_callback and self.is_listening:
                self.transcription_callback(chunk)
            await asyncio.sleep(delay)
    
    def add_audio_bytes(self, audio_bytes: bytes, sample_rate: int = 16000):
        """Placeholder for audio bytes (simulated mode ignores actual audio)."""
        pass
