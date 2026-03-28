"""
Async FHIR Server wrapper for Firestore operations.
Non-blocking, event-loop friendly operations.
"""

import logging
from datetime import datetime
from typing import Any

from src.config.async_firestore import get_async_firestore_client

logger = logging.getLogger(__name__)


class AsyncFirestoreFHIRServer:
    """Async FHIR server backed by Firestore (non-blocking)."""

    def __init__(self):
        """Initialize with async Firestore client."""
        self.db = get_async_firestore_client()
        logger.info("AsyncFirestoreFHIRServer initialized with async Firestore backend")

    async def get_patient(self, patient_id: str) -> dict | None:
        """Async get patient demographic data."""
        return await self.db.get_document("patients", patient_id)

    async def get_patient_summary(self, patient_id: str) -> dict | None:
        """Async get comprehensive patient summary including all related resources."""
        patient_data = await self.get_patient(patient_id)
        if not patient_data:
            return None

        # Calculate age
        birth_date_str = patient_data.get("birthDate", "")
        try:
            birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d")
            age = (datetime.now() - birth_date).days // 365
        except (ValueError, TypeError):
            age = 0

        # Get subcollections (parallelized)
        import asyncio
        (conditions, medications, allergies, observations, images) = await asyncio.gather(
            self.db.get_subcollection("patients", patient_id, "conditions"),
            self.db.get_subcollection("patients", patient_id, "medications"),
            self.db.get_subcollection("patients", patient_id, "allergies"),
            self.db.get_subcollection("patients", patient_id, "observations"),
            self.db.get_subcollection("patients", patient_id, "images"),
        )

        # Parse name robustly
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

        summary = {
            "patient": {
                "id": patient_id,
                "name": full_name,
                "age": age,
                "gender": patient_data.get("gender", "unknown"),
                "location": patient_data.get("city", "Unknown"),
            },
            "conditions": [
                {
                    "name": c.get("name", "Unknown"),
                    "status": c.get("status", "unknown"),
                    "onset": c.get("onset", "Unknown"),
                }
                for c in conditions
            ],
            "medications": [
                {
                    "name": m.get("name", "Unknown"),
                    "dosage": m.get("dosage", "Unknown"),
                    "status": m.get("status", "unknown"),
                }
                for m in medications
            ],
            "allergies": [
                {
                    "substance": a.get("substance", "Unknown"),
                    "reaction": a.get("reaction", "Unknown"),
                    "severity": a.get("severity", "unknown"),
                }
                for a in allergies
            ],
            "observations": observations or [],
            "images": images or [],
        }

        return summary

    async def list_patients(self) -> list[dict]:
        """Async list all patients."""
        return await self.db.list_collection("patients")

    async def get_conditions(self, patient_id: str) -> list[dict]:
        """Async get patient conditions."""
        return await self.db.get_subcollection("patients", patient_id, "conditions")

    async def get_medications(self, patient_id: str) -> list[dict]:
        """Async get patient medications."""
        return await self.db.get_subcollection("patients", patient_id, "medications")

    async def create_observation(
        self, patient_id: str, observation_data: dict
    ) -> None:
        """Async create observation for patient."""
        import uuid
        obs_id = str(uuid.uuid4())
        await self.db.write_document(
            f"patients/{patient_id}/observations",
            obs_id,
            {**observation_data, "id": obs_id, "timestamp": datetime.now().isoformat()},
        )

    async def update_patient(self, patient_id: str, data: dict) -> None:
        """Async update patient data."""
        await self.db.update_document("patients", patient_id, data)


# Global instance for convenience
_async_fhir_server: AsyncFirestoreFHIRServer | None = None


def get_async_fhir_server() -> AsyncFirestoreFHIRServer:
    """Get or create async FHIR server instance."""
    global _async_fhir_server
    if _async_fhir_server is None:
        try:
            _async_fhir_server = AsyncFirestoreFHIRServer()
        except RuntimeError:
            logger.warning("AsyncFirestoreFHIRServer could not initialize, Firestore not configured")
            raise
    return _async_fhir_server
