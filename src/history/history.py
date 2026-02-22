"""
Patient History Service
Retrieve and display patient historical data via FunctionGemma.
"""

from datetime import datetime, timedelta
from typing import Any
from dataclasses import dataclass, field


@dataclass
class HistoryEntry:
    """A single entry in patient history."""
    date: datetime
    category: str  # condition, medication, observation, imaging, encounter
    title: str
    details: str
    source: str = "EHR"
    
    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "date_display": self.date.strftime("%b %d, %Y"),
            "category": self.category,
            "title": self.title,
            "details": self.details,
            "source": self.source
        }


class PatientHistoryService:
    """Service for retrieving patient historical data."""
    
    def __init__(self, fhir_server=None):
        """Initialize with optional FHIR server connection."""
        self.fhir = fhir_server
        if not self.fhir:
            from src.ehr import get_fhir_server
            self.fhir = get_fhir_server()
    
    def get_patient_timeline(self, patient_id: str, days_back: int = 365) -> list[dict]:
        """
        Get chronological timeline of all patient events.
        
        Args:
            patient_id: Patient identifier
            days_back: Number of days to look back
            
        Returns:
            List of history entries sorted by date (newest first)
        """
        entries = []
        cutoff = datetime.now() - timedelta(days=days_back)
        
        # Get patient summary
        summary = self.fhir.get_patient_summary(patient_id)
        if not summary:
            return []
        
        # Add conditions
        for condition in summary.get("conditions", []):
            onset = condition.get("onset_date") or condition.get("onset")
            if onset and onset != "Unknown":
                try:
                    date = datetime.fromisoformat(onset)
                    entries.append(HistoryEntry(
                        date=date,
                        category="condition",
                        title=condition.get("name", "Unknown Condition"),
                        details=f"Status: {condition.get('status', 'active')}"
                    ))
                except ValueError:
                    pass
        
        # Add medications
        for med in summary.get("medications", []):
            start = med.get("start_date") or med.get("date") or datetime.now().isoformat()
            if start and start != "Unknown":
                try:
                    date = datetime.fromisoformat(start)
                    entries.append(HistoryEntry(
                        date=date,
                        category="medication",
                        title=med.get("name", "Unknown Medication"),
                        details=f"Dosage: {med.get('dosage', 'N/A')}"
                    ))
                except ValueError:
                    pass
        
        # Add observations
        for obs in summary.get("observations", []) or summary.get("recent_observations", []):
            obs_date = obs.get("date")
            if obs_date and obs_date != "Unknown":
                try:
                    date = datetime.fromisoformat(obs_date.replace("Z", "+00:00")).replace(tzinfo=None)
                    entries.append(HistoryEntry(
                        date=date,
                        category="observation",
                        title=obs.get("type", "Observation"),
                        details=f"Value: {obs.get('value', 'N/A')} {obs.get('unit', '')}".strip()
                    ))
                except ValueError:
                    pass
                    
        # Add imaging studies
        for img in summary.get("images", []):
            img_date = img.get("timestamp") or img.get("date")
            if img_date and img_date != "Unknown":
                try:
                    date = datetime.fromisoformat(img_date.replace("Z", "+00:00")).replace(tzinfo=None)
                    entries.append(HistoryEntry(
                        date=date,
                        category="imaging",
                        title=f"{str(img.get('modality', 'Imaging')).upper()} Study",
                        details=img.get("analysis") or img.get("description", "Imaging study performed")
                    ))
                except ValueError:
                    pass
        
        # Sort by date (newest first) and filter
        entries = [e for e in entries if e.date >= cutoff]
        entries.sort(key=lambda x: x.date, reverse=True)
        
        return [e.to_dict() for e in entries]
    
    def search_observations(
        self,
        patient_id: str,
        observation_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None
    ) -> list[dict]:
        """
        Search patient observations with filters.
        
        Args:
            patient_id: Patient identifier
            observation_type: Filter by type (vitals, labs, etc.)
            date_from: Start date (YYYY-MM-DD)
            date_to: End date (YYYY-MM-DD)
        """
        summary = self.fhir.get_patient_summary(patient_id)
        if not summary:
            return []
        
        observations = summary.get("observations", [])
        
        # Filter by type
        if observation_type:
            observations = [o for o in observations if observation_type.lower() in o.get("type", "").lower()]
        
        # Filter by date range
        if date_from:
            from_date = datetime.fromisoformat(date_from)
            observations = [o for o in observations if datetime.fromisoformat(o.get("date", "1900-01-01")) >= from_date]
        
        if date_to:
            to_date = datetime.fromisoformat(date_to)
            observations = [o for o in observations if datetime.fromisoformat(o.get("date", "2100-01-01")) <= to_date]
        
        return observations
    
    def get_medication_history(self, patient_id: str) -> list[dict]:
        """Get all medications (current and past) for a patient."""
        summary = self.fhir.get_patient_summary(patient_id)
        if not summary:
            return []
        
        medications = summary.get("medications", [])
        return sorted(medications, key=lambda x: x.get("start_date", ""), reverse=True)
    
    def get_imaging_studies(self, patient_id: str, modality: str | None = None) -> list[dict]:
        """Get imaging studies for a patient."""
        # Mock imaging data
        studies = [
            {
                "study_id": "IMG-001",
                "date": "2025-12-15",
                "modality": "xray",
                "body_part": "chest",
                "description": "Chest X-ray PA and Lateral",
                "findings_summary": "No acute cardiopulmonary abnormality"
            },
            {
                "study_id": "IMG-002", 
                "date": "2025-10-20",
                "modality": "ct",
                "body_part": "chest",
                "description": "CT Chest with contrast",
                "findings_summary": "2mm nodule in right lower lobe, recommend follow-up"
            }
        ]
        
        if modality:
            studies = [s for s in studies if s["modality"] == modality]
        
        return studies
    
    def get_encounter_history(self, patient_id: str) -> list[dict]:
        """Get all clinical encounters for a patient."""
        # Mock encounter data
        return [
            {
                "encounter_id": "ENC-001",
                "date": "2026-02-01",
                "type": "Office Visit",
                "provider": "Dr. Sarah Smith",
                "chief_complaint": "Annual checkup",
                "diagnosis": ["Routine examination"]
            },
            {
                "encounter_id": "ENC-002",
                "date": "2025-11-15",
                "type": "Urgent Care",
                "provider": "Dr. Michael Jones",
                "chief_complaint": "Chest pain",
                "diagnosis": ["Costochondritis"]
            }
        ]


# Singleton instance
_history_service = None

def get_history_service(fhir_server=None) -> PatientHistoryService:
    """Get or create the history service singleton."""
    global _history_service
    if _history_service is None:
        _history_service = PatientHistoryService(fhir_server=fhir_server)
    return _history_service
