# MedGemma Feature–Backend Map

Maps each implemented feature to its module, key classes/functions, HTTP routes, and required environment variables.

## Feature × Backend Table

| # | Feature | Module(s) | Key Classes / Functions | HTTP Routes | Env Vars |
|---|---------|-----------|-------------------------|-------------|----------|
| 1 | **Audit Logging** | `src/audit/audit_logger.py` | `AuditLogger`, `AuditEvent`, `get_audit_logger()` | `GET /api/audit/recent`<br>`GET /api/audit/patient/{id}` | `FIREBASE_*` (optional, for Firestore persistence) |
| 2 | **LACE Readmission Scoring** | `src/inpatient/discharge.py` | `InpatientDischargePlanner._compute_lace()`<br>`_compute_charlson_score()` | `POST /api/inpatient/{id}/discharge-summary` | — |
| 3 | **Expanded Safety Rules** | `src/inpatient/safety.py` | `InpatientSafetyService._check_falls_risk()`<br>`_check_pressure_ulcer_risk()`<br>`_check_antibiotic_deescalation()`<br>`_check_glycemic_control()` | `GET /api/inpatient/safety`<br>`GET /api/inpatient/{id}/safety` | — |
| 4 | **Prior Auth + Referral** | `src/auth/prior_auth.py`<br>`src/referral/referral_letter.py` | `PriorAuthService`, `PriorAuthRequest`<br>`ReferralLetterService`, `ReferralLetter` | `GET /api/prior-auth/request/{auth_id}`<br>`POST /api/prior-auth/request/{auth_id}/approve`<br>`POST /api/prior-auth/request/{auth_id}/deny`<br>`GET /api/prior-auth/{patient_id}`<br>`POST /api/prior-auth/{patient_id}/detect`<br>`GET /api/referral/{patient_id}`<br>`POST /api/referral/{patient_id}/generate` | `FIREBASE_*` (optional) |
| 5 | **Feature–Backend Map** | `docs/feature_backend_map.md` | — | — | — |
| 6 | **RAG Embedding Cache** | `src/council/rag.py` | `embed()`, `_embedding_cache` (OrderedDict LRU)<br>`_sha256_hex()` | — (internal, called by council deliberation) | — |
| 7 | **Performance Profiling** | `src/monitoring/perf_tracker.py` | `track_perf()` decorator<br>`get_stats()` | `GET /api/metrics` | — |
| 8 | **ICD-10 NLM Lookup** | `src/clinical/intelligence.py` | `ClinicalIntelligence.lookup_icd10()`<br>`lookup_icd10_nlm()`<br>`_nlm_icd10_lookup_cached()` (LRU-cached) | — (internal, called by SOAP/council pipelines) | Network access to `clinicaltables.nlm.nih.gov` |
| 9 | **Medication Reconciliation** | `src/inpatient/discharge.py` | `InpatientDischargePlanner.reconcile_medications()`<br>`MedReconciliation` dataclass | `GET /api/inpatient/{id}/med-reconciliation` | — |
| 10 | **Multi-Hospital Config** | `src/config/hospital_config.py`<br>`src/ehr/fhir_mock.py` | `HospitalRegistry`, `Hospital`<br>`get_hospital_registry()` | `GET /api/hospitals`<br>`GET /api/hospitals/{hospital_id}`<br>`POST /api/hospitals`<br>`GET /api/hospitals/{hospital_id}/patients` | `FIREBASE_*` (optional, for Firestore persistence) |

---

## Instrumented Routes (Performance Tracking)

The following routes are decorated with `@track_perf()` and appear in `GET /api/metrics`:

| Operation Key | Route |
|---|---|
| `council_deliberation` | `POST /api/council/deliberate` |
| `council_iterative` | `POST /api/council/iterative-deliberate` |
| `rounding` | `POST /api/inpatient/{id}/rounding-note` |
| `handoff` | `POST /api/inpatient/{id}/sbar` |
| `discharge_summary` | `POST /api/inpatient/{id}/discharge-summary` |

---

## Audit Event Types

Events logged by `AuditLogger` and queryable via `GET /api/audit/recent`:

| Event Type | Trigger |
|---|---|
| `SOAP_GENERATED` | SOAP note generation via `POST /api/encounters/{id}/generate-soap` |
| `COUNCIL_DELIBERATION` | Council deliberation (standard and iterative) |
| `HANDOFF_GENERATED` | Rounding note or SBAR generation |
| `DISCHARGE_PLANNED` | Discharge summary generation |

---

## Environment Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | No | — | Path to Firebase service account JSON for Firestore persistence (audit logs, hospital registry, referral letters, prior auth) |
| `FIREBASE_PROJECT_ID` | No | — | Firebase project ID (auto-detected from credentials if omitted) |
| `FIREBASE_KEY_PATH` | No | `firebase-key.json` | Alternative path to Firebase credentials file |
| `SIMULATED_MODE` | No | `"false"` | Set to `"true"` to bypass GPU model loading and use mock AI responses |
| `USE_VLLM` | No | `"false"` | Set to `"true"` to use vLLM backend for inference |
| `VLLM_BASE_URL` | No | — | Base URL for vLLM server when `USE_VLLM=true` |
| `ANTHROPIC_API_KEY` | No | — | Used by Claude-based agents (if applicable) |

> **Note:** Firebase environment variables are all optional. When Firebase is not available, audit logs are
> kept in-memory only (ring buffer, max 1000 events), hospital configurations are in-memory only, and
> referral letters / prior auth requests are not persisted across restarts.

---

## Demo Patient Hospital Assignment

| Patient | Name | Hospital | Ward |
|---|---|---|---|
| P001 | Sarah Wilson | GENERAL (General Hospital, Chicago) | Outpatient |
| P002 | Carlos Martinez | GENERAL (General Hospital, Chicago) | Outpatient |
| P003 | John Doe | GENERAL (General Hospital, Chicago) | Outpatient |
| P004 | Raymond Okafor | GENERAL (General Hospital, Chicago) | ICU |
| P005 | Dorothy Chen | COMMUNITY (Community Medical Center, New York) | Cardiology |
