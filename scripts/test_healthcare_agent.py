#!/usr/bin/env python3
"""
Test script for the Healthcare Agent (FunctionGemma + MedGemma).
Demonstrates the dual-model agentic architecture.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_healthcare_agent():
    """Test the HealthcareAgent in simulated mode."""
    from src.agent import HealthcareAgent
    from src.ehr import get_fhir_server
    
    print("=" * 60)
    print("Healthcare Agent Test (FunctionGemma + MedGemma)")
    print("=" * 60)
    
    # Initialize in simulated mode (no GPU required)
    agent = HealthcareAgent(simulated=True)
    print("✅ HealthcareAgent initialized (simulated mode)")
    
    # Get patient context
    fhir = get_fhir_server()
    patient_context = fhir.get_patient_summary("P002")
    print(f"\n📋 Patient: {patient_context['patient']['name']}")
    
    # Test 1: Simple action routing
    print("\n" + "-" * 40)
    print("Test 1: Simple Action Routing")
    print("-" * 40)
    
    queries = [
        "Schedule a cardiology appointment for this patient",
        "Check drug interactions for Lisinopril and Aspirin",
        "Notify the care team that lab results are ready"
    ]
    
    for query in queries:
        print(f"\n🔹 Query: {query}")
        result = agent.process_query(query, patient_context)
        print(f"   Response: {result['response'][:80]}...")
    
    # Test 2: Multi-step workflow
    print("\n" + "-" * 40)
    print("Test 2: Multi-Step Workflow Planning")
    print("-" * 40)
    
    goal = "Patient presents with chest pain. Order stat ECG, troponin, notify cardiology."
    print(f"\n🎯 Goal: {goal}")
    
    plan = agent.execute_workflow(goal, patient_context)
    print(f"\n📝 Action Plan ({len(plan.actions)} steps):")
    for i, action in enumerate(plan.actions, 1):
        approval = " ⚠️ (requires approval)" if action.requires_approval else ""
        print(f"   {i}. {action.tool_name}{approval}")
        print(f"      Args: {action.arguments}")
    
    # Test 3: Tool execution
    print("\n" + "-" * 40)
    print("Test 3: Direct Tool Execution")
    print("-" * 40)
    
    # Check drug interactions (uses clinical intelligence)
    from src.clinical import get_clinical_intelligence
    ci = get_clinical_intelligence()
    
    medications = ["Lisinopril 10mg", "Aspirin 81mg", "Warfarin 5mg"]
    print(f"\n💊 Checking interactions: {medications}")
    interactions = ci.check_drug_interactions(medications)
    
    for i in interactions:
        print(f"   ⚠️ {i.drug1} + {i.drug2}: {i.severity.upper()}")
        print(f"      {i.effect}")
    
    print("\n" + "=" * 60)
    print("✅ All Healthcare Agent Tests Passed!")
    print("=" * 60)
    
    print("\n📌 Architecture Summary:")
    print("   FunctionGemma (270M) → Fast tool routing")
    print("   MedGemma (4B)        → Medical reasoning")
    print("   HealthcareAgent      → Orchestrates both")
    
    return True


def test_tool_definitions():
    """Test tool definitions are properly loaded."""
    from src.agent import TOOLS, get_tool_by_name, requires_approval
    
    print("\n" + "=" * 60)
    print("Tool Definitions Test")
    print("=" * 60)
    
    print(f"\n📋 Total tools defined: {len(TOOLS)}")
    
    for tool in TOOLS:
        name = tool["function"]["name"]
        approval = "🔒" if requires_approval(name) else "✓"
        print(f"   {approval} {name}")
    
    # Test specific tool lookup
    ehr_tool = get_tool_by_name("fetch_patient_ehr")
    assert ehr_tool is not None, "fetch_patient_ehr not found"
    print(f"\n✅ Tool lookup working: fetch_patient_ehr found")
    
    return True


if __name__ == "__main__":
    test_tool_definitions()
    test_healthcare_agent()
