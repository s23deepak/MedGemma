"""
Patient Memory Module — Persistent clinical memory powered by Mem0.

Provides cross-encounter memory for patient information:
- Allergies, medications, diagnoses, procedures
- Patient preferences (communication, scheduling)
- Social history and lifestyle factors
- Critical clinical notes and alerts

Memories are automatically extracted from encounters and stored
for semantic retrieval in future visits.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Check Mem0 availability
try:
    from mem0 import Memory
    MEM0_AVAILABLE = True
except ImportError:
    MEM0_AVAILABLE = False
    logger.warning("mem0ai not installed. Run: pip install mem0ai")


# Clinical fact extraction prompt — tuned for medical data
CLINICAL_EXTRACTION_PROMPT = """You are a clinical information extraction system.
Given a conversation or clinical note, extract ONLY factual medical information.

Extract these categories of facts:
1. ALLERGIES: Drug allergies, food allergies, environmental allergies, and reactions
2. MEDICATIONS: Current medications, dosages, frequencies, and routes
3. DIAGNOSES: Active and historical diagnoses, conditions, and problems
4. PROCEDURES: Past surgical procedures, interventions, and treatments
5. VITALS/LABS: Significant vital signs, lab results, or measurements
6. PREFERENCES: Patient preferences for communication, scheduling, treatment
7. SOCIAL HISTORY: Smoking status, alcohol use, occupation, living situation
8. FAMILY HISTORY: Relevant family medical history
9. CRITICAL ALERTS: Drug interactions, fall risk, infection precautions

Rules:
- Extract ONLY factual statements, not opinions or assessments
- Include specific values (doses, dates, measurements) when available
- Flag any life-threatening allergies or critical safety information
- Do NOT extract procedural or conversational content
- Each fact should be a standalone, self-contained statement
"""


class PatientMemory:
    """
    Persistent patient memory using Mem0.
    
    Stores and retrieves clinical facts across encounters,
    enabling longitudinal patient context without EHR re-queries.
    """
    
    def __init__(self, config: dict | None = None):
        """
        Initialize patient memory.
        
        Args:
            config: Optional Mem0 configuration dict. If None, uses defaults
                    with OpenAI for extraction and local Qdrant for storage.
        """
        if not MEM0_AVAILABLE:
            raise ImportError(
                "mem0ai is not installed. Run: pip install mem0ai"
            )
        
        if config:
            self.memory = Memory.from_config(config)
        else:
            # Default config — uses OpenAI for extraction, local Qdrant
            default_config = self._build_default_config()
            if default_config:
                self.memory = Memory.from_config(default_config)
            else:
                self.memory = Memory()
        
        logger.info("PatientMemory initialized with Mem0")
    
    def _build_default_config(self) -> dict | None:
        """Build default Mem0 config with clinical extraction prompt."""
        config = {
            "custom_fact_extraction_prompt": CLINICAL_EXTRACTION_PROMPT,
            "version": "v1.1",
        }
        
        # Use OpenAI if key available
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            config["llm"] = {
                "provider": "openai",
                "config": {
                    "model": "gpt-4.1-nano",
                    "temperature": 0.1,
                    "api_key": openai_key,
                }
            }
            config["embedder"] = {
                "provider": "openai",
                "config": {
                    "model": "text-embedding-3-small",
                    "api_key": openai_key,
                }
            }
        
        return config
    
    # ================================================================
    # Core Memory Operations
    # ================================================================
    
    def add_encounter(
        self,
        patient_id: str,
        encounter_data: dict,
        metadata: dict | None = None
    ) -> dict:
        """
        Extract and store facts from a clinical encounter.
        
        Args:
            patient_id: Unique patient identifier
            encounter_data: Dict with keys like 'transcription', 'soap_note', 
                          'image_analysis', 'chief_complaint'
            metadata: Optional metadata (encounter_id, date, provider)
            
        Returns:
            Dict with extracted memories
        """
        # Build a comprehensive text from encounter data
        parts = []
        
        if encounter_data.get("chief_complaint"):
            parts.append(f"Chief Complaint: {encounter_data['chief_complaint']}")
        
        if encounter_data.get("transcription"):
            parts.append(f"Encounter Notes:\n{encounter_data['transcription']}")
        
        if encounter_data.get("soap_note"):
            parts.append(f"SOAP Note:\n{encounter_data['soap_note']}")
        
        if encounter_data.get("image_analysis"):
            analysis = encounter_data["image_analysis"]
            if isinstance(analysis, dict):
                parts.append(f"Imaging: {analysis.get('analysis', '')}")
            else:
                parts.append(f"Imaging: {analysis}")
        
        if encounter_data.get("medications"):
            meds = encounter_data["medications"]
            if isinstance(meds, list):
                parts.append(f"Medications: {', '.join(meds)}")
        
        if encounter_data.get("allergies"):
            allergies = encounter_data["allergies"]
            if isinstance(allergies, list):
                parts.append(f"Allergies: {', '.join(allergies)}")
        
        if encounter_data.get("diagnoses"):
            dx = encounter_data["diagnoses"]
            if isinstance(dx, list):
                parts.append(f"Diagnoses: {', '.join(dx)}")
        
        encounter_text = "\n\n".join(parts)
        
        if not encounter_text.strip():
            logger.warning(f"Empty encounter data for patient {patient_id}")
            return {"memories": [], "patient_id": patient_id}
        
        # Build message format for Mem0
        messages = [
            {
                "role": "user",
                "content": encounter_text
            }
        ]
        
        # Add with metadata
        mem_metadata = metadata or {}
        mem_metadata["source"] = "clinical_encounter"
        
        result = self.memory.add(
            messages,
            user_id=patient_id,
            metadata=mem_metadata
        )
        
        logger.info(f"Stored encounter memories for patient {patient_id}")
        return result
    
    def add_clinical_note(
        self,
        patient_id: str,
        note: str,
        category: str = "general",
        metadata: dict | None = None
    ) -> dict:
        """
        Add a specific clinical note to patient memory.
        
        Args:
            patient_id: Unique patient identifier
            note: The clinical note text
            category: Category (allergy, medication, diagnosis, preference, etc.)
            metadata: Optional metadata
            
        Returns:
            Dict with stored memory results
        """
        messages = [
            {"role": "user", "content": note}
        ]
        
        mem_metadata = metadata or {}
        mem_metadata["category"] = category
        mem_metadata["source"] = "clinical_note"
        
        result = self.memory.add(
            messages,
            user_id=patient_id,
            metadata=mem_metadata
        )
        
        logger.info(f"Added {category} note for patient {patient_id}")
        return result
    
    def recall(
        self,
        patient_id: str,
        query: str,
        limit: int = 10
    ) -> list[dict]:
        """
        Semantically search patient memories.
        
        Args:
            patient_id: Unique patient identifier
            query: What to search for (e.g., "allergies", "cardiac history")
            limit: Max results to return
            
        Returns:
            List of matching memory dicts with 'memory', 'score', etc.
        """
        results = self.memory.search(
            query,
            user_id=patient_id,
            limit=limit
        )
        
        # Normalize output format
        if isinstance(results, dict) and "results" in results:
            return results["results"]
        elif isinstance(results, list):
            return results
        return []
    
    def get_all(self, patient_id: str) -> list[dict]:
        """
        Retrieve ALL memories for a patient.
        
        Args:
            patient_id: Unique patient identifier
            
        Returns:
            List of all memory dicts
        """
        results = self.memory.get_all(user_id=patient_id)
        
        if isinstance(results, dict) and "results" in results:
            return results["results"]
        elif isinstance(results, list):
            return results
        return []
    
    def delete_memory(self, memory_id: str) -> dict:
        """Delete a specific memory by ID."""
        self.memory.delete(memory_id)
        return {"status": "deleted", "memory_id": memory_id}
    
    def delete_all(self, patient_id: str) -> dict:
        """Delete ALL memories for a patient. Use with caution."""
        self.memory.delete_all(user_id=patient_id)
        logger.warning(f"Deleted all memories for patient {patient_id}")
        return {"status": "deleted_all", "patient_id": patient_id}
    
    # ================================================================
    # Clinical Convenience Methods
    # ================================================================
    
    def get_allergies(self, patient_id: str) -> list[dict]:
        """Recall allergy-related memories."""
        return self.recall(patient_id, "drug allergies food allergies reactions")
    
    def get_medications(self, patient_id: str) -> list[dict]:
        """Recall medication-related memories."""
        return self.recall(patient_id, "current medications dosages prescriptions")
    
    def get_diagnoses(self, patient_id: str) -> list[dict]:
        """Recall diagnosis-related memories."""
        return self.recall(patient_id, "diagnoses conditions problems medical history")
    
    def get_critical_alerts(self, patient_id: str) -> list[dict]:
        """Recall critical safety alerts."""
        return self.recall(
            patient_id,
            "critical alerts drug interactions life-threatening allergy fall risk"
        )
    
    def get_preferences(self, patient_id: str) -> list[dict]:
        """Recall patient preferences."""
        return self.recall(
            patient_id,
            "patient preferences communication scheduling treatment choices"
        )
    
    def build_context_summary(self, patient_id: str) -> str:
        """
        Build a comprehensive context summary for a patient encounter.
        Useful for injecting into prompts before a new encounter.
        
        Returns:
            Formatted string with categorized patient memories
        """
        memories = self.get_all(patient_id)
        
        if not memories:
            return f"No prior memories found for patient {patient_id}."
        
        # Format memories into a clinical summary
        lines = [f"**Patient Memory Summary ({len(memories)} facts):**\n"]
        
        for mem in memories:
            memory_text = mem.get("memory", "")
            if memory_text:
                lines.append(f"- {memory_text}")
        
        return "\n".join(lines)


# Singleton
_patient_memory: PatientMemory | None = None


def get_patient_memory(config: dict | None = None) -> PatientMemory:
    """Get or create the singleton PatientMemory instance."""
    global _patient_memory
    if _patient_memory is None:
        try:
            _patient_memory = PatientMemory(config=config)
        except Exception as e:
            logger.error(f"Failed to initialize PatientMemory: {e}")
            raise
    return _patient_memory


def is_mem0_available() -> bool:
    """Check if Mem0 is available."""
    return MEM0_AVAILABLE
