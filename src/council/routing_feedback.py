"""
Specialist Routing Feedback & Adaptive Learning

Learns from physician overrides and specialist feedback to progressively
tune specialist routing rules and improve diagnostic accuracy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .physician_override import (
    get_physician_override_handler,
    OverrideFeedback,
)
from .specialist_router import (
    get_specialist_router,
    SpecialistRouter,
)

logger = logging.getLogger(__name__)


@dataclass
class RoutingRuleAdjustment:
    """Recommended adjustment to specialist routing rules."""
    specialist: str
    change_type: str  # "increase_threshold", "decrease_threshold", "auto_route", "remove"
    reason: str
    confidence: float  # 0.0-1.0 how confident in adjustment
    evidence_count: int  # How many cases informed this adjustment


class RoutingFeedbackLearner:
    """
    Learns from physician overrides to adapt specialist routing.

    Tracks:
    - Specialist consultation accuracy
    - False positive referrals (cases that didn't need specialist)
    - False negative referrals (cases that should have used specialist)
    - Diagnosis improvement with specialist involvement
    - Workflow efficiency (time/resource use per specialist)
    """

    def __init__(self, router: Optional[SpecialistRouter] = None):
        """
        Initialize the feedback learner.

        Args:
            router: SpecialistRouter instance for rule updates
        """
        self.router = router or get_specialist_router()
        self.override_handler = get_physician_override_handler()
        self.specialist_stats: dict[str, dict] = {}

    def analyze_workflow_feedback(self, workflow_id: str) -> RoutingRuleAdjustment:
        """
        Analyze feedback from a single workflow to generate routing adjustment.

        Args:
            workflow_id: Workflow to analyze

        Returns:
            Routing rule adjustment recommendation
        """
        specialist_feedback = self.override_handler.get_specialist_feedback_history(
            workflow_id
        )
        if not specialist_feedback:
            return None

        # Aggregate feedback by specialist
        feedback_by_spec = {}
        for fb in specialist_feedback:
            spec = fb.specialist_name
            if spec not in feedback_by_spec:
                feedback_by_spec[spec] = {
                    "correct": 0,
                    "incorrect": 0,
                    "helpful": 0,
                    "redundant": 0,
                    "accuracy_scores": [],
                }

            if fb.feedback_type == OverrideFeedback.CORRECT:
                feedback_by_spec[spec]["correct"] += 1
            elif fb.feedback_type == OverrideFeedback.INCORRECT:
                feedback_by_spec[spec]["incorrect"] += 1
            elif fb.feedback_type == OverrideFeedback.HELPFUL:
                feedback_by_spec[spec]["helpful"] += 1
            elif fb.feedback_type == OverrideFeedback.REDUNDANT:
                feedback_by_spec[spec]["redundant"] += 1

            feedback_by_spec[spec]["accuracy_scores"].append(fb.accuracy_score)

        # Generate adjustments for each specialist
        adjustments = []
        for spec, stats in feedback_by_spec.items():
            total_feedback = sum([
                stats["correct"],
                stats["incorrect"],
                stats["helpful"],
                stats["redundant"],
            ])

            if total_feedback < 2:  # Need at least 2 data points
                continue

            accuracy = (
                (stats["correct"] + stats["helpful"]) / total_feedback
                if total_feedback > 0
                else 0.0
            )

            if accuracy > 0.75 and stats["helpful"] > stats["redundant"]:
                # Specialist is valuable - route more cases
                adjustments.append(
                    RoutingRuleAdjustment(
                        specialist=spec,
                        change_type="increase_threshold",
                        reason=f"High accuracy ({accuracy:.0%}) and helpful feedback",
                        confidence=min(accuracy, 0.9),
                        evidence_count=total_feedback,
                    )
                )

            elif accuracy < 0.4 or (stats["redundant"] > stats["helpful"]):
                # Specialist is providing little value - route fewer cases
                adjustments.append(
                    RoutingRuleAdjustment(
                        specialist=spec,
                        change_type="decrease_threshold",
                        reason=f"Low accuracy ({accuracy:.0%}) or redundant feedback",
                        confidence=min(1 - accuracy, 0.9),
                        evidence_count=total_feedback,
                    )
                )

        return adjustments if adjustments else []

    def calculate_specialist_metrics(self, specialist: str) -> dict:
        """
        Calculate comprehensive metrics for a specialist.

        Returns:
            {
                "name": specialist,
                "accuracy_score": 0-1,
                "consultation_rate": % of cases
                "value_score": 0-100,
                "routing_recommendation": "auto_route" | "manual" | "reduce",
                "confidence": 0-1,
            }
        """
        if specialist not in self.specialist_stats:
            return {
                "name": specialist,
                "accuracy_score": 0.5,
                "consultation_count": 0,
                "value_score": 50,
                "routing_recommendation": "manual",
                "confidence": 0.0,
            }

        stats = self.specialist_stats[specialist]
        accuracy = stats.get("accuracy", 0.5)
        value_score = int(
            accuracy * 50 +  # Accuracy up to 50 points
            (1 - stats.get("redundancy_rate", 0)) * 30 +  # Low redundancy up to 30
            stats.get("timeliness_score", 0.5) * 20  # Timely response up to 20
        )

        if accuracy > 0.8 and value_score > 70:
            recommendation = "auto_route"
        elif accuracy < 0.5 or value_score < 40:
            recommendation = "reduce"
        else:
            recommendation = "manual"

        return {
            "name": specialist,
            "accuracy_score": round(accuracy, 2),
            "consultation_count": stats.get("consultation_count", 0),
            "value_score": value_score,
            "routing_recommendation": recommendation,
            "confidence": min(accuracy, 0.95),  # Confidence capped at 95%
        }

    def get_routing_adjustments_batch(
        self,
        workflow_ids: list[str],
    ) -> list[RoutingRuleAdjustment]:
        """
        Analyze multiple workflows and aggregate routing adjustments.

        Args:
            workflow_ids: List of workflow IDs to analyze

        Returns:
            List of aggregated routing adjustments
        """
        all_adjustments = []

        for workflow_id in workflow_ids:
            adjustments = self.analyze_workflow_feedback(workflow_id)
            if adjustments:
                if isinstance(adjustments, list):
                    all_adjustments.extend(adjustments)
                else:
                    all_adjustments.append(adjustments)

        # Aggregate identical adjustments
        adjustment_map = {}
        for adj in all_adjustments:
            key = f"{adj.specialist}:{adj.change_type}"
            if key not in adjustment_map:
                adjustment_map[key] = {
                    "total_confidence": 0.0,
                    "total_evidence": 0,
                    "count": 0,
                    "reasons": [],
                }

            adjustment_map[key]["total_confidence"] += adj.confidence
            adjustment_map[key]["total_evidence"] += adj.evidence_count
            adjustment_map[key]["count"] += 1
            adjustment_map[key]["reasons"].append(adj.reason)

        # Convert back to adjustments with aggregated stats
        aggregated = []
        for key, data in adjustment_map.items():
            specialist, change_type = key.split(":")
            avg_confidence = data["total_confidence"] / data["count"]

            if avg_confidence > 0.6:  # Only recommend if confident
                aggregated.append(
                    RoutingRuleAdjustment(
                        specialist=specialist,
                        change_type=change_type,
                        reason=f"Aggregated from {data['count']} workflows: " + "; ".join(
                            set(data["reasons"])
                        ),
                        confidence=avg_confidence,
                        evidence_count=data["total_evidence"],
                    )
                )

        return sorted(
            aggregated,
            key=lambda x: x.confidence * x.evidence_count,
            reverse=True,
        )

    def generate_routing_report(self) -> str:
        """
        Generate a report on specialist routing effectiveness.

        Returns:
            Markdown-formatted report
        """
        lines = [
            "# Specialist Routing Effectiveness Report\n",
            "Generated: " + datetime.utcnow().isoformat() + "\n",
        ]

        specialists = [
            "cardiology",
            "rheumatology",
            "neurology",
            "infectious_disease",
            "internal_medicine",
        ]

        lines.append("## Specialist Metrics\n")
        lines.append("| Specialist | Accuracy | Consultations | Value Score | Recommendation |")
        lines.append("|---|---|---|---|---|")

        for spec in specialists:
            metrics = self.calculate_specialist_metrics(spec)
            lines.append(
                f"| {metrics['name']} | {metrics['accuracy_score']:.0%} | "
                f"{metrics['consultation_count']} | {metrics['value_score']:d} | "
                f"{metrics['routing_recommendation']} |"
            )

        lines.append("\n## Recommended Adjustments\n")

        # Get recent adjustments
        sample_workflows = []  # In production, would get recent workflows
        if sample_workflows:
            adjustments = self.get_routing_adjustments_batch(sample_workflows)
            for adj in adjustments[:10]:  # Top 10 adjustments
                lines.append(
                    f"- **{adj.specialist}**: {adj.change_type} "
                    f"(confidence: {adj.confidence:.0%}) - {adj.reason}"
                )
        else:
            lines.append("(No recent workflows to analyze)")

        return "\n".join(lines)


# Singleton instance
_learner: Optional[RoutingFeedbackLearner] = None


def get_routing_feedback_learner(
    router: Optional[SpecialistRouter] = None,
) -> RoutingFeedbackLearner:
    """Get or create the routing feedback learner singleton."""
    global _learner
    if _learner is None:
        _learner = RoutingFeedbackLearner(router=router)
    return _learner


# Import at end to avoid circular dependency
from datetime import datetime
