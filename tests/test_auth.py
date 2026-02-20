"""
Tests for src/auth/auth.py — Role-based authentication
"""

from src.auth.auth import (
    Role,
    authenticate,
    has_permission,
    get_accessible_features,
    get_user_by_email,
    ROLE_PERMISSIONS,
)


class TestAuthentication:
    def test_valid_credentials(self):
        user = authenticate("dr.smith@hospital.org", "doc123")
        assert user is not None
        assert user["role"] == Role.DOCTOR
        assert user["name"] == "Dr. Sarah Smith"

    def test_invalid_password(self):
        user = authenticate("dr.smith@hospital.org", "wrongpassword")
        assert user is None

    def test_unknown_email(self):
        user = authenticate("nobody@hospital.org", "pass")
        assert user is None


class TestRolePermissions:
    def test_doctor_permissions(self):
        features = get_accessible_features(Role.DOCTOR)
        assert "history" in features
        assert "compliance" in features
        assert "council" in features
        assert "encounters" in features

    def test_patient_permissions(self):
        features = get_accessible_features(Role.PATIENT)
        assert features == ["patient-portal"]
        assert "history" not in features

    def test_has_permission_checks(self):
        assert has_permission(Role.ADMIN, "admin") is True
        assert has_permission(Role.NURSE, "compliance") is False
        assert has_permission(Role.PATIENT, "patient-portal") is True
        assert has_permission("doctor", "encounters") is True  # string role
        assert has_permission("invalid_role", "anything") is False
