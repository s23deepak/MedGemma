# MedGemma Clinical Assistant - Architecture Flow

## End-to-End Process Flow

```mermaid
flowchart TB
    subgraph User["👨‍⚕️ Physician Interface"]
        A[Voice Input / Text] --> B[Upload X-ray Image]
    end

    subgraph Frontend["🖥️ Web UI"]
        B --> C[WebSocket ASR]
        C --> D[Real-time Transcription]
    end

    subgraph Router["🔀 FunctionGemma Router (270M)"]
        D --> E{Query Type?}
        E -->|Simple Action| F[Tool Selection]
        E -->|Medical Query| G[Escalate to MedGemma]
    end

    subgraph Tools["🔧 Healthcare Tools"]
        F --> H[fetch_patient_ehr]
        F --> I[schedule_appointment]
        F --> J[order_lab_tests]
        F --> K[notify_care_team]
        F --> L[check_drug_interactions]
    end

    subgraph MedGemma["🧠 MedGemma (4B)"]
        G --> M[analyze_medical_image]
        G --> N[generate_soap_note]
        M --> O[Clinical Reasoning]
        N --> O
    end

    subgraph Clinical["📊 Clinical Intelligence"]
        O --> P[ICD-10 Codes]
        O --> Q[Confidence Scores]
        O --> R[Critical Alerts]
        O --> S[Drug Interactions]
        O --> T[Differential Diagnosis]
    end

    subgraph Output["📋 Enhanced SOAP Note"]
        P --> U[Final Report]
        Q --> U
        R --> U
        S --> U
        T --> U
        H --> U
    end

    subgraph Approval["✅ Physician Approval"]
        U --> V{Approve?}
        V -->|Yes| W[Update EHR]
        V -->|No| X[Edit & Resubmit]
    end

    W --> Y[(FHIR EHR)]
```

---

## Dual-Model Architecture

```mermaid
flowchart LR
    subgraph Input["Input Layer"]
        A1[Text Query]
        A2[Medical Image]
        A3[Patient Context]
    end

    subgraph FG["FunctionGemma 270M"]
        B1[Tool Router]
        B2[Action Planner]
        B3[Multi-step Workflow]
    end

    subgraph MG["MedGemma 4B"]
        C1[Vision Encoder]
        C2[Medical Reasoning]
        C3[SOAP Generation]
    end

    subgraph Execute["Execution"]
        D1[FHIR API]
        D2[Scheduling System]
        D3[Notification Service]
    end

    A1 --> B1
    B1 -->|Simple| D1
    B1 -->|Medical| C2
    A2 --> C1
    C1 --> C2
    A3 --> C2
    C2 --> C3
    B2 --> D2
    B3 --> D3
```

---

## Request Processing Pipeline

```mermaid
sequenceDiagram
    participant P as Physician
    participant UI as Web UI
    participant FG as FunctionGemma
    participant MG as MedGemma
    participant FHIR as EHR System
    participant CI as Clinical Intel

    P->>UI: Start encounter + upload X-ray
    UI->>FG: Route request
    
    alt Simple Action (scheduling, notifications)
        FG->>FHIR: Execute tool directly
        FHIR-->>UI: Result
    else Medical Query (diagnosis, imaging)
        FG->>MG: Escalate for reasoning
        MG->>MG: Analyze image
        MG->>CI: Get clinical intelligence
        CI-->>MG: ICD-10, alerts, interactions
        MG-->>UI: Enhanced SOAP note
    end
    
    UI->>P: Display for approval
    P->>UI: Approve
    UI->>FHIR: Update patient record
```

---

## Tool Routing Decision Tree

```mermaid
flowchart TD
    A[Incoming Query] --> B{Contains Image?}
    B -->|Yes| C[MedGemma Vision]
    B -->|No| D{Query Type}
    
    D -->|"Schedule appointment"| E[schedule_appointment]
    D -->|"Check medications"| F[check_drug_interactions]
    D -->|"Get patient data"| G[fetch_patient_ehr]
    D -->|"Notify team"| H[notify_care_team]
    D -->|"Order labs"| I[order_lab_tests]
    D -->|"Clinical question"| J[MedGemma Reasoning]
    
    C --> K[Clinical Intelligence]
    J --> K
    K --> L[Enhanced SOAP Note]
    
    E --> M{Requires Approval?}
    I --> M
    M -->|Yes| N[Queue for Physician]
    M -->|No| O[Execute Immediately]
```

---

## Component Summary

| Layer | Component | Model/Tech | Purpose |
|-------|-----------|------------|---------|
| **Routing** | FunctionGemma | Gemma 3 270M | Fast tool selection |
| **Reasoning** | MedGemma | 4B multimodal | Medical analysis |
| **Vision** | MedGemma | SigLIP encoder | X-ray/CT analysis |
| **Clinical** | Intelligence | Rule-based + ML | ICD-10, alerts |
| **EHR** | FHIR Server | Mock/Real | Patient data |
| **Frontend** | FastAPI + JS | WebSocket | Real-time UI |
