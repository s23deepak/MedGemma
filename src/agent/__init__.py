"""Agent module initialization."""
from .medgemma_agent import MedGemmaAgent
from .tools import TOOLS, get_tool_by_name, format_tools_for_prompt, requires_approval

# Lazy imports for optional agents (require vLLM)
try:
    from .vllm_agent import MedGemmaVLLMAgent, is_vllm_available
except ImportError:
    MedGemmaVLLMAgent = None
    is_vllm_available = lambda: False

try:
    from .functiongemma_agent import FunctionGemmaAgent, is_functiongemma_available
except ImportError:
    FunctionGemmaAgent = None
    is_functiongemma_available = lambda: False

try:
    from .healthcare_agent import HealthcareAgent, AgentAction, AgentPlan
except ImportError:
    HealthcareAgent = None
    AgentAction = None
    AgentPlan = None

try:
    from .vllm_manager import VLLMModelManager, get_vllm_manager, is_vllm_manager_available
except ImportError:
    VLLMModelManager = None
    get_vllm_manager = None
    is_vllm_manager_available = lambda: False

__all__ = [
    # Core agents
    "MedGemmaAgent",
    "MedGemmaVLLMAgent",
    "FunctionGemmaAgent",
    "HealthcareAgent",
    # vLLM sleep-mode manager
    "VLLMModelManager",
    "get_vllm_manager",
    "is_vllm_manager_available",
    # Agent types
    "AgentAction",
    "AgentPlan",
    # Availability checks
    "is_vllm_available",
    "is_functiongemma_available",
    # Tool utilities
    "TOOLS",
    "get_tool_by_name",
    "format_tools_for_prompt",
    "requires_approval"
]
