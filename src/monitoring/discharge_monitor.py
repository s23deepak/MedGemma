"""
Post-discharge monitoring service.

After encounter approval a physician can set a discharge plan with:
  - Vitals thresholds (blood pressure, heart rate, oxygen saturation, etc.)
  - Monitoring duration
  - Alert contacts (care team notification via existing notify_care_team tool)

Patients submit vitals via the patient portal.  The service evaluates each
submission against the thresholds and returns alert-level feedback immediately.
Alerts are stored in fhir_server.discharge_alerts and can be fetched by the
care team.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.ehr.fhir_mock import MockFHIRServer


class AlertLevel(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"


# ── Threshold definitions ─────────────────────────────────────────────────────

DEFAULT_THRESHOLDS: dict[str, dict] = {
    "systolic_bp": {
        "warning_high": 150, "critical_high": 180,
        "warning_low": 90,   "critical_low": 70,
        "unit": "mmHg",
    },
    "diastolic_bp": {
        "warning_high": 100, "critical_high": 120,
        "warning_low": 60,   "critical_low": 40,
        "unit": "mmHg",
    },
    "heart_rate": {
        "warning_high": 110, "critical_high": 130,
        "warning_low": 50,   "critical_low": 40,
        "unit": "bpm",
    },
    "oxygen_saturation": {
        "warning_low": 93, "critical_low": 90,
        "unit": "%",
    },
    "temperature": {
        "warning_high": 38.3, "critical_high": 39.5,
        "warning_low": 35.5,  "critical_low": 35.0,
        "unit": "°C",
    },
    "blood_glucose": {
        "warning_high": 200, "critical_high": 300,
        "warning_low": 70,   "critical_low": 55,
        "unit": "mg/dL",
    },
    "weight_change_kg": {
        "warning_high": 2.0, "critical_high": 3.5,    # gain vs last reading
        "unit": "kg",
    },
}


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class DischargePlan:
    """Monitoring plan set by physician at discharge."""
    plan_id: str
    patient_id: str
    encounter_id: str
    created_at: datetime
    monitor_until: datetime   # date to stop monitoring
    thresholds: dict          # override of DEFAULT_THRESHOLDS
    instructions: str         # plain-text discharge instructions
    notify_on_warning: bool = True
    notify_on_critical: bool = True
    active: bool = True

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "patient_id": self.patient_id,
            "encounter_id": self.encounter_id,
            "created_at": self.created_at.isoformat(),
            "monitor_until": self.monitor_until.isoformat(),
            "thresholds": self.thresholds,
            "instructions": self.instructions,
            "notify_on_warning": self.notify_on_warning,
            "notify_on_critical": self.notify_on_critical,
            "active": self.active,
        }


@dataclass
class VitalsSubmission:
    """A single vitals reading submitted by the patient."""
    submission_id: str
    patient_id: str
    plan_id: str
    submitted_at: datetime
    vitals: dict[str, float]   # e.g. {"systolic_bp": 142, "heart_rate": 88}
    notes: str = ""
    alert_level: AlertLevel = AlertLevel.NORMAL
    alerts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "submission_id": self.submission_id,
            "patient_id": self.patient_id,
            "plan_id": self.plan_id,
            "submitted_at": self.submitted_at.isoformat(),
            "vitals": self.vitals,
            "notes": self.notes,
            "alert_level": self.alert_level.value,
            "alerts": self.alerts,
        }


# ── Service ───────────────────────────────────────────────────────────────────

class DischargeMonitor:
    """Evaluates post-discharge vitals against physician-defined thresholds."""

    def __init__(self, fhir_server: "MockFHIRServer"):
        self.fhir = fhir_server
        if not hasattr(self.fhir, "discharge_plans"):
            self.fhir.discharge_plans: dict[str, list[dict]] = {}
        if not hasattr(self.fhir, "discharge_alerts"):
            self.fhir.discharge_alerts: dict[str, list[dict]] = {}
        if not hasattr(self.fhir, "vitals_submissions"):
            self.fhir.vitals_submissions: dict[str, list[dict]] = {}

    # ── Discharge plan management ─────────────────────────────────────────────

    def create_plan(
        self,
        patient_id: str,
        encounter_id: str,
        instructions: str,
        monitor_days: int = 14,
        thresholds: dict | None = None,
        notify_on_warning: bool = True,
        notify_on_critical: bool = True,
    ) -> DischargePlan:
        """Create a new discharge monitoring plan for a patient."""
        plan = DischargePlan(
            plan_id=f"DP-{uuid.uuid4().hex[:8].upper()}",
            patient_id=patient_id,
            encounter_id=encounter_id,
            created_at=datetime.now(),
            monitor_until=datetime.now() + timedelta(days=monitor_days),
            thresholds={**DEFAULT_THRESHOLDS, **(thresholds or {})},
            instructions=instructions,
            notify_on_warning=notify_on_warning,
            notify_on_critical=notify_on_critical,
        )
        if patient_id not in self.fhir.discharge_plans:
            self.fhir.discharge_plans[patient_id] = []
        self.fhir.discharge_plans[patient_id].append(plan.to_dict())
        return plan

    def get_active_plan(self, patient_id: str) -> dict | None:
        """Return the most recent active plan for a patient."""
        plans = self.fhir.discharge_plans.get(patient_id, [])
        now = datetime.now()
        for plan in reversed(plans):
            if plan.get("active") and datetime.fromisoformat(plan["monitor_until"]) > now:
                return plan
        return None

    def get_all_plans(self, patient_id: str) -> list[dict]:
        return list(reversed(self.fhir.discharge_plans.get(patient_id, [])))

    # ── Vitals submission and evaluation ─────────────────────────────────────

    def submit_vitals(
        self,
        patient_id: str,
        vitals: dict[str, float],
        notes: str = "",
    ) -> VitalsSubmission:
        """
        Patient submits vitals readings.  Returns alert level and messages.

        Args:
            patient_id: Patient placing the submission
            vitals: Dict of metric name → numeric value
            notes: Optional patient free-text notes

        Returns:
            VitalsSubmission with alert_level and alerts list populated
        """
        plan = self.get_active_plan(patient_id)
        plan_id = plan["plan_id"] if plan else "NO_PLAN"
        thresholds = plan["thresholds"] if plan else DEFAULT_THRESHOLDS

        alert_level, alerts = self._evaluate(vitals, thresholds)

        submission = VitalsSubmission(
            submission_id=f"VS-{uuid.uuid4().hex[:8].upper()}",
            patient_id=patient_id,
            plan_id=plan_id,
            submitted_at=datetime.now(),
            vitals=vitals,
            notes=notes,
            alert_level=alert_level,
            alerts=alerts,
        )

        # Persist
        if patient_id not in self.fhir.vitals_submissions:
            self.fhir.vitals_submissions[patient_id] = []
        self.fhir.vitals_submissions[patient_id].append(submission.to_dict())

        # Store alerts separately for care-team feeds
        if alerts and patient_id not in self.fhir.discharge_alerts:
            self.fhir.discharge_alerts[patient_id] = []
        if alerts:
            self.fhir.discharge_alerts[patient_id].append({
                "submission_id": submission.submission_id,
                "alert_level": alert_level.value,
                "alerts": alerts,
                "vitals": vitals,
                "timestamp": submission.submitted_at.isoformat(),
                "resolved": False,
            })

        return submission

    def get_vitals_history(self, patient_id: str) -> list[dict]:
        """Return all vitals submissions for a patient (newest first)."""
        return list(reversed(self.fhir.vitals_submissions.get(patient_id, [])))

    def get_pending_alerts(self, patient_id: str) -> list[dict]:
        """Return unresolved alerts for care team review."""
        return [
            a for a in self.fhir.discharge_alerts.get(patient_id, [])
            if not a.get("resolved")
        ]

    def resolve_alert(self, patient_id: str, submission_id: str) -> bool:
        """Mark an alert as resolved by care team."""
        for alert in self.fhir.discharge_alerts.get(patient_id, []):
            if alert.get("submission_id") == submission_id:
                alert["resolved"] = True
                alert["resolved_at"] = datetime.now().isoformat()
                return True
        return False

    # ── Evaluation engine ─────────────────────────────────────────────────────

    @staticmethod
    def _evaluate(
        vitals: dict[str, float],
        thresholds: dict,
    ) -> tuple[AlertLevel, list[str]]:
        """
        Evaluate vitals against thresholds.

        Returns:
            (highest AlertLevel across all metrics, list of alert message strings)
        """
        overall = AlertLevel.NORMAL
        messages: list[str] = []

        for metric, value in vitals.items():
            rules = thresholds.get(metric)
            if rules is None:
                continue
            unit = rules.get("unit", "")

            # Check critical first (higher priority)
            if "critical_high" in rules and value >= rules["critical_high"]:
                messages.append(
                    f"CRITICAL: {metric.replace('_', ' ').title()} {value} {unit} "
                    f"(threshold: ≥{rules['critical_high']})"
                )
                overall = AlertLevel.CRITICAL
            elif "critical_low" in rules and value <= rules["critical_low"]:
                messages.append(
                    f"CRITICAL: {metric.replace('_', ' ').title()} {value} {unit} "
                    f"(threshold: ≤{rules['critical_low']})"
                )
                overall = AlertLevel.CRITICAL
            elif "warning_high" in rules and value >= rules["warning_high"]:
                messages.append(
                    f"WARNING: {metric.replace('_', ' ').title()} {value} {unit} "
                    f"(threshold: ≥{rules['warning_high']})"
                )
                if overall == AlertLevel.NORMAL:
                    overall = AlertLevel.WARNING
            elif "warning_low" in rules and value <= rules["warning_low"]:
                messages.append(
                    f"WARNING: {metric.replace('_', ' ').title()} {value} {unit} "
                    f"(threshold: ≤{rules['warning_low']})"
                )
                if overall == AlertLevel.NORMAL:
                    overall = AlertLevel.WARNING

        return overall, messages


# ── Singleton ─────────────────────────────────────────────────────────────────
_discharge_monitor: DischargeMonitor | None = None


def get_discharge_monitor(fhir_server=None) -> DischargeMonitor:
    """Get or create the DischargeMonitor singleton."""
    global _discharge_monitor
    if _discharge_monitor is None:
        if fhir_server is None:
            from src.ehr import get_fhir_server
            fhir_server = get_fhir_server()
        _discharge_monitor = DischargeMonitor(fhir_server)
    return _discharge_monitor
