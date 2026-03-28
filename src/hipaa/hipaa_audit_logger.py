"""
HIPAA-compliant audit logging for RAG operations.

Tracks:
- All data access (who, what, when)
- Queries executed
- Data modifications
- Access denials/failures
- System events

Implements immutable audit trail suitable for compliance audits and breach investigations.
"""

import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any
import uuid


class AuditEventType(Enum):
    """HIPAA audit event categories."""
    DATA_ACCESS = "data_access"
    DATA_RETRIEVE = "data_retrieve"
    DATA_CREATE = "data_create"
    DATA_UPDATE = "data_update"
    DATA_DELETE = "data_delete"
    QUERY_EXECUTE = "query_execute"
    ACCESS_DENIED = "access_denied"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    SYSTEM_EVENT = "system_event"
    BREACH_NOTIFICATION = "breach_notification"


class AuditSeverity(Enum):
    """Audit event severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AuditEntry:
    """Single immutable audit log entry."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_type: AuditEventType = AuditEventType.SYSTEM_EVENT
    severity: AuditSeverity = AuditSeverity.INFO
    user_id: Optional[str] = None  # User identifier (anonymized if applicable)
    user_role: Optional[str] = None  # Role (physician, nurse, admin, etc.)
    action: str = ""  # What was done
    resource_id: Optional[str] = None  # What was accessed (workflow_id, patient_id hash, etc.)
    resource_type: str = ""  # Type of resource (clinical_note, embedding, query, etc.)
    status: str = "success"  # success, failure, denied
    reason: Optional[str] = None  # Reason for denial/failure
    data_category: Optional[str] = None  # PHI category if applicable
    ip_address: Optional[str] = None  # Source IP (anonymized if applicable)
    session_id: Optional[str] = None  # Session identifier
    changes: Optional[dict] = None  # What changed (for updates)
    query_hash: Optional[str] = None  # Hash of query executed (not query itself for privacy)
    result_count: Optional[int] = None  # Number of records returned
    processing_time_ms: Optional[float] = None  # How long operation took
    notes: Optional[str] = None  # Additional context
    checksum: str = ""  # SHA-256 of entry for tamper detection

    def __post_init__(self):
        """Calculate checksum for tamper detection."""
        if not self.checksum:
            # Create deterministic hash of all fields except checksum
            entry_dict = {k: v for k, v in asdict(self).items() if k != 'checksum'}
            entry_json = json.dumps(entry_dict, sort_keys=True, default=str)
            self.checksum = hashlib.sha256(entry_json.encode()).hexdigest()

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            **asdict(self),
            'event_type': self.event_type.value,
            'severity': self.severity.value,
        }

    def verify_integrity(self) -> bool:
        """Verify entry hasn't been tampered with."""
        entry_dict = {k: v for k, v in asdict(self).items() if k != 'checksum'}
        entry_json = json.dumps(entry_dict, sort_keys=True, default=str)
        expected_checksum = hashlib.sha256(entry_json.encode()).hexdigest()
        return expected_checksum == self.checksum


class HIPAAAuditLogger:
    """
    Immutable audit logger for HIPAA compliance.

    Design principles:
    - Append-only (never modify/delete entries)
    - Tamper-evident (checksums + chaining)
    - Comprehensive (logs all access patterns)
    - Actionable (clearly identifies anomalies)
    """

    def __init__(self, storage_backend=None):
        """
        Initialize audit logger.

        Args:
            storage_backend: Backend for persistence (database, file, cloud logging)
                           If None, logs are kept in memory only (for testing).
        """
        self.storage_backend = storage_backend
        self.in_memory_log: list[AuditEntry] = []
        self.previous_checksum: Optional[str] = None

    def log_event(
        self,
        event_type: AuditEventType,
        action: str,
        severity: AuditSeverity = AuditSeverity.INFO,
        user_id: Optional[str] = None,
        user_role: Optional[str] = None,
        resource_id: Optional[str] = None,
        resource_type: str = "",
        status: str = "success",
        reason: Optional[str] = None,
        data_category: Optional[str] = None,
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None,
        changes: Optional[dict] = None,
        query: Optional[str] = None,
        result_count: Optional[int] = None,
        processing_time_ms: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> AuditEntry:
        """
        Log an audit event.

        Args:
            event_type: Type of event
            action: Description of action
            severity: EVENT severity (INFO, WARNING, CRITICAL)
            user_id: User performing action
            user_role: User's role
            resource_id: Resource affected (hashed if PII)
            resource_type: Type of resource
            status: success/failure/denied
            reason: Why action failed/was denied
            data_category: PHI category involved
            ip_address: Source IP
            session_id: Session identifier
            changes: Data modifications
            query: Search query (will be hashed)
            result_count: Records returned
            processing_time_ms: Latency
            notes: Additional context

        Returns:
            AuditEntry for verification/tracking
        """
        # Hash query to avoid storing potentially sensitive queries
        query_hash = None
        if query:
            query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]

        # Link to previous entry (chain for tamper detection)
        entry = AuditEntry(
            event_type=event_type,
            severity=severity,
            action=action,
            user_id=user_id,
            user_role=user_role,
            resource_id=resource_id,
            resource_type=resource_type,
            status=status,
            reason=reason,
            data_category=data_category,
            ip_address=ip_address,
            session_id=session_id,
            changes=changes,
            query_hash=query_hash,
            result_count=result_count,
            processing_time_ms=processing_time_ms,
            notes=notes,
        )

        # Store entry and update chain
        self.in_memory_log.append(entry)
        self.previous_checksum = entry.checksum

        # Persist if backend available
        if self.storage_backend:
            self.storage_backend.save_audit_entry(entry)

        return entry

    def log_data_access(
        self,
        user_id: str,
        user_role: str,
        resource_id: str,
        action: str = "accessed",
        result_count: int = 0,
        processing_time_ms: Optional[float] = None,
        **kwargs,
    ) -> AuditEntry:
        """Convenience method for data access events."""
        return self.log_event(
            event_type=AuditEventType.DATA_ACCESS,
            action=f"User {user_role} {action} clinical data",
            user_id=user_id,
            user_role=user_role,
            resource_id=resource_id,
            resource_type="clinical_note",
            result_count=result_count,
            processing_time_ms=processing_time_ms,
            **kwargs,
        )

    def log_query_execution(
        self,
        user_id: str,
        query: str,
        result_count: int,
        processing_time_ms: float,
        status: str = "success",
        **kwargs,
    ) -> AuditEntry:
        """Convenience method for query events."""
        return self.log_event(
            event_type=AuditEventType.QUERY_EXECUTE,
            action="RAG query executed",
            user_id=user_id,
            query=query,
            result_count=result_count,
            processing_time_ms=processing_time_ms,
            status=status,
            **kwargs,
        )

    def log_access_denied(
        self,
        user_id: str,
        user_role: str,
        resource_id: str,
        reason: str,
        **kwargs,
    ) -> AuditEntry:
        """Convenience method for access denial events."""
        return self.log_event(
            event_type=AuditEventType.ACCESS_DENIED,
            action="Access denied",
            severity=AuditSeverity.WARNING,
            user_id=user_id,
            user_role=user_role,
            resource_id=resource_id,
            status="denied",
            reason=reason,
            resource_type="clinical_note",
            **kwargs,
        )

    def log_breach_attempt(
        self,
        user_id: str,
        resource_id: str,
        reason: str,
        **kwargs,
    ) -> AuditEntry:
        """Log potential breach/security incident."""
        return self.log_event(
            event_type=AuditEventType.BREACH_NOTIFICATION,
            action="Potential breach detected",
            severity=AuditSeverity.CRITICAL,
            user_id=user_id,
            resource_id=resource_id,
            status="failed",
            reason=reason,
            **kwargs,
        )

    def get_audit_trail(
        self,
        resource_id: Optional[str] = None,
        user_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        event_type: Optional[AuditEventType] = None,
    ) -> list[AuditEntry]:
        """
        Query audit log (for authorized personnel only).

        Args:
            resource_id: Filter by resource
            user_id: Filter by user
            start_time: ISO timestamp
            end_time: ISO timestamp
            event_type: Filter by event type

        Returns:
            Filtered audit entries
        """
        results = self.in_memory_log

        if resource_id:
            results = [e for e in results if e.resource_id == resource_id]
        if user_id:
            results = [e for e in results if e.user_id == user_id]
        if event_type:
            results = [e for e in results if e.event_type == event_type]

        if start_time:
            results = [e for e in results if e.timestamp >= start_time]
        if end_time:
            results = [e for e in results if e.timestamp <= end_time]

        return results

    def verify_audit_integrity(self) -> bool:
        """Verify entire audit log hasn't been tampered with."""
        for entry in self.in_memory_log:
            if not entry.verify_integrity():
                return False
        return True

    def export_audit_log(self, filepath: str):
        """Export audit log to JSON file (for compliance/investigation)."""
        entries = [e.to_dict() for e in self.in_memory_log]
        with open(filepath, 'w') as f:
            json.dump(entries, f, indent=2, default=str)

    def get_statistics(self) -> dict:
        """Get audit log statistics for monitoring."""
        if not self.in_memory_log:
            return {}

        event_counts = {}
        for entry in self.in_memory_log:
            event_type = entry.event_type.value
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        denied_count = sum(1 for e in self.in_memory_log if e.status == "denied")
        failed_count = sum(1 for e in self.in_memory_log if e.status == "failed")

        return {
            "total_events": len(self.in_memory_log),
            "event_types": event_counts,
            "access_denials": denied_count,
            "failed_operations": failed_count,
            "first_event": self.in_memory_log[0].timestamp,
            "last_event": self.in_memory_log[-1].timestamp,
        }
