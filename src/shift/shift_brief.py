"""
Pre-shift AI briefing service.

Generates a role-tailored summary of upcoming appointments and clinical duties
before a doctor, resident, or nurse starts their shift.

Flow:
1. Query all patients from the FHIR server.
2. For each patient, inspect their appointments subcollection to find upcoming
   encounters assigned to the requesting provider.
3. Fetch the full clinical context (conditions, medications, allergies, vitals,
   recent labs).
4. Build a role-specific prompt and call MedGemma (or produce a structured
   simulated brief when the agent is unavailable).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── Provider catalogue (mirrors MOCK_USERS in src/auth/auth.py) ───────────────
PROVIDERS = [
    {"name": "Dr. Sarah Smith",    "role": "doctor"},
    {"name": "Dr. Michael Jones",  "role": "doctor"},
    {"name": "Dr. Emily Lee",      "role": "resident"},
    {"name": "Maria Garcia, RN",   "role": "nurse"},
]

# ── Role-specific briefing focus ──────────────────────────────────────────────
ROLE_FOCUS = {
    "doctor": (
        "Focus on clinical priorities: active diagnoses, recent lab/imaging results, "
        "pending orders requiring physician sign-off, medication reconciliation, and "
        "any critical alerts or follow-up items from previous encounters."
    ),
    "resident": (
        "Highlight learning opportunities, differential diagnoses worth exploring, "
        "clinical reasoning for each case, and any teaching points. Include key "
        "conditions to review before the appointment."
    ),
    "nurse": (
        "Focus on practical care tasks: scheduled medications and timing, vital sign "
        "monitoring requirements, PRN medications that may be needed, fall/safety "
        "risk flags, patient comfort needs, and any special care instructions."
    ),
}


class ShiftBriefService:
    """Generates pre-shift briefings for clinical staff."""

    def __init__(self, fhir_server):
        self.fhir = fhir_server

    # ── Public API ────────────────────────────────────────────────────────────

    def get_provider_patients(self, provider_name: str) -> list[dict]:
        """
        Return all patients who have an appointment assigned to ``provider_name``.

        Each entry contains:
        - patient_id, patient_name, age, gender
        - appointment: the matching appointment record
        - clinical_context: conditions, medications, allergies, vitals
        """
        all_patients = self._list_patients()
        results = []

        for patient_stub in all_patients:
            pid = patient_stub["id"]
            appointments = self._get_appointments(pid)
            matched = self._find_appointment(appointments, provider_name)
            if matched is None:
                continue

            ctx = self._get_clinical_context(pid)
            results.append({
                "patient_id": pid,
                "patient_name": patient_stub.get("name", "Unknown"),
                "age": ctx.get("age"),
                "gender": ctx.get("gender"),
                "appointment": matched,
                "conditions": ctx.get("conditions", []),
                "medications": ctx.get("medications", []),
                "allergies": ctx.get("allergies", []),
                "observations": ctx.get("observations", []),
                "critical_alerts": ctx.get("critical_alerts", []),
            })

        return results

    def generate_brief(
        self,
        provider_name: str,
        role: str,
        agent=None,
    ) -> dict:
        """
        Build and return the full shift brief.

        Returns a dict with:
        - provider_name, role, shift_date
        - patients: list of matched patient records
        - ai_summary: AI-generated narrative or structured fallback
        """
        role_lower = role.lower()
        patients = self.get_provider_patients(provider_name)

        shift_date = datetime.now().strftime("%A, %B %d, %Y")

        if not patients:
            return {
                "provider_name": provider_name,
                "role": role_lower,
                "shift_date": shift_date,
                "patients": [],
                "ai_summary": (
                    f"No upcoming appointments found for {provider_name} today. "
                    "Please check the scheduling system for any same-day additions."
                ),
            }

        ai_summary = self._generate_ai_summary(provider_name, role_lower, patients, agent)

        return {
            "provider_name": provider_name,
            "role": role_lower,
            "shift_date": shift_date,
            "patients": patients,
            "ai_summary": ai_summary,
        }

    # ── AI summary generation ─────────────────────────────────────────────────

    def _generate_ai_summary(
        self,
        provider_name: str,
        role: str,
        patients: list[dict],
        agent,
    ) -> str:
        """Call MedGemma for a narrative, or fall back to a structured summary."""
        if agent is not None:
            return self._call_agent(provider_name, role, patients, agent)
        return self._structured_summary(provider_name, role, patients)

    def _call_agent(self, provider_name, role, patients, agent) -> str:
        """Build a clinical prompt and call the MedGemma agent."""
        focus = ROLE_FOCUS.get(role, ROLE_FOCUS["doctor"])
        patient_blocks = []
        for i, p in enumerate(patients, start=1):
            block = [
                f"Patient {i}: {p['patient_name']}, "
                f"{p.get('age', '?')}y {p.get('gender', '')}",
            ]
            appt = p["appointment"]
            block.append(
                f"  Appointment: {appt.get('type', 'Visit')} on {appt.get('date', 'today')} "
                f"(provider: {appt.get('provider', provider_name)})"
            )
            if p["conditions"]:
                cond_names = ", ".join(c["name"] for c in p["conditions"])
                block.append(f"  Active conditions: {cond_names}")
            if p["medications"]:
                med_names = ", ".join(m["name"] for m in p["medications"])
                block.append(f"  Current medications: {med_names}")
            if p["allergies"]:
                allergy_str = ", ".join(a.get("substance", "") for a in p["allergies"])
                block.append(f"  Allergies: {allergy_str}")
            if p["observations"]:
                obs_str = "; ".join(
                    f"{o.get('type','')}: {o.get('value','')}" for o in p["observations"]
                )
                block.append(f"  Recent vitals/labs: {obs_str}")
            if p["critical_alerts"]:
                block.append(f"  CRITICAL ALERTS: {', '.join(p['critical_alerts'])}")
            patient_blocks.append("\n".join(block))

        prompt = (
            f"You are a clinical assistant preparing a pre-shift briefing for "
            f"{provider_name} ({role}).\n\n"
            f"Today is {datetime.now().strftime('%A, %B %d, %Y')}. "
            f"The following patients are scheduled. {focus}\n\n"
            + "\n\n".join(patient_blocks)
            + "\n\nGenerate a concise, structured shift briefing that helps "
            f"{provider_name} prioritise their day and prepare for each patient. "
            "Format it with clear sections per patient, then a priorities summary at the end."
        )
        try:
            result = agent.process_query(prompt)
            return result.get("response", self._structured_summary(provider_name, role, patients))
        except Exception as e:
            logger.warning(f"Agent call failed for shift brief: {e}")
            return self._structured_summary(provider_name, role, patients)

    def _structured_summary(self, provider_name: str, role: str, patients: list[dict]) -> str:
        """Return a formatted text summary without calling an AI model."""
        today = datetime.now().strftime("%A, %B %d, %Y")
        lines = [
            f"Shift Briefing — {provider_name}",
            f"Date: {today}",
            f"Role: {role.capitalize()}",
            "=" * 50,
            "",
        ]

        for i, p in enumerate(patients, start=1):
            appt = p["appointment"]
            lines.append(f"Patient {i}: {p['patient_name']}")
            lines.append(
                f"  Visit: {appt.get('type', 'Appointment')} — {appt.get('date', 'today')}"
            )
            if p["conditions"]:
                lines.append(
                    "  Conditions: " + ", ".join(c["name"] for c in p["conditions"])
                )
            if p["medications"]:
                lines.append(
                    "  Medications: " + ", ".join(m["name"] for m in p["medications"])
                )
            if p["allergies"]:
                lines.append(
                    "  Allergies: " + ", ".join(
                        a.get("substance", "") for a in p["allergies"]
                    )
                )
            if p["observations"]:
                obs_summary = "; ".join(
                    f"{o.get('type','')}: {o.get('value','')}" for o in p["observations"]
                )
                lines.append(f"  Recent vitals/labs: {obs_summary}")
            if appt.get("instructions"):
                instructions = appt["instructions"]
                if isinstance(instructions, list):
                    lines.append("  Outstanding instructions:")
                    for ins in instructions:
                        lines.append(f"    - {ins}")
            if p["critical_alerts"]:
                lines.append("  ⚠ CRITICAL: " + ", ".join(p["critical_alerts"]))

            # Role-specific notes
            if role == "nurse":
                prn_meds = [
                    m["name"] for m in p["medications"]
                    if "prn" in m.get("dosage", "").lower()
                    or "as needed" in m.get("dosage", "").lower()
                ]
                if prn_meds:
                    lines.append("  PRN medications available: " + ", ".join(prn_meds))
            elif role == "resident":
                if p["conditions"]:
                    lines.append(
                        "  Review before visit: pathophysiology of "
                        + p["conditions"][0]["name"]
                    )

            lines.append("")

        # Priorities summary
        lines.append("Priorities for this shift:")
        critical_patients = [
            p["patient_name"] for p in patients if p.get("critical_alerts")
        ]
        if critical_patients:
            lines.append(f"  - CRITICAL attention needed: {', '.join(critical_patients)}")
        lines.append(f"  - Total patients: {len(patients)}")
        if role == "nurse":
            lines.append("  - Confirm all medication schedules before rounds start")
        elif role == "doctor":
            lines.append("  - Review pending orders and lab results before encounters")
        elif role == "resident":
            lines.append("  - Discuss complex cases with attending before encounters")

        return "\n".join(lines)

    # ── Data access helpers ───────────────────────────────────────────────────

    def _list_patients(self) -> list[dict]:
        """List all patient stubs from the FHIR server."""
        try:
            if hasattr(self.fhir, "list_patients"):
                return self.fhir.list_patients()
            # MockFHIRServer uses patients dict
            patients = getattr(self.fhir, "patients", {})
            return [
                {"id": pid, "name": data.get("name", {}).get("text", "Unknown")}
                for pid, data in patients.items()
            ]
        except Exception as e:
            logger.warning(f"ShiftBriefService._list_patients failed: {e}")
            return []

    def _get_appointments(self, patient_id: str) -> list[dict]:
        """Fetch appointment records for a patient."""
        try:
            if hasattr(self.fhir, "_get_subcollection"):
                return self.fhir._get_subcollection(patient_id, "appointments")
            appt = getattr(self.fhir, "appointments", {}).get(patient_id, [])
            return appt if isinstance(appt, list) else [appt]
        except Exception as e:
            logger.warning(f"ShiftBriefService._get_appointments({patient_id}) failed: {e}")
            return []

    def _find_appointment(
        self, appointments: list[dict], provider_name: str
    ) -> dict | None:
        """Return the first appointment whose provider field matches provider_name."""
        name_lower = provider_name.lower()
        for appt in appointments:
            appt_provider = appt.get("provider", "")
            if name_lower in appt_provider.lower() or appt_provider.lower() in name_lower:
                return appt
        return None

    def _get_clinical_context(self, patient_id: str) -> dict:
        """Return a flat clinical context dict for a patient."""
        try:
            summary = self.fhir.get_patient_summary(patient_id)
        except Exception as e:
            logger.warning(f"ShiftBriefService._get_clinical_context({patient_id}): {e}")
            return {}

        if not summary:
            return {}

        patient = summary.get("patient", {})
        return {
            "age": patient.get("age"),
            "gender": patient.get("gender"),
            "conditions": summary.get("conditions", []),
            "medications": summary.get("medications", []),
            "allergies": summary.get("allergies", []),
            "observations": summary.get("observations", []),
            "critical_alerts": summary.get("critical_alerts", []),
        }


# ── Singleton ──────────────────────────────────────────────────────────────────
_shift_brief_service: ShiftBriefService | None = None


def get_shift_brief_service(fhir_server=None) -> ShiftBriefService:
    """Get or create the ShiftBriefService singleton."""
    global _shift_brief_service
    if _shift_brief_service is None:
        if fhir_server is None:
            from src.ehr import get_fhir_server
            fhir_server = get_fhir_server()
        _shift_brief_service = ShiftBriefService(fhir_server)
    return _shift_brief_service
