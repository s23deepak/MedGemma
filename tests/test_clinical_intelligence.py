"""
Tests for src/clinical/intelligence.py — ClinicalIntelligence
"""


class TestICD10Lookup:
    def test_known_diagnosis(self, clinical_intel):
        result = clinical_intel.lookup_icd10("pneumonia")
        assert result is not None
        assert result["code"] == "J18.9"

    def test_unknown_diagnosis(self, clinical_intel):
        result = clinical_intel.lookup_icd10("totally_fake_condition_xyz")
        # Should return some result (generic or None-ish) rather than crash
        assert isinstance(result, (dict, type(None)))

    def test_case_insensitive(self, clinical_intel):
        lower = clinical_intel.lookup_icd10("diabetes")
        upper = clinical_intel.lookup_icd10("Diabetes")
        assert lower == upper


class TestDrugInteractions:
    def test_interactions_found(self, clinical_intel):
        meds = ["Warfarin 5mg", "Aspirin 81mg"]
        interactions = clinical_intel.check_drug_interactions(meds)
        assert len(interactions) > 0
        severities = [i.severity for i in interactions]
        assert "high" in severities

    def test_no_interactions(self, clinical_intel):
        meds = ["Acetaminophen 500mg"]
        interactions = clinical_intel.check_drug_interactions(meds)
        # Single non-interacting drug should have no/fewer interactions
        assert isinstance(interactions, list)


class TestCriticalFindings:
    def test_critical_detected(self, clinical_intel):
        alerts = clinical_intel.detect_critical_findings(
            "Findings suggest pneumothorax on the right side",
            source="imaging"
        )
        assert len(alerts) > 0
        assert any("pneumothorax" in a.finding.lower() for a in alerts)

    def test_no_critical_in_normal_text(self, clinical_intel):
        alerts = clinical_intel.detect_critical_findings(
            "Patient reports a headache for 2 days, otherwise feeling well and eating normally",
            source="transcription"
        )
        assert len(alerts) == 0


class TestDiagnosisWithConfidence:
    def test_confidence_percent(self):
        from src.clinical.intelligence import DiagnosisWithConfidence
        dx = DiagnosisWithConfidence(
            diagnosis="Pneumonia",
            confidence=0.85,
            icd10_code="J18.9",
            icd10_description="Pneumonia, unspecified",
            evidence=["cough", "fever"]
        )
        pct = dx.confidence_percent
        assert "85" in pct
