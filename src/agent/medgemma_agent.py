"""
MedGemma Agent - Core multimodal reasoning engine
Handles image analysis, tool calling, and clinical decision support.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

import torch
from PIL import Image
from transformers import AutoProcessor, AutoModelForImageTextToText, BitsAndBytesConfig

from .tools import TOOLS, format_tools_for_prompt

logger = logging.getLogger(__name__)


class MedGemmaAgent:
    """
    MedGemma-based clinical decision support agent.
    Handles multimodal input (images + text) and tool calling.
    """
    
    MODEL_ID = "google/medgemma-1.5-4b-it"
    
    def __init__(self, device: str = "cuda", load_in_4bit: bool = True):
        """
        Initialize the MedGemma agent.
        
        Args:
            device: Device to load the model on
            load_in_4bit: Whether to use 4-bit quantization (recommended for 8GB VRAM)
        """
        self.device = device
        self.model = None
        self.processor = None
        self.tool_handlers = {}
        
        self._load_model(load_in_4bit)
    
    def _load_model(self, load_in_4bit: bool):
        """Load the MedGemma model with optional quantization."""
        logger.info(f"Loading MedGemma model: {self.MODEL_ID}")
        
        # Configure quantization for 8GB VRAM
        if load_in_4bit:
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True
            )
            logger.info("Using 4-bit quantization for memory efficiency")
        else:
            quantization_config = None
        
        # Load processor
        self.processor = AutoProcessor.from_pretrained(
            self.MODEL_ID,
            trust_remote_code=True
        )
        
        # Load model
        self.model = AutoModelForImageTextToText.from_pretrained(
            self.MODEL_ID,
            quantization_config=quantization_config,
            device_map="auto",
            torch_dtype=torch.bfloat16,
            trust_remote_code=True
        )
        
        logger.info("MedGemma model loaded successfully")
    
    def register_tool_handler(self, tool_name: str, handler: callable):
        """Register a handler function for a tool."""
        self.tool_handlers[tool_name] = handler
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for clinical assistant behavior."""
        return """You are a clinical decision support assistant powered by MedGemma.

Your role is to assist physicians during patient encounters by:
1. Analyzing medical images when provided
2. Identifying potential findings that may need attention
3. Helping generate structured SOAP documentation
4. Flagging potential missed diagnoses or critical findings

IMPORTANT GUIDELINES:
- Always present findings as suggestions, not definitive diagnoses
- Highlight any urgent or critical findings prominently
- Be thorough but concise in your analysis
- Consider the patient's history and context when available
- Flag any inconsistencies between reported symptoms and image findings

When you need to perform actions, use the available tools by responding with a JSON tool call in this format:
```json
{"tool": "tool_name", "parameters": {...}}
```

""" + format_tools_for_prompt()
    
    def analyze_image(
        self,
        image_path: str | Path,
        clinical_context: str = "",
        modality: str = "xray",
        patient_symptoms: list[str] | None = None,
        chief_complaint: str = "",
        body_region: str = ""
    ) -> dict:
        """
        Analyze a medical image with artifact detection and clinical correlation.
        
        Args:
            image_path: Path to the medical image
            clinical_context: Clinical context from physician dictation
            modality: Imaging modality (xray, ct, mri, ultrasound)
            patient_symptoms: Patient's reported symptoms for correlation
            chief_complaint: Primary reason for visit
            body_region: Body region being imaged
            
        Returns:
            Structured analysis results with artifact and correlation data
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        # Load image
        image = Image.open(image_path).convert("RGB")
        
        # Build symptom context
        symptoms_str = ", ".join(patient_symptoms) if patient_symptoms else "Not provided"
        complaint_str = chief_complaint if chief_complaint else "Not provided"
        
        # Enhanced analysis prompt with artifact detection and clinical correlation
        prompt = f"""Analyze this {modality.upper()} image for a clinical encounter.

Clinical Context: {clinical_context if clinical_context else "Not provided"}
Patient's Chief Complaint: {complaint_str}
Patient's Reported Symptoms: {symptoms_str}
Body Region: {body_region if body_region else "Not specified"}

Please provide a structured analysis with ALL of the following sections:

## 1. IMAGE QUALITY & ARTIFACTS
Assess the technical quality of this image:
- **Overall Quality**: [diagnostic / acceptable / degraded / non-diagnostic]
- **Artifacts Found**: List any artifacts detected:
  - Motion artifacts (patient movement during acquisition)
  - Metal artifacts (implants, jewelry, external objects)
  - Positioning errors (rotation, tilt, incomplete coverage)
  - Exposure issues (overexposure, underexposure)
  - Other artifacts (aliasing, truncation, susceptibility)
- **Impact on Interpretation**: [none / limited / significant]
- **Recommendation**: [proceed with interpretation / repeat study with corrections]
If no artifacts are found, state "No significant artifacts identified."

## 2. KEY FINDINGS
List ALL observable findings, organized by clinical significance.

## 3. CLINICAL CORRELATION
For EACH finding, classify it as:
- **CLINICALLY CORRELATED**: Finding matches the patient's symptoms/complaint
- **INCIDENTAL**: Finding is present but does NOT relate to the patient's symptoms
  - For incidental findings, note their prevalence in asymptomatic populations
  - Example: "Disc bulge at L4-L5 — INCIDENTAL. Found in 30-40% of asymptomatic adults. Does not explain the patient's knee pain."

IMPORTANT: A radiological finding does NOT automatically mean pathology. 
For example, disc bulges, osteophytes, and degenerative changes are extremely 
common in asymptomatic individuals and should be correlated with clinical symptoms.

## 4. DIFFERENTIAL CONSIDERATIONS
Possible diagnoses to consider, prioritized by clinical correlation.

## 5. RECOMMENDATIONS
Suggested next steps, distinguishing between:
- Actions needed for correlated findings
- Follow-up (if any) for incidental findings

Be thorough but concise. Flag any urgent findings prominently with ⚠️."""
        
        # Prepare inputs
        messages = [
            {"role": "user", "content": [
                {"type": "image"},
                {"type": "text", "text": self._build_system_prompt() + "\n\n" + prompt}
            ]}
        ]
        
        text = self.processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=False
        )
        
        inputs = self.processor(
            text=text,
            images=image,
            return_tensors="pt"
        ).to(self.model.device)
        
        # Generate response
        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=1536,
                do_sample=True,
                temperature=0.3,
                top_p=0.9
            )
        
        # Decode response
        response = self.processor.decode(
            outputs[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True
        )
        
        # Post-process with clinical correlator if symptoms provided
        correlation_result = None
        if patient_symptoms:
            correlator = get_clinical_correlator()
            
            # Extract findings from response (simple heuristic)
            findings = self._extract_findings_from_response(response)
            if findings:
                correlation_result = correlator.correlate(
                    findings=findings,
                    symptoms=patient_symptoms,
                    chief_complaint=chief_complaint,
                    body_region=body_region,
                    modality=modality
                )
        
        result = {
            "modality": modality,
            "image_path": str(image_path),
            "analysis": response,
            "clinical_context": clinical_context,
            "chief_complaint": chief_complaint,
            "patient_symptoms": patient_symptoms or [],
        }
        
        if correlation_result:
            result["clinical_correlation"] = correlation_result.to_dict()
        
        return result
    
    def _extract_findings_from_response(self, response: str) -> list[str]:
        """Extract individual findings from model response text."""
        findings = []
        in_findings_section = False
        
        for line in response.split("\n"):
            line = line.strip()
            # Look for findings section headers
            if "KEY FINDINGS" in line.upper() or "FINDINGS" in line.upper():
                in_findings_section = True
                continue
            # Stop at next section
            if in_findings_section and line.startswith("## "):
                in_findings_section = False
                continue
            # Extract bullet points in findings section
            if in_findings_section and (line.startswith("- ") or line.startswith("* ")):
                finding = line.lstrip("-* ").strip()
                # Clean up markdown bold
                finding = finding.replace("**", "")
                if finding and len(finding) > 5:
                    findings.append(finding)
        
        return findings
    
    def process_encounter(
        self,
        transcription: str,
        patient_context: dict | None = None,
        image_path: str | None = None,
        image_modality: str = "xray"
    ) -> dict:
        """
        Process a complete clinical encounter with all available data.
        
        Args:
            transcription: Physician dictation transcription
            patient_context: EHR data for the patient
            image_path: Optional path to medical image
            image_modality: Type of imaging
            
        Returns:
            Complete encounter analysis with SOAP note
        """
        results = {
            "transcription": transcription,
            "patient_context": patient_context,
            "image_analysis": None,
            "soap_note": None,
            "alerts": []
        }
        
        # Analyze image if provided
        if image_path:
            results["image_analysis"] = self.analyze_image(
                image_path,
                clinical_context=transcription,
                modality=image_modality
            )
        
        # Build comprehensive prompt for SOAP generation
        context_parts = [f"**Physician Dictation:**\n{transcription}"]
        
        if patient_context:
            context_parts.append(f"\n**Patient EHR Context:**\n{json.dumps(patient_context, indent=2)}")
        
        if results["image_analysis"]:
            context_parts.append(f"\n**Image Analysis ({image_modality.upper()}):**\n{results['image_analysis']['analysis']}")
        
        prompt = f"""Based on the following clinical encounter data, generate a complete SOAP note.

{chr(10).join(context_parts)}

Generate a structured SOAP note with the following sections:

## Subjective
[Patient's reported symptoms and history]

## Objective  
[Physical examination findings, vital signs, and imaging results]

## Assessment
[Clinical impression, differential diagnoses, and reasoning]

## Plan
[Treatment plan, follow-up, and any referrals]

---

Additionally, identify:
1. **Potential Missed Diagnoses**: Any conditions suggested by the data that may not have been explicitly considered
2. **Critical Alerts**: Any urgent findings requiring immediate attention
3. **Inconsistencies**: Any discrepancies between reported symptoms and objective findings"""

        # Prepare inputs (text only for SOAP generation)
        messages = [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": prompt}
        ]
        
        inputs = self.processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt"
        ).to(self.model.device)
        
        # Generate SOAP note
        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=2048,
                do_sample=True,
                temperature=0.4,
                top_p=0.9
            )
        
        response = self.processor.decode(
            outputs[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True
        )
        
        results["soap_note"] = response
        
        # Extract any critical alerts
        if "CRITICAL" in response.upper() or "URGENT" in response.upper():
            results["alerts"].append({
                "level": "critical",
                "message": "Critical finding detected - please review immediately"
            })
        
        return results
    
    def chat(self, message: str, history: list[dict] | None = None) -> str:
        """
        Simple chat interface for conversational interactions.
        
        Args:
            message: User message
            history: Optional conversation history
            
        Returns:
            Model response
        """
        messages = [{"role": "system", "content": [{"type": "text", "text": self._build_system_prompt()}]}]
        
        if history:
            messages.extend(history)
        
        messages.append({"role": "user", "content": [{"type": "text", "text": message}]})
        
        inputs = self.processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt"
        ).to(self.model.device)
        
        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=1024,
                do_sample=True,
                temperature=0.5,
                top_p=0.9
            )
        
        return self.processor.decode(
            outputs[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True
        )
