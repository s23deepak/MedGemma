"""
Role-Based Authentication Module
Defines roles and access control for clinical features.
"""

from enum import Enum
from functools import wraps
from typing import Callable


class Role(str, Enum):
    """User roles in the clinical system."""
    ADMIN = "admin"
    DOCTOR = "doctor"
    RESIDENT = "resident"
    NURSE = "nurse"
    PATIENT = "patient"


# Role-based access permissions
ROLE_PERMISSIONS = {
    Role.ADMIN: ["history", "compliance", "council", "encounters", "admin"],
    Role.DOCTOR: ["history", "compliance", "council", "encounters"],
    Role.RESIDENT: ["history", "council", "encounters"],
    Role.NURSE: ["history", "encounters"],
    Role.PATIENT: ["patient-portal"],
}


def has_permission(role: Role | str, feature: str) -> bool:
    """Check if a role has permission to access a feature."""
    if isinstance(role, str):
        try:
            role = Role(role)
        except ValueError:
            return False
    return feature in ROLE_PERMISSIONS.get(role, [])


def get_accessible_features(role: Role | str) -> list[str]:
    """Get list of features accessible to a role."""
    if isinstance(role, str):
        try:
            role = Role(role)
        except ValueError:
            return []
    return ROLE_PERMISSIONS.get(role, [])


# Mock user database for demonstration
MOCK_USERS = {
    "admin@hospital.org": {"password": "admin123", "role": Role.ADMIN, "name": "System Admin"},
    "dr.smith@hospital.org": {"password": "doc123", "role": Role.DOCTOR, "name": "Dr. Sarah Smith"},
    "dr.jones@hospital.org": {"password": "doc123", "role": Role.DOCTOR, "name": "Dr. Michael Jones"},
    "resident.lee@hospital.org": {"password": "res123", "role": Role.RESIDENT, "name": "Dr. Emily Lee"},
    "nurse.garcia@hospital.org": {"password": "nurse123", "role": Role.NURSE, "name": "Maria Garcia, RN"},
    "patient.p001@email.com": {"password": "patient123", "role": Role.PATIENT, "name": "John Doe"},
}


def authenticate(email: str, password: str) -> dict | None:
    """Authenticate a user and return their info."""
    user = MOCK_USERS.get(email)
    if user and user["password"] == password:
        return {
            "email": email,
            "role": user["role"],
            "name": user["name"]
        }
    return None


def get_user_by_email(email: str) -> dict | None:
    """Get user info by email (without password check)."""
    user = MOCK_USERS.get(email)
    if user:
        return {
            "email": email,
            "role": user["role"],
            "name": user["name"]
        }
    return None
