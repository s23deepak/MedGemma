"""
HIPAA-compliant access control and consent management.

Implements:
- Role-Based Access Control (RBAC) for clinical data
- Patient consent tracking and enforcement
- Purpose-of-use restrictions
- Minimum necessary principle
- Audit trail for access decisions
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, Set
from abc import ABC, abstractmethod


class UserRole(Enum):
    """Clinical system roles with access levels."""
    ADMIN = "admin"  # System administrator
    PHYSICIAN = "physician"  # Treating physician
    HOSPITALIST = "hospitalist"  # Hospital physician
    SPECIALIST = "specialist"  # Specialist physician
    RESIDENT = "resident"  # Medical resident
    NURSE = "nurse"  # Registered nurse
    AIDE = "aide"  # Nursing aide
    RESEARCHER = "researcher"  # Research user (limited access)
    AUDITOR = "auditor"  # Compliance auditor
    SYSTEM = "system"  # Automated system


class ConsentType(Enum):
    """Types of patient consent per HIPAA."""
    TREATMENT = "treatment"  # For treatment of patient
    PAYMENT = "payment"  # For billing/insurance
    HEALTHCARE_OPS = "healthcare_operations"  # System operations
    RESEARCH = "research"  # Research purposes
    DISCLOSURE = "disclosure"  # To external parties
    MARKETING = "marketing"  # Marketing communications


class PurposeOfUse(Enum):
    """HIPAA-defined purposes for data access."""
    TREATMENT = "treatment"
    PAYMENT = "payment"
    HEALTHCARE_OPS = "healthcare_operations"
    RESEARCH = "research"
    PUBLIC_HEALTH = "public_health"
    JUDICIAL = "judicial_proceedings"
    LAW_ENFORCEMENT = "law_enforcement"
    INVESTIGATION = "investigation"
    QUALITY_IMPROVEMENT = "quality_improvement"


@dataclass
class ConsentRecord:
    """Patient consent for data usage."""
    patient_id_hash: str  # SHA-256 of patient_id for privacy
    consent_type: ConsentType
    purpose_of_use: PurposeOfUse
    granted: bool = True  # True = consent given, False = denied
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: Optional[str] = None  # When consent expires
    authorized_users: list[str] = field(default_factory=list)  # User IDs allowed under consent
    authorized_roles: list[UserRole] = field(default_factory=list)  # Roles allowed
    notes: Optional[str] = None
    acknowledged_by: Optional[str] = None  # User who obtained consent

    def is_valid(self) -> bool:
        """Check if consent is currently valid."""
        if not self.granted:
            return False
        if self.expires_at:
            if datetime.fromisoformat(self.expires_at) < datetime.now(timezone.utc):
                return False
        return True

    def can_access(self, user_id: str, user_role: UserRole) -> bool:
        """Check if specific user can access under this consent."""
        if not self.is_valid():
            return False
        if self.authorized_users and user_id not in self.authorized_users:
            return False
        if self.authorized_roles and user_role not in self.authorized_roles:
            return False
        return True


@dataclass
class AccessPolicy:
    """Role-based access policy."""
    role: UserRole
    allowed_purposes: Set[PurposeOfUse] = field(default_factory=set)
    data_types: Set[str] = field(default_factory=set)  # e.g., "clinical_note", "lab_result"
    max_records_per_query: int = 500
    can_export: bool = False
    can_modify: bool = False
    can_delete: bool = False
    requires_justification: bool = False  # Must provide access reason
    requires_audit_review: bool = False


class AccessControlManager:
    """
    HIPAA-compliant access control manager.

    Enforces:
    - Minimum Necessary Principle: Only access needed information
    - Role-Based Access Control: Based on job function
    - Consent Requirements: Honor patient wishes
    - Purpose Restrictions: Use data only for stated purpose
    - Audit Requirements: Log all access decisions
    """

    def __init__(self):
        """Initialize access control system."""
        self.consent_records: dict[str, list[ConsentRecord]] = {}  # patient_id_hash -> consents
        self.access_policies: dict[UserRole, AccessPolicy] = {}
        self._initialize_default_policies()

    def _initialize_default_policies(self):
        """Set up default access policies for clinical roles."""
        # Treating physician: full treatment access, selective ops/research
        self.access_policies[UserRole.PHYSICIAN] = AccessPolicy(
            role=UserRole.PHYSICIAN,
            allowed_purposes={
                PurposeOfUse.TREATMENT,
                PurposeOfUse.HEALTHCARE_OPS,
                PurposeOfUse.QUALITY_IMPROVEMENT,
            },
            data_types={"clinical_note", "lab_result", "imaging_report", "vital_signs", "medication"},
            max_records_per_query=1000,
            can_modify=True,
            can_export=False,
        )

        # Specialist: limited to relevant records
        self.access_policies[UserRole.SPECIALIST] = AccessPolicy(
            role=UserRole.SPECIALIST,
            allowed_purposes={PurposeOfUse.TREATMENT, PurposeOfUse.HEALTHCARE_OPS},
            data_types={"clinical_note", "lab_result", "imaging_report"},
            max_records_per_query=500,
            can_modify=False,
            can_export=False,
            requires_justification=True,
        )

        # Nurse: treatment-only access
        self.access_policies[UserRole.NURSE] = AccessPolicy(
            role=UserRole.NURSE,
            allowed_purposes={PurposeOfUse.TREATMENT},
            data_types={"clinical_note", "vital_signs", "medication"},
            max_records_per_query=100,
            can_modify=False,
            can_export=False,
        )

        # Researcher: limited to consented research data
        self.access_policies[UserRole.RESEARCHER] = AccessPolicy(
            role=UserRole.RESEARCHER,
            allowed_purposes={PurposeOfUse.RESEARCH, PurposeOfUse.QUALITY_IMPROVEMENT},
            data_types={"clinical_note", "lab_result"},
            max_records_per_query=50,
            can_modify=False,
            can_export=True,  # For research analysis
            requires_justification=True,
            requires_audit_review=True,
        )

        # Auditor: read-only of audit trails and metadata
        self.access_policies[UserRole.AUDITOR] = AccessPolicy(
            role=UserRole.AUDITOR,
            allowed_purposes={PurposeOfUse.HEALTHCARE_OPS},
            data_types={"audit_log", "access_log"},
            max_records_per_query=10000,
            can_modify=False,
            can_export=True,
        )

    def add_consent(self, consent: ConsentRecord) -> None:
        """Record patient consent."""
        if consent.patient_id_hash not in self.consent_records:
            self.consent_records[consent.patient_id_hash] = []
        self.consent_records[consent.patient_id_hash].append(consent)

    def revoke_consent(
        self,
        patient_id_hash: str,
        consent_type: ConsentType,
        effective_immediately: bool = True,
    ) -> bool:
        """Revoke specific consent type."""
        if patient_id_hash not in self.consent_records:
            return False

        for consent in self.consent_records[patient_id_hash]:
            if consent.consent_type == consent_type:
                consent.granted = False
                return True
        return False

    def has_consent(
        self,
        patient_id_hash: str,
        consent_type: ConsentType,
        user_id: Optional[str] = None,
        user_role: Optional[UserRole] = None,
    ) -> bool:
        """Check if valid consent exists."""
        if patient_id_hash not in self.consent_records:
            return False

        for consent in self.consent_records[patient_id_hash]:
            if consent.consent_type != consent_type:
                continue
            if not consent.is_valid():
                continue
            if user_id and user_role:
                if not consent.can_access(user_id, user_role):
                    continue
            return True

        return False

    def can_access(
        self,
        user_id: str,
        user_role: UserRole,
        patient_id_hash: str,
        purpose: PurposeOfUse,
        data_type: str = "clinical_note",
        record_count: int = 1,
        justification: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Check if user can access patient data.

        Returns:
            (can_access: bool, reason_if_denied: Optional[str])
        """
        # Get policy for role
        policy = self.access_policies.get(user_role)
        if not policy:
            return False, f"Role {user_role.value} not recognized"

        # Check purpose of use
        if purpose not in policy.allowed_purposes:
            return False, f"Purpose {purpose.value} not allowed for {user_role.value}"

        # Check data type
        if data_type not in policy.data_types:
            return False, f"Data type {data_type} not accessible to {user_role.value}"

        # Check record count (minimum necessary principle)
        if record_count > policy.max_records_per_query:
            return False, f"Requesting {record_count} exceeds limit of {policy.max_records_per_query}"

        # Check justification requirement
        if policy.requires_justification and not justification:
            return False, "Justification required for this access"

        # Check consent if required
        # Treatment purposes require treatment consent
        if purpose == PurposeOfUse.TREATMENT:
            if not self.has_consent(patient_id_hash, ConsentType.TREATMENT, user_id, user_role):
                return False, "Patient consent for treatment not found"

        # Research requires research consent
        if purpose == PurposeOfUse.RESEARCH:
            if not self.has_consent(patient_id_hash, ConsentType.RESEARCH, user_id, user_role):
                return False, "Patient consent for research not found"

        return True, None

    def get_access_policy(self, role: UserRole) -> Optional[AccessPolicy]:
        """Get access policy for a role."""
        return self.access_policies.get(role)

    def update_policy(self, policy: AccessPolicy) -> None:
        """Update access policy for a role."""
        self.access_policies[policy.role] = policy


class AccessControlEnforcer:
    """
    Decorator/middleware for enforcing access control on RAG operations.
    """

    def __init__(self, access_manager: AccessControlManager, audit_logger=None):
        """
        Initialize enforcer.

        Args:
            access_manager: AccessControlManager instance
            audit_logger: Optional HIPAAAuditLogger for logging access decisions
        """
        self.access_manager = access_manager
        self.audit_logger = audit_logger

    def check_access(
        self,
        user_id: str,
        user_role: UserRole,
        patient_id_hash: str,
        purpose: PurposeOfUse,
        action: str = "retrieve",
        data_type: str = "clinical_note",
        record_count: int = 1,
        justification: Optional[str] = None,
    ) -> bool:
        """
        Check access and optionally log the decision.

        Raises ValueError if access denied, logs decision via audit logger.
        """
        can_access, reason = self.access_manager.can_access(
            user_id=user_id,
            user_role=user_role,
            patient_id_hash=patient_id_hash,
            purpose=purpose,
            data_type=data_type,
            record_count=record_count,
            justification=justification,
        )

        if self.audit_logger:
            if can_access:
                self.audit_logger.log_data_access(
                    user_id=user_id,
                    user_role=user_role.value,
                    resource_id=patient_id_hash,
                    action=action,
                    result_count=record_count,
                    data_category=data_type,
                    notes=f"Purpose: {purpose.value}; Justification: {justification}",
                )
            else:
                self.audit_logger.log_access_denied(
                    user_id=user_id,
                    user_role=user_role.value,
                    resource_id=patient_id_hash,
                    reason=reason or "Unknown",
                )

        if not can_access:
            raise PermissionError(reason or "Access denied")

        return True
