"""
Integration guide and examples for HIPAA-compliant RAG pipeline.

Shows how to wire up all HIPAA components (de-identification, access control,
audit logging, retention) with the existing MedGemma council workflow.
"""

from datetime import datetime, timedelta, timezone
from src.hipaa.hipaa_rag_wrapper import HIPAACompliantRAGPipeline
from src.hipaa.hipaa_audit_logger import HIPAAAuditLogger
from src.hipaa.hipaa_access_control import (
    AccessControlManager,
    UserRole,
    PurposeOfUse,
    ConsentType,
    ConsentRecord,
)
from src.hipaa.hipaa_retention_policy import (
    HIPAADataRetentionManager,
    DataClassification,
)
from src.council.rag import NoteMetadata


# ────────────────────────────────────────────────────────────────────────────
# SETUP EXAMPLE: Initialize HIPAA stack
# ────────────────────────────────────────────────────────────────────────────

def setup_hipaa_rag_for_diagnostic_council():
    """
    Complete setup for HIPAA-compliant RAG in diagnostic council.

    Returns:
        Configured HIPAACompliantRAGPipeline ready for use
    """
    # 1. Initialize audit logger
    audit_logger = HIPAAAuditLogger()

    # 2. Initialize access control
    access_manager = AccessControlManager()

    # 3. Initialize retention policy
    retention_manager = HIPAADataRetentionManager()

    # Setup deletion callback to actually delete from storage
    # (in production, this would delete from Firestore)
    def delete_from_storage(retained_data):
        """Callback to delete data from backend storage."""
        # TODO: Implement deletion from Firestore/DB
        print(f"[RETENTION] Would delete: {retained_data.data_id}")

    retention_manager.register_deletion_callback(delete_from_storage)

    # 4. Initialize HIPAA RAG pipeline
    hipaa_rag = HIPAACompliantRAGPipeline(
        audit_logger=audit_logger,
        access_manager=access_manager,
        retention_manager=retention_manager,
    )

    return hipaa_rag, audit_logger, access_manager, retention_manager


# ────────────────────────────────────────────────────────────────────────────
# USAGE EXAMPLE 1: Basic retrieval with access control
# ────────────────────────────────────────────────────────────────────────────

def example_physician_case_review():
    """Example: Physician retrieves clinical notes for patient case."""
    hipaa_rag, audit_logger, access_manager, _ = setup_hipaa_rag_for_diagnostic_council()

    # Add patient consent for treatment
    patient_id = "PAT-12345"
    patient_id_hash = __import__('hashlib').sha256(patient_id.encode()).hexdigest()[:16]

    consent = ConsentRecord(
        patient_id_hash=patient_id_hash,
        consent_type=ConsentType.TREATMENT,
        purpose_of_use=PurposeOfUse.TREATMENT,
        granted=True,
        authorized_roles=[UserRole.PHYSICIAN, UserRole.SPECIALIST],
    )
    access_manager.add_consent(consent)

    # Sample clinical note with PHI
    raw_note = """
    Patient Name: John Doe
    MRN: 12345678
    DOB: 01/15/1960
    DATE: 03/27/2026
    Phone: (555) 123-4567

    CHIEF COMPLAINT: Chest pain x 2 days

    HISTORY: 67 year old male with hypertension presents with substernal chest pain.
    Attending: Dr. Jane Smith

    PHYSICAL EXAM: BP 140/90, HR 88, RR 16, Temp 98.6F
    Cardiac: Regular rate and rhythm, no murmurs

    ASSESSMENT: Chest pain - rule out ACS.
    Plan: Troponin, EKG, admit for monitoring.
    """

    # Retrieve with access control
    chunks, access_granted, denial_reason = hipaa_rag.retrieve_with_access_control(
        user_id="DR-456",
        user_role=UserRole.PHYSICIAN,
        patient_id=patient_id,
        query="chest pain hypertension cardiac",
        notes_for_retrieval=[
            hipaa_rag.de_identify_note(raw_note, f"{patient_id}_admit_note", patient_id)
        ],
        purpose_of_use=PurposeOfUse.TREATMENT,
        top_k=3,
        justification="Patient under my care in ED",
    )

    print(f"\n✓ Access Granted: {access_granted}")
    print(f"  Retrieved {len(chunks)} chunks")
    for i, chunk in enumerate(chunks):
        print(f"\n  Chunk {i+1}:")
        print(f"    Score: {chunk.score:.3f}")
        print(f"    De-identified: {chunk.de_identified}")
        print(f"    Text: {chunk.text[:100]}...")

    # Show audit trail
    audit_trail = audit_logger.get_statistics()
    print(f"\n✓ Audit Trail:")
    print(f"  Total events: {audit_trail['total_events']}")
    print(f"  Event types: {audit_trail['event_types']}")


# ────────────────────────────────────────────────────────────────────────────
# USAGE EXAMPLE 2: Access denial and audit
# ────────────────────────────────────────────────────────────────────────────

def example_unauthorized_access_denial():
    """Example: Researcher without consent tries to access patient data."""
    hipaa_rag, audit_logger, access_manager, _ = setup_hipaa_rag_for_diagnostic_council()

    # No consent granted
    patient_id = "PAT-67890"

    raw_note = "Clinical data for patient PAT-67890"

    # Researcher tries to access without consent
    chunks, access_granted, denial_reason = hipaa_rag.retrieve_with_access_control(
        user_id="RESEARCHER-789",
        user_role=UserRole.RESEARCHER,
        patient_id=patient_id,
        query="clinical findings",
        notes_for_retrieval=[
            hipaa_rag.de_identify_note(raw_note, f"{patient_id}_note_1", patient_id)
        ],
        purpose_of_use=PurposeOfUse.RESEARCH,
        top_k=5,
        justification="",  # No justification provided
    )

    print(f"\n✗ Access Denied: {not access_granted}")
    print(f"  Reason: {denial_reason}")

    # Show audit trail shows the denial
    audit_events = audit_logger.get_audit_trail(
        event_type=__import__('src.council.hipaa_audit_logger', fromlist=['AuditEventType']).AuditEventType.ACCESS_DENIED
    )
    print(f"\n✓ Audit Trail Records {len(audit_events)} access denials")


# ────────────────────────────────────────────────────────────────────────────
# USAGE EXAMPLE 3: Integration with diagnostic council
# ────────────────────────────────────────────────────────────────────────────

def example_council_integration():
    """Example: Use HIPAA RAG in diagnostic council workflow."""
    hipaa_rag, audio_logger, access_manager, _ = setup_hipaa_rag_for_diagnostic_council()

    # Simulate physician requesting diagnostic consensus
    patient_id = "PAT-COUNCIL-001"
    user_id = "DR-CHIEF"

    # Add consent
    patient_id_hash = __import__('hashlib').sha256(patient_id.encode()).hexdigest()[:16]
    consent = ConsentRecord(
        patient_id_hash=patient_id_hash,
        consent_type=ConsentType.TREATMENT,
        purpose_of_use=PurposeOfUse.TREATMENT,
        granted=True,
        authorized_roles=[UserRole.PHYSICIAN, UserRole.SPECIALIST],
    )
    access_manager.add_consent(consent)

    # Multiple clinical notes
    raw_notes = [
        ("""Patient: De-identified
        DATE: De-identified
        Chief Complaint: Severe dyspnea, fever x 3 days
        Vitals: T 102.5F, RR 28, O2 sat 88%
        CXR: Bilateral infiltrates
        Assessment: Pneumonia, rule out sepsis""",
         NoteMetadata(
             source="Admission H&P",
             author_role="physician",
             note_date="2026-03-25",
             note_type="admission",
         )),
    ]

    # Get context for council
    context, metadata = hipaa_rag.get_retrieval_context(
        user_id=user_id,
        user_role=UserRole.PHYSICIAN,
        patient_id=patient_id,
        raw_notes=raw_notes,
        symptoms=["dyspnea", "fever", "infiltrates", "sepsis"],
        purpose_of_use=PurposeOfUse.TREATMENT,
        justification="Case presentation for diagnostic council",
        top_k=5,
    )

    print(f"\n✓ Council Context Retrieved:")
    print(f"  Access Granted: {metadata['access_granted']}")
    print(f"  Notes Processed: {metadata['notes_processed']}")
    print(f"  PHI Found and Masked: {metadata['phi_found']}")
    print(f"  De-identified: {metadata['de_identified']}")
    print(f"  Chunks Retrieved: {metadata['chunks_retrieved']}")

    if context:
        print(f"\n  Context (first 200 chars):")
        print(f"    {context[:200]}...")


# ────────────────────────────────────────────────────────────────────────────
# USAGE EXAMPLE 4: Retention policy and compliance
# ────────────────────────────────────────────────────────────────────────────

def example_retention_and_compliance():
    """Example: Check data retention and generate compliance report."""
    hipaa_rag, _, _, retention_manager = setup_hipaa_rag_for_diagnostic_council()

    # Register some data
    retention_manager.register_data(
        data_id="chunk_001",
        classification=DataClassification.WORKING,
        content="Clinical text for active case",
        notes="Active diagnostic case",
    )

    # Check compliance
    compliance = retention_manager.check_retention_compliance()
    print(f"\n✓ Retention Compliance Status: {compliance['compliance_status']}")
    print(f"  Total Monitored Items: {compliance['total_data_items']}")
    print(f"  Violations: {len(compliance['violations'])}")

    # Generate full report
    report = retention_manager.get_retention_report()
    print(f"\n✓ Retention Report:")
    print(f"  Generated: {report['report_date']}")
    print(f"  Total Data Items: {report['total_data_items']}")

    # Generate compliance report across all components
    full_compliance = hipaa_rag.get_compliance_report()
    print(f"\n✓ Full HIPAA Compliance Report:")
    print(f"  Timestamp: {full_compliance['timestamp']}")
    print(f"  Audit Integrity Verified: {full_compliance['audit_integrity']['verified']}")
    print(f"  Retention Status: {full_compliance['retention_compliance']['compliance_status']}")


# ────────────────────────────────────────────────────────────────────────────
# INTEGRATION WITH EXISTING COUNCIL CODE
# ────────────────────────────────────────────────────────────────────────────

def integrate_with_existing_council():
    """
    Shows how to wire HIPAA RAG into existing council.py code.

    In council.py, replace:
        context = compress_note(raw_note, symptoms)

    With:
        hipaa_rag = HIPAACompliantRAGPipeline()
        context, access_granted, reason = hipaa_rag.compress_note_with_privacy(
            user_id=user_id,
            user_role=UserRole.PHYSICIAN,
            patient_id=patient_id,
            raw_note=raw_note,
            symptoms=symptoms,
            purpose_of_use=PurposeOfUse.TREATMENT,
            justification="Patient case in council session",
        )
    """
    pass


if __name__ == "__main__":
    print("=" * 70)
    print("HIPAA-COMPLIANT RAG PIPELINE - USAGE EXAMPLES")
    print("=" * 70)

    print("\n" + "─" * 70)
    print("EXAMPLE 1: Physician Case Review with Access Control")
    print("─" * 70)
    example_physician_case_review()

    print("\n" + "─" * 70)
    print("EXAMPLE 2: Unauthorized Access Denial")
    print("─" * 70)
    example_unauthorized_access_denial()

    print("\n" + "─" * 70)
    print("EXAMPLE 3: Diagnostic Council Integration")
    print("─" * 70)
    example_council_integration()

    print("\n" + "─" * 70)
    print("EXAMPLE 4: Data Retention & Compliance")
    print("─" * 70)
    example_retention_and_compliance()

    print("\n" + "=" * 70)
    print("✓ All examples completed successfully!")
    print("=" * 70)
