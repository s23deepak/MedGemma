# MedGemma Clinical Assistant

An AI-powered clinical decision support system for the MedGemma Impact Challenge.

## Agent Description

This agent assists physicians with clinical encounters by:
1. **Listening** to doctor-patient conversations via MedASR
2. **Analyzing** medical images (CT, MRI, X-ray) with MedGemma
3. **Fetching** patient context from EHR via FHIR
4. **Correlating** local public-health/environment trends with same-day symptoms
5. **Generating** SOAP documentation with missed diagnosis detection
6. **Updating** EHR records upon physician approval

## Available Tools

### fetch_patient_ehr
Retrieve patient data from FHIR server.
- **Input**: `patient_id` (string)
- **Output**: Patient demographics, conditions, medications, allergies, recent observations

### analyze_medical_image  
Analyze medical imaging with clinical context.
- **Input**: `image_path` (string), `modality` (string: "xray", "ct", "mri")
- **Output**: Structured findings, potential concerns, comparison notes

### generate_soap_note
Generate structured SOAP documentation from encounter data.
- **Input**: `encounter_data` (object with transcription, image_findings, patient_context)
- **Output**: Formatted SOAP note with highlighted recommendations

### update_ehr
Update patient electronic health record.
- **Input**: `patient_id` (string), `updates` (object)
- **Requires**: Physician approval before execution
- **Output**: Confirmation of record update

### search_pubmed
Query PubMed via NCBI E-utils in one of three clinical synthesis modes.
- **Input**: `mode` (enum: "case_matcher" | "ebm_validator" | "ddi_monitor"), plus mode-specific fields:
  - *case_matcher*: `symptoms` (list), `atypical_markers` (list, optional), `max_results` (int)
  - *ebm_validator*: `assessment` (str), `plan` (str), `max_results` (int), `date_years_back` (int)
  - *ddi_monitor*: `medications` (list), `new_medications` (list, optional), `max_results_per_pair` (int), `date_years_back` (int)
- **Output**: `PubMedSearchResult` with articles, summary, key_findings, and mode-specific fields:
  - *case_matcher* → `rare_diagnoses` list
  - *ebm_validator* → `divergences` list (plan vs. latest evidence)
  - *ddi_monitor* → `ddi_alerts` list (novel interaction signals)
- **Modes**:
  - **Case Matcher (Zebra Hunt)**: Searches PubMed Case Reports for rare diagnoses matching unusual symptom clusters. Uses progressive query relaxation if no results — removes atypical markers one by one, then falls back to a broad "rare/unusual/atypical" filter.
  - **EBM Validator**: Retrieves Systematic Reviews, Meta-analyses, and RCTs from the last N years to validate a physician's plan. Flags divergences where current evidence differs from the proposed treatment.
  - **DDI Monitor**: Scans pharmacology literature for novel drug-drug interactions not yet captured in standard databases. Prioritizes pairs containing newly added medications. Caps at 12 drug pairs to respect NCBI rate limits.
- **Rate limiting**: 3 req/s by default; set `NCBI_API_KEY` env var for 10 req/s
- **Non-blocking**: After SOAP generation, PubMed analysis runs as a FastAPI `BackgroundTask` and can be polled via `GET /api/encounters/{session_id}/pubmed-insights`

### diagnostic_council
Multi-rollout AI deliberation for consensus diagnosis via a LangGraph `StateGraph`.
- **Input**: `symptoms` (list[str]), `patient_history` (str), `imaging_findings` (str), `vitals` (str), `num_rollouts` (int, default 5), `mode` ("standard" | "iterative")
- **Output**: `CouncilDeliberation` (standard) or `IterativeDeliberation` (iterative)

#### Deliberation Modes
- **Standard**: Fans out `num_rollouts` parallel opinion nodes → calculates consensus → runs PubMed Zebra Hunt → returns result
- **Iterative (Deep Dive)**: Same Round 1, then if PubMed returns rare diagnoses, fans out a second round with rare diagnoses injected into each opinion prompt → calculates R2 consensus → reports whether consensus shifted

#### Graph Topology (`src/council/graph.py`)
```
START → initialize → retrieve_context (RAG)
      → [Send×N] generate_r1_opinion  (parallel fan-out)
            → calculate_consensus
                  → run_pubmed
                        ├─ [iterative + rare_dx] → [Send×N] generate_r2_opinion → calculate_r2_consensus → END
                        └─ [standard | no rare_dx]                                                        → END
```

#### Implementation Details
- **State**: `CouncilState(TypedDict)` with `Annotated[list[dict], operator.add]` reducers on `opinions` and `r2_opinions` to merge parallel branch outputs
- **Parallel fan-out**: `Send` API dispatches N concurrent `generate_r1_opinion` nodes; each returns `{"opinions": [one_dict]}`; LangGraph merges via `operator.add`
- **Two-node routing**: The same `_opinion_node` function is registered as both `"generate_r1_opinion"` (edges to `calculate_consensus`) and `"generate_r2_opinion"` (edges to `calculate_r2_consensus`) — distinct downstream routing without code duplication
- **Agent capture**: `build_council_graph(agent, pubmed_agent)` factory captures references via closure; graph is lazily compiled and cached in `DiagnosticCouncil._graph`; cache is invalidated when agent or pubmed_agent is set after initial singleton creation
- **API routes**: `POST /api/council/deliberate` (standard), `POST /api/council/iterative-deliberate` (Deep Dive)

#### Context Engineering
Each opinion prompt is stateless and compact (~300–400 tokens): only structured case fields + a JSON schema + urgency constraint. No cross-opinion conversation history is shared — each of the N rollouts sees only the raw case info, preventing anchoring bias. In Round 2, only rare diagnosis *names* (3–5 bullet points) are appended, not full PubMed abstracts.

**RAG context compression (`raw_note` parameter):** When a full clinical note (H&P, progress note, etc.) is supplied via `raw_note`, a `retrieve_context` graph node runs before the fan-out. It calls `src/council/rag.py:compress_note()` to chunk the note into overlapping ~250-word windows and retrieve the top-5 most symptom-relevant excerpts via cosine similarity. Only those excerpts are injected into each opinion prompt, keeping token budgets controlled regardless of note length. The embedder uses `sentence-transformers/all-MiniLM-L6-v2` when installed (`uv pip install "medgemma-assistant[rag]"`), and falls back automatically to L2-normalised TF-IDF (numpy-only) otherwise. When `raw_note` is empty, the node is a no-op and existing behaviour is unchanged.

### local_health_trends (automatic context pipeline)
The system automatically enriches encounters with location-aware trend context.
- **Input source**: Patient location from EHR demographics
- **Signals**: Public health alerts, outbreaks, air quality/wildfire smoke, heat risk, water contamination
- **Vocabulary**: External NLM MeSH enrichment + ICD-10 augmentation + local fallback lexicon
- **Caching**: In-memory + optional Firestore shared cache (`system_cache/medical_vocab_mesh`)
- **Output**: Supportive `local_trend_insights` included in SOAP generation response
- **Guardrail**: Trend context is non-diagnostic and always requires physician validation

### generate_progress_note
Generate a 24-hour SOAP progress note for an admitted inpatient.
- **Input**: `patient_id` (string), optional `agent` for MedGemma narrative
- **Output**: `note_text` (full SOAP), `todo_items` (list of outstanding tasks), `los_hours`, `source` (`medgemma` | `structured_fallback`)
- **Fallback**: Structured note from EHR data when agent is unavailable

### generate_sbar
Generate a structured SBAR (Situation–Background–Assessment–Recommendation) shift handoff packet.
- **Input**: `patient_id` (string)
- **Output**:
  - `sbar`: `{situation, background, assessment, recommendation, contingency_plans}`
  - `completeness`: `{score, percentage, checks, missing_fields, warnings}` — 8-point rule audit covering code status, allergies, high-risk meds, active devices, contingency plan, sections present
- **Completeness audit**: flags missing code status, unmentioned allergies, unflagged high-risk medications (insulin, anticoagulants, opioids, vasopressors), undocumented active devices (Foley, central line, ventilator)

### run_safety_checks
Rule-based inpatient safety watchlist checker.
- **Input**: `patient_id` (string), optional `ward` filter
- **Output**: List of `SafetyAlert` with fields: `alert_id`, `rule_id`, `severity` (`critical` | `warning`), `title`, `detail`, `suggested_action`, `ai_explanation`
- **Rules implemented**:
  1. VTE prophylaxis: admitted >24h with no order and no documented contraindication → CRITICAL
  2. Foley catheter: dwell time >3 days without reassessment note in last 24h → WARNING
  3. High-risk medication (vancomycin, aminoglycosides, insulin, metformin, NSAIDs) without renal function lab in last 48h → WARNING
  4. No physician progress note in >24h → WARNING
  5. Falls risk (Morse scale): age ≥65, ≥2 fall history, assistive device/IV line documented → CRITICAL if high Morse score
  6. Pressure ulcer risk (Braden scale): limited mobility + nutritional deficit indicators → WARNING
  7. Antibiotic de-escalation: broad-spectrum antibiotic (vancomycin, meropenem, piperacillin) active with culture results available → WARNING to review spectrum
  8. Glycemic control: active insulin order without glucose monitoring observation in last 6h → WARNING
- **Dashboard**: `get_ward_safety_dashboard(ward)` aggregates alerts for all inpatients, sorted critical-first

### generate_discharge_summary
Generate a patient-friendly discharge summary with readmission risk assessment.
- **Input**: `patient_id` (string), optional `soap_note` context
- **Output**: `DischargeSummary` with: `why_admitted`, `what_was_done`, `medications` (with counseling notes), `follow_up_tasks`, `red_flag_symptoms`, `activity_restrictions`, `diet_instructions`, `missing_fields`, `readmission_risk` (`high` | `medium` | `low`), `readmission_risk_reasons`, `readmission_risk_explanation`
- **Reading level**: 5th–6th grade when MedGemma agent is available
- **MISSING enforcement**: Required fields not found in the record are explicitly marked `MISSING` so physicians cannot sign an incomplete document
- **Risk binning**:
  - HIGH: CHF, COPD, sepsis, CKD, prior admission in last 30 days, LOS >7 days
  - MEDIUM: Diabetes, AF, stroke, post-surgical, polypharmacy (≥5 meds)
  - LOW: No identified risk factors
- **LACE Index**: Quantitative readmission risk score: L (LOS 0–7) + A (Acuity: 3 if ER admit) + C (Charlson comorbidity weighted score, capped 5) + E (ED visits in last 6 months, 0–4). Score ≥10 = HIGH, 5–9 = MEDIUM, <5 = LOW. Included in discharge summary response as `lace_score`, `lace_components`, `lace_interpretation`.

### prior_auth_and_referral
Auto-detect and manage prior authorization requests and specialist referral letters.
- **Prior auth detection**: `POST /api/prior-auth/{patient_id}/detect` — scans order text for medications and procedures requiring prior auth (immunologics, biologics, specialty imaging)
- **Approve/Deny**: `POST /api/prior-auth/request/{auth_id}/approve` and `.../deny`
- **Referral letters**: `POST /api/referral/{patient_id}/generate` — AI-generated specialist letters from encounter context
- **Routes**: `GET /api/prior-auth/{patient_id}`, `GET /api/prior-auth/request/{auth_id}`, `GET /api/referral/{patient_id}`

### audit_and_metrics
- **Audit trail**: Every clinical AI action (SOAP generation, council deliberation, rounding, SBAR, discharge) is logged as an `AuditEvent` with timestamp, event type, patient_id, and user_id. Queryable via `GET /api/audit/recent` and `GET /api/audit/patient/{id}`
- **Performance metrics**: All major route handlers are instrumented with `@track_perf()`. Rolling 200-sample latency stats (avg/min/max/count) available at `GET /api/metrics`

### hospital_registry
Multi-tenant hospital configuration with per-hospital formulary restrictions and feature flags.
- **Routes**: `GET /api/hospitals`, `GET /api/hospitals/{id}`, `POST /api/hospitals`, `GET /api/hospitals/{id}/patients`
- **Demo hospitals**: GENERAL (Chicago) — all features enabled; COMMUNITY (New York) — prior_auth and simulation disabled, formulary restricts adalimumab and pembrolizumab
- **Patient assignment**: P001–P004 → GENERAL; P005 (Dorothy Chen) → COMMUNITY

### rare_disease_director
TTT-inspired iterative rare disease diagnostic hunt for atypical presentations where common diagnoses have been excluded.
- **Route**: `POST /api/rare-disease/hunt` (JSON body), `GET /rare-disease` (UI page)
- **Input**: `RareCaseInput` — `symptoms` (list[str]), `patient_history` (str), `imaging_findings` (str), `labs` (dict[str, str]), `vitals` (str), `demographics` (dict), `raw_note` (str), `max_hypotheses` (1–10)
- **Output**: `RareDiseaseReport` — ranked `hypotheses`, `convergence` metadata, `disclaimer`, `generated_at`
- **Each hypothesis**: `name`, `icd10`, `reasoning`, `matching_features`, `anti_features`, `symptom_coverage`, `evidence_strength`, `coherence_score`, `reward_score`, `evidence_tier` (well-evidenced / some-evidence / speculative), `confirmatory_tests`, `specialist_type`, `urgency` (urgent / elective / low), `pubmed_citations`

#### TTT-Inspired Loop
Architecture inspired by the `discover` repo (https://github.com/test-time-training/discover — RL at test time).
Instead of gradient weight updates, adaptation is performed through iterative evidence retrieval + hypothesis expansion:

```
[Round 0] Symptom Fingerprinting + Ontology Seed Hypotheses (fast, no LLM)
[Round 1] MedGemma LLM Hypothesis Generation (merged with seeds)
[TTT Loop — max 3 iterations]
  ├─ PubMed Zebra Hunt per hypothesis
  ├─ Reward = 0.40×symptom_coverage + 0.40×evidence_strength + 0.20×coherence
  ├─ If best_reward ≥ 0.55 → CONVERGE
  ├─ iter 1 expansion: ontology adjacency for top-3 hypotheses
  └─ iter 2+ expansion: LLM self-critique for unexplained features
Output: ranked direction report (top N hypotheses)
```

#### Ontology Knowledge Base (~60 rare diseases, 8 organ systems)
Rheumatologic · Metabolic/Genetic · Hematologic · Neurologic · Endocrine · Vascular/Cardiac · Hepatic/GI · Pulmonary

#### Safety
- Every hunt is logged to the audit trail with symptom count, iterations, and top hypothesis
- All outputs carry a mandatory disclaimer: directional guidance only, requiring physician validation

## Safety Constraints

1. **Never diagnose autonomously** - All findings are suggestions requiring physician validation
2. **Flag critical findings** - Urgent conditions trigger immediate alerts
3. **Require approval** - EHR updates must be explicitly approved by the physician
4. **Audit trail** - All AI suggestions and physician decisions are logged

## Usage Context

This agent operates in a clinical setting where:
- A physician is conducting a patient encounter
- Medical images may be reviewed during the visit
- The physician dictates observations and findings
- Documentation is generated in real-time for review

## Infrastructure & Deployment

### Model Backend

Three modes, controlled by environment variables:

| Mode | Env var | Model loading |
|------|---------|---------------|
| **vLLM** (recommended) | `USE_VLLM=true` | `VLLMModelManager` — 3 models sleep/wake on one GPU |
| **Transformers** (default) | *(unset)* | `MedGemmaAgent` — HuggingFace 4-bit quantization |
| **Simulated** (no GPU) | `SIMULATED_MODE=true` | Mock responses, zero GPU usage |

### vLLM Setup (medgemma-assistant project)

```bash
# Activate the uv project environment
cd /home/deepu/MedGemma

# Install vLLM extra (already installed in this project)
uv pip install "medgemma-assistant[vllm]"

# Start with vLLM backend
USE_VLLM=true uv run python main.py

# Optional: disable FunctionGemma or MedASR to save RAM
# (configure via VLLMModelManager kwargs in load_models_lazy)
```

### VLLMModelManager (`src/agent/vllm_manager.py`)

Manages **FunctionGemma (270M) + MedGemma (4B) + MedASR** with `vllm.sleep(level=2)`:
- Level-2 sleep offloads weights **and** KV cache to CPU — GPU is fully free between calls
- Only one model awake at a time; an `asyncio.Lock` serialises wake/sleep transitions
- `chat(message)` — text-only inference, used by Diagnostic Council and SOAP generation
- `generate_medgemma(prompt, image)` — multimodal inference (text + optional PIL image)
- `generate_functiongemma(prompt)` — routing/function-call decisions (270M)
- `transcribe_audio_file / transcribe_audio_bytes` — forwards to MedASR

### Memory Config (RTX 5060 8 GB / single GPU)

**Root cause of OOM:** vLLM profiles encoder memory by running dummy forward passes with `max_num_batched_tokens / tokens_per_image` images. At the default `max_num_batched_tokens=8192`, this is 32 images → ~3.4 GB activation memory during init — overflowing 8 GB combined with the 3.5 GB quantized model. Quantizing weights does NOT help (activations are always bfloat16). The actual fix is reducing the profiling batch size.

Default constructor values tuned for 8 GB VRAM:

| Parameter | Default | Reason |
|-----------|---------|--------|
| `quantization` | `"bitsandbytes"` | 4-bit reduces MedGemma 4B weight storage: 8 GB → 3.5 GB |
| `dtype` | `"bfloat16"` | Stable numerics; activations always in bf16 regardless of quantization |
| `enforce_eager` | `True` | Avoids ~0.5 GB CUDA graph overhead |
| `max_model_len` | `4096` | Reduces KV-cache footprint |
| `gpu_memory_utilization` | `0.85` | Leaves headroom for OS/CUDA context |
| `max_num_batched_tokens` | `1024` | **Key fix.** Reduces encoder profiling from 32 images → 4 images → ~0.4 GB activation memory. Leaves 0.6 GB for KV cache (4,480 tokens). Vision fully enabled. |
| `enable_vision` | `True` | Full multimodal inference. Set `False` only if 1024 still OOMs — uses `limit_mm_per_prompt={"image": 0}` to skip encoder profiling entirely. |

Memory breakdown at default settings:
```
Weights (4-bit):        3.73 GB
Encoder profiling:      ~0.40 GB  (4 images × 256 tokens)
KV cache pages:         ~0.60 GB  (4,480 tokens)
CUDA context + misc:    ~2.50 GB
Total:                  ~7.23 GB  ← fits in 8 GB at gpu_memory_utilization=0.85
```

