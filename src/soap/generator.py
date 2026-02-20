"""
SOAP Note Generator (Enhanced)
Structures clinical encounter data into standard SOAP format with:
- ICD-10 code suggestions
- Confidence scores for diagnoses
- Drug interaction alerts
- Evidence citations
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Import clinical intelligence
try:
    from src.clinical import (
        get_clinical_intelligence,
        DiagnosisWithConfidence,
        DrugInteraction,
        CriticalAlert,
    )
except ImportError:
    # Fallback if module not available
    get_clinical_intelligence = None


@dataclass
class EnhancedSOAPNote:
    """
    Enhanced SOAP note with clinical decision support features.
    """
    subjective: str
    objective: str
    assessment: str
    plan: str
    
    # Enhanced features
    differentials: list[dict] = field(default_factory=list)  # With confidence & ICD-10
    drug_interactions: list[dict] = field(default_factory=list)
    critical_alerts: list[dict] = field(default_factory=list)
    evidence_citations: list[dict] = field(default_factory=list)
    missed_diagnoses: list[str] = field(default_factory=list)
    
    generated_at: str | None = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "subjective": self.subjective,
            "objective": self.objective,
            "assessment": self.assessment,
            "plan": self.plan,
            "differentials": self.differentials,
            "drug_interactions": self.drug_interactions,
            "critical_alerts": self.critical_alerts,
            "evidence_citations": self.evidence_citations,
            "missed_diagnoses": self.missed_diagnoses,
            "generated_at": self.generated_at or datetime.now().isoformat()
        }
    
    def to_markdown(self) -> str:
        """Convert to formatted markdown."""
        sections = []
        
        # Header
        sections.append(f"# SOAP Note\n*Generated: {self.generated_at or datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
        
        # Critical alerts at top
        if self.critical_alerts:
            alerts_text = "\n".join(
                f"- 🚨 **{a.get('finding', 'Alert')}** ({a.get('severity', 'warning').upper()}): {a.get('recommendation', '')}"
                for a in self.critical_alerts
            )
            sections.append(f"## 🚨 Critical Alerts\n{alerts_text}\n")
        
        # Drug interactions
        if self.drug_interactions:
            interactions_text = "\n".join(
                f"- ⚠️ **{i['drug1']} + {i['drug2']}** ({i['severity']}): {i['effect']}"
                for i in self.drug_interactions
            )
            sections.append(f"## ⚠️ Drug Interactions\n{interactions_text}\n")
        
        # SOAP sections
        sections.append(f"## Subjective\n{self.subjective}\n")
        sections.append(f"## Objective\n{self.objective}\n")
        sections.append(f"## Assessment\n{self.assessment}\n")
        
        # Differential diagnoses with confidence
        if self.differentials:
            diff_text = "\n".join(
                f"- **{d['diagnosis']}** ({d['confidence_percent']}) - ICD-10: {d.get('icd10_code', 'N/A')}"
                for d in self.differentials
            )
            sections.append(f"### Differential Diagnoses\n{diff_text}\n")
        
        sections.append(f"## Plan\n{self.plan}\n")
        
        # Missed diagnoses
        if self.missed_diagnoses:
            diagnoses_text = "\n".join(f"- 🔍 {d}" for d in self.missed_diagnoses)
            sections.append(f"## Potential Missed Diagnoses\n{diagnoses_text}\n")
        
        return "\n".join(sections)
    
    def to_html(self) -> str:
        """Convert to enhanced HTML for display with all features."""
        html_parts = []
        
        # Critical alerts (prominent red banner)
        if self.critical_alerts:
            alerts_html = "".join(
                f'''<div class="critical-alert-item {a.get('severity', 'warning')}">
                    <span class="alert-icon">🚨</span>
                    <div class="alert-content">
                        <strong>{a.get('finding', 'Alert')}</strong>
                        <span class="severity-badge">{a.get('severity', 'warning').upper()}</span>
                        <p>{a.get('recommendation', '')}</p>
                    </div>
                </div>'''
                for a in self.critical_alerts
            )
            html_parts.append(f'''
            <div class="soap-critical-alerts">
                <h3>🚨 Critical Findings</h3>
                {alerts_html}
            </div>
            ''')
        
        # Drug interactions
        if self.drug_interactions:
            interactions_html = "".join(
                f'''<div class="drug-interaction-item severity-{i['severity']}">
                    <span class="drug-pair">{i['drug1']} ↔ {i['drug2']}</span>
                    <span class="severity-badge {i['severity']}">{i['severity'].upper()}</span>
                    <p class="effect">{i['effect']}</p>
                </div>'''
                for i in self.drug_interactions
            )
            html_parts.append(f'''
            <div class="soap-drug-interactions">
                <h3>💊 Drug Interaction Alerts</h3>
                {interactions_html}
            </div>
            ''')
        
        # SOAP sections
        html_parts.append(f'''
        <div class="soap-section subjective">
            <h3>S - Subjective</h3>
            <div class="content">{self._format_html_content(self.subjective)}</div>
        </div>
        ''')
        
        html_parts.append(f'''
        <div class="soap-section objective">
            <h3>O - Objective</h3>
            <div class="content">{self._format_html_content(self.objective)}</div>
        </div>
        ''')
        
        # Assessment with differentials
        assessment_html = self._format_html_content(self.assessment)
        
        if self.differentials:
            diff_html = "".join(
                f'''<div class="differential-item">
                    <div class="diagnosis-header">
                        <span class="diagnosis-name">{d['diagnosis']}</span>
                        <span class="confidence-badge" style="--confidence: {d['confidence']}">{d['confidence_percent']}</span>
                    </div>
                    <div class="diagnosis-details">
                        {f'<span class="icd-code">ICD-10: {d["icd10_code"]}</span>' if d.get('icd10_code') else ''}
                        {f'<span class="icd-desc">{d.get("icd10_description", "")}</span>' if d.get('icd10_description') else ''}
                    </div>
                    <div class="evidence-list">
                        {''.join(f'<span class="evidence-tag" data-source="transcription">{e}</span>' for e in d.get('evidence', []))}
                    </div>
                </div>'''
                for d in self.differentials
            )
            assessment_html += f'''
            <div class="differential-diagnosis-section">
                <h4>Differential Diagnoses (Ranked by Confidence)</h4>
                <div class="differentials-list">{diff_html}</div>
            </div>
            '''
        
        html_parts.append(f'''
        <div class="soap-section assessment">
            <h3>A - Assessment</h3>
            <div class="content">{assessment_html}</div>
        </div>
        ''')
        
        html_parts.append(f'''
        <div class="soap-section plan">
            <h3>P - Plan</h3>
            <div class="content">{self._format_html_content(self.plan)}</div>
        </div>
        ''')
        
        # Missed diagnoses (if still separate from differentials)
        if self.missed_diagnoses:
            diagnoses_html = "".join(f'<li>{d}</li>' for d in self.missed_diagnoses)
            html_parts.append(f'''
            <div class="soap-missed-diagnoses">
                <h3>🔍 Additional Considerations</h3>
                <ul>{diagnoses_html}</ul>
            </div>
            ''')
        
        # Evidence citations footer
        if self.evidence_citations:
            citations_html = "".join(
                f'<span class="citation-tag" data-source="{c.get("source", "")}">{c.get("keyword", "")}</span>'
                for c in self.evidence_citations[:10]  # Limit to 10
            )
            html_parts.append(f'''
            <div class="soap-evidence-footer">
                <h4>Evidence Sources</h4>
                <div class="citations-list">{citations_html}</div>
            </div>
            ''')
        
        return f'''
        <div class="soap-note enhanced" data-generated="{self.generated_at or datetime.now().isoformat()}">
            {"".join(html_parts)}
        </div>
        '''
    
    def _format_html_content(self, text: str) -> str:
        """Format text content for HTML display."""
        lines = text.split("\n")
        formatted_lines = []
        in_list = False
        
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("- ") or stripped.startswith("* "):
                if not in_list:
                    formatted_lines.append("<ul>")
                    in_list = True
                formatted_lines.append(f"<li>{stripped[2:]}</li>")
            else:
                if in_list:
                    formatted_lines.append("</ul>")
                    in_list = False
                if stripped:
                    formatted_lines.append(f"<p>{stripped}</p>")
        
        if in_list:
            formatted_lines.append("</ul>")
        
        return "\n".join(formatted_lines)


# Keep backward compatibility with original SOAPNote
@dataclass
class SOAPNote:
    """Structured SOAP note representation (legacy compatibility)."""
    subjective: str
    objective: str
    assessment: str
    plan: str
    missed_diagnoses: list[str] | None = None
    critical_alerts: list[str] | None = None
    generated_at: str | None = None
    
    def to_dict(self) -> dict:
        return {
            "subjective": self.subjective,
            "objective": self.objective,
            "assessment": self.assessment,
            "plan": self.plan,
            "missed_diagnoses": self.missed_diagnoses or [],
            "critical_alerts": self.critical_alerts or [],
            "generated_at": self.generated_at or datetime.now().isoformat()
        }
    
    def to_markdown(self) -> str:
        sections = []
        sections.append(f"# SOAP Note\n*Generated: {self.generated_at or datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
        if self.critical_alerts:
            alert_text = "\n".join(f"- ⚠️ {alert}" for alert in self.critical_alerts)
            sections.append(f"## ⚠️ Critical Alerts\n{alert_text}\n")
        sections.append(f"## Subjective\n{self.subjective}\n")
        sections.append(f"## Objective\n{self.objective}\n")
        sections.append(f"## Assessment\n{self.assessment}\n")
        sections.append(f"## Plan\n{self.plan}\n")
        if self.missed_diagnoses:
            diagnoses_text = "\n".join(f"- 🔍 {d}" for d in self.missed_diagnoses)
            sections.append(f"## Potential Missed Diagnoses\n{diagnoses_text}\n")
        return "\n".join(sections)
    
    def to_html(self) -> str:
        html_parts = []
        if self.critical_alerts:
            alerts_html = "".join(f'<li class="alert-item">{alert}</li>' for alert in self.critical_alerts)
            html_parts.append(f'<div class="soap-alerts"><h3>⚠️ Critical Alerts</h3><ul>{alerts_html}</ul></div>')
        html_parts.append(f'<div class="soap-section subjective"><h3>S - Subjective</h3><div class="content"><p>{self.subjective}</p></div></div>')
        html_parts.append(f'<div class="soap-section objective"><h3>O - Objective</h3><div class="content"><p>{self.objective}</p></div></div>')
        html_parts.append(f'<div class="soap-section assessment"><h3>A - Assessment</h3><div class="content"><p>{self.assessment}</p></div></div>')
        html_parts.append(f'<div class="soap-section plan"><h3>P - Plan</h3><div class="content"><p>{self.plan}</p></div></div>')
        if self.missed_diagnoses:
            diagnoses_html = "".join(f'<li>{d}</li>' for d in self.missed_diagnoses)
            html_parts.append(f'<div class="soap-missed-diagnoses"><h3>🔍 Potential Missed Diagnoses</h3><ul>{diagnoses_html}</ul></div>')
        return f'<div class="soap-note" data-generated="{self.generated_at or datetime.now().isoformat()}">{"".join(html_parts)}</div>'


class SOAPGenerator:
    """
    Enhanced SOAP note generator with clinical decision support.
    """
    
    def __init__(self):
        self.clinical_intel = None
        if get_clinical_intelligence:
            try:
                self.clinical_intel = get_clinical_intelligence()
            except Exception:
                pass
    
    def generate_enhanced_soap(
        self,
        transcription: str,
        patient_context: dict | None = None,
        image_findings: str | None = None,
        raw_soap_text: str | None = None
    ) -> EnhancedSOAPNote:
        """
        Generate an enhanced SOAP note with all clinical intelligence features.
        
        Args:
            transcription: Clinical encounter transcription
            patient_context: EHR patient data
            image_findings: Medical image analysis results
            raw_soap_text: Optional raw SOAP text from MedGemma
            
        Returns:
            EnhancedSOAPNote with all features populated
        """
        # Parse base SOAP if provided
        if raw_soap_text:
            base_soap = self.parse_from_text(raw_soap_text)
        else:
            # Generate placeholder structure
            base_soap = SOAPNote(
                subjective=transcription[:500] if transcription else "No subjective data",
                objective="Physical examination pending",
                assessment="Assessment pending clinical review",
                plan="Plan pending clinical review"
            )
        
        # Initialize enhanced note
        enhanced = EnhancedSOAPNote(
            subjective=base_soap.subjective,
            objective=base_soap.objective,
            assessment=base_soap.assessment,
            plan=base_soap.plan,
            missed_diagnoses=base_soap.missed_diagnoses or [],
            generated_at=datetime.now().isoformat()
        )
        
        if self.clinical_intel:
            # Extract symptoms from transcription for differential
            symptoms = self._extract_symptoms(transcription)
            
            # Generate differential diagnoses with confidence
            differentials = self.clinical_intel.generate_differential_with_confidence(
                symptoms=symptoms,
                patient_history=patient_context,
                imaging_findings=image_findings
            )
            enhanced.differentials = [d.to_dict() for d in differentials]
            
            # Check for critical findings
            all_text = f"{transcription} {image_findings or ''}"
            critical_alerts = self.clinical_intel.detect_critical_findings(
                all_text, 
                source="clinical_encounter"
            )
            enhanced.critical_alerts = [a.to_dict() for a in critical_alerts]
            
            # Check drug interactions
            if patient_context and "medications" in patient_context:
                current_meds = [m.get("name", "") for m in patient_context["medications"]]
                interactions = self.clinical_intel.check_drug_interactions(current_meds)
                enhanced.drug_interactions = [i.to_dict() for i in interactions]
            
            # Extract evidence citations
            citations = self.clinical_intel.extract_evidence_citations(
                base_soap.assessment,
                transcription,
                image_findings
            )
            enhanced.evidence_citations = citations
        
        return enhanced
    
    def _extract_symptoms(self, transcription: str) -> list[str]:
        """Extract symptom keywords from transcription."""
        symptom_keywords = [
            "cough", "dyspnea", "shortness of breath", "wheezing", "chest pain",
            "fever", "chills", "fatigue", "weakness", "weight loss", "weight gain",
            "nausea", "vomiting", "diarrhea", "constipation", "abdominal pain",
            "headache", "dizziness", "syncope", "palpitations", "edema",
            "pain", "swelling", "rash", "itching", "numbness", "tingling"
        ]
        
        transcription_lower = transcription.lower()
        found_symptoms = []
        
        for symptom in symptom_keywords:
            if symptom in transcription_lower:
                found_symptoms.append(symptom)
        
        return found_symptoms
    
    def parse_from_text(self, raw_text: str) -> SOAPNote:
        """Parse a raw SOAP note text into structured format."""
        sections = {
            "subjective": "",
            "objective": "",
            "assessment": "",
            "plan": ""
        }
        
        missed_diagnoses = []
        critical_alerts = []
        
        section_patterns = [
            (r"(?:##?\s*)?(?:S(?:ubjective)?[:\s]*)", "subjective"),
            (r"(?:##?\s*)?(?:O(?:bjective)?[:\s]*)", "objective"),
            (r"(?:##?\s*)?(?:A(?:ssessment)?[:\s]*)", "assessment"),
            (r"(?:##?\s*)?(?:P(?:lan)?[:\s]*)", "plan"),
        ]
        
        boundaries = []
        for pattern, section_name in section_patterns:
            for match in re.finditer(pattern, raw_text, re.IGNORECASE):
                boundaries.append((match.start(), match.end(), section_name))
        
        boundaries.sort(key=lambda x: x[0])
        
        for i, (start, end, section_name) in enumerate(boundaries):
            if i + 1 < len(boundaries):
                content_end = boundaries[i + 1][0]
            else:
                content_end = len(raw_text)
            content = raw_text[end:content_end].strip()
            sections[section_name] = content
        
        # Extract missed diagnoses
        missed_pattern = r"(?:Missed\s+Diagnos[ie]s?|Potential\s+Diagnos[ie]s?)[:\s]*(.*?)(?=\n##|\n\*\*|$)"
        missed_match = re.search(missed_pattern, raw_text, re.IGNORECASE | re.DOTALL)
        if missed_match:
            missed_text = missed_match.group(1)
            missed_diagnoses = [
                line.strip().lstrip("-*• ")
                for line in missed_text.split("\n")
                if line.strip() and not line.strip().startswith("#")
            ]
        
        # Extract critical alerts
        alert_pattern = r"(?:Critical\s+(?:Alerts?|Findings?)|URGENT)[:\s]*(.*?)(?=\n##|\n\*\*|$)"
        alert_match = re.search(alert_pattern, raw_text, re.IGNORECASE | re.DOTALL)
        if alert_match:
            alert_text = alert_match.group(1)
            critical_alerts = [
                line.strip().lstrip("-*• ")
                for line in alert_text.split("\n")
                if line.strip() and not line.strip().startswith("#")
            ]
        
        return SOAPNote(
            subjective=sections["subjective"],
            objective=sections["objective"],
            assessment=sections["assessment"],
            plan=sections["plan"],
            missed_diagnoses=missed_diagnoses if missed_diagnoses else None,
            critical_alerts=critical_alerts if critical_alerts else None,
            generated_at=datetime.now().isoformat()
        )
    
    def generate_template(
        self,
        chief_complaint: str,
        transcription: str,
        patient_context: dict | None = None,
        image_findings: str | None = None
    ) -> str:
        """Generate a SOAP note prompt template for MedGemma."""
        parts = [f"**Chief Complaint:** {chief_complaint}"]
        parts.append(f"\n**Clinical Encounter Transcription:**\n{transcription}")
        
        if patient_context:
            parts.append(f"\n**Patient Context:**")
            
            if "patient" in patient_context:
                p = patient_context["patient"]
                parts.append(f"- Patient: {p.get('name', 'Unknown')}, {p.get('age', 'Unknown')} y/o {p.get('gender', 'Unknown')}")
            
            if "conditions" in patient_context:
                conditions = [c.get("name", "Unknown") for c in patient_context["conditions"]]
                parts.append(f"- Active Conditions: {', '.join(conditions)}")
            
            if "medications" in patient_context:
                meds = [m.get("name", "Unknown") for m in patient_context["medications"]]
                parts.append(f"- Current Medications: {', '.join(meds)}")
            
            if "allergies" in patient_context:
                allergies = [a.get("substance", "Unknown") for a in patient_context["allergies"]]
                parts.append(f"- Allergies: {', '.join(allergies)}")
        
        if image_findings:
            parts.append(f"\n**Imaging Findings:**\n{image_findings}")
        
        return "\n".join(parts)
