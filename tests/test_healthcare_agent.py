"""
Integration tests for src/agent/healthcare_agent.py — HealthcareAgent
Tests cross-module interactions in simulated mode (no GPU).
"""


class TestAgentInit:
    def test_init_simulated(self, agent):
        assert agent is not None
        assert agent.simulated is True

    def test_all_tools_registered(self, agent):
        expected = {
            "fetch_patient_ehr",
            "schedule_appointment",
            "order_lab_tests",
            "notify_care_team",
            "check_drug_interactions",
            "retrieve_prior_imaging",
            "update_ehr",
            "recall_patient_memory",
            "save_patient_memory",
        }
        registered = set(agent.tools.keys())
        for tool in expected:
            assert tool in registered, f"Tool '{tool}' not registered"


class TestToolHandlers:
    def test_tool_fetch_ehr(self, agent):
        result = agent.tools["fetch_patient_ehr"](patient_id="P001")
        assert "patient" in result
        assert result["patient"]["id"] == "P001"

    def test_tool_drug_interactions(self, agent):
        result = agent.tools["check_drug_interactions"](
            medications=["Warfarin 5mg", "Aspirin 81mg"]
        )
        assert "interactions" in result
        assert len(result["interactions"]) > 0

    def test_tool_schedule(self, agent):
        result = agent.tools["schedule_appointment"](
            patient_id="P001",
            specialty="cardiology",
            urgency="routine"
        )
        assert "status" in result

    def test_tool_recall_memory_no_mem0(self, agent):
        # Without OPENAI_API_KEY, patient_memory is None
        result = agent.tools["recall_patient_memory"](
            patient_id="P001",
            query="allergies"
        )
        # Should gracefully return error, not crash
        assert "memories" in result or "error" in result

    def test_tool_save_memory_no_mem0(self, agent):
        result = agent.tools["save_patient_memory"](
            patient_id="P001",
            note="Allergic to penicillin"
        )
        assert "error" in result or "status" in result


class TestContextBuilding:
    def test_build_context_with_patient(self, agent, patient_context):
        context = agent._build_context(patient_context)
        assert "Patient:" in context
        assert context != "No context available"

    def test_build_context_none(self, agent):
        context = agent._build_context(None)
        assert context == "No context available"


class TestWorkflow:
    def test_workflow_execution(self, agent, patient_context):
        plan = agent.execute_workflow(
            "Patient has chest pain, order ECG and notify cardiology",
            patient_context
        )
        assert plan is not None
        assert len(plan.actions) > 0

    def test_process_query_simulated(self, agent, patient_context):
        result = agent.process_query(
            "What medications is this patient on?",
            patient_context
        )
        assert "response" in result
        assert result["response"] != ""
