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
    pubmed_insights: dict = field(default_factory=dict)   # PubMed case_matcher results

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
            "dissenting_opinions": self.dissenting_opinions,
            "pubmed_insights": self.pubmed_insights,
        }


@dataclass
class IterativeDeliberation:
    """Result of a 2-round iterative deliberation with PubMed evidence feedback."""
    case_id: str
    created_at: datetime
    initial_consensus: str
    final_consensus: str
    consensus_shifted: bool
    rare_diagnoses_injected: list[str]
    rounds: list[dict]
    final_recommendation: str
    discussion_summary: str

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "created_at": self.created_at.isoformat(),
            "initial_consensus": self.initial_consensus,
            "final_consensus": self.final_consensus,
            "consensus_shifted": self.consensus_shifted,
            "rare_diagnoses_injected": self.rare_diagnoses_injected,
            "rounds": self.rounds,
            "final_recommendation": self.final_recommendation,
            "discussion_summary": self.discussion_summary,
        }


# ── Module-level helpers (importable by graph.py without circular deps) ──────

def _calc_consensus(
    opinions: list["DiagnosticOpinion"],
) -> tuple[str | None, "ConsensusStrength", float]:
    """Calculate consensus from multiple opinions."""
    if not opinions:
        return None, ConsensusStrength.SPLIT, 0.0

    diagnosis_counts: dict[str, int] = {}
    diagnosis_confidences: dict[str, list[float]] = {}

    for opinion in opinions:
        diag = opinion.diagnosis
        diagnosis_counts[diag] = diagnosis_counts.get(diag, 0) + 1
        if diag not in diagnosis_confidences:
            diagnosis_confidences[diag] = []
        diagnosis_confidences[diag].append(opinion.confidence)

    max_count = max(diagnosis_counts.values())
    agreement_rate = max_count / len(opinions)
    top_diagnosis = max(diagnosis_counts.keys(), key=lambda d: diagnosis_counts[d])
    avg_confidence = sum(diagnosis_confidences[top_diagnosis]) / len(
        diagnosis_confidences[top_diagnosis]
    )

    if agreement_rate > 0.8:
        strength = ConsensusStrength.STRONG
    elif agreement_rate >= 0.6:
        strength = ConsensusStrength.MODERATE
    elif agreement_rate >= 0.4:
        strength = ConsensusStrength.WEAK
    else:
        strength = ConsensusStrength.SPLIT

    return top_diagnosis, strength, avg_confidence


def _synth_discussion(
    opinions: list["DiagnosticOpinion"],
    consensus: str,
) -> str:
    """Synthesize a discussion summary from opinions."""
    agreeing = [o for o in opinions if o.diagnosis == consensus]
    dissenting = [o for o in opinions if o.diagnosis != consensus]

    parts = [f"The council reviewed the case and generated {len(opinions)} independent analyses."]

    if agreeing:
        parts.append(
            f"\n\n**Majority Opinion ({len(agreeing)}/{len(opinions)}):** "
            f"The primary diagnosis of '{consensus}' was supported by {len(agreeing)} council members. "
            f"Key reasoning: {agreeing[0].reasoning}"
        )

    if dissenting:
        parts.append(
            f"\n\n**Alternative Considerations:** "
            f"{len(dissenting)} member(s) suggested alternative diagnoses including: "
            f"{', '.join(set(o.diagnosis for o in dissenting))}. "
            f"These should be considered in the differential."
        )

    all_tests: set[str] = set()
    for o in opinions:
        all_tests.update(o.recommended_tests)

    parts.append(
        f"\n\n**Recommended Workup:** Based on the collective analysis, "
        f"the following tests are recommended: {', '.join(sorted(all_tests))}."
    )

    return "".join(parts)


def _get_diagnoses(symptoms: list[str]) -> list[dict]:
    """Get possible diagnoses based on symptoms (mock data)."""
    symptom_str = " ".join(symptoms).lower()
    diagnoses: list[dict] = []

    if "chest pain" in symptom_str or "shortness of breath" in symptom_str:
        diagnoses.extend([
            {
                "name": "Acute Coronary Syndrome",
                "reasoning": "Chest pain with cardiac risk factors warrants immediate cardiac workup",
                "tests": ["Troponin", "ECG", "Chest X-ray"],
                "urgency": "emergent",
                "confidence_boost": 0.1,
            },
            {
                "name": "Pulmonary Embolism",
                "reasoning": "Sudden onset dyspnea with chest pain suggests PE until proven otherwise",
                "tests": ["D-dimer", "CT-PA", "Lower extremity doppler"],
                "urgency": "emergent",
                "confidence_boost": 0.05,
            },
            {
                "name": "Pneumonia",
                "reasoning": "Respiratory symptoms may indicate infectious etiology",
                "tests": ["Chest X-ray", "CBC", "Procalcitonin"],
                "urgency": "urgent",
                "confidence_boost": 0,
            },
        ])

    if "cough" in symptom_str or "fever" in symptom_str:
        diagnoses.extend([
            {
                "name": "Community-Acquired Pneumonia",
                "reasoning": "Cough with fever classic presentation for pneumonia",
                "tests": ["Chest X-ray", "CBC", "Sputum culture"],
                "urgency": "urgent",
                "confidence_boost": 0.08,
            },
            {
                "name": "Acute Bronchitis",
                "reasoning": "Cough without significant fever may be viral bronchitis",
                "tests": ["Clinical diagnosis", "Chest X-ray if needed"],
                "urgency": "routine",
                "confidence_boost": 0,
            },
        ])

    if "headache" in symptom_str:
        diagnoses.extend([
            {
                "name": "Tension Headache",
                "reasoning": "Most common cause of headache, bilateral and mild-moderate",
                "tests": ["Clinical diagnosis"],
                "urgency": "routine",
                "confidence_boost": 0,
            },
            {
                "name": "Migraine",
                "reasoning": "Recurrent headache with associated symptoms suggests migraine",
                "tests": ["Clinical diagnosis", "Consider MRI if atypical"],
                "urgency": "routine",
                "confidence_boost": 0.05,
            },
        ])

    if not diagnoses:
        diagnoses = [
            {
                "name": "Further Evaluation Needed",
                "reasoning": "Insufficient information for definitive diagnosis",
                "tests": ["Comprehensive metabolic panel", "CBC"],
                "urgency": "routine",
                "confidence_boost": -0.2,
            }
        ]

    return diagnoses


class DiagnosticCouncil:
    """
    Multi-rollout diagnostic council that generates multiple AI opinions
    and synthesizes them into a consensus recommendation.
    """

    def __init__(self, agent=None, num_rollouts: int = 5, pubmed_agent=None):
        """
        Initialize the diagnostic council.

        Args:
            agent: MedGemma agent for generating opinions
            num_rollouts: Number of parallel opinions to generate
            pubmed_agent: PubMedSynthesisAgent for literature backing
        """
        self.agent = agent
        self.num_rollouts = num_rollouts
        self.pubmed_agent = pubmed_agent
        self.deliberation_history: list[CouncilDeliberation] = []
        self._graph = None  # lazy-built LangGraph workflow

    def _get_graph(self):
        """Lazily build and cache the LangGraph workflow."""
        if self._graph is None:
            from .graph import build_council_graph
            self._graph = build_council_graph(self.agent, self.pubmed_agent)
        return self._graph

    def _build_deliberation(
        self,
        case_id: str,
        case_summary: str,
        result: dict,
        op_key: str = "opinions",
        consensus_key: str = "consensus_diagnosis",
        strength_key: str = "consensus_strength",
        confidence_key: str = "consensus_confidence",
        discussion_key: str = "discussion_summary",
        pubmed_insights: dict | None = None,
    ) -> CouncilDeliberation:
        """Build a CouncilDeliberation from LangGraph invoke() result."""
        op_dicts = result.get(op_key, [])
        opinions = [
            DiagnosticOpinion(
                opinion_id=o["opinion_id"],
                diagnosis=o["diagnosis"],
                confidence=o["confidence"],
                reasoning=o["reasoning"],
                differential_diagnoses=o.get("differential_diagnoses", []),
                recommended_tests=o.get("recommended_tests", []),
                urgency=o["urgency"],
            )
            for o in op_dicts
        ]
        consensus_diagnosis = result.get(consensus_key)
        consensus_strength = ConsensusStrength(result.get(strength_key, "weak"))
        consensus_confidence = float(result.get(confidence_key, 0.0))
        discussion = result.get(discussion_key, "")

        urgency_levels = [o.urgency for o in opinions]
        most_urgent = (
            "emergent" if "emergent" in urgency_levels
            else "urgent" if "urgent" in urgency_levels
            else "routine"
        )
        final_recommendation = (
            f"Based on the diagnostic council's deliberation, the most likely diagnosis is "
            f"**{consensus_diagnosis}** with {int(consensus_confidence * 100)}% confidence "
            f"({consensus_strength.value} consensus). "
            f"Recommended urgency: {most_urgent}."
        )
        dissenting = list({o.diagnosis for o in opinions if o.diagnosis != consensus_diagnosis})

        return CouncilDeliberation(
            case_id=case_id,
            created_at=datetime.now(),
            case_summary=case_summary,
            opinions=opinions,
            consensus_diagnosis=consensus_diagnosis,
            consensus_strength=consensus_strength,
            consensus_confidence=consensus_confidence,
            discussion_summary=discussion,
            final_recommendation=final_recommendation,
            dissenting_opinions=dissenting,
            pubmed_insights=pubmed_insights if pubmed_insights is not None
                            else result.get("pubmed_insights", {}),
        )
    
    def _generate_single_opinion(
        self,
        case_info: dict,
        opinion_id: str,
        temperature: float = 0.7,
        evidence_context: list[str] | None = None,
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
            idx = int(opinion_id.rsplit("-", 1)[-1]) % len(possible_diagnoses)
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

        # Inject PubMed rare diagnoses context if available
        if evidence_context:
            rare_list = "\n".join(f"• {d}" for d in evidence_context)
            prompt += (
                f"\n\nPublished case report literature has identified these rare diagnoses "
                f"for similar presentations:\n{rare_list}\n"
                f"Consider whether any of these rare diagnoses fit this case better than "
                f"the most common alternative."
            )

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
            idx = int(opinion_id.rsplit("-", 1)[-1]) % len(possible_diagnoses)
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
        return _get_diagnoses(symptoms)

    def _calculate_consensus(self, opinions: list[DiagnosticOpinion]) -> tuple[str | None, ConsensusStrength, float]:
        """Calculate consensus from multiple opinions."""
        return _calc_consensus(opinions)

    def _synthesize_discussion(self, opinions: list[DiagnosticOpinion], consensus: str) -> str:
        """Synthesize a discussion summary from the opinions."""
        return _synth_discussion(opinions, consensus)

    def deliberate(
        self,
        symptoms: list[str],
        patient_history: str = "",
        imaging_findings: str = "",
        vitals: dict | None = None,
        raw_note: str = "",
    ) -> CouncilDeliberation:
        """
        Conduct a full diagnostic council deliberation.

        Args:
            symptoms: List of presenting symptoms
            patient_history: Relevant patient history
            imaging_findings: Imaging results if available
            vitals: Current vital signs
            raw_note: Full unstructured clinical note (H&P, progress note, etc.).
                      When provided, the most symptom-relevant excerpts are retrieved
                      via RAG and injected into each opinion prompt.

        Returns:
            CouncilDeliberation with consensus and all opinions
        """
        from .graph import CouncilState

        case_id = f"CASE-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        case_info = {
            "symptoms": symptoms,
            "patient_history": patient_history,
            "imaging_findings": imaging_findings,
            "vitals": vitals or {},
        }
        case_summary = (
            f"Patient presenting with: {', '.join(symptoms)}. "
            f"History: {patient_history or 'Not provided'}. "
            f"Imaging: {imaging_findings or 'None available'}."
        )

        init_state: CouncilState = {
            "case_info": case_info,
            "num_rollouts": self.num_rollouts,
            "mode": "standard",
            "raw_note": raw_note,
            "retrieved_context": "",
            "opinions": [],
            "consensus_diagnosis": None,
            "consensus_strength": "weak",
            "consensus_confidence": 0.0,
            "discussion_summary": "",
            "pubmed_insights": {},
            "rare_diagnoses": [],
            "r2_opinions": [],
            "r2_consensus_diagnosis": None,
            "r2_consensus_strength": "weak",
            "r2_consensus_confidence": 0.0,
            "r2_discussion_summary": "",
        }

        result = self._get_graph().invoke(init_state)
        deliberation = self._build_deliberation(case_id, case_summary, result)
        self.deliberation_history.append(deliberation)
        return deliberation

    def iterative_deliberate(
        self,
        symptoms: list[str],
        patient_history: str = "",
        imaging_findings: str = "",
        vitals: dict | None = None,
        raw_note: str = "",
    ) -> "IterativeDeliberation":
        """
        2-round iterative deliberation with PubMed evidence feedback.

        Round 1: Standard deliberation — generates consensus + PubMed rare diagnoses.
        Round 2: Re-deliberates with rare diagnoses injected into opinion prompts.
        Returns an IterativeDeliberation showing whether consensus shifted.
        """
        from .graph import CouncilState

        case_id = f"ITER-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        case_info = {
            "symptoms": symptoms,
            "patient_history": patient_history,
            "imaging_findings": imaging_findings,
            "vitals": vitals or {},
        }
        case_summary = (
            f"Patient presenting with: {', '.join(symptoms)}. "
            f"History: {patient_history or 'Not provided'}. "
            f"Imaging: {imaging_findings or 'None available'}."
        )

        init_state: CouncilState = {
            "case_info": case_info,
            "num_rollouts": self.num_rollouts,
            "mode": "iterative",
            "raw_note": raw_note,
            "retrieved_context": "",
            "opinions": [],
            "consensus_diagnosis": None,
            "consensus_strength": "weak",
            "consensus_confidence": 0.0,
            "discussion_summary": "",
            "pubmed_insights": {},
            "rare_diagnoses": [],
            "r2_opinions": [],
            "r2_consensus_diagnosis": None,
            "r2_consensus_strength": "weak",
            "r2_consensus_confidence": 0.0,
            "r2_discussion_summary": "",
        }

        result = self._get_graph().invoke(init_state)

        # ── Round 1 deliberation ─────────────────────────────────────────────
        round1 = self._build_deliberation(case_id + "-R1", case_summary, result)

        rare_diagnoses: list[str] = result.get("rare_diagnoses", [])
        r2_opinion_dicts: list[dict] = result.get("r2_opinions", [])

        # ── No Round 2 (PubMed returned no rare diagnoses) ──────────────────
        if not r2_opinion_dicts:
            return IterativeDeliberation(
                case_id=case_id,
                created_at=datetime.now(),
                initial_consensus=round1.consensus_diagnosis or "Undetermined",
                final_consensus=round1.consensus_diagnosis or "Undetermined",
                consensus_shifted=False,
                rare_diagnoses_injected=[],
                rounds=[round1.to_dict()],
                final_recommendation=round1.final_recommendation,
                discussion_summary=(
                    "Round 2 skipped: PubMed returned no rare diagnosis candidates "
                    "for this symptom cluster."
                ),
            )

        # ── Round 2 deliberation ─────────────────────────────────────────────
        r2_opinions = [
            DiagnosticOpinion(
                opinion_id=o["opinion_id"],
                diagnosis=o["diagnosis"],
                confidence=o["confidence"],
                reasoning=o["reasoning"],
                differential_diagnoses=o.get("differential_diagnoses", []),
                recommended_tests=o.get("recommended_tests", []),
                urgency=o["urgency"],
            )
            for o in r2_opinion_dicts
        ]
        r2_consensus = result.get("r2_consensus_diagnosis")
        r2_strength = ConsensusStrength(result.get("r2_consensus_strength", "weak"))
        r2_confidence = float(result.get("r2_consensus_confidence", 0.0))
        r2_discussion = result.get("r2_discussion_summary", "")

        urgency_levels = [o.urgency for o in r2_opinions]
        most_urgent = (
            "emergent" if "emergent" in urgency_levels
            else "urgent" if "urgent" in urgency_levels
            else "routine"
        )
        round2_recommendation = (
            f"Based on evidence-informed deliberation, the most likely diagnosis is "
            f"**{r2_consensus}** with {int(r2_confidence * 100)}% confidence "
            f"({r2_strength.value} consensus). "
            f"Recommended urgency: {most_urgent}. "
            f"PubMed literature considered {len(rare_diagnoses)} rare diagnosis candidate(s)."
        )

        round2 = CouncilDeliberation(
            case_id=case_id + "-R2",
            created_at=datetime.now(),
            case_summary=case_summary,
            opinions=r2_opinions,
            consensus_diagnosis=r2_consensus,
            consensus_strength=r2_strength,
            consensus_confidence=r2_confidence,
            discussion_summary=r2_discussion,
            final_recommendation=round2_recommendation,
            dissenting_opinions=list(
                {o.diagnosis for o in r2_opinions if o.diagnosis != r2_consensus}
            ),
            pubmed_insights=round1.pubmed_insights,
        )

        # ── Summarise evolution ──────────────────────────────────────────────
        consensus_shifted = (
            r2_consensus is not None
            and round1.consensus_diagnosis is not None
            and r2_consensus.lower() != round1.consensus_diagnosis.lower()
        )

        summary = (
            f"Round 1 consensus: {round1.consensus_diagnosis} "
            f"({round1.consensus_strength.value}).\n"
            f"PubMed surfaced {len(rare_diagnoses)} rare diagnosis candidate(s).\n"
            f"Round 2 consensus after evidence injection: {r2_consensus} "
            f"({r2_strength.value}).\n"
            + (
                "Consensus SHIFTED — rare diagnosis promoted to leading hypothesis."
                if consensus_shifted else
                "Consensus held — original diagnosis reinforced by literature review."
            )
        )

        return IterativeDeliberation(
            case_id=case_id,
            created_at=datetime.now(),
            initial_consensus=round1.consensus_diagnosis or "Undetermined",
            final_consensus=r2_consensus or "Undetermined",
            consensus_shifted=consensus_shifted,
            rare_diagnoses_injected=rare_diagnoses,
            rounds=[round1.to_dict(), round2.to_dict()],
            final_recommendation=round2_recommendation,
            discussion_summary=summary,
        )

    def initiate_long_horizon_workflow(
        self,
        symptoms: list[str],
        patient_id: str,
        created_by: str,
        patient_history: str = "",
        imaging_findings: str = "",
        vitals: dict | None = None,
        raw_note: str = "",
    ) -> str:
        """
        Initiate a long-horizon workflow for continuous monitoring and re-deliberation.

        Args:
            symptoms: List of presenting symptoms
            patient_id: Patient identifier
            created_by: User/physician initiating the workflow
            patient_history: Relevant patient history
            imaging_findings: Imaging results if available
            vitals: Current vital signs
            raw_note: Full unstructured clinical note (optional)

        Returns:
            Workflow ID for future reference and re-deliberations
        """
        from .workflow_engine import get_workflow_engine
        from .long_horizon_state import extend_council_state_to_long_horizon

        engine = get_workflow_engine()

        # Create initial council state
        council_state = {
            "case_info": {
                "symptoms": symptoms,
                "patient_history": patient_history,
                "imaging_findings": imaging_findings,
                "vitals": vitals or {},
            },
            "num_rollouts": self.num_rollouts,
            "mode": "iterative",
            "raw_note": raw_note,
            "retrieved_context": "",
            "opinions": [],
            "consensus_diagnosis": None,
            "consensus_strength": "weak",
            "consensus_confidence": 0.0,
            "discussion_summary": "",
            "minority_challenge": "",
            "pubmed_insights": {},
            "rare_diagnoses": [],
            "r2_opinions": [],
            "r2_consensus_diagnosis": None,
            "r2_consensus_strength": "weak",
            "r2_consensus_confidence": 0.0,
            "r2_discussion_summary": "",
        }

        # Initiate workflow
        workflow_id = engine.initiate_workflow(
            council_state=council_state,
            patient_id=patient_id,
            created_by=created_by,
        )

        return workflow_id

    def get_workflow_status(self, workflow_id: str) -> dict:
        """Get status and summary of a long-horizon workflow."""
        from .workflow_engine import get_workflow_engine

        engine = get_workflow_engine()
        return engine.summarize_workflow(workflow_id)

    def get_deliberation_history(self) -> list[dict]:
        """Get all past deliberations."""
        return [d.to_dict() for d in self.deliberation_history]


# Singleton instance
_council = None

def get_diagnostic_council(agent=None, num_rollouts: int = 5, pubmed_agent=None) -> DiagnosticCouncil:
    """Get or create the diagnostic council singleton."""
    global _council
    if _council is None:
        _council = DiagnosticCouncil(agent=agent, num_rollouts=num_rollouts, pubmed_agent=pubmed_agent)
    else:
        if agent is not None and _council.agent is None:
            _council.agent = agent
            _council._graph = None  # reset graph so it picks up the new agent
        if pubmed_agent is not None and _council.pubmed_agent is None:
            _council.pubmed_agent = pubmed_agent
            _council._graph = None  # reset graph so it picks up the new pubmed_agent
    return _council
