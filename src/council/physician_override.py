"""
Physician Override & Intervention Handler

Captures physician decisions that override or modify AI consensus,
logs feedback, and feeds learning loops for specialist routing tuning
and escalation rule improvement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Literal

from .decision_trail import get_decision_trail_recorder
from .workflow_store import get_workflow_store, WorkflowStore

logger = logging.getLogger(__name__)


class OverrideType(str, Enum):
    """Physician override decision types."""
    DIAGNOSIS_CHANGED = "diagnosis_changed"  # Changed final diagnosis
    CONFIDENCE_ADJUSTED = "confidence_adjusted"  # Modified confidence
    SPECIALIST_ADDED = "specialist_added"  # Added specialist consultation
    ESCALATION_DISMISSED = "escalation_dismissed"  # Override escalation
    ESCALATION_TRIGGERED = "escalation_triggered"  # Agree with/enforce escalation
    INVESTIGATION_ADDED = "investigation_added"  # Added investigation
    INVESTIGATION_SKIPPED = "investigation_skipped"  # Skipped recommended test


class OverrideFeedback(str, Enum):
    """Feedback on specialist routing accuracy."""
    CORRECT = "correct"  # Specialist recommendation was correct
    INCORRECT = "incorrect"  # Specialist recommendation was wrong
    INCOMPLETE = "incomplete"  # Specialist missed something
    OVER_REFERRED = "over_referred"  # Unnecessary specialist consultation
    HELPFUL = "helpful"  # Specialist added value
    REDUNDANT = "redundant"  # Specialist opinion duplicated main council


@dataclass
class PhysicianOverride:
    """Record of a physician intervention/override."""
    override_id: str
    workflow_id: str
    physician_id: str
    override_type: OverrideType
    timestamp: str
    ai_recommendation: str  # What AI suggested
    physician_decision: str  # What physician chose
    reasoning: str  # Why physician made this choice
    confidence_before: float  # AI confidence pre-override
    confidence_after: float  # Physician confidence post-override
    metadata: dict = field(default_factory=dict)


@dataclass
class SpecialistFeedback:
    """Feedback on specialist recommendation accuracy."""
    feedback_id: str
    workflow_id: str
    physician_id: str
    specialist_name: str
    feedback_type: OverrideFeedback
    timestamp: str
    reasoning: str = ""
    accuracy_score: float = 0.5  # 0.0 (wrong) to 1.0 (correct)
    metadata: dict = field(default_factory=dict)


class PhysicianOverrideHandler:
    """
    Handles physician overrides and interventions.

    Records override events with full context for:
    - Audit trail compliance
    - Feedback loop for specialist routing tuning
    - Learning from physician decisions
    - System performance metrics
    """

    def __init__(self, store: Optional[WorkflowStore] = None):
        """
        Initialize the override handler.

        Args:
            store: WorkflowStore instance
        """
        self.store = store or get_workflow_store()
        self.override_history: dict[str, list[PhysicianOverride]] = {}
        self.specialist_feedback_history: dict[str, list[SpecialistFeedback]] = {}

    def record_override(
        self,
        workflow_id: str,
        physician_id: str,
        override_type: OverrideType,
        ai_recommendation: str,
        physician_decision: str,
        reasoning: str,
        confidence_before: float = 0.0,
        confidence_after: float = 0.5,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Record a physician override/intervention.

        Args:
            workflow_id: Workflow identifier
            physician_id: Physician making override
            override_type: Type of override
            ai_recommendation: What AI suggested
            physician_decision: What physician chose
            reasoning: Why physician made this decision
            confidence_before: AI confidence level
            confidence_after: Physician's assessed confidence
            metadata: Optional metadata

        Returns:
            Override ID
        """
        import uuid

        override_id = f"override_{uuid.uuid4().hex[:8]}"
        override = PhysicianOverride(
            override_id=override_id,
            workflow_id=workflow_id,
            physician_id=physician_id,
            override_type=override_type,
            timestamp=datetime.utcnow().isoformat(),
            ai_recommendation=ai_recommendation,
            physician_decision=physician_decision,
            reasoning=reasoning,
            confidence_before=confidence_before,
            confidence_after=confidence_after,
            metadata=metadata or {},
        )

        if workflow_id not in self.override_history:
            self.override_history[workflow_id] = []

        self.override_history[workflow_id].append(override)

        # Log to decision trail for audit
        recorder = get_decision_trail_recorder(workflow_id)
        recorder.record_physician_request(
            physician_id=physician_id,
            reason=f"{override_type.value}: {reasoning}",
        )

        logger.info(
            f"Recorded override {override_id} for {workflow_id}: "
            f"{override_type.value} ({physician_decision})"
        )
        return override_id

    def record_specialist_feedback(
        self,
        workflow_id: str,
        physician_id: str,
        specialist_name: str,
        feedback_type: OverrideFeedback,
        reasoning: str = "",
        accuracy_score: float = 0.5,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Record feedback on specialist recommendation accuracy.

        Args:
            workflow_id: Workflow identifier
            physician_id: Physician providing feedback
            specialist_name: Name of specialist (e.g., "cardiology")
            feedback_type: Type of feedback
            reasoning: Explanation for feedback
            accuracy_score: 0.0 (incorrect) to 1.0 (correct)
            metadata: Optional metadata

        Returns:
            Feedback ID
        """
        import uuid

        feedback_id = f"feedback_{uuid.uuid4().hex[:8]}"
        feedback = SpecialistFeedback(
            feedback_id=feedback_id,
            workflow_id=workflow_id,
            physician_id=physician_id,
            specialist_name=specialist_name,
            feedback_type=feedback_type,
            timestamp=datetime.utcnow().isoformat(),
            reasoning=reasoning,
            accuracy_score=max(0.0, min(1.0, accuracy_score)),
            metadata=metadata or {},
        )

        if workflow_id not in self.specialist_feedback_history:
            self.specialist_feedback_history[workflow_id] = []

        self.specialist_feedback_history[workflow_id].append(feedback)

        logger.info(
            f"Recorded specialist feedback {feedback_id} for {specialist_name}: "
            f"{feedback_type.value} (accuracy: {accuracy_score:.1%})"
        )
        return feedback_id

    def get_override_history(self, workflow_id: str) -> list[PhysicianOverride]:
        """Get all overrides for a workflow."""
        return self.override_history.get(workflow_id, [])

    def get_specialist_feedback_history(
        self,
        workflow_id: str,
        specialist_filter: Optional[str] = None,
    ) -> list[SpecialistFeedback]:
        """Get specialist feedback for a workflow."""
        feedback = self.specialist_feedback_history.get(workflow_id, [])
        if specialist_filter:
            feedback = [f for f in feedback if f.specialist_name == specialist_filter]
        return feedback

    def summarize_override_patterns(
        self,
        workflow_id: str,
    ) -> dict:
        """
        Summarize override patterns for a workflow.

        Returns:
            {
                "total_overrides": int,
                "by_type": {type: count},
                "confidence_change": float,  # avg change
                "override_reasons": {reason: count},
            }
        """
        overrides = self.get_override_history(workflow_id)

        if not overrides:
            return {
                "total_overrides": 0,
                "by_type": {},
                "average_confidence_change": 0.0,
                "override_reasons": {},
            }

        by_type = {}
        confidence_changes = []

        for override in overrides:
            override_type = override.override_type.value
            by_type[override_type] = by_type.get(override_type, 0) + 1
            confidence_changes.append(override.confidence_after - override.confidence_before)

        avg_confidence_change = (
            sum(confidence_changes) / len(confidence_changes)
            if confidence_changes
            else 0.0
        )

        return {
            "total_overrides": len(overrides),
            "by_type": by_type,
            "average_confidence_change": avg_confidence_change,
            "total_physicians": len(set(o.physician_id for o in overrides)),
        }

    def summarize_specialist_feedback(
        self,
        workflow_id: str,
    ) -> dict:
        """
        Summarize specialist feedback accuracy.

        Returns:
            {
                "specialists": {name: {correct: count, incorrect: count, accuracy: 0-1}},
                "overall_accuracy": 0-1,
                "feedback_types": {type: count},
            }
        """
        feedback = self.get_specialist_feedback_history(workflow_id)

        if not feedback:
            return {
                "specialists": {},
                "overall_accuracy": 0.0,
                "feedback_types": {},
            }

        specialists = {}
        feedback_types = {}
        accuracy_scores = []

        for fb in feedback:
            # By specialist
            if fb.specialist_name not in specialists:
                specialists[fb.specialist_name] = {
                    "correct": 0,
                    "incorrect": 0,
                    "feedback_count": 0,
                    "accuracy_scores": [],
                }

            if fb.feedback_type in [OverrideFeedback.CORRECT, OverrideFeedback.HELPFUL]:
                specialists[fb.specialist_name]["correct"] += 1
            elif fb.feedback_type in [OverrideFeedback.INCORRECT, OverrideFeedback.INCOMPLETE]:
                specialists[fb.specialist_name]["incorrect"] += 1

            specialists[fb.specialist_name]["feedback_count"] += 1
            specialists[fb.specialist_name]["accuracy_scores"].append(fb.accuracy_score)

            # By feedback type
            feedback_type = fb.feedback_type.value
            feedback_types[feedback_type] = feedback_types.get(feedback_type, 0) + 1

            accuracy_scores.append(fb.accuracy_score)

        # Calculate accuracy per specialist
        for name, data in specialists.items():
            scores = data["accuracy_scores"]
            data["average_accuracy"] = (
                sum(scores) / len(scores) if scores else 0.0
            )
            del data["accuracy_scores"]  # Remove raw scores from output

        overall_accuracy = (
            sum(accuracy_scores) / len(accuracy_scores)
            if accuracy_scores
            else 0.0
        )

        return {
            "specialists": specialists,
            "overall_accuracy": round(overall_accuracy, 2),
            "feedback_types": feedback_types,
            "total_feedback_items": len(feedback),
        }

    def get_learning_insights(self, workflow_id: str) -> dict:
        """
        Generate learning insights from overrides and specialist feedback.

        Returns:
            {
                "patterns": [insight string],
                "specialist_recommendations": {specialist: recommendation},
                "routing_rule_suggestions": [suggestion],
                "escalation_rule_suggestions": [suggestion],
            }
        """
        overrides = self.get_override_history(workflow_id)
        specialist_feedback = self.get_specialist_feedback_history(workflow_id)

        patterns = []
        specialist_recs = {}
        routing_suggestions = []
        escalation_suggestions = []

        # Pattern 1: Confidence discrepancy
        avg_confidence_delta = (
            sum(o.confidence_after - o.confidence_before for o in overrides) / len(overrides)
            if overrides
            else 0.0
        )
        if avg_confidence_delta > 0.15:
            patterns.append(
                f"Physicians consistently increase confidence by {avg_confidence_delta:.0%} "
                f"beyond AI assessment (AI may be under-confident)"
            )
            escalation_suggestions.append(
                "Consider raising escalation thresholds (AI confidence may be too conservative)"
            )
        elif avg_confidence_delta < -0.15:
            patterns.append(
                f"Physicians reduce confidence by {-avg_confidence_delta:.0%} "
                f"below AI assessment (AI may be over-confident)"
            )
            escalation_suggestions.append(
                "Consider lowering escalation thresholds (AI may be too aggressive)"
            )

        # Pattern 2: Specialist accuracy
        specialist_summary = self.summarize_specialist_feedback(workflow_id)
        for spec_name, spec_data in specialist_summary["specialists"].items():
            avg_accuracy = spec_data.get("average_accuracy", 0.5)
            if avg_accuracy > 0.8:
                specialist_recs[spec_name] = "HIGH_VALUE - Consider auto-routing more cases"
                routing_suggestions.append(
                    f"Increase {spec_name} referral threshold (accuracy: {avg_accuracy:.0%})"
                )
            elif avg_accuracy < 0.5:
                specialist_recs[spec_name] = "LOW_VALUE - Consider reducing referral frequency"
                routing_suggestions.append(
                    f"Decrease {spec_name} referral threshold (accuracy: {avg_accuracy:.0%})"
                )

        # Pattern 3: Override types
        override_summary = self.summarize_override_patterns(workflow_id)
        if override_summary["by_type"].get("diagnosis_changed", 0) > 0:
            patterns.append(
                f"Diagnosis changed {override_summary['by_type']['diagnosis_changed']} time(s) "
                f"by physician (may indicate weak consensus threshold)"
            )

        return {
            "patterns": patterns,
            "specialist_recommendations": specialist_recs,
            "routing_rule_suggestions": routing_suggestions,
            "escalation_rule_suggestions": escalation_suggestions,
        }


# Singleton instance
_handler: Optional[PhysicianOverrideHandler] = None


def get_physician_override_handler(
    store: Optional[WorkflowStore] = None,
) -> PhysicianOverrideHandler:
    """Get or create the physician override handler singleton."""
    global _handler
    if _handler is None:
        _handler = PhysicianOverrideHandler(store=store)
    return _handler
