# MedGemma Clinical Assistant — Technical Write-up

## Executive Summary

The **MedGemma Clinical Assistant** is an AI-powered clinical decision support system built on Google's MedGemma 1.5 4B IT model. It targets two compounding problems in healthcare: **physician documentation burden** (2+ hours/day) and **diagnostic error** (affecting ~12 million Americans annually).

The system provides:
- Real-time multimodal encounter support — speech transcription, medical image analysis, and EHR context combined into automated SOAP documentation
- A **Diagnostic Council** — a LangGraph-orchestrated multi-rollout deliberation system where N independent AI opinions are generated in parallel and synthesized into a consensus diagnosis, backed by live PubMed case literature
- An **Iterative Evidence Feedback Loop** — a two-round deliberation that challenges its own initial hypothesis by injecting PubMed-sourced rare diagnoses into a second round of AI opinions
- **RAG context compression** for full clinical notes — semantic retrieval of the most symptom-relevant excerpts before injecting into council prompts
- An end-to-end **inpatient workflow** covering progress notes, SBAR shift handoffs, safety watchlist alerts, and discharge planning with readmission risk scoring
- A **Patient Portal** and **AI Chat Portal** with safety guardrails, image annotation, and persistent cross-encounter memory via Mem0

---

## 1. The Clinical Problem

Physicians spend over 2 hours per day on documentation — time taken away from patients. Meanwhile, diagnostic errors affect roughly 12 million Americans annually. Many of these errors are not from lack of knowledge, but from cognitive overload: a physician seeing 20+ patients per shift cannot exhaustively search rare-disease literature for every atypical presentation.

This system addresses both problems simultaneously:
- **Documentation burden**: Transcription + imaging + EHR context → SOAP note generated automatically, requiring only physician approval
- **Diagnostic error**: Multi-opinion consensus + live PubMed literature → rare diagnoses surfaced that might otherwise be missed; inpatient safety rules catch VTE prophylaxis gaps, Foley dwell risks, and overdue documentation

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Frontend (HTML/JS)                               │
│  Transcription · Image upload · SOAP preview · Diagnostic Council       │
│  Patient Portal  · AI Chat Portal (annotate + voice) · Inpatient       │
│  PubMed literature panels  · Rounding / SBAR / Safety / Discharge      │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ WebSocket / REST
┌──────────────────────────────▼──────────────────────────────────────────┐
│                       FastAPI Backend (main.py)                          │
│   /api/encounters/*  /api/council/*  /api/pubmed/*  /api/inpatient/*    │
│   /api/portal/*  /api/memory/*  /api/ai-portal/*  /ws/audio/*          │
└──┬───────┬───────┬───────┬────────┬────────┬────────┬──────────────────┘
   │       │       │       │        │        │        │
   ▼       ▼       ▼       ▼        ▼        ▼        ▼
MedGemma  MedASR  FHIR  PubMed  Diagnostic  Local  Inpatient
 Agent   Stream  server  Synth   Council    Trends  Services
 (4-bit)         (Fire-  Agent  (LangGraph) (RSS)  (rounding
                 store /        RAG+Iter.           SBAR/safe
                 Mock)          Evidence           /discharge)
```

**Data flow for a typical encounter:**

```
Doctor speaks
   → MedASR streaming transcription (WebSocket)
   → Session accumulates transcript + image findings
   → POST /api/encounters/{id}/generate-soap
       ├── Local trend correlation (patient location × symptoms)
       ├── MedGemma processes encounter (image + transcript + EHR)
       ├── SOAP note generated with ICD-10 codes & critical alerts
       ├── Background: PubMed synthesis in 3 modes
       │     ├── case_matcher   → rare_diagnoses
       │     ├── ebm_validator  → plan divergences
       │     └── ddi_monitor    → drug interaction alerts
       └── Returns SOAP + local_trend_insights to UI
   → Doctor reviews, approves → EHR updated
```

---

## 3. MedGemma Integration (`src/agent/`)

MedGemma 1.5 4B IT is the backbone of the system, used in four distinct ways:

| Usage | Where | Description |
|-------|-------|-------------|
| Medical image analysis | Encounter UI | Analyzes X-ray/CT/MRI with clinical context; flags critical findings |
| SOAP note generation | Encounter workflow | Processes transcript + image findings + EHR context → structured S/O/A/P |
| Diagnostic Council prompts | `/api/council/*` | Each rollout calls MedGemma with a compact case prompt; returns JSON diagnosis |
| Patient Portal & AI Chat | `/api/portal/*`, `/api/ai-portal/*` | Multi-turn Q&A with guardrails, voice, and image annotation support |

**Memory optimization:**
- 4-bit NF4 quantization via BitsAndBytes — fits in 8 GB VRAM (RTX 5060 compatible)
- vLLM backend available (`--use-vllm`) for 2–3x faster inference
- Simulated mode (`SIMULATED_MODE=true`) for zero-GPU demos

---

## 4. Diagnostic Council — LangGraph Multi-Rollout Deliberation (`src/council/`)

The Diagnostic Council is the most architecturally novel component. It replaces sequential single-model inference with **N independent parallel opinions** orchestrated by a LangGraph `StateGraph`.

### 4.1 Why Multi-Rollout?

A single LLM call is subject to anchoring bias — it converges on a probable diagnosis before considering rarer alternatives. By running N stateless, independent prompts (each seeing only the raw case info, not prior opinions), we get genuine diversity. Consensus is computed from the distribution of those N answers:

- **Strong**: >80% agreement
- **Moderate**: 60–80%
- **Weak**: 40–60%
- **Split**: <40%

A weak or split result is itself clinically meaningful — it indicates the differential is genuinely ambiguous and warrants more investigation.

### 4.2 Graph Topology

```
START → initialize → retrieve_context (RAG)
      → [Send×N] generate_r1_opinion  (parallel fan-out)
            → calculate_consensus
                  → run_pubmed (Zebra Hunt)
                        ├─ [iterative + rare_dx] → [Send×N] generate_r2_opinion
                        │                                  → calculate_r2_consensus → END
                        └─ [standard | no rare_dx] ──────────────────────────────→ END
```

**Key LangGraph patterns used:**

| Pattern | Where | Why |
|---------|-------|-----|
| `Annotated[list[dict], operator.add]` | `opinions`, `r2_opinions` fields | Merges parallel branch outputs into one list without race conditions |
| `Send` API | `fan_out_r1`, `route_after_pubmed` | Dispatches N concurrent nodes; each carries its own `_opinion_idx` and `_round` |
| Two-node routing | `generate_r1_opinion` → `calculate_consensus`; `generate_r2_opinion` → `calculate_r2_consensus` | Same underlying function, different downstream edges — avoids code duplication while enabling distinct routing |
| Conditional edge returning `END` | `route_after_pubmed` | Standard mode or no rare diagnoses → short-circuit, skip Round 2 |
| Closure capture | `build_council_graph(agent, pubmed_agent)` factory | Agent references captured at graph build time; graph lazily compiled and cached |

### 4.3 Iterative Evidence Feedback Loop (Deep Dive)

When mode is `"iterative"` and PubMed returns rare diagnosis candidates:

1. **Round 1**: Standard N-rollout deliberation → initial consensus (e.g., "Community-Acquired Pneumonia")
2. **PubMed Zebra Hunt**: `case_matcher` searches PubMed Case Reports for the symptom cluster
3. **Round 2**: A second fan-out runs with rare diagnoses injected into each opinion prompt (as bullet points, not full abstracts — ~50-token overhead). Each R2 opinion may now elevate a rare diagnosis if it fits the case better
4. **Shift detection**: If R2 consensus differs from R1 consensus, `consensus_shifted=True` and a yellow ⚡ banner appears

This creates a self-challenging mechanism: the system questions its own initial assessment using real medical literature evidence.

### 4.4 RAG Context Compression (`src/council/rag.py`)

When full clinical notes are provided (`raw_note` parameter), the `retrieve_context` graph node compresses them before the fan-out:

```
raw_note (full H&P or progress note)
   → chunk_note()   — sentence-boundary split with 50-word overlap, ~250-word chunks
   → embed()        — sentence-transformers (semantic) or TF-IDF numpy (fallback)
   → retrieve()     — top-5 chunks by cosine similarity to symptom query
   → compress_note() returns joined excerpts (preserved in narrative order)
   → injected into each opinion prompt as "Relevant excerpts from clinical notes"
```

Design choices:
- **No mandatory new dependencies**: TF-IDF fallback uses only numpy (already a dependency). `sentence-transformers` is an optional extra (`[rag]`)
- **Narrative order**: Retrieved chunks are re-sorted by original position, not score, so the assembled context reads coherently
- **No-op for short inputs**: When `raw_note` is empty, the node returns immediately — zero overhead for standard usage

---

## 5. PubMed Synthesis Agent (`src/pubmed/`)

Three clinical synthesis modes, each tailored to a distinct workflow need:

| Mode | Query target | Clinical use | Output field |
|------|-------------|--------------|--------------|
| `case_matcher` | PubMed Case Reports | Find rare diagnoses for atypical symptom clusters | `rare_diagnoses` |
| `ebm_validator` | Systematic reviews, meta-analyses, RCTs (last N years) | Validate physician's treatment plan against current evidence | `divergences` |
| `ddi_monitor` | Pharmacology literature | Surface novel drug-drug interactions not in standard databases | `ddi_alerts` |

**Implementation details:**
- Pure stdlib (`urllib`, `xml.etree`) — no external HTTP library required for PubMed access
- Progressive query relaxation in `case_matcher`: removes atypical markers one by one; falls back to broad `(rare OR unusual OR atypical)` filter if needed
- `ddi_monitor` caps at 12 drug pairs to respect NCBI rate limits (3 req/s default, 10 req/s with `NCBI_API_KEY`)
- After SOAP generation, all three modes run as a FastAPI `BackgroundTask` — UI polls `GET /api/encounters/{id}/pubmed-insights` for completion

**Integration points:**
- Encounter UI: results appear in the right panel after SOAP generation
- Diagnostic Council: `run_pubmed` node in the LangGraph graph fires automatically; results populate the PubMed Zebra Hunt panel
- AI Chat Portal: intent detection per message dispatches the appropriate mode alongside the MedGemma response

---

## 6. Local Health Trend Correlation (`src/trends/`)

The system correlates patient symptoms with same-day local public health and environmental events:

1. Patient location extracted from FHIR EHR demographics
2. Three Google News RSS feeds queried: public health/clinical advisories; disease outbreaks; environmental hazards (wildfire smoke, air quality, heat, water contamination)
3. Results classified into four event categories, then matched against symptom clusters
4. Matched signals surface in the SOAP response as `local_trend_insights`

**Vocabulary enrichment:**
- External NLM MeSH Lookup API enriches the symptom-to-category mapping
- Results cached in Firestore (`system_cache/medical_vocab_mesh`) with 12-hour TTL and local fallback
- Optional semantic vector expansion via `MEDICAL_VOCAB_VECTOR_BACKEND`

**Guardrail**: Trend context is explicitly labelled non-diagnostic and always requires physician validation before acting on it.

---

## 7. Inpatient Workflow Suite (`src/inpatient/`)

Four services covering the full inpatient lifecycle:

### 7.1 Rounding Copilot (`/rounding`)

Generates a 24-hour SOAP progress note per admitted patient with:
- Current vitals, active medications, latest labs from EHR
- MedGemma narrative synthesis when available; structured fallback otherwise
- `todo_items` list: flagged gaps (pending labs, missing reassessment notes, etc.)
- LOS hours computed from admission date

### 7.2 SBAR Handoff Generator (`/handoff`)

Structured Situation–Background–Assessment–Recommendation document with an 8-point completeness audit:
- Code status documented?
- Allergies mentioned?
- High-risk medications flagged (insulin, anticoagulants, opioids, vasopressors)?
- Active devices documented (Foley, central line, ventilator)?
- Contingency plans present?

Incomplete handoffs receive a score and a `missing_fields` list — physicians cannot sign incomplete documents.

### 7.3 Safety Watchlist (`/safety-dashboard`)

Rule-based alert engine, sorted critical-first:

| Rule | Severity | Trigger |
|------|----------|---------|
| VTE prophylaxis | CRITICAL | Admitted >24 h, no order, no documented contraindication |
| Foley catheter | WARNING | Dwell >3 days, no reassessment note in last 24 h |
| High-risk medication | WARNING | Vancomycin/aminoglycosides/insulin/metformin/NSAIDs without renal function lab in last 48 h |
| Progress note absent | WARNING | No physician note in >24 h |

Each alert includes a `suggested_action` and `ai_explanation` field.

### 7.4 Discharge Planner

Patient-friendly 5th–6th grade discharge summary with:
- Three-tier readmission risk scoring (HIGH/MEDIUM/LOW) with explicit reasoning
- MISSING-field enforcement: required fields not found in the record are explicitly marked `MISSING`, preventing sign-off on incomplete documents
- Medication counselling notes per drug
- Red flag symptoms for return precautions

### 7.5 LACE Readmission Scoring

Quantitative readmission risk embedded in every discharge summary:

| Component | Scoring |
|-----------|---------|
| L — Length of Stay | 0=<1d, 1=1d, 2=2d, 3=3d, 4=4-6d, 5=7-13d, 7=>14d |
| A — Acuity (emergency admit) | 3 if admitted via ED, else 0 |
| C — Charlson Comorbidity Index | Weighted keyword match against conditions, capped at 5 |
| E — ED visits in prior 6 months | 0=none, 1=once, 2=twice, 3=thrice, 4=≥4 |

Score ≥10 → HIGH, 5–9 → MEDIUM, <5 → LOW. Exposed as `lace_score` and `lace_components` in discharge summary response.

### 7.6 Expanded Safety Rules

Four additional safety checks beyond the original four:

| Rule | Severity | Logic |
|------|----------|-------|
| Falls Risk (Morse) | CRITICAL / WARNING | Age ≥65, ≥2 fall history, presence of IV line or assistive device |
| Pressure Ulcer Risk (Braden) | WARNING | Limited mobility + nutritional deficit indicators |
| Antibiotic De-escalation | WARNING | Broad-spectrum antibiotic (vancomycin, meropenem, piperacillin) active with culture results available |
| Glycemic Control | WARNING | Insulin active without glucose monitoring observation in last 6h |

### 7.7 Medication Reconciliation

`GET /api/inpatient/{id}/med-reconciliation` returns a `MedReconciliation` object:
- `added_meds`: Medications in inpatient orders not present at admission
- `discontinued_meds`: Admission medications not continued as inpatient orders
- `reconciliation_status`: `"complete"` or `"review_required"` (when discontinuations detected)

---

## 8. AI Chat Portal (`/ai-portal`)

Three-panel layout designed for flexible clinical queries:

- **Left panel**: Patient context (EHR summary or free-text paste)
- **Center panel**: Medical image drop zone with `<canvas>` annotation overlay — physicians draw bounding boxes to focus MedGemma on regions of interest
- **Right panel**: Multi-turn chat with voice input and Markdown rendering

PubMed intent detection: each chat message is analysed for keywords indicating DDI, EBM, or rare-disease inquiry — the appropriate synthesis mode runs in parallel with the MedGemma response. Results appear as a collapsible Evidence Check pill.

---

## 9. Patient Portal (`/patient-portal`)

- Emergency keyword detection (chest pain, seizure, bleeding, etc.) → immediate escalation prompt
- Medical guardrails: refuses dosage/medication modification advice
- Query categorization (medication, symptoms, appointment, general)
- Patient memory (Mem0): allergies, medications, diagnoses recall across encounters

---

## 10. Key Technical Design Decisions

| Decision | Rationale |
|----------|-----------|
| LangGraph `Send` API for fan-out | Native parallel execution without managing asyncio tasks; `operator.add` reducer handles merge automatically |
| Two-node naming trick (`generate_r1_opinion` / `generate_r2_opinion`) | Same function body, different downstream edges — avoids duplicating logic while enabling distinct routing per round |
| Stateless opinion prompts | No cross-opinion history → genuine independence, prevents anchoring bias; each of N prompts sees only raw case data |
| TF-IDF numpy fallback for RAG | Zero new mandatory dependencies; `sentence-transformers` optional for better quality; feature degrades gracefully, never breaks |
| Narrative-order chunk return | Re-sort retrieved chunks by original position before injection — assembled context reads as a coherent clinical excerpt, not ranked fragments |
| PubMed stdlib-only client | No HTTPX/requests dependency at the PubMed layer; rate limiting via global sleep state keeps NCBI compliance simple |
| FastAPI `BackgroundTasks` for PubMed | Non-blocking response to physician; PubMed synthesis (up to 12 API calls) runs in parallel with SOAP display |
| MISSING-field enforcement in discharge | Prevents sign-off on incomplete documents; parallels SBAR completeness scoring for handoffs |

---

## 11. Compliance and Infrastructure

### 11.1 Audit Logging (`src/audit/`)

Every clinical AI action is recorded as an `AuditEvent`:
- **Storage**: In-memory `deque(maxlen=1000)` ring buffer + fire-and-forget Firestore write
- **Event types**: `SOAP_GENERATED`, `COUNCIL_DELIBERATION`, `HANDOFF_GENERATED`, `DISCHARGE_PLANNED`
- **Fields**: `event_id`, `timestamp`, `event_type`, `action`, `user_id`, `user_role`, `patient_id`, `success`
- **Routes**: `GET /api/audit/recent?limit=N`, `GET /api/audit/patient/{patient_id}`

### 11.2 Performance Profiling (`src/monitoring/`)

`@track_perf("operation_name")` decorator wraps both sync and async route handlers. Stores up to 200 samples per operation in a `deque`; `get_stats()` computes avg/min/max/count. Instrumented operations: `council_deliberation`, `council_iterative`, `rounding`, `handoff`, `discharge_summary`. Exposed via `GET /api/metrics`.

### 11.3 Multi-Hospital Configuration (`src/config/`)

`HospitalRegistry` is a singleton registry loaded on startup, pre-seeded with GENERAL and COMMUNITY demo hospitals and overlaid with Firestore data if available. Supports per-hospital:
- `formulary_restrictions`: list of medication names requiring alternative confirmation
- `features_enabled`: audit_log, prior_auth, referral, simulation toggles
- `contact_info`, `timezone`, `branding`

### 11.4 Prior Authorization + Referral Letters

`PriorAuthService` auto-detects orders requiring prior authorization based on keyword matching against known medication/procedure categories (biologics, specialty imaging, etc.). Workflow: detect → pending → approve/deny. `ReferralLetterService` generates AI-formatted specialist referral letters from encounter context.

---

## 12. Performance

| Backend | First-load | Inference | VRAM |
|---------|-----------|-----------|------|
| Transformers 4-bit | ~30 s | ~5 s/response | ~6 GB |
| vLLM | ~20 s | ~2 s/response | ~7 GB |
| Simulated (no GPU) | instant | instant | 0 |

---

## 13. API Reference (Summary)

### Encounter Workflow
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/patients` | List patients |
| POST | `/api/encounters/start` | Begin encounter |
| POST | `/api/encounters/{id}/image` | Upload medical image |
| POST | `/api/encounters/{id}/generate-soap` | Generate SOAP + trigger PubMed background |
| GET | `/api/encounters/{id}/pubmed-insights` | Poll PubMed background result |
| POST | `/api/encounters/{id}/approve` | Approve note → EHR update |

### Diagnostic Council
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/council/deliberate` | Standard N-rollout deliberation |
| POST | `/api/council/iterative-deliberate` | Deep Dive 2-round evidence feedback loop |
| GET | `/api/council/history` | Past deliberations |

### PubMed
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/pubmed/zebra-hunt` | Case matcher for rare diagnoses |
| POST | `/api/pubmed/validate-plan` | EBM validator for treatment plan |
| GET | `/api/pubmed/ddi-monitor/{patient_id}` | DDI monitor using FHIR medications |

### Inpatient
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/inpatient/ward` | List admitted patients |
| POST | `/api/inpatient/{id}/rounding-note` | 24-hour progress note |
| POST | `/api/inpatient/{id}/sbar` | SBAR handoff with completeness audit |
| GET | `/api/inpatient/safety` | Ward safety dashboard |
| POST | `/api/inpatient/{id}/discharge-summary` | Discharge summary with readmission risk |
| GET | `/api/inpatient/{id}/med-reconciliation` | Medication reconciliation diff |

### Audit & Metrics
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/audit/recent` | Most recent audit events (limit param) |
| GET | `/api/audit/patient/{id}` | Audit events for a patient |
| GET | `/api/metrics` | Latency stats for tracked operations |

### Prior Auth & Referral
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/prior-auth/{patient_id}` | All prior auth requests for patient |
| POST | `/api/prior-auth/{patient_id}/detect` | Auto-detect orders requiring prior auth |
| GET | `/api/prior-auth/request/{auth_id}` | Look up request by auth_id |
| POST | `/api/prior-auth/request/{auth_id}/approve` | Approve a prior auth request |
| POST | `/api/prior-auth/request/{auth_id}/deny` | Deny a prior auth request |
| GET | `/api/referral/{patient_id}` | All referral letters for patient |
| POST | `/api/referral/{patient_id}/generate` | Generate specialist referral letters |

### Hospital Registry
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/hospitals` | List all hospital profiles |
| GET | `/api/hospitals/{hospital_id}` | Get single hospital |
| POST | `/api/hospitals` | Register new hospital |
| GET | `/api/hospitals/{hospital_id}/patients` | Patients assigned to hospital |

---

## 14. Running the Demo

```bash
# No GPU required
SIMULATED_MODE=true uv run python main.py

# Full mode (MedGemma + MedASR)
uv run python main.py

# With vLLM backend (2-3x faster)
uv run python main.py --use-vllm

# Semantic RAG (optional, improves clinical note compression)
uv pip install "medgemma-assistant[rag]"

# Run tests
uv run pytest tests/ -v --tb=short
```

Open http://localhost:8000

---

## 15. Competition Compliance

| Requirement | Status |
|-------------|--------|
| Uses MedGemma 1.5 4B IT | ✅ |
| Multimodal (image + text) | ✅ |
| Clinical decision support use case | ✅ |
| Structured output (SOAP notes) | ✅ |
| EHR integration (FHIR + Firestore) | ✅ |
| Safety guardrails | ✅ Emergency detection, medical guardrails, CRITICAL alerts |
| Evidence-based clinical correlation | ✅ Live PubMed (3 synthesis modes) |
| Multi-opinion consensus | ✅ LangGraph Diagnostic Council (N parallel rollouts) |
| Persistent patient memory | ✅ Mem0 cross-encounter memory |
| Location-aware context | ✅ Local health/environment trend correlation |
| Inpatient care coverage | ✅ Rounding, SBAR, safety watchlist, discharge planner |
| Context compression / RAG | ✅ Semantic retrieval for full clinical notes |
| Iterative evidence feedback | ✅ 2-round Deep Dive with PubMed rare diagnosis injection |
| Human-in-the-loop approval | ✅ All EHR updates require explicit physician approval |
| Reproducibility | ✅ Simulated mode + test suite (72 tests, no GPU) |
| Audit logging | ✅ Immutable AuditEvent trail, ring buffer + Firestore, 4 event types |
| Prior auth & referral | ✅ Auto-detection, approve/deny workflow, AI referral letters |
| LACE readmission index | ✅ L+A+C+E scoring with Charlson comorbidity in every discharge summary |
| Expanded safety rules | ✅ Falls (Morse), pressure ulcer (Braden), antibiotic de-escalation, glycemic control |
| Medication reconciliation | ✅ Admission vs. inpatient medication diff |
| Multi-hospital tenancy | ✅ Per-hospital formulary restrictions and feature flags |
| Performance profiling | ✅ @track_perf decorator, rolling latency stats, GET /api/metrics |

---

## 16. Future Work

1. **Production MedASR** — Replace simulated speech recognition with production-grade streaming model
2. **Real FHIR Integration** — Connect to Epic/Cerner via standard SMART on FHIR flow
3. **HL7 CDA Export** — Standards-compliant documentation for interoperability
4. **Multi-GPU Scaling** — vLLM tensor parallelism for concurrent encounters
5. **Managed Vector Backend** — Optional Qdrant/Pinecone backend replacing the current in-memory TF-IDF for cross-patient semantic retrieval
6. **PubMed Semantic Search** — Replace keyword-based intent detection with embedding-based dispatch
7. **Federated Learning** — Privacy-preserving fine-tuning on institution-specific clinical patterns
