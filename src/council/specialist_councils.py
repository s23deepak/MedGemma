"""
Specialist sub-councils for domain-specific diagnostic deliberation.

Five specialized LangGraphs that can be invoked when the main council
encounters weak consensus or complex cases:
- Cardiology Council: CAD, arrhythmia, heart failure differentials
- Rheumatology Council: Autoimmune disease clustering, serology
- Neurology Council: CNS localization, seizure differential, EEG
- Infectious Disease Council: Pathogen narrowing, culture correlation
- IMU (Internal Medicine/Unspecialized): General medicine fallback
"""

from __future__ import annotations

import json
import logging
import random
import uuid
from dataclasses import dataclass
from typing import Literal, Optional

logger = logging.getLogger(__name__)


@dataclass
class SpecialistOpinion:
    """A single specialist council opinion."""
    opinion_id: str
    specialty: str
    diagnosis: str
    confidence: float
    reasoning: str
    differential_diagnoses: list[str]
    severity_assessment: str  # "low_acuity", "intermediate", or "high_acuity"
    specialist_recommendation: str
    urgency: str  # routine, urgent, emergent
    evidence_tier: str  # "well-established", "emerging", "speculative"


@dataclass
class SpecialistDeliberation:
    """Result of a specialist sub-council deliberation."""
    specialty: str
    case_summary: str
    opinions: list[SpecialistOpinion]
    consensus_diagnosis: Optional[str]
    consensus_confidence: float
    consensus_reasoning: str
    recommended_workup: list[str]
    specialist_referral_indicated: bool


class SpecialistCouncilBase:
    """Base class for specialist councils."""

    def __init__(self, agent=None, num_rollouts: int = 3):
        """
        Initialize specialist council.

        Args:
            agent: MedGemma agent for generating opinions
            num_rollouts: Number of parallel opinions to generate
        """
        self.agent = agent
        self.num_rollouts = num_rollouts
        self.specialty = "unknown"

    def generate_opinion(
        self,
        case_info: dict,
        opinion_num: int,
        specialty_context: str = "",
    ) -> SpecialistOpinion:
        """
        Generate a single specialist opinion.

        Args:
            case_info: Case information dict
            opinion_num: Opinion index (for deterministic fallback)
            specialty_context: Domain-specific context

        Returns:
            SpecialistOpinion
        """
        symptoms = case_info.get("symptoms", [])
        history = case_info.get("patient_history", "")
        imaging = case_info.get("imaging_findings", "")
        labs = case_info.get("labs", {})

        opinion_id = f"{self.specialty.upper()}-OPINION-{opinion_num + 1}"

        if self.agent is None:
            # Fallback mock response
            return SpecialistOpinion(
                opinion_id=opinion_id,
                specialty=self.specialty,
                diagnosis="Diagnosis (mock fallback)",
                confidence=0.5 + random.random() * 0.3,
                reasoning="Mock specialist assessment",
                differential_diagnoses=["Alt1", "Alt2"],
                severity_assessment="intermediate",
                specialist_recommendation="Requires clinical correlation",
                urgency="routine",
                evidence_tier="speculative",
            )

        # Build specialist prompt
        prompt = self._build_specialist_prompt(
            symptoms=symptoms,
            history=history,
            imaging=imaging,
            labs=labs,
            specialty_context=specialty_context,
        )

        try:
            if hasattr(self.agent, "process_query"):
                result = self.agent.process_query(query=prompt, patient_context=None)
                response_text = result.get("response", "")
            else:
                response_text = self.agent.chat(prompt)

            # Parse JSON response
            import re
            json_match = re.search(r"```(?:json)?(.*?)```", response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(1)
            response_text = response_text.replace("[Simulated] Processed query: ", "").strip()

            opinion_dict = json.loads(response_text)

            return SpecialistOpinion(
                opinion_id=opinion_id,
                specialty=self.specialty,
                diagnosis=opinion_dict.get("diagnosis", "Unknown"),
                confidence=float(opinion_dict.get("confidence", 0.5)),
                reasoning=opinion_dict.get("reasoning", ""),
                differential_diagnoses=opinion_dict.get("differentials", []),
                severity_assessment=opinion_dict.get("severity", "intermediate"),
                specialist_recommendation=opinion_dict.get("recommendation", ""),
                urgency=opinion_dict.get("urgency", "routine"),
                evidence_tier=opinion_dict.get("evidence_tier", "speculative"),
            )
        except Exception as e:
            logger.error(f"Error generating specialist opinion for {self.specialty}: {e}")
            return SpecialistOpinion(
                opinion_id=opinion_id,
                specialty=self.specialty,
                diagnosis="Unable to assess (error)",
                confidence=0.0,
                reasoning=f"Error: {str(e)}",
                differential_diagnoses=[],
                severity_assessment="intermediate",
                specialist_recommendation="Clinical review recommended",
                urgency="routine",
                evidence_tier="speculative",
            )

    def _build_specialist_prompt(
        self,
        symptoms: list[str],
        history: str,
        imaging: str,
        labs: dict,
        specialty_context: str,
    ) -> str:
        """Build domain-specific prompt. Override in subclasses."""
        prompt = (
            f"You are a board-certified {self.specialty} specialist participating in a diagnostic council.\n"
            f"Analyze from a {self.specialty} perspective and provide your assessment:\n"
            f"Symptoms: {', '.join(symptoms)}\n"
            f"History: {history}\n"
            f"Imaging: {imaging}\n"
        )
        if labs:
            prompt += f"Labs: {', '.join(f'{k}={v}' for k, v in labs.items())}\n"
        if specialty_context:
            prompt += f"\n{specialty_context}\n"

        prompt += (
            f"\nProvide your diagnostic assessment as JSON:\n"
            f'{{\n'
            f'  "diagnosis": "Primary diagnosis",\n'
            f'  "confidence": 0.85,\n'
            f'  "reasoning": "Your specialist reasoning",\n'
            f'  "differentials": ["Alt1", "Alt2"],\n'
            f'  "severity": "low_acuity|intermediate|high_acuity",\n'
            f'  "recommendation": "Specialist recommendation",\n'
            f'  "urgency": "routine|urgent|emergent",\n'
            f'  "evidence_tier": "well-established|emerging|speculative"\n'
            f'}}\n'
        )
        return prompt

    def deliberate(self, case_info: dict) -> SpecialistDeliberation:
        """Run specialist council deliberation."""
        opinions = []
        for i in range(self.num_rollouts):
            opinion = self.generate_opinion(case_info, i)
            opinions.append(opinion)

        # Calculate consensus
        diagnosis_counts = {}
        for op in opinions:
            diagnosis_counts[op.diagnosis] = diagnosis_counts.get(op.diagnosis, 0) + 1

        if diagnosis_counts:
            top_diagnosis = max(diagnosis_counts.keys(), key=lambda d: diagnosis_counts[d])
            top_confidences = [op.confidence for op in opinions if op.diagnosis == top_diagnosis]
            consensus_confidence = sum(top_confidences) / len(top_confidences) if top_confidences else 0.0
        else:
            top_diagnosis = None
            consensus_confidence = 0.0

        # Collect all recommended tests
        all_tests = set()
        for op in opinions:
            # Extract tests from specialty context (simplified)
            pass

        consensus_reasoning = (
            f"Based on {len(opinions)} specialist assessments, "
            f"the consensus diagnosis is '{top_diagnosis}' with {consensus_confidence:.0%} confidence."
        )

        referral_indicated = consensus_confidence < 0.6 or any(
            op.urgency == "emergent" for op in opinions
        )

        return SpecialistDeliberation(
            specialty=self.specialty,
            case_summary=f"Case with symptoms: {', '.join(case_info.get('symptoms', []))}",
            opinions=opinions,
            consensus_diagnosis=top_diagnosis,
            consensus_confidence=consensus_confidence,
            consensus_reasoning=consensus_reasoning,
            recommended_workup=list(all_tests),
            specialist_referral_indicated=referral_indicated,
        )


class CardiologyCouncil(SpecialistCouncilBase):
    """Cardiology specialist council."""

    def __init__(self, agent=None):
        super().__init__(agent, num_rollouts=3)
        self.specialty = "cardiology"

    def _build_specialist_prompt(self, symptoms, history, imaging, labs, specialty_context):
        prompt = super()._build_specialist_prompt(symptoms, history, imaging, labs, specialty_context)
        prompt += (
            "\n\nCardiology Focus:\n"
            "- Assess for acute coronary syndrome, arrhythmia, heart failure, myocarditis\n"
            "- Consider troponin, BNP, ECG findings, echocardiography\n"
            "- Evaluate urgency (STEMI = emergent, unstable angina = urgent, stable CAD = routine)\n"
        )
        return prompt


class RheumatologyCouncil(SpecialistCouncilBase):
    """Rheumatology specialist council."""

    def __init__(self, agent=None):
        super().__init__(agent, num_rollouts=3)
        self.specialty = "rheumatology"

    def _build_specialist_prompt(self, symptoms, history, imaging, labs, specialty_context):
        prompt = super()._build_specialist_prompt(symptoms, history, imaging, labs, specialty_context)
        prompt += (
            "\n\nRheumatology Focus:\n"
            "- Assess for autoimmune diseases (SLE, RA, SSc, vasculitis)\n"
            "- Consider ANA, RF, anti-CCP, complement levels, ESR/CRP\n"
            "- Evaluate polyarticular vs monoarticular, systemic vs local\n"
        )
        return prompt


class NeurologyCouncil(SpecialistCouncilBase):
    """Neurology specialist council."""

    def __init__(self, agent=None):
        super().__init__(agent, num_rollouts=3)
        self.specialty = "neurology"

    def _build_specialist_prompt(self, symptoms, history, imaging, labs, specialty_context):
        prompt = super()._build_specialist_prompt(symptoms, history, imaging, labs, specialty_context)
        prompt += (
            "\n\nNeurology Focus:\n"
            "- Assess for CNS localization, seizures, stroke, encephalitis, migration disorder\n"
            "- Consider EEG patterns, lumbar puncture findings, MR diffusion\n"
            "- Evaluate focal vs generalized, progressive vs acute\n"
        )
        return prompt


class InfectiousDiseaseCouncil(SpecialistCouncilBase):
    """Infectious disease specialist council."""

    def __init__(self, agent=None):
        super().__init__(agent, num_rollouts=3)
        self.specialty = "infectious_disease"

    def _build_specialist_prompt(self, symptoms, history, imaging, labs, specialty_context):
        prompt = super()._build_specialist_prompt(symptoms, history, imaging, labs, specialty_context)
        prompt += (
            "\n\nInfectious Disease Focus:\n"
            "- Assess for bacterial, viral, fungal, parasitic etiologies\n"
            "- Consider culture results, PCR, serology, risk factors (travel, immunity)\n"
            "- Evaluate empiric therapy appropriateness and de-escalation\n"
        )
        return prompt


class InternalMedicineCouncil(SpecialistCouncilBase):
    """General internal medicine council (fallback)."""

    def __init__(self, agent=None):
        super().__init__(agent, num_rollouts=3)
        self.specialty = "internal_medicine"

    def _build_specialist_prompt(self, symptoms, history, imaging, labs, specialty_context):
        prompt = super()._build_specialist_prompt(symptoms, history, imaging, labs, specialty_context)
        prompt += (
            "\n\nGeneral Internal Medicine Focus:\n"
            "- Assess from first-principles clinical reasoning\n"
            "- Consider prevalence, risk factors, test accuracies\n"
            "- Evaluate workup efficiency and cost-effectiveness\n"
        )
        return prompt


def get_specialist_council(specialty: str, agent=None) -> SpecialistCouncilBase:
    """
    Factory function to get a specialist council by name.

    Args:
        specialty: One of "cardiology", "rheumatology", "neurology", "infectious_disease", "internal_medicine"
        agent: MedGemma agent

    Returns:
        Specialized SpecialistCouncilBase instance
    """
    specialist_map = {
        "cardiology": CardiologyCouncil,
        "rheumatology": RheumatologyCouncil,
        "neurology": NeurologyCouncil,
        "infectious_disease": InfectiousDiseaseCouncil,
        "internal_medicine": InternalMedicineCouncil,
    }

    council_class = specialist_map.get(specialty.lower(), InternalMedicineCouncil)
    return council_class(agent=agent)
