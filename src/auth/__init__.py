"""Auth module initialization."""
from .auth import Role, has_permission, get_accessible_features, authenticate, get_user_by_email
from .prior_auth import PriorAuthService, AuthStatus, get_prior_auth_service

__all__ = [
    "Role", "has_permission", "get_accessible_features", "authenticate", "get_user_by_email",
    "PriorAuthService", "AuthStatus", "get_prior_auth_service",
]
