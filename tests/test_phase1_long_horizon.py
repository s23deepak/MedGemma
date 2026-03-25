"""
Phase 1 Integration Tests: Long-Horizon Diagnostic Council Workflow

Tests checkpoint functionality, state persistence, escalation rules, and API integration.
"""

import pytest
import json
from datetime import datetime
from src.council.long_horizon_state import (
    LongHorizonCouncilState,
    CheckpointEntry,
    DecisionTrailEvent,
    EscalationFlag,
    SpecialistFinding,
    extend_council_state_to_long_horizon,
    serialize_long_horizon_state,
    deserialize_long_horizon_state,
)
from src.council.workflow_store import get_workflow_store, WorkflowStore
from src.council.workflow_engine import get_workflow_engine, WorkflowEngine
from src.council.escalation_rules import get_escalation_service, EscalationRulesEngine


class TestLongHorizonState:
    """Test extended state schema and serialization."""

    def test_extend_council_state(self):
        """Test extending base CouncilState with long-horizon fields."""
        base_state = {
            "case_info": {"symptoms": ["chest pain"]},
            "num_rollouts": 5,
            "mode": "iterative",
            "raw_note": "",
            "retrieved_context": "",
            "opinions": [],
            "consensus_diagnosis": None,
            "consensus_strength": "weak",
            "consensus_confidence": 0.0,
            "discussion_summary": "",
            "minority_challenge": "",
            "pubmed_insights": {},
            "rare_diagnoses": [],
            "r2_opinions": [],
            "r2_consensus_diagnosis": None,
            "r2_consensus_strength": "weak",
            "r2_consensus_confidence": 0.0,
            "r2_discussion_summary": "",
        }

        extended = extend_council_state_to_long_horizon(
            council_state=base_state,
            workflow_id="WORKFLOW-P001-12345678",
            created_by="dr_smith",
            branch_id=None,
        )

        # Verify new fields are present
        assert extended["workflow_id"] == "WORKFLOW-P001-12345678"
        assert extended["branch_id"] is None
        assert extended["created_by"] == "dr_smith"
        assert isinstance(extended["checkpoint_stack"], list)
        assert isinstance(extended["decision_trail"], list)
        assert isinstance(extended["escalation_flags"], list)
        assert isinstance(extended["specialist_findings"], dict)
        assert extended["workflow_start_time"] is not None

    def test_serialize_deserialize(self):
        """Test round-trip serialization of long-horizon state."""
        base_state = {
            "case_info": {"symptoms": ["chest pain"]},
            "num_rollouts": 5,
            "mode": "iterative",
            "raw_note": "",
            "retrieved_context": "",
            "opinions": [],
            "consensus_diagnosis": "Acute Coronary Syndrome",
            "consensus_strength": "moderate",
            "consensus_confidence": 0.75,
            "discussion_summary": "Council agrees on ACS",
            "minority_challenge": "",
            "pubmed_insights": {},
            "rare_diagnoses": [],
            "r2_opinions": [],
            "r2_consensus_diagnosis": None,
            "r2_consensus_strength": "weak",
            "r2_consensus_confidence": 0.0,
            "r2_discussion_summary": "",
        }

        extended = extend_council_state_to_long_horizon(
            council_state=base_state,
            workflow_id="WORKFLOW-P001-12345678",
            created_by="dr_smith",
        )

        # Serialize
        serialized = serialize_long_horizon_state(extended)
        assert isinstance(serialized, dict)
        assert serialized["workflow_id"] == "WORKFLOW-P001-12345678"
        assert isinstance(serialized["workflow_start_time"], str)  # Should be ISO string

        # Deserialize
        deserialized = deserialize_long_horizon_state(serialized)
        assert deserialized["workflow_id"] == "WORKFLOW-P001-12345678"
        assert deserialized["consensus_diagnosis"] == "Acute Coronary Syndrome"


class TestWorkflowStore:
    """Test Firestore persistence layer."""

    def test_workflow_create(self):
        """Test creating a workflow in the store."""
        store = get_workflow_store()
        workflow_id = "WORKFLOW-TEST-12345678"

        metadata = store.create_workflow(
            workflow_id=workflow_id,
            patient_id="P001",
            created_by="dr_smith",
            branch_id="main",
        )

        assert metadata["workflow_id"] == workflow_id
        assert metadata["patient_id"] == "P001"
        assert metadata["status"] == "active"

    def test_checkpoint_save_retrieve(self):
        """Test saving and retrieving checkpoints."""
        store = get_workflow_store()
        workflow_id = "WORKFLOW-CHECKPOINT-12345678"

        store.create_workflow(
            workflow_id=workflow_id,
            patient_id="P002",
            created_by="dr_smith",
        )

        # Create a test state
        base_state = {
            "case_info": {"symptoms": ["fever", "cough"]},
            "num_rollouts": 5,
            "mode": "standard",
            "raw_note": "",
            "retrieved_context": "",
            "opinions": [],
            "consensus_diagnosis": "Community-Acquired Pneumonia",
            "consensus_strength": "strong",
            "consensus_confidence": 0.85,
            "discussion_summary": "Strong agreement on CAP",
            "minority_challenge": "",
            "pubmed_insights": {},
            "rare_diagnoses": [],
            "r2_opinions": [],
            "r2_consensus_diagnosis": None,
            "r2_consensus_strength": "weak",
            "r2_consensus_confidence": 0.0,
            "r2_discussion_summary": "",
        }

        state = extend_council_state_to_long_horizon(
            council_state=base_state,
            workflow_id=workflow_id,
            created_by="dr_smith",
        )

        # Save checkpoint
        checkpoint_id = store.save_checkpoint(
            workflow_id=workflow_id,
            node_name="calculate_consensus",
            state=state,
        )

        assert checkpoint_id is not None

        # Retrieve checkpoint
        result = store.get_latest_checkpoint(workflow_id)
        assert result is not None
        checkpoint_id_retrieved, retrieved_state = result
        assert retrieved_state["workflow_id"] == workflow_id
        assert retrieved_state["consensus_diagnosis"] == "Community-Acquired Pneumonia"

    def test_decision_trail_logging(self):
        """Test logging and retrieving decision trail events."""
        store = get_workflow_store()
        workflow_id = "WORKFLOW-TRAIL-12345678"

        store.create_workflow(
            workflow_id=workflow_id,
            patient_id="P003",
            created_by="dr_smith",
        )

        # Log decision event
        event = DecisionTrailEvent(
            event_id="event_001",
            timestamp=datetime.utcnow(),
            node_name="calculate_consensus",
            action="consensus_calculated",
            evidence_sources=["pubmed", "hpo"],
            reasoning="5/5 opinions agree on CAP",
            consensus_before="Undetermined",
            consensus_after="Community-Acquired Pneumonia",
        )

        event_id = store.log_decision_event(workflow_id, event)
        assert event_id == "event_001"

        # Retrieve trail
        trail = store.get_decision_trail(workflow_id)
        assert len(trail) > 0
        assert trail[0]["action"] == "consensus_calculated"


class TestEscalationRules:
    """Test escalation rules engine."""

    def test_weak_consensus_urgent(self):
        """Test weak consensus with urgent urgency triggers escalation."""
        engine = get_escalation_service()

        escalations = engine.evaluate_consensus(
            consensus_diagnosis="Undifferentiated chest pain",
            consensus_confidence=0.45,
            consensus_strength="weak",
            urgency="urgent",
            num_opinions=5,
            dissenting_count=2,
        )

        assert len(escalations) > 0
        assert escalations[0].severity == "critical"

    def test_split_consensus(self):
        """Test split consensus with multiple competing diagnoses."""
        engine = get_escalation_service()

        escalations = engine.evaluate_consensus(
            consensus_diagnosis="Acute Coronary Syndrome",
            consensus_confidence=0.40,
            consensus_strength="split",
            urgency="routine",
            num_opinions=5,
            dissenting_count=3,
        )

        # Should trigger split consensus rule
        assert any(e.rule_id == "split_consensus" for e in escalations)

    def test_no_escalation_on_strong_consensus(self):
        """Test strong consensus doesn't trigger escalations."""
        engine = get_escalation_service()

        escalations = engine.evaluate_consensus(
            consensus_diagnosis="Pneumonia",
            consensus_confidence=0.95,
            consensus_strength="strong",
            urgency="routine",
            num_opinions=5,
            dissenting_count=0,
        )

        assert len(escalations) == 0


class TestWorkflowEngine:
    """Test workflow orchestration engine."""

    def test_initiate_workflow(self):
        """Test initiating a new workflow."""
        engine = get_workflow_engine()

        council_state = {
            "case_info": {"symptoms": ["headache", "fever"]},
            "num_rollouts": 5,
            "mode": "iterative",
            "raw_note": "",
            "retrieved_context": "",
            "opinions": [],
            "consensus_diagnosis": None,
            "consensus_strength": "weak",
            "consensus_confidence": 0.0,
            "discussion_summary": "",
            "minority_challenge": "",
            "pubmed_insights": {},
            "rare_diagnoses": [],
            "r2_opinions": [],
            "r2_consensus_diagnosis": None,
            "r2_consensus_strength": "weak",
            "r2_consensus_confidence": 0.0,
            "r2_discussion_summary": "",
        }

        workflow_id = engine.initiate_workflow(
            council_state=council_state,
            patient_id="P004",
            created_by="dr_test",
        )

        assert workflow_id is not None
        assert "WORKFLOW" in workflow_id
        assert "P004" in workflow_id

    def test_redlib_branching(self):
        """Test creating a re-deliberation branch."""
        engine = get_workflow_engine()
        store = get_workflow_store()

        # First, create initial workflow
        council_state = {
            "case_info": {"symptoms": ["chest pain"]},
            "num_rollouts": 5,
            "mode": "iterative",
            "raw_note": "",
            "retrieved_context": "",
            "opinions": [],
            "consensus_diagnosis": "ACS",
            "consensus_strength": "moderate",
            "consensus_confidence": 0.65,
            "discussion_summary": "",
            "minority_challenge": "",
            "pubmed_insights": {},
            "rare_diagnoses": [],
            "r2_opinions": [],
            "r2_consensus_diagnosis": None,
            "r2_consensus_strength": "weak",
            "r2_consensus_confidence": 0.0,
            "r2_discussion_summary": "",
        }

        workflow_id = engine.initiate_workflow(
            council_state=council_state,
            patient_id="P005",
            created_by="dr_test",
        )

        # Save a checkpoint so we can re-deliberate
        state = extend_council_state_to_long_horizon(
            council_state=council_state,
            workflow_id=workflow_id,
            created_by="dr_test",
        )

        store.save_checkpoint(
            workflow_id=workflow_id,
            node_name="calculate_consensus",
            state=state,
        )

        # Now initiate re-deliberation with new labs
        new_workflow_id, resumed_state = engine.initiate_re_deliberation(
            workflow_id=workflow_id,
            new_case_info={"symptoms": ["chest pain", "elevated troponin"]},
        )

        assert new_workflow_id != workflow_id
        assert "re_deliberate" in new_workflow_id
        assert resumed_state["is_resuming"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
