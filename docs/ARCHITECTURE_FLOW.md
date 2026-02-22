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
       └──────────────┼──────────────┘
                      ▼
  ┌───────────────────────────────────────────┐
  │          Enhanced SOAP Note               │
  │  S: Subjective  │ O: Objective            │
  │  A: Assessment   │ P: Plan                │
  │  + ICD-10 codes, confidence, alerts       │
  │  + Incidental vs correlated findings      │
  └───────────────────┬───────────────────────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
  ┌──────────┐ ┌───────────┐ ┌───────────┐
  │Diagnostic│ │ SOAP      │ │ Physician │
  │ Council  │ │ Compliance│ │ Approval  │
  │          │ │           │ │           │
  │ 5 Opins  │ │ Symptom   │ │ Approve   │
  │ Consensus│ │ Flags     │ │ or Edit   │
  └──────────┘ └───────────┘ └─────┬─────┘
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
│ Detection│   │ Classifcation│
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

## 4. Registered Tools (9 total)

```
  ┌─────────────────────────────────────────────┐
  │           FunctionGemma Tool Router          │
  └──────────────────┬──────────────────────────┘
                     │
  ┌──────────────────┼──────────────────────────┐
  │                  │                          │
  ▼                  ▼                          ▼
  EHR Tools        Action Tools          Memory Tools
  ──────────       ────────────          ────────────
  fetch_ehr        schedule_appt        recall_memory
  update_ehr       order_lab_tests      save_memory
  check_drug_ix    notify_care_team
  get_prior_img
```

---

## 5. Diagnostic Council

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
          └─────────────────┘
```

---

## 6. Patient Portal Safety

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

## 7. Request Sequence

```
  Physician        Web UI         FunctionGemma     MedGemma       EHR        Mem0
     │                │                │               │            │           │
     │──Start────────►│                │               │            │           │
     │  encounter     │──Recall───────────────────────────────────────────────►│
     │                │◄─Past encounters──────────────────────────────────────│
     │                │──Route query──►│               │            │           │
     │                │                │               │            │           │
     │          ┌─────┼────────────────┼───────────────┼────────────┼───┐       │
     │          │ ALT │ Simple action  │               │            │   │       │
     │          │     │                │──Execute─────────────────►│   │       │
     │          │     │◄───────────────┼──Result───────────────────│   │       │
     │          ├─────┼────────────────┼───────────────┼────────────┼───┤       │
     │          │     │ Medical query  │               │            │   │       │
     │          │     │                │──Escalate───►│            │   │       │
     │          │     │                │              ││ Analyze    │   │       │
     │          │     │                │              ││ Correlate  │   │       │
     │          │     │                │              ││ ICD-10     │   │       │
     │          │     │◄───────────────┼──SOAP note──│            │   │       │
     │          └─────┼────────────────┼───────────────┼────────────┼───┘       │
     │                │                │               │            │           │
     │◄──Display──────│                │               │            │           │
     │──Approve──────►│                │               │            │           │
     │                │──Update EHR──────────────────────────────►│           │
     │                │──Save encounter───────────────────────────────────────►│
     │                │                │               │            │           │
```

---

## 8. Component Summary

| Layer | Component | Technology | Purpose |
|-------|-----------|------------|---------|
| Auth | Role-Based Access | Password + 4 Roles | Doctor, Nurse, Admin, Patient |
| Routing | FunctionGemma | Gemma 3 270M | Tool selection and workflows |
| Reasoning | MedGemma | 4B multimodal | Medical analysis and SOAP |
| Correlation | Clinical Correlator | Rule-based | Artifact detection, incidental vs correlated |
| Intelligence | Clinical Intel | Rule-based | ICD-10, drug interactions, alerts |
| Council | Diagnostic Council | Multi-rollout | 5 opinions + consensus |
| Compliance | SOAP Checker | Rule-based | Symptom flags, documentation rates |
| Portal | Patient Assistant | NLP + Rules | Emergency detection, guardrails |
| Memory | Mem0 | LLM + Vector DB | Persistent cross-encounter memory |
| History | History Service | FHIR queries | Timeline, medications, imaging |
| EHR | FHIR Server | Mock / Real | Patient data storage |
| Frontend | FastAPI + JS | WebSocket + REST | Real-time UI, 4 feature pages |
| Testing | pytest | 72 tests | Full coverage, no GPU needed |
