"""
MedGemma Clinical Assistant - Tool Definitions
Defines the agentic tools available for clinical decision support.
Extended for FunctionGemma + MedGemma dual-model architecture.
"""

from typing import Any

# Tool schemas for function calling (FunctionGemma/MedGemma)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "fetch_patient_ehr",
            "description": "Retrieve patient EHR data from FHIR server including demographics, conditions, medications, allergies, and recent observations",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "The unique patient identifier"
                    }
                },
                "required": ["patient_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_medical_image",
            "description": "Analyze a medical image (X-ray, CT, MRI) with artifact detection and clinical correlation. Identifies imaging artifacts, classifies findings as clinically correlated or incidental, and provides prevalence context for common incidental findings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {
                        "type": "string",
                        "description": "Path to the medical image file"
                    },
                    "modality": {
                        "type": "string",
                        "enum": ["xray", "ct", "mri", "ultrasound"],
                        "description": "The imaging modality"
                    },
                    "clinical_context": {
                        "type": "string",
                        "description": "Clinical context from the physician's dictation to guide analysis"
                    },
                    "patient_symptoms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Patient's reported symptoms for clinical correlation (e.g., ['back pain', 'leg numbness'])"
                    },
                    "chief_complaint": {
                        "type": "string",
                        "description": "Patient's primary reason for visit (e.g., 'right knee pain')"
                    },
                    "body_region": {
                        "type": "string",
                        "description": "Body region being imaged (e.g., 'lumbar spine', 'chest', 'knee')"
                    }
                },
                "required": ["image_path", "modality"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_soap_note",
            "description": "Generate a structured SOAP note from encounter data. Requires MedGemma for clinical synthesis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chief_complaint": {
                        "type": "string",
                        "description": "The patient's primary complaint"
                    },
                    "transcription": {
                        "type": "string",
                        "description": "The full transcription of the clinical encounter"
                    },
                    "image_findings": {
                        "type": "string",
                        "description": "Findings from medical image analysis, if any"
                    },
                    "patient_context": {
                        "type": "object",
                        "description": "Patient EHR context including conditions, medications, allergies"
                    }
                },
                "required": ["chief_complaint", "transcription"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_ehr",
            "description": "Update the patient's electronic health record. REQUIRES physician approval before execution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "The unique patient identifier"
                    },
                    "encounter_note": {
                        "type": "string",
                        "description": "The approved SOAP note to add to the record"
                    },
                    "new_conditions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New conditions to add to the patient's problem list"
                    },
                    "new_medications": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New medications to add to the patient's medication list"
                    }
                },
                "required": ["patient_id", "encounter_note"]
            }
        }
    },
    # ==================== New Tools for FunctionGemma ====================
    {
        "type": "function",
        "function": {
            "name": "schedule_appointment",
            "description": "Schedule a follow-up appointment for the patient with a specialist or for a specific service.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "The unique patient identifier"
                    },
                    "specialty": {
                        "type": "string",
                        "enum": ["general", "cardiology", "pulmonology", "endocrinology", "neurology", "orthopedics", "oncology"],
                        "description": "Medical specialty for the appointment"
                    },
                    "urgency": {
                        "type": "string",
                        "enum": ["routine", "urgent", "emergent"],
                        "description": "Appointment urgency level"
                    }
                },
                "required": ["patient_id", "specialty"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "order_lab_tests",
            "description": "Order laboratory tests for a patient. Requires physician approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "The unique patient identifier"
                    },
                    "tests": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of lab tests to order (e.g., CBC, BMP, Troponin, HbA1c)"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["routine", "stat"],
                        "description": "Order priority"
                    }
                },
                "required": ["patient_id", "tests"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "notify_care_team",
            "description": "Send a notification to the patient's care team or a specific provider.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "The unique patient identifier"
                    },
                    "message": {
                        "type": "string",
                        "description": "Notification message content"
                    },
                    "urgency": {
                        "type": "string",
                        "enum": ["normal", "urgent", "critical"],
                        "description": "Notification urgency level"
                    },
                    "recipient": {
                        "type": "string",
                        "description": "Specific recipient (e.g., 'on-call cardiologist', 'primary care')"
                    }
                },
                "required": ["patient_id", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_fhir_observations",
            "description": "Search patient observations in FHIR store by code or category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "The unique patient identifier"
                    },
                    "code": {
                        "type": "string",
                        "description": "LOINC or observation code to search (e.g., 'liver_panel', 'glucose', 'blood_pressure')"
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Start date for observation search (YYYY-MM-DD)"
                    }
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_prior_imaging",
            "description": "Retrieve prior imaging studies for a patient from the PACS/DICOMweb system.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "The unique patient identifier"
                    },
                    "modality": {
                        "type": "string",
                        "enum": ["xray", "ct", "mri", "ultrasound", "all"],
                        "description": "Filter by imaging modality"
                    },
                    "body_part": {
                        "type": "string",
                        "description": "Filter by body part (e.g., 'chest', 'abdomen', 'head')"
                    }
                },
                "required": ["patient_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_drug_interactions",
            "description": "Check for potential drug-drug interactions in a medication list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "medications": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of current medications to check"
                    },
                    "new_medications": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New medications being considered"
                    }
                },
                "required": ["medications"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_medgemma",
            "description": "Escalate query to MedGemma for complex medical reasoning, diagnosis, or clinical analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Reason for escalation to medical AI"
                    },
                    "query": {
                        "type": "string",
                        "description": "The medical query requiring analysis"
                    }
                },
                "required": ["reason"]
            }
        }
    },
    # ==================== Patient Memory Tools (Mem0) ====================
    {
        "type": "function",
        "function": {
            "name": "recall_patient_memory",
            "description": "Search persistent memory for a patient's history, preferences, allergies, medications, diagnoses, and past clinical notes. Uses semantic search powered by Mem0.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "The unique patient identifier"
                    },
                    "query": {
                        "type": "string",
                        "description": "What to search for (e.g., 'allergies', 'cardiac history', 'medication list')"
                    }
                },
                "required": ["patient_id", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_patient_memory",
            "description": "Save a clinical note or fact to a patient's persistent memory. The memory system automatically extracts and stores relevant clinical facts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "The unique patient identifier"
                    },
                    "note": {
                        "type": "string",
                        "description": "Clinical note or fact to store (e.g., 'Patient is allergic to penicillin')"
                    },
                    "category": {
                        "type": "string",
                        "enum": ["allergy", "medication", "diagnosis", "procedure", "preference", "social_history", "critical_alert", "general"],
                        "description": "Category of the clinical fact"
                    }
                },
                "required": ["patient_id", "note"]
            }
        }
    }
]


def get_tool_by_name(name: str) -> dict | None:
    """Get a tool definition by its name."""
    for tool in TOOLS:
        if tool["function"]["name"] == name:
            return tool
    return None


def format_tools_for_prompt() -> str:
    """Format tools as a string for inclusion in prompts."""
    lines = ["Available tools:"]
    for tool in TOOLS:
        func = tool["function"]
        lines.append(f"\n- **{func['name']}**: {func['description']}")
        params = func["parameters"]["properties"]
        for param_name, param_info in params.items():
            required = param_name in func["parameters"].get("required", [])
            req_str = " (required)" if required else ""
            lines.append(f"  - {param_name}: {param_info.get('description', '')}{req_str}")
    return "\n".join(lines)


def get_tools_for_functiongemma() -> list[dict]:
    """Get tools formatted for FunctionGemma."""
    return TOOLS


# Tools that require physician approval before execution
APPROVAL_REQUIRED_TOOLS = [
    "update_ehr",
    "order_lab_tests",
    "schedule_appointment"
]


def requires_approval(tool_name: str) -> bool:
    """Check if a tool requires physician approval."""
    return tool_name in APPROVAL_REQUIRED_TOOLS

