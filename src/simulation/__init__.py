"""Clinical simulation module — resident training environment."""

from .simulator import SimulationEngine, get_simulation_engine
from .cases import list_cases, get_case

__all__ = ["SimulationEngine", "get_simulation_engine", "list_cases", "get_case"]
