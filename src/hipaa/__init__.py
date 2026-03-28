"""
HIPAA-Compliant RAG and Data Security Module

This module provides project-wide HIPAA compliance for all RAG and data access operations:
- De-identification (PHI masking)
- Access control (RBAC + consent)
- Audit logging (immutable trails)
- Data retention (automatic purging)
- Query privacy (hashing)

Use HIPAACompliantRAGPipeline as a drop-in replacement for all RAG operations.
"""

from src.hipaa.hipaa_rag_wrapper import HIPAACompliantRAGPipeline, HIPAARankedChunk, HIPAAClinicalNote
from src.hipaa.hipaa_de_identification import PHIDetector, DeIdentificationResult, PHIReplacement, PHICategory
from src.hipaa.hipaa_audit_logger import HIPAAAuditLogger, AuditEntry, AuditEventType, AuditSeverity
from src.hipaa.hipaa_access_control import (
    AccessControlManager,
    AccessControlEnforcer,
    UserRole,
    PurposeOfUse,
    ConsentType,
    ConsentRecord,
    AccessPolicy,
)
from src.hipaa.hipaa_retention_policy import (
    HIPAADataRetentionManager,
    RetainedData,
    DataClassification,
    RetentionPolicy,
    RetentionStatus,
)

__all__ = [
    # RAG Wrapper
    "HIPAACompliantRAGPipeline",
    "HIPAARankedChunk",
    "HIPAAClinicalNote",
    # De-identification
    "PHIDetector",
    "DeIdentificationResult",
    "PHIReplacement",
    "PHICategory",
    # Audit Logger
    "HIPAAAuditLogger",
    "AuditEntry",
    "AuditEventType",
    "AuditSeverity",
    # Access Control
    "AccessControlManager",
    "AccessControlEnforcer",
    "UserRole",
    "PurposeOfUse",
    "ConsentType",
    "ConsentRecord",
    "AccessPolicy",
    # Retention
    "HIPAADataRetentionManager",
    "RetainedData",
    "DataClassification",
    "RetentionPolicy",
    "RetentionStatus",
]

__version__ = "1.0"
__doc__ = "HIPAA-Compliant RAG and Data Security Module"
