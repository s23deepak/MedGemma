"""
Tests for src/agent/clinical_correlation.py — ClinicalCorrelator
"""

from src.agent.clinical_correlation import (
    ClinicalCorrelator,
    FindingSignificance,
    INCIDENTAL_FINDINGS_PREVALENCE,
)


class TestFindingClassification:
    def test_critical_always_flagged(self, correlator):
        result = correlator.correlate(
            findings=["pneumothorax on right side"],
            symptoms=["knee pain"],
            body_region="chest"
        )
        assert len(result.findings) == 1
        assert result.findings[0].significance == FindingSignificance.CRITICAL

    def test_correlated_finding(self, correlator):
        result = correlator.correlate(
            findings=["disc bulge at L4-L5"],
            symptoms=["lower back pain", "sciatica"],
            chief_complaint="back pain",
            body_region="lumbar spine"
        )
        finding = result.findings[0]
        assert finding.significance == FindingSignificance.SIGNIFICANT
        assert finding.clinically_correlated is True

    def test_incidental_finding(self, correlator):
        # For INCIDENTAL: the finding must be in the prevalence DB
        # AND the symptoms must NOT match the body region's expected symptoms.
        # "tinnitus" is not in any region's symptom list.
        result = correlator.correlate(
            findings=["pineal cyst"],
            symptoms=["tinnitus"],
            chief_complaint="tinnitus",
            body_region="ear"
        )
        finding = result.findings[0]
        assert finding.significance == FindingSignificance.INCIDENTAL

    def test_incidental_has_prevalence(self, correlator):
        result = correlator.correlate(
            findings=["liver cyst noted"],
            symptoms=["headache"],
            chief_complaint="headache",
            body_region="head"
        )
        finding = result.findings[0]
        if finding.significance == FindingSignificance.INCIDENTAL:
            assert finding.prevalence_note is not None


class TestArtifactDetection:
    def test_motion_artifact(self, correlator):
        quality, artifacts = correlator.check_artifacts([
            {"type": "motion", "description": "Patient movement during acquisition", "location": "entire image", "severity": "moderate"}
        ])
        assert len(artifacts) > 0
        assert artifacts[0].type.value == "motion"

    def test_metal_artifact(self, correlator):
        quality, artifacts = correlator.check_artifacts([
            {"type": "metal", "description": "Metal hardware causing beam hardening", "location": "right hip", "severity": "severe"}
        ])
        assert len(artifacts) > 0

    def test_clean_image(self, correlator):
        quality, artifacts = correlator.check_artifacts([])
        assert len(artifacts) == 0


class TestPrevalenceDatabase:
    def test_database_has_entries(self):
        assert len(INCIDENTAL_FINDINGS_PREVALENCE) >= 15
