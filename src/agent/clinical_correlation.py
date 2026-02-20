"""
Clinical Correlation Module - Artifact Detection & Finding Classification

Handles two key clinical radiology principles:
1. Artifact detection: Identifying imaging artifacts that may affect interpretation
2. Clinical correlation: Distinguishing incidental findings from clinically significant ones

Example: A disc bulge on lumbar spine MRI is found in 30-40% of asymptomatic adults.
If the patient presents with knee pain (not back pain), the disc bulge is incidental.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ArtifactType(Enum):
    """Common imaging artifact types."""
    MOTION = "motion"
    METAL = "metal"
    POSITIONING = "positioning"
    EXPOSURE = "exposure"
    OVERLAP = "overlap"
    ROTATION = "rotation"
    TRUNCATION = "truncation"
    ALIASING = "aliasing"
    SUSCEPTIBILITY = "susceptibility"


class ArtifactSeverity(Enum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


class ArtifactImpact(Enum):
    NONE = "none"                # No impact on interpretation
    LIMITED = "limited"          # Some regions obscured
    SIGNIFICANT = "significant"  # Major impact, may need repeat


class FindingSignificance(Enum):
    CRITICAL = "critical"      # Urgent, requires immediate action
    SIGNIFICANT = "significant"  # Clinically relevant to this encounter
    INCIDENTAL = "incidental"  # Real finding but not related to complaint
    ARTIFACT = "artifact"      # Not a real finding, imaging artifact


class ImageQuality(Enum):
    DIAGNOSTIC = "diagnostic"          # Good quality, reliable interpretation
    ACCEPTABLE = "acceptable"          # Minor issues, interpretation possible
    DEGRADED = "degraded"              # Notable issues, limited interpretation
    NON_DIAGNOSTIC = "non-diagnostic"  # Cannot reliably interpret


@dataclass
class ImagingArtifact:
    """Represents an identified imaging artifact."""
    type: ArtifactType
    severity: ArtifactSeverity
    location: str
    description: str
    impact: ArtifactImpact
    recommendation: str  # e.g., "proceed", "repeat with corrections"

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "severity": self.severity.value,
            "location": self.location,
            "description": self.description,
            "impact": self.impact.value,
            "recommendation": self.recommendation
        }


@dataclass
class ClinicalFinding:
    """Represents a classified imaging finding."""
    description: str
    location: str
    significance: FindingSignificance
    clinically_correlated: bool
    correlation_reasoning: str
    prevalence_note: str | None = None
    recommended_action: str | None = None

    def to_dict(self) -> dict:
        result = {
            "description": self.description,
            "location": self.location,
            "significance": self.significance.value,
            "clinically_correlated": self.clinically_correlated,
            "correlation_reasoning": self.correlation_reasoning,
        }
        if self.prevalence_note:
            result["prevalence_note"] = self.prevalence_note
        if self.recommended_action:
            result["recommended_action"] = self.recommended_action
        return result


@dataclass
class CorrelationResult:
    """Complete correlation analysis result."""
    image_quality: ImageQuality
    artifacts: list[ImagingArtifact]
    findings: list[ClinicalFinding]
    correlation_summary: str
    chief_complaint: str
    symptoms: list[str]

    @property
    def has_artifacts(self) -> bool:
        return len(self.artifacts) > 0

    @property
    def significant_artifacts(self) -> list[ImagingArtifact]:
        return [a for a in self.artifacts if a.impact == ArtifactImpact.SIGNIFICANT]

    @property
    def clinically_correlated_findings(self) -> list[ClinicalFinding]:
        return [f for f in self.findings if f.clinically_correlated]

    @property
    def incidental_findings(self) -> list[ClinicalFinding]:
        return [f for f in self.findings if f.significance == FindingSignificance.INCIDENTAL]

    @property
    def critical_findings(self) -> list[ClinicalFinding]:
        return [f for f in self.findings if f.significance == FindingSignificance.CRITICAL]

    @property
    def needs_repeat_imaging(self) -> bool:
        return any(a.impact == ArtifactImpact.SIGNIFICANT for a in self.artifacts)

    def to_dict(self) -> dict:
        return {
            "image_quality": self.image_quality.value,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "findings": [f.to_dict() for f in self.findings],
            "correlation_summary": self.correlation_summary,
            "chief_complaint": self.chief_complaint,
            "symptoms": self.symptoms,
            "stats": {
                "total_findings": len(self.findings),
                "correlated": len(self.clinically_correlated_findings),
                "incidental": len(self.incidental_findings),
                "critical": len(self.critical_findings),
                "artifacts_found": len(self.artifacts),
                "needs_repeat": self.needs_repeat_imaging
            }
        }


# ============================================================
# Prevalence Database - Common Incidental Findings
# ============================================================

# Evidence-based prevalence data for common incidental findings
# in asymptomatic populations. Sources: peer-reviewed radiology literature.
INCIDENTAL_FINDINGS_PREVALENCE: dict[str, dict[str, Any]] = {
    # Spine
    "disc bulge": {
        "prevalence": "30-40% of asymptomatic adults",
        "body_parts": ["spine", "lumbar", "cervical", "thoracic"],
        "note": "Disc bulges are extremely common in asymptomatic individuals. "
                "A bulge alone does NOT indicate the source of a patient's pain. "
                "Clinical correlation with dermatomal symptoms is essential."
    },
    "disc protrusion": {
        "prevalence": "25-30% of asymptomatic adults under 60",
        "body_parts": ["spine", "lumbar", "cervical"],
        "note": "Similar to disc bulge — often incidental. Must correlate "
                "with radiculopathy pattern if present."
    },
    "disc degeneration": {
        "prevalence": "37% at age 20, 96% at age 80",
        "body_parts": ["spine", "lumbar", "cervical", "thoracic"],
        "note": "Degenerative disc disease is nearly universal with aging. "
                "It is a normal finding and does not equate to pathology."
    },
    "annular fissure": {
        "prevalence": "19-33% of asymptomatic adults",
        "body_parts": ["spine", "lumbar"],
        "note": "Annular fissures are common and usually not a source of pain."
    },
    "facet joint arthropathy": {
        "prevalence": "Up to 89% of adults over 60",
        "body_parts": ["spine", "lumbar", "cervical"],
        "note": "Facet arthropathy is age-related degeneration, "
                "not necessarily a pain generator."
    },
    "spondylolisthesis": {
        "prevalence": "6-7% of adults (grade I)",
        "body_parts": ["spine", "lumbar"],
        "note": "Low-grade (I) spondylolisthesis is often asymptomatic. "
                "Clinical significance depends on symptoms and stability."
    },
    # Abdomen
    "liver cyst": {
        "prevalence": "15-18% of the population",
        "body_parts": ["abdomen", "liver"],
        "note": "Simple hepatic cysts are benign and almost never clinically significant."
    },
    "renal cyst": {
        "prevalence": "27-32% of adults over 50",
        "body_parts": ["abdomen", "kidney", "renal"],
        "note": "Simple renal cysts (Bosniak I) are benign. "
                "No follow-up needed unless complex features are present."
    },
    "gallstone": {
        "prevalence": "10-15% of adults",
        "body_parts": ["abdomen", "gallbladder"],
        "note": "Most gallstones are asymptomatic. Only 1-4% per year become symptomatic."
    },
    "hepatic hemangioma": {
        "prevalence": "5-20% of the population",
        "body_parts": ["abdomen", "liver"],
        "note": "Hepatic hemangiomas are the most common benign liver tumor. "
                "They are incidental and require no treatment."
    },
    # Chest
    "pulmonary nodule": {
        "prevalence": "25-50% of chest CTs in adults",
        "body_parts": ["chest", "lung"],
        "note": "Small pulmonary nodules (<6mm) are very common and usually benign. "
                "Follow Fleischner Society guidelines for follow-up based on size and risk."
    },
    "aortic calcification": {
        "prevalence": "Common in adults over 50",
        "body_parts": ["chest", "aorta", "abdomen"],
        "note": "Mild aortic calcification is an age-related finding. "
                "Significant only if extensive or associated with aneurysm."
    },
    "pericardial effusion": {
        "prevalence": "Small effusions in 8-15% of echocardiograms",
        "body_parts": ["chest", "heart"],
        "note": "Small, physiologic pericardial effusions are often incidental."
    },
    # Joints / MSK
    "osteophyte": {
        "prevalence": "Very common in adults over 40",
        "body_parts": ["spine", "knee", "hip", "shoulder"],
        "note": "Osteophytes are bone spurs from normal aging/degeneration. "
                "Presence does not equate to symptoms."
    },
    "meniscal tear": {
        "prevalence": "Up to 36% of asymptomatic adults over 45",
        "body_parts": ["knee"],
        "note": "Degenerative meniscal tears are common without symptoms. "
                "Surgery is NOT recommended for incidental meniscal tears."
    },
    "rotator cuff tear": {
        "prevalence": "20-54% of adults over 60 (partial or full)",
        "body_parts": ["shoulder"],
        "note": "Partial rotator cuff tears are common with aging. "
                "Many are asymptomatic and do not require intervention."
    },
    # Brain
    "white matter lesion": {
        "prevalence": "11-21% of adults in their 60s",
        "body_parts": ["brain", "head"],
        "note": "White matter hyperintensities are common with aging and hypertension. "
                "May be incidental depending on clinical context."
    },
    "pineal cyst": {
        "prevalence": "1-4% of brain MRIs",
        "body_parts": ["brain", "head"],
        "note": "Pineal cysts are almost always benign and incidental."
    },
    "arachnoid cyst": {
        "prevalence": "1-2% of the population",
        "body_parts": ["brain", "head"],
        "note": "Arachnoid cysts are congenital and almost always incidental."
    },
}

# Body region → symptom mapping for clinical correlation
SYMPTOM_BODY_REGION_MAP: dict[str, list[str]] = {
    "lumbar spine": [
        "back pain", "lower back pain", "leg pain", "sciatica",
        "numbness in legs", "tingling in legs", "leg weakness",
        "radiculopathy", "cauda equina"
    ],
    "cervical spine": [
        "neck pain", "arm pain", "arm numbness", "hand tingling",
        "cervical radiculopathy", "myelopathy"
    ],
    "chest": [
        "chest pain", "shortness of breath", "dyspnea", "cough",
        "wheezing", "hemoptysis", "pleuritic pain"
    ],
    "abdomen": [
        "abdominal pain", "nausea", "vomiting", "diarrhea",
        "constipation", "bloating", "flank pain"
    ],
    "knee": [
        "knee pain", "knee swelling", "joint pain", "locking",
        "giving way", "knee instability"
    ],
    "shoulder": [
        "shoulder pain", "arm weakness", "limited range of motion",
        "overhead pain"
    ],
    "head": [
        "headache", "seizure", "dizziness", "confusion",
        "vision changes", "cognitive decline"
    ],
}


class ClinicalCorrelator:
    """
    Correlates imaging findings with clinical presentation.
    
    Implements the radiology principle: findings must be correlated
    with clinical symptoms to determine significance.
    """

    def __init__(self):
        self.prevalence_db = INCIDENTAL_FINDINGS_PREVALENCE
        self.symptom_map = SYMPTOM_BODY_REGION_MAP

    def correlate(
        self,
        findings: list[str],
        symptoms: list[str],
        chief_complaint: str = "",
        body_region: str = "",
        modality: str = "xray"
    ) -> CorrelationResult:
        """
        Correlate imaging findings with patient symptoms.

        Args:
            findings: List of imaging findings from model output
            symptoms: Patient's reported symptoms
            chief_complaint: Primary reason for visit
            body_region: Body region imaged
            modality: Imaging modality

        Returns:
            CorrelationResult with classified findings
        """
        classified_findings = []
        symptoms_lower = [s.lower().strip() for s in symptoms]
        complaint_lower = chief_complaint.lower().strip()

        for finding_text in findings:
            finding_lower = finding_text.lower()

            # Check if this is a known incidental finding
            prevalence_match = self._match_prevalence(finding_lower)

            # Check if finding correlates with symptoms
            is_correlated = self._check_symptom_correlation(
                finding_lower, symptoms_lower, complaint_lower, body_region
            )

            # Determine significance
            if self._is_critical_finding(finding_lower):
                significance = FindingSignificance.CRITICAL
                is_correlated = True  # Critical findings always matter
                reasoning = "Critical finding requiring immediate clinical attention regardless of presenting complaint."
                action = "Immediate physician review required"
            elif is_correlated:
                significance = FindingSignificance.SIGNIFICANT
                reasoning = self._build_correlation_reasoning(
                    finding_lower, symptoms_lower, complaint_lower, correlated=True
                )
                action = "Include in assessment and plan"
            elif prevalence_match:
                significance = FindingSignificance.INCIDENTAL
                reasoning = self._build_correlation_reasoning(
                    finding_lower, symptoms_lower, complaint_lower, correlated=False
                )
                action = "Document as incidental finding; no immediate action needed"
            else:
                # Unknown finding without clear correlation
                significance = FindingSignificance.SIGNIFICANT
                is_correlated = False
                reasoning = (
                    "Finding does not clearly correlate with presenting symptoms. "
                    "Clinical correlation recommended."
                )
                action = "Further clinical correlation recommended"

            classified_findings.append(ClinicalFinding(
                description=finding_text,
                location=body_region or "unspecified",
                significance=significance,
                clinically_correlated=is_correlated,
                correlation_reasoning=reasoning,
                prevalence_note=prevalence_match.get("prevalence") if prevalence_match else None,
                recommended_action=action
            ))

        # Build summary
        summary = self._build_correlation_summary(
            classified_findings, symptoms, chief_complaint
        )

        return CorrelationResult(
            image_quality=ImageQuality.DIAGNOSTIC,  # Updated by artifact analysis
            artifacts=[],  # Updated by artifact analysis
            findings=classified_findings,
            correlation_summary=summary,
            chief_complaint=chief_complaint,
            symptoms=symptoms
        )

    def check_artifacts(
        self,
        artifact_descriptions: list[dict[str, str]]
    ) -> tuple[ImageQuality, list[ImagingArtifact]]:
        """
        Parse and classify imaging artifacts.

        Args:
            artifact_descriptions: List of dicts with 'type', 'description', 'location'

        Returns:
            Tuple of (image_quality, list of ImagingArtifact)
        """
        artifacts = []
        for desc in artifact_descriptions:
            art_type = self._parse_artifact_type(desc.get("type", ""))
            severity = self._parse_severity(desc.get("severity", "mild"))

            impact = ArtifactImpact.NONE
            if severity == ArtifactSeverity.SEVERE:
                impact = ArtifactImpact.SIGNIFICANT
            elif severity == ArtifactSeverity.MODERATE:
                impact = ArtifactImpact.LIMITED

            recommendation = "Proceed with interpretation"
            if impact == ArtifactImpact.SIGNIFICANT:
                recommendation = "Consider repeating study with corrections"

            artifacts.append(ImagingArtifact(
                type=art_type,
                severity=severity,
                location=desc.get("location", "unspecified"),
                description=desc.get("description", ""),
                impact=impact,
                recommendation=recommendation
            ))

        # Determine overall image quality
        if any(a.impact == ArtifactImpact.SIGNIFICANT for a in artifacts):
            quality = ImageQuality.DEGRADED
        elif any(a.impact == ArtifactImpact.LIMITED for a in artifacts):
            quality = ImageQuality.ACCEPTABLE
        elif artifacts:
            quality = ImageQuality.DIAGNOSTIC
        else:
            quality = ImageQuality.DIAGNOSTIC

        return quality, artifacts

    def _match_prevalence(self, finding_lower: str) -> dict | None:
        """Check if a finding matches known incidental findings."""
        for key, data in self.prevalence_db.items():
            if key in finding_lower:
                return data
        return None

    def _check_symptom_correlation(
        self,
        finding_lower: str,
        symptoms_lower: list[str],
        complaint_lower: str,
        body_region: str
    ) -> bool:
        """Check if a finding correlates with patient's symptoms."""
        # Get expected symptoms for the body region
        region_lower = body_region.lower() if body_region else ""
        expected_symptoms: list[str] = []
        for region, symptoms_list in self.symptom_map.items():
            if region in region_lower or region_lower in region:
                expected_symptoms.extend(symptoms_list)

        # Check if any patient symptom matches expected symptoms for this region
        for symptom in symptoms_lower:
            for expected in expected_symptoms:
                if expected in symptom or symptom in expected:
                    return True

        # Check direct keyword overlap between finding and complaint
        finding_keywords = set(finding_lower.split())
        complaint_keywords = set(complaint_lower.split())
        symptom_keywords = set()
        for s in symptoms_lower:
            symptom_keywords.update(s.split())

        # Remove common medical stop words
        stop_words = {"the", "a", "an", "of", "in", "at", "with", "mild", "moderate",
                      "severe", "small", "large", "noted", "seen", "shows", "no", "is"}
        finding_keywords -= stop_words
        complaint_keywords -= stop_words
        symptom_keywords -= stop_words

        overlap = finding_keywords & (complaint_keywords | symptom_keywords)
        if len(overlap) >= 1:
            return True

        return False

    def _is_critical_finding(self, finding_lower: str) -> bool:
        """Check if a finding is critical regardless of symptoms."""
        critical_terms = [
            "pneumothorax", "tension pneumothorax",
            "aortic dissection", "aortic rupture",
            "pulmonary embolism", "pe",
            "stroke", "hemorrhage", "intracranial bleed",
            "fracture with displacement",
            "malignant", "mass suspicious for malignancy",
            "free air", "pneumoperitoneum",
            "cauda equina", "cord compression",
            "unstable fracture", "spinal cord injury",
            "cardiac tamponade",
            "large pleural effusion",
        ]
        return any(term in finding_lower for term in critical_terms)

    def _build_correlation_reasoning(
        self,
        finding_lower: str,
        symptoms_lower: list[str],
        complaint_lower: str,
        correlated: bool
    ) -> str:
        """Build human-readable correlation reasoning."""
        symptoms_str = ", ".join(symptoms_lower) if symptoms_lower else "none reported"
        prevalence = self._match_prevalence(finding_lower)

        if correlated:
            return (
                f"This finding is consistent with the patient's presenting symptoms "
                f"({symptoms_str}). It should be considered in the clinical assessment."
            )
        else:
            reasoning = (
                f"This finding does NOT correlate with the patient's presenting "
                f"complaint ({complaint_lower or 'not specified'}) or reported symptoms "
                f"({symptoms_str})."
            )
            if prevalence:
                reasoning += (
                    f" {prevalence['note']} "
                    f"Prevalence in asymptomatic individuals: {prevalence['prevalence']}."
                )
            return reasoning

    def _build_correlation_summary(
        self,
        findings: list[ClinicalFinding],
        symptoms: list[str],
        chief_complaint: str
    ) -> str:
        """Build overall correlation summary."""
        total = len(findings)
        correlated = sum(1 for f in findings if f.clinically_correlated)
        incidental = sum(1 for f in findings if f.significance == FindingSignificance.INCIDENTAL)
        critical = sum(1 for f in findings if f.significance == FindingSignificance.CRITICAL)

        parts = [f"Of {total} imaging finding(s):"]

        if critical:
            parts.append(f"  ⚠️ {critical} CRITICAL finding(s) requiring immediate attention")
        if correlated:
            parts.append(
                f"  ✅ {correlated} finding(s) clinically correlated with "
                f"presenting complaint ({chief_complaint or 'unspecified'})"
            )
        if incidental:
            parts.append(
                f"  ℹ️ {incidental} incidental finding(s) — common in asymptomatic "
                f"individuals, unlikely related to current symptoms"
            )
        uncorrelated = total - correlated - incidental - critical
        if uncorrelated > 0:
            parts.append(f"  ❓ {uncorrelated} finding(s) require further clinical correlation")

        if incidental:
            parts.append(
                "\n⚕️ Note: Incidental findings are documented for completeness but "
                "do not necessarily indicate pathology. Clinical correlation is essential."
            )

        return "\n".join(parts)

    def _parse_artifact_type(self, type_str: str) -> ArtifactType:
        """Parse artifact type from string."""
        type_lower = type_str.lower()
        for art_type in ArtifactType:
            if art_type.value in type_lower:
                return art_type
        return ArtifactType.MOTION  # Default

    def _parse_severity(self, severity_str: str) -> ArtifactSeverity:
        """Parse severity from string."""
        severity_lower = severity_str.lower()
        if "severe" in severity_lower:
            return ArtifactSeverity.SEVERE
        elif "moderate" in severity_lower:
            return ArtifactSeverity.MODERATE
        return ArtifactSeverity.MILD


# Singleton instance
_correlator: ClinicalCorrelator | None = None


def get_clinical_correlator() -> ClinicalCorrelator:
    """Get or create the singleton ClinicalCorrelator."""
    global _correlator
    if _correlator is None:
        _correlator = ClinicalCorrelator()
    return _correlator
