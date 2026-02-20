"""
Tests for src/ehr/fhir_mock.py — MockFHIRServer
"""


class TestListPatients:
    def test_returns_all_patients(self, fhir_server):
        patients = fhir_server.list_patients()
        assert len(patients) >= 2, f"Expected ≥2 patients, got {len(patients)}"

    def test_patient_has_required_fields(self, fhir_server):
        patients = fhir_server.list_patients()
        for p in patients:
            assert "id" in p
            assert "name" in p


class TestGetPatientSummary:
    def test_returns_summary(self, fhir_server):
        summary = fhir_server.get_patient_summary("P001")
        assert summary is not None
        assert "patient" in summary
        assert "conditions" in summary
        assert "medications" in summary

    def test_patient_has_demographics(self, fhir_server):
        summary = fhir_server.get_patient_summary("P001")
        patient = summary["patient"]
        for field in ("id", "name", "age", "gender"):
            assert field in patient, f"Missing field: {field}"

    def test_unknown_patient_returns_none(self, fhir_server):
        result = fhir_server.get_patient_summary("NONEXISTENT")
        assert result is None


class TestUpdatePatientRecord:
    def test_add_condition(self, fhir_server):
        result = fhir_server.update_patient_record(
            "P001",
            new_conditions=["Test Condition"]
        )
        assert result is not None
        # Verify the condition was added
        summary = fhir_server.get_patient_summary("P001")
        condition_names = [c.get("name", "") for c in summary.get("conditions", [])]
        assert "Test Condition" in condition_names
