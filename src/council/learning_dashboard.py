"""
Learning Dashboard for Case Analytics & System Performance

Provides comprehensive metrics and analytics on diagnostic accuracy,
specialist effectiveness, escalation patterns, and system improvements
driven by physician feedback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .physician_override import get_physician_override_handler
from .routing_feedback import get_routing_feedback_learner
from .decision_trail_query import get_decision_trail_query

logger = logging.getLogger(__name__)


@dataclass
class CaseMetrics:
    """Metrics for a single case/workflow."""
    workflow_id: str
    patient_id: str
    initial_diagnosis: str
    final_diagnosis: str
    specialist_consulted: list[str]
    specialist_accuracy: float
    time_to_diagnosis: int  # seconds
    escalations: int
    overrides: int
    confidence_change: float  # AI to physician final


@dataclass
class SystemMetrics:
    """Aggregate system performance metrics."""
    total_cases: int
    average_accuracy: float
    specialist_utilization: dict  # {specialist: utilization_rate}
    escalation_rate: float
    override_rate: float
    average_time_to_diagnosis: int
    physician_agreement_rate: float  # % of AI conclusions physician agrees with
    specialist_improvement: dict  # {specialist: improvement_delta}


class LearningDashboard:
    """
    Comprehensive analytics dashboard for system performance.

    Tracks:
    - Case outcomes and diagnostic accuracy
    - Specialist consultation effectiveness
    - Escalation patterns and appropriateness
    - Physician override patterns
    - System improvement trends
    - Performance by specialist, hospital, physician
    """

    def __init__(self):
        """Initialize the learning dashboard."""
        self.override_handler = get_physician_override_handler()
        self.routing_learner = get_routing_feedback_learner()
        self.trail_query = get_decision_trail_query()
        self.case_metrics: dict[str, CaseMetrics] = {}

    def record_case_outcome(
        self,
        workflow_id: str,
        patient_id: str,
        initial_diagnosis: str,
        final_diagnosis: str,
        specialist_consulted: list[str],
        time_to_diagnosis: int,
        escalation_count: int = 0,
    ) -> str:
        """
        Record outcome metrics for a case.

        Args:
            workflow_id: Workflow ID
            patient_id: Patient ID
            initial_diagnosis: AI initial diagnosis
            final_diagnosis: Final diagnosis (after physician review)
            specialist_consulted: List of specialists involved
            time_to_diagnosis: Time in seconds
            escalation_count: Number of escalation events

        Returns:
            Workflow ID for reference
        """
        overrides = self.override_handler.get_override_history(workflow_id)
        specialist_feedbacks = self.override_handler.get_specialist_feedback_history(workflow_id)

        specialist_accuracy = (
            sum(f.accuracy_score for f in specialist_feedbacks) / len(specialist_feedbacks)
            if specialist_feedbacks
            else 0.5
        )

        metrics = CaseMetrics(
            workflow_id=workflow_id,
            patient_id=patient_id,
            initial_diagnosis=initial_diagnosis,
            final_diagnosis=final_diagnosis,
            specialist_consulted=specialist_consulted,
            specialist_accuracy=specialist_accuracy,
            time_to_diagnosis=time_to_diagnosis,
            escalations=escalation_count,
            overrides=len(overrides),
            confidence_change=(
                sum(o.confidence_after - o.confidence_before for o in overrides) / len(overrides)
                if overrides
                else 0.0
            ),
        )

        self.case_metrics[workflow_id] = metrics
        logger.info(f"Recorded case metrics for {workflow_id}")
        return workflow_id

    def calculate_system_metrics(
        self,
        workflow_ids: Optional[list[str]] = None,
    ) -> SystemMetrics:
        """
        Calculate aggregate system performance metrics.

        Args:
            workflow_ids: Optional list of workflows to analyze (default: all)

        Returns:
            SystemMetrics with aggregate statistics
        """
        workflows = workflow_ids or list(self.case_metrics.keys())
        if not workflows:
            return SystemMetrics(
                total_cases=0,
                average_accuracy=0.0,
                specialist_utilization={},
                escalation_rate=0.0,
                override_rate=0.0,
                average_time_to_diagnosis=0,
                physician_agreement_rate=0.0,
                specialist_improvement={},
            )

        # Collect metrics
        cases = [self.case_metrics[wid] for wid in workflows if wid in self.case_metrics]

        if not cases:
            return SystemMetrics(
                total_cases=0,
                average_accuracy=0.0,
                specialist_utilization={},
                escalation_rate=0.0,
                override_rate=0.0,
                average_time_to_diagnosis=0,
                physician_agreement_rate=0.0,
                specialist_improvement={},
            )

        # Calculate metrics
        accuracy_correct = sum(
            1 for c in cases if c.initial_diagnosis.lower() == c.final_diagnosis.lower()
        )
        average_accuracy = accuracy_correct / len(cases) if cases else 0.0

        # Specialist utilization
        specialist_usage = {}
        for case in cases:
            for spec in case.specialist_consulted:
                specialist_usage[spec] = specialist_usage.get(spec, 0) + 1

        specialist_utilization = {
            spec: usage / len(cases) for spec, usage in specialist_usage.items()
        }

        escalation_rate = (
            sum(c.escalations for c in cases) / len(cases) if cases else 0.0
        )

        override_rate = (
            sum(c.overrides for c in cases) / len(cases) if cases else 0.0
        )

        average_time = (
            sum(c.time_to_diagnosis for c in cases) // len(cases) if cases else 0
        )

        # Physician agreement rate (cases with no overrides = physician agreed)
        no_override_cases = sum(1 for c in cases if c.overrides == 0)
        physician_agreement_rate = (
            no_override_cases / len(cases) if cases else 0.0
        )

        # Specialist improvement (trending)
        specialist_improvement = {}
        for spec in specialist_utilization.keys():
            improvement = self._calculate_specialist_improvement(spec, cases)
            if improvement != 0.0:
                specialist_improvement[spec] = improvement

        return SystemMetrics(
            total_cases=len(cases),
            average_accuracy=round(average_accuracy, 2),
            specialist_utilization=specialist_utilization,
            escalation_rate=round(escalation_rate, 2),
            override_rate=round(override_rate, 2),
            average_time_to_diagnosis=average_time,
            physician_agreement_rate=round(physician_agreement_rate, 2),
            specialist_improvement=specialist_improvement,
        )

    def _calculate_specialist_improvement(
        self,
        specialist: str,
        cases: list[CaseMetrics],
    ) -> float:
        """
        Calculate improvement trend for a specialist.

        Positive value = improving, Negative = declining.
        """
        specialist_cases = [
            c for c in cases if specialist in c.specialist_consulted
        ]

        if len(specialist_cases) < 2:
            return 0.0

        # Compare recent vs older cases
        mid_point = len(specialist_cases) // 2
        older_avg = (
            sum(c.specialist_accuracy for c in specialist_cases[:mid_point]) /
            max(1, mid_point)
        )
        recent_avg = (
            sum(c.specialist_accuracy for c in specialist_cases[mid_point:]) /
            max(1, len(specialist_cases) - mid_point)
        )

        return round(recent_avg - older_avg, 2)

    def generate_dashboard_report(
        self,
        workflow_ids: Optional[list[str]] = None,
    ) -> str:
        """
        Generate comprehensive dashboard report.

        Returns:
            Markdown-formatted dashboard report
        """
        metrics = self.calculate_system_metrics(workflow_ids)

        lines = [
            "# Learning Dashboard Report\n",
            f"Generated: {datetime.utcnow().isoformat()}\n",
            f"Analysis Period: {len(self.case_metrics)} total cases\n",
        ]

        # Summary section
        lines.append("## Summary\n")
        lines.append(f"- **Total Cases**: {metrics.total_cases}")
        lines.append(f"- **Diagnostic Accuracy**: {metrics.average_accuracy:.0%}")
        lines.append(f"- **Physician Agreement Rate**: {metrics.physician_agreement_rate:.0%}")
        lines.append(f"- **Average Time to Diagnosis**: {metrics.average_time_to_diagnosis}s")
        lines.append(f"- **Escalation Rate**: {metrics.escalation_rate:.1%}")
        lines.append(f"- **Override Rate**: {metrics.override_rate:.1%}\n")

        # Specialist performance
        lines.append("## Specialist Performance\n")
        lines.append("| Specialist | Utilization | Improvement |")
        lines.append("|---|---|---|")

        for spec, util in metrics.specialist_utilization.items():
            improvement = metrics.specialist_improvement.get(spec, 0.0)
            improvement_str = f"{improvement:+.1%}" if improvement != 0 else "—"
            lines.append(f"| {spec} | {util:.0%} | {improvement_str} |")

        lines.append("\n")

        # Trends
        lines.append("## Trends\n")
        if metrics.escalation_rate > 0.2:
            lines.append("⚠️ High escalation rate detected\n")
        if metrics.override_rate > 0.15:
            lines.append("⚠️ High physician override rate - check consensus confidence thresholds\n")
        if metrics.average_accuracy < 0.7:
            lines.append("⚠️ Accuracy below 70% - consider specialist routing review\n")
        if metrics.physician_agreement_rate > 0.9:
            lines.append("✓ High physician agreement - system performing well\n")
        if any(i > 0.05 for i in metrics.specialist_improvement.values()):
            lines.append("✓ Specialist accuracy improving - learning loop working\n")

        return "\n".join(lines)

    def get_specialist_leaderboard(self) -> list[dict]:
        """
        Get specialist rankings by effectiveness.

        Returns:
            List of specialists ranked by accuracy and value
        """
        specialists = {}

        for case in self.case_metrics.values():
            for spec in case.specialist_consulted:
                if spec not in specialists:
                    specialists[spec] = {
                        "name": spec,
                        "cases": 0,
                        "accuracy_sum": 0.0,
                        "successful_interventions": 0,
                    }

                specialists[spec]["cases"] += 1
                specialists[spec]["accuracy_sum"] += case.specialist_accuracy

                # Count successful ones (when specialist was consulted + diagnosis improved)
                if not case.initial_diagnosis.lower() == case.final_diagnosis.lower():
                    specialists[spec]["successful_interventions"] += 1

        # Calculate rankings
        leaderboard = []
        for spec_name, data in specialists.items():
            avg_accuracy = (
                data["accuracy_sum"] / data["cases"]
                if data["cases"] > 0
                else 0.0
            )
            success_rate = (
                data["successful_interventions"] / data["cases"]
                if data["cases"] > 0
                else 0.0
            )

            leaderboard.append({
                "specialist": spec_name,
                "cases": data["cases"],
                "accuracy": round(avg_accuracy, 2),
                "success_rate": round(success_rate, 2),
                "score": round(avg_accuracy * 0.6 + success_rate * 0.4, 2),
            })

        # Sort by score
        return sorted(leaderboard, key=lambda x: x["score"], reverse=True)


# Singleton instance
_dashboard: Optional[LearningDashboard] = None


def get_learning_dashboard() -> LearningDashboard:
    """Get or create the learning dashboard singleton."""
    global _dashboard
    if _dashboard is None:
        _dashboard = LearningDashboard()
    return _dashboard
