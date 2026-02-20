# MedGemma Clinical Assistant - Technical Write-up

## Executive Summary

The **MedGemma Clinical Assistant** is an AI-powered clinical decision support system that integrates MedGemma for multimodal reasoning, speech recognition for physician dictation, and a FHIR-compatible mock EHR. The system is designed for the MedGemma Impact Challenge.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Frontend (HTML/JS/CSS)                       │
│  • Real-time transcription display                              │
│  • Medical image upload                                         │
│  • SOAP note preview & approval                                 │
└────────────────────┬───────────────────────────────────────────┘
                     │ WebSocket / REST
┌────────────────────▼───────────────────────────────────────────┐
│                    FastAPI Backend                              │
│  • /api/encounters/* - Clinical encounter management            │
│  • /ws/audio/* - Real-time audio streaming                      │
│  • /api/patients/* - FHIR EHR access                            │
└────────────────────┬───────────────────────────────────────────┘
                     │
    ┌────────────────┼────────────────┬───────────────────────────┐
    ▼                ▼                ▼                           ▼
┌────────┐    ┌───────────┐    ┌────────────┐    ┌───────────────────┐
│MedGemma│    │  MedASR   │    │ Mock FHIR  │    │Clinical           │
│ Agent  │    │ Streaming │    │   Server   │    │Intelligence       │
├────────┤    ├───────────┤    ├────────────┤    ├───────────────────┤
│• Image │    │• Real-time│    │• 2 test    │    │• ICD-10 codes     │
│  anlys │    │  audio    │    │  patients  │    │• Drug interaction │
│• SOAP  │    │• Whisper  │    │• Conditions│    │• Critical alerts  │
│  gen   │    │  fallback │    │• Meds      │    │• Differentials    │
└────────┘    └───────────┘    └────────────┘    └───────────────────┘
```

---

## Key Components

### 1. MedGemma Agent (`src/agent/`)

| Component | Description |
|-----------|-------------|
| `medgemma_agent.py` | HuggingFace Transformers with 4-bit quantization |
| `vllm_agent.py` | **NEW** vLLM backend for 2-3x faster inference |
| `tools.py` | Function-calling tool definitions |

**Memory Optimization:**
- 4-bit NF4 quantization via BitsAndBytes
- Fits in 8GB VRAM (RTX 5060 compatible)

### 2. Clinical Intelligence (`src/clinical/`)

Six enhanced features:

| Feature | Implementation |
|---------|----------------|
| ICD-10 Codes | 30+ diagnosis mappings |
| Confidence Scores | 0-100% with evidence |
| Critical Alerts | PE, Mass, Sepsis detection |
| Drug Interactions | 20+ interaction pairs |
| Differential Ranking | Top 5 ranked by confidence |
| Evidence Citations | Source → SOAP linking |

### 3. SOAP Note Generation (`src/soap/`)

- `SOAPNote` - Basic structured note
- `EnhancedSOAPNote` - Full clinical intelligence
- Parses MedGemma output into sections
- HTML/Markdown rendering

### 4. Mock FHIR EHR (`src/ehr/`)

Two demo patients:
- **P001**: Sarah Wilson (55F) - Hypertension, Asthma
- **P002**: Carlos Martinez (70M) - Diabetes, COPD

---

## Performance

| Backend | Load Time | Inference | VRAM |
|---------|-----------|-----------|------|
| Transformers (4-bit) | ~30s | ~5s/response | ~6GB |
| vLLM | ~20s | ~2s/response | ~7GB |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/patients` | List all patients |
| GET | `/api/patients/{id}` | Get patient summary |
| POST | `/api/encounters/start` | Start encounter |
| POST | `/api/encounters/{id}/image` | Upload X-ray |
| POST | `/api/encounters/{id}/generate-soap` | Generate SOAP |
| POST | `/api/encounters/{id}/approve` | Approve to EHR |

---

## Running the Demo

```bash
# Install and run
cd /home/deepu/MedGemma
uv sync
uv run python main.py

# With vLLM (faster)
uv run python main.py --use-vllm

# Simulated mode (no GPU)
SIMULATED_MODE=true uv run python main.py
```

Open http://localhost:8000 in browser.

---

## Future Work

1. **Production MedASR** - Replace simulated speech recognition
2. **Real FHIR Integration** - Connect to Epic/Cerner
3. **HL7 CDA Export** - Standards-compliant documentation
4. **Multi-GPU Scaling** - vLLM tensor parallelism

---

## Competition Compliance

- ✅ Uses MedGemma 1.5 4B IT
- ✅ Demonstrates multimodal (image + text)
- ✅ Clinical decision support use case
- ✅ Structured output (SOAP notes)
- ✅ EHR integration pattern
