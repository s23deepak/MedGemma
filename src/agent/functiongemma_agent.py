"""
FunctionGemma Agent - Tool Calling Router
Uses FunctionGemma (Gemma 3 270M) for efficient function calling and action routing.
"""

import json
import logging
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Check if vLLM is available
try:
    from vllm import LLM, SamplingParams
    VLLM_AVAILABLE = True
except ImportError:
    VLLM_AVAILABLE = False
    logger.warning("vLLM not installed. FunctionGemma will use Transformers fallback.")


class FunctionGemmaAgent:
    """
    FunctionGemma agent for tool calling and action routing.
    Designed to work alongside MedGemma for healthcare applications.
    
    Architecture:
        - FunctionGemma: Handles tool selection and routing (fast, 270M)
        - MedGemma: Handles medical reasoning when needed (detailed, 4B)
    """
    
    MODEL_ID = "google/functiongemma-3-270m"
    
    def __init__(
        self,
        gpu_memory_utilization: float = 0.3,  # Small model, minimal VRAM
        max_model_len: int = 2048
    ):
        """
        Initialize FunctionGemma agent.
        
        Args:
            gpu_memory_utilization: Fraction of GPU memory (0.3 is enough for 270M)
            max_model_len: Maximum sequence length
        """
    def _load_model(self, gpu_memory_utilization: float, max_model_len: int):
        """Load FunctionGemma model."""
        logger.info(f"Loading FunctionGemma: {self.MODEL_ID}")
        
        self.use_vllm = VLLM_AVAILABLE
        
        if self.use_vllm:
            logger.info("Using vLLM backend for FunctionGemma")
            self.model = LLM(
                model=self.MODEL_ID,
                gpu_memory_utilization=gpu_memory_utilization,
                max_model_len=max_model_len,
                trust_remote_code=True
            )
        else:
            logger.info("Using Transformers backend for FunctionGemma")
            from transformers import AutoModelForCausalLM, AutoTokenizer
            import torch
            
            self.tokenizer = AutoTokenizer.from_pretrained(self.MODEL_ID)
            # 270M model is small enough we might not strictly need 4-bit, but it helps
            self.hf_model = AutoModelForCausalLM.from_pretrained(
                self.MODEL_ID,
                device_map="auto",
                torch_dtype=torch.float16,
                trust_remote_code=True
            )
        
        logger.info("FunctionGemma loaded successfully")
    
    def register_tool(
        self,
        name: str,
        description: str,
        parameters: dict,
        handler: Callable | None = None
    ):
        """
        Register a tool that FunctionGemma can call.
        
        Args:
            name: Tool function name
            description: What the tool does
            parameters: JSON Schema for parameters
            handler: Optional callable to execute the tool
        """
        self.tools[name] = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters
            }
        }
        
        if handler:
            self.tool_handlers[name] = handler
    
    def register_tools_from_list(self, tools: list[dict]):
        """Register multiple tools from a list of tool definitions."""
        for tool in tools:
            func = tool.get("function", tool)
            self.tools[func["name"]] = tool
    
    def _format_tools_for_prompt(self) -> str:
        """Format registered tools for FunctionGemma prompt."""
        if not self.tools:
            return "No tools available."
        
        tool_specs = []
        for name, tool in self.tools.items():
            func = tool.get("function", tool)
            params = func.get("parameters", {}).get("properties", {})
            required = func.get("parameters", {}).get("required", [])
            
            param_strs = []
            for pname, pinfo in params.items():
                req = " (required)" if pname in required else ""
                param_strs.append(f"    - {pname}: {pinfo.get('description', '')}{req}")
            
            tool_specs.append(
                f"- {func['name']}: {func['description']}\n" +
                "\n".join(param_strs)
            )
        
        return "Available functions:\n" + "\n\n".join(tool_specs)
    
    def _parse_function_call(self, response: str) -> dict | None:
        """
        Parse FunctionGemma's response to extract function call.
        
        FunctionGemma uses a specific format for function calls.
        """
        # Try to find JSON function call in response
        patterns = [
            r'\{"tool":\s*"([^"]+)",\s*"parameters":\s*(\{[^}]+\})\}',
            r'\{"function":\s*"([^"]+)",\s*"arguments":\s*(\{[^}]+\})\}',
            r'\{"name":\s*"([^"]+)",\s*"arguments":\s*(\{[^}]+\})\}',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response, re.DOTALL)
            if match:
                try:
                    return {
                        "name": match.group(1),
                        "arguments": json.loads(match.group(2))
                    }
                except json.JSONDecodeError:
                    continue
        
        # Try direct JSON parse
        try:
            # Look for any JSON block
            json_match = re.search(r'\{[^{}]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
                if "tool" in data or "function" in data or "name" in data:
                    name = data.get("tool") or data.get("function") or data.get("name")
                    args = data.get("parameters") or data.get("arguments") or {}
                    return {"name": name, "arguments": args}
        except json.JSONDecodeError:
            pass
        
        return None
    
    def route_query(
        self,
        query: str,
        context: str = "",
        available_actions: list[str] | None = None
    ) -> dict:
        """
        Route a user query to the appropriate function.
        
        Args:
            query: User's request
            context: Additional context (patient info, current state)
            available_actions: Optional subset of tools to consider
            
        Returns:
            dict with keys:
                - needs_medical_reasoning: bool - whether to escalate to MedGemma
                - function_call: dict | None - parsed function call
                - raw_response: str - model's raw output
        """
        # Build prompt
        tools_spec = self._format_tools_for_prompt()
        
        prompt = f"""You are a healthcare agent router. Your job is to:
1. Determine what action to take for the user's request
2. Call the appropriate function with correct parameters
3. If the request requires medical reasoning or diagnosis, indicate that

{tools_spec}

Special actions:
- If the request needs medical reasoning, diagnosis, or clinical analysis, respond with:
  {{"tool": "escalate_to_medgemma", "parameters": {{"reason": "..."}}}}

Context: {context}

User request: {query}

Respond with a JSON function call:"""

        if self.use_vllm:
            sampling_params = SamplingParams(
                temperature=0.1,  # Low temp for deterministic routing
                top_p=0.95,
                max_tokens=256,
                stop=["User:", "\n\n"]
            )
            
            outputs = self.model.generate([prompt], sampling_params=sampling_params)
            response = outputs[0].outputs[0].text.strip()
        else:
            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.hf_model.device)
            outputs = self.hf_model.generate(
                **inputs,
                max_new_tokens=256,
                temperature=0.1,
                top_p=0.95,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id
            )
            response = self.tokenizer.decode(
                outputs[0][inputs.input_ids.shape[1]:], 
                skip_special_tokens=True
            ).strip()
            
            # Manual stop sequence handling
            for stop_seq in ["User:", "\n\n"]:
                if stop_seq in response:
                    response = response[:response.index(stop_seq)].strip()
        
        # Parse the function call
        function_call = self._parse_function_call(response)
        
        # Check if needs medical reasoning
        needs_medical = False
        if function_call:
            if function_call["name"] == "escalate_to_medgemma":
                needs_medical = True
            elif function_call["name"] in ["analyze_medical_image", "generate_soap_note"]:
                needs_medical = True
        
        return {
            "needs_medical_reasoning": needs_medical,
            "function_call": function_call,
            "raw_response": response
        }
    
    def execute_function(self, function_call: dict) -> Any:
        """
        Execute a function call if a handler is registered.
        
        Args:
            function_call: dict with 'name' and 'arguments'
            
        Returns:
            Result from the function handler
        """
        name = function_call.get("name")
        args = function_call.get("arguments", {})
        
        if name not in self.tool_handlers:
            return {"error": f"No handler registered for function: {name}"}
        
        try:
            return self.tool_handlers[name](**args)
        except Exception as e:
            logger.error(f"Error executing {name}: {e}")
            return {"error": str(e)}
    
    def plan_actions(
        self,
        goal: str,
        context: str = "",
        max_steps: int = 5
    ) -> list[dict]:
        """
        Generate a multi-step action plan for a complex goal.
        
        Args:
            goal: The overall objective
            context: Current context/state
            max_steps: Maximum number of actions to plan
            
        Returns:
            List of function calls to execute in order
        """
        tools_spec = self._format_tools_for_prompt()
        
        prompt = f"""You are a healthcare workflow planner. Create a step-by-step action plan.

{tools_spec}

Goal: {goal}
Context: {context}

Generate a JSON array of function calls to achieve this goal (max {max_steps} steps):
[
  {{"tool": "...", "parameters": {{...}}}},
  ...
]

Action plan:"""

        if self.use_vllm:
            sampling_params = SamplingParams(
                temperature=0.2,
                top_p=0.95,
                max_tokens=512,
                stop=["Goal:", "Context:"]
            )
            
            outputs = self.model.generate([prompt], sampling_params=sampling_params)
            response = outputs[0].outputs[0].text.strip()
        else:
            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.hf_model.device)
            outputs = self.hf_model.generate(
                **inputs,
                max_new_tokens=512,
                temperature=0.2,
                top_p=0.95,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id
            )
            response = self.tokenizer.decode(
                outputs[0][inputs.input_ids.shape[1]:], 
                skip_special_tokens=True
            ).strip()
            
            # Manual stop sequence handling
            for stop_seq in ["Goal:", "Context:"]:
                if stop_seq in response:
                    response = response[:response.index(stop_seq)].strip()
        
        # Parse action plan
        try:
            # Find JSON array
            array_match = re.search(r'\[[\s\S]*\]', response)
            if array_match:
                actions = json.loads(array_match.group())
                return actions[:max_steps]
        except json.JSONDecodeError:
            pass
        
        # Fall back to single action
        single_action = self._parse_function_call(response)
        return [single_action] if single_action else []


def is_functiongemma_available() -> bool:
    """Check if FunctionGemma can be loaded."""
    return True
