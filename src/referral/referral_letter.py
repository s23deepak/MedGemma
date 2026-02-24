"""
Specialist referral letter service.

Generates a formal referral letter whenever an encounter plan includes a
specialist referral order.  The letter incorporates:
  - Patient demographics and full clinical history
  - All longitudinal memories (allergies, medications, diagnoses, procedures)
  - Current encounter SOAP assessment and management plan
  - Vitals / recent labs
  - Referring provider signature block

Letters are stored in Firestore at:
  patients/{patient_id}/referral_letters/{letter_id}

and returned with the encounter approval response so the care team can
copy/print them immediately.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class ReferralLetter:
    """A single specialist referral letter."""
    letter_id: str
    patient_id: str
    encounter_id: str
    referred_to_specialty: str          # e.g. "Cardiology"
    referred_to_provider: str           # optional specific name
    referring_provider: str             # e.g. "Dr. Sarah Smith"
    reason: str                         # one-line reason
    letter_text: str                    # full formatted letter
    urgency: str                        # routine | urgent | emergency
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "letter_id": self.letter_id,
            "patient_id": self.patient_id,
            "encounter_id": self.encounter_id,
            "referred_to_specialty": self.referred_to_specialty,
            "referred_to_provider": self.referred_to_provider,
            "referring_provider": self.referring_provider,
            "reason": self.reason,
            "letter_text": self.letter_text,
            "urgency": self.urgency,
            "created_at": self.created_at.isoformat(),
        }


# ── Specialty keyword detection ───────────────────────────────────────────────

SPECIALTY_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bcardiol", re.I),        "Cardiology"),
    (re.compile(r"\bendocrinol", re.I),     "Endocrinology"),
    (re.compile(r"\bneurol", re.I),         "Neurology"),
    (re.compile(r"\bpulmonol", re.I),       "Pulmonology"),
    (re.compile(r"\bnephrol", re.I),        "Nephrology"),
    (re.compile(r"\bgastroenterol", re.I),  "Gastroenterology"),
    (re.compile(r"\brheumatol", re.I),      "Rheumatology"),
    (re.compile(r"\boncol", re.I),          "Oncology"),
    (re.compile(r"\borthop", re.I),         "Orthopedics"),
    (re.compile(r"\burol", re.I),           "Urology"),
    (re.compile(r"\bdermatol", re.I),       "Dermatology"),
    (re.compile(r"\bophthalmol", re.I),     "Ophthalmology"),
    (re.compile(r"\bpsychiatr", re.I),      "Psychiatry"),
    (re.compile(r"\bhematol", re.I),        "Hematology"),
    (re.compile(r"\binfectious\s+disease", re.I), "Infectious Disease"),
    (re.compile(r"\bvascular\s+surg", re.I), "Vascular Surgery"),
    (re.compile(r"\bgynecol|ob[-/]gyn", re.I), "Obstetrics & Gynecology"),
    (re.compile(r"\bspecialist", re.I),     "Specialist"),
]


def _detect_specialty(text: str) -> str:
    """Return the first specialty detected in text, or 'Specialist'."""
    for pattern, specialty in SPECIALTY_PATTERNS:
        if pattern.search(text):
            return specialty
    return "Specialist"


def _detect_urgency(text: str) -> str:
    """Infer urgency from text keywords."""
    text_lower = text.lower()
    if any(w in text_lower for w in ["urgent", "emergency", "stat", "immediately"]):
        return "urgent"
    return "routine"


# ── Service ───────────────────────────────────────────────────────────────────

class ReferralLetterService:
    """Generates and stores referral letters after encounter approval."""

    def __init__(self, fhir_server):
        self.fhir = fhir_server

    # ── Public API ────────────────────────────────────────────────────────────

    def generate_letters_for_encounter(
        self,
        patient_id: str,
        encounter_id: str,
        referral_orders: list[str],
        soap_note,
        patient_context: dict,
        memories: list[dict],
        referring_provider: str = "",
        agent=None,
    ) -> list[ReferralLetter]:
        """
        Create one referral letter per referral order found in the encounter.

        Args:
            referral_orders: List of referral strings from pending_orders["referrals"]
            soap_note:       EnhancedSOAPNote from the encounter
            patient_context: Full patient summary dict from FHIR
            memories:        List of memory dicts from PatientMemory.get_all()
            referring_provider: Name of the doctor approving the encounter
            agent:           Optional MedGemma agent for AI-generated text

        Returns:
            List of generated ReferralLetter objects
        """
        letters: list[ReferralLetter] = []
        for order in referral_orders:
            specialty = _detect_specialty(order)
            urgency = _detect_urgency(order)

            letter = self._generate_single_letter(
                patient_id=patient_id,
                encounter_id=encounter_id,
                referral_order=order,
                specialty=specialty,
                urgency=urgency,
                soap_note=soap_note,
                patient_context=patient_context,
                memories=memories,
                referring_provider=referring_provider,
                agent=agent,
            )
            letters.append(letter)
            self._write_to_firestore(letter)

        return letters

    def get_letters(self, patient_id: str) -> list[dict]:
        """Return all referral letters for a patient from Firestore (newest first)."""
        try:
            from src.config.firebase_config import get_firestore_client, is_firebase_available
            if not is_firebase_available():
                return []
            db = get_firestore_client()
            if db is None:
                return []
            docs = (
                db.collection("patients")
                .document(patient_id)
                .collection("referral_letters")
                .order_by("created_at", direction="DESCENDING")
                .stream()
            )
            return [d.to_dict() for d in docs]
        except Exception as e:
            logger.warning(f"get_letters({patient_id}) failed: {e}")
            return []

    # ── Internal generation ───────────────────────────────────────────────────

    def _generate_single_letter(
        self,
        patient_id: str,
        encounter_id: str,
        referral_order: str,
        specialty: str,
        urgency: str,
        soap_note,
        patient_context: dict,
        memories: list[dict],
        referring_provider: str,
        agent,
    ) -> ReferralLetter:
        reason = f"Referral to {specialty} — {referral_order}"

        if agent is not None:
            letter_text = self._call_agent_letter(
                referral_order, specialty, urgency,
                soap_note, patient_context, memories,
                referring_provider, agent,
            )
        else:
            letter_text = self._structured_letter(
                referral_order, specialty, urgency,
                soap_note, patient_context, memories,
                referring_provider,
            )

        return ReferralLetter(
            letter_id=f"RL-{uuid.uuid4().hex[:8].upper()}",
            patient_id=patient_id,
            encounter_id=encounter_id,
            referred_to_specialty=specialty,
            referred_to_provider="",
            referring_provider=referring_provider,
            reason=reason,
            letter_text=letter_text,
            urgency=urgency,
        )

    def _call_agent_letter(
        self,
        referral_order: str,
        specialty: str,
        urgency: str,
        soap_note,
        patient_context: dict,
        memories: list[dict],
        referring_provider: str,
        agent,
    ) -> str:
        """Ask MedGemma to write the referral letter."""
        patient = patient_context.get("patient", {})
        conditions = patient_context.get("conditions", [])
        meds = patient_context.get("medications", [])
        allergies = patient_context.get("allergies", [])
        observations = patient_context.get("observations", [])

        assessment = getattr(soap_note, "assessment", "") or ""
        plan = getattr(soap_note, "plan", "") or ""

        # Build memory summary
        mem_lines = self._format_memories(memories)

        obs_summary = "; ".join(f"{o.get('type','')} {o.get('value','')}" for o in observations[:6]) or "Not recorded"
        prompt = (
            f"Write a formal specialist referral letter from a physician to a {specialty} specialist.\n\n"
            f"Patient: {patient.get('name', 'Patient')}, "
            f"{patient.get('age', '?')}y {patient.get('gender', '')}\n"
            f"Referring Provider: {referring_provider or 'Attending Physician'}\n"
            f"Referral Reason: {referral_order}\n"
            f"Urgency: {urgency.capitalize()}\n\n"
            f"Active Conditions: {', '.join(c.get('name','') for c in conditions) or 'None documented'}\n"
            f"Current Medications: {', '.join(m.get('name','') for m in meds) or 'None'}\n"
            f"Allergies: {', '.join(a.get('substance','') for a in allergies) or 'NKDA'}\n"
            f"Recent Vitals/Labs: {obs_summary}\n\n"
            f"Clinical Assessment from this encounter:\n{assessment[:600]}\n\n"
            f"Management Plan:\n{plan[:400]}\n\n"
            f"Patient Memory Summary:\n{mem_lines}\n\n"
            f"Write a complete, formal referral letter (3-4 paragraphs) including:\n"
            f"1. Opening: patient introduction and reason for referral\n"
            f"2. Clinical history and relevant background (include memory details)\n"
            f"3. Current encounter findings and what specific evaluation is requested\n"
            f"4. Closing with contact information placeholder\n"
            f"Use professional medical letter format."
        )
        try:
            result = agent.process_query(prompt)
            return result.get(
                "response",
                self._structured_letter(
                    referral_order, specialty, urgency,
                    soap_note, patient_context, memories, referring_provider,
                ),
            )
        except Exception as e:
            logger.warning(f"Agent referral letter generation failed: {e}")
            return self._structured_letter(
                referral_order, specialty, urgency,
                soap_note, patient_context, memories, referring_provider,
            )

    @staticmethod
    def _structured_letter(
        referral_order: str,
        specialty: str,
        urgency: str,
        soap_note,
        patient_context: dict,
        memories: list[dict],
        referring_provider: str,
    ) -> str:
        """Build a complete referral letter without AI."""
        from datetime import datetime as _dt
        today = _dt.now().strftime("%B %d, %Y")

        patient = patient_context.get("patient", {})
        name = patient.get("name", "the patient")
        age = patient.get("age", "?")
        gender = patient.get("gender", "")
        dob = patient.get("birthDate", "")
        conditions = patient_context.get("conditions", [])
        meds = patient_context.get("medications", [])
        allergies = patient_context.get("allergies", [])
        observations = patient_context.get("observations", [])

        assessment = getattr(soap_note, "assessment", "") or "See clinical notes"
        plan = getattr(soap_note, "plan", "") or "Specialist evaluation planned"

        allergy_str = (
            ", ".join(a.get("substance", "") for a in allergies)
            if allergies else "No known drug allergies"
        )
        cond_str = (
            "\n".join(f"  - {c.get('name','')} (onset {c.get('onset','')})" for c in conditions)
            if conditions else "  - None documented"
        )
        med_str = (
            "\n".join(f"  - {m.get('name','')} {m.get('dosage','')}" for m in meds)
            if meds else "  - None"
        )
        obs_str = (
            "\n".join(f"  - {o.get('type','')}: {o.get('value','')}" for o in observations[:8])
            if observations else "  - Not available"
        )

        # Memories — group by category
        mem_section = ""
        if memories:
            mem_lines = []
            for m in memories[:20]:
                mem_text = m.get("memory", m.get("text", ""))
                if mem_text:
                    mem_lines.append(f"  - {mem_text}")
            if mem_lines:
                mem_section = "\nLONGITUDINAL CLINICAL MEMORY\n" + "\n".join(mem_lines) + "\n"

        lines = [
            f"Date: {today}",
            f"Re: Referral — {name}",
            f"{'DOB: ' + dob if dob else ''}{'  |  ' if dob and (age or gender) else ''}",
            f"Patient ID: {patient.get('id', 'N/A')}",
            "",
            f"Dear {specialty} Colleague,",
            "",
            f"I am writing to refer {name}, a {age}-year-old {gender}, for specialist evaluation "
            f"and management by your {specialty} service. {'This is an URGENT referral.' if urgency == 'urgent' else ''}",
            "",
            f"REASON FOR REFERRAL",
            f"  {referral_order}",
            "",
            f"ACTIVE CONDITIONS",
            cond_str,
            "",
            f"CURRENT MEDICATIONS",
            med_str,
            "",
            f"ALLERGIES",
            f"  {allergy_str}",
            "",
            f"RECENT VITALS / LABORATORY RESULTS",
            obs_str,
            "",
            f"CLINICAL ASSESSMENT (from this encounter)",
            f"  {assessment[:800]}",
            "",
            f"MANAGEMENT PLAN",
            f"  {plan[:600]}",
        ]

        if mem_section:
            lines.append(mem_section)

        lines += [
            "",
            "I would be grateful for your expert evaluation and management of this patient. "
            "Please do not hesitate to contact our office if you require any additional "
            "clinical information or documentation.",
            "",
            "Yours sincerely,",
            "",
            f"{referring_provider or 'Attending Physician'}",
            "[Practice / Hospital Name]",
            "[Phone: XXX-XXX-XXXX  |  Fax: XXX-XXX-XXXX]",
            "[Email: provider@hospital.org]",
        ]
        return "\n".join(lines)

    @staticmethod
    def _format_memories(memories: list[dict]) -> str:
        """Format memory list into a compact text block."""
        if not memories:
            return "No prior memories recorded."
        lines = []
        for m in memories[:20]:
            text = m.get("memory", m.get("text", ""))
            if text:
                lines.append(f"- {text}")
        return "\n".join(lines) if lines else "No prior memories recorded."

    # ── Firestore persistence ─────────────────────────────────────────────────

    def _write_to_firestore(self, letter: ReferralLetter) -> None:
        """Persist referral letter to patients/{patient_id}/referral_letters/{letter_id}."""
        try:
            from src.config.firebase_config import get_firestore_client, is_firebase_available
            if not is_firebase_available():
                return
            db = get_firestore_client()
            if db is None:
                return
            (
                db.collection("patients")
                .document(letter.patient_id)
                .collection("referral_letters")
                .document(letter.letter_id)
                .set(letter.to_dict())
            )
            logger.info(
                f"Referral letter {letter.letter_id} written to Firestore "
                f"for patient {letter.patient_id} → {letter.referred_to_specialty}"
            )
        except Exception as e:
            logger.warning(f"Failed to write referral letter to Firestore: {e}")


# ── Singleton ──────────────────────────────────────────────────────────────────
_referral_service: ReferralLetterService | None = None


def get_referral_letter_service(fhir_server=None) -> ReferralLetterService:
    """Get or create the ReferralLetterService singleton."""
    global _referral_service
    if _referral_service is None:
        if fhir_server is None:
            from src.ehr import get_fhir_server
            fhir_server = get_fhir_server()
        _referral_service = ReferralLetterService(fhir_server)
    return _referral_service
