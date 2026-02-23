import asyncio
from src.history.history import get_history_service
from src.ehr.fhir_mock import get_fhir_server
history_service = get_history_service(get_fhir_server())
print(history_service.get_patient_timeline('P003'))
