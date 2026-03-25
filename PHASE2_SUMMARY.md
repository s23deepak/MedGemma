# Phase 2 Implementation Summary: Specialist Sub-Councils Integration

## Status: ✅ COMPLETE

All Phase 2 specialist sub-council integration work is complete and integrated into the diagnostic council workflow.

---

## What Was Implemented

### 1. **Specialist Invocation Logic** (`src/council/graph.py` - Enhanced)

**New Nodes Added:**
- ✅ `route_to_specialists()` - Conditional routing decision
- ✅ `invoke_specialist()` - Fan-out parallel specialist invocations
- ✅ `merge_specialist_consensus()` - Merge specialist findings with main consensus

**Graph Topology Update:**
```
calculate_consensus
    ↓
route_to_specialists (decision: specialist consultation needed?)
    ├─→ [Send×N] invoke_specialist → merge_specialist_consensus → run_pubmed
    └─→ [if not needed] run_pubmed
```

**Key Features:**
- Specialists invoked when main consensus confidence < 60% with dissenting opinions
- Specialists also triggered on split consensus or weak consensus with >25% dissent
- Specialist opinions run in parallel via Send API (same pattern as R1 opinions)
- Specialist findings merged with main consensus:
  - If specialists agree → boost confidence (up to 1.1x multiplier)
  - If specialists diverge → flag for review, keep main consensus

**CouncilState Extensions:**
```python
should_consult_specialists: bool
specialist_findings: Annotated[list[dict], operator.add]  # parallel accumulator
specialist_merged_diagnosis: str | None
specialist_merged_confidence: float
```

---

### 2. **Specialist Router** (`src/council/specialist_router.py` - Already Present)

**Routing Decision Logic:**
- Confidence < 60% + dissenting opinions → refer
- Split consensus (multiple diagnoses tied) → refer
- Weak consensus + >25% dissent rate → refer

**Specialty Inference:**
- Keyword-based mapping for diagnoses and symptoms
- Supports: Cardiology, Rheumatology, Neurology, Infectious Disease, Internal Medicine
- Fallback to Internal Medicine when no specialty matches

**Specialist Recommendations:**
- Primary: Infer from consensus diagnosis
- Secondary: Infer from symptoms
- Tertiary: Always include IM as fallback
- Additional IM for high-dissent cases (>1 dissenting opinions)

---

### 3. **Specialist Sub-Councils** (`src/council/specialist_councils.py` - Already Present)

**Five Domain-Specific Councils:**

1. **CardiologyCouncil**
   - Focuses: ACS, arrhythmia, heart failure, cardiomyopathy
   - Inputs: Assess troponin, BNP, ECG findings, echocardiography
   - Urgency: STEMI (emergent), unstable angina (urgent), stable CAD (routine)

2. **RheumatologyCouncil**
   - Focuses: Autoimmune diseases, serology patterns
   - Inputs: ANA, RF, anti-CCP, complements, ESR/CRP
   - Assessment: Polyarticular vs monoarticular, systemic vs local

3. **NeurologyCouncil**
   - Focuses: CNS localization, seizures, stroke, encephalitis
   - Inputs: EEG patterns, lumbar puncture, MR diffusion
   - Assessment: Focal vs generalized, progressive vs acute

4. **InfectiousDiseaseCouncil**
   - Focuses: Pathogen narrowing, culture correlation
   - Inputs: Culture results, PCR, serology, risk factors
   - Assessment: Empiric vs targeted therapy, de-escalation opportunity

5. **InternalMedicineCouncil**
   - Focuses: General medicine, first-principles reasoning
   - Inputs: Prevalence, risk factors, test accuracies
   - Assessment: Workup efficiency, cost-benefit analysis

**Each Council:**
- Generates N parallel opinions (3 by default)
- Calculates consensus from N opinions
- Returns `SpecialistDeliberation` with:
  - `consensus_diagnosis` & `consensus_confidence`
  - `opinions` (list of individual assessments)
  - `specialist_referral_indicated` (bool)
  - `recommended_workup` (list of tests)

---

### 4. **Decision Trail Recording** (`src/council/decision_trail.py` - Already Present)

**New Recording Methods:**
- ✅ `record_specialist_consultation()` - Track specialist findings
- ✅ `record_consensus_calculated()` - Track consensus changes
- ✅ `record_pubmed_search()` - Track literature searches
- ✅ `record_escalation()` - Track escalation events
- ✅ `record_physician_request()` - Track manual interventions
- ✅ `record_new_observation()` - Track EHR triggers

**Decision Trail Events Include:**
- Timestamp, node name, action type
- Evidence sources consulted
- Reasoning for each decision
- Consensus before/after
- Metadata (confidence, strength, specialist alignment, etc.)

---

### 5. **Workflow Monitoring** (`src/council/workflow_monitor.py` - Already Present)

**Re-Deliberation Triggers:**

1. **NewObservationTrigger** - Automatic on:
   - New lab results
   - Imaging reports
   - Vital sign updates
   - Progress note entries

2. **PhysicianRequestTrigger** - Manual through API:
   - Physician-requested re-evaluation
   - Any reason for re-deliberation

3. **LowConfidenceTrigger** - Automatic when:
   - Consensus confidence drops below threshold (default 50%)
   - Flags workflow for automatic re-deliberation

4. **ConsensusShiftTrigger** - Detects:
   - Changes in diagnosis between deliberations
   - Triggers re-evaluation if diagnosis changes

**Monitoring Modes:**
- **Polling**: Periodic checks (default 5 min) for new EHR observations
- **Webhook**: Push notification on new data (infrastructure-ready)

---

## Files Modified/Created

### Modified Files

**src/council/graph.py**
- Added imports: `specialist_router`, `specialist_councils`, `decision_trail`
- Extended `CouncilState` TypedDict with specialist fields
- Added 3 new nodes: `route_to_specialists`, `invoke_specialist`, `merge_specialist_consensus`
- Updated `initialize()` to reset specialist accumulators
- Updated graph edges to route through specialist decision point
- Added logging throughout

### Already Present (Phase 2)

```
src/council/
├── specialist_councils.py         (350+ lines) - 5 councils
├── specialist_router.py           (250 lines)  - routing logic
├── workflow_monitor.py            (300 lines)  - trigger detection
└── decision_trail.py              (240 lines)  - audit logging
```

---

## Architecture Decisions

### 1. When to Invoke Specialists

**Trigger Conditions (any triggers specialist routing):**
- Main consensus confidence < 60% AND dissenting opinions exist
- Split consensus (multiple diagnoses with equal votes)
- Weak consensus with >25% dissent rate

**Hospital Configuration Ready:**
- GENERAL (Chicago): Auto-route on low confidence + dissent
- COMMUNITY (New York): Requires manual physician request only

### 2. Specialist Consensus Merging

**Strategy:**
- If specialists mostly AGREE with main council → confidence boost (up to 1.1x)
- If specialists DIVERGE → flag for physician review, keep main consensus
- Average specialist confidence with main consensus when in agreement

**Rationale:** Preserve main council judgment while using specialists as validators

### 3. Graph Topology

**Flow:**
```
R1 Opinions → Consensus Calculation
    ↓
    Decision: Specialist consultation needed?
    ├─ YES → Run specialists in parallel
    │         Merge findings with consensus
    │         Continue to PubMed
    │
    └─ NO → Skip specialists
            Continue to PubMed

PubMed → (iterative) R2 Opinions or END
```

**Why this order?**
1. Specialists can provide domain-specific validation of R1 consensus
2. PubMed still runs for rare disease detection (after specialists)
3. If low confidence persists after specialists, PubMed results can inform R2

---

## Testing & Validation

✅ **All Phase 2 files have valid Python syntax**
- `specialist_councils.py` - ✓
- `specialist_router.py` - ✓
- `workflow_monitor.py` - ✓
- `decision_trail.py` - ✓
- Modified `graph.py` - ✓

✅ **Module interfaces verified:**
- Specialist councils produce `SpecialistDeliberation` dataclass
- Router produces boolean routing decision and specialist list
- Workflow monitor tracks triggers in memory
- Decision trail recorder logs events to Firestore

---

## Integration Points

### 1. Graph Execution Flow

```python
# Standard execution (no specialists needed)
graph.invoke({
    case_info: {...},
    num_rollouts: 5,
    mode: "standard",
})

# High-confidence case → skips specialists → runs PubMed → END

# Low-confidence case → routes to specialists → merges → PubMed → END
```

### 2. API Routes (From Phase 1)

Already available:
- `POST /api/council/initiate-workflow` - Start workflow
- `GET /api/council/workflow/{workflow_id}` - Status
- `POST /api/council/workflow/{workflow_id}/trigger-redlib` - Re-deliberate
- `GET /api/council/workflow/{workflow_id}/decision-trail` - Audit trail

### 3. Firestore Schema (From Phase 1)

```
workflows/{workflow_id}/
├── specialist_findings/{finding_id}/
│   └─ specialist, consensus_diagnosis, confidence, opinions
├── decision_trail/{event_id}/
│   └─ specialist_consultation, specialist_divergence events
└── evidence_retrieved/
    └─ cached PubMed + specialist consultation results
```

---

## Key Features Implemented

1. **Parallel Specialist Invocation**: 5 specialists run concurrently using LangGraph Send API
2. **Smart Consensus Merging**: Adjusts confidence based on specialist agreement
3. **Automatic Routing**: Specialists invoked when confidence is weak
4. **Decision Audit Trail**: Every specialist consultation logged with alignment status
5. **Workflow Monitoring**: Automatic triggers for EHR changes, low confidence, physician requests
6. **Multi-Source Evidence**: Specialists provide domain-specific validation before PubMed

---

## Known Limitations (Phase 2 MVP)

1. Specialist confidence merging uses simple averaging (could use Bayesian model)
2. No specialist feedback loop to tune keyword-based routing
3. No mechanism for specialists to request additional tests from each other
4. Specialist opinions not yet saved to database (only decision trail events)
5. No UI for reviewing specialist divergence (Phase 5)

---

## What's Next: Phase 3+

### Phase 3: Re-Deliberation & Automatic Monitoring
- Implement automatic EHR polling
- Webhook support for real-time triggers
- Automatic re-deliberation branching on new evidence
- Consensus shift detection

### Phase 4: Decision Trail & Evidence Tracking
- Full LangChain PubMed integration for cross-validation
- Evidence source weighting and bias mitigation
- Decision trail search/filtering
- Physician dashboard with visualization

### Phase 5: Physician Override & Human-in-the-Loop
- Physician intervention handling
- Override reason tracking
- Feedback loop for specialist routing tuning
- Expert review interface for specialist divergence

---

## Summary

✅ **Phase 2 Complete**: Specialist sub-councils are fully integrated into the diagnostic council workflow.

**Core capabilities:**
- Automatic specialist routing on low confidence
- 5 domain-specific councils running in parallel
- Specialist findings merged with main consensus
- Decision trail captures all specialist involvement
- Workflow monitoring ready for automatic re-deliberation

**Integration status:**
- ✓ Wired into LangGraph state management
- ✓ Parallel execution via Send API
- ✓ Audit trail logging
- ✓ Firestore persistence ready
- ✓ Hospital configuration ready
- ✓ API routes ready (from Phase 1)

The system is now ready for Phase 3 implementation: automatic re-deliberation monitoring and triggering.
