"""
Clinical Intelligence Module
Provides ICD-10 codes, drug interactions, and clinical decision support.
"""

from dataclasses import dataclass
from typing import Any


# Common ICD-10 codes for demonstration
ICD10_CODES = {
    # Respiratory
    "pneumonia": {"code": "J18.9", "description": "Pneumonia, unspecified organism"},
    "bronchitis": {"code": "J40", "description": "Bronchitis, not specified as acute or chronic"},
    "asthma": {"code": "J45.909", "description": "Unspecified asthma, uncomplicated"},
    "asthma exacerbation": {"code": "J45.901", "description": "Unspecified asthma with (acute) exacerbation"},
    "copd": {"code": "J44.9", "description": "Chronic obstructive pulmonary disease, unspecified"},
    "cough": {"code": "R05.9", "description": "Cough, unspecified"},
    "shortness of breath": {"code": "R06.02", "description": "Shortness of breath"},
    "dyspnea": {"code": "R06.00", "description": "Dyspnea, unspecified"},
    "wheezing": {"code": "R06.2", "description": "Wheezing"},
    "pulmonary nodule": {"code": "R91.1", "description": "Solitary pulmonary nodule"},
    "lung mass": {"code": "R91.8", "description": "Other nonspecific abnormal finding of lung field"},
    
    # Cardiovascular
    "hypertension": {"code": "I10", "description": "Essential (primary) hypertension"},
    "chest pain": {"code": "R07.9", "description": "Chest pain, unspecified"},
    "coronary artery disease": {"code": "I25.10", "description": "Atherosclerotic heart disease of native coronary artery"},
    "heart failure": {"code": "I50.9", "description": "Heart failure, unspecified"},
    "atrial fibrillation": {"code": "I48.91", "description": "Unspecified atrial fibrillation"},
    
    # Metabolic
    "diabetes": {"code": "E11.9", "description": "Type 2 diabetes mellitus without complications"},
    "diabetes type 2": {"code": "E11.9", "description": "Type 2 diabetes mellitus without complications"},
    "hyperlipidemia": {"code": "E78.5", "description": "Hyperlipidemia, unspecified"},
    
    # Other
    "fever": {"code": "R50.9", "description": "Fever, unspecified"},
    "fatigue": {"code": "R53.83", "description": "Other fatigue"},
    "weight loss": {"code": "R63.4", "description": "Abnormal weight loss"},
}


# Drug interaction database (simplified for demo)
DRUG_INTERACTIONS = {
    "lisinopril": {
        "potassium": {"severity": "moderate", "effect": "Hyperkalemia risk"},
        "nsaids": {"severity": "moderate", "effect": "Reduced antihypertensive effect, kidney risk"},
        "spironolactone": {"severity": "high", "effect": "Severe hyperkalemia risk"},
        "lithium": {"severity": "high", "effect": "Increased lithium toxicity"},
    },
    "metformin": {
        "contrast dye": {"severity": "high", "effect": "Lactic acidosis risk - hold 48h before/after"},
        "alcohol": {"severity": "moderate", "effect": "Increased lactic acidosis risk"},
    },
    "warfarin": {
        "aspirin": {"severity": "high", "effect": "Increased bleeding risk"},
        "nsaids": {"severity": "high", "effect": "Increased bleeding risk"},
        "vitamin k": {"severity": "moderate", "effect": "Reduced anticoagulant effect"},
    },
    "aspirin": {
        "warfarin": {"severity": "high", "effect": "Increased bleeding risk"},
        "ibuprofen": {"severity": "moderate", "effect": "Reduced cardioprotective effect"},
        "ssri": {"severity": "moderate", "effect": "Increased GI bleeding risk"},
    },
    "albuterol": {
        "beta blockers": {"severity": "high", "effect": "Beta blockers may reduce albuterol effectiveness"},
        "diuretics": {"severity": "low", "effect": "May worsen hypokalemia"},
    },
    "atorvastatin": {
        "grapefruit": {"severity": "moderate", "effect": "Increased statin levels, myopathy risk"},
        "gemfibrozil": {"severity": "high", "effect": "Severe myopathy/rhabdomyolysis risk"},
        "clarithromycin": {"severity": "moderate", "effect": "Increased statin levels"},
    },
}


# Critical findings that require immediate attention
CRITICAL_FINDINGS = [
    # Imaging
    "pulmonary embolism", "pe", "aortic dissection", "tension pneumothorax",
    "pneumothorax", "hemothorax", "pericardial effusion", "cardiac tamponade",
    "mass", "tumor", "nodule", "malignancy", "cancer", "metastasis",
    "fracture", "hemorrhage", "bleeding", "aneurysm",
    
    # Clinical
    "sepsis", "septic shock", "respiratory failure", "cardiac arrest",
    "stroke", "cva", "mi", "myocardial infarction", "stemi", "nstemi",
    "hypoxia", "desaturation", "apnea",
    
    # Lab values
    "critical value", "panic value", "troponin elevated",
]


@dataclass
class DiagnosisWithConfidence:
    """Diagnosis with confidence score and ICD-10 code."""
    diagnosis: str
    confidence: float  # 0.0 to 1.0
    icd10_code: str | None
    icd10_description: str | None
    evidence: list[str]  # Supporting evidence from transcription/imaging
    
    @property
    def confidence_percent(self) -> str:
        """Return formatted confidence percentage."""
        return f"{int(self.confidence * 100)}%"
    
    def to_dict(self) -> dict:
        return {
            "diagnosis": self.diagnosis,
            "confidence": self.confidence,
            "confidence_percent": self.confidence_percent,
            "icd10_code": self.icd10_code,
            "icd10_description": self.icd10_description,
            "evidence": self.evidence
        }


@dataclass 
class DrugInteraction:
    """Drug interaction alert."""
    drug1: str
    drug2: str
    severity: str  # "low", "moderate", "high"
    effect: str
    
    def to_dict(self) -> dict:
        return {
            "drug1": self.drug1,
            "drug2": self.drug2,
            "severity": self.severity,
            "effect": self.effect
        }


@dataclass
class CriticalAlert:
    """Critical finding alert."""
    finding: str
    source: str  # "imaging", "transcription", "lab"
    severity: str  # "warning", "critical"
    recommendation: str
    
    def to_dict(self) -> dict:
        return {
            "finding": self.finding,
            "source": self.source,
            "severity": self.severity,
            "recommendation": self.recommendation
        }


class ClinicalIntelligence:
    """
    Clinical decision support providing:
    - ICD-10 code lookup
    - Drug interaction checking
    - Critical finding detection
    - Differential diagnosis ranking
    """
    
    def __init__(self):
        self.icd10_codes = ICD10_CODES
        self.drug_interactions = DRUG_INTERACTIONS
        self.critical_findings = CRITICAL_FINDINGS
    
    def lookup_icd10(self, diagnosis: str) -> dict | None:
        """Look up ICD-10 code for a diagnosis."""
        diagnosis_lower = diagnosis.lower().strip()
        
        # Direct match
        if diagnosis_lower in self.icd10_codes:
            return self.icd10_codes[diagnosis_lower]
        
        # Partial match
        for key, value in self.icd10_codes.items():
            if key in diagnosis_lower or diagnosis_lower in key:
                return value
        
        return None
    
    def check_drug_interactions(
        self, 
        current_medications: list[str], 
        new_medications: list[str] | None = None
    ) -> list[DrugInteraction]:
        """
        Check for drug interactions between current and new medications.
        
        Args:
            current_medications: List of current medication names
            new_medications: Optional list of new medications to check
            
        Returns:
            List of identified drug interactions
        """
        interactions = []
        all_meds = [m.lower().split()[0] for m in current_medications]  # Get first word (drug name)
        
        if new_medications:
            all_meds.extend([m.lower().split()[0] for m in new_medications])
        
        # Check each pair
        checked_pairs = set()
        for med1 in all_meds:
            if med1 in self.drug_interactions:
                for med2 in all_meds:
                    if med1 != med2:
                        pair = tuple(sorted([med1, med2]))
                        if pair not in checked_pairs:
                            checked_pairs.add(pair)
                            
                            # Check if med2 interacts with med1
                            for interacting_drug, interaction_info in self.drug_interactions[med1].items():
                                if interacting_drug in med2 or med2 in interacting_drug:
                                    interactions.append(DrugInteraction(
                                        drug1=med1.title(),
                                        drug2=med2.title(),
                                        severity=interaction_info["severity"],
                                        effect=interaction_info["effect"]
                                    ))
        
        return interactions
    
    def detect_critical_findings(
        self, 
        text: str, 
        source: str = "transcription"
    ) -> list[CriticalAlert]:
        """
        Detect critical findings in text that require immediate attention.
        
        Args:
            text: Text to analyze (transcription, imaging report, etc.)
            source: Source of the text ("imaging", "transcription", "lab")
            
        Returns:
            List of critical alerts
        """
        alerts = []
        text_lower = text.lower()
        
        for finding in self.critical_findings:
            if finding in text_lower:
                # Determine severity and recommendation based on finding type
                if finding in ["pulmonary embolism", "pe", "aortic dissection", 
                              "cardiac tamponade", "tension pneumothorax", 
                              "septic shock", "cardiac arrest", "stemi"]:
                    severity = "critical"
                    recommendation = "IMMEDIATE intervention required"
                elif finding in ["mass", "tumor", "nodule", "malignancy", "cancer"]:
                    severity = "critical"
                    recommendation = "Urgent oncology referral and staging workup"
                elif finding in ["pneumothorax", "fracture", "hemorrhage"]:
                    severity = "critical"
                    recommendation = "Urgent surgical/interventional consult"
                else:
                    severity = "warning"
                    recommendation = "Close monitoring and follow-up required"
                
                alerts.append(CriticalAlert(
                    finding=finding.title(),
                    source=source,
                    severity=severity,
                    recommendation=recommendation
                ))
        
        return alerts
    
    def generate_differential_with_confidence(
        self,
        symptoms: list[str],
        patient_history: dict | None = None,
        imaging_findings: str | None = None
    ) -> list[DiagnosisWithConfidence]:
        """
        Generate differential diagnoses with confidence scores.
        
        This is a simplified rule-based system for demonstration.
        In production, this would use ML/clinical algorithms.
        """
        differentials = []
        
        # Analyze symptoms for common patterns
        symptoms_lower = " ".join(symptoms).lower()
        
        # Respiratory pattern
        if any(s in symptoms_lower for s in ["cough", "dyspnea", "shortness of breath", "wheezing"]):
            # Check for specific conditions
            if "wheezing" in symptoms_lower:
                icd = self.lookup_icd10("asthma exacerbation")
                differentials.append(DiagnosisWithConfidence(
                    diagnosis="Asthma exacerbation",
                    confidence=0.75,
                    icd10_code=icd["code"] if icd else None,
                    icd10_description=icd["description"] if icd else None,
                    evidence=["Wheezing on exam", "History of asthma"]
                ))
            
            if "cough" in symptoms_lower and ("fever" in symptoms_lower or "productive" in symptoms_lower):
                icd = self.lookup_icd10("pneumonia")
                differentials.append(DiagnosisWithConfidence(
                    diagnosis="Community-acquired pneumonia",
                    confidence=0.65,
                    icd10_code=icd["code"] if icd else None,
                    icd10_description=icd["description"] if icd else None,
                    evidence=["Cough", "Possible fever"]
                ))
            
            if "cough" in symptoms_lower:
                icd = self.lookup_icd10("bronchitis")
                differentials.append(DiagnosisWithConfidence(
                    diagnosis="Acute bronchitis",
                    confidence=0.55,
                    icd10_code=icd["code"] if icd else None,
                    icd10_description=icd["description"] if icd else None,
                    evidence=["Persistent cough"]
                ))
        
        # Check imaging findings for additional diagnoses
        if imaging_findings:
            findings_lower = imaging_findings.lower()
            if any(f in findings_lower for f in ["nodule", "opacity", "mass", "lesion"]):
                icd = self.lookup_icd10("pulmonary nodule")
                differentials.append(DiagnosisWithConfidence(
                    diagnosis="Pulmonary nodule - requires follow-up",
                    confidence=0.85,
                    icd10_code=icd["code"] if icd else None,
                    icd10_description=icd["description"] if icd else None,
                    evidence=["Imaging finding: nodule/opacity"]
                ))
            
            if "interstitial" in findings_lower:
                differentials.append(DiagnosisWithConfidence(
                    diagnosis="Interstitial lung disease",
                    confidence=0.60,
                    icd10_code="J84.9",
                    icd10_description="Interstitial pulmonary disease, unspecified",
                    evidence=["Imaging: interstitial markings"]
                ))
        
        # Check patient history
        if patient_history and isinstance(patient_history, dict):
            raw_conditions = patient_history.get("conditions", [])
            conditions = [
                (c.get("name", "") if isinstance(c, dict) else str(c)).lower()
                for c in raw_conditions
            ]
            
            # Former smoker + respiratory symptoms
            if any("smok" in str(patient_history).lower() for _ in [1]):
                if symptoms_lower and "cough" in symptoms_lower:
                    differentials.append(DiagnosisWithConfidence(
                        diagnosis="COPD evaluation recommended",
                        confidence=0.50,
                        icd10_code="J44.9",
                        icd10_description="Chronic obstructive pulmonary disease, unspecified",
                        evidence=["Smoking history", "Respiratory symptoms"]
                    ))
        
        # Sort by confidence
        differentials.sort(key=lambda x: x.confidence, reverse=True)
        
        return differentials[:5]  # Return top 5
    
    def extract_evidence_citations(
        self,
        soap_section: str,
        transcription: str,
        imaging_findings: str | None = None
    ) -> list[dict]:
        """
        Extract evidence citations linking SOAP content to source material.
        
        Returns list of citations with text and source reference.
        """
        citations = []
        
        # Simple keyword matching for demo
        # In production, use NLP/semantic similarity
        keywords = [
            "cough", "dyspnea", "shortness of breath", "wheezing",
            "fever", "pain", "nodule", "opacity", "infiltrate",
            "blood pressure", "heart rate", "oxygen", "temperature"
        ]
        
        for keyword in keywords:
            if keyword in soap_section.lower():
                # Check if in transcription
                if keyword in transcription.lower():
                    # Find the sentence containing the keyword
                    sentences = transcription.split(".")
                    for sentence in sentences:
                        if keyword in sentence.lower():
                            citations.append({
                                "keyword": keyword,
                                "source": "transcription",
                                "context": sentence.strip()[:100] + "..."
                            })
                            break
                
                # Check if in imaging
                if imaging_findings and keyword in imaging_findings.lower():
                    citations.append({
                        "keyword": keyword,
                        "source": "imaging",
                        "context": "Imaging finding"
                    })
        
        return citations


# Singleton instance
_clinical_intel: ClinicalIntelligence | None = None


def get_clinical_intelligence() -> ClinicalIntelligence:
    """Get or create singleton instance."""
    global _clinical_intel
    if _clinical_intel is None:
        _clinical_intel = ClinicalIntelligence()
    return _clinical_intel
