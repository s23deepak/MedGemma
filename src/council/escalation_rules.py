"""
Escalation rules engine for long-horizon diagnostic council workflows.

Implements decision rules for when to escalate cases to physician review:
- Weak consensus (< 50%)
- Split consensus (multiple diagnoses tied)
- Specialist divergence (specialist council contradicts main)
- High urgency with low confidence
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class EscalationSeverity(str, Enum):
    """Severity levels for escalation flags."""
    CRITICAL = "critical"
    WARNING = "warning"


class EscalationRuleId(str, Enum):
    """Predefined escalation rule IDs."""
    WEAK_CONSENSUS_URGENT = "weak_consensus_urgent"
    SPLIT_CONSENSUS = "split_consensus"
    SPECIALIST_DIVERGENCE = "specialist_divergence"
    NO_CONSENSUS = "no_consensus"
    CONFIDENCE_LOW_URGENCY_HIGH = "confidence_low_urgency_high"
    RARE_DIAGNOSIS_UNCONFIRMED = "rare_diagnosis_unconfirmed"


@dataclass
class EscalationRecommendation:
    """Recommendation for handling an escalated case."""
    rule_id: str
    severity: EscalationSeverity
    reason: str
    recommended_action: str
    suggested_specialists: list[str]


class EscalationRulesEngine:
    """
    Rule engine for determining when to escalate consensus results to physicians.
    """

    def __init__(self):
        """Initialize the escalation rules engine."""
        self.rules = {
            EscalationRuleId.WEAK_CONSENSUS_URGENT: self._rule_weak_consensus_urgent,
            EscalationRuleId.SPLIT_CONSENSUS: self._rule_split_consensus,
            EscalationRuleId.SPECIALIST_DIVERGENCE: self._rule_specialist_divergence,
            EscalationRuleId.NO_CONSENSUS: self._rule_no_consensus,
            EscalationRuleId.CONFIDENCE_LOW_URGENCY_HIGH: self._rule_confidence_low_urgency_high,
            EscalationRuleId.RARE_DIAGNOSIS_UNCONFIRMED: self._rule_rare_diagnosis_unconfirmed,
        }

    def evaluate_consensus(
        self,
        consensus_diagnosis: Optional[str],
        consensus_confidence: float,
        consensus_strength: str,
        urgency: str,
        num_opinions: int,
        dissenting_count: int,
    ) -> list[EscalationRecommendation]:
        """
        Evaluate consensus state against all escalation rules.

        Args:
            consensus_diagnosis: The consensus diagnosis (or None)
            consensus_confidence: Confidence score (0.0-1.0)
            consensus_strength: "strong", "moderate", "weak", or "split"
            urgency: "routine", "urgent", or "emergent"
            num_opinions: Total number of opinions generated
            dissenting_count: Number of dissenting opinions

        Returns:
            List of EscalationRecommendation if any rules triggered
        """
        escalations = []

        # Rule 1: Weak consensus with urgent/emergent urgency
        if consensus_strength in ("weak", "split") and urgency in ("urgent", "emergent"):
            rec = self._rule_weak_consensus_urgent(
                consensus_confidence, urgency, consensus_diagnosis, dissenting_count
            )
            if rec:
                escalations.append(rec)

        # Rule 2: Split consensus (3+ diagnoses competing)
        if consensus_strength == "split":
            rec = self._rule_split_consensus(num_opinions, dissenting_count)
            if rec:
                escalations.append(rec)

        # Rule 3: No consensus reached at all
        if consensus_diagnosis is None:
            rec = self._rule_no_consensus(num_opinions)
            if rec:
                escalations.append(rec)

        # Rule 4: Low confidence with high urgency
        if consensus_confidence < 0.5 and urgency in ("urgent", "emergent"):
            rec = self._rule_confidence_low_urgency_high(
                consensus_confidence, urgency, consensus_diagnosis
            )
            if rec:
                escalations.append(rec)

        return escalations

    def evaluate_specialist_divergence(
        self,
        main_consensus: Optional[str],
        specialist_consensus: Optional[str],
        specialty: str,
        specialist_confidence: float,
    ) -> Optional[EscalationRecommendation]:
        """
        Evaluate if specialist council contradicts main council.

        Args:
            main_consensus: Main council's consensus diagnosis
            specialist_consensus: Specialist council's consensus diagnosis
            specialty: Name of specialist council (e.g., "cardiology")
            specialist_confidence: Specialist confidence score

        Returns:
            EscalationRecommendation if specialist diverges significantly
        """
        return self._rule_specialist_divergence(
            main_consensus, specialist_consensus, specialty, specialist_confidence
        )

    def evaluate_rare_diagnosis(
        self,
        rare_diagnoses: list[str],
        consensus_diagnosis: Optional[str],
        num_confirmatory_tests_available: int,
    ) -> Optional[EscalationRecommendation]:
        """
        Evaluate if rare diagnoses are on the table without confirmation.

        Args:
            rare_diagnoses: List of rare diagnoses from PubMed
            consensus_diagnosis: Main consensus diagnosis
            num_confirmatory_tests_available: Number of available confirmatory tests

        Returns:
            EscalationRecommendation if rare diagnosis lacks confirmation
        """
        return self._rule_rare_diagnosis_unconfirmed(
            rare_diagnoses, consensus_diagnosis, num_confirmatory_tests_available
        )

    def get_recommendation(self, rule_id: str, reason: str) -> EscalationRecommendation:
        """
        Get a recommendation for a specific escalation rule.

        Args:
            rule_id: The rule ID that triggered
            reason: Contextual reason for the escalation

        Returns:
            EscalationRecommendation with actionable guidance
        """
        recommendations = {
            EscalationRuleId.WEAK_CONSENSUS_URGENT: EscalationRecommendation(
                rule_id=rule_id,
                severity=EscalationSeverity.CRITICAL,
                reason=reason,
                recommended_action="ESCALATE to physician urgently. Low agreement among AI analysts on urgent case.",
                suggested_specialists=["internal_medicine", "relevant_specialty"],
            ),
            EscalationRuleId.SPLIT_CONSENSUS: EscalationRecommendation(
                rule_id=rule_id,
                severity=EscalationSeverity.WARNING,
                reason=reason,
                recommended_action="FLAG for physician review. AI council unable to reach clear majority consensus.",
                suggested_specialists=["relevant_specialty"],
            ),
            EscalationRuleId.SPECIALIST_DIVERGENCE: EscalationRecommendation(
                rule_id=rule_id,
                severity=EscalationSeverity.WARNING,
                reason=reason,
                recommended_action="FLAG for physician review. Specialist council contradicts main council consensus.",
                suggested_specialists=["relevant_specialty"],
            ),
            EscalationRuleId.NO_CONSENSUS: EscalationRecommendation(
                rule_id=rule_id,
                severity=EscalationSeverity.CRITICAL,
                reason=reason,
                recommended_action="ESCALATE to physician. No clear diagnosis reached despite analysis.",
                suggested_specialists=["internal_medicine"],
            ),
            EscalationRuleId.CONFIDENCE_LOW_URGENCY_HIGH: EscalationRecommendation(
                rule_id=rule_id,
                severity=EscalationSeverity.CRITICAL,
                reason=reason,
                recommended_action="ESCALATE to physician immediately. High urgency case with low diagnostic confidence.",
                suggested_specialists=["relevant_specialty", "emergency_medicine"],
            ),
            EscalationRuleId.RARE_DIAGNOSIS_UNCONFIRMED: EscalationRecommendation(
                rule_id=rule_id,
                severity=EscalationSeverity.WARNING,
                reason=reason,
                recommended_action="FLAG for physician review. Rare diagnosis candidate identified but lacks confirmatory testing.",
                suggested_specialists=["relevant_specialty"],
            ),
        }
        return recommendations.get(
            rule_id,
            EscalationRecommendation(
                rule_id=rule_id,
                severity=EscalationSeverity.WARNING,
                reason=reason,
                recommended_action="Review case for clinical context.",
                suggested_specialists=[],
            ),
        )

    # ────────────────────────────────────────────────────────────────────────────────
    # Rule implementations
    # ────────────────────────────────────────────────────────────────────────────────

    def _rule_weak_consensus_urgent(
        self,
        consensus_confidence: float,
        urgency: str,
        consensus_diagnosis: Optional[str],
        dissenting_count: int,
    ) -> Optional[EscalationRecommendation]:
        """Weak consensus with urgent/emergent urgency → ESCALATE."""
        if consensus_confidence < 0.6 and urgency in ("urgent", "emergent"):
            return EscalationRecommendation(
                rule_id=EscalationRuleId.WEAK_CONSENSUS_URGENT,
                severity=EscalationSeverity.CRITICAL,
                reason=f"Weak consensus ({consensus_confidence:.0%}) on {urgency} case. "
                       f"{dissenting_count} dissenting opinion(s) on '{consensus_diagnosis}'.",
                recommended_action="ESCALATE to physician urgently. Recommend second opinion or specialist consultation.",
                suggested_specialists=["emergency_medicine", "relevant_specialty"],
            )
        return None

    def _rule_split_consensus(
        self,
        num_opinions: int,
        dissenting_count: int,
    ) -> Optional[EscalationRecommendation]:
        """Split consensus (3+ diagnoses competing) → FLAG."""
        if dissenting_count > 2:  # Implies multiple competing diagnoses
            return EscalationRecommendation(
                rule_id=EscalationRuleId.SPLIT_CONSENSUS,
                severity=EscalationSeverity.WARNING,
                reason=f"Split consensus: {dissenting_count} dissenting opinions across {num_opinions} analyses.",
                recommended_action="FLAG for physician review. Recommend specialist consultation to break tie.",
                suggested_specialists=["relevant_specialty"],
            )
        return None

    def _rule_specialist_divergence(
        self,
        main_consensus: Optional[str],
        specialist_consensus: Optional[str],
        specialty: str,
        specialist_confidence: float,
    ) -> Optional[EscalationRecommendation]:
        """Specialist contradicts main council → FLAG."""
        if (
            main_consensus is not None
            and specialist_consensus is not None
            and main_consensus.lower() != specialist_consensus.lower()
        ):
            return EscalationRecommendation(
                rule_id=EscalationRuleId.SPECIALIST_DIVERGENCE,
                severity=EscalationSeverity.WARNING,
                reason=f"{specialty.title()} specialist suggested '{specialist_consensus}' "
                       f"(confidence: {specialist_confidence:.0%}) vs main council '{main_consensus}'.",
                recommended_action="FLAG for physician review. Specialist opinion differs from primary assessment.",
                suggested_specialists=[specialty],
            )
        return None

    def _rule_no_consensus(
        self,
        num_opinions: int,
    ) -> Optional[EscalationRecommendation]:
        """No consensus reached → ESCALATE."""
        return EscalationRecommendation(
            rule_id=EscalationRuleId.NO_CONSENSUS,
            severity=EscalationSeverity.CRITICAL,
            reason=f"No consensus reached after {num_opinions} independent analyses.",
            recommended_action="ESCALATE to physician. Unable to identify leading diagnosis; recommend comprehensive reassessment.",
            suggested_specialists=["internal_medicine"],
        )

    def _rule_confidence_low_urgency_high(
        self,
        consensus_confidence: float,
        urgency: str,
        consensus_diagnosis: Optional[str],
    ) -> Optional[EscalationRecommendation]:
        """Low confidence with high urgency → ESCALATE."""
        if consensus_confidence < 0.5 and urgency in ("urgent", "emergent"):
            return EscalationRecommendation(
                rule_id=EscalationRuleId.CONFIDENCE_LOW_URGENCY_HIGH,
                severity=EscalationSeverity.CRITICAL,
                reason=f"Low confidence ({consensus_confidence:.0%}) on {urgency} case. "
                       f"Suggested diagnosis: '{consensus_diagnosis}'.",
                recommended_action="ESCALATE to physician immediately. Recommend urgent physician assessment and possible specialist consultation.",
                suggested_specialists=["emergency_medicine", "relevant_specialty"],
            )
        return None

    def _rule_rare_diagnosis_unconfirmed(
        self,
        rare_diagnoses: list[str],
        consensus_diagnosis: Optional[str],
        num_confirmatory_tests_available: int,
    ) -> Optional[EscalationRecommendation]:
        """Rare diagnoses on table without confirmation → FLAG."""
        if rare_diagnoses and num_confirmatory_tests_available == 0:
            rare_list = ", ".join(rare_diagnoses[:3])  # Show top 3
            return EscalationRecommendation(
                rule_id=EscalationRuleId.RARE_DIAGNOSIS_UNCONFIRMED,
                severity=EscalationSeverity.WARNING,
                reason=f"Rare diagnoses identified ({rare_list}) but no confirmatory tests available. "
                       f"Main consensus: '{consensus_diagnosis}'.",
                recommended_action="FLAG for physician review. Consider rare disease diagnostic pathway and specialist referral.",
                suggested_specialists=["relevant_specialty"],
            )
        return None


# Singleton instance
_engine: Optional[EscalationRulesEngine] = None


def get_escalation_service() -> EscalationRulesEngine:
    """Get or create the EscalationRulesEngine singleton."""
    global _engine
    if _engine is None:
        _engine = EscalationRulesEngine()
    return _engine
