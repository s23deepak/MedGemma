"""
MedASR Streaming Integration
Real-time medical speech recognition using Google's MedASR model.
"""

import asyncio
import logging
import queue
import threading
from typing import AsyncGenerator, Callable

import numpy as np
import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

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
        """Load MedASR model with explicit device placement (no device_map='auto')
        so that sleep()/wake_up() can freely move weights between CPU and GPU."""
        logger.info(f"Loading MedASR model: {self.MODEL_ID}")

        self.processor = AutoProcessor.from_pretrained(
            self.MODEL_ID,
            trust_remote_code=True
        )

        self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
            self.MODEL_ID,
            torch_dtype=torch.float16,
            trust_remote_code=True
        ).to(self.device)

        logger.info("MedASR model loaded successfully")

    def sleep(self):
        """Offload model weights to CPU to free GPU memory (mirrors vLLM sleep)."""
        if self.model is None:
            return
        current_device = next(self.model.parameters()).device
        if current_device.type != "cpu":
            logger.info("MedASR sleeping (moving weights to CPU)")
            self.model = self.model.to("cpu")
            torch.cuda.empty_cache()

    def wake_up(self):
        """Move model weights back to GPU (mirrors vLLM wake_up)."""
        if self.model is None:
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
            audio_data: Audio samples as numpy array
            
        Returns:
            Transcribed text
        """
        try:
            model_device = next(self.model.parameters()).device
            inputs = self.processor(
                audio_data,
                sampling_rate=self.SAMPLE_RATE,
                return_tensors="pt"
            ).to(model_device)
            
            with torch.inference_mode():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=256,
                    language="en"
                )
            
            text = self.processor.batch_decode(
                outputs,
                skip_special_tokens=True
            )[0]
            
            return text.strip()
            
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return ""
    
    def _transcribe_buffer(self) -> str:
        """Transcribe all remaining audio in buffer."""
        if not self.audio_buffer:
            return ""
        
        audio_data = np.array(self.audio_buffer)
        return self._transcribe_chunk(audio_data)
    
    def transcribe_file(self, audio_path: str) -> str:
        """
        Transcribe an audio file.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Complete transcription
        """
        import soundfile as sf
        
        audio_data, sample_rate = sf.read(audio_path)
        
        # Convert to mono if stereo
        if len(audio_data.shape) > 1:
            audio_data = audio_data.mean(axis=1)
        
        # Resample if needed
        if sample_rate != self.SAMPLE_RATE:
            from scipy import signal
            audio_data = signal.resample(
                audio_data,
                int(len(audio_data) * self.SAMPLE_RATE / sample_rate)
            )
        
        return self._transcribe_chunk(audio_data.astype(np.float32))


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
