"""
Healthcare Agent - Dual-Model Orchestrator
Combines FunctionGemma (routing) + MedGemma (reasoning) for intelligent healthcare automation.
"""

import json
import logging
from typing import Any, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AgentAction:
    """Represents an action to be executed."""
    tool_name: str
    arguments: dict
    requires_approval: bool = False
    result: Any = None
    error: str | None = None


@dataclass
class AgentPlan:
    """Multi-step execution plan."""
    goal: str
    actions: list[AgentAction] = field(default_factory=list)
    current_step: int = 0
    completed: bool = False


class HealthcareAgent:
    """
    Dual-model healthcare agent combining:
    - FunctionGemma (270M) for tool routing and action planning
    - MedGemma (4B) for medical reasoning and clinical analysis
    
    Architecture:
    ```
    User Query → FunctionGemma → [Simple Action] → Execute Tool
                      ↓
            [Complex Medical Query]
                      ↓
                 MedGemma → Analyze → Synthesize Response
    ```
    """
    
    def __init__(
        self,
        use_vllm: bool = True,
        load_functiongemma: bool = True,
        load_medgemma: bool = True,
        simulated: bool = False
    ):
        """
        Initialize the healthcare agent.
        
        Args:
            use_vllm: Use vLLM for inference
            load_functiongemma: Load FunctionGemma for routing
            load_medgemma: Load MedGemma for medical reasoning
            simulated: Use simulated responses (no GPU)
        """
        self.simulated = simulated
        self.function_agent = None
        self.medical_agent = None
        self.tools: dict[str, Callable] = {}
        
        if not simulated:
            if load_functiongemma:
                self._load_function_agent(use_vllm)
            if load_medgemma:
                self._load_medical_agent(use_vllm)
        
        # Register default healthcare tools
        self._register_default_tools()
    
    def _load_function_agent(self, use_vllm: bool):
        """Load FunctionGemma for routing."""
        try:
            if use_vllm:
                from .functiongemma_agent import FunctionGemmaAgent, is_functiongemma_available
                if is_functiongemma_available():
                    self.function_agent = FunctionGemmaAgent()
                    logger.info("FunctionGemma loaded for routing")
        except Exception as e:
            logger.warning(f"Could not load FunctionGemma: {e}")
    
    def _load_medical_agent(self, use_vllm: bool):
        """Load MedGemma for medical reasoning."""
        try:
            if use_vllm:
                from .vllm_agent import MedGemmaVLLMAgent, is_vllm_available
                if is_vllm_available():
                    self.medical_agent = MedGemmaVLLMAgent()
                    logger.info("MedGemma (vLLM) loaded for reasoning")
            else:
                from .medgemma_agent import MedGemmaAgent
                self.medical_agent = MedGemmaAgent(load_in_4bit=True)
                logger.info("MedGemma (Transformers) loaded for reasoning")
        except Exception as e:
            logger.warning(f"Could not load MedGemma: {e}")
    
    def _register_default_tools(self):
        """Register default healthcare tool handlers."""
        # These are placeholder implementations
        # In production, these would connect to real systems
        
        self.register_tool("fetch_patient_ehr", self._tool_fetch_ehr)
        self.register_tool("search_fhir_observations", self._tool_search_fhir)
        self.register_tool("schedule_appointment", self._tool_schedule_appointment)
        self.register_tool("order_lab_tests", self._tool_order_labs)
        self.register_tool("notify_care_team", self._tool_notify_team)
        self.register_tool("check_drug_interactions", self._tool_check_interactions)
        self.register_tool("retrieve_prior_imaging", self._tool_retrieve_imaging)
        self.register_tool("update_ehr", self._tool_update_ehr)
    
    def register_tool(self, name: str, handler: Callable):
        """Register a tool with its handler function."""
        self.tools[name] = handler
        
        # Also register with FunctionGemma if available
        if self.function_agent:
            self.function_agent.tool_handlers[name] = handler
    
    # ==================== Core Agent Methods ====================
    
    def process_query(
        self,
        query: str,
        patient_context: dict | None = None,
        image_path: str | None = None
    ) -> dict:
        """
        Process a user query through the dual-model pipeline.
        
        Args:
            query: User's natural language request
            patient_context: Current patient EHR context
            image_path: Optional medical image path
            
        Returns:
            dict with:
                - response: Final response text
                - actions_taken: List of executed actions
                - medical_analysis: MedGemma analysis if performed
        """
        result = {
            "response": "",
            "actions_taken": [],
            "medical_analysis": None,
            "requires_approval": False
        }
        
        # Build context string
        context = self._build_context(patient_context, image_path)
        
        if self.simulated:
            return self._simulated_response(query, context)
        
        # Step 1: Route through FunctionGemma
        if self.function_agent:
            routing = self.function_agent.route_query(query, context)
            
            if routing["needs_medical_reasoning"]:
                # Escalate to MedGemma
                result["medical_analysis"] = self._medical_reasoning(
                    query, patient_context, image_path
                )
                result["response"] = result["medical_analysis"].get("response", "")
            elif routing["function_call"]:
                # Execute the function
                action_result = self._execute_action(routing["function_call"])
                result["actions_taken"].append(action_result)
                result["response"] = self._format_action_result(action_result)
        else:
            # Fallback: route everything to MedGemma
            result["medical_analysis"] = self._medical_reasoning(
                query, patient_context, image_path
            )
            result["response"] = result["medical_analysis"].get("response", "")
        
        return result
    
    def execute_workflow(
        self,
        goal: str,
        patient_context: dict | None = None,
        auto_execute: bool = False
    ) -> AgentPlan:
        """
        Plan and optionally execute a multi-step workflow.
        
        Args:
            goal: Overall workflow objective
            patient_context: Current patient context
            auto_execute: Whether to execute actions automatically
            
        Returns:
            AgentPlan with planned/executed actions
        """
        context = self._build_context(patient_context)
        plan = AgentPlan(goal=goal)
        
        if self.simulated:
            plan.actions = self._simulated_plan(goal)
            return plan
        
        # Generate action plan with FunctionGemma
        if self.function_agent:
            action_list = self.function_agent.plan_actions(goal, context)
            
            for action_dict in action_list:
                action = AgentAction(
                    tool_name=action_dict.get("tool", action_dict.get("name", "")),
                    arguments=action_dict.get("parameters", action_dict.get("arguments", {})),
                    requires_approval=self._requires_approval(action_dict.get("tool", ""))
                )
                plan.actions.append(action)
        
        # Execute if auto_execute is enabled
        if auto_execute:
            for i, action in enumerate(plan.actions):
                if action.requires_approval:
                    # Stop at actions requiring approval
                    plan.current_step = i
                    break
                
                result = self._execute_action({
                    "name": action.tool_name,
                    "arguments": action.arguments
                })
                action.result = result
                plan.current_step = i + 1
            
            plan.completed = plan.current_step >= len(plan.actions)
        
        return plan
    
    # ==================== Tool Implementations ====================
    
    def _tool_fetch_ehr(self, patient_id: str) -> dict:
        """Fetch patient EHR from FHIR server."""
        try:
            from src.ehr import get_fhir_server
            fhir = get_fhir_server()
            return fhir.get_patient_summary(patient_id)
        except Exception as e:
            return {"error": str(e)}
    
    def _tool_search_fhir(self, code: str, patient_id: str = None) -> dict:
        """Search FHIR observations."""
        try:
            from src.ehr import get_fhir_server
            fhir = get_fhir_server()
            return {"observations": fhir.search_observations(patient_id, code)}
        except Exception as e:
            return {"error": str(e), "observations": []}
    
    def _tool_schedule_appointment(
        self,
        patient_id: str,
        specialty: str = "general",
        urgency: str = "routine"
    ) -> dict:
        """Schedule a patient appointment."""
        # Mock implementation
        return {
            "status": "scheduled",
            "patient_id": patient_id,
            "specialty": specialty,
            "urgency": urgency,
            "appointment_id": f"APT-{patient_id}-001",
            "message": f"Appointment scheduled with {specialty} ({urgency})"
        }
    
    def _tool_order_labs(self, patient_id: str, tests: list[str]) -> dict:
        """Order laboratory tests."""
        return {
            "status": "ordered",
            "patient_id": patient_id,
            "tests": tests,
            "order_id": f"LAB-{patient_id}-001",
            "message": f"Lab orders placed: {', '.join(tests)}"
        }
    
    def _tool_notify_team(
        self,
        patient_id: str,
        message: str,
        urgency: str = "normal"
    ) -> dict:
        """Send notification to care team."""
        return {
            "status": "sent",
            "patient_id": patient_id,
            "urgency": urgency,
            "notification_id": f"NOT-{patient_id}-001",
            "message": f"Notification sent: {message}"
        }
    
    def _tool_check_interactions(self, medications: list[str]) -> dict:
        """Check drug interactions."""
        try:
            from src.clinical import get_clinical_intelligence
            ci = get_clinical_intelligence()
            interactions = ci.check_drug_interactions(medications)
            return {
                "checked": True,
                "medications": medications,
                "interactions": [i.to_dict() for i in interactions]
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _tool_retrieve_imaging(
        self,
        patient_id: str,
        modality: str = "xray"
    ) -> dict:
        """Retrieve prior imaging studies."""
        # Mock implementation
        return {
            "patient_id": patient_id,
            "modality": modality,
            "studies": [
                {"study_id": "IMG-001", "date": "2025-12-15", "modality": modality}
            ]
        }
    
    def _tool_update_ehr(
        self,
        patient_id: str,
        encounter_note: str,
        new_conditions: list[str] = None,
        new_medications: list[str] = None
    ) -> dict:
        """Update patient EHR (requires approval)."""
        return {
            "status": "pending_approval",
            "patient_id": patient_id,
            "changes": {
                "encounter_note": len(encounter_note),
                "new_conditions": new_conditions or [],
                "new_medications": new_medications or []
            },
            "message": "EHR update queued for physician approval"
        }
    
    # ==================== Helper Methods ====================
    
    def _build_context(
        self,
        patient_context: dict | None,
        image_path: str | None = None
    ) -> str:
        """Build context string from available data."""
        parts = []
        
        if patient_context:
            patient = patient_context.get("patient", {})
            parts.append(f"Patient: {patient.get('name', 'Unknown')}, {patient.get('age', '?')} y/o")
            
            conditions = patient_context.get("conditions", [])
            if conditions:
                cond_names = [c.get("name", "") for c in conditions]
                parts.append(f"Conditions: {', '.join(cond_names)}")
            
            meds = patient_context.get("medications", [])
            if meds:
                med_names = [m.get("name", "") for m in meds]
                parts.append(f"Medications: {', '.join(med_names)}")
        
        if image_path:
            parts.append(f"Medical image available: {image_path}")
        
        return "; ".join(parts) if parts else "No context available"
    
    def _medical_reasoning(
        self,
        query: str,
        patient_context: dict | None,
        image_path: str | None
    ) -> dict:
        """Perform medical reasoning with MedGemma."""
        if not self.medical_agent:
            return {"response": "Medical reasoning unavailable", "error": "MedGemma not loaded"}
        
        if image_path:
            result = self.medical_agent.analyze_image(
                image_path,
                clinical_context=query
            )
            return {"response": result.get("analysis", ""), "image_analysis": result}
        else:
            result = self.medical_agent.process_encounter(
                transcription=query,
                patient_context=patient_context
            )
            return {"response": result.get("soap_note", ""), "encounter": result}
    
    def _execute_action(self, function_call: dict) -> dict:
        """Execute a function call."""
        name = function_call.get("name", "")
        args = function_call.get("arguments", {})
        
        if name not in self.tools:
            return {"tool": name, "error": f"Unknown tool: {name}"}
        
        try:
            result = self.tools[name](**args)
            return {"tool": name, "arguments": args, "result": result}
        except Exception as e:
            return {"tool": name, "arguments": args, "error": str(e)}
    
    def _format_action_result(self, action_result: dict) -> str:
        """Format action result as readable response."""
        if "error" in action_result:
            return f"Error: {action_result['error']}"
        
        result = action_result.get("result", {})
        if isinstance(result, dict):
            msg = result.get("message", json.dumps(result, indent=2))
            return msg
        return str(result)
    
    def _requires_approval(self, tool_name: str) -> bool:
        """Check if a tool requires physician approval."""
        approval_required = ["update_ehr", "order_labs", "schedule_appointment"]
        return tool_name in approval_required
    
    def _simulated_response(self, query: str, context: str) -> dict:
        """Generate simulated response for testing."""
        return {
            "response": f"[Simulated] Processed query: {query[:50]}...",
            "actions_taken": [],
            "medical_analysis": {
                "response": "Simulated medical analysis",
                "simulated": True
            },
            "requires_approval": False
        }
    
    def _simulated_plan(self, goal: str) -> list[AgentAction]:
        """Generate simulated action plan."""
        return [
            AgentAction(
                tool_name="fetch_patient_ehr",
                arguments={"patient_id": "P001"}
            ),
            AgentAction(
                tool_name="check_drug_interactions",
                arguments={"medications": ["Lisinopril", "Aspirin"]}
            )
        ]
