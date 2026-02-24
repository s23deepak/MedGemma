"""
Inpatient Safety Watchlist Service.

Rule-based engine that audits admitted patients against common inpatient
safety protocols and generates MedGemma-backed explanations + suggested
note text for each alert.

Rules implemented:
  1. VTE prophylaxis: admitted >24h with no VTE prophylaxis order and no
     documented contraindication
  2. Foley / urinary catheter: dwell time >3 days without reassessment note
  3. High-risk medication without recent renal function lab (<48h)
  4. No physician progress note in >24h
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    WARNING = "warning"
    CRITICAL = "critical"


# High-risk meds requiring renal monitoring
RENAL_SENSITIVE_MEDS = [
    "vancomycin", "gentamicin", "tobramycin", "amikacin",
    "metformin", "insulin",
    "methotrexate", "cisplatin", "carboplatin",
    "nsaid", "ibuprofen", "naproxen", "ketorolac",
]

# VTE prophylaxis order keywords
VTE_PROPHYLAXIS_KEYWORDS = [
    "enoxaparin", "heparin", "fondaparinux", "rivaroxaban",
    "sequential compression", "scd", "ted hose", "compression stockings",
    "vte prophylaxis", "dvt prophylaxis",
]

# Renal function lab keywords
RENAL_LAB_KEYWORDS = ["creatinine", "bmp", "cmp", "egfr", "renal panel", "cr", "basic metabolic"]

# Foley / catheter keywords
FOLEY_KEYWORDS = ["foley", "urinary catheter", "foley catheter", "indwelling catheter"]


@dataclass
class SafetyAlert:
    """A single patient safety alert."""
    alert_id: str
    patient_id: str
    patient_name: str
    ward: str
    rule_id: str
    severity: AlertSeverity
    title: str
    detail: str
    suggested_action: str
    ai_explanation: str = ""
    triggered_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "patient_id": self.patient_id,
            "patient_name": self.patient_name,
            "ward": self.ward,
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "title": self.title,
            "detail": self.detail,
            "suggested_action": self.suggested_action,
            "ai_explanation": self.ai_explanation,
            "triggered_at": self.triggered_at,
        }


class InpatientSafetyService:
    """
    Rule-based inpatient safety watchlist with optional MedGemma explanations.
    """

    def __init__(self, fhir_server):
        self.fhir = fhir_server

    # ── Public API ────────────────────────────────────────────────────────────

    def run_safety_checks(self, patient_id: str, agent=None) -> list[SafetyAlert]:
        """
        Run all safety rules for a single patient.

        Returns a list of SafetyAlert objects (may be empty if no issues).
        If agent is provided, each alert gets an AI-generated explanation.
        """
        ctx = self._build_context(patient_id)
        if not ctx:
            return []

        alerts: list[SafetyAlert] = []
        alerts += self._check_vte_prophylaxis(ctx)
        alerts += self._check_foley_dwell(ctx)
        alerts += self._check_high_risk_meds(ctx)
        alerts += self._check_note_currency(ctx)

        if agent and alerts:
            for alert in alerts:
                try:
                    alert.ai_explanation = self._generate_explanation(alert, ctx, agent)
                except Exception as e:
                    logger.warning(f"AI explanation failed for {alert.alert_id}: {e}")

        return alerts

    def get_ward_safety_dashboard(self, ward: str | None = None, agent=None) -> dict:
        """
        Run safety checks across all admitted patients.

        Args:
            ward: If provided, filter to that ward only.
            agent: Optional MedGemma agent for explanations.

        Returns dict with: inpatients_checked, total_alerts, critical_count,
                           warning_count, alerts_by_patient, all_alerts.
        """
        inpatients = self._list_inpatients()
        if ward:
            inpatients = [p for p in inpatients if p.get("ward", "").lower() == ward.lower()]

        all_alerts: list[dict] = []
        alerts_by_patient: dict[str, list[dict]] = {}

        for pt in inpatients:
            pid = pt["id"]
            patient_alerts = self.run_safety_checks(pid, agent=agent)
            if patient_alerts:
                alert_dicts = [a.to_dict() for a in patient_alerts]
                alerts_by_patient[pid] = alert_dicts
                all_alerts.extend(alert_dicts)

        critical = [a for a in all_alerts if a["severity"] == "critical"]
        warnings = [a for a in all_alerts if a["severity"] == "warning"]

        # Sort: critical first, then by patient
        all_alerts.sort(key=lambda a: (0 if a["severity"] == "critical" else 1, a["patient_name"]))

        return {
            "generated_at": datetime.now().isoformat(),
            "ward_filter": ward,
            "inpatients_checked": len(inpatients),
            "total_alerts": len(all_alerts),
            "critical_count": len(critical),
            "warning_count": len(warnings),
            "alerts_by_patient": alerts_by_patient,
            "all_alerts": all_alerts,
        }

    # ── Safety rules ──────────────────────────────────────────────────────────

    def _check_vte_prophylaxis(self, ctx: dict) -> list[SafetyAlert]:
        """Rule 1: Admitted >24h with no VTE prophylaxis and no contraindication."""
        los_hours = ctx["los_hours"]
        if los_hours < 24:
            return []

        orders_text = " ".join(o["name"].lower() for o in ctx["active_orders"])
        has_vte = any(kw in orders_text for kw in VTE_PROPHYLAXIS_KEYWORDS)
        if has_vte:
            return []

        # Check notes for documented contraindication
        notes_text = " ".join(n["note_text"].lower() for n in ctx["progress_notes"])
        has_contraindication = any(
            kw in notes_text
            for kw in ["vte contraindication", "anticoagulation contraindicated",
                       "heparin contraindicated", "thrombocytopenia", "active bleeding",
                       "prophylaxis held", "on therapeutic anticoagulation"]
        )
        if has_contraindication:
            return []

        pt = ctx["patient"]
        return [SafetyAlert(
            alert_id=f"VTE-{pt['id']}-{datetime.now().strftime('%Y%m%d')}",
            patient_id=pt["id"],
            patient_name=pt["name"],
            ward=pt.get("ward", "Unknown"),
            rule_id="VTE_PROPHYLAXIS",
            severity=AlertSeverity.CRITICAL,
            title="No VTE Prophylaxis Ordered",
            detail=(
                f"Patient admitted {los_hours:.0f}h ago. No VTE prophylaxis order found "
                f"and no documented contraindication in progress notes."
            ),
            suggested_action=(
                "Order VTE prophylaxis (e.g. enoxaparin 40mg SQ daily) or document "
                "contraindication (e.g. active bleeding, thrombocytopenia) in progress note."
            ),
        )]

    def _check_foley_dwell(self, ctx: dict) -> list[SafetyAlert]:
        """Rule 2: Foley catheter dwell time >3 days without reassessment."""
        now = datetime.now()
        foley_orders = [
            o for o in ctx["active_orders"]
            if any(kw in o["name"].lower() for kw in FOLEY_KEYWORDS)
        ]
        alerts = []
        for order in foley_orders:
            inserted_str = order.get("inserted_at") or order.get("ordered_at", "")
            if not inserted_str:
                continue
            try:
                inserted_dt = datetime.fromisoformat(inserted_str)
            except ValueError:
                continue

            dwell_hours = (now - inserted_dt).total_seconds() / 3600
            if dwell_hours < 72:  # < 3 days
                continue

            # Check for reassessment note in last 24h
            cutoff = now - timedelta(hours=24)
            recent_notes_text = " ".join(
                n["note_text"].lower() for n in ctx["progress_notes"]
                if self._parse_dt(n.get("created_at", "")) >= cutoff
            )
            has_reassessment = any(
                kw in recent_notes_text
                for kw in ["foley", "catheter", "voiding", "urinary", "foley removal",
                           "catheter necessary", "foley remains"]
            )
            if has_reassessment:
                continue

            pt = ctx["patient"]
            alerts.append(SafetyAlert(
                alert_id=f"FOLEY-{pt['id']}-{datetime.now().strftime('%Y%m%d')}",
                patient_id=pt["id"],
                patient_name=pt["name"],
                ward=pt.get("ward", "Unknown"),
                rule_id="FOLEY_DWELL",
                severity=AlertSeverity.WARNING,
                title=f"Foley Catheter Dwell {dwell_hours/24:.1f} Days — No Recent Reassessment",
                detail=(
                    f"Foley catheter has been in place for {dwell_hours:.0f}h ({dwell_hours/24:.1f} days). "
                    f"No Foley reassessment documented in last 24h."
                ),
                suggested_action=(
                    "Assess if Foley catheter remains medically necessary. If patient is ambulatory "
                    "and voiding well, consider removal to reduce CAUTI risk. Document reassessment in progress note."
                ),
            ))
        return alerts

    def _check_high_risk_meds(self, ctx: dict) -> list[SafetyAlert]:
        """Rule 3: High-risk medication (insulin/renal-sensitive) without recent renal lab."""
        patient_hrm = [
            m for m in ctx["medications"]
            if any(h in m["name"].lower() for h in RENAL_SENSITIVE_MEDS)
        ]
        if not patient_hrm:
            return []

        now = datetime.now()
        cutoff_48h = now - timedelta(hours=48)

        # Check observations and orders for recent renal lab
        obs_text = " ".join(
            o["type"].lower() for o in ctx["recent_observations"]
            if self._parse_dt(o.get("date", "")) >= cutoff_48h
        )
        orders_text = " ".join(o["name"].lower() for o in ctx["active_orders"])
        has_renal_lab = any(
            kw in obs_text or kw in orders_text
            for kw in RENAL_LAB_KEYWORDS
        )
        if has_renal_lab:
            return []

        pt = ctx["patient"]
        hrm_names = ", ".join(m["name"] for m in patient_hrm[:3])
        return [SafetyAlert(
            alert_id=f"HRM-{pt['id']}-{datetime.now().strftime('%Y%m%d')}",
            patient_id=pt["id"],
            patient_name=pt["name"],
            ward=pt.get("ward", "Unknown"),
            rule_id="HIGH_RISK_MED_RENAL",
            severity=AlertSeverity.WARNING,
            title="High-Risk Medication Without Recent Renal Function Lab",
            detail=(
                f"Patient is on {hrm_names}. No renal function lab (creatinine/BMP) "
                f"found in the last 48 hours."
            ),
            suggested_action=(
                f"Order BMP or creatinine to verify adequate renal clearance for {hrm_names}. "
                f"Adjust dosing if eGFR <30."
            ),
        )]

    def _check_note_currency(self, ctx: dict) -> list[SafetyAlert]:
        """Rule 4: No physician progress note in >24h."""
        if not ctx["progress_notes"]:
            last_note_hours = ctx["los_hours"]
        else:
            last_note_dt = self._parse_dt(ctx["progress_notes"][0].get("created_at", ""))
            if last_note_dt == datetime.min:
                return []
            last_note_hours = (datetime.now() - last_note_dt).total_seconds() / 3600

        if last_note_hours <= 24:
            return []

        pt = ctx["patient"]
        return [SafetyAlert(
            alert_id=f"NOTE-{pt['id']}-{datetime.now().strftime('%Y%m%d')}",
            patient_id=pt["id"],
            patient_name=pt["name"],
            ward=pt.get("ward", "Unknown"),
            rule_id="NOTE_OVERDUE",
            severity=AlertSeverity.WARNING,
            title=f"No Progress Note in {last_note_hours:.0f}h",
            detail=(
                f"Last physician progress note was {last_note_hours:.0f} hours ago. "
                f"Inpatient patients require at least daily physician documentation."
            ),
            suggested_action=(
                "Write a progress note documenting current clinical status, assessment, "
                "and plan for each active problem."
            ),
        )]

    # ── AI explanation ────────────────────────────────────────────────────────

    def _generate_explanation(self, alert: SafetyAlert, ctx: dict, agent) -> str:
        """Use MedGemma to generate a brief clinical explanation for the alert."""
        cond_str = ", ".join(c["name"] for c in ctx["conditions"][:3])
        prompt = (
            f"Patient: {alert.patient_name}, {ctx['patient'].get('age', '?')}y, "
            f"Ward: {alert.ward}. Conditions: {cond_str}.\n\n"
            f"Safety Alert: {alert.title}\n"
            f"Detail: {alert.detail}\n\n"
            f"In 2-3 sentences, explain the clinical significance of this safety issue "
            f"and the specific risk to this patient. Then provide one concrete suggested "
            f"documentation phrase a physician could use in their note to address this alert."
        )
        try:
            result = agent.process_query(prompt)
            return result.get("response", "")
        except Exception as e:
            logger.warning(f"AI explanation error: {e}")
            return ""

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_context(self, patient_id: str) -> dict:
        summary = self.fhir.get_patient_summary(patient_id)
        if not summary or summary["patient"].get("encounter_type") != "inpatient":
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
        }

    def _list_inpatients(self) -> list[dict]:
        if hasattr(self.fhir, "list_inpatients"):
            return self.fhir.list_inpatients()
        return [p for p in (self.fhir.list_patients() or []) if p.get("encounter_type") == "inpatient"]

    @staticmethod
    def _parse_dt(dt_str: str) -> datetime:
        if not dt_str:
            return datetime.min
        try:
            return datetime.fromisoformat(dt_str.replace("Z", ""))
        except ValueError:
            return datetime.min


# ── Singleton ──────────────────────────────────────────────────────────────────
_safety_service: InpatientSafetyService | None = None


def get_safety_service(fhir_server=None) -> InpatientSafetyService:
    """Get or create the InpatientSafetyService singleton."""
    global _safety_service
    if _safety_service is None:
        if fhir_server is None:
            from src.ehr import get_fhir_server
            fhir_server = get_fhir_server()
        _safety_service = InpatientSafetyService(fhir_server)
    return _safety_service
