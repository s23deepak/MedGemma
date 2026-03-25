"""
Workflow monitoring service for detecting re-deliberation triggers.

Monitors for:
- New EHR observations (labs, imaging results)
- Physician re-evaluation requests
- Low confidence thresholds
- Consensus shifts detected
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


class WorkflowTrigger:
    """Base class for workflow re-deliberation triggers."""

    def __init__(self, trigger_id: str, workflow_id: str):
        """
        Initialize a workflow trigger.

        Args:
            trigger_id: Unique trigger identifier
            workflow_id: Associated workflow ID
        """
        self.trigger_id = trigger_id
        self.workflow_id = workflow_id
        self.triggered_at: Optional[datetime] = None
        self.new_evidence: dict = {}

    def should_trigger_redlib(self) -> bool:
        """Determine if re-deliberation should be triggered."""
        raise NotImplementedError


class NewObservationTrigger(WorkflowTrigger):
    """Triggers re-deliberation when new EHR observations arrive."""

    def __init__(self, workflow_id: str, patient_id: str, observation_type: str):
        """
        Args:
            workflow_id: Associated workflow
            patient_id: Patient identifier
            observation_type: "lab_result", "imaging_result", "vital_signs", "progress_note"
        """
        super().__init__(f"new_obs_{observation_type}_{patient_id}", workflow_id)
        self.patient_id = patient_id
        self.observation_type = observation_type

    def should_trigger_redlib(self) -> bool:
        """Always trigger on new observations."""
        return True


class PhysicianRequestTrigger(WorkflowTrigger):
    """Manually triggered by physician request."""

    def __init__(self, workflow_id: str, physician_id: str, reason: str):
        super().__init__(f"physician_request_{workflow_id}", workflow_id)
        self.physician_id = physician_id
        self.reason = reason

    def should_trigger_redlib(self) -> bool:
        """Always trigger on explicit physician request."""
        return True


class LowConfidenceTrigger(WorkflowTrigger):
    """Triggers re-deliberation if consensus confidence drops below threshold."""

    def __init__(self, workflow_id: str, threshold: float = 0.5):
        super().__init__(f"low_confidence_{workflow_id}", workflow_id)
        self.threshold = threshold

    def should_trigger_redlib(self, current_confidence: float) -> bool:
        """Trigger if confidence below threshold."""
        return current_confidence < self.threshold


class ConsensusShiftTrigger(WorkflowTrigger):
    """Detects if consensus diagnosis has changed between deliberations."""

    def __init__(self, workflow_id: str, original_diagnosis: Optional[str]):
        super().__init__(f"consensus_shift_{workflow_id}", workflow_id)
        self.original_diagnosis = original_diagnosis

    def should_trigger_redlib(self, new_diagnosis: Optional[str]) -> bool:
        """Trigger if diagnosis changed."""
        if self.original_diagnosis is None or new_diagnosis is None:
            return False
        return self.original_diagnosis.lower() != new_diagnosis.lower()


class WorkflowMonitor:
    """
    Service for monitoring workflows and detecting re-deliberation triggers.

    Can operate in two modes:
    1. Polling: Periodically check EHR for new observations
    2. Webhook: Receive push notifications on new data
    """

    def __init__(self):
        """Initialize the workflow monitor."""
        self.triggers: dict[str, list[WorkflowTrigger]] = {}
        self.polling_interval: int = 300  # 5 minutes default
        self.polling_tasks: dict[str, asyncio.Task] = {}

    def register_trigger(self, workflow_id: str, trigger: WorkflowTrigger) -> None:
        """Register a new trigger for a workflow."""
        if workflow_id not in self.triggers:
            self.triggers[workflow_id] = []
        self.triggers[workflow_id].append(trigger)
        logger.info(f"Registered trigger {trigger.trigger_id} for workflow {workflow_id}")

    def register_new_observation(
        self,
        workflow_id: str,
        patient_id: str,
        observation_type: str,
        observation_data: dict,
    ) -> None:
        """
        Register a new EHR observation that may trigger re-deliberation.

        Args:
            workflow_id: Associated workflow
            patient_id: Patient ID
            observation_type: Type of observation (lab, imaging, vitals)
            observation_data: Observation data dict
        """
        trigger = NewObservationTrigger(workflow_id, patient_id, observation_type)
        trigger.new_evidence = observation_data
        trigger.triggered_at = datetime.utcnow()
        self.register_trigger(workflow_id, trigger)
        logger.info(f"New {observation_type} observation registered for patient {patient_id}")

    def register_physician_request(
        self,
        workflow_id: str,
        physician_id: str,
        reason: str,
    ) -> None:
        """
        Register a physician's manual re-evaluation request.

        Args:
            workflow_id: Associated workflow
            physician_id: Physician requesting re-evaluation
            reason: Reason for request
        """
        trigger = PhysicianRequestTrigger(workflow_id, physician_id, reason)
        trigger.triggered_at = datetime.utcnow()
        self.register_trigger(workflow_id, trigger)
        logger.info(f"Physician request registered for workflow {workflow_id}: {reason}")

    def register_low_confidence_alert(
        self,
        workflow_id: str,
        current_confidence: float,
        threshold: float = 0.5,
    ) -> None:
        """
        Register a low confidence alert.

        Args:
            workflow_id: Associated workflow
            current_confidence: Current consensus confidence
            threshold: Confidence threshold
        """
        if current_confidence < threshold:
            trigger = LowConfidenceTrigger(workflow_id, threshold)
            trigger.triggered_at = datetime.utcnow()
            trigger.new_evidence = {"previous_confidence": current_confidence}
            self.register_trigger(workflow_id, trigger)
            logger.warning(
                f"Low confidence alert for workflow {workflow_id}: "
                f"{current_confidence:.0%} < {threshold:.0%}"
            )

    def get_pending_triggers(self, workflow_id: str) -> list[WorkflowTrigger]:
        """Get all pending triggers for a workflow that haven't been processed yet."""
        if workflow_id not in self.triggers:
            return []

        # Return all triggers (in real system, would mark as processed)
        return self.triggers[workflow_id]

    def clear_triggers(self, workflow_id: str) -> None:
        """Clear all triggers for a workflow after processing."""
        if workflow_id in self.triggers:
            self.triggers[workflow_id] = []
            logger.info(f"Cleared triggers for workflow {workflow_id}")

    async def start_polling_ehr(
        self,
        workflow_id: str,
        patient_id: str,
        ehr_service: Any,  # FirestoreFHIRServer or similar
        check_fn: Optional[Callable[[list], list[WorkflowTrigger]]] = None,
    ) -> None:
        """
        Start periodic polling of EHR for new observations.

        Args:
            workflow_id: Workflow to monitor
            patient_id: Patient ID to monitor
            ehr_service: EHR service instance
            check_fn: Optional custom check function
        """
        async def poll_loop():
            while True:
                try:
                    # Fetch latest patient observations
                    observations = ehr_service.list_patient_observations(patient_id)

                    # If custom check provided, use it
                    if check_fn:
                        new_triggers = check_fn(observations)
                        for trigger in new_triggers:
                            self.register_trigger(workflow_id, trigger)
                    else:
                        # Default: check for observations younger than last update
                        for obs in observations:
                            obs_id = obs.get("id")
                            obs_type = obs.get("code", {}).get("coding", [{}])[0].get("code")
                            if obs_type in ("lab", "imaging", "vital-signs"):
                                self.register_new_observation(
                                    workflow_id,
                                    patient_id,
                                    obs_type,
                                    obs,
                                )

                    await asyncio.sleep(self.polling_interval)

                except asyncio.CancelledError:
                    logger.info(f"Polling stopped for workflow {workflow_id}")
                    raise
                except Exception as e:
                    logger.error(f"Error polling EHR for {workflow_id}: {e}")
                    await asyncio.sleep(self.polling_interval * 2)  # Back off on error

        # Create and store polling task
        task = asyncio.create_task(poll_loop())
        self.polling_tasks[workflow_id] = task
        logger.info(f"Started EHR polling for workflow {workflow_id}")

    async def stop_polling_ehr(self, workflow_id: str) -> None:
        """Stop polling for a workflow."""
        if workflow_id in self.polling_tasks:
            self.polling_tasks[workflow_id].cancel()
            try:
                await self.polling_tasks[workflow_id]
            except asyncio.CancelledError:
                pass
            del self.polling_tasks[workflow_id]
            logger.info(f"Stopped EHR polling for workflow {workflow_id}")

    def has_pending_redlib(self, workflow_id: str) -> bool:
        """Check if any pending triggers exist for a workflow."""
        triggers = self.get_pending_triggers(workflow_id)
        return len(triggers) > 0

    def summarize_pending_triggers(self, workflow_id: str) -> dict:
        """Generate a summary of pending triggers."""
        triggers = self.get_pending_triggers(workflow_id)

        summary = {
            "workflow_id": workflow_id,
            "pending_trigger_count": len(triggers),
            "triggers": [
                {
                    "trigger_id": t.trigger_id,
                    "type": type(t).__name__,
                    "triggered_at": t.triggered_at.isoformat() if t.triggered_at else None,
                    "evidence": t.new_evidence,
                }
                for t in triggers
            ],
        }
        return summary


# Singleton instance
_monitor: Optional[WorkflowMonitor] = None


def get_workflow_monitor() -> WorkflowMonitor:
    """Get or create the WorkflowMonitor singleton."""
    global _monitor
    if _monitor is None:
        _monitor = WorkflowMonitor()
    return _monitor
