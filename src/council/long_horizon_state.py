"""
Extended state schema for long-horizon agentic diagnostic council workflows.

Builds on CouncilState by adding:
- Workflow persistence (workflow_id, branch_id, checkpoint stack)
- Decision trail (audit log of decisions + evidence sources)
- Escalation flags (when to escalate weak consensus)
- Specialist findings (outputs from sub-council deliberations)
- Evidence source tracking (which APIs were accessed, caching)
- Human override tracking (physician intervention history)
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Literal
from typing_extensions import TypedDict


@dataclass
class CheckpointEntry:
    """Represents a completed node in the workflow execution path."""
    node_name: str
    timestamp: datetime
    state_snapshot: dict  # Full state after this node
    result: dict  # Specific node output


@dataclass
class DecisionTrailEvent:
    """Audit log entry for a decision point in the workflow."""
    event_id: str
    timestamp: datetime
    node_name: str
    action: str  # e.g., "consensus_calculated", "specialist_routed", "escalated"
    evidence_sources: list[str]  # ["pubmed", "hpo", "mesh", "wiley", "news_rss"]
    reasoning: str
    consensus_before: str | None
    consensus_after: str | None
    metadata: dict = field(default_factory=dict)


@dataclass
class EscalationFlag:
    """Flag indicating when consensus warrants escalation."""
    flag_id: str
    timestamp: datetime
    rule_id: str  # e.g., "weak_consensus_urgent", "split_consensus"
    severity: Literal["critical", "warning"]
    reason: str
    actionable_recommendation: str


@dataclass
class SpecialistFinding:
    """Output from a specialist sub-council deliberation."""
    specialty: str  # "cardiology", "rheumatology", "neurology", "infectious_disease"
    consensus_diagnosis: str | None
    confidence: float
    reasoning: str
    differential_diagnoses: list[str]
    aligned_with_main: bool  # True if specialist agrees with main council
    evidence_sources: list[str]


@dataclass
class HumanOverride:
    """Record of physician override intervention."""
    timestamp: datetime
    physician_id: str
    action: Literal["exclude_diagnosis", "promote_diagnosis", "request_reeval", "accept"]
    target_diagnosis: str | None
    rationale: str
    triggered_reeval: bool


class LongHorizonCouncilState(TypedDict):
    """Extended state for long-horizon workflow with checkpointing and persistence."""

    # ────────────────────────────────────────────────────────────────────────────────
    # Original CouncilState fields (preserved for compatibility)
    # ────────────────────────────────────────────────────────────────────────────────
    case_info: dict  # {symptoms, patient_history, imaging_findings, vitals}
    num_rollouts: int
    mode: Literal["standard", "iterative"]

    # RAG context compression
    raw_note: str
    retrieved_context: str

    # Round-1 fan-out accumulator
    opinions: Annotated[list[dict], operator.add]

    # Round-1 results
    consensus_diagnosis: str | None
    consensus_strength: str
    consensus_confidence: float
    discussion_summary: str
    minority_challenge: str

    # PubMed results
    pubmed_insights: dict
    rare_diagnoses: list[str]

    # Round-2 fan-out accumulator
    r2_opinions: Annotated[list[dict], operator.add]

    # Round-2 results
    r2_consensus_diagnosis: str | None
    r2_consensus_strength: str
    r2_consensus_confidence: float
    r2_discussion_summary: str

    # ────────────────────────────────────────────────────────────────────────────────
    # NEW: Workflow persistence & long-horizon fields
    # ────────────────────────────────────────────────────────────────────────────────

    # Unique identifiers for workflow tracking
    workflow_id: str  # Persists across checkpoints; format: WORKFLOW-{patient_id}-{timestamp}
    branch_id: str | None  # For re-deliberations: e.g., "re_deliberate_v2"; None for main branch
    created_by: str  # User ID / physician ID who initiated workflow

    # Checkpoint and resumption tracking
    checkpoint_stack: Annotated[list[CheckpointEntry], operator.add]  # List of completed nodes
    last_checkpoint_node: str  # Name of the last node that was persisted
    is_resuming: bool  # True if this invocation is resuming from earlier checkpoint

    # Decision audit trail
    decision_trail: Annotated[list[DecisionTrailEvent], operator.add]  # Timestamped events

    # Escalation tracking
    escalation_flags: Annotated[list[EscalationFlag], operator.add]

    # Specialist sub-council results
    specialist_findings: dict[str, SpecialistFinding]  # keyed by specialty name
    specialist_routing_applied: bool  # True if specialist councils were consulted

    # Evidence source tracking (for bias mitigation & re-fetch prevention)
    evidence_sources_used: set[str]  # {"pubmed", "hpo", "mesh", "wiley", "news_rss", ...}
    evidence_cache_keys: dict[str, str]  # Mapping of source → cache key for re-fetch prevention

    # Human override tracking
    human_override: HumanOverride | None  # Most recent physician intervention, if any
    override_history: Annotated[list[HumanOverride], operator.add]  # All past overrides

    # Timing metadata
    workflow_start_time: datetime
    workflow_last_update: datetime
    estimated_completion_time: datetime | None


class LongHorizonCouncilStateMinimal(TypedDict, total=False):
    """Minimal required fields for workflow initialization."""
    workflow_id: str
    branch_id: str | None
    created_by: str
    workflow_start_time: datetime
    evidence_sources_used: set[str]
    checkpoint_stack: Annotated[list[CheckpointEntry], operator.add]
    decision_trail: Annotated[list[DecisionTrailEvent], operator.add]
    escalation_flags: Annotated[list[EscalationFlag], operator.add]


def extend_council_state_to_long_horizon(
    council_state: dict,
    workflow_id: str,
    created_by: str,
    branch_id: str | None = None,
) -> LongHorizonCouncilState:
    """
    Convert a standard CouncilState dict into a LongHorizonCouncilState.

    Args:
        council_state: Original CouncilState dict
        workflow_id: Unique workflow identifier
        created_by: User/physician ID who initiated
        branch_id: Optional branch identifier for re-deliberations

    Returns:
        Extended state with all new long-horizon fields initialized
    """
    now = datetime.utcnow()

    return {
        # Keep all original fields
        **council_state,

        # Add new long-horizon fields
        "workflow_id": workflow_id,
        "branch_id": branch_id,
        "created_by": created_by,
        "checkpoint_stack": [],
        "last_checkpoint_node": "initialize",
        "is_resuming": False,
        "decision_trail": [],
        "escalation_flags": [],
        "specialist_findings": {},
        "specialist_routing_applied": False,
        "evidence_sources_used": set(),
        "evidence_cache_keys": {},
        "human_override": None,
        "override_history": [],
        "workflow_start_time": now,
        "workflow_last_update": now,
        "estimated_completion_time": None,
    }


def serialize_long_horizon_state(state: LongHorizonCouncilState) -> dict:
    """
    Serialize long-horizon state to JSON-compatible dict for Firestore storage.
    Handles non-JSON types (datetime, sets, dataclasses).
    """
    def serialize_value(v):
        if isinstance(v, datetime):
            return v.isoformat()
        elif isinstance(v, set):
            return list(v)
        elif isinstance(v, CheckpointEntry):
            return {
                "node_name": v.node_name,
                "timestamp": v.timestamp.isoformat(),
                "state_snapshot": serialize_value(v.state_snapshot),
                "result": serialize_value(v.result),
            }
        elif isinstance(v, DecisionTrailEvent):
            return {
                "event_id": v.event_id,
                "timestamp": v.timestamp.isoformat(),
                "node_name": v.node_name,
                "action": v.action,
                "evidence_sources": v.evidence_sources,
                "reasoning": v.reasoning,
                "consensus_before": v.consensus_before,
                "consensus_after": v.consensus_after,
                "metadata": v.metadata,
            }
        elif isinstance(v, EscalationFlag):
            return {
                "flag_id": v.flag_id,
                "timestamp": v.timestamp.isoformat(),
                "rule_id": v.rule_id,
                "severity": v.severity,
                "reason": v.reason,
                "actionable_recommendation": v.actionable_recommendation,
            }
        elif isinstance(v, SpecialistFinding):
            return {
                "specialty": v.specialty,
                "consensus_diagnosis": v.consensus_diagnosis,
                "confidence": v.confidence,
                "reasoning": v.reasoning,
                "differential_diagnoses": v.differential_diagnoses,
                "aligned_with_main": v.aligned_with_main,
                "evidence_sources": v.evidence_sources,
            }
        elif isinstance(v, HumanOverride):
            return {
                "timestamp": v.timestamp.isoformat(),
                "physician_id": v.physician_id,
                "action": v.action,
                "target_diagnosis": v.target_diagnosis,
                "rationale": v.rationale,
                "triggered_reeval": v.triggered_reeval,
            }
        elif isinstance(v, dict):
            return {k: serialize_value(val) for k, val in v.items()}
        elif isinstance(v, list):
            return [serialize_value(item) for item in v]
        else:
            return v

    return serialize_value(state)


def deserialize_long_horizon_state(data: dict) -> LongHorizonCouncilState:
    """
    Deserialize long-horizon state from Firestore dict.
    Reconstructs datetime, sets, and dataclass objects.
    """
    def deserialize_value(v, field_hint=None):
        if isinstance(v, str) and field_hint in ("datetime", "timestamp"):
            return datetime.fromisoformat(v)
        elif isinstance(v, str) and field_hint == "set":
            return set()  # Restored as empty set; list items will be added by caller
        elif isinstance(v, dict):
            if "event_id" in v and "node_name" in v and "action" in v:
                return DecisionTrailEvent(
                    event_id=v["event_id"],
                    timestamp=datetime.fromisoformat(v["timestamp"]),
                    node_name=v["node_name"],
                    action=v["action"],
                    evidence_sources=v.get("evidence_sources", []),
                    reasoning=v.get("reasoning", ""),
                    consensus_before=v.get("consensus_before"),
                    consensus_after=v.get("consensus_after"),
                    metadata=v.get("metadata", {}),
                )
            elif "specialty" in v and "consensus_diagnosis" in v:
                return SpecialistFinding(
                    specialty=v["specialty"],
                    consensus_diagnosis=v.get("consensus_diagnosis"),
                    confidence=v.get("confidence", 0.0),
                    reasoning=v.get("reasoning", ""),
                    differential_diagnoses=v.get("differential_diagnoses", []),
                    aligned_with_main=v.get("aligned_with_main", False),
                    evidence_sources=v.get("evidence_sources", []),
                )
            else:
                return {k: deserialize_value(val) for k, val in v.items()}
        elif isinstance(v, list):
            return [deserialize_value(item) for item in v]
        else:
            return v

    return deserialize_value(data)
