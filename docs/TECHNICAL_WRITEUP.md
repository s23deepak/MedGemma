# MedGemma Clinical Assistant — Technical Write-up

## Executive Summary

The **MedGemma Clinical Assistant** is an AI-powered clinical decision support system that integrates MedGemma for multimodal reasoning, speech recognition for physician dictation, and a FHIR-compatible EHR. It features imaging artifact detection, clinical correlation analysis, a multi-opinion Diagnostic Council backed by live PubMed literature, SOAP compliance monitoring, a patient-facing portal with safety guardrails, an AI Chat Portal with image annotation, and persistent patient memory powered by Mem0.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Frontend (HTML/JS/CSS)                            │
│  • Real-time transcription   • Medical image upload                 │
│  • SOAP note preview         • Patient history timeline             │
│  • Compliance dashboard      • Diagnostic council panel             │
│  • Patient portal            • AI Chat Portal (annotate + voice)   │
│  • Role-based navigation     • PubMed literature panels            │
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
│  • /api/pubmed/*        - PubMed search, zebra-hunt, EBM, DDI      │
│  • /api/ai-portal/*     - Physician multimodal chat                 │
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
│Gen   │ │Whisper │ │        │ │Alerts  │ │Classif │ │+ PubMed  │
└──────┘ └────────┘ └────────┘ └────────┘ └────────┘ └──────────┘

  ┌──────────┬──────────┬──────────┬────────────┬──────────┐
  ▼          ▼          ▼          ▼            ▼          ▼
┌──────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐ ┌──────┐
│SOAP  │ │Patient │ │Patient │ │Patient │ │PubMed    │ │AI    │
│Compl │ │Portal  │ │History │ │Memory  │ │Synthesis │ │Chat  │
│iance │ │        │ │        │ │(Mem0)  │ │Agent     │ │Portal│
├──────┤ ├────────┤ ├────────┤ ├────────┤ ├──────────┤ ├──────┤
│Sympt │ │Emerg   │ │Time-   │ │Cross-  │ │Case      │ │Anno- │
│Flags │ │Detect  │ │line    │ │Encntr  │ │Matcher   │ │tate  │
│Rates │ │Guard-  │ │Meds &  │ │Recall  │ │EBM Valid │ │Voice │
│      │ │rails   │ │Imaging │ │Extract │ │DDI Mon.  │ │Image │
└──────┘ └────────┘ └────────┘ └────────┘ └──────────┘ └──────┘
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
| `tools.py` | 10 function-calling tool definitions (includes `search_pubmed`) |
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
- `extract_clinical_orders()` — extracts lab, imaging, medication, and referral orders from plan text
- HTML, Markdown, and dict rendering

### 5. SOAP Compliance (`src/compliance/`)

- Symptom duration threshold monitoring
- Documentation update frequency tracking
- Per-patient compliance flags with severity levels
- Aggregate compliance rate reporting

### 6. Diagnostic Council (`src/council/`)

- 3–7 independent diagnostic opinions per case (configurable)
- Consensus strength scoring (Strong / Moderate / Weak / Split)
- Accepts symptoms, patient history, and imaging findings
- PubMed Zebra Hunt: `case_matcher` runs automatically after deliberation to surface rare diagnoses from literature
- Deliberation history tracking

### 7. PubMed Synthesis Agent (`src/pubmed/`)

| Component | Description |
|-----------|-------------|
| `pubmed_client.py` | NCBI E-utils API client with retry, rate-limiting (3 or 10 req/s) |
| `synthesis_agent.py` | Three-mode synthesis agent |

**Three synthesis modes:**

| Mode | Query Type | Output Field |
|------|-----------|--------------|
| `case_matcher` | PubMed Case Reports matching unusual symptom clusters | `rare_diagnoses` |
| `ebm_validator` | Systematic Reviews + RCTs validating treatment plans | `divergences` |
| `ddi_monitor` | Pharmacology literature for novel drug-drug interactions | `ddi_alerts` |

- Progressive query relaxation in `case_matcher`: removes atypical markers one by one, then falls back to broad rare/unusual filter
- `ddi_monitor` caps at 12 drug pairs to respect NCBI rate limits
- Background task after SOAP generation; polled via `GET /api/encounters/{id}/pubmed-insights`
- Surfaces results inline in Encounter UI, Diagnostic Council panel, and AI Chat Portal

### 8. AI Chat Portal (`/ai-portal`)

- Three-panel layout: Patient Context | Medical Imaging | Chat
- Supports existing patient selection or manual text entry for context
- Image drop zone with `<canvas>` annotation overlay — physicians draw bounding boxes to focus MedGemma on regions of interest
- Voice input via MedASR in both context and chat panels
- Inline PubMed context enrichment: intent detected per message (DDI / EBM / zebra keywords) → appropriate synthesis mode runs alongside the MedGemma response
- Markdown rendering for assistant messages

### 9. Patient Portal (`src/portal/`)

- Emergency keyword detection (chest pain, seizure, bleeding, etc.)
- Medical guardrails (prevents dosage/medication modification advice)
- Query categorization (medication, symptoms, appointment, general)
- Query history per patient
- Appointment summary generation

### 10. Patient Memory (`src/memory/`)

- Powered by Mem0 with OpenAI for fact extraction
- 12 methods: `add_encounter()`, `recall()`, `get_allergies()`, `get_medications()`, etc.
- Auto-recall past context during encounters
- Category-based retrieval: diagnoses, allergies, medications, preferences
- Graceful fallback when OPENAI_API_KEY is not set

### 11. Authentication (`src/auth/`)

| Role | Features |
|------|----------|
| Doctor | History, Compliance, Council, Encounters, Portal, AI Chat |
| Nurse | History, Encounters, Portal |
| Resident | History, Council, Encounters, AI Chat |
| Admin | All features |
| Patient | Patient Portal only |

### 12. Mock FHIR EHR (`src/ehr/`)

Two demo patients:
- **P001**: Sarah Wilson (58F) — Hypertension, Asthma
- **P002**: Carlos Martinez (70M) — Diabetes, COPD

### 13. Patient History (`src/history/`)

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
| POST | `/api/encounters/{id}/generate-soap` | Generate SOAP note (triggers PubMed background task) |
| POST | `/api/encounters/{id}/approve` | Approve note to EHR |
| GET | `/api/encounters/{id}/pubmed-insights` | Poll PubMed background task result |

### Clinical Features

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/history/{id}/timeline` | Patient encounter timeline |
| GET | `/api/history/{id}/medications` | Medication history |
| GET | `/api/history/{id}/imaging` | Imaging history |
| POST | `/api/compliance/check` | Run compliance check |
| GET | `/api/compliance/report` | Get compliance report |
| POST | `/api/council/deliberate` | Diagnostic council deliberation (includes PubMed Zebra Hunt) |
| GET | `/api/council/history` | Past deliberations |

### PubMed

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/pubmed/search` | Generic mode dispatch (case_matcher / ebm_validator / ddi_monitor) |
| POST | `/api/pubmed/zebra-hunt` | Case matcher with common + atypical symptom split |
| POST | `/api/pubmed/validate-plan` | EBM validator for assessment + plan text |
| GET | `/api/pubmed/ddi-monitor/{patient_id}` | DDI monitor using patient's FHIR medications |

### AI Chat Portal

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/ai-portal/chat` | Multimodal chat with optional image + patient context; returns PubMed enrichment |

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
7. **PubMed Semantic Search** — Replace keyword-based intent detection with embeddings

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
- ✅ Live PubMed literature grounding (3 synthesis modes)
- ✅ Persistent patient memory (Mem0)
