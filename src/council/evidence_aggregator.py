"""
Multi-Source Evidence Aggregator for Decision Support

Tracks evidence sources (PubMed, OpenWiley, EHR observations, specialist opinions)
and assigns reliability/bias weights. Provides evidence weighting and bias mitigation
for consensus decisions.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Literal

logger = logging.getLogger(__name__)


class EvidenceSource(str, Enum):
    """Evidence source types."""
    PUBMED_CASE_REPORTS = "pubmed:case_reports"
    PUBMED_SYSTEMATIC_REVIEWS = "pubmed:systematic_reviews"
    PUBMED_RCT = "pubmed:rct"
    EHR_LABORATORY = "ehr:laboratory"
    EHR_IMAGING = "ehr:imaging"
    EHR_VITALS = "ehr:vitals"
    EHR_CLINICAL_NOTE = "ehr:clinical_note"
    SPECIALIST_OPINION = "specialist:opinion"
    PHYSICIAN_ASSESSMENT = "physician:assessment"
    CLINICAL_TRIAL = "clinical:trial"
    TEXTBOOK_REFERENCE = "textbook:reference"


class ReliabilityTier(str, Enum):
    """Evidence reliability tiers (GRADE methodology)."""
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    VERY_LOW = "very_low"


@dataclass
class EvidenceItem:
    """Single piece of evidence with metadata."""
    evidence_id: str
    source: EvidenceSource
    content: str  # Citation, finding, or observation
    reliability_tier: ReliabilityTier
    bias_score: float  # 0.0 (no bias) to 1.0 (high bias)
    confidence_boost: float  # 0.0 to 1.0: how much to boost consensus confidence
    timestamp: str  # ISO 8601
    metadata: dict = field(default_factory=dict)

    def reliability_weight(self) -> float:
        """Calculate normalized reliability weight (0-1)."""
        tier_weights = {
            ReliabilityTier.HIGH: 1.0,
            ReliabilityTier.MODERATE: 0.7,
            ReliabilityTier.LOW: 0.4,
            ReliabilityTier.VERY_LOW: 0.1,
        }
        # Adjust by bias (reduce if biased)
        base_weight = tier_weights[self.reliability_tier]
        bias_reduction = self.bias_score * 0.3  # Bias reduces weight by up to 30%
        return max(0.0, base_weight - bias_reduction)


class EvidenceAggregator:
    """
    Aggregates evidence from multiple sources for a workflow.

    Tracks source reliability, bias, and provides weighted consensus
    calculations that account for evidence quality.
    """

    def __init__(self):
        """Initialize the evidence aggregator."""
        self.evidence_store: dict[str, list[EvidenceItem]] = {}

    def add_evidence(
        self,
        workflow_id: str,
        source: EvidenceSource,
        content: str,
        reliability_tier: ReliabilityTier = ReliabilityTier.MODERATE,
        bias_score: float = 0.0,
        confidence_boost: float = 0.5,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Add evidence item to the store.

        Args:
            workflow_id: Workflow identifier
            source: Evidence source type
            content: Evidence content (citation, finding, etc.)
            reliability_tier: GRADE reliability classification
            bias_score: 0.0 (no bias) to 1.0 (high bias)
            confidence_boost: 0.0 to 1.0
            metadata: Optional additional metadata

        Returns:
            Evidence ID
        """
        import uuid
        from datetime import datetime

        evidence_id = f"evidence_{uuid.uuid4().hex[:8]}"
        item = EvidenceItem(
            evidence_id=evidence_id,
            source=source,
            content=content,
            reliability_tier=reliability_tier,
            bias_score=max(0.0, min(1.0, bias_score)),  # Clamp to [0, 1]
            confidence_boost=max(0.0, min(1.0, confidence_boost)),
            timestamp=datetime.utcnow().isoformat(),
            metadata=metadata or {},
        )

        if workflow_id not in self.evidence_store:
            self.evidence_store[workflow_id] = []

        self.evidence_store[workflow_id].append(item)
        logger.info(
            f"Added evidence {evidence_id} for {workflow_id}: "
            f"{source} [{reliability_tier}]"
        )
        return evidence_id

    def get_evidence_for_workflow(
        self,
        workflow_id: str,
        source_filter: Optional[EvidenceSource] = None,
        include_bias: bool = False,
    ) -> list[EvidenceItem]:
        """
        Get evidence items for a workflow.

        Args:
            workflow_id: Workflow identifier
            source_filter: Optional source type filter
            include_bias: Include high-bias evidence (if False, filter out)

        Returns:
            List of evidence items
        """
        evidence = self.evidence_store.get(workflow_id, [])

        if source_filter:
            evidence = [e for e in evidence if e.source == source_filter]

        if not include_bias:
            evidence = [e for e in evidence if e.bias_score < 0.5]

        return evidence

    def calculate_evidence_weighted_confidence(
        self,
        workflow_id: str,
        base_confidence: float,
    ) -> tuple[float, dict]:
        """
        Calculate confidence adjustment based on evidence quality.

        Args:
            workflow_id: Workflow identifier
            base_confidence: Base consensus confidence (0-1)

        Returns:
            Tuple of (adjusted_confidence, adjustment_details)
        """
        evidence = self.evidence_store.get(workflow_id, [])
        if not evidence:
            return base_confidence, {
                "adjustment": 0.0,
                "reason": "No evidence items",
                "evidence_count": 0,
            }

        # Calculate average reliability weight
        avg_reliability = sum(e.reliability_weight() for e in evidence) / len(evidence)

        # Calculate bias penalty (average bias can reduce confidence)
        avg_bias = sum(e.bias_score for e in evidence) / len(evidence)
        bias_penalty = avg_bias * 0.2  # Bias reduces confidence by up to 20%

        # Calculate confidence boost from evidence
        avg_boost = sum(e.confidence_boost for e in evidence) / len(evidence)
        boost_factor = 0.1 * avg_boost  # Evidence can boost by up to 10%

        # Combine effects
        adjustment = boost_factor - bias_penalty
        adjusted_confidence = max(0.0, min(1.0, base_confidence + adjustment))

        details = {
            "base_confidence": base_confidence,
            "adjusted_confidence": adjusted_confidence,
            "adjustment": adjustment,
            "average_reliability": avg_reliability,
            "average_bias": avg_bias,
            "boost_factor": boost_factor,
            "bias_penalty": bias_penalty,
            "evidence_count": len(evidence),
            "evidence_sources": list(set(e.source.value for e in evidence)),
            "reason": f"Adjusted by {adjustment:+.1%} based on {len(evidence)} evidence item(s)",
        }

        return adjusted_confidence, details

    def get_evidence_summary(self, workflow_id: str) -> dict:
        """
        Generate comprehensive evidence summary for a workflow.

        Returns:
            {
                "total_evidence_items": int,
                "by_source": {source: count},
                "by_reliability": {tier: count},
                "high_bias_items": count,
                "average_reliability": float,
                "average_bias": float,
                "evidence_quality_score": 0-100,
            }
        """
        evidence = self.evidence_store.get(workflow_id, [])

        if not evidence:
            return {
                "total_evidence_items": 0,
                "by_source": {},
                "by_reliability": {},
                "high_bias_items": 0,
                "average_reliability": 1.0,
                "average_bias": 0.0,
                "evidence_quality_score": 0,
            }

        # Group by source
        by_source = {}
        for item in evidence:
            source = item.source.value
            by_source[source] = by_source.get(source, 0) + 1

        # Group by reliability
        by_reliability = {}
        for item in evidence:
            tier = item.reliability_tier.value
            by_reliability[tier] = by_reliability.get(tier, 0) + 1

        # Calculate metrics
        high_bias_count = sum(1 for e in evidence if e.bias_score >= 0.5)
        avg_reliability = sum(e.reliability_weight() for e in evidence) / len(evidence)
        avg_bias = sum(e.bias_score for e in evidence) / len(evidence)

        # Quality score: combination of reliability, low bias, and diversity
        quality_score = int(
            avg_reliability * 50 +  # Reliability up to 50 points
            (1 - avg_bias) * 30 +   # Low bias up to 30 points
            min(20, len(by_source) * 5)  # Source diversity up to 20 points
        )

        return {
            "total_evidence_items": len(evidence),
            "by_source": by_source,
            "by_reliability": by_reliability,
            "high_bias_items": high_bias_count,
            "average_reliability": round(avg_reliability, 2),
            "average_bias": round(avg_bias, 2),
            "evidence_quality_score": quality_score,
        }

    def detect_bias_patterns(self, workflow_id: str) -> list[dict]:
        """
        Detect potential bias patterns in the evidence.

        Returns:
            List of bias findings with recommendations
        """
        evidence = self.evidence_store.get(workflow_id, [])
        findings = []

        if not evidence:
            return []

        # Detection 1: Single source dominance
        by_source = {}
        for item in evidence:
            by_source[item.source.value] = by_source.get(item.source.value, 0) + 1

        dominant_source = max(by_source.items(), key=lambda x: x[1])[1]
        if dominant_source > len(evidence) * 0.7:  # >70% from one source
            findings.append({
                "bias_type": "source_concentration",
                "severity": "high",
                "message": f"Evidence heavily weighted toward {dominant_source} source",
                "recommendation": "Seek evidence from additional independent sources",
            })

        # Detection 2: High bias items present
        high_bias_items = [e for e in evidence if e.bias_score >= 0.7]
        if high_bias_items:
            findings.append({
                "bias_type": "high_bias_evidence",
                "severity": "medium",
                "message": f"{len(high_bias_items)} evidence item(s) with high bias (>0.7)",
                "recommendation": "De-weight or exclude high-bias items from consensus",
                "items": [e.evidence_id for e in high_bias_items],
            })

        # Detection 3: Low reliability dominance
        low_reliability = [e for e in evidence if e.reliability_tier in [
            ReliabilityTier.LOW,
            ReliabilityTier.VERY_LOW,
        ]]
        if len(low_reliability) > len(evidence) * 0.5:  # >50% low reliability
            findings.append({
                "bias_type": "low_reliability_dominance",
                "severity": "medium",
                "message": f"{len(low_reliability)} low-reliability item(s) dominate evidence",
                "recommendation": "Prioritize high-reliability evidence in consensus",
            })

        return findings

    def get_evidence_recommendations(self, workflow_id: str) -> dict:
        """
        Generate recommendations for evidence gathering.

        Returns:
            {
                "current_coverage": ["source1", "source2"],
                "missing_sources": ["source3", "source4"],
                "investigation_needed": ["topic1", "topic2"],
                "confidence_lift_opportunity": float,
            }
        """
        evidence = self.evidence_store.get(workflow_id, [])
        current_sources = set(e.source.value for e in evidence)

        # All available sources
        all_sources = set(s.value for s in EvidenceSource)
        missing_sources = list(all_sources - current_sources)

        # Quality improvements available
        quality_summary = self.get_evidence_summary(workflow_id)
        max_possible_quality = 100
        quality_lift = max_possible_quality - quality_summary["evidence_quality_score"]

        return {
            "current_coverage": sorted(list(current_sources)),
            "missing_sources": sorted(missing_sources),
            "investigation_needed": (
                ["Systematic reviews", "RCT evidence"]
                if "pubmed:rct" not in current_sources
                else []
            ),
            "confidence_lift_opportunity": quality_lift * 0.01,  # Up to 1.0
            "next_steps": _generate_next_steps(quality_summary),
        }


def _generate_next_steps(quality_summary: dict) -> list[str]:
    """Generate actionable next steps based on quality summary."""
    steps = []

    if quality_summary["evidence_quality_score"] < 50:
        steps.append("Gather more high-reliability evidence (RCTs, systematic reviews)")

    if quality_summary["high_bias_items"] > 0:
        steps.append(f"Review {quality_summary['high_bias_items']} high-bias item(s)")

    if len(quality_summary["by_source"]) < 3:
        steps.append("Consider evidence from additional independent sources")

    if quality_summary["average_reliability"] < 0.6:
        steps.append("Prioritize high-reliability evidence over low-reliability items")

    return steps if steps else ["Current evidence quality is good; proceed with confidence"]


# Singleton instance
_aggregator: Optional[EvidenceAggregator] = None


def get_evidence_aggregator() -> EvidenceAggregator:
    """Get or create the evidence aggregator singleton."""
    global _aggregator
    if _aggregator is None:
        _aggregator = EvidenceAggregator()
    return _aggregator
