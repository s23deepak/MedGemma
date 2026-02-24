"""
Clinical Simulation Engine

Manages resident simulation sessions end-to-end:
  1. Case presentation
  2. Interactive history taking (MedGemma plays the patient)
  3. Physical examination reveal
  4. Investigation ordering
  5. Diagnosis and management submission
  6. AI-powered scoring and feedback (MedGemma as tutor)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .cases import ClinicalCase, get_case, list_cases

logger = logging.getLogger(__name__)


# ── Session model ──────────────────────────────────────────────────────────────

@dataclass
class SimulationSession:
    session_id: str
    resident_name: str
    case_id: str
    case: ClinicalCase

    # Interaction history
    history_questions: list[dict] = field(default_factory=list)   # [{q, a, ts}]
    exam_systems_viewed: list[str] = field(default_factory=list)
    investigations_ordered: list[str] = field(default_factory=list)

    # Submissions
    diagnosis_submitted: str = ""
    management_submitted: list[str] = field(default_factory=list)

    # Scoring
    score: dict | None = None

    # State
    status: str = "active"   # active | submitted | scored
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str = ""

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "resident_name": self.resident_name,
            "case_id": self.case_id,
            "case_title": self.case.title,
            "specialty": self.case.specialty,
            "difficulty": self.case.difficulty,
            "presentation": self.case.presentation,
            "initial_vitals": self.case.initial_vitals,
            "learning_objectives": self.case.learning_objectives,
            "history_questions": self.history_questions,
            "exam_systems_viewed": self.exam_systems_viewed,
            "investigations_ordered": self.investigations_ordered,
            "diagnosis_submitted": self.diagnosis_submitted,
            "management_submitted": self.management_submitted,
            "score": self.score,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


# ── Patient persona prompt template ───────────────────────────────────────────

PATIENT_PERSONA_TEMPLATE = """\
You are roleplaying as a patient in a medical simulation for resident education.

Patient background:
{presentation}

Your known history (answer ONLY from this information, stay in character):
{history_context}

Rules:
- Respond as the patient in first person, naturally and emotionally
- Only reveal information that the resident's question specifically asks about
- If the resident asks about something not in your history, say you don't know or it's not relevant
- Show appropriate distress, fear, or discomfort based on the presentation
- Do NOT volunteer information the resident hasn't asked about
- Do NOT use medical terminology — speak as a layperson
- Keep responses to 2-4 sentences

Resident's question: {question}
"""

TUTOR_SCORING_PROMPT = """\
You are a senior clinician and medical educator assessing a resident's performance in a clinical simulation.

CASE: {case_title}
CORRECT DIAGNOSIS: {correct_diagnosis}
CORRECT MANAGEMENT STEPS: {correct_management}

RESIDENT PERFORMANCE:
History questions asked: {history_questions}
Examination systems reviewed: {exam_systems}
Investigations ordered: {investigations}
Diagnosis submitted: {diagnosis_submitted}
Management plan submitted: {management_submitted}

Score each domain on the given maximum points and provide specific feedback:

1. HISTORY TAKING (max {w_history} pts): Did the resident ask the key discriminating questions?
2. PHYSICAL EXAMINATION (max {w_exam} pts): Did they examine the relevant systems?
3. INVESTIGATIONS (max {w_inv} pts): Were the key investigations ordered? Any unnecessary ones?
4. DIAGNOSIS (max {w_diag} pts): Is the diagnosis correct or partially correct?
5. MANAGEMENT (max {w_mgmt} pts): Are the management steps appropriate and complete?

Also provide:
- OVERALL FEEDBACK: 2-3 sentences of constructive summary
- MISSED DIAGNOSES: Any important differentials they should have considered
- CRITICAL ERRORS: Any dangerous or harmful decisions made
- KEY LEARNING POINTS: 2-3 most important teaching points for this case

Format your response as structured text with clear section headers.
"""


# ── Simulator ─────────────────────────────────────────────────────────────────

class SimulationEngine:
    """Manages all active simulation sessions."""

    def __init__(self, agent=None):
        self.agent = agent
        self._sessions: dict[str, SimulationSession] = {}

    def set_agent(self, agent) -> None:
        self.agent = agent

    # ── Session lifecycle ──────────────────────────────────────────────────────

    def start_session(self, resident_name: str, case_id: str) -> SimulationSession:
        case = get_case(case_id)
        if case is None:
            raise ValueError(f"Case {case_id} not found")
        session = SimulationSession(
            session_id=f"SIM-{uuid.uuid4().hex[:8].upper()}",
            resident_name=resident_name,
            case_id=case_id,
            case=case,
        )
        self._sessions[session.session_id] = session
        logger.info(f"Simulation session {session.session_id} started for {resident_name} — case {case_id}")
        return session

    def get_session(self, session_id: str) -> SimulationSession | None:
        return self._sessions.get(session_id)

    # ── Interactions ───────────────────────────────────────────────────────────

    def ask_history(self, session_id: str, question: str) -> dict:
        """
        Resident asks the patient a history question.
        MedGemma responds in character as the patient.
        Returns {"question": ..., "response": ..., "ai": bool}
        """
        session = self._get_active_session(session_id)
        case = session.case

        # Build history context string from case data
        history_ctx = "\n".join(f"- {k}: {v}" for k, v in case.history_data.items())

        if self.agent is not None:
            prompt = PATIENT_PERSONA_TEMPLATE.format(
                presentation=case.presentation,
                history_context=history_ctx,
                question=question,
            )
            try:
                if hasattr(self.agent, "process_query"):
                    result = self.agent.process_query(query=prompt, patient_context={})
                    response = result.get("response", "").strip()
                elif hasattr(self.agent, "chat"):
                    response = self.agent.chat(prompt)
                else:
                    response = self._keyword_patient_response(case, question)
            except Exception as e:
                logger.warning(f"Agent history response failed: {e}")
                response = self._keyword_patient_response(case, question)
            ai = True
        else:
            response = self._keyword_patient_response(case, question)
            ai = False

        entry = {
            "question": question,
            "response": response,
            "ai": ai,
            "ts": datetime.now().isoformat(),
        }
        session.history_questions.append(entry)
        return entry

    def view_exam(self, session_id: str, system: str) -> dict:
        """Resident requests physical examination findings for a body system."""
        session = self._get_active_session(session_id)
        system_key = next(
            (k for k in session.case.physical_exam if system.lower() in k.lower()),
            None,
        )
        if system_key is None:
            findings = "No specific findings documented for this system."
        else:
            findings = session.case.physical_exam[system_key]
            if system_key not in session.exam_systems_viewed:
                session.exam_systems_viewed.append(system_key)

        return {"system": system_key or system, "findings": findings}

    def order_investigation(self, session_id: str, investigation: str) -> dict:
        """Resident orders an investigation. Returns the result."""
        session = self._get_active_session(session_id)
        inv_key = next(
            (k for k in session.case.investigations if investigation.lower() in k.lower()),
            None,
        )
        if inv_key is None:
            result = "Investigation not available in this simulation or result pending."
            key = investigation
        else:
            result = session.case.investigations[inv_key]
            key = inv_key
            if key not in session.investigations_ordered:
                session.investigations_ordered.append(key)

        return {"investigation": key, "result": result}

    def submit_assessment(
        self,
        session_id: str,
        diagnosis: str,
        management: list[str],
    ) -> dict:
        """
        Resident submits their final diagnosis and management plan.
        Triggers AI scoring and returns full feedback.
        """
        session = self._get_active_session(session_id)
        session.diagnosis_submitted = diagnosis
        session.management_submitted = management
        session.status = "submitted"

        score = self._score_session(session)
        session.score = score
        session.status = "scored"
        session.completed_at = datetime.now().isoformat()

        return score

    # ── Scoring ────────────────────────────────────────────────────────────────

    def _score_session(self, session: SimulationSession) -> dict:
        """Generate structured score + feedback using MedGemma or rule-based fallback."""
        if self.agent is not None:
            return self._ai_score(session)
        return self._rule_based_score(session)

    def _ai_score(self, session: SimulationSession) -> dict:
        case = session.case
        w = case.score_weights
        prompt = TUTOR_SCORING_PROMPT.format(
            case_title=case.title,
            correct_diagnosis=case.correct_diagnosis,
            correct_management="\n".join(f"- {m}" for m in case.correct_management),
            history_questions="\n".join(f"- Q: {h['question']} | A: {h['response']}" for h in session.history_questions),
            exam_systems=", ".join(session.exam_systems_viewed) or "None",
            investigations=", ".join(session.investigations_ordered) or "None",
            diagnosis_submitted=session.diagnosis_submitted or "Not submitted",
            management_submitted="\n".join(f"- {m}" for m in session.management_submitted) or "Not submitted",
            w_history=w["history"],
            w_exam=w["exam"],
            w_inv=w["investigations"],
            w_diag=w["diagnosis"],
            w_mgmt=w["management"],
        )
        try:
            if hasattr(self.agent, "process_query"):
                result = self.agent.process_query(query=prompt, patient_context={})
                feedback_text = result.get("response", "")
            elif hasattr(self.agent, "chat"):
                feedback_text = self.agent.chat(prompt)
            else:
                feedback_text = ""

            if feedback_text:
                numeric = self._rule_based_score(session)
                numeric["ai_feedback"] = feedback_text
                numeric["key_learning_points"] = case.key_learning_points
                return numeric
        except Exception as e:
            logger.warning(f"AI scoring failed, falling back to rule-based: {e}")

        return self._rule_based_score(session)

    def _rule_based_score(self, session: SimulationSession) -> dict:
        """Deterministic scoring based on keyword matching."""
        case = session.case
        w = case.score_weights
        scores = {}
        feedback = {}

        # History (did they ask about key topics?)
        key_history_keywords = list(case.history_data.keys())[:8]
        questions_text = " ".join(h["question"].lower() for h in session.history_questions)
        history_hits = sum(1 for kw in key_history_keywords if kw.lower() in questions_text)
        scores["history"] = round(min(w["history"], (history_hits / max(len(key_history_keywords), 1)) * w["history"]))
        feedback["history"] = (
            f"Asked {len(session.history_questions)} questions, covering {history_hits}/{len(key_history_keywords)} key areas."
        )

        # Exam
        key_systems = list(case.physical_exam.keys())
        exam_hits = sum(1 for s in key_systems if s in session.exam_systems_viewed)
        scores["exam"] = round(min(w["exam"], (exam_hits / max(len(key_systems), 1)) * w["exam"]))
        feedback["exam"] = (
            f"Examined {len(session.exam_systems_viewed)}/{len(key_systems)} relevant systems."
        )

        # Investigations
        key_invs = list(case.investigations.keys())[:6]
        inv_hits = sum(1 for i in key_invs if i in session.investigations_ordered)
        scores["investigations"] = round(min(w["investigations"], (inv_hits / max(len(key_invs), 1)) * w["investigations"]))
        feedback["investigations"] = (
            f"Ordered {len(session.investigations_ordered)} investigations, {inv_hits}/{len(key_invs)} key ones included."
        )

        # Diagnosis
        diag_lower = session.diagnosis_submitted.lower()
        correct_lower = case.correct_diagnosis.lower()
        acceptable_lower = [d.lower() for d in case.acceptable_diagnoses]
        if any(term in diag_lower for term in correct_lower.split()):
            diag_score = w["diagnosis"]
            feedback["diagnosis"] = "Correct diagnosis identified."
        elif any(any(term in diag_lower for term in acc.split()) for acc in acceptable_lower):
            diag_score = round(w["diagnosis"] * 0.6)
            feedback["diagnosis"] = "Partially correct — core diagnosis captured but incomplete detail."
        else:
            diag_score = 0
            feedback["diagnosis"] = f"Incorrect. Correct diagnosis: {case.correct_diagnosis}"
        scores["diagnosis"] = diag_score

        # Management
        mgmt_text = " ".join(session.management_submitted).lower()
        mgmt_hits = sum(
            1 for step in case.correct_management
            if any(word in mgmt_text for word in step.lower().split()[:4])
        )
        scores["management"] = round(min(w["management"], (mgmt_hits / max(len(case.correct_management), 1)) * w["management"]))
        feedback["management"] = (
            f"Covered {mgmt_hits}/{len(case.correct_management)} management steps."
        )

        total = sum(scores.values())
        max_score = sum(w.values())

        return {
            "total": total,
            "max_score": max_score,
            "percentage": round((total / max_score) * 100),
            "grade": _grade(total / max_score),
            "domain_scores": scores,
            "domain_feedback": feedback,
            "correct_diagnosis": case.correct_diagnosis,
            "correct_management": case.correct_management,
            "key_learning_points": case.key_learning_points,
            "ai_feedback": "",
        }

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _get_active_session(self, session_id: str) -> SimulationSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")
        if session.status == "scored":
            raise ValueError("Session already completed")
        return session

    @staticmethod
    def _keyword_patient_response(case: ClinicalCase, question: str) -> str:
        """Fallback: match question to history data by keyword."""
        question_lower = question.lower()
        for key, response in case.history_data.items():
            if key.lower() in question_lower or any(word in question_lower for word in key.lower().split()):
                return response
        return (
            "I'm not sure what you mean. Could you ask me differently? "
            "I can tell you about my symptoms, medications, or medical history."
        )


def _grade(ratio: float) -> str:
    if ratio >= 0.85:
        return "Excellent"
    if ratio >= 0.70:
        return "Satisfactory"
    if ratio >= 0.50:
        return "Borderline"
    return "Unsatisfactory"


# ── Singleton ──────────────────────────────────────────────────────────────────
_engine: SimulationEngine | None = None


def get_simulation_engine(agent=None) -> SimulationEngine:
    global _engine
    if _engine is None:
        _engine = SimulationEngine(agent=agent)
    elif agent is not None:
        _engine.set_agent(agent)
    return _engine
