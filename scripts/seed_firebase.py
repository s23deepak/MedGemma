"""
Seed Firebase with MedGemma demo data.
Pushes the 2 demo patients and their clinical data into Firestore.

Usage:
    uv run python scripts/seed_firebase.py
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.firebase_config import get_firestore_client, is_firebase_available
from src.agent.medgemma_agent import MedGemmaAgent


def clear_subcollection(db, patient_id: str, subcol: str):
    """Delete all documents in a patient subcollection before re-seeding."""
    coll = db.collection("patients").document(patient_id).collection(subcol)
    docs = coll.stream()
    for doc in docs:
        doc.reference.delete()


def seed_patients(db):
    """Seed demo patient demographics."""
    patients = {
        "P001": {
            "name": "Sarah M Wilson",
            "gender": "female",
            "birthDate": "1968-03-15",
            "city": "Chicago",
            "state": "IL"
        },
        "P002": {
            "name": "Carlos Martinez",
            "gender": "male",
            "birthDate": "1955-11-22",
            "city": "Miami",
            "state": "FL"
        },
        "P003": {
            "name": "John Doe",
            "gender": "male",
            "birthDate": "1980-07-10",
            "city": "Los Angeles",
            "state": "CA"
        }
    }

    for pid, data in patients.items():
        db.collection("patients").document(pid).set(data)
        print(f"  ✓ Patient {pid}: {data['name']}")

    return patients


def seed_conditions(db):
    """Seed patient conditions."""
    conditions = {
        "P001": [
            {"name": "Asthma", "status": "active", "onset": "2015-06-01", "code": "195967001"},
            {"name": "Hypertension", "status": "active", "onset": "2020-01-15", "code": "38341003"}
        ],
        "P002": [
            {"name": "Diabetes mellitus type 2", "status": "active", "onset": "2010-03-20", "code": "73211009"},
            {"name": "Coronary artery disease", "status": "active", "onset": "2018-09-10"},
            {"name": "Chronic kidney disease stage 3", "status": "active", "onset": "2022-04-01"}
        ],
        "P003": [
            {"name": "Anxiety disorder", "status": "active", "onset": "2021-03-15"},
            {"name": "Migraine", "status": "active", "onset": "2019-08-20"}
        ]
    }

    for pid, conds in conditions.items():
        clear_subcollection(db, pid, "conditions")
        coll = db.collection("patients").document(pid).collection("conditions")
        for i, c in enumerate(conds):
            coll.document(str(i)).set(c)
        print(f"  ✓ {pid}: {len(conds)} conditions")


def seed_medications(db):
    """Seed patient medications."""
    medications = {
        "P001": [
            {"name": "Albuterol inhaler", "dosage": "2 puffs PRN", "status": "active"},
            {"name": "Lisinopril 10mg", "dosage": "Once daily", "status": "active"}
        ],
        "P002": [
            {"name": "Metformin 1000mg", "dosage": "Twice daily with meals", "status": "active"},
            {"name": "Atorvastatin 40mg", "dosage": "Once daily at bedtime", "status": "active"},
            {"name": "Aspirin 81mg", "dosage": "Once daily", "status": "active"}
        ],
        "P003": [
            {"name": "Sertraline 50mg", "dosage": "Once daily in the morning", "status": "active"},
            {"name": "Sumatriptan 50mg", "dosage": "As needed for migraines", "status": "active"},
            {"name": "Ibuprofen 400mg", "dosage": "As needed for pain", "status": "active"}
        ]
    }

    for pid, meds in medications.items():
        clear_subcollection(db, pid, "medications")
        coll = db.collection("patients").document(pid).collection("medications")
        for i, m in enumerate(meds):
            coll.document(str(i)).set(m)
        print(f"  ✓ {pid}: {len(meds)} medications")


def seed_allergies(db):
    """Seed patient allergies."""
    allergies = {
        "P001": [
            {"substance": "Penicillin", "reaction": "Rash", "severity": "moderate"}
        ],
        "P002": [
            {"substance": "Sulfa drugs", "reaction": "Anaphylaxis", "severity": "severe"}
        ],
        "P003": [
            {"substance": "Latex", "reaction": "Skin irritation", "severity": "moderate"},
            {"substance": "Codeine", "reaction": "Nausea and vomiting", "severity": "moderate"}
        ]
    }

    for pid, allgs in allergies.items():
        clear_subcollection(db, pid, "allergies")
        coll = db.collection("patients").document(pid).collection("allergies")
        for i, a in enumerate(allgs):
            coll.document(str(i)).set(a)
        print(f"  ✓ {pid}: {len(allgs)} allergies")


def seed_observations(db):
    """Seed patient observations/vitals."""
    observations = {
        "P001": [
            {"type": "Blood Pressure", "value": "138 mmHg", "date": "2026-02-01T10:00:00Z"},
            {"type": "Heart Rate", "value": "78 bpm", "date": "2026-02-01T10:00:00Z"},
            {"type": "Oxygen Saturation", "value": "96 %", "date": "2026-02-01T10:00:00Z"},
            {"type": "Smoking Status", "value": "Former smoker (quit 2019)", "date": "2026-01-15T09:00:00Z"}
        ],
        "P002": [
            {"type": "HbA1c", "value": "7.8 %", "date": "2026-01-20T08:00:00Z"},
            {"type": "eGFR", "value": "45 mL/min/1.73m2", "date": "2026-01-20T08:00:00Z"}
        ],
        "P003": [
            {"type": "Blood Pressure", "value": "122/78 mmHg", "date": "2026-02-10T09:00:00Z"},
            {"type": "Heart Rate", "value": "72 bpm", "date": "2026-02-10T09:00:00Z"},
            {"type": "BMI", "value": "24.5", "date": "2026-02-10T09:00:00Z"}
        ]
    }

    for pid, obs in observations.items():
        clear_subcollection(db, pid, "observations")
        coll = db.collection("patients").document(pid).collection("observations")
        for i, o in enumerate(obs):
            coll.document(str(i)).set(o)
        print(f"  ✓ {pid}: {len(obs)} observations")


def seed_images(db):
    """Seed patient images dynamically."""

    analysis_text = "Analysis pending..."
    try:
        agent = MedGemmaAgent()
        image_path = Path("data/sample_xray_normal.jpg")
        if image_path.exists():
            print("  Analyzing sample X-Ray with MedGemma... this may take a moment.")
            result = agent.analyze_image(str(image_path), modality="xray")
            analysis_text = result.get("analysis", "Error in analysis generation.")
            print(f"  Successfully generated analysis: {analysis_text[:50]}...")
        else:
            print("  Warning: sample_xray_normal.jpg not found. Using fallback text.")
            analysis_text = "PA and Lateral views of the chest demonstrate clear lungs without focal consolidation, pneumothorax, or pleural effusion. The cardiac silhouette is normal in size and contour. The mediastinum and hila are unremarkable. The visible osseous structures are intact. Conclusion: Normal chest radiograph."
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"  Warning: Could not dynamically analyze image: {e}")
        analysis_text = "PA and Lateral views of the chest demonstrate clear lungs without focal consolidation, pneumothorax, or pleural effusion. The cardiac silhouette is normal in size and contour. The mediastinum and hila are unremarkable. The visible osseous structures are intact. Conclusion: Normal chest radiograph."

    images = {
        "P003": [
            {
                "url": "/static/images/mock_chest_xray.jpg",
                "modality": "xray",
                "timestamp": "2025-11-15T14:30:00Z",
                "analysis": analysis_text
            }
        ]
    }

    for pid, imgs in images.items():
        clear_subcollection(db, pid, "images")
        coll = db.collection("patients").document(pid).collection("images")
        for i, img in enumerate(imgs):
            coll.document(str(i)).set(img)
        print(f"  ✓ {pid}: {len(imgs)} images")


def seed_appointments(db):
    """Seed patient appointments."""
    appointments = {
        "P001": [
            {
                "date": "February 5, 2026",
                "provider": "Dr. Sarah Smith",
                "type": "Follow-up Visit",
                "diagnoses": ["Hypertension (controlled)", "Asthma (stable)"],
                "medications": [
                    {"name": "Lisinopril 10mg", "instructions": "Take once daily in the morning"},
                    {"name": "Albuterol inhaler", "instructions": "2 puffs as needed"}
                ],
                "instructions": [
                    "Continue current medications",
                    "Monitor blood pressure at home",
                    "Follow low-sodium diet",
                    "Return in 3 months for follow-up"
                ],
                "followup_date": "May 5, 2026"
            }
        ],
        "P002": [
            {
                "date": "January 28, 2026",
                "provider": "Dr. James Rodriguez",
                "type": "Endocrinology Consult",
                "diagnoses": ["Type 2 Diabetes (suboptimal control)", "CKD Stage 3"],
                "medications": [
                    {"name": "Metformin 1000mg", "instructions": "Take twice daily with meals"},
                    {"name": "Atorvastatin 40mg", "instructions": "Take once daily at bedtime"},
                    {"name": "Aspirin 81mg", "instructions": "Take once daily"}
                ],
                "instructions": [
                    "Increase Metformin monitoring",
                    "Check HbA1c in 3 months",
                    "Renal panel in 6 weeks",
                    "Low-carb, renal-friendly diet"
                ],
                "followup_date": "April 28, 2026"
            }
        ],
        "P003": [
            {
                "date": "February 10, 2026",
                "provider": "Dr. Emily Chen",
                "type": "Annual Physical",
                "diagnoses": ["Anxiety disorder (managed)", "Migraine (intermittent)"],
                "medications": [
                    {"name": "Sertraline 50mg", "instructions": "Take once daily in the morning"},
                    {"name": "Sumatriptan 50mg", "instructions": "Take as needed at migraine onset"},
                    {"name": "Ibuprofen 400mg", "instructions": "Take as needed, max 3 times daily"}
                ],
                "instructions": [
                    "Continue Sertraline, monitor mood",
                    "Keep migraine diary",
                    "Exercise 30 min/day for anxiety management",
                    "Return in 6 months for follow-up"
                ],
                "followup_date": "August 10, 2026"
            }
        ]
    }

    for pid, appts in appointments.items():
        clear_subcollection(db, pid, "appointments")
        coll = db.collection("patients").document(pid).collection("appointments")
        for i, a in enumerate(appts):
            coll.document(str(i)).set(a)
        print(f"  ✓ {pid}: {len(appts)} appointments")


def main():
    print("=" * 50)
    print("MedGemma — Firebase Data Seeding")
    print("=" * 50)
    
    if not is_firebase_available():
        print("\n❌ Firebase is not configured.")
        print("   Make sure firebase-key.json exists in the project root.")
        print("   See docs/firebase_setup.md for instructions.")
        sys.exit(1)
    
    db = get_firestore_client()
    
    print("\n📋 Seeding patients...")
    seed_patients(db)
    
    print("\n🩺 Seeding conditions...")
    seed_conditions(db)
    
    print("\n💊 Seeding medications...")
    seed_medications(db)
    
    print("\n⚠️  Seeding allergies...")
    seed_allergies(db)
    
    print("\n📊 Seeding observations...")
    seed_observations(db)
    
    print("\n🖼️  Seeding images...")
    seed_images(db)
    
    print("\n📅 Seeding appointments...")
    seed_appointments(db)

    print("\n🏥 Seeding inpatients...")
    seed_inpatients(db)

    print("\n" + "=" * 50)
    print("✅ All data seeded successfully!")
    print("   Run: uv run python main.py --use-vllm")
    print("=" * 50)


def seed_inpatients(db):
    """Seed inpatient demo patients P004 and P005 with clinical + orders + notes."""
    now = datetime.now()
    admission_p004 = (now - timedelta(hours=36)).isoformat()
    admission_p005 = (now - timedelta(days=4)).isoformat()

    # --- Root patient documents ---
    inpatients = {
        "P004": {
            "name": "Raymond Okafor",
            "gender": "male",
            "birthDate": "1972-04-18",
            "city": "Houston",
            "state": "TX",
            "encounter_type": "inpatient",
            "admission_date": admission_p004,
            "ward": "ICU",
            "bed": "ICU-04",
            "code_status": "Full Code",
            "attending": "Dr. Sarah Smith",
        },
        "P005": {
            "name": "Dorothy Chen",
            "gender": "female",
            "birthDate": "1949-09-03",
            "city": "Seattle",
            "state": "WA",
            "encounter_type": "inpatient",
            "admission_date": admission_p005,
            "ward": "Cardiology",
            "bed": "CARD-12",
            "code_status": "DNR/DNI",
            "attending": "Dr. Michael Jones",
        },
    }

    for pid, data in inpatients.items():
        db.collection("patients").document(pid).set(data)
        print(f"  ✓ Inpatient {pid}: {data['name']}")

    # --- Conditions ---
    conditions = {
        "P004": [
            {"name": "Sepsis due to gram-negative bacteria", "status": "active", "onset": admission_p004},
            {"name": "Acute respiratory failure", "status": "active", "onset": admission_p004},
            {"name": "Type 2 diabetes mellitus", "status": "active", "onset": "2015-06-10"},
            {"name": "Acute kidney injury stage 2", "status": "active",
             "onset": (now - timedelta(hours=18)).isoformat()},
        ],
        "P005": [
            {"name": "Acute exacerbation of congestive heart failure", "status": "active",
             "onset": admission_p005},
            {"name": "Atrial fibrillation", "status": "active", "onset": "2019-11-05"},
            {"name": "Chronic kidney disease stage 3", "status": "active", "onset": "2021-03-18"},
            {"name": "Type 2 diabetes mellitus", "status": "active", "onset": "2008-07-22"},
        ],
    }
    for pid, conds in conditions.items():
        clear_subcollection(db, pid, "conditions")
        coll = db.collection("patients").document(pid).collection("conditions")
        for i, c in enumerate(conds):
            coll.document(str(i)).set(c)
        print(f"  ✓ {pid}: {len(conds)} conditions")

    # --- Medications ---
    medications = {
        "P004": [
            {"name": "Piperacillin-Tazobactam 3.375g IV", "dosage": "Every 6 hours IV", "status": "active"},
            {"name": "Norepinephrine infusion", "dosage": "0.08 mcg/kg/min IV (titrate for MAP >65)",
             "status": "active"},
            {"name": "Insulin Regular (sliding scale)", "dosage": "Sliding scale per ICU protocol",
             "status": "active"},
        ],
        "P005": [
            {"name": "Furosemide 80mg IV", "dosage": "Twice daily IV (transitioning to oral)", "status": "active"},
            {"name": "Carvedilol 6.25mg", "dosage": "Twice daily oral", "status": "active"},
            {"name": "Lisinopril 5mg", "dosage": "Once daily (held while Cr elevated)", "status": "active"},
            {"name": "Apixaban 5mg", "dosage": "Twice daily (a-fib anticoagulation)", "status": "active"},
            {"name": "Insulin Glargine 18 units", "dosage": "Once nightly subcutaneous", "status": "active"},
        ],
    }
    for pid, meds in medications.items():
        clear_subcollection(db, pid, "medications")
        coll = db.collection("patients").document(pid).collection("medications")
        for i, m in enumerate(meds):
            coll.document(str(i)).set(m)
        print(f"  ✓ {pid}: {len(meds)} medications")

    # --- Allergies ---
    allergies = {
        "P004": [
            {"substance": "Vancomycin", "reaction": "Red man syndrome", "severity": "moderate"},
        ],
        "P005": [
            {"substance": "Aspirin", "reaction": "Bronchospasm", "severity": "severe"},
        ],
    }
    for pid, allgs in allergies.items():
        clear_subcollection(db, pid, "allergies")
        coll = db.collection("patients").document(pid).collection("allergies")
        for i, a in enumerate(allgs):
            coll.document(str(i)).set(a)
        print(f"  ✓ {pid}: {len(allgs)} allergies")

    # --- Observations ---
    # P004: trending labs to support rich AI reasoning (WBC, Creatinine trend, Procalcitonin, cultures)
    # P005: BNP + Weight trajectory over 4 days, rising Creatinine (diuresis-induced CKD stress)
    observations = {
        "P004": [
            {"type": "Blood Pressure", "value": "88/52 mmHg",
             "date": (now - timedelta(hours=1)).isoformat()},
            {"type": "Heart Rate", "value": "118 bpm",
             "date": (now - timedelta(hours=1)).isoformat()},
            {"type": "Temperature", "value": "38.9 °C",
             "date": (now - timedelta(hours=2)).isoformat()},
            {"type": "Oxygen Saturation", "value": "94 %",
             "date": (now - timedelta(hours=1)).isoformat()},
            {"type": "Lactate", "value": "3.2 mmol/L",
             "date": (now - timedelta(hours=4)).isoformat()},
            {"type": "Blood Glucose", "value": "218 mg/dL",
             "date": (now - timedelta(hours=2)).isoformat()},
            # Trending WBC — downtrending (treatment response)
            {"type": "WBC", "value": "19.2 K/uL",
             "date": (now - timedelta(hours=36)).isoformat()},
            {"type": "WBC", "value": "16.8 K/uL",
             "date": (now - timedelta(hours=8)).isoformat()},
            # Trending Creatinine — uptrending AKI stage 2
            {"type": "Creatinine", "value": "1.4 mg/dL",
             "date": (now - timedelta(hours=36)).isoformat()},
            {"type": "Creatinine", "value": "2.1 mg/dL",
             "date": (now - timedelta(hours=18)).isoformat()},
            {"type": "Creatinine", "value": "2.4 mg/dL",
             "date": (now - timedelta(hours=8)).isoformat()},
            {"type": "Procalcitonin", "value": "42.8 ng/mL",
             "date": (now - timedelta(hours=36)).isoformat()},
            {"type": "Blood Culture Result",
             "value": "Gram-negative bacteremia — E. coli, susceptibilities pending",
             "date": (now - timedelta(hours=14)).isoformat()},
            {"type": "Urine Output", "value": "22 mL/hr",
             "date": (now - timedelta(hours=2)).isoformat()},
            {"type": "Mean Arterial Pressure", "value": "68 mmHg",
             "date": (now - timedelta(hours=2)).isoformat()},
        ],
        "P005": [
            {"type": "Blood Pressure", "value": "118/72 mmHg",
             "date": (now - timedelta(hours=3)).isoformat()},
            {"type": "Heart Rate", "value": "76 bpm",
             "date": (now - timedelta(hours=3)).isoformat()},
            {"type": "Oxygen Saturation", "value": "96 %",
             "date": (now - timedelta(hours=3)).isoformat()},
            # Weight trajectory: -6.4 kg over 4 days (diuresis response)
            {"type": "Weight", "value": "78.8 kg",
             "date": (now - timedelta(days=4)).isoformat()},
            {"type": "Weight", "value": "74.8 kg",
             "date": (now - timedelta(days=2)).isoformat()},
            {"type": "Weight", "value": "72.4 kg",
             "date": (now - timedelta(hours=6)).isoformat()},
            # BNP trajectory: 2100 → 1250 → 620 (improving)
            {"type": "BNP", "value": "2100 pg/mL",
             "date": (now - timedelta(days=4)).isoformat()},
            {"type": "BNP", "value": "1250 pg/mL",
             "date": (now - timedelta(days=2)).isoformat()},
            {"type": "BNP", "value": "620 pg/mL",
             "date": (now - timedelta(hours=8)).isoformat()},
            # Creatinine trajectory: rising (diuresis-induced CKD stress)
            {"type": "Creatinine", "value": "1.4 mg/dL",
             "date": (now - timedelta(days=4)).isoformat()},
            {"type": "Creatinine", "value": "1.5 mg/dL",
             "date": (now - timedelta(days=3)).isoformat()},
            {"type": "Creatinine", "value": "1.6 mg/dL",
             "date": (now - timedelta(days=2)).isoformat()},
            {"type": "Creatinine", "value": "1.7 mg/dL",
             "date": (now - timedelta(hours=8)).isoformat()},
            {"type": "eGFR", "value": "35 mL/min",
             "date": (now - timedelta(hours=8)).isoformat()},
        ],
    }
    for pid, obs in observations.items():
        clear_subcollection(db, pid, "observations")
        coll = db.collection("patients").document(pid).collection("observations")
        for i, o in enumerate(obs):
            coll.document(str(i)).set(o)
        print(f"  ✓ {pid}: {len(obs)} observations")

    # --- Active Orders ---
    # P004: Full ICU orders + consults; intentionally NO VTE prophylaxis → CRITICAL safety alert
    # P005: CHF management orders; Foley inserted at admission (96h dwell → Foley WARNING)
    active_orders = {
        "P004": [
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
            # NOTE: No VTE prophylaxis order — intentional to trigger CRITICAL safety alert
        ],
        "P005": [
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
        ],
    }
    for pid, orders in active_orders.items():
        clear_subcollection(db, pid, "active_orders")
        coll = db.collection("patients").document(pid).collection("active_orders")
        for i, o in enumerate(orders):
            coll.document(str(i)).set(o)
        print(f"  ✓ {pid}: {len(orders)} active orders")

    # --- Progress Notes ---
    # P004: last note >26h ago → triggers note-currency WARNING
    # P005: 3 notes with last note 10h ago → no warning; trajectory narrative present
    progress_notes = {
        "P004": [
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
                    "Repeat lactate 3.2, downtrending. Blood cultures x2 — E. coli identified, "
                    "susceptibilities pending. Creatinine rising (1.4 → 2.1 → 2.4): "
                    "AKI stage 2 — ID consult and renal ultrasound ordered. "
                    "Glucose 218 — added to insulin sliding scale. Urine output 22 mL/hr."
                ),
            },
        ],
        "P005": [
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
                    "Day 4: significant clinical improvement. Weight 72.4 kg (total -6.4 kg). "
                    "BNP 620 (trending down). Room air O2 sat 96%. "
                    "Creatinine 1.7 — rising trend (1.4→1.5→1.6→1.7), monitor closely; "
                    "Lisinopril held. Plan: transition furosemide to oral, target discharge tomorrow. "
                    "Needs cardiology follow-up, daily weights at home, return precautions."
                ),
            },
        ],
    }
    for pid, notes in progress_notes.items():
        clear_subcollection(db, pid, "progress_notes")
        coll = db.collection("patients").document(pid).collection("progress_notes")
        for i, n in enumerate(notes):
            coll.document(str(i)).set(n)
        print(f"  ✓ {pid}: {len(notes)} progress notes")


if __name__ == "__main__":
    main()
