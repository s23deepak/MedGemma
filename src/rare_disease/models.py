"""
Pydantic models for the TTT-inspired Rare Disease Director.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RareCaseInput(BaseModel):
    """Input payload for a rare disease diagnostic hunt."""

    symptoms: list[str] = Field(..., description="List of presenting symptoms")
    patient_history: str = Field(
        default="",
        description="Relevant patient history, PMH, comorbidities",
    )
    imaging_findings: str = Field(
        default="",
        description="Imaging findings from radiology reports",
    )
    labs: dict[str, str] = Field(
        default_factory=dict,
        description="Lab values as key-value strings, e.g. {'WBC': '12.3', 'Hgb': '8.1'}",
    )
    vitals: str = Field(default="", description="Vital signs string")
    demographics: dict[str, str] = Field(
        default_factory=dict,
        description="Patient demographics, e.g. {'age': '34', 'sex': 'female'}",
    )
    raw_note: str = Field(
        default="",
        description="Full clinical note for RAG context compression (optional)",
    )
    max_hypotheses: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum hypothesis count to return",
    )


class RareDiseaseHypothesis(BaseModel):
    """A single rare disease hypothesis with scoring and directional guidance."""

    name: str
    icd10: str
    reasoning: str
    matching_features: list[str] = Field(default_factory=list)
    anti_features: list[str] = Field(
        default_factory=list,
        description="Features present in this patient that argue against this diagnosis",
    )
    symptom_coverage: float = Field(ge=0.0, le=1.0)
    evidence_strength: float = Field(ge=0.0, le=1.0)
    coherence_score: float = Field(ge=0.0, le=1.0)
    reward_score: float = Field(ge=0.0, le=1.0)
    evidence_tier: Literal["well-evidenced", "some-evidence", "speculative"]
    confirmatory_tests: list[str] = Field(default_factory=list)
    specialist_type: str
    urgency: Literal["urgent", "elective", "low"]
    pubmed_citations: list[str] = Field(default_factory=list)


class TTTConvergenceMetadata(BaseModel):
    """Metadata describing how the TTT iterative loop converged."""

    iterations_performed: int
    converged: bool
    initial_hypotheses_count: int
    final_hypotheses_count: int
    convergence_reward: float
    expansion_rounds: list[str] = Field(
        default_factory=list,
        description="Expansion strategies applied per iteration",
    )


class RareDiseaseReport(BaseModel):
    """Full directional report for physician review."""

    hypotheses: list[RareDiseaseHypothesis]
    convergence: TTTConvergenceMetadata
    disclaimer: str = (
        "This analysis provides directional guidance only and does not constitute a "
        "diagnosis. All findings must be evaluated and validated by a qualified "
        "physician. Clinical context, physical examination, and physician judgment "
        "take precedence over AI suggestions."
    )
    generated_at: datetime = Field(default_factory=datetime.utcnow)
