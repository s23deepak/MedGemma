"""
Tests for src/portal/patient_portal.py — PatientAssistant
"""

from src.portal.patient_portal import EMERGENCY_KEYWORDS, QueryCategory


class TestEmergencyDetection:
    def test_chest_pain_triggers_emergency(self, patient_assistant):
        result = patient_assistant.ask("P001", "I'm having chest pain")
        assert result.category == QueryCategory.EMERGENCY

    def test_all_emergency_keywords(self, patient_assistant):
        for keyword in EMERGENCY_KEYWORDS:
            result = patient_assistant.ask("P001", f"I am experiencing {keyword}")
            assert result.category == QueryCategory.EMERGENCY, (
                f"Keyword '{keyword}' did not trigger EMERGENCY"
            )


class TestNormalQuestions:
    def test_normal_question_answered(self, patient_assistant):
        result = patient_assistant.ask("P001", "When is my next appointment?")
        assert result.response != ""
        assert result.category != QueryCategory.EMERGENCY

    def test_query_categorization_medication(self, patient_assistant):
        result = patient_assistant.ask("P001", "What are the side effects of my medication?")
        assert result.category == QueryCategory.MEDICATION


class TestGuardrails:
    def test_restricted_topic_flagged(self, patient_assistant):
        result = patient_assistant.ask("P001", "Should I stop taking medication?")
        # Should either warn or flag requires_followup
        assert result.requires_followup or "doctor" in result.response.lower() or "provider" in result.response.lower()


class TestQueryHistory:
    def test_queries_stored(self, patient_assistant):
        patient_assistant.ask("P001", "What is my diagnosis?")
        patient_assistant.ask("P001", "When should I come back?")
        history = patient_assistant.get_query_history("P001")
        assert len(history) >= 2

    def test_appointment_summary(self, patient_assistant):
        summary = patient_assistant.get_appointment_summary("P001")
        assert isinstance(summary, dict)
