"""
Mock FHIR EHR Server
Provides simulated patient data in FHIR R4 format for demo purposes.
"""

import json
from datetime import datetime, date
from pathlib import Path
from typing import Any

from fhir.resources.patient import Patient
from fhir.resources.condition import Condition
from fhir.resources.medicationstatement import MedicationStatement
from fhir.resources.allergyintolerance import AllergyIntolerance
from fhir.resources.observation import Observation


class MockFHIRServer:
    """
    Mock FHIR R4 server for demo purposes.
    Provides realistic patient data for clinical decision support demos.
    """
    
    def __init__(self, data_path: str | Path | None = None):
        """Initialize with optional path to sample patient data."""
        self.patients: dict[str, dict] = {}
        self.conditions: dict[str, list[dict]] = {}
        self.medications: dict[str, list[dict]] = {}
        self.allergies: dict[str, list[dict]] = {}
        self.observations: dict[str, list[dict]] = {}
        
        if data_path:
            self._load_data(Path(data_path))
        else:
            self._init_sample_data()
    
    def _init_sample_data(self):
        """Initialize with built-in sample patient data."""
        
        # Demo Patient 1: Perfect for chest X-ray demo
        self.patients["P001"] = {
            "resourceType": "Patient",
            "id": "P001",
            "name": [{"family": "Wilson", "given": ["Sarah", "M"]}],
            "gender": "female",
            "birthDate": "1968-03-15",
            "address": [{"city": "Chicago", "state": "IL"}]
        }
        
        self.conditions["P001"] = [
            {
                "resourceType": "Condition",
                "id": "C001",
                "subject": {"reference": "Patient/P001"},
                "code": {"coding": [{"system": "http://snomed.info/sct", "code": "195967001", "display": "Asthma"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": "2015-06-01"
            },
            {
                "resourceType": "Condition",
                "id": "C002",
                "subject": {"reference": "Patient/P001"},
                "code": {"coding": [{"system": "http://snomed.info/sct", "code": "38341003", "display": "Hypertension"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": "2020-01-15"
            }
        ]
        
        self.medications["P001"] = [
            {
                "resourceType": "MedicationStatement",
                "id": "M001",
                "subject": {"reference": "Patient/P001"},
                "medicationCodeableConcept": {"coding": [{"display": "Albuterol inhaler"}]},
                "status": "active",
                "dosage": [{"text": "2 puffs PRN"}]
            },
            {
                "resourceType": "MedicationStatement",
                "id": "M002",
                "subject": {"reference": "Patient/P001"},
                "medicationCodeableConcept": {"coding": [{"display": "Lisinopril 10mg"}]},
                "status": "active",
                "dosage": [{"text": "Once daily"}]
            }
        ]
        
        self.allergies["P001"] = [
            {
                "resourceType": "AllergyIntolerance",
                "id": "A001",
                "patient": {"reference": "Patient/P001"},
                "code": {"coding": [{"display": "Penicillin"}]},
                "reaction": [{"manifestation": [{"coding": [{"display": "Rash"}]}]}]
            }
        ]
        
        self.observations["P001"] = [
            {
                "resourceType": "Observation",
                "id": "O001",
                "subject": {"reference": "Patient/P001"},
                "code": {"coding": [{"display": "Blood Pressure"}]},
                "valueQuantity": {"value": 138, "unit": "mmHg", "system": "systolic"},
                "effectiveDateTime": "2026-02-01T10:00:00Z"
            },
            {
                "resourceType": "Observation",
                "id": "O002", 
                "subject": {"reference": "Patient/P001"},
                "code": {"coding": [{"display": "Heart Rate"}]},
                "valueQuantity": {"value": 78, "unit": "bpm"},
                "effectiveDateTime": "2026-02-01T10:00:00Z"
            },
            {
                "resourceType": "Observation",
                "id": "O003",
                "subject": {"reference": "Patient/P001"},
                "code": {"coding": [{"display": "Oxygen Saturation"}]},
                "valueQuantity": {"value": 96, "unit": "%"},
                "effectiveDateTime": "2026-02-01T10:00:00Z"
            },
            {
                "resourceType": "Observation",
                "id": "O004",
                "subject": {"reference": "Patient/P001"},
                "code": {"coding": [{"display": "Smoking Status"}]},
                "valueString": "Former smoker (quit 2019)",
                "effectiveDateTime": "2026-01-15T09:00:00Z"
            }
        ]
        
        # Demo Patient 2: Complex case
        self.patients["P002"] = {
            "resourceType": "Patient",
            "id": "P002",
            "name": [{"family": "Martinez", "given": ["Carlos"]}],
            "gender": "male",
            "birthDate": "1955-11-22",
            "address": [{"city": "Miami", "state": "FL"}]
        }
        
        self.conditions["P002"] = [
            {
                "resourceType": "Condition",
                "id": "C010",
                "subject": {"reference": "Patient/P002"},
                "code": {"coding": [{"system": "http://snomed.info/sct", "code": "73211009", "display": "Diabetes mellitus type 2"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": "2010-03-20"
            },
            {
                "resourceType": "Condition",
                "id": "C011",
                "subject": {"reference": "Patient/P002"},
                "code": {"coding": [{"display": "Coronary artery disease"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": "2018-09-10"
            },
            {
                "resourceType": "Condition",
                "id": "C012",
                "subject": {"reference": "Patient/P002"},
                "code": {"coding": [{"display": "Chronic kidney disease stage 3"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": "2022-04-01"
            }
        ]
        
        self.medications["P002"] = [
            {
                "resourceType": "MedicationStatement",
                "id": "M010",
                "subject": {"reference": "Patient/P002"},
                "medicationCodeableConcept": {"coding": [{"display": "Metformin 1000mg"}]},
                "status": "active",
                "dosage": [{"text": "Twice daily with meals"}]
            },
            {
                "resourceType": "MedicationStatement",
                "id": "M011",
                "subject": {"reference": "Patient/P002"},
                "medicationCodeableConcept": {"coding": [{"display": "Atorvastatin 40mg"}]},
                "status": "active",
                "dosage": [{"text": "Once daily at bedtime"}]
            },
            {
                "resourceType": "MedicationStatement",
                "id": "M012",
                "subject": {"reference": "Patient/P002"},
                "medicationCodeableConcept": {"coding": [{"display": "Aspirin 81mg"}]},
                "status": "active",
                "dosage": [{"text": "Once daily"}]
            }
        ]
        
        self.allergies["P002"] = [
            {
                "resourceType": "AllergyIntolerance",
                "id": "A010",
                "patient": {"reference": "Patient/P002"},
                "code": {"coding": [{"display": "Sulfa drugs"}]},
                "reaction": [{"manifestation": [{"coding": [{"display": "Anaphylaxis"}]}], "severity": "severe"}]
            }
        ]
        
        self.observations["P002"] = [
            {
                "resourceType": "Observation",
                "id": "O010",
                "subject": {"reference": "Patient/P002"},
                "code": {"coding": [{"display": "HbA1c"}]},
                "valueQuantity": {"value": 7.8, "unit": "%"},
                "effectiveDateTime": "2026-01-20T08:00:00Z"
            },
            {
                "resourceType": "Observation",
                "id": "O011",
                "subject": {"reference": "Patient/P002"},
                "code": {"coding": [{"display": "eGFR"}]},
                "valueQuantity": {"value": 45, "unit": "mL/min/1.73m2"},
                "effectiveDateTime": "2026-01-20T08:00:00Z"
            }
        ]
    
    def _load_data(self, data_path: Path):
        """Load patient data from JSON file."""
        if data_path.exists():
            with open(data_path) as f:
                data = json.load(f)
            self.patients = data.get("patients", {})
            self.conditions = data.get("conditions", {})
            self.medications = data.get("medications", {})
            self.allergies = data.get("allergies", {})
            self.observations = data.get("observations", {})
    
    def get_patient(self, patient_id: str) -> dict | None:
        """Get patient demographic data."""
        return self.patients.get(patient_id)
    
    def get_patient_summary(self, patient_id: str) -> dict | None:
        """
        Get comprehensive patient summary including all related resources.
        This is the main method used by the clinical assistant.
        """
        patient = self.patients.get(patient_id)
        if not patient:
            return None
        
        # Calculate age
        birth_date = datetime.strptime(patient["birthDate"], "%Y-%m-%d")
        age = (datetime.now() - birth_date).days // 365
        
        # Format patient summary
        name = patient["name"][0]
        full_name = f"{' '.join(name.get('given', []))} {name.get('family', '')}"
        
        return {
            "patient": {
                "id": patient_id,
                "name": full_name,
                "age": age,
                "gender": patient.get("gender", "unknown"),
                "location": patient.get("address", [{}])[0].get("city", "Unknown")
            },
            "conditions": [
                {
                    "name": c["code"]["coding"][0].get("display", "Unknown"),
                    "status": c["clinicalStatus"]["coding"][0].get("code", "unknown"),
                    "onset": c.get("onsetDateTime", "Unknown")
                }
                for c in self.conditions.get(patient_id, [])
            ],
            "medications": [
                {
                    "name": m["medicationCodeableConcept"]["coding"][0].get("display", "Unknown"),
                    "dosage": m.get("dosage", [{}])[0].get("text", "Unknown"),
                    "status": m.get("status", "unknown")
                }
                for m in self.medications.get(patient_id, [])
            ],
            "allergies": [
                {
                    "substance": a["code"]["coding"][0].get("display", "Unknown"),
                    "reaction": a.get("reaction", [{}])[0].get("manifestation", [{}])[0].get("coding", [{}])[0].get("display", "Unknown")
                }
                for a in self.allergies.get(patient_id, [])
            ],
            "recent_observations": [
                {
                    "type": o["code"]["coding"][0].get("display", "Unknown"),
                    "value": f"{o.get('valueQuantity', {}).get('value', o.get('valueString', 'N/A'))} {o.get('valueQuantity', {}).get('unit', '')}".strip(),
                    "date": o.get("effectiveDateTime", "Unknown")
                }
                for o in self.observations.get(patient_id, [])
            ]
        }
    
    def update_patient_record(
        self,
        patient_id: str,
        encounter_note: str | None = None,
        new_conditions: list[str] | None = None,
        new_medications: list[str] | None = None
    ) -> dict:
        """
        Update patient record with new encounter data.
        Returns a summary of what was updated.
        """
        if patient_id not in self.patients:
            return {"success": False, "error": "Patient not found"}
        
        updates = []
        
        if new_conditions:
            for condition in new_conditions:
                new_id = f"C{len(self.conditions.get(patient_id, [])) + 100}"
                if patient_id not in self.conditions:
                    self.conditions[patient_id] = []
                self.conditions[patient_id].append({
                    "resourceType": "Condition",
                    "id": new_id,
                    "subject": {"reference": f"Patient/{patient_id}"},
                    "code": {"coding": [{"display": condition}]},
                    "clinicalStatus": {"coding": [{"code": "active"}]},
                    "onsetDateTime": datetime.now().isoformat()
                })
                updates.append(f"Added condition: {condition}")
        
        if new_medications:
            for medication in new_medications:
                new_id = f"M{len(self.medications.get(patient_id, [])) + 100}"
                if patient_id not in self.medications:
                    self.medications[patient_id] = []
                self.medications[patient_id].append({
                    "resourceType": "MedicationStatement",
                    "id": new_id,
                    "subject": {"reference": f"Patient/{patient_id}"},
                    "medicationCodeableConcept": {"coding": [{"display": medication}]},
                    "status": "active"
                })
                updates.append(f"Added medication: {medication}")
        
        if encounter_note:
            updates.append(f"Added encounter note ({len(encounter_note)} characters)")
        
        return {
            "success": True,
            "patient_id": patient_id,
            "updates": updates,
            "timestamp": datetime.now().isoformat()
        }
    
    def list_patients(self) -> list[dict]:
        """List all available patients for demo selection."""
        return [
            {
                "id": pid,
                "name": f"{' '.join(p['name'][0].get('given', []))} {p['name'][0].get('family', '')}",
                "gender": p.get("gender"),
                "birthDate": p.get("birthDate")
            }
            for pid, p in self.patients.items()
        ]


# Singleton instance
_fhir_server: MockFHIRServer | None = None


def get_fhir_server() -> MockFHIRServer:
    """Get or create the singleton FHIR server instance."""
    global _fhir_server
    if _fhir_server is None:
        _fhir_server = MockFHIRServer()
    return _fhir_server
