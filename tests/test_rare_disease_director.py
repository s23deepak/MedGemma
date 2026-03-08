"""
Unit tests for the TTT-inspired RareDiseaseDirector.

All tests run without GPU — the director operates in "no-agent / no-pubmed"
mode so the ontology and scorer are exercised without any model calls.
"""
import asyncio
import sys
import os

# Ensure repo root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from src.rare_disease.ontology import (
    get_seed_hypotheses,
    get_adjacent_diseases,
    get_disease_details,
    list_all_diseases,
)
from src.rare_disease.scorer import DiagnosticRewardScorer
from src.rare_disease.director import RareDiseaseDirector
from src.rare_disease.models import RareCaseInput


# ─────────────────────────────────────────────────────────────────────────── #
# Ontology tests                                                               #
# ─────────────────────────────────────────────────────────────────────────── #

class TestOntology:
    def test_hlh_seeded_by_classic_symptoms(self):
        symptoms = ["recurrent fever", "splenomegaly", "elevated ferritin", "cytopenias"]
        seeds = get_seed_hypotheses(symptoms)
        hlh_names = [s for s in seeds if "Hemophagocytic" in s]
        assert hlh_names, f"HLH not found in seeds: {seeds}"

    def test_aps_seeded_by_thrombosis_symptoms(self):
        symptoms = ["recurrent DVT", "thrombocytopenia", "recurrent miscarriage"]
        seeds = get_seed_hypotheses(symptoms)
        aps_names = [s for s in seeds if "Antiphospholipid" in s]
        assert aps_names, f"APS not found in seeds: {seeds}"

    def test_wilson_seeded_by_liver_and_neuro(self):
        symptoms = ["Kayser-Fleischer rings", "liver disease young patient", "neuropsychiatric symptoms"]
        seeds = get_seed_hypotheses(symptoms)
        wilson_names = [s for s in seeds if "Wilson" in s]
        assert wilson_names, f"Wilson's disease not found in seeds: {seeds}"

    def test_no_seeds_for_irrelevant_symptoms(self):
        symptoms = ["common cold", "sore throat"]
        seeds = get_seed_hypotheses(symptoms)
        # Common cold / sore throat should not match rare diseases
        assert len(seeds) == 0 or all("Gaucher" not in s for s in seeds)

    def test_adjacent_diseases_returns_same_system(self):
        adjacent = get_adjacent_diseases("Hemophagocytic Lymphohistiocytosis (HLH)")
        assert isinstance(adjacent, list)
        # HLH is rheumatologic, AOSD is also rheumatologic → should be adjacent
        aosd_names = [a for a in adjacent if "Still" in a]
        assert aosd_names, f"AOSD should be adjacent to HLH: {adjacent}"

    def test_adjacent_diseases_includes_mimics(self):
        adjacent = get_adjacent_diseases("Hemophagocytic Lymphohistiocytosis (HLH)")
        # HLH mimics include AOSD and lymphoma (but lymphoma not in ontology)
        assert len(adjacent) >= 1

    def test_get_disease_details_returns_entry(self):
        details = get_disease_details("Wilson's Disease")
        assert details is not None
        assert details["icd10"] == "E83.01"
        assert "confirmatory_tests" in details
        assert len(details["confirmatory_tests"]) > 0

    def test_get_disease_details_unknown_returns_none(self):
        assert get_disease_details("Unicorn Syndrome") is None

    def test_list_all_diseases_coverage(self):
        all_d = list_all_diseases()
        assert len(all_d) >= 30, f"Expected ≥30 diseases, got {len(all_d)}"
        # Spot-check a few key diseases
        for name_fragment in ["HLH", "Wilson", "POEMS", "Takayasu", "MELAS"]:
            matches = [d for d in all_d if name_fragment in d]
            assert matches, f"Disease containing '{name_fragment}' not found"


# ─────────────────────────────────────────────────────────────────────────── #
# Scorer tests                                                                 #
# ─────────────────────────────────────────────────────────────────────────── #

class TestDiagnosticRewardScorer:
    def setup_method(self):
        self.scorer = DiagnosticRewardScorer()

    def test_zero_reward_with_no_data(self):
        sc, es, co = self.scorer.score(
            hypothesis_name="Unknown Disease",
            symptoms=[],
            pubmed_result={},
            imaging="",
            labs={},
        )
        reward = self.scorer.compute_reward(sc, es, co)
        assert reward >= 0.0
        assert reward <= 1.0

    def test_high_evidence_strength_with_many_articles(self):
        pubmed_result = {
            "articles": [
                {"title": f"Case report {i}", "abstract": "ferritin splenomegaly cytopenias"}
                for i in range(5)
            ],
            "summary": "Multiple cases of HLH matched",
            "rare_diagnoses": ["HLH"],
        }
        _, es, _ = self.scorer.score(
            "Hemophagocytic Lymphohistiocytosis (HLH)",
            ["elevated ferritin", "cytopenias"],
            pubmed_result,
            "",
            {},
        )
        assert es >= 0.85, f"Expected high evidence_strength, got {es}"

    def test_low_evidence_strength_with_no_articles(self):
        _, es, _ = self.scorer.score(
            "Hemophagocytic Lymphohistiocytosis (HLH)",
            ["fever"],
            {},
            "",
            {},
        )
        assert es <= 0.20, f"Expected low evidence_strength with no articles, got {es}"

    def test_symptom_coverage_with_matching_symptoms(self):
        sc, _, _ = self.scorer.score(
            "Hemophagocytic Lymphohistiocytosis (HLH)",
            symptoms=["elevated ferritin", "splenomegaly", "fever", "cytopenias"],
            pubmed_result={},
            imaging="",
            labs={},
        )
        assert sc > 0.4, f"Expected coverage > 0.4 for well-matching HLH symptoms, got {sc}"

    def test_coherence_score_imaging_keyword_match(self):
        _, _, co = self.scorer.score(
            "Hemophagocytic Lymphohistiocytosis (HLH)",
            symptoms=[],
            pubmed_result={},
            imaging="hepatosplenomegaly noted on CT",
            labs={"Ferritin": "12000 (markedly elevated)", "Fibrinogen": "90 (low)"},
        )
        assert co > 0.1, f"Expected coherence > 0.1 with matching imaging/labs, got {co}"

    def test_reward_is_weighted_combination(self):
        sc, es, co = 0.8, 0.6, 0.5
        reward = self.scorer.compute_reward(sc, es, co)
        expected = 0.40 * 0.8 + 0.40 * 0.6 + 0.20 * 0.5
        assert abs(reward - expected) < 0.001

    def test_get_matching_features_returns_nonempty(self):
        features = self.scorer.get_matching_features(
            "Hemophagocytic Lymphohistiocytosis (HLH)",
            symptoms=["elevated ferritin", "splenomegaly", "cytopenias"],
            imaging="hepatosplenomegaly",
            labs={},
        )
        assert len(features) > 0

    def test_get_anti_features_for_hlh_without_data(self):
        anti = self.scorer.get_anti_features(
            "Hemophagocytic Lymphohistiocytosis (HLH)",
            symptoms=["mild fever"],
            imaging="",
            labs={},
        )
        # Should surface some high-weight absent features
        assert isinstance(anti, list)


# ─────────────────────────────────────────────────────────────────────────── #
# Director (no-agent / no-pubmed mode)                                         #
# ─────────────────────────────────────────────────────────────────────────── #

class TestRareDiseaseDirector:
    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_hunt_returns_report_with_hlh_case(self):
        director = RareDiseaseDirector(agent=None, pubmed_agent=None, max_iterations=1)
        case = RareCaseInput(
            symptoms=["recurrent fever", "splenomegaly", "elevated ferritin", "cytopenias"],
            patient_history="24yo female, recurrent episodes",
            imaging_findings="CT: hepatosplenomegaly",
            labs={"Ferritin": "14200 (markedly elevated)", "Triglycerides": "410 (elevated)"},
            vitals="T 39.4, HR 118",
            demographics={"age": "24", "sex": "female"},
            max_hypotheses=5,
        )
        report = self._run(director.hunt(case))
        assert report is not None
        assert len(report.hypotheses) >= 1
        assert report.convergence.iterations_performed >= 1
        hlh_found = any("Hemophagocytic" in h.name for h in report.hypotheses)
        assert hlh_found, f"HLH not found in top results: {[h.name for h in report.hypotheses]}"

    def test_hunt_returns_report_with_wilson_case(self):
        director = RareDiseaseDirector(agent=None, pubmed_agent=None, max_iterations=1)
        case = RareCaseInput(
            symptoms=["Kayser-Fleischer rings", "liver disease young patient", "neuropsychiatric symptoms"],
            patient_history="21yo male, psychiatric symptoms, tremor",
            labs={"Ceruloplasmin": "5 (low)", "ALT": "280 (elevated)"},
            max_hypotheses=5,
        )
        report = self._run(director.hunt(case))
        assert len(report.hypotheses) >= 1
        wilson_found = any("Wilson" in h.name for h in report.hypotheses)
        assert wilson_found, f"Wilson's not found: {[h.name for h in report.hypotheses]}"

    def test_hunt_convergence_metadata_present(self):
        director = RareDiseaseDirector(agent=None, pubmed_agent=None, max_iterations=2)
        case = RareCaseInput(
            symptoms=["recurrent DVT", "thrombocytopenia", "livedo reticularis"],
            max_hypotheses=3,
        )
        report = self._run(director.hunt(case))
        conv = report.convergence
        assert conv.iterations_performed >= 1
        assert conv.initial_hypotheses_count >= 0
        assert conv.final_hypotheses_count >= 0

    def test_hunt_all_hypotheses_have_required_fields(self):
        director = RareDiseaseDirector(agent=None, pubmed_agent=None, max_iterations=1)
        case = RareCaseInput(
            symptoms=["recurrent fever", "splenomegaly", "cytopenias"],
            max_hypotheses=3,
        )
        report = self._run(director.hunt(case))
        for h in report.hypotheses:
            assert h.name
            assert h.icd10
            assert 0.0 <= h.reward_score <= 1.0
            assert h.evidence_tier in ("well-evidenced", "some-evidence", "speculative")
            assert h.urgency in ("urgent", "elective", "low")
            assert isinstance(h.confirmatory_tests, list)

    def test_hunt_respects_max_hypotheses(self):
        director = RareDiseaseDirector(agent=None, pubmed_agent=None, max_iterations=1)
        case = RareCaseInput(
            symptoms=["recurrent fever", "splenomegaly", "cytopenias", "elevated ferritin"],
            max_hypotheses=2,
        )
        report = self._run(director.hunt(case))
        assert len(report.hypotheses) <= 2

    def test_hunt_disclaimer_always_present(self):
        director = RareDiseaseDirector(agent=None, pubmed_agent=None)
        case = RareCaseInput(symptoms=["nonspecific symptom"])
        report = self._run(director.hunt(case))
        assert "physician" in report.disclaimer.lower()

    def test_hypotheses_ranked_by_reward_descending(self):
        director = RareDiseaseDirector(agent=None, pubmed_agent=None, max_iterations=1)
        case = RareCaseInput(
            symptoms=["recurrent fever", "splenomegaly", "elevated ferritin", "cytopenias"],
            max_hypotheses=5,
        )
        report = self._run(director.hunt(case))
        rewards = [h.reward_score for h in report.hypotheses]
        assert rewards == sorted(rewards, reverse=True), "Hypotheses not sorted by reward descending"
