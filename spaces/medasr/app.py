"""
MedASR HuggingFace Space
Medical Speech Recognition using google/medasr (105M CTC model).

Exposes:
  - Interactive Gradio UI  (microphone / file upload)
  - Programmatic API       (api_name="transcribe", called by medasr_streaming.py)

ZeroGPU: decorated with @spaces.GPU when the `spaces` package is available
(requires GPU-enabled Space tier on HuggingFace).  Falls back to CPU automatically.
"""

import logging

import numpy as np
import torch
import gradio as gr
from transformers import AutoModelForCTC, AutoProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── ZeroGPU (optional) ───────────────────────────────────────────────────────
try:
    import spaces  # type: ignore
    HAS_ZERO_GPU = True
    logger.info("ZeroGPU available — GPU bursts will be used for inference")
except ImportError:
    HAS_ZERO_GPU = False
    logger.info("Running on CPU (ZeroGPU not available)")

# ── Load model ───────────────────────────────────────────────────────────────
MODEL_ID = "google/medasr"
SAMPLE_RATE = 16_000

logger.info(f"Loading {MODEL_ID} ...")
processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
model = AutoModelForCTC.from_pretrained(MODEL_ID, trust_remote_code=True)
model.eval()
logger.info(f"{MODEL_ID} loaded — parameters: {sum(p.numel() for p in model.parameters()):,}")


# ── Core inference (CPU) ─────────────────────────────────────────────────────
def _run_ctc(audio_np: np.ndarray, sr: int) -> str:
    """CTC argmax inference — runs on whichever device the model is on."""
    if audio_np.ndim > 1:
        audio_np = audio_np.mean(axis=1)

    audio_np = audio_np.astype(np.float32)
    # Normalise int16 PCM → float32 [-1, 1]
    if audio_np.max() > 1.0:
        audio_np = audio_np / 32_768.0

    device = next(model.parameters()).device
    inputs = processor(audio_np, sampling_rate=sr, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.inference_mode():
        logits = model(**inputs).logits

    predicted_ids = torch.argmax(logits, dim=-1)
    return processor.batch_decode(predicted_ids, skip_special_tokens=True)[0].strip()


# ── Transcription function (with optional ZeroGPU) ───────────────────────────
if HAS_ZERO_GPU:
    @spaces.GPU
    def transcribe(audio: tuple) -> str:
        """Transcribe audio — GPU burst via ZeroGPU."""
        if audio is None:
            return ""
        sr, data = audio
        model.to("cuda")
        result = _run_ctc(data, sr)
        model.to("cpu")
        torch.cuda.empty_cache()
        return result
else:
    def transcribe(audio: tuple) -> str:
        """Transcribe audio — CPU inference."""
        if audio is None:
            return ""
        sr, data = audio
        return _run_ctc(data, sr)


# ── Gradio UI ─────────────────────────────────────────────────────────────────
with gr.Blocks(title="MedASR — Medical Speech Recognition") as demo:
    gr.Markdown(
        """
        # 🏥 MedASR — Medical Speech Recognition
        **Model:** `google/medasr` · 105M parameters · CTC architecture · Trained on medical audio

        Record or upload clinical audio to transcribe it.
        """
    )

    with gr.Row():
        with gr.Column():
            audio_input = gr.Audio(
                label="Clinical Audio",
                sources=["microphone", "upload"],
                type="numpy",
            )
            transcribe_btn = gr.Button("Transcribe", variant="primary")

        with gr.Column():
            text_output = gr.Textbox(
                label="Transcription",
                lines=6,
                placeholder="Transcription will appear here …",
            )

    transcribe_btn.click(
        fn=transcribe,
        inputs=audio_input,
        outputs=text_output,
        api_name="transcribe",   # ← stable API endpoint name used by MedGemma app
    )

    # Also trigger on audio stop-recording for live feel
    audio_input.stop_recording(
        fn=transcribe,
        inputs=audio_input,
        outputs=text_output,
    )

    gr.Markdown(
        """
        ---
        ### Programmatic API
        Set `MEDASR_SPACE_ID=your-username/medasr` in your MedGemma `.env`.
        The app calls `POST /gradio_api/call/transcribe` automatically.
        """
    )

if __name__ == "__main__":
    demo.launch()
