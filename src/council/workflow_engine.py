"""
LangGraph workflow engine with checkpointing, resumption, and persistence.

Wraps the diagnostic council graph to:
- Save checkpoints after each node execution
- Resume workflows from checkpoints on re-deliberation
- Track decision evolutions and escalations
- Support specialist sub-council branching
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional, Callable

from .workflow_store import get_workflow_store, WorkflowStore
from .long_horizon_state import (
    LongHorizonCouncilState,
    CheckpointEntry,
    DecisionTrailEvent,
    EscalationFlag,
    extend_council_state_to_long_horizon,
)
from .escalation_rules import get_escalation_service

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """
    Long-horizon workflow engine with checkpointing and resumption.

    Orchestrates:
    - State persistence and checkpointing
    - Workflow resumption from checkpoints
    - Decision trail tracking
    - Escalation handling
    - Specialist sub-council branching
    """

    def __init__(self, store: Optional[WorkflowStore] = None):
        """
        Initialize the workflow engine.

        Args:
            store: WorkflowStore instance (defaults to singleton)
        """
        self.store = store or get_workflow_store()
        self.escalation_service = get_escalation_service()

    def initiate_workflow(
        self,
        council_state: dict,
        patient_id: str,
        created_by: str,
    ) -> str:
        """
        Initiate a new long-horizon workflow.

        Args:
            council_state: Initial CouncilState dict
            patient_id: Patient identifier
            created_by: User/physician initiating the workflow

        Returns:
            Workflow ID
        """
        workflow_id = f"WORKFLOW-{patient_id}-{uuid.uuid4().hex[:8]}"

        # Extend state with long-horizon fields
        extended_state: LongHorizonCouncilState = extend_council_state_to_long_horizon(
            council_state=council_state,
            workflow_id=workflow_id,
            created_by=created_by,
            branch_id=None,  # Main branch
        )

        # Create workflow record in store
        self.store.create_workflow(
            workflow_id=workflow_id,
            patient_id=patient_id,
            created_by=created_by,
            branch_id="main",
        )

        logger.info(f"Initiated workflow {workflow_id} for patient {patient_id}")
        return workflow_id

    def initiate_re_deliberation(
        self,
        workflow_id: str,
        new_case_info: Optional[dict] = None,
        triggered_by_escalation: bool = False,
    ) -> tuple[str, LongHorizonCouncilState]:
        """
        Initiate a re-deliberation branch based on new evidence or physician request.

        Args:
            workflow_id: Original workflow ID
            new_case_info: Optional updated case info (new labs, imaging, vitals)
            triggered_by_escalation: True if triggered by escalation rule

        Returns:
            Tuple of (new_workflow_id, resumed_state)

        Raises:
            ValueError if workflow not found
        """
        # Fetch latest checkpoint from original workflow
        checkpoint_result = self.store.get_latest_checkpoint(workflow_id)
        if checkpoint_result is None:
            raise ValueError(f"No checkpoint found for workflow {workflow_id}")

        checkpoint_id, state = checkpoint_result

        # Create new branch ID
        branch_id = f"re_deliberate_v{self._count_re_deliberations(workflow_id) + 1}"
        new_workflow_id = f"{workflow_id}-{branch_id}"

        # Update state for re-deliberation
        updated_state = state.copy()
        updated_state["workflow_id"] = new_workflow_id
        updated_state["branch_id"] = branch_id
        updated_state["is_resuming"] = True

        # Merge new case info if provided
        if new_case_info:
            if "case_info" in updated_state:
                updated_state["case_info"].update(new_case_info)
            updated_state["workflow_last_update"] = datetime.utcnow()

        # Clear Round 2 results to force re-evaluation
        updated_state["r2_opinions"] = []
        updated_state["r2_consensus_diagnosis"] = None

        # Create workflow record for new branch
        original_workflow = self.store.get_workflow(workflow_id)
        if original_workflow:
            self.store.create_workflow(
                workflow_id=new_workflow_id,
                patient_id=original_workflow.get("patient_id", ""),
                created_by=original_workflow.get("created_by", ""),
                branch_id=branch_id,
            )

        logger.info(
            f"Initiated re-deliberation: {new_workflow_id} (branch: {branch_id}) "
            f"from checkpoint {checkpoint_id}"
        )

        return new_workflow_id, updated_state

    def create_node_checkpoint_hook(
        self,
        workflow_id: str,
    ) -> Callable[[str, LongHorizonCouncilState], None]:
        """
        Create a checkpoint hook function for use after node execution.

        Returns a closure that captures workflow_id and saves state to Firestore.

        Args:
            workflow_id: The workflow ID to checkpoint to

        Returns:
            Checkpoint function: (node_name, state) -> None
        """
        def checkpoint(node_name: str, state: LongHorizonCouncilState) -> None:
            try:
                # Add checkpoint entry to state accumulator
                checkpoint_entry = CheckpointEntry(
                    node_name=node_name,
                    timestamp=datetime.utcnow(),
                    state_snapshot=dict(state),
                    result={},  # Could capture node-specific results here
                )

                # Save to Firestore
                checkpoint_id = self.store.save_checkpoint(
                    workflow_id=workflow_id,
                    node_name=node_name,
                    state=state,
                )

                logger.debug(f"Checkpoint saved: {checkpoint_id} for node {node_name}")
            except Exception as e:
                logger.error(f"Failed to create checkpoint after node {node_name}: {e}")

        return checkpoint

    def create_decision_trail_hook(
        self,
        workflow_id: str,
    ) -> Callable[[str, str, str, list[str], str | None, str | None], None]:
        """
        Create a decision trail logging hook.

        Args:
            workflow_id: The workflow ID to log to

        Returns:
            Decision trail logging function
        """
        def log_decision(
            node_name: str,
            action: str,
            reasoning: str,
            evidence_sources: list[str],
            consensus_before: Optional[str] = None,
            consensus_after: Optional[str] = None,
        ) -> None:
            try:
                event_id = f"event_{uuid.uuid4().hex[:8]}"
                event = DecisionTrailEvent(
                    event_id=event_id,
                    timestamp=datetime.utcnow(),
                    node_name=node_name,
                    action=action,
                    evidence_sources=evidence_sources,
                    reasoning=reasoning,
                    consensus_before=consensus_before,
                    consensus_after=consensus_after,
                )
                self.store.log_decision_event(workflow_id, event)
            except Exception as e:
                logger.error(f"Failed to log decision event: {e}")

        return log_decision

    def create_escalation_hook(
        self,
        workflow_id: str,
    ) -> Callable[[str, str, str], None]:
        """
        Create an escalation flag logging hook.

        Args:
            workflow_id: The workflow ID to escalate

        Returns:
            Escalation function
        """
        def escalate(
            rule_id: str,
            severity: str,  # "critical" or "warning"
            reason: str,
        ) -> None:
            try:
                flag_id = f"escalation_{uuid.uuid4().hex[:8]}"

                # Get recommendation from escalation service
                recommendation = self.escalation_service.get_recommendation(rule_id, reason)

                # Update workflow status to escalated
                self.store.update_workflow_status(workflow_id, "escalated")

                logger.warning(
                    f"Escalation triggered for {workflow_id}: {rule_id} ({severity}) - {reason}"
                )
            except Exception as e:
                logger.error(f"Failed to handle escalation: {e}")

        return escalate

    def _count_re_deliberations(self, workflow_id: str) -> int:
        """Count how many re-deliberation branches exist for a workflow."""
        # Simple heuristic: count workflows in Firestore with matching pattern
        # In production, could maintain a counter in workflow metadata
        count = 0
        prefix = f"{workflow_id}-re_deliberate_v"
        try:
            docs = get_workflow_store().db.collection("workflows").stream()
            for doc in docs:
                if doc.id.startswith(prefix):
                    count += 1
        except Exception:
            pass
        return count

    async def execute_with_checkpoints(
        self,
        graph_invoke_fn: Callable[[LongHorizonCouncilState], dict],
        initial_state: LongHorizonCouncilState,
        checkpoint_after_nodes: Optional[list[str]] = None,
    ) -> dict:
        """
        Execute the workflow graph with checkpoint hooks after specified nodes.

        Args:
            graph_invoke_fn: Function that invokes the LangGraph (e.g., graph.invoke())
            initial_state: Initial workflow state
            checkpoint_after_nodes: List of node names after which to checkpoint
                                   (if None, checkpoints after major nodes)

        Returns:
            Final graph result
        """
        if checkpoint_after_nodes is None:
            checkpoint_after_nodes = [
                "retrieve_context",
                "calculate_consensus",
                "run_pubmed",
                "calculate_r2_consensus",
            ]

        workflow_id = initial_state.get("workflow_id", "unknown")

        try:
            # Create hooks for this execution
            checkpoint_fn = self.create_node_checkpoint_hook(workflow_id)
            decision_fn = self.create_decision_trail_hook(workflow_id)
            escalation_fn = self.create_escalation_hook(workflow_id)

            # Store hooks in state for node functions to access
            state_with_hooks = initial_state.copy()
            state_with_hooks["_checkpoint_fn"] = checkpoint_fn
            state_with_hooks["_decision_fn"] = decision_fn
            state_with_hooks["_escalation_fn"] = escalation_fn

            # Execute graph (synchronous for now; can wrap in executor for true async)
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: graph_invoke_fn(state_with_hooks),
            )

            # Final checkpoint after completion
            checkpoint_fn("END", result)

            # Update workflow status
            self.store.update_workflow_status(workflow_id, "completed")

            logger.info(f"Workflow {workflow_id} execution completed")
            return result

        except Exception as e:
            logger.error(f"Workflow {workflow_id} execution failed: {e}")
            self.store.update_workflow_status(workflow_id, "failed")
            raise

    def summarize_workflow(self, workflow_id: str) -> dict:
        """
        Generate a summary of a completed workflow.

        Returns:
            Dict with: status, decision_trail, escalations, final_consensus, etc.
        """
        workflow_meta = self.store.get_workflow(workflow_id)
        decision_trail = self.store.get_decision_trail(workflow_id)
        latest_checkpoint = self.store.get_latest_checkpoint(workflow_id)

        summary = {
            "workflow_id": workflow_id,
            "status": workflow_meta.get("status") if workflow_meta else "unknown",
            "created_at": workflow_meta.get("created_at") if workflow_meta else None,
            "last_updated": workflow_meta.get("last_updated") if workflow_meta else None,
            "checkpoint_count": workflow_meta.get("checkpoint_count") if workflow_meta else 0,
            "decision_event_count": workflow_meta.get("decision_event_count") if workflow_meta else 0,
            "decision_trail": decision_trail,
            "final_state": latest_checkpoint[1] if latest_checkpoint else None,
        }

        return summary


# Singleton instance
_engine: Optional[WorkflowEngine] = None


def get_workflow_engine(store: Optional[WorkflowStore] = None) -> WorkflowEngine:
    """Get or create the WorkflowEngine singleton."""
    global _engine
    if _engine is None:
        _engine = WorkflowEngine(store=store)
    return _engine
