"""
MedGemma vLLM Agent - High-performance multimodal inference
Uses vLLM for faster inference compared to HuggingFace Transformers.
"""

import json
import logging
from pathlib import Path
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

# Check if vLLM is available
try:
    from vllm import LLM, SamplingParams
    VLLM_AVAILABLE = True
except ImportError:
    VLLM_AVAILABLE = False
    logger.warning("vLLM not installed. Use `pip install vllm` for faster inference.")


class MedGemmaVLLMAgent:
    """
    MedGemma agent using vLLM for high-throughput inference.
    Supports multimodal (image + text) input for medical image analysis.
    """
    
    MODEL_ID = "google/medgemma-1.5-4b-it"
    
    def __init__(
        self,
        tensor_parallel_size: int = 1,
        gpu_memory_utilization: float = 0.85,
        max_model_len: int = 8192
    ):
        """
        Initialize the vLLM-based MedGemma agent.
        
        Args:
            tensor_parallel_size: Number of GPUs for tensor parallelism
            gpu_memory_utilization: Fraction of GPU memory to use
            max_model_len: Maximum sequence length
        """
        if not VLLM_AVAILABLE:
            raise ImportError("vLLM is not installed. Run: pip install vllm")
        
        self.model = None
        self._load_model(tensor_parallel_size, gpu_memory_utilization, max_model_len)
    
    def _load_model(
        self,
        tensor_parallel_size: int,
        gpu_memory_utilization: float,
        max_model_len: int
    ):
        """Load MedGemma model with vLLM."""
        logger.info(f"Loading MedGemma with vLLM: {self.MODEL_ID}")
        
        self.model = LLM(
            model=self.MODEL_ID,
            tensor_parallel_size=tensor_parallel_size,
            gpu_memory_utilization=gpu_memory_utilization,
            max_model_len=max_model_len,
            trust_remote_code=True,
            # Enable multimodal support for vision-language models
            limit_mm_per_prompt={"image": 1}
        )
        
        logger.info("MedGemma vLLM model loaded successfully")
    
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
"""
    
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
        
        # Enhanced prompt with artifact detection and clinical correlation
        prompt = f"""Analyze this {modality.upper()} image for a clinical encounter.

Clinical Context: {clinical_context if clinical_context else "Not provided"}
Patient's Chief Complaint: {complaint_str}
Patient's Reported Symptoms: {symptoms_str}
Body Region: {body_region if body_region else "Not specified"}

Please provide a structured analysis with ALL of the following sections:

## 1. IMAGE QUALITY & ARTIFACTS
Assess the technical quality of this image:
- **Overall Quality**: [diagnostic / acceptable / degraded / non-diagnostic]
- **Artifacts Found**: List any artifacts (motion, metal, positioning, exposure, etc.)
- **Impact on Interpretation**: [none / limited / significant]
- **Recommendation**: [proceed with interpretation / repeat study with corrections]
If no artifacts are found, state "No significant artifacts identified."

## 2. KEY FINDINGS
List ALL observable findings, organized by clinical significance.

## 3. CLINICAL CORRELATION
For EACH finding, classify it as:
- **CLINICALLY CORRELATED**: Finding matches the patient's symptoms/complaint
- **INCIDENTAL**: Finding is present but does NOT relate to symptoms
  - Note prevalence in asymptomatic populations for incidental findings

IMPORTANT: A radiological finding does NOT automatically mean pathology.
Disc bulges, osteophytes, and degenerative changes are extremely common in
asymptomatic individuals and must be correlated with clinical symptoms.

## 4. DIFFERENTIAL CONSIDERATIONS
Possible diagnoses prioritized by clinical correlation.

## 5. RECOMMENDATIONS
Next steps for correlated findings and follow-up for incidental findings.

Flag any urgent findings with ⚠️."""
        
        # Sampling parameters for medical analysis
        sampling_params = SamplingParams(
            temperature=0.3,
            top_p=0.9,
            max_tokens=1536,
            stop=["<|end|>", "<|eot_id|>"]
        )
        
        # Generate with multimodal input
        outputs = self.model.generate(
            [
                {
                    "prompt": prompt,
                    "multi_modal_data": {"image": image}
                }
            ],
            sampling_params=sampling_params
        )
        
        response = outputs[0].outputs[0].text
        
        # Post-process with clinical correlator if symptoms provided
        correlation_result = None
        if patient_symptoms:
            from .clinical_correlation import get_clinical_correlator
            correlator = get_clinical_correlator()
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
            if "KEY FINDINGS" in line.upper() or "FINDINGS" in line.upper():
                in_findings_section = True
                continue
            if in_findings_section and line.startswith("## "):
                in_findings_section = False
                continue
            if in_findings_section and (line.startswith("- ") or line.startswith("* ")):
                finding = line.lstrip("-* ").strip().replace("**", "")
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

        # Sampling for SOAP generation
        sampling_params = SamplingParams(
            temperature=0.4,
            top_p=0.9,
            max_tokens=2048,
            stop=["<|end|>", "<|eot_id|>"]
        )
        
        # Generate SOAP note (text-only)
        outputs = self.model.generate([prompt], sampling_params=sampling_params)
        response = outputs[0].outputs[0].text
        
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
        # Build conversation from history
        conversation = self._build_system_prompt() + "\n\n"
        
        if history:
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    conversation += f"User: {content}\n"
                else:
                    conversation += f"Assistant: {content}\n"
        
        conversation += f"User: {message}\nAssistant:"
        
        sampling_params = SamplingParams(
            temperature=0.5,
            top_p=0.9,
            max_tokens=1024,
            stop=["User:", "<|end|>"]
        )
        
        outputs = self.model.generate([conversation], sampling_params=sampling_params)
        return outputs[0].outputs[0].text.strip()


def is_vllm_available() -> bool:
    """Check if vLLM is available for use."""
    return VLLM_AVAILABLE
