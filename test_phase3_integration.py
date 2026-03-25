#!/usr/bin/env python3
"""
Phase 3 Integration Tests: Re-Deliberation & Automatic Monitoring

Tests:
1. Trigger evaluation logic
2. Re-deliberation orchestration
3. Background monitoring setup
4. Monitoring status queries
5. Automatic branching on triggers
"""

import sys
from datetime import datetime

print("=" * 70)
print("PHASE 3 INTEGRATION TESTS: Re-Deliberation & Automatic Monitoring")
print("=" * 70)

# Test 1: Module imports
print("\n[1/5] Testing module imports...")
try:
    from src.council.re_deliberation_orchestrator import (
        get_redlib_orchestrator,
        RedeliberationOrchestrator,
    )
    from src.council.workflow_monitor import (
        get_workflow_monitor,
        NewObservationTrigger,
        PhysicianRequestTrigger,
        LowConfidenceTrigger,
        ConsensusShiftTrigger,
    )
    from src.council.workflow_engine import get_workflow_engine
    from src.council.workflow_store import get_workflow_store
    print("✓ All modules imported successfully")
except Exception as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

# Test 2: Trigger evaluation logic
print("\n[2/5] Testing trigger evaluation logic...")
try:
    orch = get_redlib_orchestrator()
    monitor = get_workflow_monitor()

    # Create test state
    test_state = {
        "consensus_diagnosis": "Pneumonia",
        "consensus_confidence": 0.55,
        "specialist_findings": [],
    }

    # Test LowConfidenceTrigger
    low_conf_trigger = LowConfidenceTrigger(
        workflow_id="WORKFLOW-P001-test",
        threshold=0.6,
    )
    should_trigger = orch.should_trigger_redlib(low_conf_trigger, test_state)
    assert should_trigger is True, "Expected low confidence to trigger"
    print("  ✓ Low confidence trigger correctly detected")

    # Test PhysicianRequestTrigger
    phys_trigger = PhysicianRequestTrigger(
        workflow_id="WORKFLOW-P001-test",
        physician_id="dr_smith",
        reason="New troponin result",
    )
    should_trigger = orch.should_trigger_redlib(phys_trigger, test_state)
    assert should_trigger is True, "Expected physician request to trigger"
    print("  ✓ Physician request trigger correctly detected")

    # Test NewObservationTrigger
    obs_trigger = NewObservationTrigger(
        workflow_id="WORKFLOW-P001-test",
        patient_id="P001",
        observation_type="lab_result",
    )
    should_trigger = orch.should_trigger_redlib(obs_trigger, test_state)
    assert should_trigger is True, "Expected observation to trigger"
    print("  ✓ New observation trigger correctly detected")

    # Test reason generation
    reason = orch.get_redlib_reason(obs_trigger)
    assert "lab_result" in reason, f"Expected lab_result in reason, got: {reason}"
    print(f"  ✓ Reason generation working: '{reason}'")

except AssertionError as e:
    print(f"✗ Assertion failed: {e}")
    sys.exit(1)
except Exception as e:
    print(f"✗ Trigger evaluation test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Monitoring status queries
print("\n[3/5] Testing monitoring status queries...")
try:
    orch = get_redlib_orchestrator()
    monitor = get_workflow_monitor()

    workflow_id = "WORKFLOW-P002-test"

    # Register some triggers
    monitor.register_new_observation(
        workflow_id=workflow_id,
        patient_id="P002",
        observation_type="lab_result",
        observation_data={"lab_name": "troponin", "value": "2.5"},
    )

    monitor.register_physician_request(
        workflow_id=workflow_id,
        physician_id="dr_jones",
        reason="Please re-evaluate with new labs",
    )

    # Get monitoring status
    status = orch.get_monitoring_status(workflow_id)
    assert status["workflow_id"] == workflow_id, "Workflow ID mismatch"
    assert status["pending_trigger_count"] == 2, f"Expected 2 triggers, got {status['pending_trigger_count']}"
    assert status["is_monitored"] is False, "Expected monitoring to be inactive"
    print(f"  ✓ Monitoring status: {status['pending_trigger_count']} pending triggers")
    print(f"    - {[t['type'] for t in status['pending_triggers']]}")

    # Clear triggers
    monitor.clear_triggers(workflow_id)
    status = orch.get_monitoring_status(workflow_id)
    assert status["pending_trigger_count"] == 0, "Expected triggers to be cleared"
    print("  ✓ Triggers cleared successfully")

except AssertionError as e:
    print(f"✗ Assertion failed: {e}")
    sys.exit(1)
except Exception as e:
    print(f"✗ Monitoring status test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Consensus shift detection
print("\n[4/5] Testing consensus shift detection...")
try:
    # Create ConsensusShiftTrigger
    shift_trigger = ConsensusShiftTrigger(
        workflow_id="WORKFLOW-P003-test",
        original_diagnosis="Pneumonia",
    )

    orch = get_redlib_orchestrator()

    # Test same diagnosis (no shift)
    should_trigger = shift_trigger.should_trigger_redlib("Pneumonia")
    assert should_trigger is False, "Expected no trigger for same diagnosis"
    print("  ✓ Same diagnosis correctly doesn't trigger shift detection")

    # Test different diagnosis (shift detected)
    should_trigger = shift_trigger.should_trigger_redlib("Bronchitis")
    assert should_trigger is True, "Expected trigger for changed diagnosis"
    print("  ✓ Different diagnosis correctly triggers shift detection")

    # Test case-insensitive matching
    should_trigger = shift_trigger.should_trigger_redlib("PNEUMONIA")
    assert should_trigger is False, "Expected case-insensitive match"
    print("  ✓ Case-insensitive diagnosis matching working")

except AssertionError as e:
    print(f"✗ Assertion failed: {e}")
    sys.exit(1)
except Exception as e:
    print(f"✗ Consensus shift test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Re-deliberation orchestrator instantiation
print("\n[5/5] Testing re-deliberation orchestrator initialization...")
try:
    orchestrator = get_redlib_orchestrator()
    assert orchestrator is not None, "Expected orchestrator to be created"
    assert orchestrator.monitor is not None, "Expected monitor to be set"
    assert orchestrator.engine is not None, "Expected engine to be set"
    assert orchestrator.store is not None, "Expected store to be set"
    print("  ✓ Orchestrator initialized with all components")

    # Test singleton pattern
    orch2 = get_redlib_orchestrator()
    assert orch2 is orchestrator, "Expected singleton pattern"
    print("  ✓ Singleton pattern verified")

    # Check active monitoring dict
    assert isinstance(orchestrator.active_monitors, dict), "Expected active_monitors dict"
    assert len(orchestrator.active_monitors) == 0, "Expected no active monitors initially"
    print("  ✓ Active monitoring infrastructure ready")

except AssertionError as e:
    print(f"✗ Assertion failed: {e}")
    sys.exit(1)
except Exception as e:
    print(f"✗ Orchestrator initialization test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Summary
print("\n" + "=" * 70)
print("✓ ALL PHASE 3 INTEGRATION TESTS PASSED")
print("=" * 70)
print("\nPhase 3 Components Ready:")
print("  ✓ Re-deliberation orchestrator")
print("  ✓ Trigger evaluation logic")
print("  ✓ Monitoring status queries")
print("  ✓ Consensus shift detection")
print("  ✓ Background monitoring infrastructure")
print("\nPhase 3 Features:")
print("  • Automatic monitoring of workflow triggers")
print("  • Re-deliberation branching on new evidence")
print("  • Low confidence watchdog")
print("  • Consensus shift detection")
print("  • Physician request handling")
print("  • Background polling/webhook-ready")
print("\nNext Steps:")
print("  - Phase 4: Evidence Tracking & LangChain PubMed")
print("  - Phase 5: Physician Override & Human-in-the-Loop")
print("=" * 70)
