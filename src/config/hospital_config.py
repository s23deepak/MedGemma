"""
Hospital Registry — multi-tenant hospital configuration profiles.

Supports config-driven multi-tenancy by associating patients, users, and
clinical features with a named hospital. Pre-seeded with two demo hospitals:
  GENERAL  — General Hospital (Chicago)
  COMMUNITY — Community Medical Center (New York)

When Firebase is available, the registry loads existing hospital profiles
from the `hospitals/` Firestore collection on startup and persists new
hospital additions there automatically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Hospital dataclass ────────────────────────────────────────────────────────

@dataclass
class Hospital:
    """Configuration profile for a single hospital."""
    hospital_id: str
    name: str
    timezone: str = "UTC"
    formulary_restrictions: list[str] = field(default_factory=list)
    branding: dict = field(default_factory=lambda: {
        "logo_url": "",
        "primary_color": "#2563eb",
    })
    features_enabled: dict = field(default_factory=lambda: {
        "audit_log": True,
        "prior_auth": True,
        "referral": True,
        "simulation": True,
    })
    contact_info: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "hospital_id": self.hospital_id,
            "name": self.name,
            "timezone": self.timezone,
            "formulary_restrictions": self.formulary_restrictions,
            "branding": self.branding,
            "features_enabled": self.features_enabled,
            "contact_info": self.contact_info,
        }


# ── Pre-seeded demo hospitals ─────────────────────────────────────────────────

_DEMO_HOSPITALS: list[Hospital] = [
    Hospital(
        hospital_id="GENERAL",
        name="General Hospital",
        timezone="America/Chicago",
        formulary_restrictions=[],
        branding={"logo_url": "", "primary_color": "#2563eb"},
        features_enabled={
            "audit_log": True, "prior_auth": True,
            "referral": True, "simulation": True,
        },
        contact_info={"phone": "555-0100", "address": "123 Medical Dr, Chicago IL"},
    ),
    Hospital(
        hospital_id="COMMUNITY",
        name="Community Medical Center",
        timezone="America/New_York",
        formulary_restrictions=["adalimumab", "pembrolizumab"],
        branding={"logo_url": "", "primary_color": "#16a34a"},
        features_enabled={
            "audit_log": True, "prior_auth": False,
            "referral": True, "simulation": False,
        },
        contact_info={"phone": "555-0200", "address": "456 Community Ave, New York NY"},
    ),
]


# ── HospitalRegistry ──────────────────────────────────────────────────────────

class HospitalRegistry:
    """
    In-memory registry of hospital profiles with optional Firestore persistence.

    On init: pre-seeds GENERAL and COMMUNITY, then overlays any hospitals
    found in Firestore (allowing Firestore to override demo data).
    """

    def __init__(self) -> None:
        self._hospitals: dict[str, Hospital] = {}
        # Seed demo hospitals
        for hosp in _DEMO_HOSPITALS:
            self._hospitals[hosp.hospital_id] = hosp
        # Overlay with Firestore data if available
        self._load_from_firestore()

    def get(self, hospital_id: str) -> Hospital | None:
        """Return the Hospital for the given ID, or None if not found."""
        return self._hospitals.get(hospital_id)

    def list_all(self) -> list[dict]:
        """Return all hospital profiles as serialisable dicts."""
        return [h.to_dict() for h in self._hospitals.values()]

    def add(self, hospital: Hospital) -> Hospital:
        """
        Register a new hospital (or overwrite an existing one).

        Persists to Firestore hospitals/{hospital_id} when Firebase is available.
        Returns the stored Hospital.
        """
        self._hospitals[hospital.hospital_id] = hospital
        self._write_to_firestore(hospital)
        logger.info(f"[HospitalRegistry] Registered hospital: {hospital.hospital_id}")
        return hospital

    # ── Firestore helpers ──────────────────────────────────────────────────

    def _load_from_firestore(self) -> None:
        """Load hospital profiles from Firestore (non-fatal on failure)."""
        try:
            from src.config.firebase_config import get_firestore_client, is_firebase_available
            if not is_firebase_available():
                return
            db = get_firestore_client()
            if db is None:
                return
            docs = db.collection("hospitals").stream()
            for doc in docs:
                data = doc.to_dict()
                if not data or "hospital_id" not in data:
                    continue
                hosp = Hospital(
                    hospital_id=data["hospital_id"],
                    name=data.get("name", data["hospital_id"]),
                    timezone=data.get("timezone", "UTC"),
                    formulary_restrictions=data.get("formulary_restrictions", []),
                    branding=data.get("branding", {"logo_url": "", "primary_color": "#2563eb"}),
                    features_enabled=data.get("features_enabled", {}),
                    contact_info=data.get("contact_info", {}),
                )
                self._hospitals[hosp.hospital_id] = hosp
            logger.info(f"[HospitalRegistry] Loaded {len(self._hospitals)} hospitals from Firestore")
        except Exception as exc:
            logger.debug(f"[HospitalRegistry] Firestore load skipped ({exc})")

    def _write_to_firestore(self, hospital: Hospital) -> None:
        """Silently persist a hospital to Firestore hospitals/{hospital_id}."""
        try:
            from src.config.firebase_config import get_firestore_client, is_firebase_available
            if not is_firebase_available():
                return
            db = get_firestore_client()
            if db is None:
                return
            db.collection("hospitals").document(hospital.hospital_id).set(hospital.to_dict())
        except Exception as exc:
            logger.debug(f"[HospitalRegistry] Firestore write skipped ({exc})")


# ── Singleton ─────────────────────────────────────────────────────────────────

_registry: HospitalRegistry | None = None


def get_hospital_registry() -> HospitalRegistry:
    """Get or create the HospitalRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = HospitalRegistry()
        logger.info("[HospitalRegistry] Initialized with hospitals: "
                    + ", ".join(_registry._hospitals.keys()))
    return _registry
