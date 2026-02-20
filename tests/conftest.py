"""
Shared pytest fixtures for MedGemma test suite.
All fixtures work in simulated/mock mode — no GPU or API keys needed.
"""

import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── EHR ──────────────────────────────────────────────────────

@pytest.fixture
def fhir_server():
    """Fresh MockFHIRServer instance."""
    from src.ehr.fhir_mock import MockFHIRServer
    return MockFHIRServer()


@pytest.fixture
def patient_context(fhir_server):
    """Patient P002 summary (has conditions + medications)."""
    return fhir_server.get_patient_summary("P002")


# ── Agent ────────────────────────────────────────────────────

@pytest.fixture
def agent():
    """HealthcareAgent in simulated mode (no GPU)."""
    from src.agent import HealthcareAgent
    return HealthcareAgent(simulated=True)


# ── Clinical Intelligence ────────────────────────────────────

@pytest.fixture
def clinical_intel():
    from src.clinical.intelligence import ClinicalIntelligence
    return ClinicalIntelligence()


# ── Clinical Correlation ─────────────────────────────────────

@pytest.fixture
def correlator():
    from src.agent.clinical_correlation import ClinicalCorrelator
    return ClinicalCorrelator()


# ── SOAP ─────────────────────────────────────────────────────

@pytest.fixture
def soap_generator():
    from src.soap.generator import SOAPGenerator
    return SOAPGenerator()


# ── Compliance ───────────────────────────────────────────────

@pytest.fixture
def compliance_checker():
    from src.compliance.compliance import SOAPComplianceChecker
    return SOAPComplianceChecker()


# ── Council ──────────────────────────────────────────────────

@pytest.fixture
def council():
    from src.council.council import DiagnosticCouncil
    return DiagnosticCouncil(num_rollouts=5)


# ── Patient Portal ───────────────────────────────────────────

@pytest.fixture
def patient_assistant():
    from src.portal.patient_portal import PatientAssistant
    return PatientAssistant()


# ── History ──────────────────────────────────────────────────

@pytest.fixture
def history_service(fhir_server):
    from src.history.history import PatientHistoryService
    return PatientHistoryService(fhir_server=fhir_server)


# ── FastAPI Test Client ──────────────────────────────────────

@pytest.fixture
def client():
    """FastAPI TestClient — manually init globals since lifespan is async."""
    import os
    os.environ["SIMULATED_MODE"] = "true"
    import main
    from src.ehr.fhir_mock import MockFHIRServer
    from src.soap.generator import SOAPGenerator
    # Manually init globals that lifespan would set
    main.fhir_server = MockFHIRServer()
    main.soap_generator = SOAPGenerator()
    from fastapi.testclient import TestClient
    return TestClient(main.app)
