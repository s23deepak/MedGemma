"""EHR module initialization."""
from .fhir_mock import MockFHIRServer, get_fhir_server

__all__ = ["MockFHIRServer", "get_fhir_server"]
