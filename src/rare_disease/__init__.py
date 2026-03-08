"""
Rare Disease Director module — TTT-inspired iterative diagnostic hunt.

Usage:
    from src.rare_disease import get_rare_disease_director, RareCaseInput

    director = get_rare_disease_director()
    director.agent = medgemma_agent   # set after model load
    director.pubmed_agent = pubmed    # set after pubmed init

    report = await director.hunt(RareCaseInput(symptoms=[...], ...))
"""
from .director import RareDiseaseDirector, get_rare_disease_director
from .models import RareCaseInput, RareDiseaseHypothesis, RareDiseaseReport, TTTConvergenceMetadata
from .ontology import get_seed_hypotheses, get_adjacent_diseases, get_disease_details

__all__ = [
    "RareDiseaseDirector",
    "get_rare_disease_director",
    "RareCaseInput",
    "RareDiseaseHypothesis",
    "RareDiseaseReport",
    "TTTConvergenceMetadata",
    "get_seed_hypotheses",
    "get_adjacent_diseases",
    "get_disease_details",
]
