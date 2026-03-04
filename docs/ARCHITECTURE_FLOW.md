# MedGemma Clinical Assistant — Architecture Flow

## 1. End-to-End Encounter Flow

```
  ┌────────────────┐     ┌──────────────────┐
  │ Voice / Text   │     │ X-ray Image      │
  │ Input          │     │ Upload           │
  └───────┬────────┘     └────────┬─────────┘
          │                       │
          ▼                       ▼
  ┌───────────────────────────────────────────┐
  │          FunctionGemma Router (270M)      │
  │                                           │
  │  Simple action?──► Tool Execution         │
  │  Medical query?──► Escalate to MedGemma   │
  └───────────────────┬───────────────────────┘
                      │
                      ▼
  ┌───────────────────────────────────────────┐
  │          MedGemma 4B (Multimodal)         │
  │  • Vision Encoder (SigLIP)                │
  │  • Medical Reasoning                      │
  │  • SOAP Note Generation                   │
  └───────────────────┬───────────────────────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
  ┌──────────┐ ┌───────────┐ ┌───────────┐
  │ Clinical │ │ Clinical  │ │ Mem0      │
  │ Correlat │ │ Intel     │ │ Memory    │
  │          │ │           │ │ Recall    │
  │ Artifact │ │ ICD-10    │ │           │
  │ Detect   │ │ Drug Ix   │ │ Past      │
  │ Finding  │ │ Critical  │ │ Encounters│
  │ Classify │ │ Alerts    │ │ Allergies │
    └────┬─────┘ └─────┬─────┘ └─────┬─────┘
      │              │              │
      │              │       ┌───────────────┐
      │              │       │ Local Trends  │
      │              │       │ + Ext Vocab   │
      │              │       │ (MeSH + ICD)  │
      │              │       └──────┬────────┘
      └──────────────┼──────────────┼────────
                      ▼
  ┌───────────────────────────────────────────┐
  │          Enhanced SOAP Note               │
  │  S: Subjective  │ O: Objective            │
  │  A: Assessment  │ P: Plan                 │
  │  + ICD-10 codes, confidence, alerts       │
  │  + Incidental vs correlated findings      │
  └───────────────────┬───────────────────────┘
                      │
          ┌───────────┼─────────────────────┐
          ▼           ▼                     ▼
  ┌──────────┐ ┌───────────┐       ┌──────────────────┐
  │Diagnostic│ │ SOAP      │       │ PubMed           │
  │ Council  │ │ Compliance│       │ Synthesis Agent  │
  │          │ │           │       │ (BackgroundTask) │
  │ 3–7 Ops  │ │ Symptom   │       │                  │
  │ Consensus│ │ Flags     │       │ case_matcher     │
  │ + PubMed │ └───────────┘       │ ebm_validator    │
  │ ZebraHunt│                     │ ddi_monitor      │
  └──────────┘                     └────────┬─────────┘
                                            │
                      ┌─────────────────────┘
                      ▼
  ┌───────────────────────────────────────────┐
  │          Physician Approval UI            │
  │  • SOAP Note review                       │
  │  • PubMed literature panel (polled)       │
  │  • Approve or Edit                        │
  └───────────────────┬───────────────────────┘
                      │
                      ▼
               ┌────────────┐
               │ Update EHR │
               │ Save Mem0  │
               └────────────┘
```

---

## 2. Dual-Model Routing

```
                    ┌─────────────────┐
                    │ Incoming Query  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ Contains Image? │
                    └───┬─────────┬───┘
                   YES  │         │  NO
                        ▼         ▼
              ┌──────────┐  ┌─────────────┐
              │ MedGemma │  │ Query Type? │
              │ Vision   │  └──┬──────┬───┘
              │ (4B)     │     │      │
              └────┬─────┘  Simple  Clinical
                   │         │      │
                   │         ▼      ▼
                   │    ┌────────┐ ┌──────────┐
                   │    │Function│ │ MedGemma │
                   │    │Gemma   │ │ Reasoning│
                   │    │(270M)  │ │ (4B)     │
                   │    └───┬────┘ └────┬─────┘
                   │        │           │
                   │        ▼           │
                   │   ┌─────────┐      │
                   │   │ Tool    │      │
                   │   │Execute  │      │
                   │   └───┬─────┘      │
                   │       │            │
                   ▼       ▼            ▼
              ┌─────────────────────────────┐
              │     Response to Physician   │
              └─────────────────────────────┘
```

---

## 3. Clinical Correlation Pipeline

```
  ┌─────────────────────────────────┐
  │ Imaging Findings from MedGemma  │
  └──────────┬──────────────────────┘
             │
     ┌───────┴───────┐
     ▼               ▼
┌──────────┐   ┌──────────────┐
│ Artifact │   │ Finding      │
│ Detection│   │ Classification│
└────┬─────┘   └──────┬───────┘
     │                │
     ▼                ▼
┌──────────┐   ┌──────────────────────────────┐
│ Quality  │   │ Correlate with Symptoms      │
│          │   ├──────────────────────────────┤
│Diagnostic│   │ CRITICAL ──► Immediate Alert │
│Acceptable│   │ MATCHES  ──► Significant     │
│Degraded  │   │ NO MATCH ──► Incidental      │
│Non-Diag  │   │              + prevalence %  │
└──────────┘   └──────────────────────────────┘

  Prevalence Database: 20+ entries from radiology literature
  ─────────────────────────────────────────────────────────
  disc bulge ........... 30-40% of asymptomatic adults
  renal cyst ........... 27-32% of adults over 50
  pulmonary nodule ..... 25-50% of chest CTs
  meniscal tear ........ up to 36% over age 45
  rotator cuff tear .... 20-54% of adults over 60
```

---

## 4. Registered Tools (10 total)

```
  ┌─────────────────────────────────────────────┐
  │           FunctionGemma Tool Router          │
  └──────────────────┬──────────────────────────┘
                     │
  ┌──────────────────┼──────────────────────────┐
  │                  │                          │
  ▼                  ▼                          ▼
  EHR Tools        Action Tools          Memory / Research Tools
  ──────────       ────────────          ─────────────────────────
  fetch_ehr        schedule_appt        recall_memory
  update_ehr       order_lab_tests      save_memory
  check_drug_ix    notify_care_team     search_pubmed
  get_prior_img
```

---

## 5. PubMed Synthesis Flow

```
  ┌─────────────────────────────────────────────────────┐
  │                    Trigger Sources                  │
  │  1) SOAP generation → BackgroundTask                │
  │  2) /api/council/deliberate → sync call             │
  │  3) /api/ai-portal/chat → intent-based sync call    │
  │  4) Direct /api/pubmed/* endpoints                  │
  └─────────────────────────┬───────────────────────────┘
                            │
                   ┌────────▼────────┐
                   │   Mode Select   │
                   └──┬──────┬───┬───┘
                      │      │   │
              case_  │  ebm_ │   │ ddi_
              matcher│  valid│   │ monitor
                      ▼      ▼   ▼
         ┌───────────────────────────────────────┐
         │          NCBI E-utils API             │
         │  esearch → efetch → parse XML         │
         │  Rate: 3 req/s (10 with API key)      │
         └───────────────┬───────────────────────┘
                         │
                ┌────────▼────────┐
                │  MedGemma 4B    │
                │  Synthesize     │
                │  results into   │
                │  summary +      │
                │  mode output    │
                └────────┬────────┘
                         │
              ┌──────────┴──────────────┐
              │  PubMedSearchResult     │
              │  • summary              │
              │  • key_findings         │
              │  • citation_list        │
              │  • mode-specific:       │
              │    rare_diagnoses /     │
              │    divergences /        │
              │    ddi_alerts           │
              └──────────┬──────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
  Encounter UI     Council Panel    AI Chat Panel
  (polled every    (rendered        (inline below
   3.5s until      after deliber-   assistant
   complete)       ation)           message)
```

---

## 6. Diagnostic Council — LangGraph StateGraph

Orchestrated via a LangGraph `StateGraph` (`src/council/graph.py`).

```
  START
    └─► initialize
          └─► retrieve_context  (RAG: compress raw_note → top-5 symptom-relevant excerpts)
                └─► [Send×N] generate_r1_opinion  (parallel fan-out, N=num_rollouts default 5)
                      │
                      │  Each branch: stateless prompt, sees only raw case + JSON schema
                      │  Outputs merged via Annotated[list[dict], operator.add]
                      │
                      └─► calculate_consensus
                            ├─ STRONG    > 80% agreement
                            ├─ MODERATE  60–80%
                            ├─ WEAK      40–60%
                            └─ SPLIT     < 40%
                                  │
                                  └─► run_pubmed  (PubMed Zebra Hunt — case_matcher)
                                        │
                              ┌─────────┴─────────────────────────────────┐
                              │ iterative mode                             │ standard mode
                              │ + rare diagnoses found                     │ or no rare dx
                              ▼                                            ▼
               [Send×N] generate_r2_opinion                              END
                 (rare dx names injected                (short-circuit,
                  into each R2 prompt)                   skip Round 2)
                        │
                        └─► calculate_r2_consensus
                              │
                              └─► END  (consensus_shifted flag set if R2 ≠ R1)
```

Key LangGraph patterns:
- `Annotated[list[dict], operator.add]` on `opinions` and `r2_opinions` — merges parallel Send branches without race conditions
- Two distinct node names (`generate_r1_opinion` → `calculate_consensus`, `generate_r2_opinion` → `calculate_r2_consensus`) share the same `_opinion_node` function — enables distinct downstream routing without code duplication
- `retrieve_context` is a no-op when `raw_note` is empty — zero overhead for standard usage

---

## 7. Patient Portal Safety

```
  ┌──────────────────┐
  │ Patient Question │
  └────────┬─────────┘
           │
  ┌────────▼──────────────┐
  │ Emergency keywords?   │
  │ chest pain, seizure,  │
  │ bleeding, choking ... │
  └───┬───────────────┬───┘
     YES              NO
      │                │
      ▼                ▼
  ┌────────┐   ┌──────────────┐
  │ CALL   │   │ Guardrails?  │
  │ 911    │   │ stop meds,   │
  │ NOW    │   │ change dose  │
  └────────┘   └──┬────────┬──┘
                 YES       NO
                  │         │
                  ▼         ▼
          ┌──────────┐ ┌─────────────┐
          │ Redirect │ │ Categorize  │
          │ to       │ │ & Answer    │
          │ Provider │ │             │
          └──────────┘ │ • Medication│
                       │ • Symptoms  │
                       │ • Appts     │
                       │ • General   │
                       └─────────────┘
```

---

## 8. AI Chat Portal Flow

```
  Physician
     │
     │  (select patient or enter manual context)
     │  (optionally upload image + draw annotation boxes)
     │  (type or dictate message)
     ▼
  ┌───────────────────────────────────────────┐
  │          /api/ai-portal/chat              │
  │                                           │
  │  1. Assemble context (patient + image +   │
  │     annotations + conversation history)  │
  │  2. Call MedGemma (process_query)         │
  │  3. Intent detection on user message      │
  │     • ddi_keywords  → ddi_monitor         │
  │     • ebm_keywords  → ebm_validator       │
  │     • zebra_keywords → case_matcher       │
  │  4. Run PubMed synthesis (if intent match)│
  │  5. Return response + pubmed_context      │
  └───────────────────────────────────────────┘
     │
     ▼
  Chat Panel renders:
  • MedGemma response bubble (markdown)
  • PubMed collapsible pill (if enrichment ran)
    └─ summary + rare_diagnoses / divergences
       / ddi_alerts + key findings + citations
```

---

## 9. Request Sequence

```
  Physician        Web UI         FunctionGemma     MedGemma       EHR        Mem0       PubMed
     │                │                │               │            │           │           │
     │──Start────────►│                │               │            │           │           │
     │  encounter     │──Recall───────────────────────────────────────────────►│           │
     │                │◄─Past encounters──────────────────────────────────────│           │
     │                │──Route query──►│               │            │           │           │
     │                │                │               │            │           │           │
     │          ┌─────┼────────────────┼───────────────┼────────────┼───┐       │           │
     │          │ ALT │ Simple action  │               │            │   │       │           │
     │          │     │                │──Execute─────────────────►│   │       │           │
     │          │     │◄───────────────┼──Result───────────────────│   │       │           │
     │          ├─────┼────────────────┼───────────────┼────────────┼───┤       │           │
     │          │     │ Medical query  │               │            │   │       │           │
     │          │     │                │──Escalate───►│            │   │       │           │
     │          │     │                │              ││ Analyze    │   │       │           │
     │          │     │                │              ││ Correlate  │   │       │           │
     │          │     │                │              ││ ICD-10     │   │       │           │
     │          │     │◄───────────────┼──SOAP note──│            │   │       │           │
     │          └─────┼────────────────┼───────────────┼────────────┼───┘       │           │
     │                │                │               │            │           │           │
     │◄──Display──────│                │               │            │           │           │
     │                │──PubMed bg task (async)────────────────────────────────────────────►│
     │                │  (case_matcher + ebm_validator + ddi_monitor)                       │
     │                │◄─Poll /pubmed-insights─────────────────────────────────────────────│
     │◄──PubMed panel─│                │               │            │           │           │
     │──Approve──────►│                │               │            │           │           │
     │                │──Update EHR──────────────────────────────►│           │           │
     │                │──Save encounter───────────────────────────────────────►│           │
     │                │                │               │            │           │           │
```

---

## 10. Component Summary

| Layer | Component | Technology | Purpose |
|-------|-----------|------------|---------|
| Auth | Role-Based Access | Password + 5 Roles | Doctor, Nurse, Resident, Admin, Patient |
| Routing | FunctionGemma | Gemma 3 270M | Tool selection and workflows |
| Reasoning | MedGemma | 4B multimodal | Medical analysis and SOAP |
| Correlation | Clinical Correlator | Rule-based | Artifact detection, incidental vs correlated |
| Intelligence | Clinical Intel | Rule-based | ICD-10, drug interactions, alerts |
| Council | Diagnostic Council | LangGraph StateGraph + MedGemma | N rollouts (default 5) parallel opinions + consensus + iterative PubMed evidence loop |
| RAG | Context Compression | sentence-transformers / TF-IDF | Chunks raw clinical notes; retrieves top-5 symptom-relevant excerpts before council fan-out |
| PubMed | Synthesis Agent | NCBI E-utils + LLM | Case matching, EBM validation, DDI monitoring |
| Trends | Local Trend Engine | RSS + MeSH + Firestore cache | Location-aware environmental/public-health context |
| AI Chat | AI Portal | MedGemma + Canvas | Multimodal physician chat with annotations |
| Compliance | SOAP Checker | Rule-based | Symptom flags, documentation rates |
| Portal | Patient Assistant | NLP + Rules | Emergency detection, guardrails |
| Memory | Mem0 | LLM + Vector DB | Persistent cross-encounter memory |
| History | History Service | FHIR queries | Timeline, medications, imaging |
| EHR | FHIR Server | Mock / Real | Patient data storage |
| Frontend | FastAPI + JS | WebSocket + REST | Real-time UI, 6 feature pages |
| Testing | pytest | 72 tests | Full coverage, no GPU needed |
| Audit | AuditLogger | deque ring buffer + Firestore | Immutable event trail for all clinical AI actions |
| Performance | PerfTracker | deque rolling stats | Latency profiling for major API operations |
| Hospital | HospitalRegistry | In-memory + Firestore | Multi-tenant hospital profiles with feature flags |
| Prior Auth | PriorAuthService | In-memory + Firestore | Prior auth detect, approve, deny workflow |
| Referral | ReferralLetterService | In-memory + Firestore | AI-generated specialist referral letters |
| Med Reconciliation | InpatientDischargePlanner | FHIR comparison | Admission vs. inpatient medication diff |

---

## 11. Local Trend Intelligence Flow

```
Patient location (FHIR) ───────────────┐
                    ▼
               Trend Query Builder
             (location-anchored RSS queries)
                    ▼
             Geo Relevance + De-dup Filter
                    ▼
        External Medical Vocabulary Enrichment
         (NLM MeSH + ICD-10 + local fallback)
                    ▼
            Firestore Shared Vocab Cache
           system_cache/medical_vocab_mesh
                    ▼
            Symptom-to-trend Correlation
                    ▼
    SOAP / MedGemma context + local_trend_insights response field
```

Notes:
- Trend context is supportive and non-diagnostic.
- Cache backend is configurable: `auto` / `firestore` / `local`.
- Optional vector enrichment can be toggled via env.

---

## 12. New Backend Services

| Service | Module | Routes |
|---------|--------|--------|
| Audit Logging | `src/audit/audit_logger.py` | `GET /api/audit/recent`, `GET /api/audit/patient/{id}` |
| Performance Profiling | `src/monitoring/perf_tracker.py` | `GET /api/metrics` |
| Prior Auth | `src/auth/prior_auth.py` | `GET/POST /api/prior-auth/*` |
| Referral Letters | `src/referral/referral_letter.py` | `GET/POST /api/referral/*` |
| Medication Reconciliation | `src/inpatient/discharge.py` | `GET /api/inpatient/{id}/med-reconciliation` |
| Multi-Hospital Registry | `src/config/hospital_config.py` | `GET/POST /api/hospitals/*` |
| LACE + Expanded Safety | `src/inpatient/discharge.py`, `src/inpatient/safety.py` | Embedded in discharge and safety routes |
