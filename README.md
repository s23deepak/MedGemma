# MedGemma Clinical Assistant

AI-powered clinical decision support system using MedGemma and MedASR.

## Quick Start

```bash
# Simulated mode (no GPU required)
SIMULATED_MODE=true uv run python main.py

# Full mode (requires MedGemma + MedASR access)
uv run python main.py
```

Open: http://localhost:8000

## Features

- 🎤 **Real-time Speech Recognition** — MedASR listens to physician dictation
- 🩻 **Medical Image Analysis** — MedGemma analyzes X-rays, CT, MRI with artifact detection
- 📋 **SOAP Note Generation** — Automatic clinical documentation with ICD-10 codes
- ⚠️ **Missed Diagnosis Detection** — AI highlights potential concerns and critical alerts
- 🏥 **EHR Integration** — FHIR-based patient data with physician approval workflow
- 🧠 **Diagnostic Council** — 5 independent AI opinions with consensus scoring
- 📚 **PubMed Literature Search** — Real-time case matching, EBM validation, DDI monitoring
- 💬 **AI Chat Portal** — Multimodal physician chat with image annotation and voice input
- 📊 **SOAP Compliance Monitor** — Symptom duration flags and documentation rate tracking
- 👤 **Patient Portal** — Patient-facing Q&A with emergency detection and safety guardrails
- 🧬 **Patient Memory (Mem0)** — Persistent cross-encounter memory powered by Mem0
- 🔐 **Role-Based Access** — Doctor, Nurse, Resident, Admin, and Patient roles

## Architecture

```
MedASR (Speech) ─┐
                 ├─→ FunctionGemma Router ─→ MedGemma 4B ─→ SOAP Generator ─→ Doctor Approval ─→ EHR
Medical Image ───┘         ↑                     ↑
                           │                     │
                   FHIR EHR Context        PubMed Literature
                   Mem0 Memory Recall      Clinical Correlation
```

## Project Structure

```
├── main.py               # FastAPI server (all routes)
├── AGENTS.md             # Agent and tool definitions
├── src/
│   ├── agent/            # MedGemma agent, tools, clinical correlation
│   ├── asr/              # MedASR streaming
│   ├── auth/             # Role-based access control
│   ├── clinical/         # ICD-10, drug interactions, critical alerts
│   ├── compliance/       # SOAP compliance monitoring
│   ├── council/          # Diagnostic Council (multi-rollout deliberation)
│   ├── ehr/              # Mock FHIR server
│   ├── history/          # Patient timeline and history service
│   ├── memory/           # Mem0 patient memory integration
│   ├── portal/           # Patient-facing portal with guardrails
│   ├── pubmed/           # PubMed NCBI E-utils client + synthesis agent
│   └── soap/             # SOAP note generation
├── static/               # Frontend UI (app.js, ai_portal.js, styles.css)
├── templates/            # Jinja2 HTML templates
├── docs/                 # Architecture, technical write-up, testing guide
└── data/                 # Sample images and seed data
```

## Requirements

- Python 3.11+
- NVIDIA GPU with 8GB+ VRAM (for full mode)
- HuggingFace access to `google/medgemma-1.5-4b-it` and `google/medasr`
- `OPENAI_API_KEY` env var (for Mem0 memory extraction — optional, graceful fallback)
- `NCBI_API_KEY` env var (for PubMed 10 req/s — optional, defaults to 3 req/s)

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SIMULATED_MODE` | No | Run without GPU (all AI responses simulated) |
| `OPENAI_API_KEY` | No | Enables Mem0 patient memory extraction |
| `NCBI_API_KEY` | No | Raises PubMed rate limit from 3 to 10 req/s |
| `MEDASR_SPACE_ID` | No | HuggingFace Space ID for MedASR transcription |

## Competition

Built for the [MedGemma Impact Challenge](https://www.kaggle.com/competitions/med-gemma-impact-challenge) on Kaggle.

## License

CC BY 4.0 (per competition requirements)
