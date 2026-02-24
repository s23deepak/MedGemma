"""
Inpatient workflow modules.

Exposes service getters for the 4 inpatient feature modules:
  - InpatientRoundingService  (daily progress notes + to-do list)
  - SBARHandoffService        (structured sign-out with completeness audit)
  - InpatientSafetyService    (watchlist: VTE, Foley, high-risk meds)
  - InpatientDischargePlanner (discharge summary + readmission risk)
"""

from .rounding import InpatientRoundingService, get_rounding_service
from .handoff import SBARHandoffService, get_sbar_service
from .safety import InpatientSafetyService, get_safety_service
from .discharge import InpatientDischargePlanner, get_discharge_planner

__all__ = [
    "InpatientRoundingService", "get_rounding_service",
    "SBARHandoffService", "get_sbar_service",
    "InpatientSafetyService", "get_safety_service",
    "InpatientDischargePlanner", "get_discharge_planner",
]
