# Clinical Simulation Engine — Resident Training & Debrief

**An AI-powered standardized patient system for immersive clinical education and competency assessment.**

---

## Overview

The **Clinical Simulation Engine** transforms MedGemma into a stateful standardized patient, enabling medical residents to practice clinical reasoning in a safe, controlled environment. Residents take history, examine, order investigations, and submit a diagnosis and management plan. The system scores the encounter across five clinical domains and generates detailed, actionable feedback per domain.

### Key Features

- **Stateful Patient Persona**: Powered by LangChain's `RunnableWithMessageHistory` — the patient never contradicts itself within a session
- **Structured Scoring**: Five-domain assessment (history, examination, investigations, diagnosis, management)
- **Debrief Generation**: AI-generated narrative feedback with specific coaching points
- **Session Namespace Isolation**: Per-resident session storage with automatic history release on scoring
- **HIPAA-Ready Audit Trail**: All interactions logged for quality assurance and learner progression tracking

---

## Architecture

### Core Components

#### 1. **Stateful Chat Chain** (`src/simulation/chat_chain.py`)

The LangChain-based message history system ensures patient consistency:

```
ChatPromptTemplate (system: case context + clinical state)
  + MessagesPlaceholder("history")   ← all prior turns injected here
  + HumanMessage(question)
        │
        ▼
MedGemmaRunnable(Runnable)           ← bridges LangChain messages → agent API
  ├─ agent.generate_medgemma()       (VLLMModelManager)
  └─ agent.chat()                    (MedGemmaAgent / HF Transformers)
        │ AIMessage
        ▼
RunnableWithMessageHistory           ← persists HumanMessage + AIMessage
  └─ InMemoryChatMessageHistory        into per-session store after every turn
       keyed by session_id
```

**Why stateful?** Every interaction is stored in conversation history and injected back into the next prompt. This prevents:
- Patient contradicting timeline ("pain started 2 hours ago" → later claim "pain started yesterday")
- Symptom evolution inconsistencies
- Vital sign changes that don't track

#### 2. **Case Repository** (`src/simulation/cases/`)

Pre-built clinical cases with:
- Patient demographics (age, gender, comorbidities)
- Chief complaint and HPI template
- Physical exam baseline
- Investigation results (structured lab/imaging findings)
- Diagnosis (ground truth)
- Management roadmap (appropriate workup sequence)

#### 3. **Scoring Engine** (`src/simulation/scorer.py`)

Evaluates resident performance across five domains:

| Domain | Criteria | Scoring |
|--------|----------|---------|
| **History** | Completeness of HPI, ROS, PMH capture | 0–100 |
| **Examination** | Appropriate physical exam findings documented | 0–100 |
| **Investigations** | Logical test ordering (cost-effectiveness, diagnostic yield) | 0–100 |
| **Diagnosis** | Differential generation and final diagnosis accuracy | 0–100 |
| **Management** | Treatment plan alignment with guidelines | 0–100 |

**Scoring logic**:
- Pattern-match resident inputs against expected findings
- Penalize redundant/unnecessary tests
- Reward early diagnostic closure with cost discipline
- Flag critical safety gaps (e.g., missed sepsis workup)

#### 4. **Debrief Generator** (`src/simulation/debrief.py`)

Generates structured narrative feedback via MedGemma:
- Domain-specific strengths and gaps
- Missed diagnostic opportunities
- Cost-benefit analysis (unnecessary imaging, labs)
- Evidence-based guideline deviations
- Coaching recommendations for next case

---

## API Routes

---

## Visual Walkthrough

### Resident Interface — Interactive Questioning

The resident engages with the standardized patient through a multi-tab interface. The patient's vitals and case context appear at the top, physical exam systems are organized by anatomical region, and the conversation history is displayed in real-time.

<img src="write-up images/Simulation Question.png" width="100%" alt="Simulation — interactive questioning interface with patient dialogue and exam systems"/>

**Interface Elements:**
- **Case Presentation**: Patient demographics, vitals, and chief complaint
- **System Selection**: Organize physical exam findings by anatomical system (General, Cardiovascular, Respiratory, Abdomen, Neurological, Extremities, etc.)
- **History Taking**: Bidirectional patient-doctor dialogue with suggested prompts
- **Learning Objectives**: Real-time guidance on what to assess
- **Quick Suggestions**: Pre-built questions to guide the resident

---

## API Routes

### Session Management

#### `POST /api/simulation/session/create`
Create a new resident simulation session.

**Input:**
```json
{
  "case_id": "case_mi_001",
  "resident_id": "R001",
  "hospital_id": "general"
}
```

**Output:**
```json
{
  "session_id": "sim_abc123",
  "case": {
    "title": "52M with Acute Chest Pain",
    "chief_complaint": "Chest pain × 2 hours",
    "patient_context": "HPI to be revealed"
  }
}
```

#### `GET /api/simulation/session/{session_id}`
Retrieve session metadata and history.

**Output:**
```json
{
  "session_id": "sim_abc123",
  "resident_id": "R001",
  "case_id": "case_mi_001",
  "created_at": "2025-03-22T10:30:00Z",
  "status": "in_progress",
  "turn_count": 5,
  "message_history": [...]
}
```

---

### Patient Interaction

#### `POST /api/simulation/session/{session_id}/ask`
Ask the standardized patient a question or describe a finding.

**Input:**
```json
{
  "message": "What time did the chest pain start, and what were you doing?"
}
```

**Output:**
```json
{
  "patient_response": "It started about 2 hours ago when I was sitting at my desk. The pain came on suddenly—like an elephant sitting on my chest. I also felt a bit sweaty.",
  "turn_count": 1
}
```

**Behavior:**
- Patient response is deterministic given the session history
- MedGemma references the full conversation history from `InMemoryChatMessageHistory`
- Response is appended to history and persisted

---

### Scoring & Debrief

#### `POST /api/simulation/session/{session_id}/submit`
Resident submits history, exam, investigations, diagnosis, and management plan for scoring.

**Input:**
```json
{
  "history": {
    "hpi": "52-year-old gentleman presenting with acute chest pain...",
    "ros": "Chest pain, diaphoresis, SOB. No nausea, no abdominal pain.",
    "pmh": "Hypertension, type 2 diabetes"
  },
  "exam": {
    "vitals": "BP 145/92, HR 110, RR 18, Temp 37°C",
    "findings": "Regular rhythm, S1S2 normal, lungs clear"
  },
  "investigations": [
    {"test": "ECG", "result": "ST elevation in leads II, III, aVF"},
    {"test": "Troponin", "result": "3.5 ng/mL (>0.04 normal)"},
    {"test": "CXR", "result": "Mild pulmonary edema"}
  ],
  "differential": [
    "Acute MI (inferior wall STEMI)",
    "Pulmonary embolism",
    "Aortic dissection"
  ],
  "diagnosis": "Acute MI, inferior wall",
  "management": "PCI, dual antiplatelet therapy, beta-blocker, ACE inhibitor"
}
```

**Output:**
```json
{
  "session_id": "sim_abc123",
  "submitted_at": "2025-03-22T11:00:00Z",
  "scores": {
    "history": 92,
    "examination": 88,
    "investigations": 85,
    "diagnosis": 95,
    "management": 90,
    "overall": 90
  },
  "debrief": {
    "summary": "Excellent case management with strong diagnostic acuity. Minor opportunities for cost optimization.",
    "history_feedback": "Thorough HPI and ROS capture. Consider asking about radiation to left arm next time.",
    "exam_feedback": "Good vital sign documentation. Remember to check for peripheral edema in heart failure presentations.",
    "investigation_feedback": "Appropriate troponin and ECG ordering. D-dimer was not ordered—consider adding for PE risk stratification.",
    "diagnosis_feedback": "Correct final diagnosis with strong differential generation.",
    "management_feedback": "Guideline-concordant reperfusion therapy and medical management. Consider aspiration thrombectomy given timing.",
    "missed_opportunities": [
      "VTE prophylaxis not documented",
      "Lipid panel not ordered (baseline for statin dosing)"
    ],
    "cost_analysis": "Total investigations: $1,240. Appropriate use—no unnecessary tests.",
    "coaching_points": [
      "In acute MI, always document VTE prophylaxis plan",
      "Order baseline labs early (lipid, renal function) to guide medications"
    ]
  }
}
```

#### `GET /api/simulation/session/{session_id}/debrief`
Retrieve the full debrief after submission (if already scored).

---

### Debrief & Scoring Dashboard

After submission, the resident receives a comprehensive debrief with:
- **Overall Score**: Percentage-based performance (0–100%)
- **Five-Domain Breakdown**: Detailed scoring across history, examination, investigations, diagnosis, and management
- **Ground Truth**: Correct diagnosis confirmed
- **Model Management Plan**: Expected care pathway with actionable steps
- **Tutor Feedback**: Narrative assessment with specific coaching points and evaluation criteria

<img src="write-up images/Simulation debrief.png" width="100%" alt="Simulation — debrief dashboard with five-domain scoring and tutor feedback"/>

**Debrief Components:**
- **Performance Metrics**: Visual breakdown showing competency in each domain
- **Correct Diagnosis**: Verified against case ground truth
- **Model Management Plan**: Guideline-concordant care pathway with checkmarks for adherence
- **Tutor Feedback**: AI-generated coaching addressing history-taking technique, physical exam completeness, investigation appropriateness, diagnostic reasoning, and management planning
- **Resident Performance Analysis**: Structured evaluation highlighting strengths and improvement areas

---

## Data Model

### Session (In-Memory + Optional Persistence)

```python
@dataclass
class SimulationSession:
    session_id: str              # UUID
    resident_id: str
    case_id: str
    hospital_id: str
    created_at: datetime
    status: str                  # "in_progress" | "submitted" | "scored"
    turn_count: int
    message_history: List[dict]  # LangChain BaseMessage serialized
    submission: Optional[dict]   # Diagnosis + management submitted
    scoring_result: Optional[dict]  # Scores + debrief
```

### Message History Schema

Stored in `InMemoryChatMessageHistory` keyed by `session_id`:

```python
[
    HumanMessage(content="What time did it start?"),
    AIMessage(content="The pain started 2 hours ago..."),
    HumanMessage(content="Any radiation?"),
    AIMessage(content="Yes, into my left arm and jaw...")
]
```

---

## Simulation Lifecycle

```
1. CREATE SESSION
   → Load case, initialize empty message history, set patient context

2. QUESTIONING LOOP
   → Resident asks question / proposes finding
   → Message appended to history
   → MedGemma generates response (with full history context)
   → Response appended, persisted in InMemoryChatMessageHistory
   → [Repeat until resident ready]

3. SUBMIT
   → Resident submits H&P, investigations, Dx, plan
   → Scorer evaluates against case ground truth
   → Debrief generator creates narrative feedback

4. RELEASE HISTORY
   → Message history automatically cleared from in-memory store
   → Session archived (optional Firestore/DB persistence)
   → Resident can start next case
```

---

## Quick Start

### Installation

```bash
# Clone and setup
git clone <repo>
cd medgemma-assistant
uv sync

# In simulated mode (no GPU):
SIMULATED_MODE=true uv run python main.py

# Full mode with MedGemma:
uv run python main.py
```

### Running a Simulation

1. **Open UI**: Navigate to `http://localhost:8000/simulation`
2. **Select Case**: Choose from available clinical scenarios
3. **Ask Questions**: Type history questions or exam findings
4. **Submit**: Enter your diagnosis, differential, and management plan
5. **View Debrief**: Review feedback and scores

### API Example (cURL)

```bash
# Create session
curl -X POST http://localhost:8000/api/simulation/session/create \
  -H "Content-Type: application/json" \
  -d '{
    "case_id": "case_mi_001",
    "resident_id": "R001",
    "hospital_id": "general"
  }'

# Ask patient a question
curl -X POST http://localhost:8000/api/simulation/session/sim_abc123/ask \
  -H "Content-Type: application/json" \
  -d '{
    "message": "When did the pain start?"
  }'

# Submit assessment
curl -X POST http://localhost:8000/api/simulation/session/sim_abc123/submit \
  -H "Content-Type: application/json" \
  -d '{
    "history": {...},
    "exam": {...},
    "investigations": [...],
    "diagnosis": "Acute MI",
    "management": "PCI, dual antiplatelet, beta-blocker"
  }'
```

---

## Configuration & Environment

| Variable | Purpose | Default |
|----------|---------|---------|
| `SIMULATED_MODE` | Run without GPU | `false` |
| `SIMULATION_MAX_TURNS` | Max questions per session | `20` |
| `SIMULATION_TIMEOUT` | Session expiry (minutes) | `60` |
| `CASE_REPOSITORY_PATH` | Seed cases location | `src/simulation/cases/` |

---

## Project Structure

```
src/simulation/
├── chat_chain.py              # LangChain RunnableWithMessageHistory
├── scorer.py                  # Five-domain scoring engine
├── debrief.py                 # Narrative feedback generator
├── cases/
│   ├── case_mi_001.json       # Acute MI case
│   ├── case_sepsis_001.json   # Sepsis case
│   └── [more cases]
├── templates/
│   ├── simulation_ui.html     # Resident interface
│   └── debrief.html           # Scoring & feedback display
└── tests/
    ├── test_chat_chain.py
    ├── test_scorer.py
    └── test_debrief.py
```

---

## Safety & Compliance

1. **Audit Trail**: Every interaction logged with timestamp, resident ID, response
2. **Session Isolation**: No cross-session contamination; history cleared post-scoring
3. **Learning Outcome Tracking**: Scorecards persisted for faculty dashboards
4. **Disclaimers**: Clear messaging that simulation is for *education only* — not clinical decision support

---

## Limitations & Future Work

### Current Limitations
- **Simplified Scoring**: Pattern-matching-based; no multi-hypothesis reasoning yet
- **Fixed Case Library**: ~10 curated cases; would benefit from generative case expansion
- **No Image Simulation**: Standardized patients don't present with realistic medical images

### Roadmap
1. **Expand Case Library**: Use GPT-4 to generate diverse edge-case scenarios
2. **Multimodal Integration**: Add simulated imaging findings and physical exam videos
3. **Peer Comparison**: Anonymized scorecard comparison across resident cohorts
4. **Adaptive Difficulty**: Escalate case complexity based on resident performance
5. **Real-time Faculty Monitoring**: Live dashboard for simulation proctors

---

## Contributing

### Adding a New Case

1. Create `src/simulation/cases/case_<specialty>_<number>.json`:
```json
{
  "case_id": "case_acute_coronary_001",
  "title": "52M with Acute Chest Pain",
  "chief_complaint": "Chest pain × 2 hours",
  "demographics": {
    "age": 52,
    "gender": "M",
    "comorbidities": ["hypertension", "type-2-diabetes"]
  },
  "hpi_template": "Started 2 hours ago at rest, ongoing...",
  "baseline_vitals": {"BP": "145/92", "HR": 110, "RR": 18, "Temp": 37.0},
  "ground_truth": {
    "diagnosis": "Acute inferior wall STEMI",
    "expected_findings": [...]
  },
  "management_roadmap": [...]
}
```

2. Register in `/api/simulation/cases`
3. Add unit tests in `tests/` directory

---

## Authors & Attribution

Built by the MedGemma Clinical Assistant team for the [Google MedGemma Impact Challenge](https://www.kaggle.com/competitions/med-gemma-impact-challenge).

**License**: CC BY 4.0 (per competition requirements)

---

## Support

- **Documentation**: See `AGENTS.md` for detailed tool references
- **Issues**: Report bugs in the main project repository
- **Questions**: Refer to README.md for architectural context
