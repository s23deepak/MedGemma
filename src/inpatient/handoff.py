"""
SBAR Handoff Generator Service.

Generates structured shift sign-out packets for inpatient providers using the
SBAR (Situation-Background-Assessment-Recommendation) framework.

Also runs a completeness audit to verify:
  - Code status documented
  - Allergies mentioned
  - High-risk medications flagged
  - Active devices listed (Foley, central line, O2)
  - Contingency ("if-then") plan present
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# High-risk medications that must be flagged in handoffs
HIGH_RISK_MEDS = [
    "insulin", "heparin", "warfarin", "apixaban", "rivaroxaban", "enoxaparin",
    "morphine", "oxycodone", "hydromorphone", "fentanyl", "methadone",
    "vancomycin", "aminoglycoside", "gentamicin", "tobramycin",
    "digoxin", "lithium", "phenytoin", "carbamazepine",
    "norepinephrine", "epinephrine", "vasopressin", "dopamine",
]

# Devices that must be mentioned in handoffs
TRACKED_DEVICES = ["foley", "catheter", "central line", "picc", "arterial line",
                   "endotracheal", "ventilator", "chest tube", "ng tube"]


@dataclass
class CompletenessAudit:
    """Result of SBAR completeness check."""
    score: int          # 0–100
    max_score: int
    missing_fields: list[str]
    warnings: list[str]
    checks: dict[str, bool]

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "max_score": self.max_score,
            "percentage": round(self.score / self.max_score * 100) if self.max_score else 0,
            "missing_fields": self.missing_fields,
            "warnings": self.warnings,
            "checks": self.checks,
        }


class SBARHandoffService:
    """Generates SBAR sign-out packets with completeness auditing."""

    def __init__(self, fhir_server):
        self.fhir = fhir_server

    # ── Public API ────────────────────────────────────────────────────────────

    def generate_sbar(self, patient_id: str, agent=None) -> dict:
        """
        Generate a full SBAR handoff for a patient.

        Returns:
            {
                patient_id, patient_name,
                sbar: {situation, background, assessment, recommendation, contingency_plans},
                completeness: CompletenessAudit.to_dict(),
                generated_at, source
            }
        """
        ctx = self._build_context(patient_id)
        if not ctx:
            return {"error": f"Patient {patient_id} not found or not an inpatient"}

        if agent is not None:
            sbar = self._call_agent(ctx, agent)
        else:
            sbar = self._structured_sbar(ctx)

        audit = self.audit_completeness(ctx, sbar)

        return {
            "patient_id": patient_id,
            "patient_name": ctx["patient"]["name"],
            "sbar": sbar,
            "completeness": audit.to_dict(),
            "generated_at": datetime.now().isoformat(),
            "source": sbar.pop("_source", "structured_fallback"),
        }

    def audit_completeness(self, ctx: dict, sbar: dict) -> CompletenessAudit:
        """
        Rule-based completeness check on a generated SBAR.

        Each check is worth equal weight. Returns a CompletenessAudit.
        """
        checks: dict[str, bool] = {}
        missing: list[str] = []
        warnings: list[str] = []

        full_text = " ".join(str(v) for v in sbar.values()).lower()
        pt = ctx["patient"]

        # 1. Code status documented
        checks["code_status"] = any(k in full_text for k in ["full code", "dnr", "dni", "comfort care", "code status"])
        if not checks["code_status"]:
            missing.append("Code status not mentioned")

        # 2. Allergies mentioned
        allergy_names = [a["substance"].lower() for a in ctx.get("allergies", [])]
        checks["allergies"] = bool(allergy_names) and any(a in full_text for a in allergy_names)
        if not checks["allergies"] and allergy_names:
            missing.append(f"Allergies not mentioned ({', '.join(allergy_names)})")

        # 3. High-risk medications flagged
        patient_hrm = [
            m["name"] for m in ctx.get("medications", [])
            if any(h in m["name"].lower() for h in HIGH_RISK_MEDS)
        ]
        checks["high_risk_meds"] = not patient_hrm or any(m.lower() in full_text for m in patient_hrm)
        if not checks["high_risk_meds"]:
            warnings.append(f"High-risk meds not flagged: {', '.join(patient_hrm[:3])}")

        # 4. Active devices documented
        patient_devices = [
            o["name"] for o in ctx.get("active_orders", [])
            if any(d in o["name"].lower() for d in TRACKED_DEVICES)
        ]
        checks["active_devices"] = not patient_devices or any(d.lower() in full_text for d in patient_devices)
        if not checks["active_devices"]:
            warnings.append(f"Active devices not mentioned: {', '.join(patient_devices[:3])}")

        # 5. Contingency / "if-then" plan present
        checks["contingency_plan"] = any(k in full_text for k in ["if ", "when ", "should ", "notify ", "call ", "contact"])
        if not checks["contingency_plan"]:
            missing.append("No contingency (if-then) plan in Recommendation")

        # 6. Admission reason mentioned
        checks["admission_reason"] = bool(sbar.get("situation", "").strip())
        if not checks["admission_reason"]:
            missing.append("Situation section is empty")

        # 7. Assessment is non-empty
        checks["assessment_present"] = bool(sbar.get("assessment", "").strip())
        if not checks["assessment_present"]:
            missing.append("Assessment section is empty")

        # 8. Recommendation is non-empty
        checks["recommendation_present"] = bool(sbar.get("recommendation", "").strip())
        if not checks["recommendation_present"]:
            missing.append("Recommendation section is empty")

        score = sum(1 for v in checks.values() if v)
        return CompletenessAudit(
            score=score,
            max_score=len(checks),
            missing_fields=missing,
            warnings=warnings,
            checks=checks,
        )

    # ── Context builder ───────────────────────────────────────────────────────

    def _build_context(self, patient_id: str) -> dict:
        summary = self.fhir.get_patient_summary(patient_id)
        if not summary or summary["patient"].get("encounter_type") != "inpatient":
            return {}

        notes = []
        if hasattr(self.fhir, "get_progress_notes"):
            notes = self.fhir.get_progress_notes(patient_id)

        orders = []
        if hasattr(self.fhir, "get_active_orders"):
            orders = self.fhir.get_active_orders(patient_id)

        now = datetime.now()
        admission_str = summary["patient"].get("admission_date", "")
        los_hours = 0.0
        if admission_str:
            try:
                los_hours = (now - datetime.fromisoformat(admission_str)).total_seconds() / 3600
            except ValueError:
                pass

        # Last 12h events from notes
        cutoff_12h = now - timedelta(hours=12)
        recent_events = [
            n for n in notes
            if self._parse_dt(n.get("created_at", "")) >= cutoff_12h
        ]

        return {
            "patient": summary["patient"],
            "conditions": summary.get("conditions", []),
            "medications": summary.get("medications", []),
            "allergies": summary.get("allergies", []),
            "recent_observations": summary.get("recent_observations", []),
            "active_orders": orders,
            "progress_notes": notes,
            "recent_events": recent_events,
            "los_hours": los_hours,
        }

    # ── AI generation ─────────────────────────────────────────────────────────

    def _call_agent(self, ctx: dict, agent) -> dict:
        pt = ctx["patient"]
        los_days = ctx["los_hours"] / 24

        cond_str = "; ".join(c["name"] for c in ctx["conditions"])
        med_str = ", ".join(m["name"] for m in ctx["medications"])
        allergy_str = ", ".join(a["substance"] for a in ctx["allergies"]) or "NKDA"
        vital_str = "; ".join(f"{v['type']}: {v['value']}" for v in ctx["recent_observations"][:6])
        note_str = "\n".join(
            f"  [{n['created_at'][:16]} {n['author']}]: {n['note_text'][:250]}"
            for n in ctx["progress_notes"][:3]
        )
        device_str = ", ".join(
            o["name"] for o in ctx["active_orders"]
            if any(d in o["name"].lower() for d in TRACKED_DEVICES)
        ) or "none"

        prompt = (
            f"You are generating a cross-cover SBAR sign-out for an inpatient medicine service.\n\n"
            f"Patient: {pt['name']}, {pt.get('age', '?')}y {pt.get('gender', '')}\n"
            f"Ward: {pt.get('ward')} | Bed: {pt.get('bed')} | Code: {pt.get('code_status')}\n"
            f"LOS: {los_days:.1f} days | Attending: {pt.get('attending')}\n\n"
            f"Active Diagnoses: {cond_str}\n"
            f"Medications: {med_str}\n"
            f"Allergies: {allergy_str}\n"
            f"Active Devices: {device_str}\n"
            f"Recent Vitals: {vital_str}\n\n"
            f"Progress Notes:\n{note_str}\n\n"
            f"Generate a structured SBAR sign-out. Return exactly these 5 sections:\n"
            f"SITUATION: (primary reason for admission + any acute changes in last 12h)\n"
            f"BACKGROUND: (PMH, code status, allergies, key meds, relevant history)\n"
            f"ASSESSMENT: (current clinical status, active problems, trending direction)\n"
            f"RECOMMENDATION: (overnight plan, key tasks for cross-cover provider)\n"
            f"CONTINGENCY PLANS: (specific if-then instructions, e.g. 'If BP <80, give 500mL NS bolus and call attending')\n\n"
            f"Be specific and actionable. Include allergy and code status explicitly."
        )
        try:
            response = agent.chat(prompt)
            sbar = self._parse_sbar_sections(response)
            # If situation wasn't parsed, build it from context so it's never blank
            if not sbar.get("situation"):
                primary_dx = ctx["conditions"][0]["name"] if ctx["conditions"] else "Unknown"
                sbar["situation"] = (
                    f"{pt['name']}, {pt.get('age', '?')}y {pt.get('gender', '')} — "
                    f"{pt.get('ward')} Bed {pt.get('bed')}, LOS {los_days:.1f} days. "
                    f"Admitted for {primary_dx}."
                )
            sbar["_source"] = "medgemma"
            return sbar
        except Exception as e:
            logger.warning(f"Agent call failed for SBAR {ctx['patient']['id']}: {e}")
            result = self._structured_sbar(ctx)
            return result

    def _parse_sbar_sections(self, text: str) -> dict:
        """Extract SBAR sections from AI response text."""
        sections = {
            "situation": "",
            "background": "",
            "assessment": "",
            "recommendation": "",
            "contingency_plans": "",
        }
        current = None
        key_map = {
            "situation": "situation",
            "background": "background",
            "assessment": "assessment",
            "recommendation": "recommendation",
            "contingency": "contingency_plans",
        }
        for line in text.splitlines():
            line_lower = line.lower().strip()
            # Strip markdown formatting chars so "**SITUATION:**" matches "situation"
            cleaned = line_lower.lstrip("*#_>~ ").strip()
            matched = False
            for keyword, key in key_map.items():
                if cleaned.startswith(keyword):
                    current = key
                    remainder = line.split(":", 1)[-1].strip().lstrip("*_ ").strip()
                    sections[current] = remainder + "\n" if remainder else ""
                    matched = True
                    break
            if not matched and current:
                sections[current] += line + "\n"

        # Trim
        return {k: v.strip() for k, v in sections.items()}

    def _structured_sbar(self, ctx: dict) -> dict:
        """Build SBAR without AI using structured data."""
        pt = ctx["patient"]
        los_days = ctx["los_hours"] / 24
        allergy_str = ", ".join(a["substance"] for a in ctx["allergies"]) or "NKDA"

        primary_dx = ctx["conditions"][0]["name"] if ctx["conditions"] else "Unknown"
        recent_note = ctx["progress_notes"][0]["note_text"][:300] if ctx["progress_notes"] else "No recent notes."
        recent_event_note = (
            ctx["recent_events"][0]["note_text"][:200]
            if ctx["recent_events"]
            else "No acute events in last 12 hours documented."
        )

        vital_lines = "; ".join(
            f"{v['type']}: {v['value']}" for v in ctx["recent_observations"][:5]
        ) or "Not available"

        hrm_list = [
            m["name"] for m in ctx["medications"]
            if any(h in m["name"].lower() for h in HIGH_RISK_MEDS)
        ]

        devices = [
            o["name"] for o in ctx["active_orders"]
            if any(d in o["name"].lower() for d in TRACKED_DEVICES)
        ]

        situation = (
            f"{pt['name']}, {pt.get('age', '?')}y {pt.get('gender', '')}, "
            f"{pt.get('ward')} Bed {pt.get('bed')}, LOS {los_days:.1f} days.\n"
            f"Primary: {primary_dx}.\n"
            f"Last 12h events: {recent_event_note}"
        )

        background = (
            f"Code status: {pt.get('code_status', 'UNKNOWN — verify')}.\n"
            f"Allergies: {allergy_str}.\n"
            f"Active conditions: {', '.join(c['name'] for c in ctx['conditions'])}.\n"
            f"Key medications: {', '.join(m['name'] for m in ctx['medications'][:5])}."
            + (f"\nHigh-risk meds: {', '.join(hrm_list)}." if hrm_list else "")
            + (f"\nActive devices: {', '.join(devices)}." if devices else "")
        )

        assessment = (
            f"Current vitals: {vital_lines}.\n"
            f"Clinical summary: {recent_note}"
        )

        pending = [o["name"] for o in ctx["active_orders"] if o.get("status") == "pending"]
        recommendation = (
            f"Continue current management plan.\n"
            + (f"Pending items: {', '.join(pending)}.\n" if pending else "")
            + f"Attending: {pt.get('attending', 'Unknown')} — contact for deterioration."
        )

        contingency_plans = (
            "If hemodynamic deterioration (BP <80): 500mL NS bolus, notify attending.\n"
            "If O2 sat <90% on current support: increase FiO2, obtain ABG, notify team.\n"
            "If acute mental status change: assess glucose, call rapid response if unresponsive."
        )

        return {
            "situation": situation,
            "background": background,
            "assessment": assessment,
            "recommendation": recommendation,
            "contingency_plans": contingency_plans,
            "_source": "structured_fallback",
        }

    @staticmethod
    def _parse_dt(dt_str: str) -> datetime:
        if not dt_str:
            return datetime.min
        try:
            return datetime.fromisoformat(dt_str.replace("Z", ""))
        except ValueError:
            return datetime.min


# ── Singleton ──────────────────────────────────────────────────────────────────
_sbar_service: SBARHandoffService | None = None


def get_sbar_service(fhir_server=None) -> SBARHandoffService:
    """Get or create the SBARHandoffService singleton."""
    global _sbar_service
    if _sbar_service is None:
        if fhir_server is None:
            from src.ehr import get_fhir_server
            fhir_server = get_fhir_server()
        _sbar_service = SBARHandoffService(fhir_server)
    return _sbar_service
