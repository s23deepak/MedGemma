"""
HIPAA-compliant RAG pipeline wrapper.

Integrates:
- De-identification (PHI masking)
- Access control (RBAC + consent)
- Audit logging (immutable trails)
- Data retention (automatic purging)
- Query privacy (hash instead of logging raw queries)

Wrapper around native RAG functions with HIPAA guardrails.
All clinical notes are de-identified before embedding/retrieval.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Tuple
import hashlib
import time

from src.council.rag import (
    chunk_note_with_metadata,
    retrieve_with_provenance,
    NoteMetadata,
    RankedChunk,
    compress_note_with_provenance,
)
from src.hipaa.hipaa_de_identification import PHIDetector, DeIdentificationResult
from src.hipaa.hipaa_audit_logger import HIPAAAuditLogger, AuditEventType, AuditSeverity
from src.hipaa.hipaa_access_control import (
    AccessControlManager,
    AccessControlEnforcer,
    UserRole,
    PurposeOfUse,
    ConsentType,
)
from src.hipaa.hipaa_retention_policy import (
    HIPAADataRetentionManager,
    DataClassification,
)


@dataclass
class HIPAAClinicalNote:
    """Clinical note with de-identification metadata."""
    original_id: str  # Original source identifier (hashed)
    patient_id_hash: str  # Patient ID (hashed) - REQUIRED for isolation
    de_identified_text: str
    de_identification_result: DeIdentificationResult
    metadata: NoteMetadata
    registered_for_retention: bool = False
    access_log_id: str = ""

    def phi_detected(self) -> bool:
        """Whether PHI was detected and masked in this note."""
        return self.de_identification_result.phi_detected

    def phi_categories(self) -> list[str]:
        """Categories of PHI found in this note."""
        cats = set()
        for repl in self.de_identification_result.replacements:
            cats.add(repl.category.value)
        return sorted(list(cats))


@dataclass
class HIPAARankedChunk(RankedChunk):
    """Ranked chunk with de-identification provenance."""
    de_identified: bool = False
    phi_categories: list[str] = field(default_factory=list)
    access_justified: bool = False
    access_purpose: Optional[str] = None
    patient_id_hash: str = ""  # NEW: Track patient origin for isolation


class HIPAACompliantRAGPipeline:
    """
    HIPAA-compliant RAG system combining secure retrieval with clinical safety.

    Security layers:
    1. De-Identification: Mask PHI before embedding/retrieval
    2. Access Control: Enforce RBAC + consent before retrieval
    3. Audit Logging: Immutable trail of all access
    4. Data Retention: Automatic purging per policy
    5. Query Privacy: Hash queries instead of storing
    """

    def __init__(
        self,
        audit_logger: Optional[HIPAAAuditLogger] = None,
        access_manager: Optional[AccessControlManager] = None,
        retention_manager: Optional[HIPAADataRetentionManager] = None,
    ):
        """
        Initialize HIPAA-compliant RAG pipeline.

        Args:
            audit_logger: Audit logger (created if None)
            access_manager: Access control manager (created if None)
            retention_manager: Retention manager (created if None)
        """
        self.phi_detector = PHIDetector()
        self.audit_logger = audit_logger or HIPAAAuditLogger()
        self.access_manager = access_manager or AccessControlManager()
        self.retention_manager = retention_manager or HIPAADataRetentionManager()
        self.access_enforcer = AccessControlEnforcer(self.access_manager, self.audit_logger)

    def de_identify_note(self, note_text: str, note_id: str, patient_id: str) -> HIPAAClinicalNote:
        """
        De-identify a clinical note with patient tracking for isolation.

        Args:
            note_text: Raw clinical note
            note_id: Original note identifier
            patient_id: Patient ID (for cross-patient leakage prevention)

        Returns:
            HIPAAClinicalNote with masked PHI and patient origin tracking
        """
        # Hash IDs for privacy
        note_id_hash = hashlib.sha256(note_id.encode()).hexdigest()[:16]
        patient_id_hash = hashlib.sha256(patient_id.encode()).hexdigest()[:16]

        # De-identify
        result = self.phi_detector.de_identify(note_text)

        # Log de-identification event (including patient for audit)
        self.audit_logger.log_event(
            event_type=AuditEventType.DATA_UPDATE,
            action="Clinical note de-identified",
            resource_id=patient_id_hash,
            resource_type="clinical_note",
            data_category="PHI",
            notes=f"Found {len(result.replacements)} PHI elements: {result.to_dict()['categories_found']}",
        )

        return HIPAAClinicalNote(
            original_id=note_id_hash,
            patient_id_hash=patient_id_hash,  # NEW: Track patient for isolation
            de_identified_text=result.de_identified_text,
            de_identification_result=result,
            metadata=NoteMetadata(
                source=f"De-identified note {note_id_hash}",
                author_role="unknown",  # Masked for privacy
                note_date="",  # Masked for privacy
                note_type="note",
            ),
        )

    def retrieve_with_access_control(
        self,
        user_id: str,
        user_role: UserRole,
        patient_id: str,
        query: str,
        notes_for_retrieval: list[HIPAAClinicalNote],
        purpose_of_use: PurposeOfUse,
        top_k: int = 5,
        justification: Optional[str] = None,
    ) -> Tuple[list[HIPAARankedChunk], bool, Optional[str]]:
        """
        Retrieve relevant chunks with PATIENT-ISOLATED access control.

        Args:
            user_id: User making request
            user_role: User's role
            patient_id: Patient ID
            query: Search query
            notes_for_retrieval: De-identified clinical notes
            purpose_of_use: Purpose for retrieval
            top_k: Number of chunks to return
            justification: Reason for access (if required)

        Returns:
            (retrieved_chunks, access_granted, denial_reason)
        """
        patient_id_hash = hashlib.sha256(patient_id.encode()).hexdigest()[:16]
        start_time = time.time()

        try:
            # SECURITY: Validate all notes belong to target patient (CROSS-PATIENT LEAKAGE PREVENTION)
            for note in notes_for_retrieval:
                if note.patient_id_hash != patient_id_hash:
                    logger.warning(
                        f"SECURITY VIOLATION: Attempted to retrieve note from different patient. "
                        f"Expected {patient_id_hash}, got {note.patient_id_hash}"
                    )
                    self.audit_logger.log_access_denied(
                        user_id=user_id,
                        user_role=user_role.value,
                        resource_id=patient_id_hash,
                        reason="Cross-patient retrieval attempted - notes from different patient",
                    )
                    return [], False, "Cross-patient data boundary violation"

            # Check access control
            self.access_enforcer.check_access(
                user_id=user_id,
                user_role=user_role,
                patient_id_hash=patient_id_hash,
                purpose=purpose_of_use,
                action="retrieve",
                data_type="clinical_note",
                record_count=top_k,
                justification=justification,
            )

            # Prepare chunks for retrieval (already de-identified & patient-verified)
            chunks_with_meta = [
                (note.de_identified_text, note.metadata)
                for note in notes_for_retrieval
            ]

            if not chunks_with_meta:
                return [], True, None

            # Retrieve relevant chunks
            ranked = retrieve_with_provenance(
                query=query,
                chunks_with_meta=chunks_with_meta,
                top_k=top_k,
            )

            # Convert to HIPAA-annotated chunks with patient tracking
            hipaa_ranked = []
            for chunk in ranked:
                hipaa_chunk = HIPAARankedChunk(
                    text=chunk.text,
                    score=chunk.score,
                    position=chunk.position,
                    metadata=chunk.metadata,
                    de_identified=True,
                    access_justified=True,
                    access_purpose=purpose_of_use.value,
                    patient_id_hash=patient_id_hash,  # NEW: Track patient origin
                )
                hipaa_ranked.append(hipaa_chunk)

            # Log successful retrieval
            query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
            processing_time = (time.time() - start_time) * 1000

            self.audit_logger.log_query_execution(
                user_id=user_id,
                query=query,  # Will be hashed by audit logger
                result_count=len(hipaa_ranked),
                processing_time_ms=processing_time,
                user_role=user_role.value,
                resource_id=patient_id_hash,
                notes=f"Purpose: {purpose_of_use.value}; Justification: {justification}",
            )

            # Register retrieval data for retention tracking
            for i, chunk in enumerate(hipaa_ranked):
                data_id = f"{patient_id_hash}_chunk_{i}_{query_hash}"
                self.retention_manager.register_data(
                    data_id=data_id,
                    classification=DataClassification.WORKING,
                    content=chunk.text,
                    size_bytes=len(chunk.text),
                    notes=f"Retrieved chunk for query (hash: {query_hash})",
                )

            return hipaa_ranked, True, None

        except PermissionError as e:
            # Log access denial
            self.audit_logger.log_access_denied(
                user_id=user_id,
                user_role=user_role.value,
                resource_id=patient_id_hash,
                reason=str(e),
            )
            return [], False, str(e)

    def compress_note_with_privacy(
        self,
        user_id: str,
        user_role: UserRole,
        patient_id: str,
        raw_note: str,
        symptoms: list[str],
        purpose_of_use: PurposeOfUse,
        justification: Optional[str] = None,
        top_k: int = 5,
    ) -> Tuple[Optional[str], bool, Optional[str]]:
        """
        High-level helper: compress clinical note with HIPAA guardrails.

        Args:
            user_id: User making request
            user_role: User's role
            patient_id: Patient ID
            raw_note: Raw clinical note
            symptoms: Diagnostic symptoms for retrieval
            purpose_of_use: Purpose for access
            justification: Reason for access
            top_k: Number of chunks to retrieve

        Returns:
            (compressed_note_or_None, access_granted, denial_reason)
        """
        # De-identify first (with patient_id for isolation)
        hipaa_note = self.de_identify_note(raw_note, f"{patient_id}_note", patient_id)

        # Retrieve chunks with access control
        chunks, access_granted, denial_reason = self.retrieve_with_access_control(
            user_id=user_id,
            user_role=user_role,
            patient_id=patient_id,
            query=" ".join(symptoms),
            notes_for_retrieval=[hipaa_note],
            purpose_of_use=purpose_of_use,
            top_k=top_k,
            justification=justification,
        )

        if not access_granted:
            return None, False, denial_reason

        # Assemble compressed context from chunks
        if not chunks:
            return "", True, None

        compressed = "\n---\n".join(c.text for c in chunks)
        return compressed, True, None

    def get_retrieval_context(
        self,
        user_id: str,
        user_role: UserRole,
        patient_id: str,
        raw_notes: list[Tuple[str, NoteMetadata]],
        symptoms: list[str],
        purpose_of_use: PurposeOfUse,
        justification: Optional[str] = None,
        top_k: int = 5,
    ) -> Tuple[Optional[str], dict]:
        """
        Get retrieval context suitable for diagnostic council.

        Args:
            user_id: User ID
            user_role: User role
            patient_id: Patient ID
            raw_notes: List of (raw_note_text, metadata) tuples
            symptoms: Diagnostic symptoms
            purpose_of_use: Purpose for access
            justification: Access justification
            top_k: Chunks to retrieve

        Returns:
            (context_string, metadata_dict)
        """
        metadata = {
            'user_id': user_id,
            'user_role': user_role.value,
            'patient_id_hash': hashlib.sha256(patient_id.encode()).hexdigest()[:16],
            'purpose': purpose_of_use.value,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'de_identified': True,
            'access_granted': False,
            'denial_reason': None,
            'notes_processed': 0,
            'chunks_retrieved': 0,
            'phi_found': False,
        }

        try:
            # De-identify all notes with patient tracking for isolation
            hipaa_notes = []
            for raw_note, note_meta in raw_notes:
                hipaa_note = self.de_identify_note(raw_note, f"{patient_id}_{len(hipaa_notes)}", patient_id)
                hipaa_notes.append(hipaa_note)
                metadata['notes_processed'] += 1
                if hipaa_note.phi_detected():
                    metadata['phi_found'] = True

            # Retrieve chunks
            chunks, access_granted, denial_reason = self.retrieve_with_access_control(
                user_id=user_id,
                user_role=user_role,
                patient_id=patient_id,
                query=" ".join(symptoms),
                notes_for_retrieval=hipaa_notes,
                purpose_of_use=purpose_of_use,
                top_k=top_k,
                justification=justification,
            )

            metadata['access_granted'] = access_granted
            metadata['denial_reason'] = denial_reason
            metadata['chunks_retrieved'] = len(chunks)

            if not access_granted:
                return None, metadata

            # Assemble context
            context = "\n---\n".join(c.text for c in chunks)
            return context, metadata

        except Exception as e:
            metadata['error'] = str(e)
            self.audit_logger.log_event(
                event_type=AuditEventType.SYSTEM_EVENT,
                action="Error in HIPAA RAG pipeline",
                severity=AuditSeverity.WARNING,
                user_id=user_id,
                reason=str(e),
            )
            return None, metadata

    def get_compliance_report(self) -> dict:
        """Generate compliance report across all HIPAA components."""
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'audit_trail': self.audit_logger.get_statistics(),
            'retention_compliance': self.retention_manager.check_retention_compliance(),
            'audit_integrity': {
                'verified': self.audit_logger.verify_audit_integrity(),
                'total_entries': len(self.audit_logger.in_memory_log),
            },
        }
