# Phase 3 Implementation Summary: Re-Deliberation & Automatic Monitoring

## Status: ✅ COMPLETE

All Phase 3 re-deliberation and automatic monitoring infrastructure is complete and ready for workflow integration.

---

## What Was Implemented

### 1. **Re-Deliberation Orchestrator** (`src/council/re_deliberation_orchestrator.py`)

**Core Class: `RedeliberationOrchestrator`**

**Key Methods:**
- ✅ `should_trigger_redlib()` - Evaluate if a trigger warrants re-deliberation
- ✅ `get_redlib_reason()` - Generate human-readable reason for re-deliberation
- ✅ `process_triggers_for_workflow()` - Process pending triggers and initiate re-deliberations
- ✅ `start_background_monitoring()` - Start async monitoring for a workflow
- ✅ `stop_background_monitoring()` - Stop monitoring gracefully
- ✅ `get_monitoring_status()` - Query current monitoring state and pending triggers

**Orchestrator Features:**
- Evaluates all 4 trigger types (observations, physician requests, low confidence, consensus shifts)
- Automatically initiates re-deliberation branches when conditions met
- Tracks active monitoring tasks per workflow
- Integrates with WorkflowMonitor, WorkflowEngine, and WorkflowStore
- Records re-deliberation reasons in decision trail

### 2. **Re-Deliberation Trigger Logic**

**Automatic Re-Deliberation Triggers:**

1. **NewObservationTrigger** - Always triggers on:
   - Lab results (CBC, chemistry, troponin, etc.)
   - Imaging reports (CT, MRI, X-ray, Echo)
   - Vital signs updates
   - Progress notes

2. **PhysicianRequestTrigger** - Always triggers on:
   - Manual physician requests via API
   - Any reason: new evidence, uncertainty, reassessment needed

3. **LowConfidenceTrigger** - Triggers when:
   - Current consensus confidence drops below threshold
   - Default threshold: 50% confidence
   - Configurable per hospital/workflow

4. **ConsensusShiftTrigger** - Triggers when:
   - Diagnosis changes between deliberations
   - Case-insensitive matching
   - Captures diagnostic evolution

### 3. **Background Monitoring (Async)**

**Monitoring Capabilities:**
- Periodic polling of workflow for pending triggers
- Configurable check interval (default 5 minutes)
- Graceful start/stop of background tasks
- Built-in support for EHR service polling

**Monitoring Workflow:**
```
1. Background task starts
2. Sleeps for check_interval
3. Poll EHR service (if provided)
4. Check for pending triggers in WorkflowMonitor
5. Evaluate each trigger
6. If warranted: initiate re-deliberation
7. Clear processed triggers
8. Repeat
```

### 4. **Monitoring Status Queries**

**Status API:**
```python
status = orchestrator.get_monitoring_status(workflow_id)
# {
#   "workflow_id": "WORKFLOW-P001-...",
#   "is_monitored": True,
#   "pending_trigger_count": 2,
#   "pending_triggers": [
#     {
#       "trigger_id": "new_obs_lab_result_P001",
#       "type": "NewObservationTrigger",
#       "triggered_at": "2026-03-25T14:30:00",
#       "evidence": {"lab": "troponin", "value": "2.5"}
#     },
#     ...
#   ]
# }
```

### 5. **Re-Deliberation Branching**

**Automatic Workflow Branching:**

When re-deliberation triggered:
1. Fetch latest checkpoint from current workflow
2. Create new branch with new workflow_id (e.g., `WORKFLOW-P001-uuid-re_deliberate_v1`)
3. Merge new evidence into state
4. Clear Round 2 results to force re-evaluation
5. Execute graph with hooks from WorkflowEngine
6. Save checkpoints after each node
7. Record decision trail events

**Original workflow preserved for audit trail.**

### 6. **Integration with Phase 1-2 Components**

**Integration Points:**
- Uses `WorkflowMonitor` for trigger management
- Uses `WorkflowEngine` for workflow execution and checkpointing
- Uses `WorkflowStore` for state persistence and decision trail logging
- Uses `DecisionTrailRecorder` for audit events
- Compatible with specialist routing and consensus merging

---

## Files Created

### New Files

**src/council/re_deliberation_orchestrator.py** (340+ lines)
- `RedeliberationOrchestrator` class with full re-deliberation infrastructure
- Singleton factory function: `get_redlib_orchestrator()`
- Integration with all monitoring trigger types
- Background monitoring task management
- Logging throughout for observability

**test_phase3_integration.py** (280+ lines)
- Comprehensive test suite for Phase 3
- Tests: imports, trigger evaluation, monitoring status, shift detection, initialization
- 5 test modules covering all Phase 3 functionality

---

## Architecture Decisions

### 1. Trigger Evaluation Strategy

**Decision Tree:**
```
Trigger received
  ├─ NewObservationTrigger → Always trigger
  ├─ PhysicianRequestTrigger → Always trigger
  ├─ LowConfidenceTrigger → Compare current confidence to threshold
  ├─ ConsensusShiftTrigger → Compare diagnoses (case-insensitive)
  └─ Other → Skip
```

**Rationale:** New evidence and explicit physician requests always warrant re-deliberation. Automated triggers (confidence, shift) require explicit threshold checks.

### 2. Background Monitoring

**Async Pattern:**
- Each workflow can have one background monitoring task
- Long-running async loop with configurable check interval
- Non-blocking: doesn't interfere with graph execution
- Graceful cancellation support

**Rationale:** Polling-based monitoring scales better than webhook-based in MVP, easier to test and debug.

### 3. Re-Deliberation Branching

**Same Workflow ID Strategy:**
- Original: `WORKFLOW-P001-uuid`
- Re-deliberation: `WORKFLOW-P001-uuid-re_deliberate_v1`
- Next re-deliberation: `WORKFLOW-P001-uuid-re_deliberate_v2`

**Rationale:** Maintains unified case history; easier for physicians to track full diagnostic evolution.

### 4. Monitoring State Management

**Per-Workflow Monitoring:**
- Triggers stored in `WorkflowMonitor.triggers[workflow_id]`
- Active monitoring tasks tracked in `active_monitors[workflow_id]`
- Clear separation between monitoring state and workflow state

**Rationale:** Supports multiple simultaneous workflows; each can have different monitoring configuration.

---

## Testing & Validation

✅ **Module Syntax Verification:**
- `re_deliberation_orchestrator.py` - ✓

✅ **Test Coverage:**
- Phase 3 integration tests cover:
  1. Module imports
  2. All 4 trigger type evaluations
  3. Monitoring status queries
  4. Consensus shift detection
  5. Orchestrator initialization and singleton pattern

---

## Integration Points

### 1. With WorkflowEngine

```python
# Orchestrator uses engine to:
new_workflow_id, resumed_state = engine.initiate_re_deliberation(
    workflow_id=original_workflow_id,
    new_case_info=trigger.new_evidence,  # Injected from trigger
    triggered_by_escalation=False,
)

# Then executes with checkpoints:
result = await engine.execute_with_checkpoints(
    graph_invoke_fn=graph.invoke,
    initial_state=resumed_state,
)
```

### 2. With WorkflowMonitor

```python
# Orchestrator polls monitor for triggers:
triggers = monitor.get_pending_triggers(workflow_id)

# Clears after processing:
monitor.clear_triggers(workflow_id)

# Registers new observations:
monitor.register_new_observation(...)
```

### 3. With DecisionTrailRecorder

```python
# Records re-deliberation reasons:
recorder = get_decision_trail_recorder(new_workflow_id)
recorder.record_new_observation(
    observation_type=type(trigger).__name__,
    observation_data=trigger.new_evidence,
)
```

### 4. With Specialist Router

```
# Re-deliberation executes full graph including:
  • Main consensus calculation (R1)
  • Specialist routing (if low confidence)
  • Specialist invocations (parallel)
  • Specialist consensus merging
  • PubMed search
  • Round 2 (iterative mode)
```

---

## Key Features Implemented

1. **Automatic Re-Deliberation**: Triggers initiate new deliberation branches automatically
2. **Evidence Injection**: New observations merged into workflow state
3. **Checkpoint Preservation**: Original workflow preserved for audit
4. **Background Monitoring**: Async polling with configurable intervals
5. **Status Queries**: Real-time view of pending triggers and monitoring state
6. **Audit Trail**: All re-deliberations logged with reasoning
7. **Graceful Shutdown**: Background tasks can be stopped cleanly
8. **Singleton Pattern**: One orchestrator manages all workflows

---

## Known Limitations (Phase 3 MVP)

1. No persistent monitoring configuration (in-memory only)
2. Single check per polling cycle (could batch multiple triggers)
3. No exponential backoff on monitoring failures
4. EHR polling is placeholder (infrastructure-ready)
5. No webhook support yet (infrastructure-ready)
6. No rate limiting on re-deliberation branching
7. Monitoring not integrated into API routes yet (Phase 4)

---

## What's Next: Phase 4+

### Phase 4: Decision Trail & Evidence Tracking
- Full decision trail search/filtering
- Evidence source weighting and bias mitigation
- LangChain PubMed cross-validation
- Physician dashboard with timeline visualization

### Phase 5: Physician Override & Human-in-the-Loop
- Physician intervention handling
- Override reason tracking
- Feedback loop for specialist routing tuning
- Expert review interface for specialist divergence

---

## API Integration Ready (Phase 4)

**Routes to be added to main.py:**
- `POST /api/council/workflow/{workflow_id}/start-monitoring` - Start background monitoring
- `POST /api/council/workflow/{workflow_id}/stop-monitoring` - Stop monitoring
- `GET /api/council/workflow/{workflow_id}/monitoring-status` - Get trigger status
- `POST /api/council/workflow/{workflow_id}/manually-trigger-redlib` - Trigger explicitly
- `POST /api/council/workflow/{workflow_id}/register-observation` - Register new observation

---

## Summary

✅ **Phase 3 Complete**: Re-deliberation orchestrator fully implemented with automatic monitoring infrastructure.

**Core capabilities:**
- Automatic trigger evaluation and re-deliberation initiation
- Background monitoring with async polling
- Re-deliberation branching with evidence injection
- Full decision trail logging
- Graceful monitoring lifecycle management

**Integration status:**
- ✓ Connected to WorkflowMonitor for trigger detection
- ✓ Connected to WorkflowEngine for re-deliberation execution
- ✓ Connected to WorkflowStore for state persistence
- ✓ Connected to DecisionTrail for audit logging
- ✓ Specialist routing and consensus merging preserved
- ✓ Checkpoint preservation for audit
- ✓ API routes ready for Phase 4

The system now supports fully automated re-evaluation workflows triggered by new evidence, low confidence watchdog, or physician requests. All re-deliberations are tracked, audited, and branched from the original workflow for complete diagnostic history.
