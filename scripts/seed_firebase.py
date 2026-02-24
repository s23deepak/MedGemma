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
            {"name": "Sepsis", "status": "active", "onset": admission_p004},
            {"name": "Acute Kidney Injury", "status": "active", "onset": admission_p004},
            {"name": "Hypertension", "status": "active", "onset": "2015-03-10"},
        ],
        "P005": [
            {"name": "Congestive Heart Failure", "status": "active", "onset": "2020-06-01"},
            {"name": "Atrial Fibrillation", "status": "active", "onset": "2021-09-15"},
            {"name": "Chronic Kidney Disease Stage 3", "status": "active", "onset": "2022-11-20"},
            {"name": "Hypertension", "status": "active", "onset": "2012-04-05"},
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
            {"name": "Piperacillin-Tazobactam 3.375g IV", "dosage": "q6h", "status": "active"},
            {"name": "Norepinephrine", "dosage": "0.1 mcg/kg/min IV", "status": "active"},
            {"name": "Vancomycin 1250mg IV", "dosage": "q12h", "status": "active"},
        ],
        "P005": [
            {"name": "Furosemide 40mg IV", "dosage": "BID", "status": "active"},
            {"name": "Metoprolol Succinate 25mg", "dosage": "Once daily", "status": "active"},
            {"name": "Lisinopril 5mg", "dosage": "Once daily", "status": "active"},
            {"name": "Spironolactone 25mg", "dosage": "Once daily", "status": "active"},
            {"name": "Apixaban 5mg", "dosage": "Twice daily", "status": "active"},
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
            {"substance": "Penicillin", "reaction": "Rash", "severity": "moderate"},
        ],
        "P005": [
            {"substance": "Aspirin", "reaction": "GI bleeding", "severity": "severe"},
        ],
    }
    for pid, allgs in allergies.items():
        clear_subcollection(db, pid, "allergies")
        coll = db.collection("patients").document(pid).collection("allergies")
        for i, a in enumerate(allgs):
            coll.document(str(i)).set(a)
        print(f"  ✓ {pid}: {len(allgs)} allergies")

    # --- Observations ---
    observations = {
        "P004": [
            {"type": "Temperature", "value": "38.9 C", "date": admission_p004},
            {"type": "Blood Pressure", "value": "88/52 mmHg", "date": admission_p004},
            {"type": "Heart Rate", "value": "118 bpm", "date": admission_p004},
            {"type": "Creatinine", "value": "2.1 mg/dL", "date": admission_p004},
        ],
        "P005": [
            {"type": "BNP", "value": "1840 pg/mL", "date": admission_p005},
            {"type": "eGFR", "value": "38 mL/min/1.73m2", "date": admission_p005},
            {"type": "Weight", "value": "84 kg (up 3 kg from baseline)", "date": admission_p005},
            {"type": "Oxygen Saturation", "value": "94% on 2L nasal cannula", "date": admission_p005},
        ],
    }
    for pid, obs in observations.items():
        clear_subcollection(db, pid, "observations")
        coll = db.collection("patients").document(pid).collection("observations")
        for i, o in enumerate(obs):
            coll.document(str(i)).set(o)
        print(f"  ✓ {pid}: {len(obs)} observations")

    # --- Active Orders ---
    # P004: Pip-Tazo, Vancomycin, Foley — intentionally NO VTE prophylaxis (triggers CRITICAL)
    # P005: Furosemide, Telemetry, Foley inserted 4 days ago (triggers Foley dwell WARNING)
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
                "name": "Vancomycin 1250mg IV q12h",
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
            # NOTE: No VTE prophylaxis order — intentional to trigger CRITICAL safety alert
        ],
        "P005": [
            {
                "order_id": "ORD-P005-001",
                "type": "medication",
                "name": "Furosemide 40mg IV BID",
                "ordered_at": admission_p005,
                "status": "active",
            },
            {
                "order_id": "ORD-P005-002",
                "type": "monitoring",
                "name": "Continuous cardiac telemetry",
                "ordered_at": admission_p005,
                "status": "active",
            },
            {
                "order_id": "ORD-P005-003",
                "type": "device",
                "name": "Foley catheter",
                "ordered_at": admission_p005,
                "inserted_at": admission_p005,
                "status": "active",
            },
            {
                "order_id": "ORD-P005-004",
                "type": "medication",
                "name": "Enoxaparin 40mg SC daily (VTE prophylaxis)",
                "ordered_at": admission_p005,
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
    # P004: last note >26h ago → triggers "no note in 24h" WARNING
    # P005: recent note within 12h → no warning
    progress_notes = {
        "P004": [
            {
                "note_id": "PN-P004-001",
                "author": "Dr. Sarah Smith",
                "role": "attending",
                "created_at": admission_p004,
                "note_text": (
                    "62M admitted via ED with sepsis secondary to pneumonia. "
                    "Hypotensive on arrival, started on vasopressors. "
                    "Blood cultures drawn, empirical antibiotics initiated. "
                    "Foley placed for strict I&Os. ICU-level monitoring."
                ),
            },
            {
                "note_id": "PN-P004-002",
                "author": "Dr. Emily Lee",
                "role": "resident",
                "created_at": (now - timedelta(hours=26)).isoformat(),
                "note_text": (
                    "Overnight: hemodynamically marginal, MAP 62 on norepi 0.08. "
                    "Urine output 20 mL/hr. Creatinine trending up to 2.3. "
                    "Family updated on ICU course."
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
                    "74F admitted with acute CHF exacerbation. "
                    "BNP 1840, 3kg weight gain. IV diuresis initiated. "
                    "AFib with RVR on admission, rate-controlled with metoprolol. "
                    "CKD stage 3 — renal function monitoring daily."
                ),
            },
            {
                "note_id": "PN-P005-002",
                "author": "Dr. Michael Jones",
                "role": "attending",
                "created_at": (now - timedelta(hours=10)).isoformat(),
                "note_text": (
                    "Day 4: Diuresis progressing well, -1.2 kg today. "
                    "BNP downtrending. Rate controlled in 70s. "
                    "Creatinine stable at 1.8. Consider discharge planning — "
                    "social work consult for home health evaluation."
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
