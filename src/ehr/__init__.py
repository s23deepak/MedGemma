"""EHR module initialization."""
from .fhir_mock import MockFHIRServer
from .fhir_mock import get_fhir_server as _get_mock_fhir_server

# Firestore backend (optional — requires firebase-admin + credentials)
try:
    from .firestore_server import FirestoreFHIRServer
except ImportError:
    FirestoreFHIRServer = None


def get_fhir_server():
    """
    Return the active FHIR server.

    Uses FirestoreFHIRServer when Firebase is configured (firebase-key.json
    present), otherwise falls back to the in-memory MockFHIRServer.
    """
    if FirestoreFHIRServer is not None:
        try:
            from src.config.firebase_config import is_firebase_available
            if is_firebase_available():
                return FirestoreFHIRServer()
        except Exception:
            pass
    return _get_mock_fhir_server()


__all__ = ["MockFHIRServer", "FirestoreFHIRServer", "get_fhir_server"]
