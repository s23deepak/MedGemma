"""
Tests for src/council/council.py — DiagnosticCouncil
"""


class TestDeliberation:
    def test_produces_opinions(self, council):
        result = council.deliberate(
            symptoms=["chest pain", "shortness of breath"],
            patient_history="55yo male, hypertension"
        )
        assert len(result.opinions) == 5  # num_rollouts=5

    def test_consensus_strength_assigned(self, council):
        result = council.deliberate(
            symptoms=["fever", "cough", "fatigue"]
        )
        from src.council.council import ConsensusStrength
        valid_strengths = {
            ConsensusStrength.STRONG,
            ConsensusStrength.MODERATE,
            ConsensusStrength.WEAK,
            ConsensusStrength.SPLIT,
        }
        assert result.consensus_strength in valid_strengths

    def test_deliberation_with_history(self, council):
        result = council.deliberate(
            symptoms=["chest pain"],
            patient_history="History of coronary artery disease",
            imaging_findings="ST elevation in leads V1-V4"
        )
        assert result.consensus_diagnosis is not None

    def test_deliberation_to_dict(self, council):
        result = council.deliberate(symptoms=["headache", "nausea"])
        d = result.to_dict()
        assert "opinions" in d
        assert "consensus_diagnosis" in d
        assert "consensus_strength" in d

    def test_deliberation_history_stored(self, council):
        council.deliberate(symptoms=["fatigue"])
        council.deliberate(symptoms=["dizziness"])
        history = council.get_deliberation_history()
        assert len(history) >= 2
