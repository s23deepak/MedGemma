# MedGemma Clinical Assistant — Technical Write-up

## Executive Summary

The **MedGemma Clinical Assistant** is an AI-powered clinical decision support system that integrates MedGemma for multimodal reasoning, speech recognition for physician dictation, and a FHIR-compatible EHR. It features imaging artifact detection, clinical correlation analysis, a multi-opinion Diagnostic Council, SOAP compliance monitoring, a patient-facing portal with safety guardrails, and persistent patient memory powered by Mem0.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Frontend (HTML/JS/CSS)                            │
│  • Real-time transcription   • Medical image upload                 │
│  • SOAP note preview         • Patient history timeline             │
│  • Compliance dashboard      • Diagnostic council panel             │
│  • Patient portal            • Role-based navigation                │
└───────────────────────┬─────────────────────────────────────────────┘
                        │ WebSocket / REST
┌───────────────────────▼─────────────────────────────────────────────┐
│                    FastAPI Backend (main.py)                         │
│  • /api/encounters/*    - Clinical encounter management             │
│  • /api/patients/*      - FHIR EHR access                           │
│  • /api/compliance/*    - SOAP compliance checks                    │
│  • /api/council/*       - Diagnostic council deliberation           │
│  • /api/portal/*        - Patient-facing Q&A                        │
│  • /api/history/*       - Patient timeline & records                │
│  • /api/memory/*        - Persistent patient memory (Mem0)          │
│  • /api/health          - System health check                       │
│  • /ws/audio/*          - Audio streaming                           │
└───────────────────────┬─────────────────────────────────────────────┘
                        │
  ┌──────────┬──────────┼──────────┬───────────┬────────────┐
  ▼          ▼          ▼          ▼           ▼            ▼
┌──────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐
│Med   │ │Med     │ │Mock    │ │Clinical│ │Clinical│ │Diagnostic│
│Gemma │ │ASR     │ │FHIR    │ │Intel   │ │Correlat│ │Council   │
│Agent │ │Stream  │ │Server  │ │        │ │ion     │ │          │
├──────┤ ├────────┤ ├────────┤ ├────────┤ ├────────┤ ├──────────┤
│Image │ │Real-   │ │Patient │ │ICD-10  │ │Artifact│ │5 Indep.  │
│Anlys │ │time    │ │records │ │Drug Ix │ │Detect  │ │Opinions  │
│SOAP  │ │audio   │ │CRUD    │ │Crit    │ │Finding │ │Consensus │
│Gen   │ │Whisper │ │        │ │Alerts  │ │Classif │ │Strength  │
└──────┘ └────────┘ └────────┘ └────────┘ └────────┘ └──────────┘

  ┌──────────┬──────────┬──────────┬────────────┐
  ▼          ▼          ▼          ▼            ▼
┌──────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐
│SOAP  │ │Patient │ │Patient │ │Patient │ │Auth /    │
│Compl │ │Portal  │ │History │ │Memory  │ │RBAC      │
│iance │ │        │ │        │ │(Mem0)  │ │          │
├──────┤ ├────────┤ ├────────┤ ├────────┤ ├──────────┤
│Sympt │ │Emerg   │ │Time-   │ │Cross-  │ │4 Roles   │
│Flags │ │Detect  │ │line    │ │Encntr  │ │Feature   │
│Rates │ │Guard-  │ │Meds &  │ │Recall  │ │Perms     │
│      │ │rails   │ │Imaging │ │Extract │ │          │
└──────┘ └────────┘ └────────┘ └────────┘ └──────────┘
```

---

## Key Components

### 1. MedGemma Agent (`src/agent/`)

| Component | Description |
|-----------|-------------|
| `healthcare_agent.py` | Main agent with dual-model routing, tool execution, Mem0 integration |
| `medgemma_agent.py` | HuggingFace Transformers with 4-bit quantization |
| `vllm_agent.py` | vLLM backend for 2-3x faster inference |
| `function_gemma.py` | Lightweight 270M tool router |
| `tools.py` | 9 function-calling tool definitions |
| `clinical_correlation.py` | Imaging artifact detection & finding classification |

**Memory Optimization:**
- 4-bit NF4 quantization via BitsAndBytes
- Fits in 8GB VRAM (RTX 5060 compatible)

### 2. Clinical Intelligence (`src/clinical/`)

| Feature | Implementation |
|---------|----------------|
| ICD-10 Codes | 30+ diagnosis mappings |
| Confidence Scores | 0-100% with evidence |
| Critical Alerts | PE, Mass, Sepsis, Pneumothorax detection |
| Drug Interactions | 20+ interaction pairs with severity levels |
| Differential Ranking | Top 5 ranked by confidence |
| Evidence Citations | Source → SOAP linking |

### 3. Clinical Correlation (`src/agent/clinical_correlation.py`)

| Feature | Implementation |
|---------|----------------|
| Artifact Detection | Motion, metal, positioning, exposure, aliasing, truncation |
| Image Quality | Diagnostic / Acceptable / Degraded / Non-Diagnostic |
| Finding Classification | Critical / Significant / Incidental / Artifact |
| Prevalence Database | 20+ entries from peer-reviewed radiology literature |
| Symptom-Region Mapping | 7 body regions with expected symptoms |
| Incidental Reporting | Prevalence notes for asymptomatic populations |

### 4. SOAP Note Generation (`src/soap/`)

- `SOAPNote` — Basic structured note
- `EnhancedSOAPNote` — Full clinical intelligence integration
- Parses MedGemma output into S/O/A/P sections
- HTML, Markdown, and dict rendering

### 5. SOAP Compliance (`src/compliance/`)

- Symptom duration threshold monitoring
- Documentation update frequency tracking
- Per-patient compliance flags with severity levels
- Aggregate compliance rate reporting

### 6. Diagnostic Council (`src/council/`)

- 5 independent diagnostic opinions per case
- Consensus strength scoring (Strong / Moderate / Weak / Split)
- Accepts symptoms, patient history, and imaging findings
- Deliberation history tracking

### 7. Patient Portal (`src/portal/`)

- Emergency keyword detection (chest pain, seizure, bleeding, etc.)
- Medical guardrails (prevents dosage/medication modification advice)
- Query categorization (medication, symptoms, appointment, general)
- Query history per patient
- Appointment summary generation

### 8. Patient Memory (`src/memory/`)

- Powered by Mem0 with OpenAI for fact extraction
- 12 methods: `add_encounter()`, `recall()`, `get_allergies()`, `get_medications()`, etc.
- Auto-recall past context during encounters
- Category-based retrieval: diagnoses, allergies, medications, preferences
- Graceful fallback when OPENAI_API_KEY is not set

### 9. Authentication (`src/auth/`)

| Role | Features |
|------|----------|
| Doctor | History, Compliance, Council, Encounters, Portal |
| Nurse | History, Encounters, Portal |
| Admin | All features |
| Patient | Patient Portal only |

### 10. Mock FHIR EHR (`src/ehr/`)

Two demo patients:
- **P001**: Sarah Wilson (55F) — Hypertension, Asthma
- **P002**: Carlos Martinez (70M) — Diabetes, COPD

### 11. Patient History (`src/history/`)

- Timeline view of patient encounters
- Medication history tracking
- Imaging history with results

---

## Performance

| Backend | Load Time | Inference | VRAM |
|---------|-----------|-----------|------|
| Transformers (4-bit) | ~30s | ~5s/response | ~6GB |
| vLLM | ~20s | ~2s/response | ~7GB |
| Simulated (no GPU) | instant | instant | 0 |

---

## API Endpoints

### Encounter Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/patients` | List all patients |
| GET | `/api/patients/{id}` | Get patient summary |
| POST | `/api/encounters/start` | Start clinical encounter |
| POST | `/api/encounters/{id}/image` | Upload X-ray image |
| POST | `/api/encounters/{id}/transcription` | Add transcription text |
| POST | `/api/encounters/{id}/generate-soap` | Generate SOAP note |
| POST | `/api/encounters/{id}/approve` | Approve note to EHR |

### Clinical Features

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/history/{id}/timeline` | Patient encounter timeline |
| GET | `/api/history/{id}/medications` | Medication history |
| GET | `/api/history/{id}/imaging` | Imaging history |
| POST | `/api/compliance/check` | Run compliance check |
| GET | `/api/compliance/report` | Get compliance report |
| POST | `/api/council/deliberate` | Diagnostic council deliberation |
| GET | `/api/council/history` | Past deliberations |

### Patient Portal

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/portal/{id}/summary` | Patient summary |
| POST | `/api/portal/ask` | Ask a health question |
| GET | `/api/portal/{id}/history` | Query history |

### Patient Memory (Mem0)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/memory/{id}` | Get all memories |
| POST | `/api/memory/{id}/search` | Search memories |
| POST | `/api/memory/{id}/add` | Add clinical note |
| DELETE | `/api/memory/{id}/{mem_id}` | Delete specific memory |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check with component status |

---

## Testing

72 tests across 10 test files covering all 12 modules:

| Test File | Tests | Module |
|-----------|-------|--------|
| `test_fhir_ehr.py` | 5 | EHR |
| `test_clinical_intelligence.py` | 8 | Clinical Intel |
| `test_clinical_correlation.py` | 8 | Clinical Correlation |
| `test_soap_generator.py` | 6 | SOAP |
| `test_compliance.py` | 5 | Compliance |
| `test_council.py` | 5 | Diagnostic Council |
| `test_patient_portal.py` | 7 | Patient Portal |
| `test_auth.py` | 6 | Auth |
| `test_healthcare_agent.py` | 11 | Agent Integration |
| `test_api.py` | 11 | API E2E |

```bash
uv run pytest tests/ -v --tb=short   # ~4 seconds, no GPU needed
```

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

# Run tests
uv run pytest tests/ -v --tb=short
```

Open http://localhost:8000 in browser.

---

## Future Work

1. **Production MedASR** — Replace simulated speech recognition
2. **Real FHIR Integration** — Connect to Epic/Cerner
3. **HL7 CDA Export** — Standards-compliant documentation
4. **Multi-GPU Scaling** — vLLM tensor parallelism
5. **RAG-Enhanced Memory** — Clinical guideline retrieval
6. **Audit Logging** — Full compliance trail

---

## Competition Compliance

- ✅ Uses MedGemma 1.5 4B IT
- ✅ Demonstrates multimodal (image + text)
- ✅ Clinical decision support use case
- ✅ Structured output (SOAP notes)
- ✅ EHR integration pattern
- ✅ Safety guardrails (emergency detection, medical guardrails)
- ✅ Evidence-based clinical correlation
- ✅ Multi-opinion consensus (Diagnostic Council)
