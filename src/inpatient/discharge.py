"""
Inpatient Discharge Planner Service.

Generates:
  1. Patient-friendly discharge summary (5th-6th grade reading level)
     with follow-up tasks, medication changes, and red-flag symptoms.
  2. Readmission risk assessment (rule-based binning) with optional
     MedGemma narrative explanation.

Uses MISSING placeholder for required data not found in the record,
surfaced to UI so physician cannot sign an incomplete discharge document.
"""

from __future__ import annotations

import logging
import re as _re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ReadmissionRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Conditions associated with high 30-day readmission risk
HIGH_RISK_CONDITIONS = [
    "heart failure", "congestive heart failure", "chf",
    "chronic obstructive pulmonary disease", "copd",
    "pneumonia",
    "sepsis",
    "acute myocardial infarction", "ami", "mi",
    "chronic kidney disease stage", "ckd",
    "cirrhosis", "liver failure",
]

MEDIUM_RISK_CONDITIONS = [
    "diabetes", "diabetic", "hyperglycemia",
    "atrial fibrillation", "a-fib",
    "stroke", "tia",
    "post-surgical", "postoperative",
    "deep vein thrombosis", "pulmonary embolism",
    "hypertensive urgency", "hypertensive emergency",
]

# Medications needing specific discharge counseling
DISCHARGE_COUNSELING_MEDS = {
    "insulin": "Check blood sugar daily. Signs of low blood sugar: shaking, sweating, confusion.",
    "warfarin": "Get INR checked as directed. Avoid drastic changes in vitamin K foods.",
    "apixaban": "Take exactly as prescribed. Do not stop without talking to your doctor.",
    "furosemide": "Weigh yourself every morning. Call your doctor if you gain more than 2 lbs in a day.",
    "digoxin": "Check pulse before each dose. Call your doctor if pulse is below 60.",
    "metformin": "Take with food. Hold if you need contrast dye for imaging.",
}


# ── Charlson Comorbidity Index weights ────────────────────────────────────────
# Used by LACE score (C component). Keyword matching against condition names.
# Final score is capped at 5 per the LACE index definition.
CHARLSON_WEIGHTS: dict[str, int] = {
    # Weight 1 — common chronic conditions
    "myocardial infarction": 1, "ami": 1,
    "heart failure": 1, "chf": 1, "congestive heart failure": 1,
    "peripheral vascular": 1,
    "dementia": 1,
    "copd": 1, "chronic obstructive pulmonary disease": 1,
    "connective tissue": 1, "rheumatologic": 1,
    "peptic ulcer": 1,
    "mild liver": 1,
    "diabetes": 1, "diabetic": 1,
    # Weight 2 — more serious complications
    "hemiplegia": 2, "hemiparesis": 2,
    "chronic kidney": 2, "ckd": 2, "renal failure": 2,
    "moderate liver": 2, "severe liver": 2, "cirrhosis": 2,
    "diabetes with end organ": 2,
    "tumor": 2, "lymphoma": 2, "leukemia": 2, "solid tumor": 2,
    # Weight 6 — severe/terminal conditions
    "metastatic": 6, "metastasis": 6,
    "aids": 6,
}


@dataclass
class MedReconciliation:
    """Medication reconciliation comparing home medications vs current inpatient orders."""
    home_medications: list[dict]    # medications from FHIR admission baseline
    current_medications: list[dict] # active medication orders during admission
    added_meds: list[dict]          # new medications added during admission
    discontinued_meds: list[dict]   # home medications not continued
    changed_meds: list[dict]        # dose/route changed (requires structured data; left empty)
    unchanged_meds: list[dict]      # continued without change
    discrepancies: list[dict]       # [{med, type, detail}]

    def to_dict(self) -> dict:
        return {
            "home_medications": self.home_medications,
            "current_medications": self.current_medications,
            "added_meds": self.added_meds,
            "discontinued_meds": self.discontinued_meds,
            "changed_meds": self.changed_meds,
            "unchanged_meds": self.unchanged_meds,
            "discrepancies": self.discrepancies,
        }


@dataclass
class DischargeSummary:
    """Structured patient-facing discharge summary."""
    patient_id: str
    patient_name: str
    generated_at: str
    why_admitted: str
    what_was_done: str
    medications: list[dict]     # {name, dosage, change, counseling}
    follow_up_tasks: list[str]
    red_flag_symptoms: list[str]
    activity_restrictions: str
    diet_instructions: str
    missing_fields: list[str]   # items requiring physician completion
    readmission_risk: ReadmissionRisk
    readmission_risk_reasons: list[str]
    readmission_risk_explanation: str
    source: str
    # LACE index fields (default 0/{} for backwards compat with existing call sites)
    lace_score: int = 0
    lace_components: dict = field(default_factory=dict)
    reconciliation: MedReconciliation | None = None

    def to_dict(self) -> dict:
        return {
            "patient_id": self.patient_id,
            "patient_name": self.patient_name,
            "generated_at": self.generated_at,
            "why_admitted": self.why_admitted,
            "what_was_done": self.what_was_done,
            "medications": self.medications,
            "follow_up_tasks": self.follow_up_tasks,
            "red_flag_symptoms": self.red_flag_symptoms,
            "activity_restrictions": self.activity_restrictions,
            "diet_instructions": self.diet_instructions,
            "missing_fields": self.missing_fields,
            "readmission_risk": self.readmission_risk.value,
            "readmission_risk_reasons": self.readmission_risk_reasons,
            "readmission_risk_explanation": self.readmission_risk_explanation,
            "source": self.source,
            "lace_score": self.lace_score,
            "lace_components": self.lace_components,
            "reconciliation": self.reconciliation.to_dict() if self.reconciliation else None,
        }


class InpatientDischargePlanner:
    """Generates patient-friendly discharge summaries with readmission risk."""

    def __init__(self, fhir_server):
        self.fhir = fhir_server

    # ── Public API ────────────────────────────────────────────────────────────

    def generate_discharge_summary(
        self,
        patient_id: str,
        soap_note: str = "",
        agent=None,
    ) -> DischargeSummary:
        """
        Generate a complete discharge summary.

        Args:
            patient_id: Patient to generate summary for.
            soap_note:  Optional SOAP note text from current encounter.
            agent:      Optional MedGemma agent for narrative generation.

        Returns a DischargeSummary dataclass.
        """
        ctx = self._build_context(patient_id, soap_note)
        if not ctx:
            return DischargeSummary(
                patient_id=patient_id, patient_name="Unknown",
                generated_at=datetime.now().isoformat(),
                why_admitted="MISSING", what_was_done="MISSING",
                medications=[], follow_up_tasks=[], red_flag_symptoms=[],
                activity_restrictions="MISSING", diet_instructions="MISSING",
                missing_fields=["Patient not found or not an inpatient"],
                readmission_risk=ReadmissionRisk.LOW,
                readmission_risk_reasons=[], readmission_risk_explanation="",
                source="error",
            )

        # Medication reconciliation (home vs current orders)
        reconciliation = self.reconcile_medications(patient_id)

        risk, risk_reasons = self.assess_readmission_risk(ctx)
        lace_score = ctx.get("_lace_score", 0)
        lace_components = ctx.get("_lace_components", {})
        risk_explanation = ""
        if agent:
            risk_explanation = self._generate_risk_explanation(risk, risk_reasons, ctx, agent)

        if agent:
            return self._call_agent(
                ctx, risk, risk_reasons, risk_explanation, agent,
                lace_score=lace_score, lace_components=lace_components,
                reconciliation=reconciliation,
            )
        return self._structured_summary(
            ctx, risk, risk_reasons, risk_explanation,
            lace_score=lace_score, lace_components=lace_components,
            reconciliation=reconciliation,
        )

    def assess_readmission_risk(self, ctx: dict) -> tuple[ReadmissionRisk, list[str]]:
        """
        LACE-index readmission risk assessment.

        LACE = L (length of stay, 0-7) + A (acuity, 0 or 3) +
               C (Charlson comorbidity index, 0-5) + E (ED visits, 0-4).

        Thresholds: ≥10 = HIGH, 5-9 = MEDIUM, <5 = LOW.
        Also builds human-readable reasons for the UI.
        """
        conditions = ctx.get("conditions", [])
        progress_notes = ctx.get("progress_notes", [])
        los_hours = ctx.get("los_hours", 0.0)

        # Charlson comorbidity index (capped at 5)
        charlson = self._compute_charlson_score(conditions)

        # Acuity: 3 points if admitted via ED (check patient admission_type or notes)
        acuity_text = (
            ctx["patient"].get("admission_type", "")
            + " ".join(n.get("note_text", "")[:50] for n in progress_notes[:2])
        ).lower()
        acuity = 3 if any(kw in acuity_text for kw in ["emergency", "ed admit", "er admit"]) else 0

        # ED visit count proxy (from progress note keywords)
        ed_visits = sum(
            1 for n in progress_notes
            if any(kw in n.get("note_text", "").lower() for kw in ["ed visit", "emergency department visit", "er visit"])
        )

        lace_score, lace_components = self._compute_lace(los_hours, acuity, charlson, ed_visits)

        # Risk threshold
        if lace_score >= 10:
            risk = ReadmissionRisk.HIGH
        elif lace_score >= 5:
            risk = ReadmissionRisk.MEDIUM
        else:
            risk = ReadmissionRisk.LOW

        # Human-readable reasons (also capture legacy rule matches for completeness)
        reasons: list[str] = []
        conditions_text = " ".join(c["name"].lower() for c in conditions)

        for cond in HIGH_RISK_CONDITIONS:
            if cond in conditions_text:
                reasons.append(f"High-risk diagnosis: {cond.title()}")
        notes_text = " ".join(n.get("note_text", "").lower() for n in progress_notes)
        if any(kw in notes_text for kw in ["prior admission", "readmission", "previously admitted", "re-admitted"]):
            reasons.append("Prior recent admission documented in notes")
        if los_hours > 168:
            reasons.append(f"Prolonged LOS ({los_hours/24:.1f} days)")
        for cond in MEDIUM_RISK_CONDITIONS:
            if cond in conditions_text:
                reasons.append(f"Medium-risk diagnosis: {cond.title()}")
        if len(ctx.get("medications", [])) >= 5:
            reasons.append(f"Polypharmacy ({len(ctx['medications'])} medications)")
        reasons.append(f"LACE index score: {lace_score} (L={lace_components.get('l',0)}, A={lace_components.get('a',0)}, C={lace_components.get('c',0)}, E={lace_components.get('e',0)})")

        if not reasons:
            reasons = ["No significant risk factors identified"]

        # Stash LACE data in ctx for generate_discharge_summary() to retrieve
        ctx["_lace_score"] = lace_score
        ctx["_lace_components"] = lace_components

        return risk, reasons

    # ── AI generation ─────────────────────────────────────────────────────────

    def _call_agent(
        self, ctx, risk, risk_reasons, risk_explanation, agent,
        lace_score: int = 0, lace_components: dict | None = None,
        reconciliation: MedReconciliation | None = None,
    ) -> DischargeSummary:
        pt = ctx["patient"]
        cond_str = ", ".join(c["name"] for c in ctx["conditions"])
        med_str = "\n".join(f"  - {m['name']} {m['dosage']}" for m in ctx["medications"])
        allergy_str = ", ".join(a["substance"] for a in ctx["allergies"]) or "NKDA"
        latest_note = ctx["progress_notes"][0]["note_text"][:400] if ctx["progress_notes"] else ""
        pending_orders = [o for o in ctx["active_orders"] if o.get("status") == "pending"]

        prompt = (
            f"You are generating a patient-friendly hospital discharge summary.\n"
            f"Write at a 5th-6th grade reading level. Avoid medical jargon — explain terms simply.\n\n"
            f"Patient: {pt['name']}, {pt.get('age', '?')}y {pt.get('gender', '')}\n"
            f"Admitted for: {cond_str}\n"
            f"LOS: {ctx['los_hours']/24:.1f} days\n"
            f"Allergies: {allergy_str}\n\n"
            f"Medications at discharge:\n{med_str}\n\n"
            f"Latest clinical note:\n{latest_note}\n\n"
            f"Pending/follow-up orders: {', '.join(o['name'] for o in pending_orders) or 'None'}\n\n"
            f"Additional SOAP note context:\n{ctx.get('soap_note', '')[:500]}\n\n"
            f"Generate a discharge summary with these sections:\n"
            f"WHY YOU WERE ADMITTED: (1-2 simple sentences)\n"
            f"WHAT WE DID: (treatments, procedures — in plain language)\n"
            f"YOUR MEDICATIONS: (list each medication, what it's for, any changes — use MISSING if unknown)\n"
            f"FOLLOW-UP APPOINTMENTS: (list needed follow-ups — use MISSING if not specified)\n"
            f"WHEN TO CALL YOUR DOCTOR OR GO TO THE ER: (specific warning symptoms)\n"
            f"ACTIVITY AND DIET: (restrictions or instructions — use MISSING if unclear)\n\n"
            f"IMPORTANT: If any required information is missing from the record, write the word "
            f"MISSING in capital letters as a placeholder so the physician can fill it in."
        )
        try:
            response = agent.chat(prompt)
            parsed = self._parse_ai_discharge(response)
            missing = [f for f in ["WHY YOU WERE ADMITTED", "WHAT WE DID", "FOLLOW-UP APPOINTMENTS"]
                       if "MISSING" in parsed.get(f.lower().replace(" ", "_"), "")]

            return DischargeSummary(
                patient_id=pt["id"],
                patient_name=pt["name"],
                generated_at=datetime.now().isoformat(),
                why_admitted=parsed.get("why_admitted", response[:200]),
                what_was_done=parsed.get("what_was_done", "MISSING"),
                medications=self._build_discharge_meds(ctx["medications"]),
                follow_up_tasks=self._extract_follow_up(parsed.get("follow_up", "")),
                red_flag_symptoms=self._extract_red_flags(parsed.get("warning_symptoms", "")),
                activity_restrictions=parsed.get("activity_diet", "MISSING"),
                diet_instructions=parsed.get("activity_diet", "MISSING"),
                missing_fields=missing,
                readmission_risk=risk,
                readmission_risk_reasons=risk_reasons,
                readmission_risk_explanation=risk_explanation,
                source="medgemma",
                lace_score=lace_score,
                lace_components=lace_components or {},
                reconciliation=reconciliation,
            )
        except Exception as e:
            logger.warning(f"Agent call failed for discharge summary {pt['id']}: {e}")
            return self._structured_summary(
                ctx, risk, risk_reasons, risk_explanation,
                lace_score=lace_score, lace_components=lace_components or {},
                reconciliation=reconciliation,
            )

    def _structured_summary(
        self, ctx, risk, risk_reasons, risk_explanation,
        lace_score: int = 0, lace_components: dict | None = None,
        reconciliation: MedReconciliation | None = None,
    ) -> DischargeSummary:
        """Build a structured discharge summary without AI."""
        pt = ctx["patient"]
        conditions = ctx["conditions"]
        primary_dx = conditions[0]["name"] if conditions else "MISSING — physician must specify"
        los_days = ctx["los_hours"] / 24

        why_admitted = (
            f"You were admitted to the hospital because of {primary_dx.lower()}. "
            f"You stayed with us for {los_days:.1f} days."
        )

        # What was done — based on orders
        treatments = [o["name"] for o in ctx["active_orders"] if o.get("type") in ("medication", "procedure")]
        what_was_done = (
            "During your stay, we: " + "; ".join(treatments[:5]) + "."
            if treatments else "MISSING — physician must document treatments provided."
        )

        # Medications with counseling
        discharge_meds = self._build_discharge_meds(ctx["medications"])

        # Follow-up tasks from pending orders
        follow_up_tasks = [
            o["name"] for o in ctx["active_orders"]
            if o.get("status") == "pending" or o.get("type") == "consult"
        ]
        if not follow_up_tasks:
            follow_up_tasks = ["MISSING — physician must specify follow-up appointments"]

        # Red flags — condition-specific
        red_flags = self._derive_red_flags(conditions)

        # Diet from orders
        diet_order = next((o["name"] for o in ctx["active_orders"] if o.get("type") == "diet"), None)
        diet_instructions = diet_order or "MISSING — physician must specify dietary restrictions"

        missing = []
        if "MISSING" in why_admitted:
            missing.append("Primary diagnosis")
        if "MISSING" in what_was_done:
            missing.append("Treatments provided")
        if any("MISSING" in t for t in follow_up_tasks):
            missing.append("Follow-up appointments")

        return DischargeSummary(
            patient_id=pt["id"],
            patient_name=pt["name"],
            generated_at=datetime.now().isoformat(),
            why_admitted=why_admitted,
            what_was_done=what_was_done,
            medications=discharge_meds,
            follow_up_tasks=follow_up_tasks,
            red_flag_symptoms=red_flags,
            activity_restrictions="MISSING — physician must specify activity restrictions",
            diet_instructions=diet_instructions,
            missing_fields=missing,
            readmission_risk=risk,
            readmission_risk_reasons=risk_reasons,
            readmission_risk_explanation=risk_explanation,
            source="structured_fallback",
            lace_score=lace_score,
            lace_components=lace_components or {},
            reconciliation=reconciliation,
        )

    def _generate_risk_explanation(self, risk, reasons, ctx, agent) -> str:
        """Use MedGemma to explain readmission risk in patient-friendly terms."""
        pt = ctx["patient"]
        cond_str = ", ".join(c["name"] for c in ctx["conditions"][:3])
        prompt = (
            f"Patient: {pt['name']}, {pt.get('age', '?')}y. Conditions: {cond_str}.\n"
            f"Readmission risk: {risk.value.upper()}\n"
            f"Reasons: {', '.join(reasons)}\n\n"
            f"In 2-3 sentences, explain (in plain language the patient can understand) "
            f"why this patient has a {risk.value} risk of returning to the hospital, "
            f"and what they can do to reduce that risk at home."
        )
        try:
            return agent.chat(prompt)
        except Exception as e:
            logger.warning(f"Risk explanation failed: {e}")
            return ""

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _compute_charlson_score(self, conditions: list[dict]) -> int:
        """
        Compute a proxy Charlson Comorbidity Index score from condition names.

        Returns an integer in [0, 5] — capped per the LACE index C component.
        """
        joined = " ".join(c.get("name", "").lower() for c in conditions)
        score = 0
        seen: set[int] = set()
        for keyword, weight in CHARLSON_WEIGHTS.items():
            if keyword in joined and weight not in seen:
                score += weight
                seen.add(weight)
        return min(score, 5)

    def _compute_lace(
        self, los_hours: float, acuity: int, charlson: int, ed_visits: int
    ) -> tuple[int, dict]:
        """
        Compute LACE index score.

        L = Length of stay (days, capped at 7)
        A = Acuity (0 or 3; 3 if admitted via emergency department)
        C = Charlson comorbidity index (0-5)
        E = ED visits in last 6 months (0-4)

        Returns (total_score, {l, a, c, e, total}).
        """
        l_score = min(int(los_hours / 24), 7)
        a_score = acuity  # already 0 or 3
        c_score = charlson  # already 0-5
        e_score = min(ed_visits, 4)
        total = l_score + a_score + c_score + e_score
        return total, {"l": l_score, "a": a_score, "c": c_score, "e": e_score, "total": total}

    def reconcile_medications(self, patient_id: str) -> MedReconciliation:
        """
        Compare admission baseline medications against current active medication orders
        to identify new additions and discontinued drugs.

        Returns a MedReconciliation dataclass.
        """
        ctx = self._build_context(patient_id)
        if not ctx:
            return MedReconciliation([], [], [], [], [], [], [])

        home_meds: list[dict] = ctx.get("medications", [])
        # Filter active_orders to medication type only
        current_orders: list[dict] = [
            o for o in ctx.get("active_orders", [])
            if o.get("type", "").lower() == "medication"
        ]

        def _normalize(name: str) -> str:
            """Strip dose/route suffixes and lowercase for fuzzy matching."""
            s = name.lower()
            s = _re.sub(r"\s*\d+\.?\d*\s*(mg|mcg|ml|iu|g|units?)\b", "", s)
            s = _re.sub(
                r"\b(oral|iv|sq|im|inhaled|inhaler|patch|tablet|capsule"
                r"|drops?|cream|gel|spray|solution|suspension)\b", "", s
            )
            return s.strip()

        home_map: dict[str, dict] = {_normalize(m["name"]): m for m in home_meds}
        current_map: dict[str, dict] = {_normalize(o["name"]): o for o in current_orders}

        added = [v for k, v in current_map.items() if k not in home_map]
        discontinued = [v for k, v in home_map.items() if k not in current_map]
        unchanged = [v for k, v in home_map.items() if k in current_map]

        discrepancies: list[dict] = []
        for med in discontinued:
            discrepancies.append({
                "med": med.get("name", ""),
                "type": "discontinued",
                "detail": "Medication present on admission but not in current orders",
            })
        for med in added:
            discrepancies.append({
                "med": med.get("name", ""),
                "type": "new_addition",
                "detail": "Medication added during admission",
            })

        return MedReconciliation(
            home_medications=home_meds,
            current_medications=current_orders,
            added_meds=added,
            discontinued_meds=discontinued,
            changed_meds=[],  # requires structured dosage comparison; left for future work
            unchanged_meds=unchanged,
            discrepancies=discrepancies,
        )

    def _build_context(self, patient_id: str, soap_note: str = "") -> dict:
        summary = self.fhir.get_patient_summary(patient_id)
        if not summary:
            return {}

        now = datetime.now()
        admission_str = summary["patient"].get("admission_date", "")
        los_hours = 0.0
        if admission_str:
            try:
                los_hours = (now - datetime.fromisoformat(admission_str)).total_seconds() / 3600
            except ValueError:
                pass

        orders = self.fhir.get_active_orders(patient_id) if hasattr(self.fhir, "get_active_orders") else []
        notes = self.fhir.get_progress_notes(patient_id) if hasattr(self.fhir, "get_progress_notes") else []

        return {
            "patient": summary["patient"],
            "conditions": summary.get("conditions", []),
            "medications": summary.get("medications", []),
            "allergies": summary.get("allergies", []),
            "recent_observations": summary.get("recent_observations", []),
            "active_orders": orders,
            "progress_notes": notes,
            "los_hours": los_hours,
            "soap_note": soap_note,
        }

    def _build_discharge_meds(self, medications: list[dict]) -> list[dict]:
        """Build medication list with counseling notes."""
        result = []
        for med in medications:
            name = med["name"]
            counseling = ""
            for key, note in DISCHARGE_COUNSELING_MEDS.items():
                if key in name.lower():
                    counseling = note
                    break
            result.append({
                "name": name,
                "dosage": med.get("dosage", "As directed"),
                "change": "Continue",
                "counseling": counseling,
            })
        return result

    def _derive_red_flags(self, conditions: list[dict]) -> list[str]:
        """Return condition-appropriate red-flag return symptoms."""
        flags = [
            "Chest pain or pressure",
            "Difficulty breathing or shortness of breath",
            "Sudden confusion or difficulty speaking",
            "High fever (above 38.5°C / 101.3°F)",
        ]
        cond_text = " ".join(c["name"].lower() for c in conditions)
        if any(k in cond_text for k in ["heart failure", "chf"]):
            flags.append("Sudden weight gain (more than 2 lbs in one day or 5 lbs in one week)")
            flags.append("Swelling in legs, ankles, or feet that is getting worse")
        if "sepsis" in cond_text or "infection" in cond_text:
            flags.append("Signs of infection: redness, swelling, pus, warmth at any wound site")
        if "diabetes" in cond_text:
            flags.append("Blood sugar below 70 mg/dL (shakiness, sweating, confusion)")
            flags.append("Blood sugar above 300 mg/dL for more than 2 readings")
        return flags

    def _parse_ai_discharge(self, text: str) -> dict:
        """Extract sections from AI-generated discharge text."""
        sections: dict[str, str] = {}
        key_map = {
            "why you were admitted": "why_admitted",
            "what we did": "what_was_done",
            "your medications": "medications_text",
            "follow-up": "follow_up",
            "when to call": "warning_symptoms",
            "activity": "activity_diet",
        }
        current_key = None
        for line in text.splitlines():
            line_lower = line.lower().strip()
            matched = False
            for keyword, key in key_map.items():
                if line_lower.startswith(keyword) or keyword in line_lower:
                    current_key = key
                    remainder = line.split(":", 1)[-1].strip()
                    sections[current_key] = remainder + "\n" if remainder else ""
                    matched = True
                    break
            if not matched and current_key:
                sections[current_key] = sections.get(current_key, "") + line + "\n"
        return {k: v.strip() for k, v in sections.items()}

    def _extract_follow_up(self, text: str) -> list[str]:
        items = []
        for line in text.splitlines():
            line = line.strip().lstrip("•-* ")
            if line and len(line) > 5:
                items.append(line)
        return items[:10] if items else ["MISSING — physician must specify follow-up appointments"]

    def _extract_red_flags(self, text: str) -> list[str]:
        items = []
        for line in text.splitlines():
            line = line.strip().lstrip("•-* ")
            if line and len(line) > 5:
                items.append(line)
        if not items:
            return self._derive_red_flags([])
        return items[:8]


# ── Singleton ──────────────────────────────────────────────────────────────────
_discharge_planner: InpatientDischargePlanner | None = None


def get_discharge_planner(fhir_server=None) -> InpatientDischargePlanner:
    """Get or create the InpatientDischargePlanner singleton."""
    global _discharge_planner
    if _discharge_planner is None:
        if fhir_server is None:
            from src.ehr import get_fhir_server
            fhir_server = get_fhir_server()
        _discharge_planner = InpatientDischargePlanner(fhir_server)
    return _discharge_planner
