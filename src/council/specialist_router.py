"""
Specialist routing logic for the diagnostic council.

Determines when to invoke specialist sub-councils based on:
- Main council consensus confidence
- Number of dissenting opinions
- Diagnostic terms identified (keyword-based specialty inference)
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Keyword mappings for specialty inference
SPECIALTY_KEYWORDS = {
    "cardiology": [
        "chest pain", "chest discomfort", "arrhythmia", "atrial fibrillation", "afib",
        "myocardial infarction", "mi", "acute coronary", "acs", "heart attack",
        "cor pulmonale", "pulmonary hypertension", "endocarditis", "pericarditis",
        "myocarditis", "heart failure", "chf", "cardiomyopathy", "troponin", "bnp",
        "ecg changes", "st elevation", "t wave", "left bundle", "cardiogenic", "cardiac"
    ],
    "rheumatology": [
        "lupus", "sle", "systemic lupus", "rheumatoid", "rheumatoid arthritis", "ra",
        "autoimmune", "vasculitis", "anti-nuclear", "ana", "rf+", "rheumatoid factor",
        "scleroderma", "sjögren", "sjögrens", "connective tissue", "inflammatory arthritis",
        "polyarticular", "arthralgia", "arthritis", "immune complex"
    ],
    "neurology": [
        "seizure", "epilepsy", "stroke", "cva", "tia", "transient ischemic",
        "encephalitis", "encephalopathy", "meningitis", "cns", "central nervous",
        "migraine", "headache", "altered mental status", "focal deficit",
        "weakness", "paralysis", "neuropathy", "guillain-barré", "eeg abnormality",
        "spinal cord", "myelitis", "transverse myelitis", "alzheimer", "parkinson"
    ],
    "infectious_disease": [
        "sepsis", "bacteremia", "fever of unknown", "fou", "fever", "infection",
        "pneumonia", "tuberculosis", "tb", "hiv", "aids", "viral load",
        "culture positive", "pcr positive", "endocarditis", "meningitis",
        "fungal", "parasitic", "empiric antibiotics", "antibiotic", "pathogenic"
    ],
}


class SpecialistRouter:
    """Routes cases to appropriate specialist sub-councils."""

    def __init__(self):
        """Initialize the specialist router."""
        self.specialty_keywords = SPECIALTY_KEYWORDS

    def should_refer_to_specialist(
        self,
        consensus_diagnosis: Optional[str],
        consensus_confidence: float,
        consensus_strength: str,
        num_dissenting: int,
        total_opinions: int,
    ) -> bool:
        """
        Determine if a case should be referred to specialist sub-councils.

        Triggers:
        - Confidence < 60% AND dissenting opinions exist
        - Split consensus (multiple diagnoses tied)
        - Weak consensus with moderate urgency

        Args:
            consensus_diagnosis: Main consensus diagnosis
            consensus_confidence: Confidence score (0-1)
            consensus_strength: "strong", "moderate", "weak", or "split"
            num_dissenting: Number of dissenting opinions
            total_opinions: Total number of opinions

        Returns:
            True if specialist consultation recommended
        """
        # Always escalate split consensus to specialists
        if consensus_strength == "split":
            logger.info("Split consensus detected — escalating to specialists")
            return True

        # Confidence < 60% with dissenting opinions
        if consensus_confidence < 0.6 and num_dissenting > 0:
            logger.info(f"Low confidence ({consensus_confidence:.0%}) with dissent — escalating")
            return True

        # Weak consensus with >25% dissent rate
        if consensus_strength == "weak" and num_dissenting / max(total_opinions, 1) > 0.25:
            logger.info(f"Weak consensus with {num_dissenting}/{total_opinions} dissent — escalating")
            return True

        return False

    def infer_specialty_from_diagnosis(self, diagnosis: Optional[str]) -> Optional[str]:
        """
        Infer specialty based on diagnosis keywords.

        Args:
            diagnosis: The diagnosis string

        Returns:
            Specialty name if keywords match, else None
        """
        if not diagnosis:
            return None

        diagnosis_lower = diagnosis.lower()

        for specialty, keywords in self.specialty_keywords.items():
            if any(keyword in diagnosis_lower for keyword in keywords):
                logger.info(f"Inferred specialty '{specialty}' from diagnosis '{diagnosis}'")
                return specialty

        return None

    def infer_specialty_from_symptoms(self, symptoms: list[str]) -> list[str]:
        """
        Infer applicable specialties based on symptom keywords.

        Args:
            symptoms: List of presenting symptoms

        Returns:
            List of specialty names (may be multiple)
        """
        symptoms_lower = " ".join(symptoms).lower()
        matching_specialties = set()

        for specialty, keywords in self.specialty_keywords.items():
            if any(keyword in symptoms_lower for keyword in keywords):
                matching_specialties.add(specialty)

        inferred = list(matching_specialties)
        if inferred:
            logger.info(f"Inferred specialties from symptoms: {inferred}")
        return inferred

    def recommend_specialists(
        self,
        consensus_diagnosis: Optional[str],
        symptoms: list[str],
        consensus_strength: str,
        num_dissenting: int,
    ) -> list[str]:
        """
        Recommend which specialists to consult.

        Strategy:
        1. Infer from diagnosis if consensus diagnosis available
        2. Infer from symptoms if no diagnosis or weak inference
        3. Always include Internal Medicine as fallback

        Args:
            consensus_diagnosis: Main consensus diagnosis
            symptoms: List of symptoms
            consensus_strength: Strength of consensus
            num_dissenting: Number of dissenting opinions

        Returns:
            List of recommended specialties
        """
        specialists = set()

        # Primary: infer from diagnosis
        if consensus_diagnosis:
            inferred_specialty = self.infer_specialty_from_diagnosis(consensus_diagnosis)
            if inferred_specialty:
                specialists.add(inferred_specialty)

        # Secondary: infer from symptoms if diagnosis inference weak
        if len(specialists) == 0 or consensus_strength == "split":
            symptom_specialties = self.infer_specialty_from_symptoms(symptoms)
            specialists.update(symptom_specialties)

        # Tertiary: if still no matches, recommend internal medicine
        if not specialists:
            specialists.add("internal_medicine")

        # Always include IM as secondary opinion if dissent exists
        if num_dissenting > 1 and "internal_medicine" not in specialists:
            specialists.add("internal_medicine")

        return sorted(list(specialists))

    def get_specialist_context(self, specialty: str, data: dict) -> str:
        """
        Generate domain-specific context for specialist prompt.

        Args:
            specialty: Specialty name
            data: Case data (diagnoses, findings, labs, etc.)

        Returns:
            Domain-specific context string
        """
        context_templates = {
            "cardiology": (
                "Consider:\n"
                "• Acute vs chronic presentation\n"
                "• Risk stratification (TIMI, HEART scores)\n"
                "• ECG changes and mechanism\n"
                "• Biomarker evolution (troponin, BNP kinetics)\n"
            ),
            "rheumatology": (
                "Consider:\n"
                "• Serologic pattern (ANA, RF, anti-CCP positive/negative)\n"
                "• Polyarticular vs monoarticular presentation\n"
                "• Systemic vs musculoskeletal involvement\n"
                "• Complement consumption (C3/C4) suggesting active disease\n"
            ),
            "neurology": (
                "Consider:\n"
                "• Focal vs diffuse CNS involvement\n"
                "• Acute vs subacute progression\n"
                "• EEG findings and seizure semiology if applicable\n"
                "• MRI brain/spine localization\n"
            ),
            "infectious_disease": (
                "Consider:\n"
                "• Culture positivity and sensitivities\n"
                "• Host immune status (immunocompetent vs immunocompromised)\n"
                "• Empiric therapy duration and de-escalation opportunity\n"
                "• Geographic epidemiology and exposure history\n"
            ),
            "internal_medicine": (
                "Consider:\n"
                "• Clinical likelihood ratios and pretest probability\n"
                "• Cost-benefit of diagnostic testing\n"
                "• Incidental findings vs primary diagnosis\n"
                "• Outpatient vs inpatient management pathway\n"
            ),
        }

        return context_templates.get(specialty.lower(), "Consider clinical context.")


# Singleton instance
_router: Optional[SpecialistRouter] = None


def get_specialist_router() -> SpecialistRouter:
    """Get or create the SpecialistRouter singleton."""
    global _router
    if _router is None:
        _router = SpecialistRouter()
    return _router
