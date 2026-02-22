"""
Diagnostic Council - Multi-Rollout Deliberation System
Generates multiple MedGemma opinions to reach consensus on diagnoses.
"""

from datetime import datetime
from dataclasses import dataclass, field
from typing import Any
from enum import Enum
import random


class ConsensusStrength(str, Enum):
    """Strength of diagnostic consensus."""
    STRONG = "strong"      # >80% agreement
    MODERATE = "moderate"  # 60-80% agreement
    WEAK = "weak"          # <60% agreement
    SPLIT = "split"        # No clear majority


@dataclass
class DiagnosticOpinion:
    """A single AI-generated diagnostic opinion."""
    opinion_id: str
    diagnosis: str
    confidence: float  # 0.0 to 1.0
    reasoning: str
    differential_diagnoses: list[str]
    recommended_tests: list[str]
    urgency: str  # routine, urgent, emergent
    
    def to_dict(self) -> dict:
        return {
            "opinion_id": self.opinion_id,
            "diagnosis": self.diagnosis,
            "confidence": self.confidence,
            "confidence_percent": f"{int(self.confidence * 100)}%",
            "reasoning": self.reasoning,
            "differential_diagnoses": self.differential_diagnoses,
            "recommended_tests": self.recommended_tests,
            "urgency": self.urgency
        }


@dataclass
class CouncilDeliberation:
    """Result of a diagnostic council deliberation."""
    case_id: str
    created_at: datetime
    case_summary: str
    opinions: list[DiagnosticOpinion]
    consensus_diagnosis: str | None
    consensus_strength: ConsensusStrength
    consensus_confidence: float
    discussion_summary: str
    final_recommendation: str
    dissenting_opinions: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "created_at": self.created_at.isoformat(),
            "created_at_display": self.created_at.strftime("%b %d, %Y %H:%M"),
            "case_summary": self.case_summary,
            "opinions": [o.to_dict() for o in self.opinions],
            "consensus_diagnosis": self.consensus_diagnosis,
            "consensus_strength": self.consensus_strength.value,
            "consensus_confidence": self.consensus_confidence,
            "consensus_confidence_percent": f"{int(self.consensus_confidence * 100)}%",
            "discussion_summary": self.discussion_summary,
            "final_recommendation": self.final_recommendation,
            "dissenting_opinions": self.dissenting_opinions
        }


class DiagnosticCouncil:
    """
    Multi-rollout diagnostic council that generates multiple AI opinions
    and synthesizes them into a consensus recommendation.
    """
    
    def __init__(self, agent=None, num_rollouts: int = 5):
        """
        Initialize the diagnostic council.
        
        Args:
            agent: MedGemma agent for generating opinions
            num_rollouts: Number of parallel opinions to generate
        """
        self.agent = agent
        self.num_rollouts = num_rollouts
        self.deliberation_history: list[CouncilDeliberation] = []
    
    def _generate_single_opinion(
        self,
        case_info: dict,
        opinion_id: str,
        temperature: float = 0.7
    ) -> DiagnosticOpinion:
        """
        Generate a single diagnostic opinion using the AI agent.
        """
        symptoms = case_info.get("symptoms", [])
        history = case_info.get("patient_history", "")
        imaging = case_info.get("imaging_findings", "")
        vitals = case_info.get("vitals", {})
        
        if self.agent is None:
            # Fallback to mock logic
            possible_diagnoses = self._get_possible_diagnoses(symptoms)
            idx = int(opinion_id.split("-")[1]) % len(possible_diagnoses)
            primary_diagnosis = possible_diagnoses[idx % len(possible_diagnoses)]
            confidence_base = 0.75 + (random.random() * 0.2)
            
            return DiagnosticOpinion(
                opinion_id=opinion_id,
                diagnosis=primary_diagnosis["name"],
                confidence=round(confidence_base + primary_diagnosis.get("confidence_boost", 0), 2),
                reasoning=primary_diagnosis["reasoning"],
                differential_diagnoses=[d["name"] for d in possible_diagnoses if d["name"] != primary_diagnosis["name"]][:3],
                recommended_tests=primary_diagnosis.get("tests", ["CBC", "BMP"]),
                urgency=primary_diagnosis.get("urgency", "routine")
            )
            
        # Call the AI model and ask for JSON
        import json
        import re
        
        prompt = f"""You are a medical diagnostic AI participating in a diagnostic council.
Analyze the following patient case and provide your assessment:
Symptoms: {', '.join(symptoms)}
History: {history}
Imaging: {imaging}
Vitals: {vitals}

Provide exactly 1 primary diagnosis and up to 3 differential diagnoses.
Return EXACTLY ONE valid JSON object matching this exact schema and NOTHING ELSE:
{{
  "name": "Diagnosis Name",
  "reasoning": "Brief clinical reasoning (1-2 sentences)",
  "confidence": 0.85,
  "differential_diagnoses": ["Alt1", "Alt2", "Alt3"],
  "recommended_tests": ["Test1", "Test2"],
  "urgency": "routine"
}}

Note: "urgency" MUST be one of: "routine", "urgent", "emergent"."""

        try:
            response_text = ""
            if hasattr(self.agent, 'process_query'):
                # Send context inside prompt, bypass patient_context
                result = self.agent.process_query(query=prompt, patient_context=None)
                response_text = result.get("response", "")
            elif hasattr(self.agent, 'chat'):
                response_text = self.agent.chat(prompt)
                
            # Parse JSON - try to extract JSON block if wrapped in markdown
            json_match = re.search(r'```(?:json)?(.*?)```', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(1)
                
            # Also clean up simulated prefix
            response_text = response_text.replace("[Simulated] Processed query: ", "").strip()
            if response_text.endswith("."):
                response_text = response_text[:-1] # Remove trailing period from simulated response
                
            result = json.loads(response_text)
            
            return DiagnosticOpinion(
                opinion_id=opinion_id,
                diagnosis=result.get("name", "Unknown Diagnosis"),
                confidence=float(result.get("confidence", 0.5)),
                reasoning=result.get("reasoning", "No reasoning provided."),
                differential_diagnoses=result.get("differential_diagnoses", []),
                recommended_tests=result.get("recommended_tests", []),
                urgency=result.get("urgency", "routine")
            )
            
        except Exception as e:
            # Fallback to mock data on JSON parse failure or agent error
            print(f"Error calling agent: {e}. Falling back to mock data.")
            possible_diagnoses = self._get_possible_diagnoses(symptoms)
            idx = int(opinion_id.split("-")[1]) % len(possible_diagnoses)
            primary_diagnosis = possible_diagnoses[idx % len(possible_diagnoses)]
            confidence_base = 0.75 + (random.random() * 0.2)
            
            return DiagnosticOpinion(
                opinion_id=opinion_id,
                diagnosis=primary_diagnosis["name"],
                confidence=round(confidence_base + primary_diagnosis.get("confidence_boost", 0), 2),
                reasoning=primary_diagnosis["reasoning"] + f" (Generated via mock fallback)",
                differential_diagnoses=[d["name"] for d in possible_diagnoses if d["name"] != primary_diagnosis["name"]][:3],
                recommended_tests=primary_diagnosis.get("tests", ["CBC", "BMP"]),
                urgency=primary_diagnosis.get("urgency", "routine")
            )
    
    def _get_possible_diagnoses(self, symptoms: list[str]) -> list[dict]:
        """Get possible diagnoses based on symptoms."""
        symptom_str = " ".join(symptoms).lower()
        
        diagnoses = []
        
        if "chest pain" in symptom_str or "shortness of breath" in symptom_str:
            diagnoses.extend([
                {
                    "name": "Acute Coronary Syndrome",
                    "reasoning": "Chest pain with cardiac risk factors warrants immediate cardiac workup",
                    "tests": ["Troponin", "ECG", "Chest X-ray"],
                    "urgency": "emergent",
                    "confidence_boost": 0.1
                },
                {
                    "name": "Pulmonary Embolism",
                    "reasoning": "Sudden onset dyspnea with chest pain suggests PE until proven otherwise",
                    "tests": ["D-dimer", "CT-PA", "Lower extremity doppler"],
                    "urgency": "emergent",
                    "confidence_boost": 0.05
                },
                {
                    "name": "Pneumonia",
                    "reasoning": "Respiratory symptoms may indicate infectious etiology",
                    "tests": ["Chest X-ray", "CBC", "Procalcitonin"],
                    "urgency": "urgent",
                    "confidence_boost": 0
                }
            ])
        
        if "cough" in symptom_str or "fever" in symptom_str:
            diagnoses.extend([
                {
                    "name": "Community-Acquired Pneumonia",
                    "reasoning": "Cough with fever classic presentation for pneumonia",
                    "tests": ["Chest X-ray", "CBC", "Sputum culture"],
                    "urgency": "urgent",
                    "confidence_boost": 0.08
                },
                {
                    "name": "Acute Bronchitis",
                    "reasoning": "Cough without significant fever may be viral bronchitis",
                    "tests": ["Clinical diagnosis", "Chest X-ray if needed"],
                    "urgency": "routine",
                    "confidence_boost": 0
                }
            ])
        
        if "headache" in symptom_str:
            diagnoses.extend([
                {
                    "name": "Tension Headache",
                    "reasoning": "Most common cause of headache, bilateral and mild-moderate",
                    "tests": ["Clinical diagnosis"],
                    "urgency": "routine",
                    "confidence_boost": 0
                },
                {
                    "name": "Migraine",
                    "reasoning": "Recurrent headache with associated symptoms suggests migraine",
                    "tests": ["Clinical diagnosis", "Consider MRI if atypical"],
                    "urgency": "routine",
                    "confidence_boost": 0.05
                }
            ])
        
        # Default if no specific symptoms matched
        if not diagnoses:
            diagnoses = [
                {
                    "name": "Further Evaluation Needed",
                    "reasoning": "Insufficient information for definitive diagnosis",
                    "tests": ["Comprehensive metabolic panel", "CBC"],
                    "urgency": "routine",
                    "confidence_boost": -0.2
                }
            ]
        
        return diagnoses
    
    def _calculate_consensus(self, opinions: list[DiagnosticOpinion]) -> tuple[str | None, ConsensusStrength, float]:
        """Calculate consensus from multiple opinions."""
        if not opinions:
            return None, ConsensusStrength.SPLIT, 0.0
        
        # Count diagnosis frequencies
        diagnosis_counts = {}
        diagnosis_confidences = {}
        
        for opinion in opinions:
            diag = opinion.diagnosis
            diagnosis_counts[diag] = diagnosis_counts.get(diag, 0) + 1
            if diag not in diagnosis_confidences:
                diagnosis_confidences[diag] = []
            diagnosis_confidences[diag].append(opinion.confidence)
        
        # Find most common diagnosis
        max_count = max(diagnosis_counts.values())
        agreement_rate = max_count / len(opinions)
        
        top_diagnosis = max(diagnosis_counts.keys(), key=lambda d: diagnosis_counts[d])
        avg_confidence = sum(diagnosis_confidences[top_diagnosis]) / len(diagnosis_confidences[top_diagnosis])
        
        # Determine consensus strength
        if agreement_rate > 0.8:
            strength = ConsensusStrength.STRONG
        elif agreement_rate >= 0.6:
            strength = ConsensusStrength.MODERATE
        elif agreement_rate >= 0.4:
            strength = ConsensusStrength.WEAK
        else:
            strength = ConsensusStrength.SPLIT
        
        return top_diagnosis, strength, avg_confidence
    
    def _synthesize_discussion(self, opinions: list[DiagnosticOpinion], consensus: str) -> str:
        """Synthesize a discussion summary from the opinions."""
        agreeing = [o for o in opinions if o.diagnosis == consensus]
        dissenting = [o for o in opinions if o.diagnosis != consensus]
        
        summary_parts = []
        summary_parts.append(f"The council reviewed the case and generated {len(opinions)} independent analyses.")
        
        if agreeing:
            summary_parts.append(
                f"\n\n**Majority Opinion ({len(agreeing)}/{len(opinions)}):** "
                f"The primary diagnosis of '{consensus}' was supported by {len(agreeing)} council members. "
                f"Key reasoning: {agreeing[0].reasoning}"
            )
        
        if dissenting:
            summary_parts.append(
                f"\n\n**Alternative Considerations:** "
                f"{len(dissenting)} member(s) suggested alternative diagnoses including: "
                f"{', '.join(set(o.diagnosis for o in dissenting))}. "
                f"These should be considered in the differential."
            )
        
        # Recommended tests from all opinions
        all_tests = set()
        for o in opinions:
            all_tests.update(o.recommended_tests)
        
        summary_parts.append(
            f"\n\n**Recommended Workup:** Based on the collective analysis, "
            f"the following tests are recommended: {', '.join(sorted(all_tests))}."
        )
        
        return "".join(summary_parts)
    
    def deliberate(
        self,
        symptoms: list[str],
        patient_history: str = "",
        imaging_findings: str = "",
        vitals: dict | None = None
    ) -> CouncilDeliberation:
        """
        Conduct a full diagnostic council deliberation.
        
        Args:
            symptoms: List of presenting symptoms
            patient_history: Relevant patient history
            imaging_findings: Imaging results if available
            vitals: Current vital signs
            
        Returns:
            CouncilDeliberation with consensus and all opinions
        """
        case_id = f"CASE-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        case_info = {
            "symptoms": symptoms,
            "patient_history": patient_history,
            "imaging_findings": imaging_findings,
            "vitals": vitals or {}
        }
        
        case_summary = f"Patient presenting with: {', '.join(symptoms)}. " \
                       f"History: {patient_history or 'Not provided'}. " \
                       f"Imaging: {imaging_findings or 'None available'}."
        
        # Generate multiple opinions
        opinions = []
        for i in range(self.num_rollouts):
            temperature = 0.6 + (i * 0.1)  # Vary temperature for diversity
            opinion = self._generate_single_opinion(
                case_info,
                f"OPINION-{i+1}",
                temperature=min(temperature, 1.0)
            )
            opinions.append(opinion)
        
        # Calculate consensus
        consensus_diagnosis, consensus_strength, consensus_confidence = self._calculate_consensus(opinions)
        
        # Get dissenting opinions
        dissenting = [o.diagnosis for o in opinions if o.diagnosis != consensus_diagnosis]
        
        # Synthesize discussion
        discussion = self._synthesize_discussion(opinions, consensus_diagnosis)
        
        # Generate final recommendation
        urgency_levels = [o.urgency for o in opinions]
        most_urgent = "emergent" if "emergent" in urgency_levels else \
                      "urgent" if "urgent" in urgency_levels else "routine"
        
        final_recommendation = (
            f"Based on the diagnostic council's deliberation, the most likely diagnosis is "
            f"**{consensus_diagnosis}** with {int(consensus_confidence * 100)}% confidence "
            f"({consensus_strength.value} consensus). "
            f"Recommended urgency: {most_urgent}."
        )
        
        deliberation = CouncilDeliberation(
            case_id=case_id,
            created_at=datetime.now(),
            case_summary=case_summary,
            opinions=opinions,
            consensus_diagnosis=consensus_diagnosis,
            consensus_strength=consensus_strength,
            consensus_confidence=consensus_confidence,
            discussion_summary=discussion,
            final_recommendation=final_recommendation,
            dissenting_opinions=list(set(dissenting))
        )
        
        self.deliberation_history.append(deliberation)
        return deliberation
    
    def get_deliberation_history(self) -> list[dict]:
        """Get all past deliberations."""
        return [d.to_dict() for d in self.deliberation_history]


# Singleton instance
_council = None

def get_diagnostic_council(agent=None, num_rollouts: int = 5) -> DiagnosticCouncil:
    """Get or create the diagnostic council singleton."""
    global _council
    if _council is None:
        _council = DiagnosticCouncil(agent=agent, num_rollouts=num_rollouts)
    elif agent is not None and _council.agent is None:
        _council.agent = agent
    return _council
