"""
Seed Firebase with MedGemma demo data.
Pushes the 2 demo patients and their clinical data into Firestore.

Usage:
    uv run python scripts/seed_firebase.py
"""

import sys
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
    
    print("\n" + "=" * 50)
    print("✅ All data seeded successfully!")
    print("   Run: uv run python main.py --use-vllm")
    print("=" * 50)


if __name__ == "__main__":
    main()
