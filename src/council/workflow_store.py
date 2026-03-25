"""
Firestore persistence layer for long-horizon diagnostic council workflows.

Manages:
- Workflow metadata (patient_id, status, timestamps)
- Checkpoint storage and retrieval
- Decision trail audit logging
- Evidence cache (to avoid redundant API calls)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional
from dataclasses import asdict

from src.config.firebase_config import get_firestore_client, is_firebase_available
from .long_horizon_state import (
    LongHorizonCouncilState,
    CheckpointEntry,
    DecisionTrailEvent,
    EscalationFlag,
    serialize_long_horizon_state,
    deserialize_long_horizon_state,
)

logger = logging.getLogger(__name__)


class WorkflowStore:
    """Firestore-backed storage for long-horizon workflow state and audit trail."""

    def __init__(self):
        """Initialize Firestore client."""
        self.db = get_firestore_client()
        self.available = is_firebase_available()

        if not self.available:
            logger.warning("Firebase not available. Workflow storage will be in-memory only.")
            self._memory_cache: dict[str, dict] = {}  # Fallback in-memory storage

    # ────────────────────────────────────────────────────────────────────────────────
    # Workflow Metadata
    # ────────────────────────────────────────────────────────────────────────────────

    def create_workflow(
        self,
        workflow_id: str,
        patient_id: str,
        created_by: str,
        branch_id: str | None = None,
    ) -> dict:
        """
        Create a new workflow record in Firestore.

        Args:
            workflow_id: Unique workflow identifier
            patient_id: Patient ID
            created_by: User/physician ID who initiated
            branch_id: Optional branch identifier for re-deliberations

        Returns:
            Workflow metadata dict
        """
        now = datetime.utcnow()
        metadata = {
            "workflow_id": workflow_id,
            "patient_id": patient_id,
            "created_by": created_by,
            "branch_id": branch_id or "main",
            "status": "active",
            "created_at": now.isoformat(),
            "last_updated": now.isoformat(),
            "checkpoint_count": 0,
            "decision_event_count": 0,
        }

        if self.available:
            try:
                self.db.collection("workflows").document(workflow_id).set(metadata)
                logger.info(f"Workflow {workflow_id} created in Firestore")
            except Exception as e:
                logger.error(f"Failed to create workflow in Firestore: {e}")
                self._memory_cache[workflow_id] = metadata
        else:
            self._memory_cache[workflow_id] = metadata

        return metadata

    def get_workflow(self, workflow_id: str) -> Optional[dict]:
        """Fetch workflow metadata."""
        if self.available:
            try:
                doc = self.db.collection("workflows").document(workflow_id).get()
                if doc.exists:
                    return doc.to_dict()
            except Exception as e:
                logger.error(f"Failed to fetch workflow {workflow_id}: {e}")
        return self._memory_cache.get(workflow_id)

    def update_workflow_status(self, workflow_id: str, status: str) -> None:
        """Update workflow status (active, completed, failed)."""
        update_data = {
            "status": status,
            "last_updated": datetime.utcnow().isoformat(),
        }

        if self.available:
            try:
                self.db.collection("workflows").document(workflow_id).update(update_data)
            except Exception as e:
                logger.error(f"Failed to update workflow status: {e}")
        else:
            if workflow_id in self._memory_cache:
                self._memory_cache[workflow_id].update(update_data)

    # ────────────────────────────────────────────────────────────────────────────────
    # Checkpoints
    # ────────────────────────────────────────────────────────────────────────────────

    def save_checkpoint(
        self,
        workflow_id: str,
        node_name: str,
        state: LongHorizonCouncilState,
    ) -> str:
        """
        Save a state checkpoint after node execution.

        Args:
            workflow_id: Workflow identifier
            node_name: Name of node that just completed
            state: Full state snapshot

        Returns:
            Checkpoint ID
        """
        now = datetime.utcnow()
        checkpoint_id = f"checkpoint_{now.isoformat().replace(':', '-')}"

        # Serialize state for storage
        serialized_state = serialize_long_horizon_state(state)
        checkpoint_data = {
            "checkpoint_id": checkpoint_id,
            "node_name": node_name,
            "timestamp": now.isoformat(),
            "state": serialized_state,
        }

        if self.available:
            try:
                self.db.collection("workflows").document(workflow_id).collection(
                    "checkpoints"
                ).document(checkpoint_id).set(checkpoint_data)
                # Update parent workflow checkpoint count
                self.db.collection("workflows").document(workflow_id).update({
                    "checkpoint_count": self.db.field.increment(1),
                    "last_updated": now.isoformat(),
                })
                logger.info(f"Checkpoint {checkpoint_id} saved for workflow {workflow_id} at node {node_name}")
            except Exception as e:
                logger.error(f"Failed to save checkpoint: {e}")
        else:
            # In-memory storage
            if workflow_id not in self._memory_cache:
                self._memory_cache[workflow_id] = {}
            if "checkpoints" not in self._memory_cache[workflow_id]:
                self._memory_cache[workflow_id]["checkpoints"] = {}
            self._memory_cache[workflow_id]["checkpoints"][checkpoint_id] = checkpoint_data

        return checkpoint_id

    def get_latest_checkpoint(
        self,
        workflow_id: str,
    ) -> Optional[tuple[str, LongHorizonCouncilState]]:
        """
        Fetch the most recent checkpoint for a workflow.

        Returns:
            Tuple of (checkpoint_id, state) or None if no checkpoints exist
        """
        if self.available:
            try:
                docs = (
                    self.db.collection("workflows")
                    .document(workflow_id)
                    .collection("checkpoints")
                    .order_by("timestamp", direction="DESCENDING")
                    .limit(1)
                    .stream()
                )
                for doc in docs:
                    data = doc.to_dict()
                    checkpoint_id = data.get("checkpoint_id")
                    state = deserialize_long_horizon_state(data.get("state", {}))
                    return checkpoint_id, state
            except Exception as e:
                logger.error(f"Failed to fetch latest checkpoint: {e}")
        else:
            # Check memory cache
            if workflow_id in self._memory_cache and "checkpoints" in self._memory_cache[workflow_id]:
                checkpoints = self._memory_cache[workflow_id]["checkpoints"]
                if checkpoints:
                    latest = sorted(checkpoints.items(), key=lambda x: x[1]["timestamp"], reverse=True)[0]
                    return latest[0], deserialize_long_horizon_state(latest[1]["state"])

        return None

    def get_checkpoint_at_node(
        self,
        workflow_id: str,
        node_name: str,
    ) -> Optional[tuple[str, LongHorizonCouncilState]]:
        """Fetch the most recent checkpoint after a specific node."""
        if self.available:
            try:
                docs = (
                    self.db.collection("workflows")
                    .document(workflow_id)
                    .collection("checkpoints")
                    .where("node_name", "==", node_name)
                    .order_by("timestamp", direction="DESCENDING")
                    .limit(1)
                    .stream()
                )
                for doc in docs:
                    data = doc.to_dict()
                    checkpoint_id = data.get("checkpoint_id")
                    state = deserialize_long_horizon_state(data.get("state", {}))
                    return checkpoint_id, state
            except Exception as e:
                logger.error(f"Failed to fetch checkpoint at node {node_name}: {e}")
        return None

    # ────────────────────────────────────────────────────────────────────────────────
    # Decision Trail
    # ────────────────────────────────────────────────────────────────────────────────

    def log_decision_event(
        self,
        workflow_id: str,
        event: DecisionTrailEvent,
    ) -> str:
        """
        Log a decision event to the audit trail.

        Args:
            workflow_id: Workflow identifier
            event: DecisionTrailEvent to log

        Returns:
            Event ID
        """
        event_data = {
            "event_id": event.event_id,
            "timestamp": event.timestamp.isoformat(),
            "node_name": event.node_name,
            "action": event.action,
            "evidence_sources": event.evidence_sources,
            "reasoning": event.reasoning,
            "consensus_before": event.consensus_before,
            "consensus_after": event.consensus_after,
            "metadata": event.metadata,
        }

        if self.available:
            try:
                self.db.collection("workflows").document(workflow_id).collection(
                    "decision_trail"
                ).document(event.event_id).set(event_data)
                self.db.collection("workflows").document(workflow_id).update({
                    "decision_event_count": self.db.field.increment(1),
                    "last_updated": datetime.utcnow().isoformat(),
                })
                logger.info(f"Decision event {event.event_id} logged for workflow {workflow_id}")
            except Exception as e:
                logger.error(f"Failed to log decision event: {e}")
        else:
            if workflow_id not in self._memory_cache:
                self._memory_cache[workflow_id] = {}
            if "decision_trail" not in self._memory_cache[workflow_id]:
                self._memory_cache[workflow_id]["decision_trail"] = {}
            self._memory_cache[workflow_id]["decision_trail"][event.event_id] = event_data

        return event.event_id

    def get_decision_trail(self, workflow_id: str) -> list[dict]:
        """Fetch all decision events for a workflow, ordered by timestamp."""
        events = []

        if self.available:
            try:
                docs = (
                    self.db.collection("workflows")
                    .document(workflow_id)
                    .collection("decision_trail")
                    .order_by("timestamp", direction="ASCENDING")
                    .stream()
                )
                for doc in docs:
                    events.append(doc.to_dict())
            except Exception as e:
                logger.error(f"Failed to fetch decision trail: {e}")
        else:
            if workflow_id in self._memory_cache and "decision_trail" in self._memory_cache[workflow_id]:
                events = list(self._memory_cache[workflow_id]["decision_trail"].values())
                events.sort(key=lambda x: x["timestamp"])

        return events

    # ────────────────────────────────────────────────────────────────────────────────
    # Evidence Cache (to prevent redundant API calls)
    # ────────────────────────────────────────────────────────────────────────────────

    def cache_evidence(
        self,
        workflow_id: str,
        source: str,  # "pubmed", "wiley", "hpo", "mesh", etc.
        query_key: str,  # Hash of query parameters
        results: dict,
    ) -> None:
        """Cache evidence retrieval results keyed by source and query."""
        cache_data = {
            "source": source,
            "query_key": query_key,
            "results": results,
            "cached_at": datetime.utcnow().isoformat(),
        }

        if self.available:
            try:
                cache_doc_id = f"{source}_{query_key}"
                self.db.collection("workflows").document(workflow_id).collection(
                    "evidence_retrieved"
                ).document(cache_doc_id).set(cache_data)
            except Exception as e:
                logger.error(f"Failed to cache evidence: {e}")
        else:
            if workflow_id not in self._memory_cache:
                self._memory_cache[workflow_id] = {}
            if "evidence_cache" not in self._memory_cache[workflow_id]:
                self._memory_cache[workflow_id]["evidence_cache"] = {}
            self._memory_cache[workflow_id]["evidence_cache"][f"{source}_{query_key}"] = cache_data

    def get_cached_evidence(
        self,
        workflow_id: str,
        source: str,
        query_key: str,
    ) -> Optional[dict]:
        """Retrieve cached evidence if available."""
        if self.available:
            try:
                cache_doc_id = f"{source}_{query_key}"
                doc = (
                    self.db.collection("workflows")
                    .document(workflow_id)
                    .collection("evidence_retrieved")
                    .document(cache_doc_id)
                    .get()
                )
                if doc.exists:
                    return doc.to_dict().get("results")
            except Exception as e:
                logger.error(f"Failed to retrieve cached evidence: {e}")
        else:
            if workflow_id in self._memory_cache and "evidence_cache" in self._memory_cache[workflow_id]:
                cache = self._memory_cache[workflow_id]["evidence_cache"]
                if f"{source}_{query_key}" in cache:
                    return cache[f"{source}_{query_key}"].get("results")

        return None


# Singleton instance
_store: Optional[WorkflowStore] = None


def get_workflow_store() -> WorkflowStore:
    """Get or create the WorkflowStore singleton."""
    global _store
    if _store is None:
        _store = WorkflowStore()
    return _store
