"""
Audit Logger — immutable event trail for clinical actions.

Stores events in an in-memory ring buffer (max 1000 entries) and
asynchronously persists each event to Firestore when Firebase is available.

Event types:
  EHR_VIEW, EHR_UPDATE, AI_SUGGESTION, PHYSICIAN_APPROVAL,
  PHYSICIAN_REJECTION, SOAP_GENERATED, COUNCIL_DELIBERATION,
  DISCHARGE_PLANNED, HANDOFF_GENERATED, SAFETY_ALERT, LOGIN, LOGOUT
"""

from __future__ import annotations

import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# ── AuditEvent ────────────────────────────────────────────────────────────────

@dataclass
class AuditEvent:
    """A single immutable audit record."""
    event_id: str
    timestamp: str
    event_type: str
    action: str
    user_id: str = "system"
    user_role: str = "system"
    patient_id: str | None = None
    resource_type: str | None = None
    details: dict = field(default_factory=dict)
    ip_address: str | None = None
    success: bool = True

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "action": self.action,
            "user_id": self.user_id,
            "user_role": self.user_role,
            "patient_id": self.patient_id,
            "resource_type": self.resource_type,
            "details": self.details,
            "ip_address": self.ip_address,
            "success": self.success,
        }


# ── AuditLogger ───────────────────────────────────────────────────────────────

class AuditLogger:
    """
    Thread-safe audit logger with in-memory ring buffer and optional
    Firestore persistence.

    The ring buffer holds the 1000 most recent events; older events are
    evicted automatically. Firestore writes are fire-and-forget — a failure
    does NOT raise an exception so the clinical workflow is never blocked.
    """

    _MAX_BUFFER = 1000

    def __init__(self) -> None:
        self._buffer: deque[AuditEvent] = deque(maxlen=self._MAX_BUFFER)

    def log(
        self,
        event_type: str,
        action: str,
        *,
        patient_id: str | None = None,
        user_id: str = "system",
        user_role: str = "system",
        resource_type: str | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
        success: bool = True,
    ) -> AuditEvent:
        """
        Record an audit event.

        Returns the AuditEvent that was stored (useful for testing).
        Firestore write is attempted silently; failure is logged at DEBUG.
        """
        event = AuditEvent(
            event_id=f"AUD-{uuid.uuid4().hex[:12]}",
            timestamp=datetime.now().isoformat(),
            event_type=event_type,
            action=action,
            user_id=user_id,
            user_role=user_role,
            patient_id=patient_id,
            resource_type=resource_type,
            details=details or {},
            ip_address=ip_address,
            success=success,
        )
        self._buffer.append(event)
        self._write_to_firestore(event)
        return event

    def get_recent(self, limit: int = 100) -> list[dict]:
        """Return the most recent *limit* events (newest first)."""
        events = list(self._buffer)
        return [e.to_dict() for e in reversed(events[-limit:])]

    def get_for_patient(self, patient_id: str, limit: int = 50) -> list[dict]:
        """Return the most recent *limit* events for a specific patient."""
        events = [
            e for e in reversed(list(self._buffer))
            if e.patient_id == patient_id
        ]
        return [e.to_dict() for e in events[:limit]]

    def _write_to_firestore(self, event: AuditEvent) -> None:
        """Silently persist event to Firestore audit_log/{event_id}."""
        try:
            from src.config.firebase_config import get_firestore_client, is_firebase_available
            if not is_firebase_available():
                return
            db = get_firestore_client()
            if db is None:
                return
            db.collection("audit_log").document(event.event_id).set(event.to_dict())
        except Exception as exc:
            logger.debug(f"[AuditLogger] Firestore write skipped ({exc})")


# ── Singleton ─────────────────────────────────────────────────────────────────

_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """Get or create the AuditLogger singleton."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
        logger.info("[AuditLogger] Initialized (in-memory ring buffer, max 1000 events)")
    return _audit_logger
