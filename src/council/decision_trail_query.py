"""
Decision Trail Query System

Provides search, filtering, and analysis capabilities for decision trails.
Allows physicians to analyze diagnostic evolution, track evidence sources,
and understand reasoning behind consensus decisions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Callable, Any

from .workflow_store import get_workflow_store, WorkflowStore
from .decision_trail import get_decision_trail_recorder

logger = logging.getLogger(__name__)


@dataclass
class DecisionTrailFilter:
    """Filter criteria for decision trail queries."""
    action_type: Optional[str] = None  # e.g., "consensus_calculated", "specialist_consultation"
    node_name: Optional[str] = None  # e.g., "calculate_consensus", "invoke_specialist"
    min_timestamp: Optional[datetime] = None
    max_timestamp: Optional[datetime] = None
    evidence_source: Optional[str] = None  # Filter by specific evidence source
    consensus_before: Optional[str] = None
    consensus_after: Optional[str] = None


class DecisionTrailQuery:
    """
    Query and analyze decision trails for a workflow.

    Supports:
    - Full-text search on reasoning
    - Filtering by action type, node, time range
    - Consensus evolution tracking
    - Evidence source analysis
    - Diagnostic hypothesis tracking
    """

    def __init__(self, store: Optional[WorkflowStore] = None):
        """
        Initialize the query system.

        Args:
            store: WorkflowStore instance
        """
        self.store = store or get_workflow_store()

    def get_decision_trail(
        self,
        workflow_id: str,
        filter_: Optional[DecisionTrailFilter] = None,
    ) -> list[dict]:
        """
        Get and filter decision trail events.

        Args:
            workflow_id: Workflow ID
            filter_: Optional filter criteria

        Returns:
            List of decision trail events
        """
        trail = self.store.get_decision_trail(workflow_id)
        if not trail:
            return []

        if not filter_:
            return trail

        # Apply filters
        filtered = trail

        if filter_.action_type:
            filtered = [
                e for e in filtered
                if e.get("action") == filter_.action_type
            ]

        if filter_.node_name:
            filtered = [
                e for e in filtered
                if e.get("node_name") == filter_.node_name
            ]

        if filter_.min_timestamp:
            filtered = [
                e for e in filtered
                if self._parse_timestamp(e.get("timestamp")) >= filter_.min_timestamp
            ]

        if filter_.max_timestamp:
            filtered = [
                e for e in filtered
                if self._parse_timestamp(e.get("timestamp")) <= filter_.max_timestamp
            ]

        if filter_.consensus_after:
            filtered = [
                e for e in filtered
                if e.get("consensus_after") == filter_.consensus_after
            ]

        return filtered

    def search_reasoning(self, workflow_id: str, query: str) -> list[dict]:
        """
        Search decision trail for reasoning containing query terms.

        Case-insensitive substring search on reasoning field.

        Args:
            workflow_id: Workflow ID
            query: Search query

        Returns:
            Matching decision trail events
        """
        trail = self.store.get_decision_trail(workflow_id)
        query_lower = query.lower()

        matches = [
            event for event in trail
            if query_lower in event.get("reasoning", "").lower()
        ]

        logger.info(f"Found {len(matches)} matches for '{query}' in {workflow_id}")
        return matches

    def get_consensus_evolution(self, workflow_id: str) -> list[dict]:
        """
        Track how consensus diagnosis changed over time.

        Returns:
            List of (timestamp, old_diagnosis, new_diagnosis, action)
        """
        trail = self.store.get_decision_trail(workflow_id)

        evolution = []
        last_diagnosis = None

        for event in trail:
            new_diagnosis = event.get("consensus_after")
            if new_diagnosis and new_diagnosis != last_diagnosis:
                evolution.append({
                    "timestamp": event.get("timestamp"),
                    "old_diagnosis": last_diagnosis,
                    "new_diagnosis": new_diagnosis,
                    "action": event.get("action"),
                    "reasoning": event.get("reasoning"),
                    "node": event.get("node_name"),
                })
                last_diagnosis = new_diagnosis

        return evolution

    def get_specialist_consultations(self, workflow_id: str) -> list[dict]:
        """
        Extract all specialist consultation events from trail.

        Returns:
            List of specialist findings with alignment status
        """
        trail = self.store.get_decision_trail(workflow_id)

        consultations = [
            {
                "timestamp": event.get("timestamp"),
                "specialist": event.get("metadata", {}).get("specialty"),
                "diagnosis": event.get("consensus_after"),
                "confidence": event.get("metadata", {}).get("confidence"),
                "aligned_with_main": event.get("metadata", {}).get("aligned_with_main"),
                "reasoning": event.get("reasoning"),
            }
            for event in trail
            if event.get("action") in ["specialist_aligned", "specialist_diverged"]
        ]

        aligned = sum(1 for c in consultations if c["aligned_with_main"])
        diverged = sum(1 for c in consultations if not c["aligned_with_main"])

        logger.info(f"Specialist consultations: {aligned} aligned, {diverged} diverged")

        return consultations

    def get_evidence_sources_used(self, workflow_id: str) -> dict:
        """
        Aggregate all evidence sources used in decision making.

        Returns:
            {
                "sources": {source_name: count},
                "by_action": {action_type: [sources]},
                "total_sources": int,
            }
        """
        trail = self.store.get_decision_trail(workflow_id)

        all_sources = {}
        by_action = {}

        for event in trail:
            sources = event.get("evidence_sources", [])
            for source in sources:
                all_sources[source] = all_sources.get(source, 0) + 1

            action = event.get("action")
            if action not in by_action:
                by_action[action] = []
            by_action[action].extend(sources)

        # Deduplicate within actions
        by_action = {k: list(set(v)) for k, v in by_action.items()}

        return {
            "sources": all_sources,
            "by_action": by_action,
            "total_sources": sum(all_sources.values()),
            "unique_sources": len(all_sources),
        }

    def get_escalation_history(self, workflow_id: str) -> list[dict]:
        """
        Get all escalation events for a workflow.

        Returns:
            List of escalation events with severity and reasoning
        """
        trail = self.store.get_decision_trail(workflow_id)

        escalations = [
            {
                "timestamp": event.get("timestamp"),
                "severity": event.get("metadata", {}).get("severity"),
                "rule_id": event.get("metadata", {}).get("rule_id"),
                "reason": event.get("reasoning"),
                "recommended_action": event.get("metadata", {}).get("recommended_action"),
            }
            for event in trail
            if event.get("action") == "escalated"
        ]

        return escalations

    def get_physician_actions(self, workflow_id: str) -> list[dict]:
        """
        Get all physician interventions in decision trail.

        Returns:
            List of physician actions (requests, overrides, etc.)
        """
        trail = self.store.get_decision_trail(workflow_id)

        actions = [
            {
                "timestamp": event.get("timestamp"),
                "action_type": event.get("action"),
                "physician_id": event.get("metadata", {}).get("physician_id"),
                "reason": event.get("reasoning"),
            }
            for event in trail
            if event.get("action") in ["re_evaluation_requested", "overridden", "physician_override"]
        ]

        return actions

    def generate_diagnostic_narrative(self, workflow_id: str) -> str:
        """
        Generate human-readable narrative of diagnostic process.

        Returns:
            Narrative text describing the diagnostic journey
        """
        trail = self.store.get_decision_trail(workflow_id)
        evolution = self.get_consensus_evolution(workflow_id)
        specialists = self.get_specialist_consultations(workflow_id)
        escalations = self.get_escalation_history(workflow_id)

        lines = [
            f"Diagnostic Decision Trail for Workflow: {workflow_id}\n",
            "=" * 70,
        ]

        if not trail:
            return "\n".join(lines) + "\n\nNo decision events recorded."

        # Initial consensus
        if evolution:
            first = evolution[0]
            lines.append(f"\nInitial Diagnosis: {first['new_diagnosis']}")
            lines.append(f"Reasoning: {first['reasoning'][:100]}...")

        # Specialist consultations
        if specialists:
            lines.append(f"\nSpecialist Consultations ({len(specialists)}):")
            for spec in specialists:
                alignment = "✓ Aligned" if spec["aligned_with_main"] else "✗ Diverged"
                lines.append(
                    f"  - {spec['specialist']}: {spec['diagnosis']} "
                    f"({spec['confidence']:.0%}) {alignment}"
                )

        # Consensus evolution
        if len(evolution) > 1:
            lines.append("\nDiagnostic Evolution:")
            for i, event in enumerate(evolution[1:], 1):
                lines.append(
                    f"  [{i}] {event['old_diagnosis']} → {event['new_diagnosis']}"
                )
                lines.append(f"      Reason: {event['reasoning'][:80]}...")

        # Escalations
        if escalations:
            lines.append(f"\nEscalations ({len(escalations)}):")
            for esc in escalations:
                lines.append(f"  - [{esc['severity']}] {esc['reason']}")

        # Evidence summary
        sources = self.get_evidence_sources_used(workflow_id)
        if sources["sources"]:
            lines.append(f"\nEvidence Sources ({sources['unique_sources']}):")
            for source, count in sorted(
                sources["sources"].items(),
                key=lambda x: x[1],
                reverse=True,
            ):
                lines.append(f"  - {source}: {count} citation(s)")

        return "\n".join(lines)

    def get_decision_timeline(self, workflow_id: str) -> dict:
        """
        Get a timeline view of all events.

        Returns:
            {
                "start_time": timestamp,
                "end_time": timestamp,
                "duration_seconds": int,
                "events_by_minute": {minute: [events]},
            }
        """
        trail = self.store.get_decision_trail(workflow_id)
        if not trail:
            return {
                "start_time": None,
                "end_time": None,
                "duration_seconds": 0,
                "events_by_minute": {},
            }

        timestamps = [self._parse_timestamp(e.get("timestamp")) for e in trail if e.get("timestamp")]
        if not timestamps:
            return {
                "start_time": None,
                "end_time": None,
                "duration_seconds": 0,
                "events_by_minute": {},
            }

        start_time = min(timestamps)
        end_time = max(timestamps)
        duration = (end_time - start_time).total_seconds()

        # Bin events by minute
        events_by_minute = {}
        for event in trail:
            ts = self._parse_timestamp(event.get("timestamp"))
            if ts:
                minute = int((ts - start_time).total_seconds() // 60)
                if minute not in events_by_minute:
                    events_by_minute[minute] = []
                events_by_minute[minute].append({
                    "action": event.get("action"),
                    "reasoning": event.get("reasoning")[:50] if event.get("reasoning") else "",
                })

        return {
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": int(duration),
            "event_count": len(trail),
            "events_by_minute": events_by_minute,
        }

    @staticmethod
    def _parse_timestamp(timestamp_str: str | datetime) -> datetime:
        """Parse timestamp string to datetime object."""
        if isinstance(timestamp_str, datetime):
            return timestamp_str
        if isinstance(timestamp_str, str):
            try:
                return datetime.fromisoformat(timestamp_str)
            except (ValueError, TypeError):
                return datetime.utcnow()
        return datetime.utcnow()


# Singleton instance
_query_system: Optional[DecisionTrailQuery] = None


def get_decision_trail_query(store: Optional[WorkflowStore] = None) -> DecisionTrailQuery:
    """Get or create the decision trail query system singleton."""
    global _query_system
    if _query_system is None:
        _query_system = DecisionTrailQuery(store=store)
    return _query_system
