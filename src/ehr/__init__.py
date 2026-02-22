"""EHR module initialization."""
from .fhir_mock import MockFHIRServer, get_fhir_server

# Firestore backend (optional — requires firebase-admin + credentials)
try:
    from .firestore_server import FirestoreFHIRServer
except ImportError:
    FirestoreFHIRServer = None

__all__ = ["MockFHIRServer", "FirestoreFHIRServer", "get_fhir_server"]
