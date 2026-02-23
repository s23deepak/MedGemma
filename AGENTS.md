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

### search_pubmed
Query PubMed via NCBI E-utils in one of three clinical synthesis modes.
- **Input**: `mode` (enum: "case_matcher" | "ebm_validator" | "ddi_monitor"), plus mode-specific fields:
  - *case_matcher*: `symptoms` (list), `atypical_markers` (list, optional), `max_results` (int)
  - *ebm_validator*: `assessment` (str), `plan` (str), `max_results` (int), `date_years_back` (int)
  - *ddi_monitor*: `medications` (list), `new_medications` (list, optional), `max_results_per_pair` (int), `date_years_back` (int)
- **Output**: `PubMedSearchResult` with articles, summary, key_findings, and mode-specific fields:
  - *case_matcher* → `rare_diagnoses` list
  - *ebm_validator* → `divergences` list (plan vs. latest evidence)
  - *ddi_monitor* → `ddi_alerts` list (novel interaction signals)
- **Modes**:
  - **Case Matcher (Zebra Hunt)**: Searches PubMed Case Reports for rare diagnoses matching unusual symptom clusters. Uses progressive query relaxation if no results — removes atypical markers one by one, then falls back to a broad "rare/unusual/atypical" filter.
  - **EBM Validator**: Retrieves Systematic Reviews, Meta-analyses, and RCTs from the last N years to validate a physician's plan. Flags divergences where current evidence differs from the proposed treatment.
  - **DDI Monitor**: Scans pharmacology literature for novel drug-drug interactions not yet captured in standard databases. Prioritizes pairs containing newly added medications. Caps at 12 drug pairs to respect NCBI rate limits.
- **Rate limiting**: 3 req/s by default; set `NCBI_API_KEY` env var for 10 req/s
- **Non-blocking**: After SOAP generation, PubMed analysis runs as a FastAPI `BackgroundTask` and can be polled via `GET /api/encounters/{session_id}/pubmed-insights`

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
