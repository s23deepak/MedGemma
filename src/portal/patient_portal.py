"""
Patient Portal - Post-Appointment Q&A Assistant
Safe, guardrailed interface for patients to ask questions about their care.
"""

from datetime import datetime
from dataclasses import dataclass, field
from typing import Any
from enum import Enum
import logging
import re

logger = logging.getLogger(__name__)


class QueryCategory(str, Enum):
    """Categories of patient queries."""
    MEDICATION = "medication"
    SYMPTOMS = "symptoms"
    APPOINTMENT = "appointment"
    DIAGNOSIS = "diagnosis"
    LIFESTYLE = "lifestyle"
    EMERGENCY = "emergency"
    GENERAL = "general"


@dataclass
class PatientQuery:
    """A patient's query and response."""
    query_id: str
    patient_id: str
    question: str
    category: QueryCategory
    response: str
    requires_followup: bool
    ai_generated: bool = False
    references: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "patient_id": self.patient_id,
            "question": self.question,
            "category": self.category.value,
            "response": self.response,
            "requires_followup": self.requires_followup,
            "ai_generated": self.ai_generated,
            "references": self.references,
            "created_at": self.created_at.isoformat()
        }


# Emergency keywords that should trigger immediate advice to seek care
EMERGENCY_KEYWORDS = [
    "chest pain", "can't breathe", "difficulty breathing",
    "stroke", "heart attack", "severe bleeding", "unconscious",
    "seizure", "suicidal", "overdose", "severe allergic",
    "anaphylaxis", "paralysis", "sudden numbness"
]

# Guardrails - topics we should not give specific advice on
RESTRICTED_TOPICS = [
    "dosage adjustment", "stop taking medication",
    "start new medication", "diagnosis",
    "legal", "malpractice"
]

# Patient-safe system prompt for MedGemma
PATIENT_SYSTEM_PROMPT = """You are a patient-facing healthcare assistant for a hospital portal.
Your role is to help patients understand their care AFTER a medical appointment.

CRITICAL SAFETY RULES — you MUST follow these at all times:
1. NEVER provide a specific diagnosis. Always say "your doctor can confirm..."
2. NEVER recommend starting, stopping, or adjusting medication dosages.
3. NEVER replace professional medical advice. Always recommend consulting their provider for serious concerns.
4. If the patient describes symptoms that could be an emergency, tell them to call 911 or go to the ER immediately.
5. Be warm, empathetic, and use plain language a non-medical person can understand.
6. Keep responses concise — 2-4 sentences for simple questions, up to a short paragraph for complex ones.
7. When discussing side effects or symptoms, always include "If this persists or worsens, contact your healthcare provider."

You may helpfully explain:
- General information about medications (what they're for, common side effects)
- What symptoms or side effects commonly mean in general terms
- When to seek medical attention
- General lifestyle and wellness guidance
- How to prepare for appointments
- What to expect from common procedures

Patient context will be provided when available. Use it to give more personalized (but still safe) responses.

If the patient asks you to remember, note down, or store any information for future reference, include `[STORE_MEMORY: <concise fact>]` at the end of your response. Only include this tag when the patient explicitly wants something remembered."""


class PatientAssistant:
    """
    AI assistant for patient post-appointment queries.
    Includes guardrails for safe responses.
    Routes safe questions through MedGemma when available.
    """
    
    def __init__(self, agent=None, fhir_server=None):
        """
        Initialize the patient assistant.
        
        Args:
            agent: Optional MedGemma/Healthcare agent for AI-powered responses
            fhir_server: Optional FHIR server (Firestore or mock) for patient data
        """
        self.agent = agent
        self.fhir_server = fhir_server
        self.query_history: list[PatientQuery] = []
        self.faq = self._load_faq()
    
    def _load_faq(self) -> dict[str, str]:
        """Load frequently asked questions."""
        return {
            "When should I take my medication?": 
                "Please follow the instructions on your prescription label or as directed by your "
                "doctor. If you're unsure, contact your pharmacy or doctor's office.",
            
            "What are common side effects?":
                "Side effects vary by medication. Common ones include nausea, dizziness, or fatigue. "
                "If you experience severe or unexpected side effects, contact your healthcare provider.",
            
            "Can I drink alcohol with my medication?":
                "It's best to check with your pharmacist or doctor, as alcohol can interact with many "
                "medications. When in doubt, avoid alcohol until you can confirm it's safe.",
            
            "How do I refill my prescription?":
                "You can usually refill prescriptions through your pharmacy's app, by calling them, "
                "or by contacting your doctor's office if you need a new prescription.",
            
            "When is my next appointment?":
                "Please check your patient portal or call our office to confirm your next appointment. "
                "You can also check any confirmation emails you may have received.",
            
            "What should I do if I miss a dose?":
                "Generally, take it as soon as you remember unless it's almost time for your next dose. "
                "Never double up. For specific guidance, check your medication label or call your pharmacy.",
            
            "How can I access my test results?":
                "Test results are typically available in your patient portal within a few days. "
                "Your doctor will contact you if there are any concerns that need discussion."
        }
    
    def _categorize_query(self, question: str) -> QueryCategory:
        """Categorize the patient's question."""
        question_lower = question.lower()
        
        # Check for emergency
        for keyword in EMERGENCY_KEYWORDS:
            if keyword in question_lower:
                return QueryCategory.EMERGENCY
        
        # Categorize by topic
        if any(word in question_lower for word in ["medication", "medicine", "drug", "pill", "dose", "prescription"]):
            return QueryCategory.MEDICATION
        elif any(word in question_lower for word in ["symptom", "pain", "ache", "feel", "hurts", "dizzy", "nausea"]):
            return QueryCategory.SYMPTOMS
        elif any(word in question_lower for word in ["appointment", "visit", "schedule", "book"]):
            return QueryCategory.APPOINTMENT
        elif any(word in question_lower for word in ["diagnosis", "condition", "disease", "what do i have"]):
            return QueryCategory.DIAGNOSIS
        elif any(word in question_lower for word in ["diet", "exercise", "sleep", "lifestyle", "eat", "drink"]):
            return QueryCategory.LIFESTYLE
        
        return QueryCategory.GENERAL
    
    def _check_guardrails(self, question: str) -> str | None:
        """Check if question hits any guardrails. Returns warning message if so."""
        question_lower = question.lower()
        
        for topic in RESTRICTED_TOPICS:
            if topic in question_lower:
                return (
                    "I cannot provide specific medical advice on this topic. "
                    "Please contact your healthcare provider directly for personalized guidance."
                )
        
        return None
    
    def _get_emergency_response(self) -> str:
        """Generate emergency response."""
        return (
            "⚠️ **This sounds like it could be a medical emergency.**\n\n"
            "Please seek immediate medical attention:\n"
            "- **Call 911** or your local emergency number\n"
            "- **Go to the nearest emergency room**\n"
            "- **Call the Poison Control Center** at 1-800-222-1222 (if applicable)\n\n"
            "Do not wait to see if symptoms improve. When in doubt, it's always safer to get checked."
        )
    
    def _find_faq_match(self, question: str) -> str | None:
        """Find a matching FAQ response."""
        question_lower = question.lower()
        
        for faq_question, faq_answer in self.faq.items():
            # Check for keyword overlap
            faq_words = set(faq_question.lower().split())
            question_words = set(question_lower.split())
            overlap = len(faq_words & question_words)
            
            if overlap >= 3:  # At least 3 matching words
                return faq_answer
        
        return None

    def _ask_medgemma(self, question: str, category: QueryCategory, patient_context: dict | None = None, patient_id: str | None = None) -> str | None:
        """
        Route the question to MedGemma with patient-safe system prompt.
        Returns the AI response, or None if the agent is unavailable.
        """
        if self.agent is None:
            return None
        
        try:
            # Build a patient-context-aware prompt
            prompt_parts = [PATIENT_SYSTEM_PROMPT, "\n---\n"]
            
            if patient_context:
                prompt_parts.append("Patient context:\n")
                # Patient info is nested under 'patient' key
                patient_info = patient_context.get("patient", patient_context)
                if isinstance(patient_info, dict):
                    if "name" in patient_info:
                        prompt_parts.append(f"- Name: {patient_info['name']}\n")
                    if "age" in patient_info:
                        prompt_parts.append(f"- Age: {patient_info['age']}\n")
                    if "gender" in patient_info:
                        prompt_parts.append(f"- Gender: {patient_info['gender']}\n")
                if "conditions" in patient_context:
                    conds = patient_context["conditions"]
                    if isinstance(conds, list):
                        names = [c.get("name", str(c)) if isinstance(c, dict) else str(c) for c in conds]
                        conditions = ", ".join(names)
                    else:
                        conditions = str(conds)
                    prompt_parts.append(f"- Active conditions: {conditions}\n")
                if "medications" in patient_context:
                    meds = patient_context["medications"]
                    if isinstance(meds, list):
                        names = [m.get("name", str(m)) if isinstance(m, dict) else str(m) for m in meds]
                        medications = ", ".join(names)
                    else:
                        medications = str(meds)
                    prompt_parts.append(f"- Current medications: {medications}\n")
                if "allergies" in patient_context:
                    allergies = patient_context["allergies"]
                    if isinstance(allergies, list):
                        names = [a.get("substance", str(a)) if isinstance(a, dict) else str(a) for a in allergies]
                        allergy_str = ", ".join(names)
                    else:
                        allergy_str = str(allergies)
                    prompt_parts.append(f"- Allergies: {allergy_str}\n")
                prompt_parts.append("\n")
                
            # Inject stored memories
            if self.fhir_server is not None and hasattr(self.fhir_server, 'get_memories'):
                try:
                    pid = patient_id or (patient_context.get("patient", {}).get("id", "") if patient_context else "")
                    if pid:
                        memories = self.fhir_server.get_memories(pid)
                        if memories:
                            prompt_parts.append("Stored notes & patient memories:\n")
                            for mem in memories:
                                prompt_parts.append(f"- {mem}\n")
                            prompt_parts.append("\n")
                except Exception as e:
                    logger.warning(f"Failed to fetch memories for prompt: {e}")
            
            # Include appointment data if asking about appointments
            if category == QueryCategory.APPOINTMENT and self.fhir_server is not None:
                try:
                    pid = patient_id or (patient_context.get("patient", {}).get("id", "") if patient_context else "")
                    if pid:
                        appt = self.get_appointment_summary(pid)
                        if appt:
                            prompt_parts.append("Appointment information:\n")
                            prompt_parts.append(f"- Last appointment date: {appt.get('date', 'N/A')}\n")
                            prompt_parts.append(f"- Provider: {appt.get('provider', 'N/A')}\n")
                            prompt_parts.append(f"- Visit type: {appt.get('type', 'N/A')}\n")
                            prompt_parts.append(f"- Next appointment: {appt.get('followup_date', 'N/A')}\n")
                            if appt.get('instructions'):
                                prompt_parts.append(f"- Instructions: {'; '.join(appt['instructions'])}\n")
                            prompt_parts.append("\n")
                except Exception as e:
                    logger.warning(f"Failed to fetch appointment for prompt: {e}")
            
            prompt_parts.append(f"Query category: {category.value}\n")
            prompt_parts.append(f"Patient question: {question}\n\n")
            prompt_parts.append("Provide a helpful, safe, and empathetic response:")
            
            full_prompt = "".join(prompt_parts)
            print("******************************full_prompt**********************************")
            print(full_prompt)
            print("******************************full_prompt**********************************")
            
            # Use agent.chat() (MedGemmaAgent) or agent.process_query() (HealthcareAgent)
            if hasattr(self.agent, 'chat'):
                response = self.agent.chat(full_prompt)
            elif hasattr(self.agent, 'process_query'):
                result = self.agent.process_query(query=full_prompt, patient_context=patient_context)
                response = result.get("response", "")
            else:
                logger.warning(f"Agent {type(self.agent).__name__} has no chat or process_query method")
                return None
                
            # Parse memory tags
            if response:
                memory_tags = re.findall(r'\[STORE_MEMORY:\s*(.*?)\]', response)
                for memory_fact in memory_tags:
                    if self.fhir_server is not None and hasattr(self.fhir_server, 'add_memory'):
                        try:
                            pid = patient_id or (patient_context.get("patient", {}).get("id", "") if patient_context else "")
                            if pid:
                                self.fhir_server.add_memory(pid, memory_fact.strip())
                                logger.info(f"Stored memory for {pid}: {memory_fact.strip()}")
                        except Exception as e:
                            logger.warning(f"Failed to store memory: {e}")
                
                # Strip tags from the final response
                response = re.sub(r'\[STORE_MEMORY:\s*.*?\]', '', response).strip()
            
            # Strip simulated prefix if present
            if response and response.startswith("[Simulated]"):
                response = response.replace("[Simulated] Processed query: ", "").rstrip(".")
                if len(response) < 20:
                    return None
            
            if response:
                logger.info(f"MedGemma responded to patient query (category={category.value})")
                return response
                
        except Exception as e:
            import traceback
            logger.warning(f"MedGemma patient query failed: {e}\n{traceback.format_exc()}")
        
        return None

    def _get_fallback_response(self, category: QueryCategory) -> tuple[str, bool, list[str]]:
        """Get hardcoded fallback response when no AI agent is available."""
        responses = {
            QueryCategory.MEDICATION: (
                "For questions about your medication, I recommend:\n\n"
                "1. **Check your prescription label** for dosing instructions\n"
                "2. **Contact your pharmacy** - they can answer many medication questions\n"
                "3. **Message your doctor** through the patient portal for specific concerns\n\n"
                "Never change your medication routine without consulting your healthcare provider.",
                False,
                ["Pharmacy services", "Patient portal"]
            ),
            QueryCategory.SYMPTOMS: (
                "I understand you're experiencing symptoms. Here's what I recommend:\n\n"
                "1. **Monitor your symptoms** - note when they occur and any changes\n"
                "2. **Check your discharge instructions** if recently seen\n"
                "3. **Contact your doctor** if symptoms worsen or don't improve\n\n"
                "If your symptoms are severe or concerning, don't wait - seek medical attention.",
                True,
                ["Symptom tracking guide"]
            ),
            QueryCategory.APPOINTMENT: (
                "For appointment-related questions:\n\n"
                "1. **Check your patient portal** for appointment details\n"
                "2. **Call our office** at the number on your paperwork\n"
                "3. **Check your email/text** for appointment reminders\n\n"
                "We're happy to help reschedule if needed.",
                False,
                ["Patient portal", "Office contact"]
            ),
            QueryCategory.DIAGNOSIS: (
                "Questions about your diagnosis are best discussed with your doctor, who can:\n\n"
                "1. Explain your condition in detail\n"
                "2. Answer specific questions about your case\n"
                "3. Discuss treatment options\n\n"
                "Please schedule a follow-up or send a message through the patient portal.",
                True,
                ["Patient portal messaging"]
            ),
            QueryCategory.LIFESTYLE: (
                "For lifestyle and wellness questions:\n\n"
                "1. **Follow your doctor's specific recommendations** from your visit\n"
                "2. **General guidelines**: balanced diet, regular exercise, adequate sleep\n"
                "3. **Consult your care team** for personalized advice\n\n"
                "Your doctor can provide guidance tailored to your health conditions.",
                False,
                ["CDC health guidelines", "NIH patient resources"]
            ),
            QueryCategory.GENERAL: (
                "Thank you for your question. Here are some resources:\n\n"
                "1. **Patient Portal**: Access your records, message your doctor\n"
                "2. **Office Phone**: Call during business hours\n"
                "3. **Nurse Line**: Available 24/7 for non-emergency questions\n\n"
                "For specific medical questions, please contact your healthcare provider.",
                False,
                ["Patient portal", "Office contact"]
            )
        }
        
        return responses.get(category, responses[QueryCategory.GENERAL])

    def _generate_response(self, question: str, category: QueryCategory, patient_context: dict | None = None, patient_id: str | None = None) -> tuple[str, bool, list[str], bool]:
        """
        Generate a response to the patient's question.
        
        Returns:
            tuple of (response, requires_followup, references, ai_generated)
        """
        # 1. Emergency — always hardcoded, never AI
        if category == QueryCategory.EMERGENCY:
            return self._get_emergency_response(), True, [], False
        
        # 2. Guardrails — always hardcoded, never AI
        guardrail_response = self._check_guardrails(question)
        if guardrail_response:
            return guardrail_response, True, [], False
        
        # 3. Try MedGemma for a real AI response
        ai_response = self._ask_medgemma(question, category, patient_context, patient_id=patient_id)
        if ai_response:
            # Determine if follow-up is needed based on category
            needs_followup = category in (QueryCategory.SYMPTOMS, QueryCategory.DIAGNOSIS)
            return ai_response, needs_followup, ["MedGemma AI"], True
        
        # 4. Check FAQ as fallback
        faq_match = self._find_faq_match(question)
        if faq_match:
            return faq_match, False, ["Patient FAQ"], False
        
        # 5. Hardcoded category-based fallback
        return (*self._get_fallback_response(category), False)
    
    def ask(self, patient_id: str, question: str, patient_context: dict | None = None) -> PatientQuery:
        """
        Process a patient's question.
        
        Args:
            patient_id: The patient's ID
            question: The patient's question
            patient_context: Optional EHR context for the patient
            
        Returns:
            PatientQuery with the response
        """
        query_id = f"Q-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        category = self._categorize_query(question)
        response, requires_followup, references, ai_generated = self._generate_response(
            question, category, patient_context, patient_id=patient_id
        )
        
        query = PatientQuery(
            query_id=query_id,
            patient_id=patient_id,
            question=question,
            category=category,
            response=response,
            requires_followup=requires_followup,
            ai_generated=ai_generated,
            references=references
        )
        
        self.query_history.append(query)
        return query
    
    def get_appointment_summary(self, patient_id: str) -> dict:
        """Get a summary of the patient's recent appointment from FHIR server."""
        # Try to get from FHIR server (Firestore or mock)
        if self.fhir_server is not None:
            try:
                # FirestoreFHIRServer has get_appointment_summary
                if hasattr(self.fhir_server, 'get_appointment_summary'):
                    appointment = self.fhir_server.get_appointment_summary(patient_id)
                    if appointment:
                        return appointment
                
                # Build from patient summary if no appointment data
                summary = self.fhir_server.get_patient_summary(patient_id)
                if summary:
                    return {
                        "date": "Recent",
                        "provider": "Your care team",
                        "type": "Follow-up Visit",
                        "diagnoses": [c["name"] for c in summary.get("conditions", [])],
                        "medications": [
                            {"name": m["name"], "instructions": m.get("dosage", "As prescribed")}
                            for m in summary.get("medications", [])
                        ],
                        "instructions": [
                            "Continue current medications",
                            "Follow up with your provider as scheduled"
                        ],
                        "followup_date": "As scheduled"
                    }
            except Exception as e:
                logger.warning(f"Failed to get appointment from FHIR: {e}")
        
        # Fallback: hardcoded mock
        return {
            "date": "February 5, 2026",
            "provider": "Dr. Sarah Smith",
            "type": "Follow-up Visit",
            "diagnoses": ["Hypertension (controlled)", "Type 2 Diabetes"],
            "medications": [
                {"name": "Lisinopril 10mg", "instructions": "Take once daily in the morning"},
                {"name": "Metformin 500mg", "instructions": "Take twice daily with meals"}
            ],
            "instructions": [
                "Continue current medications",
                "Monitor blood pressure at home",
                "Follow low-sodium diet",
                "Return in 3 months for follow-up"
            ],
            "followup_date": "May 5, 2026"
        }
    
    def get_query_history(self, patient_id: str) -> list[dict]:
        """Get query history for a patient."""
        return [q.to_dict() for q in self.query_history if q.patient_id == patient_id]


# Singleton instance
_patient_assistant = None

def get_patient_assistant(agent=None, fhir_server=None) -> PatientAssistant:
    """Get or create the patient assistant singleton."""
    global _patient_assistant
    if _patient_assistant is None:
        _patient_assistant = PatientAssistant(agent=agent, fhir_server=fhir_server)
    else:
        # Update agent/fhir_server if they were loaded after initial creation
        if agent is not None and _patient_assistant.agent is None:
            _patient_assistant.agent = agent
        if fhir_server is not None and _patient_assistant.fhir_server is None:
            _patient_assistant.fhir_server = fhir_server
    return _patient_assistant
