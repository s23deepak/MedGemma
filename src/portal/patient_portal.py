"""
Patient Portal - Post-Appointment Q&A Assistant
Safe, guardrailed interface for patients to ask questions about their care.
"""

from datetime import datetime
from dataclasses import dataclass, field
from typing import Any
from enum import Enum


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


class PatientAssistant:
    """
    AI assistant for patient post-appointment queries.
    Includes guardrails for safe responses.
    """
    
    def __init__(self, agent=None):
        """
        Initialize the patient assistant.
        
        Args:
            agent: Optional MedGemma agent for more advanced responses
        """
        self.agent = agent
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
        elif any(word in question_lower for word in ["symptom", "pain", "ache", "feel", "hurts"]):
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
    
    def _generate_response(self, question: str, category: QueryCategory) -> tuple[str, bool, list[str]]:
        """
        Generate a response to the patient's question.
        
        Returns:
            tuple of (response, requires_followup, references)
        """
        # Check for emergency
        if category == QueryCategory.EMERGENCY:
            return self._get_emergency_response(), True, []
        
        # Check guardrails
        guardrail_response = self._check_guardrails(question)
        if guardrail_response:
            return guardrail_response, True, []
        
        # Check FAQ
        faq_match = self._find_faq_match(question)
        if faq_match:
            return faq_match, False, ["Patient FAQ"]
        
        # Generate category-specific response
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
    
    def ask(self, patient_id: str, question: str) -> PatientQuery:
        """
        Process a patient's question.
        
        Args:
            patient_id: The patient's ID
            question: The patient's question
            
        Returns:
            PatientQuery with the response
        """
        query_id = f"Q-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        category = self._categorize_query(question)
        response, requires_followup, references = self._generate_response(question, category)
        
        query = PatientQuery(
            query_id=query_id,
            patient_id=patient_id,
            question=question,
            category=category,
            response=response,
            requires_followup=requires_followup,
            references=references
        )
        
        self.query_history.append(query)
        return query
    
    def get_appointment_summary(self, patient_id: str) -> dict:
        """Get a summary of the patient's recent appointment."""
        # Mock appointment summary
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

def get_patient_assistant() -> PatientAssistant:
    """Get or create the patient assistant singleton."""
    global _patient_assistant
    if _patient_assistant is None:
        _patient_assistant = PatientAssistant()
    return _patient_assistant
