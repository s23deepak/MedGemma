"""
Mock FHIR EHR Server
Provides simulated patient data in FHIR R4 format for demo purposes.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from fhir.resources.patient import Patient
from fhir.resources.condition import Condition
from fhir.resources.medicationstatement import MedicationStatement
from fhir.resources.allergyintolerance import AllergyIntolerance
from fhir.resources.observation import Observation


class MockFHIRServer:
    """
    Mock FHIR R4 server for demo purposes.
    Provides realistic patient data for clinical decision support demos.
    Includes outpatient (P001–P003) and inpatient (P004–P005) demo patients.
    """

    def __init__(self, data_path: str | Path | None = None):
        """Initialize with optional path to sample patient data."""
        self.patients: dict[str, dict] = {}
        self.conditions: dict[str, list[dict]] = {}
        self.medications: dict[str, list[dict]] = {}
        self.allergies: dict[str, list[dict]] = {}
        self.observations: dict[str, list[dict]] = {}
        self.memories: dict[str, list[dict]] = {}
        self.images: dict[str, list[dict]] = {}
        self.active_orders: dict[str, list[dict]] = {}
        self.progress_notes: dict[str, list[dict]] = {}

        if data_path:
            self._load_data(Path(data_path))
        else:
            self._init_sample_data()

    # ── Sample data ───────────────────────────────────────────────────────────

    def _init_sample_data(self):
        """Initialize with built-in sample patient data."""
        self._init_outpatients()
        self._init_inpatients()

    def _init_outpatients(self):
        """Outpatient demo patients P001–P003."""
        now = datetime.now()

        # ── P001: Sarah Wilson — asthma / hypertension (chest X-ray demo) ───
        self.patients["P001"] = {
            "resourceType": "Patient",
            "id": "P001",
            "name": [{"family": "Wilson", "given": ["Sarah", "M"]}],
            "gender": "female",
            "birthDate": "1968-03-15",
            "address": [{"city": "Chicago", "state": "IL"}],
            "encounter_type": "outpatient",
        }
        self.conditions["P001"] = [
            {
                "resourceType": "Condition",
                "id": "C001",
                "subject": {"reference": "Patient/P001"},
                "code": {"coding": [{"system": "http://snomed.info/sct", "code": "195967001", "display": "Asthma"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": "2015-06-01",
            },
            {
                "resourceType": "Condition",
                "id": "C002",
                "subject": {"reference": "Patient/P001"},
                "code": {"coding": [{"system": "http://snomed.info/sct", "code": "38341003", "display": "Hypertension"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": "2020-01-15",
            },
        ]
        self.medications["P001"] = [
            {
                "resourceType": "MedicationStatement",
                "id": "M001",
                "subject": {"reference": "Patient/P001"},
                "medicationCodeableConcept": {"coding": [{"display": "Albuterol inhaler"}]},
                "status": "active",
                "dosage": [{"text": "2 puffs PRN"}],
            },
            {
                "resourceType": "MedicationStatement",
                "id": "M002",
                "subject": {"reference": "Patient/P001"},
                "medicationCodeableConcept": {"coding": [{"display": "Lisinopril 10mg"}]},
                "status": "active",
                "dosage": [{"text": "Once daily"}],
            },
        ]
        self.allergies["P001"] = [
            {
                "resourceType": "AllergyIntolerance",
                "id": "A001",
                "patient": {"reference": "Patient/P001"},
                "code": {"coding": [{"display": "Penicillin"}]},
                "reaction": [{"manifestation": [{"coding": [{"display": "Rash"}]}]}],
            }
        ]
        self.observations["P001"] = [
            {
                "resourceType": "Observation", "id": "O001",
                "subject": {"reference": "Patient/P001"},
                "code": {"coding": [{"display": "Blood Pressure"}]},
                "valueQuantity": {"value": 138, "unit": "mmHg", "system": "systolic"},
                "effectiveDateTime": "2026-02-01T10:00:00Z",
            },
            {
                "resourceType": "Observation", "id": "O002",
                "subject": {"reference": "Patient/P001"},
                "code": {"coding": [{"display": "Heart Rate"}]},
                "valueQuantity": {"value": 78, "unit": "bpm"},
                "effectiveDateTime": "2026-02-01T10:00:00Z",
            },
            {
                "resourceType": "Observation", "id": "O003",
                "subject": {"reference": "Patient/P001"},
                "code": {"coding": [{"display": "Oxygen Saturation"}]},
                "valueQuantity": {"value": 96, "unit": "%"},
                "effectiveDateTime": "2026-02-01T10:00:00Z",
            },
            {
                "resourceType": "Observation", "id": "O004",
                "subject": {"reference": "Patient/P001"},
                "code": {"coding": [{"display": "Smoking Status"}]},
                "valueString": "Former smoker (quit 2019)",
                "effectiveDateTime": "2026-01-15T09:00:00Z",
            },
        ]

        # ── P002: Carlos Martinez — diabetes / CAD / CKD ─────────────────────
        self.patients["P002"] = {
            "resourceType": "Patient",
            "id": "P002",
            "name": [{"family": "Martinez", "given": ["Carlos"]}],
            "gender": "male",
            "birthDate": "1955-11-22",
            "address": [{"city": "Miami", "state": "FL"}],
            "encounter_type": "outpatient",
        }
        self.conditions["P002"] = [
            {
                "resourceType": "Condition", "id": "C010",
                "subject": {"reference": "Patient/P002"},
                "code": {"coding": [{"system": "http://snomed.info/sct", "code": "73211009", "display": "Diabetes mellitus type 2"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": "2010-03-20",
            },
            {
                "resourceType": "Condition", "id": "C011",
                "subject": {"reference": "Patient/P002"},
                "code": {"coding": [{"display": "Coronary artery disease"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": "2018-09-10",
            },
            {
                "resourceType": "Condition", "id": "C012",
                "subject": {"reference": "Patient/P002"},
                "code": {"coding": [{"display": "Chronic kidney disease stage 3"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": "2022-04-01",
            },
        ]
        self.medications["P002"] = [
            {
                "resourceType": "MedicationStatement", "id": "M010",
                "subject": {"reference": "Patient/P002"},
                "medicationCodeableConcept": {"coding": [{"display": "Metformin 1000mg"}]},
                "status": "active",
                "dosage": [{"text": "Twice daily with meals"}],
            },
            {
                "resourceType": "MedicationStatement", "id": "M011",
                "subject": {"reference": "Patient/P002"},
                "medicationCodeableConcept": {"coding": [{"display": "Atorvastatin 40mg"}]},
                "status": "active",
                "dosage": [{"text": "Once daily at bedtime"}],
            },
            {
                "resourceType": "MedicationStatement", "id": "M012",
                "subject": {"reference": "Patient/P002"},
                "medicationCodeableConcept": {"coding": [{"display": "Aspirin 81mg"}]},
                "status": "active",
                "dosage": [{"text": "Once daily"}],
            },
        ]
        self.allergies["P002"] = [
            {
                "resourceType": "AllergyIntolerance", "id": "A010",
                "patient": {"reference": "Patient/P002"},
                "code": {"coding": [{"display": "Sulfa drugs"}]},
                "reaction": [{"manifestation": [{"coding": [{"display": "Anaphylaxis"}]}], "severity": "severe"}],
            }
        ]
        self.observations["P002"] = [
            {
                "resourceType": "Observation", "id": "O010",
                "subject": {"reference": "Patient/P002"},
                "code": {"coding": [{"display": "HbA1c"}]},
                "valueQuantity": {"value": 7.8, "unit": "%"},
                "effectiveDateTime": "2026-01-20T08:00:00Z",
            },
            {
                "resourceType": "Observation", "id": "O011",
                "subject": {"reference": "Patient/P002"},
                "code": {"coding": [{"display": "eGFR"}]},
                "valueQuantity": {"value": 45, "unit": "mL/min/1.73m2"},
                "effectiveDateTime": "2026-01-20T08:00:00Z",
            },
        ]

        # ── P003: John Doe — anxiety / migraine ──────────────────────────────
        self.patients["P003"] = {
            "resourceType": "Patient",
            "id": "P003",
            "name": [{"family": "Doe", "given": ["John"]}],
            "gender": "male",
            "birthDate": "1980-07-10",
            "address": [{"city": "Los Angeles", "state": "CA"}],
            "encounter_type": "outpatient",
        }
        self.conditions["P003"] = [
            {
                "resourceType": "Condition", "id": "C020",
                "subject": {"reference": "Patient/P003"},
                "code": {"coding": [{"display": "Anxiety disorder"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": "2021-03-15",
            },
            {
                "resourceType": "Condition", "id": "C021",
                "subject": {"reference": "Patient/P003"},
                "code": {"coding": [{"display": "Migraine"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": "2019-08-20",
            },
        ]
        self.medications["P003"] = [
            {
                "resourceType": "MedicationStatement", "id": "M020",
                "subject": {"reference": "Patient/P003"},
                "medicationCodeableConcept": {"coding": [{"display": "Sertraline 50mg"}]},
                "status": "active",
                "dosage": [{"text": "Once daily in the morning"}],
            },
            {
                "resourceType": "MedicationStatement", "id": "M021",
                "subject": {"reference": "Patient/P003"},
                "medicationCodeableConcept": {"coding": [{"display": "Sumatriptan 50mg"}]},
                "status": "active",
                "dosage": [{"text": "As needed for migraines"}],
            },
            {
                "resourceType": "MedicationStatement", "id": "M022",
                "subject": {"reference": "Patient/P003"},
                "medicationCodeableConcept": {"coding": [{"display": "Ibuprofen 400mg"}]},
                "status": "active",
                "dosage": [{"text": "As needed for pain"}],
            },
        ]
        self.allergies["P003"] = [
            {
                "resourceType": "AllergyIntolerance", "id": "A020",
                "patient": {"reference": "Patient/P003"},
                "code": {"coding": [{"display": "Latex"}]},
                "reaction": [{"manifestation": [{"coding": [{"display": "Skin irritation"}]}]}],
            },
            {
                "resourceType": "AllergyIntolerance", "id": "A021",
                "patient": {"reference": "Patient/P003"},
                "code": {"coding": [{"display": "Codeine"}]},
                "reaction": [{"manifestation": [{"coding": [{"display": "Nausea and vomiting"}]}]}],
            },
        ]
        self.observations["P003"] = [
            {
                "resourceType": "Observation", "id": "O020",
                "subject": {"reference": "Patient/P003"},
                "code": {"coding": [{"display": "Blood Pressure"}]},
                "valueQuantity": {"value": 122, "unit": "mmHg", "system": "systolic"},
                "effectiveDateTime": "2026-02-10T09:00:00Z",
            },
            {
                "resourceType": "Observation", "id": "O021",
                "subject": {"reference": "Patient/P003"},
                "code": {"coding": [{"display": "Heart Rate"}]},
                "valueQuantity": {"value": 72, "unit": "bpm"},
                "effectiveDateTime": "2026-02-10T09:00:00Z",
            },
            {
                "resourceType": "Observation", "id": "O022",
                "subject": {"reference": "Patient/P003"},
                "code": {"coding": [{"display": "Weight"}]},
                "valueQuantity": {"value": 85, "unit": "kg"},
                "effectiveDateTime": "2026-02-10T09:00:00Z",
            },
        ]
        self.images["P003"] = [
            {
                "url": "/static/images/mock_chest_xray.jpg",
                "modality": "xray",
                "timestamp": "2025-11-15T14:30:00Z",
                "analysis": (
                    "PA and Lateral views of the chest demonstrate clear lungs without focal "
                    "consolidation, pneumothorax, or pleural effusion. The cardiac silhouette is "
                    "normal in size and contour. The mediastinum and hila are unremarkable. "
                    "Conclusion: Normal chest radiograph."
                ),
            }
        ]

    def _init_inpatients(self):
        """Inpatient demo patients P004 (ICU sepsis) and P005 (CHF med/surg)."""
        now = datetime.now()
        admission_p004 = (now - timedelta(hours=36)).isoformat()   # 1.5 days ago
        admission_p005 = (now - timedelta(days=4)).isoformat()      # 4 days ago

        # ── P004: Raymond Okafor — ICU sepsis, day 2 ─────────────────────────
        # Intentionally missing VTE prophylaxis → triggers safety alert.
        # Foley inserted at admission (36 h ago) → triggers dwell-time alert.
        # No physician note in last 26 h → triggers note-currency alert.
        self.patients["P004"] = {
            "resourceType": "Patient",
            "id": "P004",
            "name": [{"family": "Okafor", "given": ["Raymond"]}],
            "gender": "male",
            "birthDate": "1972-04-18",
            "address": [{"city": "Houston", "state": "TX"}],
            "encounter_type": "inpatient",
            "admission_date": admission_p004,
            "ward": "ICU",
            "bed": "ICU-04",
            "code_status": "Full Code",
            "attending": "Dr. Sarah Smith",
        }
        self.conditions["P004"] = [
            {
                "resourceType": "Condition", "id": "C030",
                "subject": {"reference": "Patient/P004"},
                "code": {"coding": [{"display": "Sepsis due to gram-negative bacteria"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": admission_p004,
            },
            {
                "resourceType": "Condition", "id": "C031",
                "subject": {"reference": "Patient/P004"},
                "code": {"coding": [{"display": "Acute respiratory failure"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": admission_p004,
            },
            {
                "resourceType": "Condition", "id": "C032",
                "subject": {"reference": "Patient/P004"},
                "code": {"coding": [{"display": "Type 2 diabetes mellitus"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": "2015-06-10",
            },
        ]
        self.medications["P004"] = [
            {
                "resourceType": "MedicationStatement", "id": "M030",
                "subject": {"reference": "Patient/P004"},
                "medicationCodeableConcept": {"coding": [{"display": "Piperacillin-Tazobactam 3.375g IV"}]},
                "status": "active",
                "dosage": [{"text": "Every 6 hours IV"}],
            },
            {
                "resourceType": "MedicationStatement", "id": "M031",
                "subject": {"reference": "Patient/P004"},
                "medicationCodeableConcept": {"coding": [{"display": "Norepinephrine infusion"}]},
                "status": "active",
                "dosage": [{"text": "0.08 mcg/kg/min IV (titrate for MAP >65)"}],
            },
            {
                "resourceType": "MedicationStatement", "id": "M032",
                "subject": {"reference": "Patient/P004"},
                "medicationCodeableConcept": {"coding": [{"display": "Insulin Regular (sliding scale)"}]},
                "status": "active",
                "dosage": [{"text": "Sliding scale per ICU protocol"}],
            },
        ]
        self.allergies["P004"] = [
            {
                "resourceType": "AllergyIntolerance", "id": "A030",
                "patient": {"reference": "Patient/P004"},
                "code": {"coding": [{"display": "Vancomycin"}]},
                "reaction": [{"manifestation": [{"coding": [{"display": "Red man syndrome"}]}], "severity": "moderate"}],
            }
        ]
        self.observations["P004"] = [
            {
                "resourceType": "Observation", "id": "O030",
                "subject": {"reference": "Patient/P004"},
                "code": {"coding": [{"display": "Blood Pressure"}]},
                "valueQuantity": {"value": 88, "unit": "mmHg", "system": "systolic"},
                "effectiveDateTime": (now - timedelta(hours=1)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O031",
                "subject": {"reference": "Patient/P004"},
                "code": {"coding": [{"display": "Heart Rate"}]},
                "valueQuantity": {"value": 118, "unit": "bpm"},
                "effectiveDateTime": (now - timedelta(hours=1)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O032",
                "subject": {"reference": "Patient/P004"},
                "code": {"coding": [{"display": "Temperature"}]},
                "valueQuantity": {"value": 38.9, "unit": "°C"},
                "effectiveDateTime": (now - timedelta(hours=2)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O033",
                "subject": {"reference": "Patient/P004"},
                "code": {"coding": [{"display": "Oxygen Saturation"}]},
                "valueQuantity": {"value": 94, "unit": "%"},
                "effectiveDateTime": (now - timedelta(hours=1)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O034",
                "subject": {"reference": "Patient/P004"},
                "code": {"coding": [{"display": "Lactate"}]},
                "valueQuantity": {"value": 3.2, "unit": "mmol/L"},
                "effectiveDateTime": (now - timedelta(hours=4)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O035",
                "subject": {"reference": "Patient/P004"},
                "code": {"coding": [{"display": "Blood Glucose"}]},
                "valueQuantity": {"value": 218, "unit": "mg/dL"},
                "effectiveDateTime": (now - timedelta(hours=2)).isoformat(),
            },
        ]
        # Active orders for P004 — NOTE: no VTE prophylaxis order (safety alert trigger)
        self.active_orders["P004"] = [
            {
                "order_id": "ORD-P004-001",
                "type": "medication",
                "name": "Piperacillin-Tazobactam 3.375g IV q6h",
                "ordered_at": admission_p004,
                "status": "active",
            },
            {
                "order_id": "ORD-P004-002",
                "type": "medication",
                "name": "Norepinephrine infusion",
                "ordered_at": admission_p004,
                "status": "active",
            },
            {
                "order_id": "ORD-P004-003",
                "type": "device",
                "name": "Foley catheter",
                "ordered_at": admission_p004,
                "inserted_at": admission_p004,
                "status": "active",
            },
            {
                "order_id": "ORD-P004-004",
                "type": "monitoring",
                "name": "Continuous cardiac monitoring",
                "ordered_at": admission_p004,
                "status": "active",
            },
            {
                "order_id": "ORD-P004-005",
                "type": "lab",
                "name": "Basic metabolic panel Q8h",
                "ordered_at": admission_p004,
                "status": "active",
            },
            # No VTE prophylaxis order — intentional for safety alert demo
        ]
        # Progress notes for P004 — last note is 26 hours ago (safety alert trigger)
        self.progress_notes["P004"] = [
            {
                "note_id": "PN-P004-001",
                "author": "Dr. Sarah Smith",
                "role": "attending",
                "created_at": admission_p004,
                "note_text": (
                    "62M admitted via ED with sepsis, likely source: community-acquired pneumonia. "
                    "Started on broad-spectrum antibiotics and vasopressor support. "
                    "Initial lactate 4.1 trending down. Intubated for airway protection."
                ),
            },
            {
                "note_id": "PN-P004-002",
                "author": "Dr. Emily Lee",
                "role": "resident",
                "created_at": (now - timedelta(hours=26)).isoformat(),
                "note_text": (
                    "Overnight: hemodynamically marginal on norepinephrine 0.08 mcg/kg/min. "
                    "Repeat lactate 3.2, downtrending. Blood cultures x2 pending. "
                    "Glucose 218 — added to insulin sliding scale. Urine output 25 mL/hr."
                ),
            },
        ]

        # ── P005: Dorothy Chen — CHF exacerbation, day 4, near discharge ──────
        self.patients["P005"] = {
            "resourceType": "Patient",
            "id": "P005",
            "name": [{"family": "Chen", "given": ["Dorothy"]}],
            "gender": "female",
            "birthDate": "1949-09-03",
            "address": [{"city": "Seattle", "state": "WA"}],
            "encounter_type": "inpatient",
            "admission_date": admission_p005,
            "ward": "Cardiology",
            "bed": "CARD-12",
            "code_status": "DNR/DNI",
            "attending": "Dr. Michael Jones",
        }
        self.conditions["P005"] = [
            {
                "resourceType": "Condition", "id": "C040",
                "subject": {"reference": "Patient/P005"},
                "code": {"coding": [{"display": "Acute exacerbation of congestive heart failure"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": admission_p005,
            },
            {
                "resourceType": "Condition", "id": "C041",
                "subject": {"reference": "Patient/P005"},
                "code": {"coding": [{"display": "Atrial fibrillation"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": "2019-11-05",
            },
            {
                "resourceType": "Condition", "id": "C042",
                "subject": {"reference": "Patient/P005"},
                "code": {"coding": [{"display": "Chronic kidney disease stage 3"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": "2021-03-18",
            },
            {
                "resourceType": "Condition", "id": "C043",
                "subject": {"reference": "Patient/P005"},
                "code": {"coding": [{"display": "Type 2 diabetes mellitus"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": "2008-07-22",
            },
        ]
        self.medications["P005"] = [
            {
                "resourceType": "MedicationStatement", "id": "M040",
                "subject": {"reference": "Patient/P005"},
                "medicationCodeableConcept": {"coding": [{"display": "Furosemide 80mg IV"}]},
                "status": "active",
                "dosage": [{"text": "Twice daily IV (transitioning to oral)"}],
            },
            {
                "resourceType": "MedicationStatement", "id": "M041",
                "subject": {"reference": "Patient/P005"},
                "medicationCodeableConcept": {"coding": [{"display": "Carvedilol 6.25mg"}]},
                "status": "active",
                "dosage": [{"text": "Twice daily oral"}],
            },
            {
                "resourceType": "MedicationStatement", "id": "M042",
                "subject": {"reference": "Patient/P005"},
                "medicationCodeableConcept": {"coding": [{"display": "Lisinopril 5mg"}]},
                "status": "active",
                "dosage": [{"text": "Once daily (held while Cr elevated)"}],
            },
            {
                "resourceType": "MedicationStatement", "id": "M043",
                "subject": {"reference": "Patient/P005"},
                "medicationCodeableConcept": {"coding": [{"display": "Apixaban 5mg"}]},
                "status": "active",
                "dosage": [{"text": "Twice daily (a-fib anticoagulation)"}],
            },
            {
                "resourceType": "MedicationStatement", "id": "M044",
                "subject": {"reference": "Patient/P005"},
                "medicationCodeableConcept": {"coding": [{"display": "Insulin Glargine 18 units"}]},
                "status": "active",
                "dosage": [{"text": "Once nightly subcutaneous"}],
            },
        ]
        self.allergies["P005"] = [
            {
                "resourceType": "AllergyIntolerance", "id": "A040",
                "patient": {"reference": "Patient/P005"},
                "code": {"coding": [{"display": "Aspirin"}]},
                "reaction": [{"manifestation": [{"coding": [{"display": "Bronchospasm"}]}], "severity": "severe"}],
            }
        ]
        self.observations["P005"] = [
            {
                "resourceType": "Observation", "id": "O040",
                "subject": {"reference": "Patient/P005"},
                "code": {"coding": [{"display": "Blood Pressure"}]},
                "valueQuantity": {"value": 118, "unit": "mmHg", "system": "systolic"},
                "effectiveDateTime": (now - timedelta(hours=3)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O041",
                "subject": {"reference": "Patient/P005"},
                "code": {"coding": [{"display": "Heart Rate"}]},
                "valueQuantity": {"value": 76, "unit": "bpm"},
                "effectiveDateTime": (now - timedelta(hours=3)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O042",
                "subject": {"reference": "Patient/P005"},
                "code": {"coding": [{"display": "Oxygen Saturation"}]},
                "valueQuantity": {"value": 96, "unit": "%"},
                "effectiveDateTime": (now - timedelta(hours=3)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O043",
                "subject": {"reference": "Patient/P005"},
                "code": {"coding": [{"display": "Weight"}]},
                "valueQuantity": {"value": 72.4, "unit": "kg"},
                "effectiveDateTime": (now - timedelta(hours=6)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O044",
                "subject": {"reference": "Patient/P005"},
                "code": {"coding": [{"display": "BNP"}]},
                "valueQuantity": {"value": 620, "unit": "pg/mL"},
                "effectiveDateTime": (now - timedelta(hours=8)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O045",
                "subject": {"reference": "Patient/P005"},
                "code": {"coding": [{"display": "Creatinine"}]},
                "valueQuantity": {"value": 1.6, "unit": "mg/dL"},
                "effectiveDateTime": (now - timedelta(hours=8)).isoformat(),
            },
        ]
        self.active_orders["P005"] = [
            {
                "order_id": "ORD-P005-001",
                "type": "medication",
                "name": "Furosemide 80mg IV BID",
                "ordered_at": admission_p005,
                "status": "active",
            },
            {
                "order_id": "ORD-P005-002",
                "type": "monitoring",
                "name": "Daily weight",
                "ordered_at": admission_p005,
                "status": "active",
            },
            {
                "order_id": "ORD-P005-003",
                "type": "monitoring",
                "name": "Strict I&O",
                "ordered_at": admission_p005,
                "status": "active",
            },
            {
                "order_id": "ORD-P005-004",
                "type": "prophylaxis",
                "name": "Enoxaparin 40mg SQ daily (VTE prophylaxis)",
                "ordered_at": admission_p005,
                "status": "active",
            },
            {
                "order_id": "ORD-P005-005",
                "type": "diet",
                "name": "2g sodium, 1500 mL fluid restriction",
                "ordered_at": admission_p005,
                "status": "active",
            },
            {
                "order_id": "ORD-P005-006",
                "type": "lab",
                "name": "BMP, BNP daily",
                "ordered_at": admission_p005,
                "status": "active",
            },
            {
                "order_id": "ORD-P005-007",
                "type": "consult",
                "name": "Cardiology follow-up within 7 days post-discharge",
                "ordered_at": (now - timedelta(days=1)).isoformat(),
                "status": "pending",
            },
        ]
        self.progress_notes["P005"] = [
            {
                "note_id": "PN-P005-001",
                "author": "Dr. Michael Jones",
                "role": "attending",
                "created_at": admission_p005,
                "note_text": (
                    "76F admitted with acute CHF exacerbation, weight up 5 kg from baseline. "
                    "Known EF 30% (last echo 2025-08). Started IV diuresis. "
                    "CXR: bilateral pulmonary edema, cardiomegaly. BNP 2100."
                ),
            },
            {
                "note_id": "PN-P005-002",
                "author": "Dr. Emily Lee",
                "role": "resident",
                "created_at": (now - timedelta(days=2)).isoformat(),
                "note_text": (
                    "Day 2: net negative 2.1L. Weight 74.8 kg. BNP 1250. "
                    "O2 requirements reduced to 2L NC. HR rate-controlled in 70s."
                ),
            },
            {
                "note_id": "PN-P005-003",
                "author": "Dr. Michael Jones",
                "role": "attending",
                "created_at": (now - timedelta(hours=10)).isoformat(),
                "note_text": (
                    "Day 4: significant clinical improvement. Weight 72.4 kg (total -5.6 kg). "
                    "BNP 620 (trending down). Room air O2 sat 96%. "
                    "Plan: transition furosemide to oral, target discharge tomorrow. "
                    "Needs cardiology follow-up, daily weights at home, return precautions."
                ),
            },
        ]

    # ── Data access ───────────────────────────────────────────────────────────

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

        birth_date = datetime.strptime(patient["birthDate"], "%Y-%m-%d")
        age = (datetime.now() - birth_date).days // 365

        name = patient["name"][0]
        full_name = f"{' '.join(name.get('given', []))} {name.get('family', '')}"

        summary = {
            "patient": {
                "id": patient_id,
                "name": full_name,
                "age": age,
                "gender": patient.get("gender", "unknown"),
                "location": patient.get("address", [{}])[0].get("city", "Unknown"),
                "encounter_type": patient.get("encounter_type", "outpatient"),
            },
            "conditions": [
                {
                    "name": c["code"]["coding"][0].get("display", "Unknown"),
                    "status": c["clinicalStatus"]["coding"][0].get("code", "unknown"),
                    "onset": c.get("onsetDateTime", "Unknown"),
                }
                for c in self.conditions.get(patient_id, [])
            ],
            "medications": [
                {
                    "name": m["medicationCodeableConcept"]["coding"][0].get("display", "Unknown"),
                    "dosage": m.get("dosage", [{}])[0].get("text", "Unknown"),
                    "status": m.get("status", "unknown"),
                }
                for m in self.medications.get(patient_id, [])
            ],
            "allergies": [
                {
                    "substance": a["code"]["coding"][0].get("display", "Unknown"),
                    "reaction": (
                        a.get("reaction", [{}])[0]
                        .get("manifestation", [{}])[0]
                        .get("coding", [{}])[0]
                        .get("display", "Unknown")
                    ),
                }
                for a in self.allergies.get(patient_id, [])
            ],
            "recent_observations": [
                {
                    "type": o["code"]["coding"][0].get("display", "Unknown"),
                    "value": (
                        f"{o.get('valueQuantity', {}).get('value', o.get('valueString', 'N/A'))} "
                        f"{o.get('valueQuantity', {}).get('unit', '')}".strip()
                    ),
                    "date": o.get("effectiveDateTime", "Unknown"),
                }
                for o in self.observations.get(patient_id, [])
            ],
            "images": self.images.get(patient_id, []),
        }

        # Append inpatient-specific fields when available
        if patient.get("encounter_type") == "inpatient":
            summary["patient"].update({
                "admission_date": patient.get("admission_date"),
                "ward": patient.get("ward"),
                "bed": patient.get("bed"),
                "code_status": patient.get("code_status"),
                "attending": patient.get("attending"),
            })

        return summary

    def update_patient_record(
        self,
        patient_id: str,
        encounter_note: str | None = None,
        new_conditions: list[str] | None = None,
        new_medications: list[str] | None = None,
    ) -> dict:
        """Update patient record with new encounter data."""
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
                    "onsetDateTime": datetime.now().isoformat(),
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
                    "status": "active",
                })
                updates.append(f"Added medication: {medication}")

        if encounter_note:
            updates.append(f"Added encounter note ({len(encounter_note)} characters)")

        return {
            "success": True,
            "patient_id": patient_id,
            "updates": updates,
            "timestamp": datetime.now().isoformat(),
        }

    def list_patients(self) -> list[dict]:
        """List all available patients for demo selection."""
        return [
            {
                "id": pid,
                "name": f"{' '.join(p['name'][0].get('given', []))} {p['name'][0].get('family', '')}",
                "gender": p.get("gender"),
                "birthDate": p.get("birthDate"),
                "encounter_type": p.get("encounter_type", "outpatient"),
            }
            for pid, p in self.patients.items()
        ]

    def list_inpatients(self) -> list[dict]:
        """List only admitted (inpatient) patients with ward/bed info."""
        result = []
        for pid, p in self.patients.items():
            if p.get("encounter_type") != "inpatient":
                continue
            name = p["name"][0]
            full_name = f"{' '.join(name.get('given', []))} {name.get('family', '')}"
            birth_date = datetime.strptime(p["birthDate"], "%Y-%m-%d")
            age = (datetime.now() - birth_date).days // 365
            result.append({
                "id": pid,
                "name": full_name,
                "age": age,
                "gender": p.get("gender"),
                "ward": p.get("ward"),
                "bed": p.get("bed"),
                "admission_date": p.get("admission_date"),
                "code_status": p.get("code_status"),
                "attending": p.get("attending"),
            })
        return result

    def get_active_orders(self, patient_id: str) -> list[dict]:
        """Return active orders for a patient."""
        return [
            o for o in self.active_orders.get(patient_id, [])
            if o.get("status") in ("active", "pending")
        ]

    def get_progress_notes(self, patient_id: str) -> list[dict]:
        """Return progress notes for a patient, newest first."""
        notes = list(self.progress_notes.get(patient_id, []))
        notes.sort(key=lambda n: n.get("created_at", ""), reverse=True)
        return notes

    def add_progress_note(self, patient_id: str, note_text: str, author: str, role: str = "physician") -> dict:
        """Add a new progress note for a patient."""
        if patient_id not in self.patients:
            return {"success": False, "error": "Patient not found"}
        import uuid
        note = {
            "note_id": f"PN-{uuid.uuid4().hex[:8].upper()}",
            "author": author,
            "role": role,
            "created_at": datetime.now().isoformat(),
            "note_text": note_text,
        }
        if patient_id not in self.progress_notes:
            self.progress_notes[patient_id] = []
        self.progress_notes[patient_id].append(note)
        return {"success": True, "note_id": note["note_id"]}

    def add_memory(self, patient_id: str, memory_text: str) -> bool:
        """Store a patient memory note."""
        if patient_id not in self.patients:
            return False
        if patient_id not in self.memories:
            self.memories[patient_id] = []
        self.memories[patient_id].append({
            "text": memory_text,
            "timestamp": datetime.now().isoformat(),
        })
        return True

    def get_memories(self, patient_id: str) -> list[str]:
        """Get all stored memories for a patient."""
        memories = self.memories.get(patient_id, [])
        memories.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
        return [m.get("text", "") for m in memories if m.get("text")]

    def _load_data(self, data_path: "Path"):
        """Load patient data from JSON file."""
        if data_path.exists():
            with open(data_path) as f:
                data = json.load(f)
            self.patients = data.get("patients", {})
            self.conditions = data.get("conditions", {})
            self.medications = data.get("medications", {})
            self.allergies = data.get("allergies", {})
            self.observations = data.get("observations", {})
            self.active_orders = data.get("active_orders", {})
            self.progress_notes = data.get("progress_notes", {})


# ── Singleton ──────────────────────────────────────────────────────────────────
_fhir_server: MockFHIRServer | None = None


def get_fhir_server() -> MockFHIRServer:
    """Get or create the singleton FHIR server instance."""
    global _fhir_server
    if _fhir_server is None:
        _fhir_server = MockFHIRServer()
    return _fhir_server
