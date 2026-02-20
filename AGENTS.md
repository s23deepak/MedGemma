# MedGemma Clinical Assistant

An AI-powered clinical decision support system for the MedGemma Impact Challenge.

## Agent Description

This agent assists physicians with clinical encounters by:
1. **Listening** to doctor-patient conversations via MedASR
2. **Analyzing** medical images (CT, MRI, X-ray) with MedGemma
3. **Fetching** patient context from EHR via FHIR
4. **Generating** SOAP documentation with missed diagnosis detection
5. **Updating** EHR records upon physician approval

## Available Tools

### fetch_patient_ehr
Retrieve patient data from FHIR server.
- **Input**: `patient_id` (string)
- **Output**: Patient demographics, conditions, medications, allergies, recent observations

### analyze_medical_image  
Analyze medical imaging with clinical context.
- **Input**: `image_path` (string), `modality` (string: "xray", "ct", "mri")
- **Output**: Structured findings, potential concerns, comparison notes

### generate_soap_note
Generate structured SOAP documentation from encounter data.
- **Input**: `encounter_data` (object with transcription, image_findings, patient_context)
- **Output**: Formatted SOAP note with highlighted recommendations

### update_ehr
Update patient electronic health record.
- **Input**: `patient_id` (string), `updates` (object)
- **Requires**: Physician approval before execution
- **Output**: Confirmation of record update

## Safety Constraints

1. **Never diagnose autonomously** - All findings are suggestions requiring physician validation
2. **Flag critical findings** - Urgent conditions trigger immediate alerts
3. **Require approval** - EHR updates must be explicitly approved by the physician
4. **Audit trail** - All AI suggestions and physician decisions are logged

## Usage Context

This agent operates in a clinical setting where:
- A physician is conducting a patient encounter
- Medical images may be reviewed during the visit
- The physician dictates observations and findings
- Documentation is generated in real-time for review
