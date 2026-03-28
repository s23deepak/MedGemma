"""
Quick verification script to test HIPAA RAG pipeline components.

Run this to verify all components are working correctly:
    python src/hipaa/test_hipaa_rag_verification.py
"""

import sys
from datetime import datetime, timezone


def test_phi_detection():
    """Test PHI detection and de-identification."""
    print("\n" + "=" * 70)
    print("TEST 1: PHI Detection & De-Identification")
    print("=" * 70)

    from src.hipaa.hipaa_de_identification import PHIDetector

    detector = PHIDetector()

    # Test note with multiple PHI types
    test_note = """
    Patient: John Doe
    SSN: 123-45-6789
    MRN: MED-87654321
    DOB: 01/15/1960
    Contact: (555) 123-4567
    Email: john.doe@example.com
    Address: 123 Main Street
    Insurance: INS-99988877

    Chief Complaint: Chest pain x 2 days
    History of Present Illness:
    67 year old male with hypertension presents with dyspnea.
    Date: 03/27/2026

    Exam: BP 140/90, HR 88
    Assessment: Pneumonia, rule out sepsis
    """

    result = detector.de_identify(test_note)

    print(f"✓ Detected {len(result.replacements)} PHI elements")
    print(f"  Categories: {result.to_dict()['categories_found']}")
    print(f"\n  Original (first 200 chars):\n  {test_note[:200]}...")
    print(f"\n  De-identified (first 200 chars):\n  {result.de_identified_text[:200]}...")
    return result.phi_detected and len(result.replacements) > 0


def test_audit_logging():
    """Test HIPAA audit logger."""
    print("\n" + "=" * 70)
    print("TEST 2: Audit Logging")
    print("=" * 70)

    from src.hipaa.hipaa_audit_logger import (
        HIPAAAuditLogger,
        AuditEventType,
        AuditSeverity,
    )

    logger = HIPAAAuditLogger()

    # Log various events
    logger.log_event(
        event_type=AuditEventType.AUTHENTICATION,
        action="User login",
        user_id="DR-123",
        status="success",
    )

    logger.log_data_access(
        user_id="DR-123",
        user_role="physician",
        resource_id="PAT-456",
        action="retrieved",
        result_count=5,
    )

    logger.log_access_denied(
        user_id="RESEARCHER-789",
        user_role="researcher",
        resource_id="PAT-456",
        reason="No valid consent",
    )

    stats = logger.get_statistics()
    print(f"✓ Logged {stats['total_events']} events")
    print(f"  Event types: {stats['event_types']}")
    print(f"  Access denials: {stats['access_denials']}")

    # Verify integrity
    integrity_ok = logger.verify_audit_integrity()
    print(f"✓ Audit integrity verified: {integrity_ok}")

    return stats['total_events'] >= 3 and integrity_ok


def test_access_control():
    """Test HIPAA access control."""
    print("\n" + "=" * 70)
    print("TEST 3: Access Control & Consent")
    print("=" * 70)

    from src.hipaa.hipaa_access_control import (
        AccessControlManager,
        UserRole,
        PurposeOfUse,
        ConsentType,
        ConsentRecord,
    )
    import hashlib

    acl = AccessControlManager()

    # Grant consent
    patient_id = "PAT-999"
    patient_hash = hashlib.sha256(patient_id.encode()).hexdigest()[:16]

    consent = ConsentRecord(
        patient_id_hash=patient_hash,
        consent_type=ConsentType.TREATMENT,
        purpose_of_use=PurposeOfUse.TREATMENT,
        granted=True,
        authorized_roles=[UserRole.PHYSICIAN, UserRole.SPECIALIST],
    )
    acl.add_consent(consent)

    # Test access: should allow
    can_access_doc, reason = acl.can_access(
        user_id="DR-123",
        user_role=UserRole.PHYSICIAN,
        patient_id_hash=patient_hash,
        purpose=PurposeOfUse.TREATMENT,
        record_count=5,
    )
    print(f"✓ Physician access to treatment data: {can_access_doc}")

    # Test access: should deny (no consent)
    can_access_research, reason = acl.can_access(
        user_id="RESEARCHER-789",
        user_role=UserRole.RESEARCHER,
        patient_id_hash=patient_hash,
        purpose=PurposeOfUse.RESEARCH,
        record_count=5,
    )
    print(f"✓ Researcher access without consent denied: {not can_access_research}")
    print(f"  Reason: {reason}")

    return can_access_doc and not can_access_research


def test_retention_management():
    """Test HIPAA data retention."""
    print("\n" + "=" * 70)
    print("TEST 4: Data Retention Management")
    print("=" * 70)

    from src.hipaa.hipaa_retention_policy import (
        HIPAADataRetentionManager,
        DataClassification,
    )

    retention = HIPAADataRetentionManager()

    # Register some data
    retained = retention.register_data(
        data_id="CHUNK-001",
        classification=DataClassification.WORKING,
        content="Sample clinical data",
    )

    print(f"✓ Registered {retained.data_id}")
    print(f"  Classification: {retained.classification.value}")
    print(f"  Size: {retained.size_bytes} bytes")
    print(f"  Status: {retained.retention_status.value}")

    # Check compliance
    compliance = retention.check_retention_compliance()
    print(f"✓ Compliance status: {compliance['compliance_status']}")
    print(f"  Total items: {compliance['total_data_items']}")

    # Get retention report
    report = retention.get_retention_report()
    print(f"✓ Report generated: {report['report_date']}")
    print(f"  Items by classification: {report['by_classification']}")

    return compliance['compliance_status'] == 'compliant'


def test_hipaa_rag_wrapper():
    """Test HIPAA RAG wrapper."""
    print("\n" + "=" * 70)
    print("TEST 5: HIPAA RAG Wrapper Integration")
    print("=" * 70)

    from src.hipaa.hipaa_rag_wrapper import HIPAACompliantRAGPipeline
    from src.hipaa.hipaa_access_control import (
        UserRole,
        PurposeOfUse,
        ConsentType,
        ConsentRecord,
    )
    import hashlib

    # Setup
    pipeline = HIPAACompliantRAGPipeline()

    # Add consent
    patient_id = "PAT-INTEGRATION"
    patient_hash = hashlib.sha256(patient_id.encode()).hexdigest()[:16]

    consent = ConsentRecord(
        patient_id_hash=patient_hash,
        consent_type=ConsentType.TREATMENT,
        purpose_of_use=PurposeOfUse.TREATMENT,
        granted=True,
        authorized_roles=[UserRole.PHYSICIAN],
    )
    pipeline.access_manager.add_consent(consent)

    # Test de-identification
    raw_note = """
    Patient John Doe, MRN 123456, age 72
    Chief Complaint: Chest pain
    History: 72 year old with HTN
    """

    hipaa_note = pipeline.de_identify_note(raw_note, patient_id, patient_id)
    print(f"✓ De-identified note")
    print(f"  PHI detected: {hipaa_note.phi_detected()}")
    print(f"  Categories: {hipaa_note.phi_categories()}")

    # Test retrieval with access control
    chunks, granted, reason = pipeline.retrieve_with_access_control(
        user_id="DR-TEST",
        user_role=UserRole.PHYSICIAN,
        patient_id=patient_id,
        query="chest pain cardiac",
        notes_for_retrieval=[hipaa_note],
        purpose_of_use=PurposeOfUse.TREATMENT,
        top_k=3,
        justification="Test case",
    )

    print(f"✓ Access granted: {granted}")
    print(f"  Chunks retrieved: {len(chunks)}")

    # Check audit log
    stats = pipeline.audit_logger.get_statistics()
    print(f"✓ Audit events logged: {stats['total_events']}")

    return granted and stats['total_events'] > 0


def main():
    """Run all verification tests."""
    print("\n" + "=" * 70)
    print("HIPAA RAG PIPELINE - VERIFICATION TESTS")
    print("=" * 70)

    tests = [
        ("PHI Detection", test_phi_detection),
        ("Audit Logging", test_audit_logging),
        ("Access Control", test_access_control),
        ("Retention Management", test_retention_management),
        ("HIPAA RAG Wrapper", test_hipaa_rag_wrapper),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ ERROR in {test_name}: {e}")
            import traceback

            traceback.print_exc()
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{len(results)} tests passed")

    if passed == len(results):
        print("\n✓ All tests passed! HIPAA RAG pipeline is ready for integration.")
        return 0
    else:
        print(f"\n✗ {len(results) - passed} test(s) failed. Review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
