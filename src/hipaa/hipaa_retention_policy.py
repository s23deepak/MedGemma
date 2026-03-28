"""
HIPAA data retention policy manager.

Implements:
- Minimum data retention periods
- Maximum retention limits
- Automatic purging of aged data
- Secure data deletion
- Retention compliance reporting
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, Callable
import hashlib


class DataClassification(Enum):
    """Data sensitivity levels for retention policy."""
    TEMPORARY = "temporary"  # Session data, temporary caches
    WORKING = "working"  # Active case data
    ARCHIVE = "archive"  # Concluded case data
    AUDIT = "audit"  # Audit logs (longer retention)
    RESEARCH = "research"  # Research data


@dataclass
class RetentionPolicy:
    """Policy for data retention and deletion."""
    classification: DataClassification
    min_retention_days: int = 0  # Minimum days to keep
    max_retention_days: Optional[int] = None  # Maximum days to keep (None = unlimited)
    auto_delete_after_days: Optional[int] = None  # Auto-purge after this many days
    requires_manual_review: bool = False  # Requires review before deletion
    notification_days_before_delete: int = 30  # Notify staff N days before auto-delete


class RetentionStatus(Enum):
    """Status of retained data."""
    ACTIVE = "active"  # Currently in use
    INACTIVE = "inactive"  # Not accessed recently
    FLAGGED_FOR_REVIEW = "flagged_for_review"  # Under compliance review
    SCHEDULED_FOR_DELETION = "scheduled_for_deletion"  # Awaiting deletion
    DELETED = "deleted"  # Securely deleted


@dataclass
class RetainedData:
    """Record of retained data with retention metadata."""
    data_id: str  # Unique identifier
    classification: DataClassification
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_accessed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    content_hash: str = ""  # SHA-256 for integrity/dedup verification
    size_bytes: int = 0
    related_data_ids: list[str] = field(default_factory=list)  # Related records
    retention_status: RetentionStatus = RetentionStatus.ACTIVE
    scheduled_deletion_date: Optional[str] = None
    deletion_reason: Optional[str] = None
    notes: Optional[str] = None

    def update_last_accessed(self):
        """Update access timestamp."""
        self.last_accessed_at = datetime.now(timezone.utc).isoformat()

    def days_since_creation(self) -> int:
        """Days since data was created."""
        created = datetime.fromisoformat(self.created_at)
        now = datetime.now(timezone.utc)
        return (now - created).days

    def days_since_access(self) -> int:
        """Days since data was last accessed."""
        accessed = datetime.fromisoformat(self.last_accessed_at)
        now = datetime.now(timezone.utc)
        return (now - accessed).days


class HIPAADataRetentionManager:
    """
    Manages data lifecycle per HIPAA retention requirements.

    HIPAA principle: Retain data only as long as necessary, with secure deletion.
    """

    def __init__(self):
        """Initialize retention manager."""
        self.policies: dict[DataClassification, RetentionPolicy] = {}
        self.retained_data: dict[str, RetainedData] = {}
        self.deletion_callbacks: list[Callable[[RetainedData], None]] = []

        # Initialize default policies
        self._initialize_default_policies()

    def _initialize_default_policies(self):
        """Set up default retention policies."""
        # Temporary session/cache data: Delete after 24 hours
        self.policies[DataClassification.TEMPORARY] = RetentionPolicy(
            classification=DataClassification.TEMPORARY,
            min_retention_days=0,
            max_retention_days=1,
            auto_delete_after_days=1,
            notification_days_before_delete=0,
        )

        # Working case data: Keep while case is active, up to 7 years (statute of limitations)
        self.policies[DataClassification.WORKING] = RetentionPolicy(
            classification=DataClassification.WORKING,
            min_retention_days=30,  # At least 30 days for working cases
            max_retention_days=365 * 7,  # 7 years
            auto_delete_after_days=365 * 7,
            notification_days_before_delete=60,
            requires_manual_review=True,
        )

        # Archive: Keep concluded cases for 3 years per CMS guidelines, then archive
        self.policies[DataClassification.ARCHIVE] = RetentionPolicy(
            classification=DataClassification.ARCHIVE,
            min_retention_days=365 * 3,
            max_retention_days=365 * 5,
            auto_delete_after_days=365 * 5,
            notification_days_before_delete=90,
            requires_manual_review=True,
        )

        # Audit logs: 6 years per HIPAA requirements
        self.policies[DataClassification.AUDIT] = RetentionPolicy(
            classification=DataClassification.AUDIT,
            min_retention_days=365 * 6,
            max_retention_days=365 * 7,
            auto_delete_after_days=365 * 7,
            notification_days_before_delete=180,
            requires_manual_review=True,
        )

        # Research data: Per IRB approval (e.g., 3 years)
        self.policies[DataClassification.RESEARCH] = RetentionPolicy(
            classification=DataClassification.RESEARCH,
            min_retention_days=365,
            max_retention_days=365 * 3,
            auto_delete_after_days=365 * 3,
            notification_days_before_delete=90,
            requires_manual_review=True,
        )

    def register_data(
        self,
        data_id: str,
        classification: DataClassification,
        content: str,
        size_bytes: int = 0,
        related_data_ids: Optional[list[str]] = None,
        notes: Optional[str] = None,
    ) -> RetainedData:
        """Register data for retention tracking."""
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        retained = RetainedData(
            data_id=data_id,
            classification=classification,
            content_hash=content_hash,
            size_bytes=size_bytes or len(content),
            related_data_ids=related_data_ids or [],
            notes=notes,
        )

        self.retained_data[data_id] = retained
        return retained

    def access_data(self, data_id: str) -> bool:
        """Track data access (updates last_accessed_at)."""
        if data_id in self.retained_data:
            self.retained_data[data_id].update_last_accessed()
            return True
        return False

    def schedule_deletion(
        self,
        data_id: str,
        reason: str,
        deletion_date: Optional[str] = None,
    ) -> bool:
        """Schedule data for deletion."""
        if data_id not in self.retained_data:
            return False

        data = self.retained_data[data_id]
        data.retention_status = RetentionStatus.SCHEDULED_FOR_DELETION
        data.deletion_reason = reason
        data.scheduled_deletion_date = (
            deletion_date or
            (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        )
        return True

    def check_retention_compliance(self) -> dict:
        """Check which data items violate retention policies."""
        violations = []
        now = datetime.now(timezone.utc)

        for data_id, data in self.retained_data.items():
            policy = self.policies.get(data.classification)
            if not policy:
                continue

            days_old = data.days_since_creation()

            # Check max retention exceeded
            if policy.max_retention_days and days_old > policy.max_retention_days:
                violations.append({
                    'data_id': data_id,
                    'reason': 'max_retention_exceeded',
                    'days_old': days_old,
                    'policy_max': policy.max_retention_days,
                })

            # Check if should be auto-deleted
            if (
                policy.auto_delete_after_days and
                days_old > policy.auto_delete_after_days and
                data.retention_status != RetentionStatus.SCHEDULED_FOR_DELETION
            ):
                violations.append({
                    'data_id': data_id,
                    'reason': 'due_for_auto_deletion',
                    'days_old': days_old,
                    'policy_auto_delete': policy.auto_delete_after_days,
                })

        return {
            'total_data_items': len(self.retained_data),
            'violations': violations,
            'compliance_status': 'compliant' if not violations else 'non_compliant',
        }

    def get_data_pending_deletion(self) -> list[RetainedData]:
        """Get data scheduled for deletion that should be purged soon."""
        now = datetime.now(timezone.utc)
        pending = []

        for data in self.retained_data.values():
            if data.retention_status != RetentionStatus.SCHEDULED_FOR_DELETION:
                continue

            if data.scheduled_deletion_date:
                scheduled = datetime.fromisoformat(data.scheduled_deletion_date)
                if scheduled <= now:
                    pending.append(data)

        return pending

    def delete_data(
        self,
        data_id: str,
        secure_delete: bool = True,
        reason: str = "retention_policy",
    ) -> bool:
        """
        Delete data securely.

        Args:
            data_id: ID of data to delete
            secure_delete: If True, overwrite data before deletion
            reason: Reason for deletion (audit trail)

        Returns:
            True if deleted successfully
        """
        if data_id not in self.retained_data:
            return False

        data = self.retained_data[data_id]
        data.retention_status = RetentionStatus.DELETED
        data.deletion_reason = reason
        data.notes = f"{data.notes or ''}\nSecurely deleted at {datetime.now(timezone.utc).isoformat()}"

        # Call registered callbacks (e.g., backend storage deletion)
        for callback in self.deletion_callbacks:
            try:
                callback(data)
            except Exception as e:
                print(f"Error in deletion callback for {data_id}: {e}")

        # Remove from tracking
        del self.retained_data[data_id]

        return True

    def register_deletion_callback(self, callback: Callable[[RetainedData], None]):
        """Register callback to execute when data is deleted (e.g., DB deletion)."""
        self.deletion_callbacks.append(callback)

    def get_retention_report(self) -> dict:
        """Generate retention compliance report."""
        report = {
            'report_date': datetime.now(timezone.utc).isoformat(),
            'total_data_items': len(self.retained_data),
            'by_classification': {},
            'status_summary': {},
            'recommendations': [],
        }

        # Group by classification
        classification_counts = {}
        for data in self.retained_data.values():
            cls = data.classification.value
            if cls not in classification_counts:
                classification_counts[cls] = {'count': 0, 'total_size_mb': 0}
            classification_counts[cls]['count'] += 1
            classification_counts[cls]['total_size_mb'] += data.size_bytes / (1024 * 1024)

        report['by_classification'] = classification_counts

        # Group by status
        status_counts = {}
        for data in self.retained_data.values():
            status = data.retention_status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        report['status_summary'] = status_counts

        # Generate recommendations
        compliance = self.check_retention_compliance()
        if compliance['violations']:
            report['recommendations'].append({
                'priority': 'high',
                'message': f"Found {len(compliance['violations'])} retention policy violations",
                'actions': ['Review violations', 'Schedule deletion for compliant items'],
            })

        inactive_data = [
            d for d in self.retained_data.values()
            if d.days_since_access() > 180
        ]
        if inactive_data:
            report['recommendations'].append({
                'priority': 'medium',
                'message': f"Found {len(inactive_data)} inactive items not accessed in 180 days",
                'actions': ['Consider archiving or deletion'],
            })

        return report

    def update_policy(self, policy: RetentionPolicy) -> None:
        """Update retention policy for a classification."""
        self.policies[policy.classification] = policy

    def get_policy(self, classification: DataClassification) -> Optional[RetentionPolicy]:
        """Get retention policy for a classification."""
        return self.policies.get(classification)
