"""
Tests for src/compliance/compliance.py — SOAPComplianceChecker
"""


class TestComplianceCheck:
    def test_check_runs(self, compliance_checker):
        report = compliance_checker.run_compliance_check()
        assert report is not None

    def test_compliance_rate_valid(self, compliance_checker):
        report = compliance_checker.run_compliance_check()
        rate = report.compliance_rate
        assert 0.0 <= rate <= 100.0

    def test_flags_have_required_fields(self, compliance_checker):
        report = compliance_checker.run_compliance_check()
        for flag in report.flags:
            assert flag.patient_id != ""
            assert flag.severity is not None
            assert flag.title != ""

    def test_total_documents_positive(self, compliance_checker):
        report = compliance_checker.run_compliance_check()
        assert report.total_soap_documents > 0

    def test_report_to_dict(self, compliance_checker):
        report = compliance_checker.run_compliance_check()
        d = report.to_dict()
        assert "compliance_rate" in d
        assert "flags" in d
        assert "total_documents" in d
