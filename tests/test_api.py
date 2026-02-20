"""
End-to-end API tests using FastAPI TestClient.
No live server needed — tests run in-process.
"""

import os
os.environ["SIMULATED_MODE"] = "true"


class TestHealthCheck:
    def test_health_endpoint(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "agent_loaded" in data
        assert "mem0_available" in data


class TestPatientEndpoints:
    def test_list_patients(self, client):
        resp = client.get("/api/patients")
        assert resp.status_code == 200
        data = resp.json()
        assert "patients" in data
        assert len(data["patients"]) >= 1

    def test_get_patient(self, client):
        resp = client.get("/api/patients/P001")
        assert resp.status_code == 200
        data = resp.json()
        assert "patient" in data


class TestEncounterEndpoints:
    def test_start_encounter(self, client):
        resp = client.post(
            "/api/encounters/start",
            data={"patient_id": "P001"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data


class TestFeaturePages:
    def test_history_page(self, client):
        resp = client.get("/history")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_compliance_page(self, client):
        resp = client.get("/compliance")
        assert resp.status_code == 200

    def test_council_page(self, client):
        resp = client.get("/council")
        assert resp.status_code == 200

    def test_patient_portal_page(self, client):
        resp = client.get("/patient-portal")
        assert resp.status_code == 200


class TestComplianceAPI:
    def test_compliance_check(self, client):
        resp = client.post("/api/compliance/check")
        assert resp.status_code == 200
        data = resp.json()
        assert "compliance_rate" in data


class TestCouncilAPI:
    def test_council_deliberate(self, client):
        resp = client.post(
            "/api/council/deliberate",
            json={
                "symptoms": ["chest pain", "shortness of breath"],
                "patient_history": "55yo male, hypertension"
            }
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "opinions" in data or "consensus_diagnosis" in data
