"""
Firestore-backed FHIR Server
Drop-in replacement for MockFHIRServer — reads/writes patient data from Firestore.
Falls back to MockFHIRServer if Firebase is not configured.
"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class FirestoreFHIRServer:
    """
    FHIR-like server backed by Google Cloud Firestore.
    Same public API as MockFHIRServer so it can be swapped in seamlessly.
    """
    
    def __init__(self):
        """Initialize with a Firestore client."""
        from src.config.firebase_config import get_firestore_client
        self.db = get_firestore_client()
        if self.db is None:
            raise RuntimeError("Firestore client not available")
        logger.info("FirestoreFHIRServer initialized with Firestore backend")
    
    def get_patient(self, patient_id: str) -> dict | None:
        """Get patient demographic data."""
        doc = self.db.collection("patients").document(patient_id).get()
        if doc.exists:
            return doc.to_dict()
        return None
    
    def get_patient_summary(self, patient_id: str) -> dict | None:
        """
        Get comprehensive patient summary including all related resources.
        This is the main method used by the clinical assistant.
        """
        patient_data = self.get_patient(patient_id)
        if not patient_data:
            return None
        
        # Calculate age
        birth_date_str = patient_data.get("birthDate", "")
        try:
            birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d")
            age = (datetime.now() - birth_date).days // 365
        except (ValueError, TypeError):
            age = 0
        
        # Get subcollections
        conditions = self._get_subcollection(patient_id, "conditions")
        medications = self._get_subcollection(patient_id, "medications")
        allergies = self._get_subcollection(patient_id, "allergies")
        observations = self._get_subcollection(patient_id, "observations")
        images = self._get_subcollection(patient_id, "images")
        
        # Parse name robustly (handle both FHIR array format and simple string format)
        raw_name = patient_data.get("name", "Unknown")
        if isinstance(raw_name, list) and len(raw_name) > 0:
            name_obj = raw_name[0]
            if isinstance(name_obj, dict):
                given = " ".join(name_obj.get("given", []))
                family = name_obj.get("family", "")
                full_name = f"{given} {family}".strip()
            else:
                full_name = str(name_obj)
        else:
            full_name = str(raw_name)
            
        return {
            "patient": {
                "id": patient_id,
                "name": full_name,
                "age": age,
                "gender": patient_data.get("gender", "unknown"),
                "location": patient_data.get("city", "Unknown")
            },
            "conditions": [
                {
                    "name": c.get("name", "Unknown"),
                    "status": c.get("status", "unknown"),
                    "onset": c.get("onset", "Unknown")
                }
                for c in conditions
            ],
            "medications": [
                {
                    "name": m.get("name", "Unknown"),
                    "dosage": m.get("dosage", "Unknown"),
                    "status": m.get("status", "unknown")
                }
                for m in medications
            ],
            "allergies": [
                {
                    "substance": a.get("substance", "Unknown"),
                    "reaction": a.get("reaction", "Unknown"),
                    "severity": a.get("severity", "unknown")
                }
                for a in allergies
            ],
            "recent_observations": [
                {
                    "type": o.get("type", "Unknown"),
                    "value": o.get("value", "N/A"),
                    "date": o.get("date", "Unknown")
                }
                for o in observations
            ],
            "images": images
        }
    
    def get_appointment_summary(self, patient_id: str) -> dict | None:
        """Get the latest appointment for a patient."""
        appointments = self._get_subcollection(patient_id, "appointments")
        if not appointments:
            return None
        # Return the most recent appointment (sorted by date descending)
        appointments.sort(key=lambda a: a.get("date", ""), reverse=True)
        return appointments[0]
    
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
        patient_ref = self.db.collection("patients").document(patient_id)
        if not patient_ref.get().exists:
            return {"success": False, "error": "Patient not found"}
        
        updates = []
        
        if new_conditions:
            cond_ref = patient_ref.collection("conditions")
            for condition in new_conditions:
                cond_ref.add({
                    "name": condition,
                    "status": "active",
                    "onset": datetime.now().isoformat()
                })
                updates.append(f"Added condition: {condition}")
        
        if new_medications:
            med_ref = patient_ref.collection("medications")
            for medication in new_medications:
                med_ref.add({
                    "name": medication,
                    "status": "active",
                    "dosage": "As prescribed"
                })
                updates.append(f"Added medication: {medication}")
        
        if encounter_note:
            patient_ref.collection("encounters").add({
                "note": encounter_note,
                "timestamp": datetime.now().isoformat()
            })
            updates.append(f"Added encounter note ({len(encounter_note)} characters)")
        
        return {
            "success": True,
            "patient_id": patient_id,
            "updates": updates,
            "timestamp": datetime.now().isoformat()
        }
    
    def list_patients(self) -> list[dict]:
        """List all available patients."""
        patients = []
        for doc in self.db.collection("patients").stream():
            data = doc.to_dict()
            patients.append({
                "id": doc.id,
                "name": data.get("name", "Unknown"),
                "gender": data.get("gender"),
                "birthDate": data.get("birthDate")
            })
        return patients
    
    def _get_subcollection(self, patient_id: str, collection_name: str) -> list[dict]:
        """Get all documents from a patient subcollection."""
        docs = (
            self.db.collection("patients")
            .document(patient_id)
            .collection(collection_name)
            .stream()
        )
        return [doc.to_dict() for doc in docs]
    
    def add_memory(self, patient_id: str, memory_text: str) -> bool:
        """Store a patient memory note."""
        patient_ref = self.db.collection("patients").document(patient_id)
        if not patient_ref.get().exists:
            return False
            
        patient_ref.collection("memories").add({
            "text": memory_text,
            "timestamp": datetime.now().isoformat()
        })
        return True
        
    def get_memories(self, patient_id: str) -> list[str]:
        """Get all stored memories for a patient."""
        memories = self._get_subcollection(patient_id, "memories")
        # Sort by timestamp descending
        memories.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
        return [m.get("text", "") for m in memories if m.get("text")]
