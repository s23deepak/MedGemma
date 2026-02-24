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
- 🌍 **Location-Aware Trend Correlation** — Correlates local public-health/environment events with same-day symptoms
- 🧾 **External Medical Vocabulary** — NLM MeSH enrichment with shared Firestore cache and optional vector expansion
- 💬 **AI Chat Portal** — Multimodal physician chat with image annotation and voice input
- 📊 **SOAP Compliance Monitor** — Symptom duration flags and documentation rate tracking
- 👤 **Patient Portal** — Patient-facing Q&A with emergency detection and safety guardrails
- 🧬 **Patient Memory (Mem0)** — Persistent cross-encounter memory powered by Mem0
- 🔐 **Role-Based Access** — Doctor, Nurse, Resident, Admin, and Patient roles
- 🔄 **Inpatient Rounding Copilot** — 24-hour SOAP progress notes with to-do checklists per admitted patient
- 📋 **SBAR Handoff Generator** — Structured shift sign-out with automated completeness audit (code status, allergies, high-risk meds, contingency plans)
- 🚨 **Inpatient Safety Watchlist** — Rule-based alerts for VTE prophylaxis gaps, Foley dwell time, high-risk med monitoring, and overdue documentation
- 🏠 **Discharge Planner** — Patient-friendly discharge summaries with readmission risk scoring (HIGH/MEDIUM/LOW) and MISSING-field enforcement

## Architecture

```
MedASR (Speech) ─┐
                 ├─→ FunctionGemma Router ─→ MedGemma 4B ─→ SOAP Generator ─→ Doctor Approval ─→ EHR
Medical Image ───┘         ↑                     ↑
                           │                     │
                   FHIR EHR Context        PubMed Literature
                   Mem0 Memory Recall      Clinical Correlation + Local Trends
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
│   ├── trends/           # Local health trends + external medical vocabulary
│   ├── inpatient/        # Rounding, SBAR handoff, safety watchlist, discharge planner
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
| `MEDICAL_VOCAB_CACHE_BACKEND` | No | Medical vocab cache backend: `auto` (default), `firestore`, or `local` |
| `MEDICAL_VOCAB_VECTOR_BACKEND` | No | Semantic enrichment backend: `in_memory` (default) or `none` |
| `DISABLE_EXTERNAL_MEDICAL_VOCAB` | No | Disable external vocabulary calls and use local/ICD fallback only |

## Competition

Built for the [MedGemma Impact Challenge](https://www.kaggle.com/competitions/med-gemma-impact-challenge) on Kaggle.

## License

CC BY 4.0 (per competition requirements)
