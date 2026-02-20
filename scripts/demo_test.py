#!/usr/bin/env python3
"""
Doctor Dictation Demo Test Script

This script demonstrates the enhanced clinical features by simulating
a doctor dictation scenario with the enhanced SOAP generator.

Run with: python scripts/demo_test.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.clinical import get_clinical_intelligence
from src.soap import SOAPGenerator
from src.ehr import get_fhir_server


def demo_patient_encounter():
    """Simulate a complete patient encounter with clinical intelligence."""
    
    print("=" * 60)
    print("MedGemma Clinical Assistant - Demo Test")
    print("=" * 60)
    
    # Get clinical intelligence service
    ci = get_clinical_intelligence()
    sg = SOAPGenerator()
    fhir = get_fhir_server()
    
    # Get patient context from mock EHR
    patient_context = fhir.get_patient_summary("P002")  # Carlos Martinez - male with COPD
    print(f"\n📋 Patient: {patient_context['patient']['name']}")
    print(f"   Age: {patient_context['patient']['age']} y/o")
    print(f"   Gender: {patient_context['patient']['gender']}")
    
    # Print current medications
    print("\n💊 Current Medications:")
    for med in patient_context['medications']:
        print(f"   - {med['name']}")
    
    # Simulated doctor dictation
    dictation = """
    Chief complaint: Patient presents with worsening cough and wheezing over the past 3 weeks.
    
    History of present illness: 67-year-old male with known COPD presents with 
    productive cough, increased shortness of breath, and audible wheezing.
    Patient reports using rescue inhaler 4-5 times daily, up from 1-2 times.
    Denies fever, chills, or chest pain. Notes some increased fatigue.
    
    Physical exam: Temperature 98.4F, BP 142/88, HR 92, SpO2 94% on room air.
    Bilateral expiratory wheezes noted throughout lung fields.
    No accessory muscle use. Good air movement.
    """
    
    print("\n🎤 Doctor Dictation (simulated):")
    print("-" * 40)
    print(dictation[:200] + "...")
    
    # Simulated imaging findings
    imaging = "Chest X-ray shows hyperinflation. Right lower lobe opacity noted, possibly consolidation. Small scattered nodule in left upper lobe requires follow-up."
    
    print(f"\n🩻 Imaging Findings:")
    print(f"   {imaging}")
    
    # Generate enhanced SOAP with clinical intelligence
    print("\n" + "=" * 60)
    print("CLINICAL INTELLIGENCE ANALYSIS")
    print("=" * 60)
    
    # 1. Critical Finding Detection
    alerts = ci.detect_critical_findings(imaging, source="imaging")
    print("\n🚨 Critical Findings:")
    if alerts:
        for alert in alerts:
            print(f"   [{alert.severity.upper()}] {alert.finding}")
            print(f"   → {alert.recommendation}")
    else:
        print("   None detected")
    
    # 2. Drug Interaction Check
    current_meds = [med['name'] for med in patient_context['medications']]
    new_meds = ["Prednisone 40mg", "Azithromycin 500mg"]  # Typical COPD exacerbation treatment
    print(f"\n💊 Drug Interaction Check:")
    print(f"   Current: {', '.join(current_meds)}")
    print(f"   New Rx:  {', '.join(new_meds)}")
    
    interactions = ci.check_drug_interactions(current_meds, new_meds)
    if interactions:
        for interaction in interactions:
            print(f"   ⚠️ {interaction.drug1} + {interaction.drug2}")
            print(f"      Severity: {interaction.severity} | {interaction.effect}")
    else:
        print("   ✅ No significant interactions detected")
    
    # 3. Differential Diagnoses
    symptoms = ["cough", "wheezing", "dyspnea", "productive"]
    diffs = ci.generate_differential_with_confidence(
        symptoms=symptoms,
        patient_history=patient_context,
        imaging_findings=imaging
    )
    
    print(f"\n📊 Differential Diagnoses (Ranked by Confidence):")
    for i, d in enumerate(diffs, 1):
        icd = f"ICD-10: {d.icd10_code}" if d.icd10_code else ""
        print(f"   {i}. {d.diagnosis}")
        print(f"      Confidence: {d.confidence_percent} | {icd}")
        print(f"      Evidence: {', '.join(d.evidence)}")
    
    # 4. ICD-10 Lookup
    print(f"\n🔢 ICD-10 Code Suggestions:")
    diagnoses = ["COPD", "pneumonia", "pulmonary nodule"]
    for dx in diagnoses:
        code = ci.lookup_icd10(dx)
        if code:
            print(f"   {dx.title()}: {code['code']} - {code['description']}")
    
    # 5. Generate Enhanced SOAP
    print("\n" + "=" * 60)
    print("ENHANCED SOAP NOTE")
    print("=" * 60)
    
    enhanced_soap = sg.generate_enhanced_soap(
        transcription=dictation,
        patient_context=patient_context,
        image_findings=imaging
    )
    
    print(f"\n📄 SOAP Note Generated:")
    print(f"   Differentials: {len(enhanced_soap.differentials)}")
    print(f"   Drug Interactions: {len(enhanced_soap.drug_interactions)}")
    print(f"   Critical Alerts: {len(enhanced_soap.critical_alerts)}")
    print(f"   Evidence Citations: {len(enhanced_soap.evidence_citations)}")
    
    # Show a sample of the structured output
    soap_dict = enhanced_soap.to_dict()
    print(f"\n   Subjective: {soap_dict['subjective'][:100]}...")
    print(f"   Generated: {soap_dict['generated_at']}")
    
    print("\n" + "=" * 60)
    print("✅ DEMO COMPLETE - All Clinical Enhancements Working!")
    print("=" * 60)
    
    return enhanced_soap


if __name__ == "__main__":
    demo_patient_encounter()
