"""
Re-Deliberation Orchestrator for Long-Horizon Workflows

Coordinates monitoring events and automatically triggers re-deliberations
when conditions are met (new observations, low confidence, physician requests, etc.).

Connects WorkflowMonitor → Re-Deliberation Decision → Workflow Engine
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional, Callable, Any

from .workflow_monitor import (
    get_workflow_monitor,
    WorkflowMonitor,
    WorkflowTrigger,
    NewObservationTrigger,
    PhysicianRequestTrigger,
    LowConfidenceTrigger,
    ConsensusShiftTrigger,
)
from .workflow_engine import get_workflow_engine, WorkflowEngine
from .workflow_store import get_workflow_store, WorkflowStore
from .decision_trail import get_decision_trail_recorder

logger = logging.getLogger(__name__)


class RedeliberationOrchestrator:
    """
    Orchestrates monitoring-driven re-deliberations.

    Listens to workflow triggers and automatically initiates re-deliberations
    when conditions warrant it. Supports:
    - Automatic EHR polling for new observations
    - Physician-requested re-evaluation
    - Low confidence watchdog
    - Consensus shift detection
    """

    def __init__(
        self,
        monitor: Optional[WorkflowMonitor] = None,
        engine: Optional[WorkflowEngine] = None,
        store: Optional[WorkflowStore] = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            monitor: WorkflowMonitor instance
            engine: WorkflowEngine instance
            store: WorkflowStore instance
        """
        self.monitor = monitor or get_workflow_monitor()
        self.engine = engine or get_workflow_engine()
        self.store = store or get_workflow_store()
        self.active_monitors: dict[str, asyncio.Task] = {}

    def should_trigger_redlib(self, trigger: WorkflowTrigger, state: dict) -> bool:
        """
        Determine if a trigger should initiate re-deliberation.

        Args:
            trigger: The workflow trigger
            state: Current workflow state

        Returns:
            True if re-deliberation should be triggered
        """
        if isinstance(trigger, NewObservationTrigger):
            # Always trigger on new observations
            logger.info(f"New observation detected: {trigger.observation_type}")
            return True

        if isinstance(trigger, PhysicianRequestTrigger):
            # Always trigger on explicit physician request
            logger.info(f"Physician request: {trigger.reason}")
            return True

        if isinstance(trigger, LowConfidenceTrigger):
            # Compare current confidence to threshold
            current_confidence = state.get("consensus_confidence", 1.0)
            if current_confidence < trigger.threshold:
                logger.warning(
                    f"Low confidence detected: {current_confidence:.0%} < "
                    f"{trigger.threshold:.0%} threshold"
                )
                return True

        if isinstance(trigger, ConsensusShiftTrigger):
            # Check if diagnosis has changed
            new_diagnosis = state.get("consensus_diagnosis")
            if trigger.should_trigger_redlib(new_diagnosis):
                logger.info(
                    f"Consensus shift: '{trigger.original_diagnosis}' → '{new_diagnosis}'"
                )
                return True

        return False

    def get_redlib_reason(self, trigger: WorkflowTrigger) -> str:
        """Generate a human-readable reason for re-deliberation."""
        if isinstance(trigger, NewObservationTrigger):
            return f"New {trigger.observation_type} observation"
        elif isinstance(trigger, PhysicianRequestTrigger):
            return f"Physician request: {trigger.reason}"
        elif isinstance(trigger, LowConfidenceTrigger):
            return f"Low confidence ({trigger.threshold:.0%} threshold)"
        elif isinstance(trigger, ConsensusShiftTrigger):
            return f"Consensus shift from '{trigger.original_diagnosis}'"
        else:
            return "Monitoring trigger"

    async def process_triggers_for_workflow(
        self,
        workflow_id: str,
        graph_invoke_fn: Optional[Callable] = None,
    ) -> None:
        """
        Process pending triggers for a workflow.

        If triggers exist, initiate re-deliberation. If graph_invoke_fn provided,
        execute the new deliberation immediately.

        Args:
            workflow_id: The workflow to check
            graph_invoke_fn: Optional graph invocation function for immediate execution
        """
        triggers = self.monitor.get_pending_triggers(workflow_id)
        if not triggers:
            return

        # Fetch current workflow state
        checkpoint_result = self.store.get_latest_checkpoint(workflow_id)
        if checkpoint_result is None:
            logger.warning(f"No checkpoint found for workflow {workflow_id}")
            return

        checkpoint_id, state = checkpoint_result

        # Check if any trigger warrants re-deliberation
        for trigger in triggers:
            should_trigger = self.should_trigger_redlib(trigger, state)
            if not should_trigger:
                logger.debug(f"Trigger {trigger.trigger_id} does not warrant re-deliberation")
                continue

            # Initiate re-deliberation
            reason = self.get_redlib_reason(trigger)
            try:
                new_workflow_id, resumed_state = self.engine.initiate_re_deliberation(
                    workflow_id=workflow_id,
                    new_case_info=trigger.new_evidence if trigger.new_evidence else None,
                    triggered_by_escalation=False,
                )

                logger.info(
                    f"Re-deliberation initiated: {new_workflow_id} "
                    f"Reason: {reason}"
                )

                # Record in decision trail
                recorder = get_decision_trail_recorder(new_workflow_id)
                recorder.record_new_observation(
                    observation_type=type(trigger).__name__,
                    observation_data=trigger.new_evidence or {},
                )

                # Execute re-deliberation if graph provided
                if graph_invoke_fn:
                    logger.info(f"Executing re-deliberation: {new_workflow_id}")
                    result = await self.engine.execute_with_checkpoints(
                        graph_invoke_fn=graph_invoke_fn,
                        initial_state=resumed_state,
                    )
                    logger.info(f"Re-deliberation completed: {new_workflow_id}")
                else:
                    logger.info(f"Re-deliberation queued: {new_workflow_id} (awaiting execution)")

                break  # Process only first valid trigger per cycle

            except Exception as e:
                logger.error(f"Failed to initiate re-deliberation for {workflow_id}: {e}")
                import traceback
                traceback.print_exc()

        # Clear processed triggers
        self.monitor.clear_triggers(workflow_id)

    async def start_background_monitoring(
        self,
        workflow_id: str,
        patient_id: str,
        ehr_service: Optional[Any] = None,
        check_interval: int = 300,  # 5 minutes default
        graph_invoke_fn: Optional[Callable] = None,
    ) -> None:
        """
        Start background monitoring for a workflow.

        Periodically checks for pending triggers and initiates re-deliberations.

        Args:
            workflow_id: Workflow to monitor
            patient_id: Patient ID
            ehr_service: Optional EHR service for polling
            check_interval: Seconds between checks
            graph_invoke_fn: Optional graph execution function
        """
        if workflow_id in self.active_monitors:
            logger.warning(f"Monitoring already active for {workflow_id}")
            return

        async def monitor_loop():
            try:
                while True:
                    await asyncio.sleep(check_interval)

                    # Poll EHR if service provided
                    if ehr_service:
                        try:
                            self.monitor.register_new_observation(
                                workflow_id=workflow_id,
                                patient_id=patient_id,
                                observation_type="ehr_poll",
                                observation_data={"polled_at": datetime.utcnow().isoformat()},
                            )
                        except Exception as e:
                            logger.debug(f"EHR polling error: {e}")

                    # Process any pending triggers
                    await self.process_triggers_for_workflow(
                        workflow_id=workflow_id,
                        graph_invoke_fn=graph_invoke_fn,
                    )

            except asyncio.CancelledError:
                logger.info(f"Background monitoring stopped for {workflow_id}")
                raise
            except Exception as e:
                logger.error(f"Background monitoring error for {workflow_id}: {e}")

        task = asyncio.create_task(monitor_loop())
        self.active_monitors[workflow_id] = task
        logger.info(f"Started background monitoring for {workflow_id} (interval: {check_interval}s)")

    async def stop_background_monitoring(self, workflow_id: str) -> None:
        """Stop background monitoring for a workflow."""
        if workflow_id in self.active_monitors:
            task = self.active_monitors[workflow_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self.active_monitors[workflow_id]
            logger.info(f"Stopped background monitoring for {workflow_id}")

    def get_monitoring_status(self, workflow_id: str) -> dict:
        """Get current monitoring status for a workflow."""
        pending_triggers = self.monitor.get_pending_triggers(workflow_id)
        is_monitored = workflow_id in self.active_monitors

        return {
            "workflow_id": workflow_id,
            "is_monitored": is_monitored,
            "pending_trigger_count": len(pending_triggers),
            "pending_triggers": [
                {
                    "trigger_id": t.trigger_id,
                    "type": type(t).__name__,
                    "triggered_at": t.triggered_at.isoformat() if t.triggered_at else None,
                    "evidence": t.new_evidence,
                }
                for t in pending_triggers
            ],
        }


# Singleton instance
_orchestrator: Optional[RedeliberationOrchestrator] = None


def get_redlib_orchestrator(
    monitor: Optional[WorkflowMonitor] = None,
    engine: Optional[WorkflowEngine] = None,
    store: Optional[WorkflowStore] = None,
) -> RedeliberationOrchestrator:
    """Get or create the re-deliberation orchestrator singleton."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = RedeliberationOrchestrator(
            monitor=monitor,
            engine=engine,
            store=store,
        )
    return _orchestrator
