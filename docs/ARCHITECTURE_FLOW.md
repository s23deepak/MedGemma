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

## 6. Diagnostic Council

```
  ┌──────────────────────────────────────────┐
  │   Case: Symptoms + History + Imaging     │
  └────┬─────┬──────┬──────┬──────┬──────────┘
       │     │      │      │      │
       ▼     ▼      ▼      ▼      ▼
     Op.1  Op.2   Op.3   Op.4   Op.5
   (indep) (indep) (indep) (indep) (indep)
       │     │      │      │      │
       └─────┴──────┼──────┴──────┘
                    ▼
          ┌─────────────────┐
          │ Consensus       │
          │ Analysis        │
          ├─────────────────┤
          │ STRONG    >80%  │
          │ MODERATE  60-80%│
          │ WEAK      40-60%│
          │ SPLIT     <40%  │
          └────────┬────────┘
                   │
                   ▼
          ┌─────────────────┐
          │ PubMed Zebra    │
          │ Hunt (auto)     │
          │                 │
          │ case_matcher on │
          │ symptoms →      │
          │ rare_diagnoses  │
          └─────────────────┘
```

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
| Council | Diagnostic Council | Multi-rollout | 3–7 opinions + consensus + PubMed |
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
