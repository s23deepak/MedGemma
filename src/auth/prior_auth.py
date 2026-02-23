"""
Prior Authorization workflow service.

State machine:
  DRAFT → SUBMITTED → PENDING_REVIEW → APPROVED | DENIED | REQUIRES_MORE_INFO
                                              ↕
                                      REQUIRES_MORE_INFO → SUBMITTED (re-submission)

A prior auth request is created automatically when:
  - A lab order, imaging order, or prescription requires it (detected by
    the MedGemma agent via a simple keyword list that mirrors real-world PA
    requirements)
  - Or manually created by a physician

The care team can update status, add notes, and attach supporting documents
(as text for the demo; real deployment would use file uploads).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.ehr.fhir_mock import MockFHIRServer


class AuthStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    DENIED = "denied"
    REQUIRES_MORE_INFO = "requires_more_info"


class ServiceType(str, Enum):
    LAB = "lab"
    IMAGING = "imaging"
    MEDICATION = "medication"
    PROCEDURE = "procedure"
    SPECIALIST_REFERRAL = "specialist_referral"


# Services that commonly require prior authorisation
PA_REQUIRED_KEYWORDS: dict[str, ServiceType] = {
    # Labs
    "genetic testing": ServiceType.LAB,
    "whole genome": ServiceType.LAB,
    "comprehensive metabolomics": ServiceType.LAB,
    # Imaging
    "MRI": ServiceType.IMAGING,
    "PET scan": ServiceType.IMAGING,
    "CT": ServiceType.IMAGING,
    "nuclear medicine": ServiceType.IMAGING,
    # Medications (high-cost / specialty)
    "adalimumab": ServiceType.MEDICATION,
    "pembrolizumab": ServiceType.MEDICATION,
    "nivolumab": ServiceType.MEDICATION,
    "infliximab": ServiceType.MEDICATION,
    "etanercept": ServiceType.MEDICATION,
    "semaglutide": ServiceType.MEDICATION,
    "dupilumab": ServiceType.MEDICATION,
    # Procedures
    "surgery": ServiceType.PROCEDURE,
    "procedure": ServiceType.PROCEDURE,
    "endoscopy": ServiceType.PROCEDURE,
    "colonoscopy": ServiceType.PROCEDURE,
    "rehabilitation": ServiceType.PROCEDURE,
    # Referrals
    "specialist referral": ServiceType.SPECIALIST_REFERRAL,
    "oncology referral": ServiceType.SPECIALIST_REFERRAL,
    "cardiology referral": ServiceType.SPECIALIST_REFERRAL,
}


@dataclass
class PriorAuthRequest:
    """A single prior authorization request in the workflow."""
    auth_id: str
    patient_id: str
    encounter_id: str
    service_type: ServiceType
    service_description: str      # human-readable description
    clinical_indication: str      # why the service is needed
    urgency: str                  # routine | urgent | emergency
    status: AuthStatus
    created_at: datetime
    updated_at: datetime
    # Optional fields filled in over the workflow
    insurer_ref: str = ""         # insurer reference / tracking number
    supporting_docs: list[str] = field(default_factory=list)   # text notes
    history: list[dict] = field(default_factory=list)          # status change log
    denial_reason: str = ""
    approved_by: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "auth_id": self.auth_id,
            "patient_id": self.patient_id,
            "encounter_id": self.encounter_id,
            "service_type": self.service_type.value,
            "service_description": self.service_description,
            "clinical_indication": self.clinical_indication,
            "urgency": self.urgency,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "insurer_ref": self.insurer_ref,
            "supporting_docs": self.supporting_docs,
            "history": self.history,
            "denial_reason": self.denial_reason,
            "approved_by": self.approved_by,
            "notes": self.notes,
        }


# ── Service ───────────────────────────────────────────────────────────────────

class PriorAuthService:
    """Manages prior authorization requests through their lifecycle."""

    def __init__(self, fhir_server: "MockFHIRServer"):
        self.fhir = fhir_server
        if not hasattr(self.fhir, "prior_auths"):
            self.fhir.prior_auths: dict[str, list[dict]] = {}  # patient_id → list

    # ── Creation ─────────────────────────────────────────────────────────────

    def create(
        self,
        patient_id: str,
        encounter_id: str,
        service_type: str | ServiceType,
        service_description: str,
        clinical_indication: str,
        urgency: str = "routine",
        auto_submit: bool = True,
    ) -> PriorAuthRequest:
        """
        Create a new prior auth request.

        Args:
            auto_submit: If True, immediately transitions from DRAFT → SUBMITTED.
        """
        if isinstance(service_type, str):
            service_type = ServiceType(service_type.lower()) if service_type.lower() in ServiceType._value2member_map_ else ServiceType.PROCEDURE

        status = AuthStatus.SUBMITTED if auto_submit else AuthStatus.DRAFT
        now = datetime.now()
        req = PriorAuthRequest(
            auth_id=f"PA-{uuid.uuid4().hex[:8].upper()}",
            patient_id=patient_id,
            encounter_id=encounter_id,
            service_type=service_type,
            service_description=service_description,
            clinical_indication=clinical_indication,
            urgency=urgency,
            status=status,
            created_at=now,
            updated_at=now,
            history=[{"status": status.value, "timestamp": now.isoformat(), "note": "Request created"}],
        )
        if patient_id not in self.fhir.prior_auths:
            self.fhir.prior_auths[patient_id] = []
        self.fhir.prior_auths[patient_id].append(req.to_dict())
        return req

    def detect_and_create(
        self,
        patient_id: str,
        encounter_id: str,
        orders: list[str],
        clinical_indication: str,
    ) -> list[PriorAuthRequest]:
        """
        Scan a list of orders for PA-required services and auto-create requests.

        Args:
            orders: List of service/medication/lab names
            clinical_indication: SOAP assessment text to use as indication

        Returns:
            List of newly created PriorAuthRequest objects
        """
        created: list[PriorAuthRequest] = []
        for order in orders:
            for keyword, svc_type in PA_REQUIRED_KEYWORDS.items():
                if keyword.lower() in order.lower():
                    req = self.create(
                        patient_id=patient_id,
                        encounter_id=encounter_id,
                        service_type=svc_type,
                        service_description=order,
                        clinical_indication=clinical_indication[:500],
                        auto_submit=True,
                    )
                    created.append(req)
                    break  # one PA per order
        return created

    # ── Status transitions ────────────────────────────────────────────────────

    def _transition(
        self,
        patient_id: str,
        auth_id: str,
        new_status: AuthStatus,
        note: str = "",
        **kwargs,
    ) -> dict | None:
        """
        Apply a status transition.

        Returns the updated request dict or None if not found.
        """
        for req in self.fhir.prior_auths.get(patient_id, []):
            if req["auth_id"] == auth_id:
                req["status"] = new_status.value
                req["updated_at"] = datetime.now().isoformat()
                req["history"].append({
                    "status": new_status.value,
                    "timestamp": datetime.now().isoformat(),
                    "note": note,
                })
                for k, v in kwargs.items():
                    req[k] = v
                return req
        return None

    def submit(self, patient_id: str, auth_id: str, notes: str = "") -> dict | None:
        """Submit a DRAFT request to the insurer."""
        return self._transition(patient_id, auth_id, AuthStatus.SUBMITTED, notes)

    def mark_pending(self, patient_id: str, auth_id: str, insurer_ref: str = "", notes: str = "") -> dict | None:
        """Insurer has received the request and is reviewing."""
        return self._transition(
            patient_id, auth_id, AuthStatus.PENDING_REVIEW, notes,
            insurer_ref=insurer_ref,
        )

    def approve(self, patient_id: str, auth_id: str, approved_by: str = "", notes: str = "") -> dict | None:
        """Approve the request."""
        return self._transition(
            patient_id, auth_id, AuthStatus.APPROVED,
            notes or "Service approved",
            approved_by=approved_by,
        )

    def deny(self, patient_id: str, auth_id: str, reason: str, notes: str = "") -> dict | None:
        """Deny the request with a reason."""
        return self._transition(
            patient_id, auth_id, AuthStatus.DENIED,
            notes or "Request denied",
            denial_reason=reason,
        )

    def request_more_info(self, patient_id: str, auth_id: str, notes: str = "") -> dict | None:
        """Insurer requests additional supporting information."""
        return self._transition(patient_id, auth_id, AuthStatus.REQUIRES_MORE_INFO, notes)

    def add_supporting_doc(self, patient_id: str, auth_id: str, doc_text: str) -> bool:
        """Attach a supporting document (text) to the request."""
        for req in self.fhir.prior_auths.get(patient_id, []):
            if req["auth_id"] == auth_id:
                req["supporting_docs"].append(doc_text)
                req["updated_at"] = datetime.now().isoformat()
                return True
        return False

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_all(self, patient_id: str) -> list[dict]:
        """Return all prior auth requests for a patient (newest first)."""
        return list(reversed(self.fhir.prior_auths.get(patient_id, [])))

    def get_pending(self, patient_id: str) -> list[dict]:
        """Return requests requiring attention (not yet approved or denied)."""
        terminal = {AuthStatus.APPROVED.value, AuthStatus.DENIED.value}
        return [
            r for r in self.fhir.prior_auths.get(patient_id, [])
            if r["status"] not in terminal
        ]

    def get_by_encounter(self, patient_id: str, encounter_id: str) -> list[dict]:
        """Return all PA requests linked to a specific encounter."""
        return [
            r for r in self.fhir.prior_auths.get(patient_id, [])
            if r.get("encounter_id") == encounter_id
        ]

    def get_by_id(self, patient_id: str, auth_id: str) -> dict | None:
        """Return a specific prior auth request."""
        for req in self.fhir.prior_auths.get(patient_id, []):
            if req["auth_id"] == auth_id:
                return req
        return None


# ── Singleton ─────────────────────────────────────────────────────────────────
_prior_auth_service: PriorAuthService | None = None


def get_prior_auth_service(fhir_server=None) -> PriorAuthService:
    """Get or create the PriorAuthService singleton."""
    global _prior_auth_service
    if _prior_auth_service is None:
        if fhir_server is None:
            from src.ehr import get_fhir_server
            fhir_server = get_fhir_server()
        _prior_auth_service = PriorAuthService(fhir_server)
    return _prior_auth_service
