"""
Decision trail auditing module for tracking diagnostic reasoning evolution.

Records:
- Consensus calculations and when they changed
- Which evidence sources were consulted
- Specialist involvement and recommendations
- Escalations and their reasons
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from .workflow_store import get_workflow_store
from .long_horizon_state import DecisionTrailEvent

logger = logging.getLogger(__name__)


class DecisionTrailRecorder:
    """Records and manages the decision trail for a workflow."""

    def __init__(self, workflow_id: str):
        """
        Initialize the decision trail recorder.

        Args:
            workflow_id: The workflow ID to record for
        """
        self.workflow_id = workflow_id
        self.store = get_workflow_store()

    def record_consensus_calculated(
        self,
        node_name: str,
        consensus_diagnosis: Optional[str],
        consensus_confidence: float,
        consensus_strength: str,
        num_opinions: int,
        num_dissenting: int,
        evidence_sources: list[str],
    ) -> str:
        """
        Record when consensus is calculated.

        Args:
            node_name: Node that calculated consensus
            consensus_diagnosis: The consensus diagnosis
            consensus_confidence: Confidence score
            consensus_strength: Strength level
            num_opinions: Total opinions
            num_dissenting: Dissenting opinions
            evidence_sources: Sources consulted for this round

        Returns:
            Event ID
        """
        event = DecisionTrailEvent(
            event_id=f"event_consensus_{node_name}_{datetime.utcnow().timestamp()}",
            timestamp=datetime.utcnow(),
            node_name=node_name,
            action="consensus_calculated",
            evidence_sources=evidence_sources,
            reasoning=(
                f"Consensus: '{consensus_diagnosis}' ({consensus_strength}) "
                f"with {consensus_confidence:.0%} confidence. "
                f"{num_opinions} opinions, {num_dissenting} dissenting."
            ),
            consensus_before=None,
            consensus_after=consensus_diagnosis,
            metadata={
                "confidence": consensus_confidence,
                "strength": consensus_strength,
                "num_opinions": num_opinions,
                "num_dissenting": num_dissenting,
            },
        )
        self.store.log_decision_event(self.workflow_id, event)
        return event.event_id

    def record_pubmed_search(
        self,
        query: str,
        rare_diagnoses_found: list[str],
        num_articles: int,
    ) -> str:
        """Record PubMed search and results."""
        event = DecisionTrailEvent(
            event_id=f"event_pubmed_{datetime.utcnow().timestamp()}",
            timestamp=datetime.utcnow(),
            node_name="run_pubmed",
            action="pubmed_search_completed",
            evidence_sources=["pubmed"],
            reasoning=(
                f"PubMed Zebra Hunt identified {len(rare_diagnoses_found)} rare diagnoses "
                f"from {num_articles} articles. Candidates: {', '.join(rare_diagnoses_found[:3])}"
            ),
            consensus_before=None,
            consensus_after=None,
            metadata={
                "query": query,
                "rare_diagnoses": rare_diagnoses_found,
                "article_count": num_articles,
            },
        )
        self.store.log_decision_event(self.workflow_id, event)
        return event.event_id

    def record_specialist_consultation(
        self,
        specialty: str,
        specialist_consensus: Optional[str],
        specialist_confidence: float,
        aligned_with_main: bool,
    ) -> str:
        """Record specialist sub-council deliberation."""
        action = "specialist_aligned" if aligned_with_main else "specialist_diverged"
        event = DecisionTrailEvent(
            event_id=f"event_specialist_{specialty}_{datetime.utcnow().timestamp()}",
            timestamp=datetime.utcnow(),
            node_name="specialist_council",
            action=action,
            evidence_sources=["specialist_" + specialty],
            reasoning=(
                f"{specialty.title()} specialist consensus: '{specialist_consensus}' "
                f"({specialist_confidence:.0%} confidence). "
                f"{'Aligns' if aligned_with_main else 'Diverges'} from main council."
            ),
            consensus_before=None,
            consensus_after=specialist_consensus,
            metadata={
                "specialty": specialty,
                "confidence": specialist_confidence,
                "aligned_with_main": aligned_with_main,
            },
        )
        self.store.log_decision_event(self.workflow_id, event)
        return event.event_id

    def record_escalation(
        self,
        rule_id: str,
        severity: str,
        reason: str,
        recommended_action: str,
    ) -> str:
        """Record escalation event."""
        event = DecisionTrailEvent(
            event_id=f"event_escalation_{rule_id}_{datetime.utcnow().timestamp()}",
            timestamp=datetime.utcnow(),
            node_name="escalation_check",
            action="escalated",
            evidence_sources=[],
            reasoning=reason,
            consensus_before=None,
            consensus_after=None,
            metadata={
                "rule_id": rule_id,
                "severity": severity,
                "recommended_action": recommended_action,
            },
        )
        self.store.log_decision_event(self.workflow_id, event)
        return event.event_id

    def record_physician_request(
        self,
        physician_id: str,
        reason: str,
    ) -> str:
        """Record physician re-evaluation request."""
        event = DecisionTrailEvent(
            event_id=f"event_physician_request_{datetime.utcnow().timestamp()}",
            timestamp=datetime.utcnow(),
            node_name="physician_input",
            action="re_evaluation_requested",
            evidence_sources=[],
            reasoning=f"Physician {physician_id} requested re-evaluation: {reason}",
            consensus_before=None,
            consensus_after=None,
            metadata={
                "physician_id": physician_id,
                "reason": reason,
            },
        )
        self.store.log_decision_event(self.workflow_id, event)
        return event.event_id

    def record_new_observation(
        self,
        observation_type: str,
        observation_data: dict,
    ) -> str:
        """Record new EHR observation that triggered re-deliberation."""
        event = DecisionTrailEvent(
            event_id=f"event_new_obs_{observation_type}_{datetime.utcnow().timestamp()}",
            timestamp=datetime.utcnow(),
            node_name="workflow_monitor",
            action="new_observation_detected",
            evidence_sources=["ehr"],
            reasoning=f"New {observation_type} observation received, triggering re-deliberation.",
            consensus_before=None,
            consensus_after=None,
            metadata={
                "observation_type": observation_type,
                "observation_summary": json.dumps(observation_data, default=str)[:200],
            },
        )
        self.store.log_decision_event(self.workflow_id, event)
        return event.event_id

    def get_full_trail(self) -> list[dict]:
        """Get complete decision trail for the workflow."""
        return self.store.get_decision_trail(self.workflow_id)

    def generate_summary(self) -> str:
        """Generate a narrative summary of the decision trail."""
        trail = self.get_full_trail()

        if not trail:
            return "No decision events recorded."

        lines = ["Decision Trail Summary:\n"]
        for event in trail:
            timestamp = event.get("timestamp", "unknown")
            action = event.get("action", "unknown")
            reasoning = event.get("reasoning", "")
            lines.append(f"• [{timestamp}] {action.upper()}: {reasoning}")

        return "\n".join(lines)


def get_decision_trail_recorder(workflow_id: str) -> DecisionTrailRecorder:
    """Get a decision trail recorder for a workflow."""
    return DecisionTrailRecorder(workflow_id)
