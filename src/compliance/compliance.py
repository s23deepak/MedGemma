"""
SOAP Compliance Monitoring Service
Periodic checks on SOAP documents for symptom duration and update compliance.
"""

from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class FlagSeverity(str, Enum):
    """Severity levels for compliance flags."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# Symptom duration thresholds (days) - when to flag
SYMPTOM_DURATION_THRESHOLDS = {
    # Acute symptoms that should resolve quickly
    "fever": {"warning": 5, "critical": 10},
    "acute cough": {"warning": 14, "critical": 21},
    "headache": {"warning": 7, "critical": 14},
    "nausea": {"warning": 3, "critical": 7},
    "vomiting": {"warning": 2, "critical": 5},
    "diarrhea": {"warning": 3, "critical": 7},
    "chest pain": {"warning": 3, "critical": 7},
    "shortness of breath": {"warning": 3, "critical": 7},
    
    # Subacute symptoms
    "fatigue": {"warning": 30, "critical": 60},
    "weight loss": {"warning": 14, "critical": 30},
    "night sweats": {"warning": 14, "critical": 21},
    
    # Chronic conditions are excluded from duration flags
}

# SOAP update frequency requirements (days)
UPDATE_FREQUENCY_REQUIREMENTS = {
    "critical_condition": 1,  # Daily updates for critical patients
    "acute_condition": 7,     # Weekly for acute
    "chronic_condition": 30,  # Monthly for chronic
    "routine": 90,            # Quarterly for routine
}


@dataclass
class ComplianceFlag:
    """A compliance issue that needs attention."""
    patient_id: str
    patient_name: str
    soap_id: str
    flag_type: str  # "symptom_duration", "update_overdue", "missing_followup"
    severity: FlagSeverity
    title: str
    description: str
    symptom: str | None = None
    duration_days: int | None = None
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "patient_id": self.patient_id,
            "patient_name": self.patient_name,
            "soap_id": self.soap_id,
            "flag_type": self.flag_type,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "symptom": self.symptom,
            "duration_days": self.duration_days,
            "created_at": self.created_at.isoformat()
        }


@dataclass
class ComplianceReport:
    """Result of a compliance check."""
    check_time: datetime
    total_soap_documents: int
    compliant_count: int
    flagged_count: int
    flags: list[ComplianceFlag]
    
    @property
    def compliance_rate(self) -> float:
        if self.total_soap_documents == 0:
            return 100.0
        return (self.compliant_count / self.total_soap_documents) * 100
    
    def to_dict(self) -> dict:
        return {
            "check_time": self.check_time.isoformat(),
            "check_time_display": self.check_time.strftime("%b %d, %Y %H:%M"),
            "total_documents": self.total_soap_documents,
            "compliant_count": self.compliant_count,
            "flagged_count": self.flagged_count,
            "compliance_rate": round(self.compliance_rate, 1),
            "flags": [f.to_dict() for f in self.flags]
        }


class SOAPComplianceChecker:
    """Service for checking SOAP document compliance."""
    
    def __init__(self):
        self.last_check: datetime | None = None
        self.last_report: ComplianceReport | None = None
        # Mock SOAP document storage
        self._mock_soap_documents = self._get_mock_documents()
    
    def _get_mock_documents(self) -> list[dict]:
        """Generate mock SOAP documents for demonstration."""
        now = datetime.now()
        return [
            {
                "soap_id": "SOAP-001",
                "patient_id": "P001",
                "patient_name": "John Doe",
                "created_at": (now - timedelta(days=5)).isoformat(),
                "last_updated": (now - timedelta(days=2)).isoformat(),
                "condition_type": "acute_condition",
                "symptoms": [
                    {"name": "fever", "onset_date": (now - timedelta(days=5)).isoformat()},
                    {"name": "cough", "onset_date": (now - timedelta(days=5)).isoformat()}
                ],
                "status": "active"
            },
            {
                "soap_id": "SOAP-002",
                "patient_id": "P002",
                "patient_name": "Carlos Martinez",
                "created_at": (now - timedelta(days=20)).isoformat(),
                "last_updated": (now - timedelta(days=15)).isoformat(),
                "condition_type": "chronic_condition",
                "symptoms": [
                    {"name": "shortness of breath", "onset_date": (now - timedelta(days=20)).isoformat()},
                    {"name": "fatigue", "onset_date": (now - timedelta(days=45)).isoformat()}
                ],
                "status": "active"
            },
            {
                "soap_id": "SOAP-003",
                "patient_id": "P003",
                "patient_name": "Alice Johnson",
                "created_at": (now - timedelta(days=3)).isoformat(),
                "last_updated": (now - timedelta(days=1)).isoformat(),
                "condition_type": "acute_condition",
                "symptoms": [
                    {"name": "headache", "onset_date": (now - timedelta(days=3)).isoformat()}
                ],
                "status": "active"
            },
            {
                "soap_id": "SOAP-004",
                "patient_id": "P004",
                "patient_name": "Robert Chen",
                "created_at": (now - timedelta(days=60)).isoformat(),
                "last_updated": (now - timedelta(days=45)).isoformat(),
                "condition_type": "chronic_condition",
                "symptoms": [
                    {"name": "chest pain", "onset_date": (now - timedelta(days=14)).isoformat()}
                ],
                "status": "active"
            }
        ]
    
    def check_symptom_duration(self, soap: dict) -> list[ComplianceFlag]:
        """Check if any symptoms have exceeded their expected duration."""
        flags = []
        now = datetime.now()
        
        for symptom in soap.get("symptoms", []):
            symptom_name = symptom.get("name", "").lower()
            onset = symptom.get("onset_date")
            
            if not onset:
                continue
            
            try:
                onset_date = datetime.fromisoformat(onset)
                duration = (now - onset_date).days
            except ValueError:
                continue
            
            # Check against thresholds
            thresholds = SYMPTOM_DURATION_THRESHOLDS.get(symptom_name)
            if not thresholds:
                continue
            
            if duration >= thresholds["critical"]:
                flags.append(ComplianceFlag(
                    patient_id=soap["patient_id"],
                    patient_name=soap["patient_name"],
                    soap_id=soap["soap_id"],
                    flag_type="symptom_duration",
                    severity=FlagSeverity.CRITICAL,
                    title=f"Critical: {symptom_name.title()} exceeds normal duration",
                    description=f"Symptom '{symptom_name}' has persisted for {duration} days (expected < {thresholds['critical']} days)",
                    symptom=symptom_name,
                    duration_days=duration
                ))
            elif duration >= thresholds["warning"]:
                flags.append(ComplianceFlag(
                    patient_id=soap["patient_id"],
                    patient_name=soap["patient_name"],
                    soap_id=soap["soap_id"],
                    flag_type="symptom_duration",
                    severity=FlagSeverity.WARNING,
                    title=f"Warning: {symptom_name.title()} prolonged",
                    description=f"Symptom '{symptom_name}' has persisted for {duration} days (expected < {thresholds['warning']} days)",
                    symptom=symptom_name,
                    duration_days=duration
                ))
        
        return flags
    
    def check_update_frequency(self, soap: dict) -> ComplianceFlag | None:
        """Check if SOAP document needs to be updated."""
        now = datetime.now()
        
        last_updated = soap.get("last_updated")
        if not last_updated:
            return None
        
        try:
            update_date = datetime.fromisoformat(last_updated)
            days_since_update = (now - update_date).days
        except ValueError:
            return None
        
        condition_type = soap.get("condition_type", "routine")
        required_frequency = UPDATE_FREQUENCY_REQUIREMENTS.get(condition_type, 90)
        
        if days_since_update > required_frequency:
            severity = FlagSeverity.CRITICAL if days_since_update > required_frequency * 2 else FlagSeverity.WARNING
            return ComplianceFlag(
                patient_id=soap["patient_id"],
                patient_name=soap["patient_name"],
                soap_id=soap["soap_id"],
                flag_type="update_overdue",
                severity=severity,
                title=f"SOAP Update Overdue",
                description=f"Last updated {days_since_update} days ago (required every {required_frequency} days for {condition_type})",
                duration_days=days_since_update
            )
        
        return None
    
    def run_compliance_check(self) -> ComplianceReport:
        """Run full compliance check on all SOAP documents."""
        self.last_check = datetime.now()
        all_flags = []
        
        for soap in self._mock_soap_documents:
            if soap.get("status") != "active":
                continue
            
            # Check symptom durations
            symptom_flags = self.check_symptom_duration(soap)
            all_flags.extend(symptom_flags)
            
            # Check update frequency
            update_flag = self.check_update_frequency(soap)
            if update_flag:
                all_flags.append(update_flag)
        
        # Sort flags by severity
        severity_order = {FlagSeverity.CRITICAL: 0, FlagSeverity.WARNING: 1, FlagSeverity.INFO: 2}
        all_flags.sort(key=lambda f: severity_order.get(f.severity, 3))
        
        flagged_soap_ids = set(f.soap_id for f in all_flags)
        
        self.last_report = ComplianceReport(
            check_time=self.last_check,
            total_soap_documents=len(self._mock_soap_documents),
            compliant_count=len(self._mock_soap_documents) - len(flagged_soap_ids),
            flagged_count=len(flagged_soap_ids),
            flags=all_flags
        )
        
        return self.last_report
    
    def get_compliant_documents(self) -> list[dict]:
        """Get list of compliant SOAP documents."""
        if not self.last_report:
            self.run_compliance_check()
        
        flagged_ids = set(f.soap_id for f in self.last_report.flags)
        return [s for s in self._mock_soap_documents if s["soap_id"] not in flagged_ids]
    
    def get_last_report(self) -> ComplianceReport | None:
        """Get the last compliance check report."""
        return self.last_report


# Singleton instance
_compliance_checker = None

def get_compliance_checker() -> SOAPComplianceChecker:
    """Get or create the compliance checker singleton."""
    global _compliance_checker
    if _compliance_checker is None:
        _compliance_checker = SOAPComplianceChecker()
    return _compliance_checker
