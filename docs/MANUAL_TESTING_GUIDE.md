# MedGemma — Manual Testing Guide

> Step-by-step guide to test every feature from the UI.

---

## 1. Start the App

```bash
cd /home/deepu/MedGemma
SIMULATED_MODE=true uv run python main.py
```

Open **http://localhost:8000** in your browser.

> **Note:** `SIMULATED_MODE=true` runs without GPU — all AI responses are simulated.
> For real MedGemma inference, omit the flag (requires GPU + model weights).

---

## 2. Test Credentials

| Email | Password | Role | Access |
|-------|----------|------|--------|
| `admin@hospital.org` | `admin123` | Admin | Everything |
| `dr.smith@hospital.org` | `doc123` | Doctor | History, Compliance, Council, Encounters, AI Chat |
| `dr.jones@hospital.org` | `doc123` | Doctor | Same as above |
| `resident.lee@hospital.org` | `res123` | Resident | History, Council, Encounters, AI Chat |
| `nurse.garcia@hospital.org` | `nurse123` | Nurse | History, Encounters |
| `patient.p001@email.com` | `patient123` | Patient | Patient Portal only |

---

## 3. Feature Testing Checklist

### 3.1 Main Dashboard (Home Page)

1. Open http://localhost:8000
2. Verify the main page loads with navigation links
3. Check that all nav links are visible: Encounters, History, Compliance, Council, Patient Portal, AI Chat Portal, Shift Brief, Simulation

---

### 3.2 Patient List & EHR

Test the patient endpoints:

1. In browser, go to: `http://localhost:8000/api/patients`
   - Should see JSON with 2 patients: Sarah Wilson (P001) and Carlos Martinez (P002)
2. Go to: `http://localhost:8000/api/patients/P001`
   - Should see full patient summary with demographics, conditions, medications
3. Go to: `http://localhost:8000/api/patients/P999`
   - Should return 404 error

---

### 3.3 Clinical Encounter (The Main Workflow)

This is the core feature — start an encounter, upload an image, generate a SOAP note.

**Start an encounter** (use a tool like browser dev console or Postman):

```javascript
fetch('/api/encounters/start', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({patient_id: 'P001', chief_complaint: 'chest pain and cough'})
}).then(r => r.json()).then(console.log)
```

Copy the `session_id` from the response.

**Upload an X-ray image:**

```javascript
const formData = new FormData();
const blob = new Blob(['test'], {type: 'image/png'});
formData.append('file', blob, 'xray.png');
fetch('/api/encounters/SESSION_ID/image', {
  method: 'POST',
  body: formData
}).then(r => r.json()).then(console.log)
```

**Generate SOAP note:**

```javascript
fetch('/api/encounters/SESSION_ID/generate-soap', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({})
}).then(r => r.json()).then(console.log)
```

- Check that the response includes `pubmed_insights_status: "running"` (PubMed background task started)
- Check that the response includes `local_trend_insights` (may be `null` when no matching signals)
- Check the `📚 PubMed Literature` card appears in the right panel after a few seconds

**Validate location-aware trend correlation:**

1. Ensure a patient with location is selected (e.g., `P002` with `Miami` / Florida context in your seed data)
2. Add transcription text with respiratory symptoms, for example:

```javascript
fetch('/api/encounters/SESSION_ID/transcription', {
  method: 'POST',
  headers: {'Content-Type': 'application/x-www-form-urlencoded'},
  body: new URLSearchParams({text: 'Patient has cough and shortness of breath after smoke exposure'})
}).then(r => r.json()).then(console.log)
```

3. Re-run `/generate-soap` and inspect `local_trend_insights` in response
   - Should include `matched_signal_count`, `matched_signals`, and disclaimer text

**Poll PubMed insights:**

```javascript
fetch('/api/encounters/SESSION_ID/pubmed-insights')
  .then(r => r.json()).then(console.log)
```

- Initially returns `{"status": "running"}`
- After 5–15 seconds returns `{"status": "completed", "summary": ..., "rare_diagnoses": [...], ...}`

**Approve to EHR:**

```javascript
fetch('/api/encounters/SESSION_ID/approve', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({})
}).then(r => r.json()).then(console.log)
```

---

### 3.4 Patient History Page

1. Go to: `http://localhost:8000/history`
   - Should render the history page template
2. Test the API directly:
   - `http://localhost:8000/api/history/P001/timeline` — encounter timeline
   - `http://localhost:8000/api/history/P001/medications` — medication list
   - `http://localhost:8000/api/history/P001/imaging` — imaging history

---

### 3.5 SOAP Compliance Monitor

1. Go to: `http://localhost:8000/compliance`
   - Should render the compliance dashboard
2. Run a compliance check:

```javascript
fetch('/api/compliance/check', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({})
}).then(r => r.json()).then(console.log)
```

3. View the compliance report:
   - `http://localhost:8000/api/compliance/report`
   - Should have `compliance_rate`, `flags`, and `total_documents`

---

### 3.6 Diagnostic Council

1. Go to: `http://localhost:8000/council`
   - Should render the council panel
2. Request a deliberation:

```javascript
fetch('/api/council/deliberate', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    symptoms: ['chest pain', 'shortness of breath', 'cough'],
    patient_history: 'Hypertension, smoker for 20 years',
    imaging_findings: 'Right lower lobe opacity'
  })
}).then(r => r.json()).then(console.log)
```

3. Check the response has:
   - `opinions` array (5 independent diagnoses)
   - `consensus_diagnosis` and `consensus_strength` (Strong/Moderate/Weak/Split)
   - `pubmed_insights` with `status`, `rare_diagnoses`, `key_findings`, `citation_list`
4. In the UI, scroll below the Discussion Summary — the **📚 PubMed — Zebra Hunt Results** panel should appear
5. View deliberation history:
   - `http://localhost:8000/api/council/history`

**Test iterative (Deep Dive) mode:**

```javascript
fetch('/api/council/iterative-deliberate', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    symptoms: ['chest pain', 'shortness of breath', 'cough', 'unexplained weight loss'],
    patient_history: 'Former smoker, 20 pack-year history',
    imaging_findings: 'Right lower lobe opacity, mediastinal widening',
    num_rollouts: 5
  })
}).then(r => r.json()).then(console.log)
```

- Check response includes `r2_opinions`, `r2_consensus_diagnosis`, `r2_consensus_strength`
- `consensus_shifted` boolean should be present (true if R2 diagnosis differs from R1)

**Test RAG context compression (`raw_note` parameter):**

```javascript
fetch('/api/council/deliberate', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    symptoms: ['chest pain', 'dyspnea'],
    patient_history: 'HTN',
    imaging_findings: 'Mild cardiomegaly',
    raw_note: 'Patient is a 65-year-old male with a long history of hypertension and type 2 diabetes. He presents today with progressive exertional chest pain over the last two weeks. He denies rest pain or radiation. He has had prior cardiac workup in 2022 showing mild LVH. Current medications include metformin, lisinopril, and atorvastatin. Review of systems is positive for dyspnea on exertion and mild ankle swelling. Examination reveals BP 145/88, HR 82, SpO2 97%. Lungs clear. Mild bilateral ankle edema noted.'
  })
}).then(r => r.json()).then(console.log)
```

- The `raw_note` is chunked and the top-5 most symptom-relevant excerpts are extracted and injected into each opinion prompt
- Response should be the same structure — the RAG compression is internal to the graph

---

### 3.7 Patient Portal

1. Go to: `http://localhost:8000/patient-portal`
   - Should render the patient portal page

2. **Test a normal question:**

```javascript
fetch('/api/portal/ask', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    patient_id: 'P001',
    question: 'What are the side effects of metformin?'
  })
}).then(r => r.json()).then(console.log)
```

3. **Test emergency detection:**

```javascript
fetch('/api/portal/ask', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    patient_id: 'P001',
    question: 'I am having severe chest pain right now'
  })
}).then(r => r.json()).then(console.log)
```
   - Should return an emergency response telling to call 911

4. **Test guardrails:**

```javascript
fetch('/api/portal/ask', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    patient_id: 'P001',
    question: 'Can I stop taking my blood pressure medication?'
  })
}).then(r => r.json()).then(console.log)
```
   - Should redirect to provider, not give medication advice

5. **View patient summary:**
   - `http://localhost:8000/api/portal/P001/summary`

6. **View query history:**
   - `http://localhost:8000/api/portal/P001/history`

---

### 3.8 Patient Memory (Mem0)

> **Requires `OPENAI_API_KEY` env variable.** Without it, memory endpoints return graceful fallback responses.

1. **Get all memories:**
   - `http://localhost:8000/api/memory/P001`

2. **Add a memory:**

```javascript
fetch('/api/memory/P001/add', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    text: 'Patient reported penicillin allergy during visit on 2024-01-15'
  })
}).then(r => r.json()).then(console.log)
```

3. **Search memories:**

```javascript
fetch('/api/memory/P001/search', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({query: 'allergies'})
}).then(r => r.json()).then(console.log)
```

4. **Delete a memory** (use a memory_id from step 1):

```javascript
fetch('/api/memory/P001/MEMORY_ID', {
  method: 'DELETE'
}).then(r => r.json()).then(console.log)
```

---

### 3.9 Health Check

- `http://localhost:8000/api/health`
- Should return component status for: `fhir_server`, `soap_generator`, `agent`, `asr`

---

### 3.10 AI Chat Portal

1. Go to: `http://localhost:8000/ai-portal`
   - Should show three-panel layout: Patient Context | Medical Imaging | Chat

2. **Select a patient** in the left panel (click Sarah Wilson or Carlos Martinez)
   - Patient demographics and conditions should load below

3. **Manual entry mode** — click "✏️ Manual Entry":
   - Type or dictate patient context in the text area

4. **Upload an image** in the center panel (drop or click):
   - The toolbar with View / Annotate / Clear Boxes should appear
   - Click **📐 Annotate** and draw a bounding box on the image
   - An annotation tag should appear in the strip below the image

5. **Send a clinical question** in the right panel:

```javascript
// From browser console:
// (the UI does this via fetch, but you can test the API directly)
fetch('/api/ai-portal/chat', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    message: 'What are the differential diagnoses for this presentation?',
    patient_context: {name: 'Sarah Wilson', age: 58},
    conversation_history: []
  })
}).then(r => r.json()).then(console.log)
```

6. **Test DDI intent** (should trigger `ddi_monitor` PubMed enrichment):

```javascript
fetch('/api/ai-portal/chat', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    message: 'Are there any drug interactions between lisinopril and albuterol?',
    patient_context: {medications: ['Lisinopril 10mg', 'Albuterol inhaler']},
    conversation_history: []
  })
}).then(r => r.json()).then(console.log)
```
   - Response should include `pubmed_context` with `mode: "ddi_monitor"`

7. **Test EBM intent** (should trigger `ebm_validator`):

```javascript
fetch('/api/ai-portal/chat', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    message: 'What is the evidence-based first-line treatment for community-acquired pneumonia?',
    conversation_history: []
  })
}).then(r => r.json()).then(console.log)
```
   - Response should include `pubmed_context` with `mode: "ebm_validator"`

8. **Test Zebra Hunt intent** (should trigger `case_matcher`):

```javascript
fetch('/api/ai-portal/chat', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    message: 'What rare diagnosis could explain chest pain with atypical night sweats?',
    conversation_history: []
  })
}).then(r => r.json()).then(console.log)
```
   - Response should include `pubmed_context` with `mode: "case_matcher"` and `rare_diagnoses`
   - In the UI, a collapsible **📊 Evidence Check** pill should appear below the assistant bubble

---

### 3.11 PubMed Direct Endpoints

1. **Generic search (case_matcher mode):**

```javascript
fetch('/api/pubmed/search', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    mode: 'case_matcher',
    symptoms: ['chest pain', 'night sweats'],
    atypical_markers: ['young patient', 'no fever'],
    max_results: 3
  })
}).then(r => r.json()).then(console.log)
```

2. **Zebra Hunt endpoint:**

```javascript
fetch('/api/pubmed/zebra-hunt', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    common_symptoms: ['cough', 'fever'],
    atypical_markers: ['no response to antibiotics'],
    max_results: 3
  })
}).then(r => r.json()).then(console.log)
```

3. **EBM Validator:**

```javascript
fetch('/api/pubmed/validate-plan', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    assessment: 'Community-acquired pneumonia, moderate severity',
    plan: 'Azithromycin 500mg for 5 days, rest, fluids'
  })
}).then(r => r.json()).then(console.log)
```

4. **DDI Monitor for a patient:**
   - `http://localhost:8000/api/pubmed/ddi-monitor/P001`
   - Pulls Sarah Wilson's medications from FHIR and scans for interactions

---

### 3.12 Shift Brief

1. Go to: `http://localhost:8000/shift-brief`
2. Select provider + role and click Generate
3. Verify returned summary and patient cards load

---

### 3.13 Simulation

1. Go to: `http://localhost:8000/simulation`
2. Start a case and run through history/exam/investigation
3. Submit diagnosis and confirm scored feedback appears

---

### 3.14 Inpatient Workflow

**List admitted patients:**

```javascript
fetch('/api/inpatient/ward')
  .then(r => r.json()).then(console.log)
```

- Should return a list of admitted patients — demo data includes Raymond Okafor (P004, ICU Sepsis) and Dorothy Chen (P005, CHF)

**Generate a rounding progress note:**

```javascript
fetch('/api/inpatient/P004/rounding-note', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({})
}).then(r => r.json()).then(console.log)
```

- Check response includes `note_text` (full SOAP), `todo_items` list, `los_hours`, `source`

**Generate an SBAR handoff:**

```javascript
fetch('/api/inpatient/P004/sbar', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({})
}).then(r => r.json()).then(console.log)
```

- Check response includes `sbar` object with `situation`, `background`, `assessment`, `recommendation`, `contingency_plans`
- Check `completeness` object: `score`, `percentage`, `checks`, `missing_fields`
- A score below 100% means some required fields are absent — those are listed in `missing_fields`

**Run the safety watchlist:**

```javascript
fetch('/api/inpatient/safety')
  .then(r => r.json()).then(console.log)
```

- Raymond Okafor (P004) should trigger a **CRITICAL** VTE prophylaxis alert (admitted >24h, no order)
- Alerts sorted critical-first; each has `suggested_action` and `ai_explanation` fields

**Generate a discharge summary:**

```javascript
fetch('/api/inpatient/P005/discharge-summary', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({})
}).then(r => r.json()).then(console.log)
```

- Dorothy Chen (P005, CHF + CKD) should return `readmission_risk: "high"`
- Check `missing_fields` — any required fields absent from her record are explicitly listed as `MISSING`
- Check `medications` array contains per-drug counselling notes

---

---

### 3.15 Expanded Safety Rules

Run the safety dashboard and verify new alert types:

```javascript
fetch('/api/inpatient/safety')
  .then(r => r.json()).then(console.log)
```

For P004 (Raymond Okafor, ICU sepsis), expect alerts for:
- `falls_risk` — age and ICU admission factors
- `antibiotic_deescalation` — broad-spectrum antibiotics with available cultures
- `glycemic_control` — insulin active without recent glucose check
- Original VTE prophylaxis CRITICAL alert still present

Patient-specific safety check:
```javascript
fetch('/api/inpatient/P004/safety')
  .then(r => r.json()).then(console.log)
```

---

### 3.16 LACE Readmission Scoring

Generate a discharge summary and check the LACE fields:

```javascript
fetch('/api/inpatient/P005/discharge-summary', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({})
}).then(r => r.json()).then(d => {
  console.log('LACE score:', d.lace_score);
  console.log('LACE components:', d.lace_components);
  console.log('Readmission risk:', d.readmission_risk);
})
```

- `lace_score` should be ≥10 for Dorothy Chen (CHF + CKD) → `readmission_risk: "high"`
- `lace_components` shows `{l, a, c, e}` breakdown

---

### 3.17 Medication Reconciliation

```javascript
fetch('/api/inpatient/P004/med-reconciliation')
  .then(r => r.json()).then(console.log)
```

- `added_meds` — ICU medications started after admission (piperacillin, norepinephrine, insulin)
- `discontinued_meds` — pre-admission medications not continued
- `reconciliation_status` — `"complete"` or `"review_required"`

---

### 3.18 Prior Authorization

**Detect orders requiring prior auth:**

```javascript
fetch('/api/prior-auth/P001/detect', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    encounter_id: 'E1',
    orders_text: 'MRI brain, adalimumab 40mg',
    clinical_indication: 'headache with visual changes'
  })
}).then(r => r.json()).then(console.log)
```

- Expect 2 prior auth requests created: MRI (imaging) + adalimumab (medication)

**View all prior auths for patient:**

```javascript
fetch('/api/prior-auth/P001')
  .then(r => r.json()).then(console.log)
```

**Look up by auth_id** (use an auth_id from above):

```javascript
fetch('/api/prior-auth/request/AUTH_ID_HERE')
  .then(r => r.json()).then(console.log)
```

**Approve a request:**

```javascript
fetch('/api/prior-auth/request/AUTH_ID_HERE/approve', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({approved_by: 'dr.smith@hospital.org', notes: 'Clinically indicated'})
}).then(r => r.json()).then(console.log)
```

**Deny a request:**

```javascript
fetch('/api/prior-auth/request/AUTH_ID_HERE/deny', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({reason: 'Not medically necessary', notes: 'Try conservative management first'})
}).then(r => r.json()).then(console.log)
```

---

### 3.19 Referral Letters

**Generate referral letters:**

```javascript
fetch('/api/referral/P001/generate', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    encounter_id: 'E1',
    referral_orders: ['Neurology referral for worsening migraines', 'Ophthalmology referral for visual aura'],
    soap_note: null
  })
}).then(r => r.json()).then(console.log)
```

- Expect 2 letters in response, each with `letter_id`, `specialty`, `letter_text`, `created_at`

**View all referral letters:**

```javascript
fetch('/api/referral/P001')
  .then(r => r.json()).then(console.log)
```

---

### 3.20 Audit Log

```javascript
// Most recent 10 events
fetch('/api/audit/recent?limit=10')
  .then(r => r.json()).then(console.log)

// Events for a specific patient
fetch('/api/audit/patient/P004')
  .then(r => r.json()).then(console.log)
```

- Each event has: `event_id`, `timestamp`, `event_type`, `action`, `patient_id`, `user_id`, `success`
- Run some SOAP/council/discharge calls first to populate the log

---

### 3.21 Performance Metrics

```javascript
fetch('/api/metrics')
  .then(r => r.json()).then(console.log)
```

- Returns `{council_deliberation: {avg_ms, min_ms, max_ms, count}, rounding: {...}, ...}`
- Run council and inpatient routes first to populate; empty object if no calls made yet

---

### 3.22 Hospital Registry (Multi-Tenant)

```javascript
// List all hospitals
fetch('/api/hospitals')
  .then(r => r.json()).then(console.log)

// Get single hospital
fetch('/api/hospitals/COMMUNITY')
  .then(r => r.json()).then(console.log)

// Patients for a hospital
fetch('/api/hospitals/GENERAL/patients')
  .then(r => r.json()).then(console.log)

// Add a new hospital
fetch('/api/hospitals', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    hospital_id: 'REGIONAL',
    name: 'Regional Medical Center',
    timezone: 'America/Los_Angeles',
    formulary_restrictions: ['pembrolizumab'],
    features_enabled: {audit_log: true, prior_auth: true, referral: true, simulation: false}
  })
}).then(r => r.json()).then(console.log)
```

- GENERAL hospital patients: P001 (Sarah Wilson), P002 (Carlos Martinez), P003 (John Doe), P004 (Raymond Okafor)
- COMMUNITY hospital patients: P005 (Dorothy Chen)

---

## 4. Quick Smoke Test (All in One)

Paste this into the browser console to hit every major endpoint:

```javascript
async function smokeTest() {
  const results = {};

  // Health
  let r = await fetch('/api/health');
  results.health = r.status;

  // Patients
  r = await fetch('/api/patients');
  results.patients = r.status;

  r = await fetch('/api/patients/P001');
  results.patient_detail = r.status;

  // Encounter
  r = await fetch('/api/encounters/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({patient_id: 'P001', chief_complaint: 'test'})
  });
  const enc = await r.json();
  results.encounter_start = r.status;
  const sid = enc.session_id;

  // Generate SOAP
  r = await fetch(`/api/encounters/${sid}/generate-soap`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({transcription: 'Patient has cough and fever.'})
  });
  results.soap_generate = r.status;

  // PubMed poll
  r = await fetch(`/api/encounters/${sid}/pubmed-insights`);
  results.pubmed_poll = r.status;

  // History
  r = await fetch('/api/history/P001/timeline');
  results.timeline = r.status;

  // Compliance
  r = await fetch('/api/compliance/check', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({})
  });
  results.compliance = r.status;

  // Council
  r = await fetch('/api/council/deliberate', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({symptoms: ['headache'], patient_history: 'None', imaging_findings: 'Normal'})
  });
  results.council = r.status;

  // AI Chat Portal
  r = await fetch('/api/ai-portal/chat', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({message: 'What are the common causes of headache?', conversation_history: []})
  });
  results.ai_portal = r.status;

  // PubMed zebra hunt
  r = await fetch('/api/pubmed/zebra-hunt', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({common_symptoms: ['headache'], atypical_markers: []})
  });
  results.pubmed_zebra = r.status;

  // Portal
  r = await fetch('/api/portal/ask', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({patient_id: 'P001', question: 'What is aspirin used for?'})
  });
  results.portal = r.status;

  // Memory
  r = await fetch('/api/memory/P001');
  results.memory = r.status;

  // Inpatient — ward list
  r = await fetch('/api/inpatient/ward');
  results.inpatient_ward = r.status;

  // Inpatient — rounding note
  r = await fetch('/api/inpatient/P004/rounding-note', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({})
  });
  results.rounding_note = r.status;

  // Inpatient — SBAR
  r = await fetch('/api/inpatient/P004/sbar', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({})
  });
  results.sbar = r.status;

  // Inpatient — safety dashboard
  r = await fetch('/api/inpatient/safety');
  results.safety_dashboard = r.status;

  // Inpatient — discharge summary
  r = await fetch('/api/inpatient/P005/discharge-summary', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({})
  });
  results.discharge_summary = r.status;

  // Audit log
  r = await fetch('/api/audit/recent?limit=5');
  results.audit_recent = r.status;

  r = await fetch('/api/audit/patient/P004');
  results.audit_patient = r.status;

  // Performance metrics
  r = await fetch('/api/metrics');
  results.metrics = r.status;

  // Prior auth
  r = await fetch('/api/prior-auth/P001');
  results.prior_auth_list = r.status;

  r = await fetch('/api/prior-auth/P001/detect', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({encounter_id: 'E1', orders_text: 'MRI brain', clinical_indication: 'headache'})
  });
  results.prior_auth_detect = r.status;

  // Medication reconciliation
  r = await fetch('/api/inpatient/P004/med-reconciliation');
  results.med_reconciliation = r.status;

  // Hospitals
  r = await fetch('/api/hospitals');
  results.hospitals = r.status;

  r = await fetch('/api/hospitals/GENERAL/patients');
  results.hospital_patients = r.status;

  console.table(results);

  const allPassed = Object.values(results).every(s => s === 200);
  console.log(allPassed ? '✅ ALL ENDPOINTS OK' : '❌ SOME ENDPOINTS FAILED');
}

smokeTest();
```

All statuses should be `200`.
