"""
Gemini Cloud API agent for MedGemma AI Chat Portal.

Provides fast inference via Google's Gemini API as an alternative to local vLLM.
Supports both streaming and non-streaming generation, plus vision (image analysis).

Usage:
    GEMINI_API_KEY=<key> python main.py
    # Optionally: GEMINI_MODEL=gemini-2.0-flash (default)
"""

import logging
import os
import time
from collections import deque
from typing import Generator

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
    from google.generativeai.types import GenerationConfig
    GEMINI_AVAILABLE = True
except ImportError:
    genai = None
    GenerationConfig = None
    GEMINI_AVAILABLE = False


def is_gemini_available() -> bool:
    """Check if Gemini SDK is installed and API key is configured."""
    return GEMINI_AVAILABLE and bool(os.environ.get("GEMINI_API_KEY"))


SYSTEM_PROMPT = (
    "You are MedGemma, a clinical AI assistant helping Doctors and Residents. "
    "Provide accurate, evidence-based clinical insights. "
    "Always note diagnostic uncertainty and recommend clinical correlation. "
    "IMPORTANT: Only analyze medical images when an actual image is provided in the current message. "
    "If the user asks about an image but none was uploaded, ask them to upload it first. "
    "Do NOT fabricate or hallucinate image analyses. "
    "RESPONSE FORMAT: Use ## headers for sections, bullet lists (-) for findings, and **bold** for key clinical terms. "
    "At the very end of your response, append exactly this JSON on its own line (no code fences): "
    '{"clinical_meta": {"key_points": ["..."], "warnings": [], "confidence": "high|moderate|low", "suggested_actions": ["..."]}}'
)


class GeminiAgent:
    """Gemini Cloud API wrapper, duck-type compatible with VLLMModelManager."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.0-flash",
    ):
        if not GEMINI_AVAILABLE:
            raise ImportError(
                "google-generativeai not installed. "
                "Run: uv pip install 'medgemma-assistant[gemini]'"
            )

        genai.configure(api_key=api_key)
        self.model_name = model_name
        self.model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=SYSTEM_PROMPT,
        )
        self.default_generation_config = GenerationConfig(
            temperature=0.4,
            top_p=0.9,
            max_output_tokens=768,
        )
        self._inference_stats: deque[dict] = deque(maxlen=100)
        logger.info(f"GeminiAgent initialized with model={model_name}")

    def generate_medgemma(
        self,
        prompt: str,
        image=None,
        temperature: float = 0.4,
        max_tokens: int = 2048,
        stop: list[str] | None = None,
    ) -> str:
        """Generate a full response (non-streaming). Compatible with VLLMModelManager."""
        config = GenerationConfig(
            temperature=temperature,
            top_p=0.9,
            max_output_tokens=max_tokens,
        )
        contents = self._build_contents(prompt, image)

        try:
            t0 = time.time()
            response = self.model.generate_content(contents, generation_config=config)
            elapsed = time.time() - t0
            self._record_stats(response, elapsed, max_tokens, multimodal=image is not None)
            return response.text
        except Exception as e:
            logger.error(f"Gemini generation failed: {e}")
            raise

    def generate_medgemma_stream(
        self,
        prompt: str,
        image=None,
        temperature: float = 0.4,
        max_tokens: int = 2048,
    ) -> Generator[str, None, None]:
        """Stream response chunk-by-chunk. Records stats after final chunk."""
        config = GenerationConfig(
            temperature=temperature,
            top_p=0.9,
            max_output_tokens=max_tokens,
        )
        contents = self._build_contents(prompt, image)

        try:
            t0 = time.time()
            response = self.model.generate_content(contents, generation_config=config, stream=True)
            for chunk in response:
                if chunk.text:
                    yield chunk.text
            # Record stats after stream completes (usage_metadata available at end)
            elapsed = time.time() - t0
            self._record_stats(response, elapsed, max_tokens, multimodal=image is not None)
        except Exception as e:
            logger.error(f"Gemini streaming failed: {e}")
            yield f"\n\n[Error: Gemini API returned: {e}]"

    def chat(self, message: str, history: list[dict] | None = None) -> str:
        """Text-only chat. Compatible with MedGemmaAgent.chat()."""
        return self.generate_medgemma(prompt=message)

    def get_inference_stats(self) -> dict:
        """Return aggregated token usage stats over the last 100 requests."""
        if not self._inference_stats:
            return {"requests": 0}
        stats = list(self._inference_stats)
        n = len(stats)
        avg = lambda key: round(sum(s[key] for s in stats) / n, 1)
        mx = lambda key: max(s[key] for s in stats)
        return {
            "requests": n,
            "backend": "gemini",
            "model": self.model_name,
            "avg_prompt_tokens": avg("prompt_tokens"),
            "avg_completion_tokens": avg("completion_tokens"),
            "avg_total_tokens": avg("total_tokens"),
            "max_completion_tokens": mx("completion_tokens"),
            "avg_latency_s": avg("latency_s"),
            "multimodal_requests": sum(1 for s in stats if s["multimodal"]),
            "recent_10": stats[-10:],
        }

    def _record_stats(self, response, elapsed: float, max_tokens: int, multimodal: bool):
        """Extract usage metadata from Gemini response and store stats."""
        try:
            usage = response.usage_metadata
            prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
            completion_tokens = getattr(usage, "candidates_token_count", 0) or 0
            self._inference_stats.append({
                "ts": time.time(),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "max_tokens_configured": max_tokens,
                "latency_s": round(elapsed, 2),
                "tokens_per_sec": round(completion_tokens / elapsed, 1) if elapsed > 0 else 0,
                "multimodal": multimodal,
            })
        except Exception:
            pass  # Non-fatal

    def _build_contents(self, prompt: str, image=None) -> list:
        """Build Gemini content parts from prompt + optional PIL image."""
        if image is not None:
            return [image, prompt]
        return [prompt]
