"""
Inpatient Rounding Copilot Service.

For each admitted patient, assembles a 24-hour clinical summary and uses
MedGemma to generate a structured progress note with:
  - Assessment per active problem
  - Length-of-stay context and trend
  - Pending items / to-do checklist
  - Discharge-readiness flag

Fall-back structured output is returned when the AI agent is unavailable.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class InpatientRoundingService:
    """Generates daily inpatient progress notes and to-do lists."""

    def __init__(self, fhir_server):
        self.fhir = fhir_server

    # ── Public API ────────────────────────────────────────────────────────────

    def get_admitted_patients(self) -> list[dict]:
        """Return all currently admitted (inpatient) patients."""
        if hasattr(self.fhir, "list_inpatients"):
            return self.fhir.list_inpatients()
        # Firestore fallback: filter list_patients by encounter_type
        return [
            p for p in (self.fhir.list_patients() or [])
            if p.get("encounter_type") == "inpatient"
        ]

    def build_24h_summary(self, patient_id: str) -> dict:
        """
        Assemble a compact 24-hour clinical snapshot for a patient.

        Returns a dict with keys: patient, conditions, medications, allergies,
        recent_vitals, active_orders, latest_notes, los_hours, last_note_hours_ago.
        """
        summary = self.fhir.get_patient_summary(patient_id)
        if not summary:
            return {}

        now = datetime.now()
        cutoff = now - timedelta(hours=24)

        # Filter observations to last 24 h
        recent_vitals = [
            o for o in summary.get("recent_observations", [])
            if self._parse_dt(o.get("date", "")) >= cutoff
        ]

        active_orders = []
        if hasattr(self.fhir, "get_active_orders"):
            active_orders = self.fhir.get_active_orders(patient_id)

        progress_notes = []
        if hasattr(self.fhir, "get_progress_notes"):
            progress_notes = self.fhir.get_progress_notes(patient_id)

        # Length-of-stay calculation
        admission_str = summary["patient"].get("admission_date")
        los_hours = 0.0
        if admission_str:
            try:
                admission_dt = datetime.fromisoformat(admission_str)
                los_hours = (now - admission_dt).total_seconds() / 3600
            except ValueError:
                pass

        # Hours since last physician note
        last_note_hours_ago: float | None = None
        if progress_notes:
            latest_note_dt = self._parse_dt(progress_notes[0].get("created_at", ""))
            if latest_note_dt > datetime.min:
                last_note_hours_ago = (now - latest_note_dt).total_seconds() / 3600

        return {
            "patient": summary["patient"],
            "conditions": summary.get("conditions", []),
            "medications": summary.get("medications", []),
            "allergies": summary.get("allergies", []),
            "recent_vitals": recent_vitals if recent_vitals else summary.get("recent_observations", []),
            "active_orders": active_orders,
            "latest_notes": progress_notes[:3],  # 3 most recent notes
            "los_hours": round(los_hours, 1),
            "last_note_hours_ago": round(last_note_hours_ago, 1) if last_note_hours_ago is not None else None,
        }

    def generate_progress_note(self, patient_id: str, agent=None) -> dict:
        """
        Generate a 24-hour inpatient progress note.

        Returns dict with: patient_id, note_text, todo_items, generated_at, source.
        """
        snap = self.build_24h_summary(patient_id)
        if not snap:
            return {"error": f"Patient {patient_id} not found or not an inpatient"}

        if agent is not None:
            return self._call_agent(snap, agent)
        return self._structured_note(snap)

    # ── AI note generation ───────────────────────────────────────────────────

    def _call_agent(self, snap: dict, agent) -> dict:
        pt = snap["patient"]
        los_days = snap["los_hours"] / 24

        cond_str = ", ".join(c["name"] for c in snap["conditions"])
        med_str = "\n".join(f"  - {m['name']} {m['dosage']}" for m in snap["medications"])
        vital_str = "\n".join(
            f"  - {v['type']}: {v['value']} ({v['date'][:16]})"
            for v in snap["recent_vitals"]
        )
        order_str = "\n".join(f"  - [{o['type'].upper()}] {o['name']}" for o in snap["active_orders"])
        note_str = "\n".join(
            f"  [{n['author']}, {n['created_at'][:16]}]: {n['note_text'][:200]}"
            for n in snap["latest_notes"]
        )

        prompt = (
            f"You are an inpatient clinical assistant generating a physician progress note.\n\n"
            f"Patient: {pt['name']}, {pt.get('age', '?')}y {pt.get('gender', '')}, "
            f"Ward: {pt.get('ward', 'Unknown')}, Bed: {pt.get('bed', '')}, "
            f"Code: {pt.get('code_status', 'Unknown')}, Attending: {pt.get('attending', 'Unknown')}\n"
            f"Admission: {pt.get('admission_date', 'Unknown')} (LOS: {los_days:.1f} days)\n\n"
            f"Active Conditions: {cond_str}\n\n"
            f"Current Medications:\n{med_str}\n\n"
            f"Allergies: {', '.join(a['substance'] for a in snap['allergies'])}\n\n"
            f"Recent Vitals/Labs (last 24h):\n{vital_str}\n\n"
            f"Active Orders:\n{order_str}\n\n"
            f"Recent Progress Notes:\n{note_str}\n\n"
            f"Generate a structured inpatient SOAP progress note with:\n"
            f"1. Subjective: patient-reported symptoms and overnight events\n"
            f"2. Objective: current vitals, key lab trends, exam findings\n"
            f"3. Assessment: problem-by-problem analysis with clinical reasoning\n"
            f"4. Plan: specific actions for each problem today\n"
            f"5. TO-DO LIST: bullet points of outstanding tasks (pending labs, consultations, "
            f"orders to place, documentation required)\n"
            f"6. Discharge readiness: briefly note barriers to discharge\n\n"
            f"Be concise and clinically precise. Flag any critical concerns."
        )
        try:
            note_text = agent.chat(prompt)
            todo_items = self._extract_todos_from_note(note_text)
            return {
                "patient_id": snap["patient"]["id"],
                "patient_name": snap["patient"]["name"],
                "note_text": note_text,
                "todo_items": todo_items,
                "los_hours": snap["los_hours"],
                "last_note_hours_ago": snap["last_note_hours_ago"],
                "generated_at": datetime.now().isoformat(),
                "source": "medgemma",
            }
        except Exception as e:
            logger.warning(f"Agent call failed for rounding note {snap['patient']['id']}: {e}")
            return self._structured_note(snap)

    def _structured_note(self, snap: dict) -> dict:
        """Return a structured fallback note without AI."""
        pt = snap["patient"]
        los_days = snap["los_hours"] / 24
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        lines = [
            f"INPATIENT PROGRESS NOTE — {now_str}",
            f"Patient: {pt['name']} | Ward: {pt.get('ward', 'Unknown')} Bed {pt.get('bed', '')}",
            f"LOS: {los_days:.1f} days | Code: {pt.get('code_status', 'Unknown')} | Attending: {pt.get('attending', 'Unknown')}",
            "",
            "SUBJECTIVE:",
            "  [Clinical interaction required — see recent progress notes below]",
        ]
        if snap["latest_notes"]:
            n = snap["latest_notes"][0]
            lines.append(f"  Last note ({n['author']}, {n['created_at'][:10]}): {n['note_text'][:300]}")

        lines += ["", "OBJECTIVE:"]
        if snap["recent_vitals"]:
            for v in snap["recent_vitals"]:
                lines.append(f"  {v['type']}: {v['value']}")
        else:
            lines.append("  No vitals recorded in last 24h")

        lines += ["", "ASSESSMENT:"]
        for c in snap["conditions"]:
            lines.append(f"  • {c['name']} (onset {c.get('onset', 'unknown')[:10]}) — active")

        lines += ["", "PLAN:"]
        for o in snap["active_orders"]:
            lines.append(f"  [{o['type'].upper()}] {o['name']}")

        # Build to-do list
        todo_items = self._derive_todos(snap)
        if todo_items:
            lines += ["", "TO-DO:"]
            for t in todo_items:
                lines.append(f"  ☐ {t}")

        lines += ["", "DISCHARGE BARRIERS:", "  Physician assessment required."]

        return {
            "patient_id": pt["id"],
            "patient_name": pt["name"],
            "note_text": "\n".join(lines),
            "todo_items": todo_items,
            "los_hours": snap["los_hours"],
            "last_note_hours_ago": snap["last_note_hours_ago"],
            "generated_at": datetime.now().isoformat(),
            "source": "structured_fallback",
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _derive_todos(self, snap: dict) -> list[str]:
        """Rule-based to-do items from clinical data."""
        todos: list[str] = []

        # Overdue note
        if snap["last_note_hours_ago"] is not None and snap["last_note_hours_ago"] > 24:
            todos.append(f"Progress note overdue ({snap['last_note_hours_ago']:.0f}h since last note)")

        # Pending lab orders
        pending_labs = [o for o in snap["active_orders"] if o.get("type") == "lab"]
        if pending_labs:
            todos.append(f"Review lab results: {', '.join(o['name'] for o in pending_labs[:3])}")

        # Pending consults
        pending_consults = [o for o in snap["active_orders"] if o.get("status") == "pending"]
        if pending_consults:
            todos.append(f"Follow up pending orders: {', '.join(o['name'] for o in pending_consults[:2])}")

        # High-risk medications need renal monitoring
        high_risk_meds = ["insulin", "opioid", "morphine", "hydromorphone", "vancomycin", "aminoglycoside"]
        for med in snap["medications"]:
            if any(h in med["name"].lower() for h in high_risk_meds):
                todos.append(f"Verify renal function for {med['name']}")
                break

        return todos

    def _extract_todos_from_note(self, note_text: str) -> list[str]:
        """Extract bullet points from AI-generated TO-DO section."""
        todos: list[str] = []
        in_todo = False
        for line in note_text.splitlines():
            line_l = line.strip().lower()
            if "to-do" in line_l or "todo" in line_l or "outstanding" in line_l:
                in_todo = True
                continue
            if in_todo:
                if line.strip().startswith(("•", "-", "☐", "*", "1", "2", "3", "4", "5")):
                    todos.append(line.strip().lstrip("•-☐* ").strip())
                elif line.strip() == "" and todos:
                    break
        return todos[:10]

    @staticmethod
    def _parse_dt(dt_str: str) -> datetime:
        """Parse ISO datetime string, returning datetime.min on failure."""
        if not dt_str:
            return datetime.min
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00").replace("+00:00", ""))
        except ValueError:
            return datetime.min


# ── Singleton ──────────────────────────────────────────────────────────────────
_rounding_service: InpatientRoundingService | None = None


def get_rounding_service(fhir_server=None) -> InpatientRoundingService:
    """Get or create the InpatientRoundingService singleton."""
    global _rounding_service
    if _rounding_service is None:
        if fhir_server is None:
            from src.ehr import get_fhir_server
            fhir_server = get_fhir_server()
        _rounding_service = InpatientRoundingService(fhir_server)
    return _rounding_service
