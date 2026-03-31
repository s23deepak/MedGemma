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

    Outpatient encounters  : P001–P003 (asthma/HTN, DM/CAD/CKD, anxiety/migraine)
    Inpatient — rounding   : P004–P005 (sepsis/ICU, CHF/cardiology)
                             P006 (CAP + COPD, Gen Medicine Day 4)
                             P007 (acute ischemic stroke, Neurology Day 2)
    Inpatient — shift brief: P008 (perforated peptic ulcer post-op, SICU)
                             P009 (NSTEMI awaiting cath, CCU)
    ED / new encounters    : P010 (probable SLE — rare disease / council)
                             P011 (progressive dyspnea + clubbing — IPF vs. malignancy)
    Rare disease hunt      : P012 (dermatomyositis — proximal weakness + heliotrope rash)
                             P013 (McArdle disease — exercise intolerance + myoglobinuria)
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
        self._init_extended_patients()

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
            "hospital_id": "GENERAL",
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
            "hospital_id": "GENERAL",
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
            "hospital_id": "GENERAL",
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
            "hospital_id": "GENERAL",
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
            {
                "resourceType": "Condition", "id": "C033",
                "subject": {"reference": "Patient/P004"},
                "code": {"coding": [{"display": "Acute kidney injury stage 2"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
                "onsetDateTime": (now - timedelta(hours=18)).isoformat(),
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
            # Trending labs added for richer AI reasoning
            {
                "resourceType": "Observation", "id": "O036",
                "subject": {"reference": "Patient/P004"},
                "code": {"coding": [{"display": "WBC"}]},
                "valueQuantity": {"value": 19.2, "unit": "K/uL"},
                "effectiveDateTime": (now - timedelta(hours=36)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O037",
                "subject": {"reference": "Patient/P004"},
                "code": {"coding": [{"display": "WBC"}]},
                "valueQuantity": {"value": 16.8, "unit": "K/uL"},
                "effectiveDateTime": (now - timedelta(hours=8)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O038",
                "subject": {"reference": "Patient/P004"},
                "code": {"coding": [{"display": "Creatinine"}]},
                "valueQuantity": {"value": 1.4, "unit": "mg/dL"},
                "effectiveDateTime": (now - timedelta(hours=36)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O039",
                "subject": {"reference": "Patient/P004"},
                "code": {"coding": [{"display": "Creatinine"}]},
                "valueQuantity": {"value": 2.1, "unit": "mg/dL"},
                "effectiveDateTime": (now - timedelta(hours=18)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O040",
                "subject": {"reference": "Patient/P004"},
                "code": {"coding": [{"display": "Creatinine"}]},
                "valueQuantity": {"value": 2.4, "unit": "mg/dL"},
                "effectiveDateTime": (now - timedelta(hours=8)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O041",
                "subject": {"reference": "Patient/P004"},
                "code": {"coding": [{"display": "Procalcitonin"}]},
                "valueQuantity": {"value": 42.8, "unit": "ng/mL"},
                "effectiveDateTime": (now - timedelta(hours=36)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O042",
                "subject": {"reference": "Patient/P004"},
                "code": {"coding": [{"display": "Blood Culture Result"}]},
                "valueQuantity": {"value": "Gram-negative bacteremia — E. coli, susceptibilities pending", "unit": "text"},
                "effectiveDateTime": (now - timedelta(hours=14)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O043",
                "subject": {"reference": "Patient/P004"},
                "code": {"coding": [{"display": "Urine Output"}]},
                "valueQuantity": {"value": 22, "unit": "mL/hr"},
                "effectiveDateTime": (now - timedelta(hours=2)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O044",
                "subject": {"reference": "Patient/P004"},
                "code": {"coding": [{"display": "Mean Arterial Pressure"}]},
                "valueQuantity": {"value": 68, "unit": "mmHg"},
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
            {
                "order_id": "ORD-P004-006",
                "type": "lab",
                "name": "Blood culture susceptibility follow-up (stat)",
                "ordered_at": (now - timedelta(hours=14)).isoformat(),
                "status": "active",
            },
            {
                "order_id": "ORD-P004-007",
                "type": "consult",
                "name": "Infectious Disease consult — gram-negative bacteremia, AKI",
                "ordered_at": (now - timedelta(hours=12)).isoformat(),
                "status": "pending",
            },
            {
                "order_id": "ORD-P004-008",
                "type": "imaging",
                "name": "Renal ultrasound — new AKI stage 2 workup",
                "ordered_at": (now - timedelta(hours=8)).isoformat(),
                "status": "pending",
            },
            {
                "order_id": "ORD-P004-009",
                "type": "lab",
                "name": "Repeat BMP in 4 hours",
                "ordered_at": (now - timedelta(hours=2)).isoformat(),
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
            "hospital_id": "COMMUNITY",
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
            # Trending labs — admission through current, for AI trajectory reasoning
            {
                "resourceType": "Observation", "id": "O046",
                "subject": {"reference": "Patient/P005"},
                "code": {"coding": [{"display": "Creatinine"}]},
                "valueQuantity": {"value": 1.4, "unit": "mg/dL"},
                "effectiveDateTime": (now - timedelta(days=4)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O047",
                "subject": {"reference": "Patient/P005"},
                "code": {"coding": [{"display": "Creatinine"}]},
                "valueQuantity": {"value": 1.5, "unit": "mg/dL"},
                "effectiveDateTime": (now - timedelta(days=3)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O048",
                "subject": {"reference": "Patient/P005"},
                "code": {"coding": [{"display": "Creatinine"}]},
                "valueQuantity": {"value": 1.6, "unit": "mg/dL"},
                "effectiveDateTime": (now - timedelta(days=2)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O049",
                "subject": {"reference": "Patient/P005"},
                "code": {"coding": [{"display": "Creatinine"}]},
                "valueQuantity": {"value": 1.7, "unit": "mg/dL"},
                "effectiveDateTime": (now - timedelta(hours=8)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O050",
                "subject": {"reference": "Patient/P005"},
                "code": {"coding": [{"display": "eGFR"}]},
                "valueQuantity": {"value": 35, "unit": "mL/min"},
                "effectiveDateTime": (now - timedelta(hours=8)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O051",
                "subject": {"reference": "Patient/P005"},
                "code": {"coding": [{"display": "BNP"}]},
                "valueQuantity": {"value": 2100, "unit": "pg/mL"},
                "effectiveDateTime": (now - timedelta(days=4)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O052",
                "subject": {"reference": "Patient/P005"},
                "code": {"coding": [{"display": "BNP"}]},
                "valueQuantity": {"value": 1250, "unit": "pg/mL"},
                "effectiveDateTime": (now - timedelta(days=2)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O053",
                "subject": {"reference": "Patient/P005"},
                "code": {"coding": [{"display": "Weight"}]},
                "valueQuantity": {"value": 78.8, "unit": "kg"},
                "effectiveDateTime": (now - timedelta(days=4)).isoformat(),
            },
            {
                "resourceType": "Observation", "id": "O054",
                "subject": {"reference": "Patient/P005"},
                "code": {"coding": [{"display": "Weight"}]},
                "valueQuantity": {"value": 74.8, "unit": "kg"},
                "effectiveDateTime": (now - timedelta(days=2)).isoformat(),
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
            {
                "order_id": "ORD-P005-008",
                "type": "device",
                "name": "Foley catheter",
                "ordered_at": admission_p005,
                "inserted_at": admission_p005,
                "status": "active",
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
                "hospital_id": patient.get("hospital_id", "GENERAL"),
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

    def _init_extended_patients(self):
        """Extended demo patients P006–P013: rounding, shift brief, encounters, rare disease."""
        now = datetime.now()

        # ─────────────────────────────────────────────────────────────────────
        # ROUNDING PATIENTS (inpatient — ward rounds)
        # ─────────────────────────────────────────────────────────────────────

        # ── P006: Eleanor Hayes — CAP + COPD exacerbation, Gen Medicine Day 4 ─
        adm006 = now - timedelta(days=4)
        self.patients["P006"] = {
            "resourceType": "Patient", "id": "P006",
            "name": [{"family": "Hayes", "given": ["Eleanor"]}],
            "gender": "female", "birthDate": "1952-08-22",
            "address": [{"city": "Boston", "state": "MA"}],
            "encounter_type": "inpatient", "hospital_id": "GENERAL",
            "admission_date": adm006.isoformat(),
            "ward": "General Medicine", "bed": "MED-15",
            "code_status": "Full Code", "attending": "Dr. Patricia Wu",
        }
        self.conditions["P006"] = [
            {"resourceType": "Condition", "id": "C060", "subject": {"reference": "Patient/P006"},
             "code": {"coding": [{"display": "Community-acquired pneumonia (right lower lobe)"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": adm006.isoformat()},
            {"resourceType": "Condition", "id": "C061", "subject": {"reference": "Patient/P006"},
             "code": {"coding": [{"display": "COPD, GOLD Stage III (severe)"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": "2018-03-10"},
            {"resourceType": "Condition", "id": "C062", "subject": {"reference": "Patient/P006"},
             "code": {"coding": [{"display": "Persistent atrial fibrillation"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": "2021-07-05"},
            {"resourceType": "Condition", "id": "C063", "subject": {"reference": "Patient/P006"},
             "code": {"coding": [{"display": "Osteoporosis"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": "2019-11-20"},
        ]
        self.medications["P006"] = [
            {"resourceType": "MedicationStatement", "id": "M060", "subject": {"reference": "Patient/P006"},
             "medicationCodeableConcept": {"coding": [{"display": "Ceftriaxone 1g IV every 24h"}]},
             "status": "active", "dosage": [{"text": "1g IV q24h × 5 days (Day 4 of 5)"}]},
            {"resourceType": "MedicationStatement", "id": "M061", "subject": {"reference": "Patient/P006"},
             "medicationCodeableConcept": {"coding": [{"display": "Azithromycin 500mg IV transitioning oral"}]},
             "status": "active", "dosage": [{"text": "500mg IV QD → PO switch planned today"}]},
            {"resourceType": "MedicationStatement", "id": "M062", "subject": {"reference": "Patient/P006"},
             "medicationCodeableConcept": {"coding": [{"display": "Albuterol 2.5mg nebulization"}]},
             "status": "active", "dosage": [{"text": "2.5mg NEB q4–6h PRN bronchospasm"}]},
            {"resourceType": "MedicationStatement", "id": "M063", "subject": {"reference": "Patient/P006"},
             "medicationCodeableConcept": {"coding": [{"display": "Ipratropium 0.5mg nebulization"}]},
             "status": "active", "dosage": [{"text": "0.5mg NEB q6h"}]},
            {"resourceType": "MedicationStatement", "id": "M064", "subject": {"reference": "Patient/P006"},
             "medicationCodeableConcept": {"coding": [{"display": "Prednisone 40mg oral"}]},
             "status": "active", "dosage": [{"text": "40mg PO QD (COPD exacerbation, Day 4 of 5)"}]},
            {"resourceType": "MedicationStatement", "id": "M065", "subject": {"reference": "Patient/P006"},
             "medicationCodeableConcept": {"coding": [{"display": "Apixaban 5mg oral twice daily"}]},
             "status": "active", "dosage": [{"text": "5mg PO BID (AF anticoagulation)"}]},
        ]
        self.allergies["P006"] = [
            {"resourceType": "AllergyIntolerance", "id": "A060",
             "patient": {"reference": "Patient/P006"},
             "code": {"coding": [{"display": "Clindamycin"}]},
             "reaction": [{"manifestation": [{"coding": [{"display": "C. difficile colitis (historical)"}]}],
                           "severity": "moderate"}]},
        ]
        self.observations["P006"] = [
            {"resourceType": "Observation", "id": "O060", "subject": {"reference": "Patient/P006"},
             "code": {"coding": [{"display": "SpO2"}]},
             "valueQuantity": {"value": "92→93→95", "unit": "%"},
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O061", "subject": {"reference": "Patient/P006"},
             "code": {"coding": [{"display": "Respiratory Rate"}]},
             "valueQuantity": {"value": 18, "unit": "breaths/min"},
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O062", "subject": {"reference": "Patient/P006"},
             "code": {"coding": [{"display": "Temperature"}]},
             "valueQuantity": {"value": 37.4, "unit": "°C"},
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O063", "subject": {"reference": "Patient/P006"},
             "code": {"coding": [{"display": "Heart Rate (irregular)"}]},
             "valueQuantity": {"value": 82, "unit": "bpm"},
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O064", "subject": {"reference": "Patient/P006"},
             "code": {"coding": [{"display": "WBC"}]},
             "valueQuantity": {"value": "16.8→14.2→11.4", "unit": "K/μL"},
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O065", "subject": {"reference": "Patient/P006"},
             "code": {"coding": [{"display": "CRP"}]},
             "valueQuantity": {"value": 142, "unit": "mg/L"},
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O066", "subject": {"reference": "Patient/P006"},
             "code": {"coding": [{"display": "Sputum Culture"}]},
             "valueString": "Streptococcus pneumoniae — susceptible to penicillin",
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O067", "subject": {"reference": "Patient/P006"},
             "code": {"coding": [{"display": "CXR"}]},
             "valueString": "Day 1: RLL consolidation with air bronchograms. Day 4: improving consolidation, no effusion.",
             "effectiveDateTime": now.isoformat()},
        ]
        self.images["P006"] = [
            {"url": "/static/images/chest_xray_pneumonia.jpg",
             "modality": "xray",
             "timestamp": adm006.isoformat(),
             "analysis": "Right lower lobe consolidation with air bronchograms consistent with bacterial pneumonia. "
                         "No pleural effusion. Hyperinflation with flattened diaphragms and increased AP diameter "
                         "consistent with underlying COPD. No pneumothorax."},
        ]
        self.active_orders["P006"] = [
            {"order_id": "ORD-P006-01", "type": "medication", "name": "Ceftriaxone 1g IV q24h",
             "ordered_at": adm006.isoformat(), "status": "active"},
            {"order_id": "ORD-P006-02", "type": "medication", "name": "Azithromycin → switch to PO today",
             "ordered_at": adm006.isoformat(), "status": "active"},
            {"order_id": "ORD-P006-03", "type": "therapy", "name": "Respiratory therapy NEB + CPT BID",
             "ordered_at": adm006.isoformat(), "status": "active"},
            {"order_id": "ORD-P006-04", "type": "monitoring", "name": "O2 titrate SpO2 ≥ 92%",
             "ordered_at": adm006.isoformat(), "status": "active"},
            {"order_id": "ORD-P006-05", "type": "lab", "name": "BMP + CBC daily",
             "ordered_at": adm006.isoformat(), "status": "active"},
            {"order_id": "ORD-P006-06", "type": "prophylaxis", "name": "Enoxaparin 40mg SQ QD (VTE)",
             "ordered_at": adm006.isoformat(), "status": "active"},
            {"order_id": "ORD-P006-07", "type": "consult", "name": "PT/OT mobility assessment",
             "ordered_at": (adm006 + timedelta(days=2)).isoformat(), "status": "pending"},
        ]
        self.progress_notes["P006"] = [
            {"note_id": "PN-P006-01", "author": "Dr. Patricia Wu", "role": "attending",
             "created_at": adm006.isoformat(),
             "note_text": "ADMISSION NOTE\nCC: Productive cough × 5 days, fever to 38.9°C, increased dyspnea.\n"
                          "HPI: 72F with COPD GOLD III and AF presenting with 5-day worsening productive cough "
                          "(yellow-green sputum), subjective fever, and progressive dyspnea on exertion now at rest.\n"
                          "A/P: CAP superimposed on COPD exacerbation. Starting ceftriaxone + azithromycin per CAP guidelines. "
                          "Bronchodilators, prednisone 40mg × 5 days. Continue apixaban for AF. Monitor O2 saturation."},
            {"note_id": "PN-P006-02", "author": "Dr. James Lee", "role": "resident",
             "created_at": (adm006 + timedelta(days=2)).isoformat(),
             "note_text": "DAY 2 PROGRESS NOTE\nS: Patient reports improved dyspnea, still productive cough. Afebrile overnight.\n"
                          "O: T 37.6, HR 80 (AF), RR 20, SpO2 93% on 2L NC. Lungs: decreased crackles RLL.\n"
                          "Labs: WBC 14.2 (↓ from 16.8). CXR: slight improvement in consolidation.\n"
                          "A: CAP improving on antibiotics. COPD exacerbation improving with bronchodilators + steroids.\n"
                          "P: Continue current regimen. Reassess O2 requirements. Encourage ambulation."},
            {"note_id": "PN-P006-03", "author": "Dr. Patricia Wu", "role": "attending",
             "created_at": (now - timedelta(hours=6)).isoformat(),
             "note_text": "DAY 4 AM ROUNDS\nS: Feels much better, appetite returning. Requesting to go home.\n"
                          "O: T 37.4 (afebrile × 48h), HR 82 (AF-controlled), RR 18, SpO2 95% on 1L NC (was 2L).\n"
                          "WBC 11.4 (trending down). Sputum: S. pneumoniae susceptible.\n"
                          "A/P: CAP resolving — completing Day 5 antibiotics tomorrow. COPD improving. "
                          "Plan: Switch azithromycin to PO today. Discharge planning: complete antibiotic course at home (oral), "
                          "arrange COPD follow-up in 1 week, outpatient pulmonology in 4 weeks. Ensure influenza + pneumococcal vaccines given before discharge."},
        ]

        # ── P007: Derrick Yates — Acute ischemic stroke, Neurology Day 2 ─────
        adm007 = now - timedelta(hours=42)
        self.patients["P007"] = {
            "resourceType": "Patient", "id": "P007",
            "name": [{"family": "Yates", "given": ["Derrick"]}],
            "gender": "male", "birthDate": "1963-02-14",
            "address": [{"city": "Philadelphia", "state": "PA"}],
            "encounter_type": "inpatient", "hospital_id": "ACADEMIC",
            "admission_date": adm007.isoformat(),
            "ward": "Neurology", "bed": "NEURO-03",
            "code_status": "Full Code", "attending": "Dr. Richard Huang",
        }
        self.conditions["P007"] = [
            {"resourceType": "Condition", "id": "C070", "subject": {"reference": "Patient/P007"},
             "code": {"coding": [{"display": "Acute ischemic stroke — left MCA territory (NIHSS 4)"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": adm007.isoformat()},
            {"resourceType": "Condition", "id": "C071", "subject": {"reference": "Patient/P007"},
             "code": {"coding": [{"display": "Atrial fibrillation — newly diagnosed"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": adm007.isoformat()},
            {"resourceType": "Condition", "id": "C072", "subject": {"reference": "Patient/P007"},
             "code": {"coding": [{"display": "Hypertension"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": "2015-06-12"},
            {"resourceType": "Condition", "id": "C073", "subject": {"reference": "Patient/P007"},
             "code": {"coding": [{"display": "Hyperlipidemia"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": "2017-09-30"},
        ]
        self.medications["P007"] = [
            {"resourceType": "MedicationStatement", "id": "M070", "subject": {"reference": "Patient/P007"},
             "medicationCodeableConcept": {"coding": [{"display": "Aspirin 325mg oral (post-tPA 24h → 81mg QD)"}]},
             "status": "active", "dosage": [{"text": "325mg PO QD Loading day 1, then 81mg QD"}]},
            {"resourceType": "MedicationStatement", "id": "M071", "subject": {"reference": "Patient/P007"},
             "medicationCodeableConcept": {"coding": [{"display": "Atorvastatin 80mg oral nightly"}]},
             "status": "active", "dosage": [{"text": "80mg PO QHS (high-intensity statin)"}]},
            {"resourceType": "MedicationStatement", "id": "M072", "subject": {"reference": "Patient/P007"},
             "medicationCodeableConcept": {"coding": [{"display": "Lisinopril 5mg oral — HELD (BP management)"}]},
             "status": "on-hold", "dosage": [{"text": "5mg PO QD — held, target BP <180/105 first 24h post-tPA"}]},
            {"resourceType": "MedicationStatement", "id": "M073", "subject": {"reference": "Patient/P007"},
             "medicationCodeableConcept": {"coding": [{"display": "Enoxaparin 40mg SQ — VTE prophylaxis"}]},
             "status": "active", "dosage": [{"text": "40mg SQ QD (start 24h post-tPA)"}]},
        ]
        self.allergies["P007"] = [
            {"resourceType": "AllergyIntolerance", "id": "A070",
             "patient": {"reference": "Patient/P007"},
             "code": {"coding": [{"display": "No known drug allergies"}]},
             "reaction": [{"manifestation": [{"coding": [{"display": "NKDA"}]}]}]},
        ]
        self.observations["P007"] = [
            {"resourceType": "Observation", "id": "O070", "subject": {"reference": "Patient/P007"},
             "code": {"coding": [{"display": "Blood Pressure"}]},
             "valueQuantity": {"value": "178/96→162/88→154/82", "unit": "mmHg"},
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O071", "subject": {"reference": "Patient/P007"},
             "code": {"coding": [{"display": "NIHSS Score"}]},
             "valueQuantity": {"value": "6→4 (mild, improving)", "unit": "points"},
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O072", "subject": {"reference": "Patient/P007"},
             "code": {"coding": [{"display": "MRI Brain — DWI/ADC"}]},
             "valueString": "Acute infarction in left MCA territory (insular cortex + inferior frontal gyrus). "
                            "No hemorrhagic transformation. No midline shift.",
             "effectiveDateTime": adm007.isoformat()},
            {"resourceType": "Observation", "id": "O073", "subject": {"reference": "Patient/P007"},
             "code": {"coding": [{"display": "Cardiac Monitor — Rhythm"}]},
             "valueString": "Paroxysmal atrial fibrillation confirmed. Ventricular rate 78 bpm.",
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O074", "subject": {"reference": "Patient/P007"},
             "code": {"coding": [{"display": "Echocardiogram — TEE"}]},
             "valueString": "EF 60%. No left atrial thrombus. LAE present. No significant valvular disease.",
             "effectiveDateTime": (adm007 + timedelta(hours=18)).isoformat()},
            {"resourceType": "Observation", "id": "O075", "subject": {"reference": "Patient/P007"},
             "code": {"coding": [{"display": "LDL Cholesterol"}]},
             "valueQuantity": {"value": 182, "unit": "mg/dL"},
             "effectiveDateTime": adm007.isoformat()},
            {"resourceType": "Observation", "id": "O076", "subject": {"reference": "Patient/P007"},
             "code": {"coding": [{"display": "Neuro Exam"}]},
             "valueString": "Right facial droop (mild). Right arm drift grade 4/5. Mild dysarthria. "
                            "Comprehension intact. No neglect.",
             "effectiveDateTime": now.isoformat()},
        ]
        self.active_orders["P007"] = [
            {"order_id": "ORD-P007-01", "type": "monitoring", "name": "Continuous cardiac telemetry + neuro checks q4h",
             "ordered_at": adm007.isoformat(), "status": "active"},
            {"order_id": "ORD-P007-02", "type": "consult", "name": "PT / OT / SLP consults",
             "ordered_at": adm007.isoformat(), "status": "active"},
            {"order_id": "ORD-P007-03", "type": "imaging", "name": "MRI brain + MRA (repeat Day 4)",
             "ordered_at": adm007.isoformat(), "status": "pending"},
            {"order_id": "ORD-P007-04", "type": "lab", "name": "Hypercoagulable panel (anticardiolipin, lupus AC)",
             "ordered_at": (adm007 + timedelta(hours=12)).isoformat(), "status": "pending"},
            {"order_id": "ORD-P007-05", "type": "medication", "name": "Apixaban 5mg BID — START in 2 weeks (AF anticoagulation)",
             "ordered_at": adm007.isoformat(), "status": "pending"},
        ]
        self.progress_notes["P007"] = [
            {"note_id": "PN-P007-01", "author": "Dr. Richard Huang", "role": "attending",
             "created_at": adm007.isoformat(),
             "note_text": "NEUROLOGY ADMIT NOTE\n61M presents with acute-onset right-sided facial droop and arm weakness "
                          "noted 90 min prior to arrival. Last known well 2.5h before ED arrival. NIHSS 6 on arrival.\n"
                          "IV tPA administered (0.9mg/kg) at 08:42 without complication. Patient transferred to "
                          "neurology stroke unit. No hemorrhage on NCCT. MRI confirms L MCA territory infarct.\n"
                          "ETIOLOGY: Likely cardioembolic — new AF identified on telemetry. No carotid stenosis >50% on CTA.\n"
                          "PLAN: ASA 325mg × 24h then 81mg. High-intensity statin. Hold lisinopril × 24h. "
                          "Anticoagulate for AF in 2–4 weeks (haemorrhagic transformation risk). PT/OT/SLP consults."},
            {"note_id": "PN-P007-02", "author": "Dr. Amy Chen", "role": "resident",
             "created_at": (adm007 + timedelta(hours=20)).isoformat(),
             "note_text": "DAY 1 PROGRESS NOTE\nS: Patient more alert, reports right hand 'clumsy', mild slurred speech. No headache.\n"
                          "O: BP 162/88, HR 78 (AF). NIHSS 5. Right facial droop improving, arm drift 4+/5. "
                          "Gait: not yet tested (OT evaluating AM).\n"
                          "A/P: Post-tPA stroke Day 1 — neurologically stable, mild improvement. "
                          "No hemorrhagic transformation on AM CT. VTE prophylaxis started (24h post-tPA). "
                          "Dysphagia screen: minimal aspiration risk per SLP — soft diet initiated."},
            {"note_id": "PN-P007-03", "author": "Dr. Richard Huang", "role": "attending",
             "created_at": (now - timedelta(hours=4)).isoformat(),
             "note_text": "DAY 2 ROUNDS — STROKE TEAM\nNIHSS 4 (improving × 2 days). BP 154/82 — allowing permissive "
                          "hypertension for now (target <180/105 until Day 7). AF confirmed — discuss anticoagulation "
                          "timing with patient: plan apixaban at 2 weeks IF no hemorrhagic transformation. "
                          "TEE: no LAA thrombus. SLP: tolerating pureed diet. Repeat MRI Day 4 for infarct evolution. "
                          "Rehab candidacy: recommend inpatient rehabilitation facility given deficits."},
        ]

        # ─────────────────────────────────────────────────────────────────────
        # SHIFT BRIEF PATIENTS (ICU / critical care handover)
        # ─────────────────────────────────────────────────────────────────────

        # ── P008: Nalini Krishnan — Perforated peptic ulcer, post-op 10h, SICU ─
        adm008 = now - timedelta(hours=10)
        self.patients["P008"] = {
            "resourceType": "Patient", "id": "P008",
            "name": [{"family": "Krishnan", "given": ["Nalini"]}],
            "gender": "female", "birthDate": "1990-05-30",
            "address": [{"city": "Houston", "state": "TX"}],
            "encounter_type": "inpatient", "hospital_id": "ACADEMIC",
            "admission_date": adm008.isoformat(),
            "ward": "Surgical ICU", "bed": "SICU-02",
            "code_status": "Full Code", "attending": "Dr. James Fortier",
        }
        self.conditions["P008"] = [
            {"resourceType": "Condition", "id": "C080", "subject": {"reference": "Patient/P008"},
             "code": {"coding": [{"display": "Perforated peptic ulcer (H. pylori confirmed) — post emergency laparotomy + Graham patch"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (adm008 - timedelta(hours=3)).isoformat()},
            {"resourceType": "Condition", "id": "C081", "subject": {"reference": "Patient/P008"},
             "code": {"coding": [{"display": "Septic shock — abdominal source"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": adm008.isoformat()},
            {"resourceType": "Condition", "id": "C082", "subject": {"reference": "Patient/P008"},
             "code": {"coding": [{"display": "Acute hypoxic respiratory failure — intubated on ventilator"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (adm008 - timedelta(hours=1)).isoformat()},
        ]
        self.medications["P008"] = [
            {"resourceType": "MedicationStatement", "id": "M080", "subject": {"reference": "Patient/P008"},
             "medicationCodeableConcept": {"coding": [{"display": "Piperacillin-tazobactam 3.375g IV q6h"}]},
             "status": "active", "dosage": [{"text": "3.375g IV q6h (septic shock dose)"}]},
            {"resourceType": "MedicationStatement", "id": "M081", "subject": {"reference": "Patient/P008"},
             "medicationCodeableConcept": {"coding": [{"display": "Metronidazole 500mg IV q8h"}]},
             "status": "active", "dosage": [{"text": "500mg IV q8h (anaerobic coverage)"}]},
            {"resourceType": "MedicationStatement", "id": "M082", "subject": {"reference": "Patient/P008"},
             "medicationCodeableConcept": {"coding": [{"display": "Norepinephrine infusion 0.12 mcg/kg/min"}]},
             "status": "active", "dosage": [{"text": "Titrate MAP ≥ 65 mmHg"}]},
            {"resourceType": "MedicationStatement", "id": "M083", "subject": {"reference": "Patient/P008"},
             "medicationCodeableConcept": {"coding": [{"display": "Propofol 20 mcg/kg/min + Fentanyl 25 mcg/h"}]},
             "status": "active", "dosage": [{"text": "Sedation/analgesia — RASS target -2"}]},
            {"resourceType": "MedicationStatement", "id": "M084", "subject": {"reference": "Patient/P008"},
             "medicationCodeableConcept": {"coding": [{"display": "Pantoprazole 40mg IV BID"}]},
             "status": "active", "dosage": [{"text": "40mg IV BID (stress ulcer prophylaxis + PUD treatment)"}]},
        ]
        self.allergies["P008"] = [
            {"resourceType": "AllergyIntolerance", "id": "A080",
             "patient": {"reference": "Patient/P008"},
             "code": {"coding": [{"display": "Ibuprofen / NSAIDs"}]},
             "reaction": [{"manifestation": [{"coding": [{"display": "GI bleed — RELEVANT to admission"}]}],
                           "severity": "severe"}]},
        ]
        self.observations["P008"] = [
            {"resourceType": "Observation", "id": "O080", "subject": {"reference": "Patient/P008"},
             "code": {"coding": [{"display": "Blood Pressure / MAP"}]},
             "valueQuantity": {"value": "88/54 MAP 66 (on vasopressors)", "unit": "mmHg"},
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O081", "subject": {"reference": "Patient/P008"},
             "code": {"coding": [{"display": "Heart Rate"}]},
             "valueQuantity": {"value": 112, "unit": "bpm"},
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O082", "subject": {"reference": "Patient/P008"},
             "code": {"coding": [{"display": "Temperature"}]},
             "valueQuantity": {"value": 38.7, "unit": "°C"},
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O083", "subject": {"reference": "Patient/P008"},
             "code": {"coding": [{"display": "Ventilator Settings"}]},
             "valueString": "AC/VC: TV 420mL (6mL/kg IBW), RR 18, FiO2 0.50, PEEP 8. Ppeak 28, Pplat 22.",
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O084", "subject": {"reference": "Patient/P008"},
             "code": {"coding": [{"display": "Lactate trend"}]},
             "valueQuantity": {"value": "4.1→2.8 (clearing)", "unit": "mmol/L"},
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O085", "subject": {"reference": "Patient/P008"},
             "code": {"coding": [{"display": "Urine Output"}]},
             "valueQuantity": {"value": 28, "unit": "mL/hr"},
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O086", "subject": {"reference": "Patient/P008"},
             "code": {"coding": [{"display": "Hemoglobin / Hematocrit"}]},
             "valueQuantity": {"value": "8.4 / 26%", "unit": "g/dL / %"},
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O087", "subject": {"reference": "Patient/P008"},
             "code": {"coding": [{"display": "Creatinine"}]},
             "valueQuantity": {"value": 1.8, "unit": "mg/dL"},
             "effectiveDateTime": now.isoformat()},
        ]
        self.images["P008"] = [
            {"url": "/static/images/mock_chest_xray.jpg",
             "modality": "xray",
             "timestamp": (adm008 - timedelta(hours=8)).isoformat(),
             "analysis": "Post-intubation CXR. ETT tip at 3cm above carina — well-positioned. "
                         "Bilateral lung fields clear. NG tube in stomach. No pneumothorax. "
                         "Mild cardiomegaly. No free air under diaphragm visible (operative site)."},
        ]
        self.active_orders["P008"] = [
            {"order_id": "ORD-P008-01", "type": "ventilator", "name": "AC/VC: TV 420, RR 18, FiO2 0.50, PEEP 8 — wean as tolerated",
             "ordered_at": adm008.isoformat(), "status": "active"},
            {"order_id": "ORD-P008-02", "type": "medication", "name": "Norepinephrine — titrate MAP ≥65, wean when able",
             "ordered_at": adm008.isoformat(), "status": "active"},
            {"order_id": "ORD-P008-03", "type": "device", "name": "Arterial line (R radial), CVC (R IJ), Foley catheter",
             "ordered_at": adm008.isoformat(), "inserted_at": adm008.isoformat(), "status": "active"},
            {"order_id": "ORD-P008-04", "type": "lab", "name": "ABG q4h, BMP + lactate q6h, CBC q12h",
             "ordered_at": adm008.isoformat(), "status": "active"},
            {"order_id": "ORD-P008-05", "type": "monitoring", "name": "Continuous hemodynamic monitoring, RASS q1h",
             "ordered_at": adm008.isoformat(), "status": "active"},
            {"order_id": "ORD-P008-06", "type": "prophylaxis", "name": "Heparin 5000u SQ BID (VTE — wound not a contraindication)",
             "ordered_at": adm008.isoformat(), "status": "active"},
        ]
        self.progress_notes["P008"] = [
            {"note_id": "PN-P008-01", "author": "Dr. James Fortier", "role": "attending",
             "created_at": adm008.isoformat(),
             "note_text": "OPERATIVE/ICU ADMISSION NOTE — SHIFT BRIEF (SBAR)\n"
                          "SITUATION: 34F post emergency Graham patch repair of perforated duodenal ulcer. Arrived SICU 10h ago. "
                          "Currently intubated/ventilated, on vasopressors.\n"
                          "BACKGROUND: NSAID allergy (GI bleed history). H. pylori confirmed on rapid urease test intraop. "
                          "Presented with acute abdomen, free air on CXR, BP 88/54 at triage. Taken emergently to OR.\n"
                          "ASSESSMENT: Septic shock improving — lactate clearing 4.1→2.8. MAP 66 on NE 0.12. "
                          "Ventilator: AC/VC, lung-protective, FiO2 weaning. Hgb 8.4 — transfusion threshold 7.0 (no active bleed).\n"
                          "PLAN/HANDOFF: Goal MAP ≥65 — wean vasopressors if stable. Wean FiO2 target SpO2 ≥94%. "
                          "UO 28mL/hr — cautious fluids (avoid overresuscitation). Serial lactates q6h. "
                          "CONCERNS: Possible NSAID-induced ulcer (ALLERGY — NO NSAIDs). If desaturates — suspect ARDS. "
                          "If pressors escalating — re-examine abdomen for anastomotic leak."},
            {"note_id": "PN-P008-02", "author": "RN Amanda Torres", "role": "nurse",
             "created_at": (now - timedelta(hours=2)).isoformat(),
             "note_text": "NURSING SHIFT BRIEF (Incoming Night Team)\n"
                          "Patient: Nalini K, SICU-02 — post-op 10h ruptured PUD + septic shock\n"
                          "Lines: A-line R radial (good waveform), R IJ CVC (3 lumens), Foley\n"
                          "Current drips: NE 0.12 mcg/kg/min, Propofol 20 mcg/kg/min, Fentanyl 25 mcg/h\n"
                          "Vent: AC/VC, TV 420, RR 18, PEEP 8, FiO2 50% — SpO2 97%\n"
                          "I/O last 8h: IN 2,200mL / OUT 320mL urine (Foley) + 180mL surgical drain\n"
                          "RASS: -2 (appropriate). Family notified and at bedside.\n"
                          "ISSUES TO WATCH: UO marginal (28mL/hr) — notify MD if <20mL/hr × 2h. "
                          "NE titrating — last increase 1h ago for MAP 62. Next lactate due in 4h."},
        ]

        # ── P009: Brett Callahan — NSTEMI, CCU, awaiting cath ────────────────
        adm009 = now - timedelta(hours=18)
        self.patients["P009"] = {
            "resourceType": "Patient", "id": "P009",
            "name": [{"family": "Callahan", "given": ["Brett"]}],
            "gender": "male", "birthDate": "1969-11-03",
            "address": [{"city": "Phoenix", "state": "AZ"}],
            "encounter_type": "inpatient", "hospital_id": "COMMUNITY",
            "admission_date": adm009.isoformat(),
            "ward": "Coronary Care Unit", "bed": "CCU-05",
            "code_status": "Full Code", "attending": "Dr. Karen Patel",
        }
        self.conditions["P009"] = [
            {"resourceType": "Condition", "id": "C090", "subject": {"reference": "Patient/P009"},
             "code": {"coding": [{"display": "NSTEMI — lateral ST depression + troponin elevation"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": adm009.isoformat()},
            {"resourceType": "Condition", "id": "C091", "subject": {"reference": "Patient/P009"},
             "code": {"coding": [{"display": "Hypertension"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": "2014-04-20"},
            {"resourceType": "Condition", "id": "C092", "subject": {"reference": "Patient/P009"},
             "code": {"coding": [{"display": "Dyslipidemia"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": "2016-08-15"},
            {"resourceType": "Condition", "id": "C093", "subject": {"reference": "Patient/P009"},
             "code": {"coding": [{"display": "Active tobacco use — 1 PPD × 30 years"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": "1993-01-01"},
        ]
        self.medications["P009"] = [
            {"resourceType": "MedicationStatement", "id": "M090", "subject": {"reference": "Patient/P009"},
             "medicationCodeableConcept": {"coding": [{"display": "Aspirin 325mg load → 81mg QD"}]},
             "status": "active", "dosage": [{"text": "Loading 325mg, then 81mg QD indefinitely"}]},
            {"resourceType": "MedicationStatement", "id": "M091", "subject": {"reference": "Patient/P009"},
             "medicationCodeableConcept": {"coding": [{"display": "Ticagrelor 180mg loading → 90mg BID"}]},
             "status": "active", "dosage": [{"text": "DAPT — loading dose given, maintenance 90mg BID"}]},
            {"resourceType": "MedicationStatement", "id": "M092", "subject": {"reference": "Patient/P009"},
             "medicationCodeableConcept": {"coding": [{"display": "Heparin infusion weight-based protocol"}]},
             "status": "active", "dosage": [{"text": "Continuous IV heparin — target aPTT 60–100s"}]},
            {"resourceType": "MedicationStatement", "id": "M093", "subject": {"reference": "Patient/P009"},
             "medicationCodeableConcept": {"coding": [{"display": "Atorvastatin 80mg oral nightly"}]},
             "status": "active", "dosage": [{"text": "80mg PO QHS (high-intensity)"}]},
            {"resourceType": "MedicationStatement", "id": "M094", "subject": {"reference": "Patient/P009"},
             "medicationCodeableConcept": {"coding": [{"display": "Metoprolol succinate 25mg BID"}]},
             "status": "active", "dosage": [{"text": "25mg PO BID (target HR <70, BP <130/80)"}]},
        ]
        self.allergies["P009"] = [
            {"resourceType": "AllergyIntolerance", "id": "A090",
             "patient": {"reference": "Patient/P009"},
             "code": {"coding": [{"display": "Clopidogrel"}]},
             "reaction": [{"manifestation": [{"coding": [{"display": "Excessive bruising — mild"}]}],
                           "severity": "mild"}]},
        ]
        self.observations["P009"] = [
            {"resourceType": "Observation", "id": "O090", "subject": {"reference": "Patient/P009"},
             "code": {"coding": [{"display": "Blood Pressure"}]},
             "valueQuantity": {"value": 138, "unit": "mmHg systolic"},
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O091", "subject": {"reference": "Patient/P009"},
             "code": {"coding": [{"display": "Heart Rate"}]},
             "valueQuantity": {"value": 72, "unit": "bpm"},
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O092", "subject": {"reference": "Patient/P009"},
             "code": {"coding": [{"display": "Troponin I trend"}]},
             "valueQuantity": {"value": "4.2→8.7→12.1 (trending up)", "unit": "ng/mL"},
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O093", "subject": {"reference": "Patient/P009"},
             "code": {"coding": [{"display": "ECG"}]},
             "valueString": "Sinus rhythm. ST depression 1–2mm leads V4–V6, I, aVL. Lateral T-wave inversions. "
                            "No STEMI criteria. No Q waves.",
             "effectiveDateTime": adm009.isoformat()},
            {"resourceType": "Observation", "id": "O094", "subject": {"reference": "Patient/P009"},
             "code": {"coding": [{"display": "Echocardiogram (bedside)"}]},
             "valueString": "EF 45% (mildly reduced). Anteroseptal wall hypokinesis. No pericardial effusion.",
             "effectiveDateTime": (adm009 + timedelta(hours=4)).isoformat()},
            {"resourceType": "Observation", "id": "O095", "subject": {"reference": "Patient/P009"},
             "code": {"coding": [{"display": "LDL / Total Cholesterol"}]},
             "valueQuantity": {"value": "LDL 198 / Total 272", "unit": "mg/dL"},
             "effectiveDateTime": adm009.isoformat()},
        ]
        self.active_orders["P009"] = [
            {"order_id": "ORD-P009-01", "type": "procedure", "name": "Cardiac catheterization — SCHEDULED 07:30 TOMORROW (AM list #2)",
             "ordered_at": adm009.isoformat(), "status": "pending"},
            {"order_id": "ORD-P009-02", "type": "monitoring", "name": "Continuous telemetry, serial ECG q6h, troponin q6h",
             "ordered_at": adm009.isoformat(), "status": "active"},
            {"order_id": "ORD-P009-03", "type": "medication", "name": "Heparin IV infusion — check aPTT in 6h",
             "ordered_at": adm009.isoformat(), "status": "active"},
            {"order_id": "ORD-P009-04", "type": "diet", "name": "NPO after midnight (pre-cath)",
             "ordered_at": (now - timedelta(hours=1)).isoformat(), "status": "active"},
            {"order_id": "ORD-P009-05", "type": "prophylaxis", "name": "Enoxaparin 40mg SQ QD (VTE — holding after midnight for cath)",
             "ordered_at": adm009.isoformat(), "status": "active"},
        ]
        self.progress_notes["P009"] = [
            {"note_id": "PN-P009-01", "author": "Dr. Karen Patel", "role": "attending",
             "created_at": adm009.isoformat(),
             "note_text": "CARDIOLOGY ADMIT H&P\n55M presenting with 3h chest pressure radiating to left arm, diaphoresis. "
                          "1 PPD smoker × 30y. Father deceased MI age 52. BP 158/92 on presentation.\n"
                          "ECG: lateral ST depression + T-wave inversions V4-V6, I, aVL. Troponin I 4.2 rising.\n"
                          "Dx: NSTEMI — lateral wall ischemia. HEART score 8 (HIGH RISK).\n"
                          "Plan: Admit CCU. DAPT (aspirin + ticagrelor — NOT clopidogrel per allergy). "
                          "Heparin drip. High-intensity statin. Beta-blocker. Cardiology cath in <24h. "
                          "Echo bedside ordered."},
            {"note_id": "PN-P009-02", "author": "Dr. David Park", "role": "fellow",
             "created_at": (now - timedelta(hours=3)).isoformat(),
             "note_text": "SHIFT BRIEF — CCU HANDOFF (OUTGOING DAYS → INCOMING NIGHTS)\n"
                          "SITUATION: Brett C, 55M, NSTEMI — cath scheduled 07:30 TOMORROW.\n"
                          "BACKGROUND: DAPT + heparin on board. Echo: EF 45%, anteroseptal hypokinesis. Troponin still rising (12.1).\n"
                          "ASSESSMENT: Hemodynamically stable. HR 72, BP 138/84. On 2L NC SpO2 99%. No recurrent chest pain × 6h.\n"
                          "PLAN: NPO after midnight. Continue heparin (check aPTT at 00:00). Repeat ECG + troponin at 01:00.\n"
                          "CONCERNS: If develops recurrent CP, ST changes, or hemodynamic instability → CALL CATH LAB for emergency PCI. "
                          "Watch: heparin supratherapeutic (last aPTT 112 — reduced infusion by 10%). "
                          "Note: CLOPIDOGREL IS CONTRAINDICATED (allergy) — patient on ticagrelor."},
        ]

        # ─────────────────────────────────────────────────────────────────────
        # ENCOUNTER PATIENTS (outpatient / ED / new referral)
        # ─────────────────────────────────────────────────────────────────────

        # ── P010: Sofia Reyes — Probable SLE, ED encounter (Rare Disease / Council) ─
        self.patients["P010"] = {
            "resourceType": "Patient", "id": "P010",
            "name": [{"family": "Reyes", "given": ["Sofia"]}],
            "gender": "female", "birthDate": "1998-04-12",
            "address": [{"city": "San Antonio", "state": "TX"}],
            "encounter_type": "outpatient", "hospital_id": "ACADEMIC",
        }
        self.conditions["P010"] = [
            {"resourceType": "Condition", "id": "C100", "subject": {"reference": "Patient/P010"},
             "code": {"coding": [{"display": "Polyarthritis — bilateral hands, wrists, knees × 3 months (morning stiffness >1h)"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (now - timedelta(days=90)).isoformat()},
            {"resourceType": "Condition", "id": "C101", "subject": {"reference": "Patient/P010"},
             "code": {"coding": [{"display": "Malar rash (butterfly distribution, spares nasolabial folds) × 6 weeks"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (now - timedelta(days=42)).isoformat()},
            {"resourceType": "Condition", "id": "C102", "subject": {"reference": "Patient/P010"},
             "code": {"coding": [{"display": "Pleuritis — pleuritic chest pain, positional × 2 weeks"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (now - timedelta(days=14)).isoformat()},
            {"resourceType": "Condition", "id": "C103", "subject": {"reference": "Patient/P010"},
             "code": {"coding": [{"display": "Oral ulcers — painless, buccal mucosa × recurrent"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (now - timedelta(days=60)).isoformat()},
            {"resourceType": "Condition", "id": "C104", "subject": {"reference": "Patient/P010"},
             "code": {"coding": [{"display": "Photosensitivity — worsening rash with sun exposure"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (now - timedelta(days=60)).isoformat()},
            {"resourceType": "Condition", "id": "C105", "subject": {"reference": "Patient/P010"},
             "code": {"coding": [{"display": "Fatigue — severe, limiting daily activities"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (now - timedelta(days=90)).isoformat()},
        ]
        self.medications["P010"] = [
            {"resourceType": "MedicationStatement", "id": "M100", "subject": {"reference": "Patient/P010"},
             "medicationCodeableConcept": {"coding": [{"display": "Ibuprofen 400mg PRN — minimal relief"}]},
             "status": "active", "dosage": [{"text": "400mg PO PRN q6h (self-prescribed, minimal benefit)"}]},
            {"resourceType": "MedicationStatement", "id": "M101", "subject": {"reference": "Patient/P010"},
             "medicationCodeableConcept": {"coding": [{"display": "Oral contraceptive pill"}]},
             "status": "active", "dosage": [{"text": "Daily"}]},
        ]
        self.allergies["P010"] = [
            {"resourceType": "AllergyIntolerance", "id": "A100",
             "patient": {"reference": "Patient/P010"},
             "code": {"coding": [{"display": "No known drug allergies"}]},
             "reaction": [{"manifestation": [{"coding": [{"display": "NKDA"}]}]}]},
        ]
        self.observations["P010"] = [
            {"resourceType": "Observation", "id": "O100", "subject": {"reference": "Patient/P010"},
             "code": {"coding": [{"display": "Physical Exam — Skin"}]},
             "valueString": "Erythematous malar rash in butterfly distribution, sparing nasolabial folds. "
                            "Painless ulcer (5mm) on right buccal mucosa. No discoid lesions. No alopecia.",
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O101", "subject": {"reference": "Patient/P010"},
             "code": {"coding": [{"display": "Physical Exam — Joints"}]},
             "valueString": "Bilateral synovitis: MCP and PIP joints (2nd, 3rd bilateral), wrists. "
                            "No joint deformity. Knee effusion bilateral (small). "
                            "No Jaccoud arthropathy.",
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O102", "subject": {"reference": "Patient/P010"},
             "code": {"coding": [{"display": "ANA (Antinuclear Antibody)"}]},
             "valueString": "1:640 titer — HIGH POSITIVE (speckled pattern)",
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O103", "subject": {"reference": "Patient/P010"},
             "code": {"coding": [{"display": "Anti-dsDNA"}]},
             "valueString": "Positive — 285 IU/mL (normal <10)",
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O104", "subject": {"reference": "Patient/P010"},
             "code": {"coding": [{"display": "Complement levels"}]},
             "valueString": "C3: 62 mg/dL (↓, normal 90–180). C4: 8 mg/dL (↓↓, normal 16–47). Consistent with complement consumption.",
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O105", "subject": {"reference": "Patient/P010"},
             "code": {"coding": [{"display": "CBC"}]},
             "valueString": "WBC 3.2 K/μL (leukopenia). Hgb 10.8 g/dL (mild anemia). Plt 118 K/μL (thrombocytopenia).",
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O106", "subject": {"reference": "Patient/P010"},
             "code": {"coding": [{"display": "Urinalysis"}]},
             "valueString": "Protein 2+ (trace proteinuria ~0.6g/24h). RBC 4/HPF. "
                            "Granular casts — possible nephritis.",
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O107", "subject": {"reference": "Patient/P010"},
             "code": {"coding": [{"display": "ESR / CRP"}]},
             "valueQuantity": {"value": "ESR 78 / CRP 42", "unit": "mm/hr / mg/L"},
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O108", "subject": {"reference": "Patient/P010"},
             "code": {"coding": [{"display": "Family History"}]},
             "valueString": "Mother: Rheumatoid arthritis. Maternal aunt: hypothyroidism. "
                            "No family history of SLE.",
             "effectiveDateTime": now.isoformat()},
        ]

        # ── P011: Frank Donahue — Progressive dyspnea + clubbing (IPF/ILD, Council) ─
        self.patients["P011"] = {
            "resourceType": "Patient", "id": "P011",
            "name": [{"family": "Donahue", "given": ["Frank"]}],
            "gender": "male", "birthDate": "1957-07-28",
            "address": [{"city": "Portland", "state": "OR"}],
            "encounter_type": "outpatient", "hospital_id": "PULMONOLOGY",
        }
        self.conditions["P011"] = [
            {"resourceType": "Condition", "id": "C110", "subject": {"reference": "Patient/P011"},
             "code": {"coding": [{"display": "Progressive exertional dyspnea × 8 months (MRC Grade 3–4)"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (now - timedelta(days=240)).isoformat()},
            {"resourceType": "Condition", "id": "C111", "subject": {"reference": "Patient/P011"},
             "code": {"coding": [{"display": "Unintentional weight loss — 15 lbs over 6 months"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (now - timedelta(days=180)).isoformat()},
            {"resourceType": "Condition", "id": "C112", "subject": {"reference": "Patient/P011"},
             "code": {"coding": [{"display": "Digital clubbing — bilateral fingernails"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (now - timedelta(days=120)).isoformat()},
            {"resourceType": "Condition", "id": "C113", "subject": {"reference": "Patient/P011"},
             "code": {"coding": [{"display": "Dry cough — non-productive × 6 months"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (now - timedelta(days=180)).isoformat()},
        ]
        self.medications["P011"] = [
            {"resourceType": "MedicationStatement", "id": "M110", "subject": {"reference": "Patient/P011"},
             "medicationCodeableConcept": {"coding": [{"display": "No current medications"}]},
             "status": "active", "dosage": [{"text": "None — first time seeking care for these symptoms"}]},
        ]
        self.allergies["P011"] = [
            {"resourceType": "AllergyIntolerance", "id": "A110",
             "patient": {"reference": "Patient/P011"},
             "code": {"coding": [{"display": "Penicillin"}]},
             "reaction": [{"manifestation": [{"coding": [{"display": "Rash"}]}],
                           "severity": "mild"}]},
        ]
        self.observations["P011"] = [
            {"resourceType": "Observation", "id": "O110", "subject": {"reference": "Patient/P011"},
             "code": {"coding": [{"display": "Physical Exam — Lungs"}]},
             "valueString": "Bilateral basal Velcro-like inspiratory crackles. Digital clubbing bilateral. "
                            "No wheeze, no stridor. RR 22 at rest. SpO2 89% on room air, 94% on 2L NC.",
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O111", "subject": {"reference": "Patient/P011"},
             "code": {"coding": [{"display": "Pulmonary Function Tests (spirometry + DLCO)"}]},
             "valueString": "FVC 62% predicted (↓↓). FEV1/FVC 0.82 (preserved ratio). DLCO 48% predicted (severely reduced). "
                            "Pattern: RESTRICTIVE with impaired gas transfer.",
             "effectiveDateTime": (now - timedelta(days=7)).isoformat()},
            {"resourceType": "Observation", "id": "O112", "subject": {"reference": "Patient/P011"},
             "code": {"coding": [{"display": "Chest X-ray"}]},
             "valueString": "Bilateral lower lobe reticular infiltrates with honeycombing pattern peripherally. "
                            "No pleural effusion. No hilar lymphadenopathy. Lung volumes reduced.",
             "effectiveDateTime": (now - timedelta(days=14)).isoformat()},
            {"resourceType": "Observation", "id": "O113", "subject": {"reference": "Patient/P011"},
             "code": {"coding": [{"display": "6-Minute Walk Test"}]},
             "valueQuantity": {"value": 320, "unit": "meters (↓↓, desaturation to 84% at end)"},
             "effectiveDateTime": (now - timedelta(days=7)).isoformat()},
            {"resourceType": "Observation", "id": "O114", "subject": {"reference": "Patient/P011"},
             "code": {"coding": [{"display": "Occupational & Exposure History"}]},
             "valueString": "Woodworker × 30 years (hardwood dust exposure). Non-smoker. "
                            "Pet birds (2 parakeets) × 8 years. No asbestos exposure. No silica.",
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O115", "subject": {"reference": "Patient/P011"},
             "code": {"coding": [{"display": "Lab Panel"}]},
             "valueString": "LDH 287 U/L (↑). ANA negative. ANCA negative. Anti-CCP negative. "
                            "Hypersensitivity pneumonitis panel: anti-bird precipitins PENDING. "
                            "CBC: normal. BMP: normal.",
             "effectiveDateTime": now.isoformat()},
        ]
        self.images["P011"] = [
            {"url": "/static/images/chest_xray_bilateral_infiltrates.png",
             "modality": "xray",
             "timestamp": (now - timedelta(days=14)).isoformat(),
             "analysis": "Bilateral lower-lobe predominant reticular opacities with peripheral and basal distribution. "
                         "Honeycombing visible in posterior basal segments bilaterally. "
                         "Traction bronchiectasis. No pleural effusion. Lung volume loss. "
                         "Pattern highly suggestive of Usual Interstitial Pneumonia (UIP) / IPF. "
                         "Differential includes fibrotic hypersensitivity pneumonitis or other fibrosing ILD."},
        ]

        # ── P012: Amara Osei — Dermatomyositis (Rare Disease Hunt) ───────────
        self.patients["P012"] = {
            "resourceType": "Patient", "id": "P012",
            "name": [{"family": "Osei", "given": ["Amara"]}],
            "gender": "female", "birthDate": "2002-09-15",
            "address": [{"city": "Atlanta", "state": "GA"}],
            "encounter_type": "outpatient", "hospital_id": "COMMUNITY",
        }
        self.conditions["P012"] = [
            {"resourceType": "Condition", "id": "C120", "subject": {"reference": "Patient/P012"},
             "code": {"coding": [{"display": "Proximal muscle weakness — bilateral, symmetric × 5 months (arms + legs)"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (now - timedelta(days=150)).isoformat()},
            {"resourceType": "Condition", "id": "C121", "subject": {"reference": "Patient/P012"},
             "code": {"coding": [{"display": "Heliotrope rash — periorbital violaceous discoloration"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (now - timedelta(days=120)).isoformat()},
            {"resourceType": "Condition", "id": "C122", "subject": {"reference": "Patient/P012"},
             "code": {"coding": [{"display": "Gottron's papules — violaceous papules over MCP/PIP joints bilaterally"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (now - timedelta(days=100)).isoformat()},
            {"resourceType": "Condition", "id": "C123", "subject": {"reference": "Patient/P012"},
             "code": {"coding": [{"display": "Dysphagia — progressive, solids then liquids × 4 weeks"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (now - timedelta(days=28)).isoformat()},
            {"resourceType": "Condition", "id": "C124", "subject": {"reference": "Patient/P012"},
             "code": {"coding": [{"display": "Photosensitivity — V-sign erythema, shawl sign"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (now - timedelta(days=90)).isoformat()},
        ]
        self.medications["P012"] = [
            {"resourceType": "MedicationStatement", "id": "M120", "subject": {"reference": "Patient/P012"},
             "medicationCodeableConcept": {"coding": [{"display": "No current medications"}]},
             "status": "active", "dosage": [{"text": "None — previously healthy college student"}]},
        ]
        self.allergies["P012"] = [
            {"resourceType": "AllergyIntolerance", "id": "A120",
             "patient": {"reference": "Patient/P012"},
             "code": {"coding": [{"display": "Sulfonamides"}]},
             "reaction": [{"manifestation": [{"coding": [{"display": "Rash"}]}],
                           "severity": "mild"}]},
        ]
        self.observations["P012"] = [
            {"resourceType": "Observation", "id": "O120", "subject": {"reference": "Patient/P012"},
             "code": {"coding": [{"display": "Muscle Strength (Manual Muscle Testing)"}]},
             "valueString": "Shoulder abduction 3/5 bilaterally. Hip flexion 3+/5 bilaterally. "
                            "Cannot rise from chair without arms. Neck flexion 3/5. Distal strength preserved.",
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O121", "subject": {"reference": "Patient/P012"},
             "code": {"coding": [{"display": "CK (Creatine Kinase)"}]},
             "valueQuantity": {"value": 4200, "unit": "U/L (↑↑↑ — normal <170)"},
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O122", "subject": {"reference": "Patient/P012"},
             "code": {"coding": [{"display": "Aldolase / Liver enzymes"}]},
             "valueString": "Aldolase 28 U/L (↑, normal <7.6). AST 78, ALT 82 (muscle-source elevations).",
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O123", "subject": {"reference": "Patient/P012"},
             "code": {"coding": [{"display": "Autoimmune Panel"}]},
             "valueString": "ANA: 1:320 positive (nucleolar pattern). Anti-Jo-1: NEGATIVE. "
                            "Anti-Mi-2: PENDING. Anti-MDA5: PENDING. Anti-TIF1γ: PENDING (malignancy-associated DM screen).",
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O124", "subject": {"reference": "Patient/P012"},
             "code": {"coding": [{"display": "EMG (Electromyography)"}]},
             "valueString": "Abnormal spontaneous activity (fibrillations + positive sharp waves) in proximal muscles. "
                            "Short-duration, low-amplitude motor unit potentials. Pattern: inflammatory myopathy.",
             "effectiveDateTime": (now - timedelta(days=3)).isoformat()},
            {"resourceType": "Observation", "id": "O125", "subject": {"reference": "Patient/P012"},
             "code": {"coding": [{"display": "CXR / Pulmonary screening"}]},
             "valueString": "CXR: mild interstitial changes bilateral lower lobes (ILD screen for anti-synthetase). "
                            "PFTs pending.",
             "effectiveDateTime": now.isoformat()},
        ]

        # ── P013: Ethan Park — McArdle disease / metabolic myopathy (Rare Disease Hunt) ─
        self.patients["P013"] = {
            "resourceType": "Patient", "id": "P013",
            "name": [{"family": "Park", "given": ["Ethan"]}],
            "gender": "male", "birthDate": "2007-03-22",
            "address": [{"city": "Seattle", "state": "WA"}],
            "encounter_type": "outpatient", "hospital_id": "PEDIATRIC",
        }
        self.conditions["P013"] = [
            {"resourceType": "Condition", "id": "C130", "subject": {"reference": "Patient/P013"},
             "code": {"coding": [{"display": "Exercise-induced muscle pain + cramping — onset 5–10 min into sustained exercise"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (now - timedelta(days=730)).isoformat()},
            {"resourceType": "Condition", "id": "C131", "subject": {"reference": "Patient/P013"},
             "code": {"coding": [{"display": "Myoglobinuria — dark cola urine after exertion × 3 episodes (rhabdomyolysis risk)"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (now - timedelta(days=180)).isoformat()},
            {"resourceType": "Condition", "id": "C132", "subject": {"reference": "Patient/P013"},
             "code": {"coding": [{"display": "'Second-wind' phenomenon — improvement after brief rest then resuming exercise"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (now - timedelta(days=730)).isoformat()},
            {"resourceType": "Condition", "id": "C133", "subject": {"reference": "Patient/P013"},
             "code": {"coding": [{"display": "Fixed proximal weakness (mild, emerging)"}]},
             "clinicalStatus": {"coding": [{"code": "active"}]},
             "onsetDateTime": (now - timedelta(days=90)).isoformat()},
        ]
        self.medications["P013"] = [
            {"resourceType": "MedicationStatement", "id": "M130", "subject": {"reference": "Patient/P013"},
             "medicationCodeableConcept": {"coding": [{"display": "No medications — advised exercise restriction"}]},
             "status": "active", "dosage": [{"text": "Activity restriction: avoid sustained isometric exercise"}]},
        ]
        self.allergies["P013"] = [
            {"resourceType": "AllergyIntolerance", "id": "A130",
             "patient": {"reference": "Patient/P013"},
             "code": {"coding": [{"display": "No known drug allergies"}]},
             "reaction": [{"manifestation": [{"coding": [{"display": "NKDA"}]}]}]},
        ]
        self.observations["P013"] = [
            {"resourceType": "Observation", "id": "O130", "subject": {"reference": "Patient/P013"},
             "code": {"coding": [{"display": "CK (Creatine Kinase) — during episode vs baseline"}]},
             "valueQuantity": {"value": "12,400 during episode / 280 baseline", "unit": "U/L"},
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O131", "subject": {"reference": "Patient/P013"},
             "code": {"coding": [{"display": "Ischemic Forearm Exercise Test (modified non-ischemic)"}]},
             "valueString": "Ammonia: normal rise (5× baseline). Lactate: FLAT RESPONSE — no rise after exercise. "
                            "Highly abnormal — consistent with glycogenolysis/glycolysis defect.",
             "effectiveDateTime": (now - timedelta(days=7)).isoformat()},
            {"resourceType": "Observation", "id": "O132", "subject": {"reference": "Patient/P013"},
             "code": {"coding": [{"display": "Urinalysis (during episode)"}]},
             "valueString": "Dipstick: strongly positive for blood (absence of RBCs on microscopy = myoglobinuria). "
                            "Myoglobin: markedly elevated.",
             "effectiveDateTime": (now - timedelta(days=30)).isoformat()},
            {"resourceType": "Observation", "id": "O133", "subject": {"reference": "Patient/P013"},
             "code": {"coding": [{"display": "Muscle MRI (thigh)"}]},
             "valueString": "Patchy T2 hyperintensity in posterior thigh compartment (active myopathy). "
                            "No significant fatty infiltration (early disease).",
             "effectiveDateTime": (now - timedelta(days=14)).isoformat()},
            {"resourceType": "Observation", "id": "O134", "subject": {"reference": "Patient/P013"},
             "code": {"coding": [{"display": "PYGM Gene Testing (myophosphorylase)"}]},
             "valueString": "PENDING — Homozygous p.R50X variant expected (most common McArdle mutation)",
             "effectiveDateTime": now.isoformat()},
            {"resourceType": "Observation", "id": "O135", "subject": {"reference": "Patient/P013"},
             "code": {"coding": [{"display": "Family & Social History"}]},
             "valueString": "High school cross-country runner. No family history of metabolic disease (parents asymptomatic — likely carriers). "
                            "No toxic exposures, no medications, no alcohol.",
             "effectiveDateTime": now.isoformat()},
        ]

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
