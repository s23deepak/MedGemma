"""
Rare disease knowledge base for the TTT-inspired diagnostic director.

Organized by organ system. Each entry contains:
  - name:               Disease name
  - icd10:              Primary ICD-10-CM code
  - system:             Organ system category
  - trigger_symptoms:   Any 2+ of these → seed this disease as a hypothesis
  - weighted_symptoms:  {symptom: weight} for coverage scoring (0.0–1.0)
  - contraindications:  Symptoms/findings that reduce coherence score
  - confirmatory_tests: Ordered list of recommended workup steps
  - specialist_type:    Primary specialist to involve
  - urgency:            "urgent" | "elective" | "low"
  - mimics:             Other diseases commonly confused with this one
"""
from __future__ import annotations

_ONTOLOGY: list[dict] = [
    # ─────────────────────────────────────────────────────────────
    # RHEUMATOLOGIC / AUTOIMMUNE
    # ─────────────────────────────────────────────────────────────
    {
        "name": "Systemic Lupus Erythematosus (SLE)",
        "icd10": "M32.9",
        "system": "rheumatologic",
        "trigger_symptoms": [
            "malar rash", "photosensitivity", "oral ulcers", "serositis",
            "nephritis", "cytopenias", "arthritis", "positive ANA",
        ],
        "weighted_symptoms": {
            "malar rash": 0.9, "photosensitivity": 0.8, "oral ulcers": 0.7,
            "serositis": 0.8, "proteinuria": 0.85, "cytopenias": 0.7,
            "arthritis": 0.6, "fatigue": 0.4, "fever": 0.5, "hair loss": 0.6,
            "pleuritis": 0.75, "pericarditis": 0.75, "positive ANA": 0.9,
            "anti-dsDNA": 1.0,
        },
        "contraindications": ["negative ANA", "skin biopsy negative for lupus"],
        "confirmatory_tests": [
            "ANA panel (anti-dsDNA, anti-Smith, anti-Ro/La, anti-Sm)",
            "Complement levels (C3, C4, CH50)",
            "Urinalysis with microscopy (casts)",
            "CBC with differential",
            "24-hour urine protein",
            "Renal biopsy if nephritis suspected",
        ],
        "specialist_type": "Rheumatology",
        "urgency": "urgent",
        "mimics": [
            "Mixed Connective Tissue Disease (MCTD)",
            "Undifferentiated Connective Tissue Disease",
            "Drug-induced lupus",
        ],
    },
    {
        "name": "Antiphospholipid Syndrome (APS)",
        "icd10": "D68.61",
        "system": "rheumatologic",
        "trigger_symptoms": [
            "recurrent thrombosis", "recurrent miscarriage", "livedo reticularis",
            "thrombocytopenia", "stroke in young patient",
        ],
        "weighted_symptoms": {
            "recurrent DVT": 0.9, "pulmonary embolism": 0.85, "stroke": 0.8,
            "livedo reticularis": 0.8, "thrombocytopenia": 0.7,
            "recurrent miscarriage": 0.9, "prolonged aPTT": 0.8,
        },
        "contraindications": ["negative antiphospholipid antibodies on repeat testing"],
        "confirmatory_tests": [
            "Lupus anticoagulant",
            "Anti-cardiolipin antibodies (IgG, IgM)",
            "Anti-β2-glycoprotein I antibodies",
            "Repeat testing after 12 weeks to confirm persistence",
        ],
        "specialist_type": "Hematology / Rheumatology",
        "urgency": "urgent",
        "mimics": ["SLE", "Heparin-induced thrombocytopenia (HIT)", "APLA-negative thrombophilia"],
    },
    {
        "name": "ANCA-Associated Vasculitis (GPA/MPA/EGPA)",
        "icd10": "M31.30",
        "system": "rheumatologic",
        "trigger_symptoms": [
            "hemoptysis", "sinusitis", "hematuria", "pulmonary infiltrates",
            "nasal crusting", "rapidly progressive glomerulonephritis",
            "mononeuritis multiplex",
        ],
        "weighted_symptoms": {
            "hemoptysis": 0.85, "sinusitis": 0.65, "nasal ulceration": 0.9,
            "hematuria": 0.8, "red cell casts": 0.9, "creatinine rise": 0.75,
            "pulmonary infiltrates": 0.7, "peripheral neuropathy": 0.7,
            "eosinophilia": 0.8, "asthma": 0.6,
        },
        "contraindications": ["negative ANCA (PR3 and MPO)"],
        "confirmatory_tests": [
            "c-ANCA (PR3) and p-ANCA (MPO) ELISA",
            "Urinalysis with microscopy (RBC casts)",
            "Creatinine and BUN",
            "Chest CT",
            "Tissue biopsy (nasal, renal, or lung)",
            "Bronchoscopy with BAL if pulmonary hemorrhage",
        ],
        "specialist_type": "Rheumatology / Nephrology",
        "urgency": "urgent",
        "mimics": ["Anti-GBM disease", "SLE nephritis", "Eosinophilic granulomatosis with polyangiitis"],
    },
    {
        "name": "Hemophagocytic Lymphohistiocytosis (HLH)",
        "icd10": "D76.1",
        "system": "rheumatologic",
        "trigger_symptoms": [
            "recurrent fever", "splenomegaly", "cytopenias", "elevated ferritin",
            "hypertriglyceridemia", "hemophagocytosis",
        ],
        "weighted_symptoms": {
            "fever": 0.7, "splenomegaly": 0.8, "cytopenias": 0.85,
            "elevated ferritin": 1.0, "hypertriglyceridemia": 0.8,
            "low fibrinogen": 0.8, "elevated LDH": 0.7, "NK cell dysfunction": 0.9,
            "hemophagocytosis on biopsy": 1.0,
        },
        "contraindications": ["ferritin < 500 ng/mL without other explanation"],
        "confirmatory_tests": [
            "Ferritin (markedly elevated, >500 ng/mL, often >10,000)",
            "Triglycerides",
            "Fibrinogen",
            "CBC with differential",
            "LDH",
            "NK cell activity assay",
            "Soluble CD25 (IL-2 receptor)",
            "Bone marrow biopsy for hemophagocytosis",
            "Genetic testing for familial HLH (PRF1, UNC13D, STX11)",
            "Infection workup (EBV, CMV, HIV, fungal)",
        ],
        "specialist_type": "Hematology / Rheumatology",
        "urgency": "urgent",
        "mimics": ["Sepsis", "Adult-onset Still's disease", "Malignant lymphoma"],
    },
    {
        "name": "Adult-Onset Still's Disease (AOSD)",
        "icd10": "M06.1",
        "system": "rheumatologic",
        "trigger_symptoms": [
            "quotidian fever", "salmon-colored rash", "arthritis",
            "elevated ferritin", "sore throat",
        ],
        "weighted_symptoms": {
            "quotidian fever": 0.9, "salmon rash": 0.95, "arthritis": 0.75,
            "elevated ferritin": 0.85, "splenomegaly": 0.7, "lymphadenopathy": 0.6,
            "leukocytosis": 0.65, "sore throat": 0.6,
        },
        "contraindications": ["positive ANA", "positive RF", "positive anti-dsDNA"],
        "confirmatory_tests": [
            "Ferritin (markedly elevated, glycosylated fraction)",
            "CBC with differential",
            "ESR and CRP",
            "ANA, RF (to exclude other autoimmune diseases)",
            "Infection workup (EBV, CMV, Parvovirus)",
            "Liver function tests",
        ],
        "specialist_type": "Rheumatology",
        "urgency": "elective",
        "mimics": ["HLH", "Infectious mononucleosis", "Lymphoma", "SLE"],
    },
    {
        "name": "Inflammatory Myopathy (Polymyositis/Dermatomyositis)",
        "icd10": "M33.20",
        "system": "rheumatologic",
        "trigger_symptoms": [
            "proximal muscle weakness", "elevated CK", "heliotrope rash",
            "Gottron papules", "dysphagia",
        ],
        "weighted_symptoms": {
            "proximal muscle weakness": 0.9, "elevated CK": 0.85,
            "heliotrope rash": 0.95, "Gottron papules": 0.95,
            "dysphagia": 0.7, "mechanic's hands": 0.8,
            "interstitial lung disease": 0.7, "anti-Jo-1": 0.9,
        },
        "contraindications": ["normal CK with no other explanation"],
        "confirmatory_tests": [
            "CK and aldolase",
            "Myositis-specific antibodies panel (anti-Jo-1, anti-MDA5, anti-Mi-2, etc.)",
            "MRI of thighs (edema pattern)",
            "EMG",
            "Muscle biopsy",
            "Pulmonary function tests + HRCT if ILD suspected",
        ],
        "specialist_type": "Rheumatology / Neurology",
        "urgency": "elective",
        "mimics": ["Statin myopathy", "Hypothyroid myopathy", "Inclusion body myositis"],
    },
    {
        "name": "Sjögren's Syndrome",
        "icd10": "M35.00",
        "system": "rheumatologic",
        "trigger_symptoms": [
            "dry eyes", "dry mouth", "parotid enlargement", "positive anti-Ro",
            "fatigue", "peripheral neuropathy",
        ],
        "weighted_symptoms": {
            "dry eyes": 0.8, "dry mouth": 0.8, "parotid enlargement": 0.8,
            "positive anti-Ro (SSA)": 0.9, "positive anti-La (SSB)": 0.85,
            "renal tubular acidosis": 0.8, "peripheral neuropathy": 0.7,
            "arthralgia": 0.5,
        },
        "contraindications": [],
        "confirmatory_tests": [
            "Anti-Ro (SSA) and anti-La (SSB) antibodies",
            "Schirmer test (tear production)",
            "Minor salivary gland biopsy",
            "Unstimulated salivary flow rate",
        ],
        "specialist_type": "Rheumatology",
        "urgency": "low",
        "mimics": ["SLE", "Medication-induced sicca", "Sarcoidosis"],
    },

    # ─────────────────────────────────────────────────────────────
    # METABOLIC / GENETIC
    # ─────────────────────────────────────────────────────────────
    {
        "name": "Wilson's Disease",
        "icd10": "E83.01",
        "system": "metabolic",
        "trigger_symptoms": [
            "Kayser-Fleischer rings", "liver disease in young patient",
            "neuropsychiatric symptoms", "hemolytic anemia",
            "movement disorder in young patient",
        ],
        "weighted_symptoms": {
            "Kayser-Fleischer rings": 1.0, "liver cirrhosis": 0.75,
            "elevated transaminases": 0.65, "neuropsychiatric symptoms": 0.8,
            "dysarthria": 0.75, "tremor": 0.65, "hemolytic anemia": 0.7,
            "Coombs-negative hemolysis": 0.8, "low ceruloplasmin": 0.9,
        },
        "contraindications": ["age > 60 without known history"],
        "confirmatory_tests": [
            "Ceruloplasmin (low in ~85%)",
            "24-hour urine copper",
            "Serum copper",
            "Slit-lamp exam (Kayser-Fleischer rings)",
            "Liver biopsy with copper quantification",
            "ATP7B gene sequencing",
        ],
        "specialist_type": "Hepatology / Neurology",
        "urgency": "urgent",
        "mimics": ["Autoimmune hepatitis", "Parkinson's disease", "Psychiatric disorders"],
    },
    {
        "name": "Gaucher Disease",
        "icd10": "E75.22",
        "system": "metabolic",
        "trigger_symptoms": [
            "splenomegaly", "hepatomegaly", "bone pain", "pancytopenia",
            "Gaucher cells on biopsy",
        ],
        "weighted_symptoms": {
            "splenomegaly": 0.85, "hepatomegaly": 0.75, "bone pain": 0.7,
            "bone crises": 0.8, "pancytopenia": 0.75, "anemia": 0.6,
            "elevated ferritin": 0.6, "low glucocerebrosidase": 0.95,
        },
        "contraindications": ["normal glucocerebrosidase activity"],
        "confirmatory_tests": [
            "Glucocerebrosidase (acid β-glucosidase) enzyme activity in WBC",
            "GBA gene sequencing",
            "Biomarkers: chitotriosidase, CCL18, glucosylsphingosine",
            "Bone marrow biopsy (Gaucher cells)",
            "Bone MRI for marrow infiltration",
        ],
        "specialist_type": "Hematology / Medical Genetics",
        "urgency": "elective",
        "mimics": ["Leukemia", "Lymphoma", "Niemann-Pick disease"],
    },
    {
        "name": "Fabry Disease",
        "icd10": "E75.21",
        "system": "metabolic",
        "trigger_symptoms": [
            "angiokeratomas", "acroparesthesias", "corneal verticillata",
            "stroke in young patient", "cardiac hypertrophy",
            "renal failure in young patient",
        ],
        "weighted_symptoms": {
            "angiokeratomas": 0.9, "acroparesthesias": 0.85,
            "corneal verticillata": 0.8, "stroke in young patient": 0.7,
            "LVH": 0.7, "proteinuria": 0.7, "low α-galactosidase A": 0.95,
        },
        "contraindications": ["normal α-galactosidase A in males"],
        "confirmatory_tests": [
            "α-galactosidase A enzyme activity (reduced in males)",
            "GLA gene sequencing (required for females)",
            "Plasma lyso-Gb3 (globotriaosylsphingosine) — elevated",
            "Cardiac MRI",
            "Renal biopsy if nephropathy present",
        ],
        "specialist_type": "Medical Genetics / Nephrology / Cardiology",
        "urgency": "elective",
        "mimics": ["Hypertrophic cardiomyopathy", "Cryptogenic stroke", "Small-fiber neuropathy"],
    },
    {
        "name": "Acute Intermittent Porphyria (AIP)",
        "icd10": "E80.21",
        "system": "metabolic",
        "trigger_symptoms": [
            "abdominal pain", "dark urine", "neuropsychiatric symptoms",
            "peripheral neuropathy", "hyponatremia", "tachycardia",
        ],
        "weighted_symptoms": {
            "severe abdominal pain": 0.85, "dark urine": 0.9,
            "peripheral neuropathy": 0.75, "neuropsychiatric symptoms": 0.7,
            "hyponatremia": 0.7, "tachycardia": 0.6,
            "elevated ALA/PBG in urine": 1.0,
        },
        "contraindications": ["normal urine ALA/PBG during attack"],
        "confirmatory_tests": [
            "Urine ALA (delta-aminolevulinic acid) and PBG (porphobilinogen) — spot urine during attack",
            "24-hour urine porphyrins",
            "HMBS gene sequencing",
            "Fecal porphyrins to exclude other porphyrias",
        ],
        "specialist_type": "Hematology / Metabolism",
        "urgency": "urgent",
        "mimics": ["Appendicitis", "Guillain-Barré syndrome", "Psychiatric disorders"],
    },
    {
        "name": "Hereditary Hemochromatosis",
        "icd10": "E83.110",
        "system": "metabolic",
        "trigger_symptoms": [
            "elevated ferritin", "elevated transferrin saturation",
            "liver disease", "diabetes", "arthropathy",
        ],
        "weighted_symptoms": {
            "elevated ferritin": 0.8, "elevated transferrin saturation > 45%": 0.9,
            "liver cirrhosis": 0.75, "diabetes mellitus": 0.6,
            "bronze skin": 0.8, "arthropathy (MCP joints)": 0.75,
            "hypogonadism": 0.7, "cardiomyopathy": 0.65,
        },
        "contraindications": ["ferritin elevation explained by inflammation or malignancy only"],
        "confirmatory_tests": [
            "Transferrin saturation (>45% suspicious, >60% highly suggestive in males)",
            "Ferritin",
            "HFE gene mutation (C282Y, H63D)",
            "Liver MRI for iron quantification (MRI-R2*)",
            "Liver biopsy (if cirrhosis suspected)",
        ],
        "specialist_type": "Hepatology / Hematology",
        "urgency": "elective",
        "mimics": ["Alcoholic liver disease", "Non-alcoholic steatohepatitis", "Transfusion-related iron overload"],
    },
    {
        "name": "MELAS Syndrome",
        "icd10": "G31.81",
        "system": "metabolic",
        "trigger_symptoms": [
            "stroke-like episodes in young patient", "elevated lactate",
            "sensorineural hearing loss", "seizures", "migraine",
        ],
        "weighted_symptoms": {
            "stroke-like episodes": 0.9, "elevated lactate": 0.85,
            "sensorineural hearing loss": 0.7, "seizures": 0.7,
            "migraine": 0.55, "short stature": 0.6, "maternal inheritance": 0.8,
            "m.3243A>G mutation": 1.0,
        },
        "contraindications": ["normal lactate during episodes"],
        "confirmatory_tests": [
            "Serum lactate and pyruvate",
            "CSF lactate",
            "MRI brain (cortical stroke-like lesions not following vascular territory)",
            "Mitochondrial DNA sequencing (blood, urine, muscle)",
            "Muscle biopsy (ragged red fibers, COX-negative fibers)",
            "Urine for heteroplasmy level",
        ],
        "specialist_type": "Neurology / Medical Genetics",
        "urgency": "urgent",
        "mimics": ["Ischemic stroke", "Epilepsy", "Encephalitis"],
    },

    # ─────────────────────────────────────────────────────────────
    # HEMATOLOGIC
    # ─────────────────────────────────────────────────────────────
    {
        "name": "Thrombotic Thrombocytopenic Purpura (TTP)",
        "icd10": "M31.1",
        "system": "hematologic",
        "trigger_symptoms": [
            "microangiopathic hemolytic anemia", "thrombocytopenia",
            "neurological symptoms", "fever", "renal impairment",
        ],
        "weighted_symptoms": {
            "thrombocytopenia": 0.9, "microangiopathic hemolytic anemia": 0.95,
            "schistocytes on smear": 0.95, "neurological symptoms": 0.8,
            "fever": 0.6, "renal impairment": 0.65,
            "low ADAMTS13 activity": 1.0, "elevated LDH": 0.8,
        },
        "contraindications": ["normal ADAMTS13 activity with confirmed diarrhea-associated HUS"],
        "confirmatory_tests": [
            "ADAMTS13 activity level (< 10% confirms acquired TTP)",
            "ADAMTS13 inhibitor (autoantibody)",
            "CBC + peripheral blood smear (schistocytes)",
            "LDH, indirect bilirubin, haptoglobin (hemolysis markers)",
            "Creatinine",
            "Direct Coombs test (neg in MAHA)",
        ],
        "specialist_type": "Hematology",
        "urgency": "urgent",
        "mimics": ["HUS", "HELLP syndrome", "DIC", "Severe sepsis"],
    },
    {
        "name": "Hemolytic Uremic Syndrome (HUS)",
        "icd10": "D59.30",
        "system": "hematologic",
        "trigger_symptoms": [
            "microangiopathic hemolytic anemia", "thrombocytopenia",
            "acute kidney injury", "bloody diarrhea",
        ],
        "weighted_symptoms": {
            "acute kidney injury": 0.9, "thrombocytopenia": 0.85,
            "microangiopathic hemolytic anemia": 0.9, "bloody diarrhea": 0.8,
            "Shiga toxin positive": 0.95, "pediatric age": 0.7,
        },
        "contraindications": ["normal creatinine"],
        "confirmatory_tests": [
            "Stool culture for E. coli O157:H7",
            "Shiga toxin PCR (stool)",
            "CBC + smear (schistocytes)",
            "Creatinine, BUN",
            "ADAMTS13 (if TTP vs HUS unclear)",
            "Complement levels (for atypical HUS)",
        ],
        "specialist_type": "Nephrology / Hematology",
        "urgency": "urgent",
        "mimics": ["TTP", "DIC", "Preeclampsia / HELLP"],
    },
    {
        "name": "Paroxysmal Nocturnal Hemoglobinuria (PNH)",
        "icd10": "D59.5",
        "system": "hematologic",
        "trigger_symptoms": [
            "hemoglobinuria", "hemolytic anemia", "thrombosis in unusual sites",
            "cytopenias", "abdominal pain",
        ],
        "weighted_symptoms": {
            "hemoglobinuria": 0.95, "hemolysis": 0.85,
            "thrombosis (portal, mesenteric, hepatic vein)": 0.9,
            "cytopenias": 0.75, "abdominal pain": 0.6,
            "aplastic anemia overlap": 0.7, "negative direct Coombs": 0.7,
        },
        "contraindications": ["normal GPI-anchor proteins on flow cytometry"],
        "confirmatory_tests": [
            "Flow cytometry for GPI-anchored proteins (CD55, CD59) on RBC and WBC",
            "Ham test (now largely replaced by flow)",
            "CBC with reticulocyte count",
            "LDH, haptoglobin, indirect bilirubin",
            "Urinalysis (hemoglobinuria)",
            "Bone marrow biopsy if aplastic anemia suspected",
        ],
        "specialist_type": "Hematology",
        "urgency": "urgent",
        "mimics": ["Aplastic anemia", "Autoimmune hemolytic anemia", "Myelodysplastic syndrome (MDS)"],
    },
    {
        "name": "Mastocytosis",
        "icd10": "D47.01",
        "system": "hematologic",
        "trigger_symptoms": [
            "urticaria pigmentosa", "flushing", "anaphylaxis",
            "elevated serum tryptase", "bone pain",
        ],
        "weighted_symptoms": {
            "urticaria pigmentosa (Darier sign)": 0.9, "flushing": 0.75,
            "anaphylaxis without trigger": 0.8, "elevated tryptase": 0.9,
            "bone pain": 0.7, "osteoporosis": 0.6,
            "KIT D816V mutation": 1.0, "hepatosplenomegaly": 0.7,
        },
        "contraindications": ["tryptase < 11.4 ng/mL without other explanation"],
        "confirmatory_tests": [
            "Serum tryptase (baseline)",
            "KIT D816V mutation (peripheral blood or bone marrow)",
            "Bone marrow biopsy (compact mast cell infiltrates)",
            "CD25/CD2 expression on mast cells",
            "24-hour urine histamine metabolites",
        ],
        "specialist_type": "Hematology / Allergy-Immunology",
        "urgency": "elective",
        "mimics": ["Carcinoid syndrome", "Pheochromocytoma", "Chronic urticaria"],
    },
    {
        "name": "Aplastic Anemia",
        "icd10": "D61.9",
        "system": "hematologic",
        "trigger_symptoms": [
            "pancytopenia", "hypocellular bone marrow", "fatigue",
            "bleeding", "infections",
        ],
        "weighted_symptoms": {
            "pancytopenia": 0.9, "hypocellular bone marrow": 0.95,
            "reticulocytopenia": 0.85, "fatigue": 0.5, "bleeding": 0.6,
            "recurrent infections": 0.65,
        },
        "contraindications": ["hypercellular marrow", "Shiga toxin positive"],
        "confirmatory_tests": [
            "CBC with differential + reticulocyte count",
            "Bone marrow biopsy (cellularity < 25%)",
            "Liver function tests (hepatitis workup)",
            "PNH clone by flow cytometry (in ~30–50%)",
            "Inherited bone marrow failure workup (telomere length, TERC/TERT mutations) if young patient",
            "HLA typing (pre-treatment if transplant considered)",
        ],
        "specialist_type": "Hematology",
        "urgency": "urgent",
        "mimics": ["Myelodysplastic syndrome", "PNH", "Hypoplastic myelodysplasia"],
    },

    # ─────────────────────────────────────────────────────────────
    # NEUROLOGIC
    # ─────────────────────────────────────────────────────────────
    {
        "name": "Autoimmune Encephalitis",
        "icd10": "G04.81",
        "system": "neurologic",
        "trigger_symptoms": [
            "subacute memory loss", "psychiatric symptoms", "seizures",
            "movement disorder", "autonomic instability",
        ],
        "weighted_symptoms": {
            "subacute memory loss": 0.85, "psychosis": 0.75, "seizures": 0.7,
            "orofacial dyskinesias": 0.9, "autonomic instability": 0.75,
            "CSF pleocytosis": 0.7, "anti-NMDA receptor antibody": 1.0,
            "MRI signal change in limbic structures": 0.85,
        },
        "contraindications": ["confirmed infectious meningitis with no autoimmune markers"],
        "confirmatory_tests": [
            "CSF analysis (cell count, protein, culture, HSV PCR)",
            "Autoimmune encephalitis antibody panel (serum + CSF): NMDA-R, LGI1, CASPR2, AMPA-R, GABA-B-R, anti-MOG",
            "MRI brain with contrast (FLAIR/DWI limbic signal)",
            "EEG (temporal slowing or seizure activity)",
            "Paraneoplastic panel if malignancy suspected",
            "CT chest/abdomen/pelvis (teratoma/thymoma)",
        ],
        "specialist_type": "Neurology",
        "urgency": "urgent",
        "mimics": ["Viral encephalitis (HSV)", "Creutzfeldt-Jakob disease", "Psychiatric disorder"],
    },
    {
        "name": "Neuromyelitis Optica Spectrum Disorder (NMOSD)",
        "icd10": "G36.0",
        "system": "neurologic",
        "trigger_symptoms": [
            "optic neuritis", "transverse myelitis", "intractable hiccups",
            "area postrema syndrome",
        ],
        "weighted_symptoms": {
            "bilateral optic neuritis": 0.9, "longitudinally extensive transverse myelitis": 0.95,
            "intractable hiccups": 0.85, "vomiting": 0.6,
            "anti-AQP4 antibody": 1.0, "anti-MOG antibody": 0.9,
            "spinal cord MRI ≥ 3 segments": 0.9,
        },
        "contraindications": ["MS pattern on MRI (Barkhof criteria without longitudinally extensive cord lesion)"],
        "confirmatory_tests": [
            "Anti-AQP4 (aquaporin-4) antibody (serum, cell-based assay)",
            "Anti-MOG antibody (serum)",
            "MRI brain + spine with gadolinium",
            "CSF analysis (cell count, oligoclonal bands)",
            "Visual evoked potentials",
        ],
        "specialist_type": "Neurology",
        "urgency": "urgent",
        "mimics": ["Multiple sclerosis", "Sagittal sinus thrombosis", "B12 deficiency myelopathy"],
    },
    {
        "name": "POEMS Syndrome",
        "icd10": "G63.3",
        "system": "neurologic",
        "trigger_symptoms": [
            "polyneuropathy", "organomegaly", "endocrinopathy",
            "M-protein", "skin changes",
        ],
        "weighted_symptoms": {
            "polyneuropathy": 0.9, "organomegaly": 0.75, "endocrinopathy": 0.7,
            "M-protein (lambda)": 0.85, "skin changes": 0.7,
            "elevated VEGF": 0.9, "sclerotic bone lesions": 0.85,
            "Castleman disease features": 0.8, "papilledema": 0.75,
        },
        "contraindications": [],
        "confirmatory_tests": [
            "Serum protein electrophoresis (SPEP) + immunofixation",
            "Serum VEGF level",
            "Bone survey or PET-CT for sclerotic lesions",
            "Bone marrow biopsy",
            "Nerve conduction studies + EMG",
            "Endocrine panel (testosterone, TSH, glucose)",
        ],
        "specialist_type": "Hematology / Neurology",
        "urgency": "elective",
        "mimics": ["CIDP", "Multiple myeloma with neuropathy", "Amyloidosis"],
    },
    {
        "name": "Neurosarcoidosis",
        "icd10": "G53.2",
        "system": "neurologic",
        "trigger_symptoms": [
            "cranial nerve palsy", "meningitis", "bilateral facial palsy",
            "elevated ACE", "hilar adenopathy",
        ],
        "weighted_symptoms": {
            "cranial nerve palsy": 0.85, "bilateral facial palsy": 0.9,
            "meningitis": 0.7, "elevated ACE": 0.75,
            "elevated lysozyme": 0.7, "hilar adenopathy": 0.7,
            "noncaseating granulomas": 0.95, "CSF pleocytosis": 0.65,
        },
        "contraindications": ["confirmed tuberculosis or fungal meningitis"],
        "confirmatory_tests": [
            "Serum ACE and lysozyme",
            "Chest CT (hilar/mediastinal adenopathy)",
            "CSF analysis including ACE",
            "MRI brain with gadolinium (leptomeningeal enhancement)",
            "18-FDG PET scan",
            "Tissue biopsy (accessible lymph node, skin, transbronchial)",
        ],
        "specialist_type": "Neurology / Pulmonology",
        "urgency": "elective",
        "mimics": ["Tuberculosis", "Lymphoma CNS involvement", "Multiple sclerosis"],
    },
    {
        "name": "Creutzfeldt-Jakob Disease (CJD)",
        "icd10": "A81.00",
        "system": "neurologic",
        "trigger_symptoms": [
            "rapidly progressive dementia", "myoclonus", "cerebellar ataxia",
            "visual disturbances", "akinetic mutism",
        ],
        "weighted_symptoms": {
            "rapidly progressive dementia": 0.95, "myoclonus": 0.85,
            "cerebellar ataxia": 0.75, "visual disturbances": 0.7,
            "periodic sharp waves on EEG": 0.9,
            "DWI cortical ribboning on MRI": 0.95,
            "elevated 14-3-3 protein in CSF": 0.85,
            "positive RT-QuIC in CSF": 1.0,
        },
        "contraindications": [],
        "confirmatory_tests": [
            "MRI brain DWI + FLAIR (cortical ribboning, basal ganglia signal)",
            "EEG (periodic sharp wave complexes — later stages)",
            "CSF: 14-3-3, tau, RT-QuIC (gold standard for sporadic CJD)",
            "PRNP gene sequencing",
        ],
        "specialist_type": "Neurology",
        "urgency": "urgent",
        "mimics": ["Autoimmune encephalitis", "Paraneoplastic encephalopathy", "Lewy body dementia"],
    },

    # ─────────────────────────────────────────────────────────────
    # ENDOCRINE
    # ─────────────────────────────────────────────────────────────
    {
        "name": "Pheochromocytoma / Paraganglioma",
        "icd10": "D35.00",
        "system": "endocrine",
        "trigger_symptoms": [
            "hypertensive crises", "palpitations", "diaphoresis",
            "headache", "pallor",
        ],
        "weighted_symptoms": {
            "hypertensive crises": 0.85, "palpitations": 0.75, "diaphoresis": 0.75,
            "headache": 0.7, "pallor": 0.65, "weight loss": 0.55,
            "elevated metanephrines": 1.0,
        },
        "contraindications": ["normal plasma metanephrines on twice repeated testing"],
        "confirmatory_tests": [
            "Plasma free metanephrines and catecholamines (highest sensitivity)",
            "24-hour urine catecholamines, metanephrines, VMA",
            "CT or MRI adrenal/abdomen/pelvis",
            "MIBG scintigraphy or 68Ga-DOTATATE PET (for localisation)",
            "Genetic testing (RET, VHL, SDHB/C/D, NF1, MAX)",
        ],
        "specialist_type": "Endocrinology / Surgery",
        "urgency": "urgent",
        "mimics": ["Panic disorder", "Hyperthyroidism", "Carcinoid syndrome"],
    },
    {
        "name": "Carcinoid Syndrome",
        "icd10": "E34.0",
        "system": "endocrine",
        "trigger_symptoms": [
            "flushing", "diarrhea", "wheezing", "right heart failure",
            "elevated 5-HIAA",
        ],
        "weighted_symptoms": {
            "flushing": 0.85, "diarrhea": 0.8, "wheezing": 0.65,
            "right-sided heart disease": 0.8, "pellagra-like skin": 0.7,
            "elevated 5-HIAA": 0.95, "elevated chromogranin A": 0.85,
        },
        "contraindications": [],
        "confirmatory_tests": [
            "24-hour urine 5-HIAA",
            "Serum chromogranin A",
            "CT chest/abdomen/pelvis",
            "68Ga-DOTATATE PET-CT (somatostatin receptor scintigraphy)",
            "Echocardiogram (carcinoid heart disease)",
        ],
        "specialist_type": "Oncology / Endocrinology",
        "urgency": "elective",
        "mimics": ["Mastocytosis", "Pheochromocytoma", "VIPoma"],
    },
    {
        "name": "Primary Adrenal Insufficiency (Addison's Disease)",
        "icd10": "E27.1",
        "system": "endocrine",
        "trigger_symptoms": [
            "hyperpigmentation", "hypotension", "hyponatremia",
            "hyperkalemia", "fatigue", "salt craving",
        ],
        "weighted_symptoms": {
            "hyperpigmentation": 0.9, "postural hypotension": 0.8,
            "hyponatremia": 0.8, "hyperkalemia": 0.75, "fatigue": 0.6,
            "salt craving": 0.75, "nausea": 0.5, "adrenal calcifications": 0.7,
            "low morning cortisol": 0.9, "low ACTH stimulation test": 1.0,
        },
        "contraindications": ["normal ACTH stimulation test"],
        "confirmatory_tests": [
            "Morning cortisol (< 3 μg/dL diagnostic, > 18 μg/dL excludes)",
            "ACTH stimulation test (250 μg Synacthen)",
            "Plasma ACTH (elevated in primary; low in secondary)",
            "Renin and aldosterone",
            "21-hydroxylase antibodies (autoimmune etiology)",
            "CT adrenal (bilateral hemorrhage, granuloma, metastasis)",
        ],
        "specialist_type": "Endocrinology",
        "urgency": "urgent",
        "mimics": ["Sepsis", "Hyponatremia of other cause", "Hemochromatosis"],
    },
    {
        "name": "Multiple Endocrine Neoplasia Type 1 (MEN1)",
        "icd10": "D44.8",
        "system": "endocrine",
        "trigger_symptoms": [
            "primary hyperparathyroidism", "pituitary adenoma",
            "pancreatic neuroendocrine tumor", "family history",
        ],
        "weighted_symptoms": {
            "hyperparathyroidism": 0.9, "pituitary adenoma": 0.85,
            "pancreatic NET": 0.85, "family history of MEN1": 0.9,
            "recurrent peptic ulcers (Zollinger-Ellison)": 0.8,
        },
        "contraindications": [],
        "confirmatory_tests": [
            "Calcium, PTH (hyperparathyroidism)",
            "Fasting gastrin (Zollinger-Ellison)",
            "Serum chromogranin A",
            "MRI pituitary",
            "68Ga-DOTATATE PET-CT",
            "MEN1 gene sequencing",
        ],
        "specialist_type": "Endocrinology / Medical Genetics",
        "urgency": "elective",
        "mimics": ["Sporadic hyperparathyroidism", "Sporadic pancreatic NET"],
    },

    # ─────────────────────────────────────────────────────────────
    # VASCULAR / CARDIAC
    # ─────────────────────────────────────────────────────────────
    {
        "name": "Takayasu Arteritis",
        "icd10": "M31.4",
        "system": "vascular",
        "trigger_symptoms": [
            "limb claudication in young woman", "absent pulses",
            "blood pressure discrepancy between arms",
            "arterial bruit", "elevated ESR/CRP",
        ],
        "weighted_symptoms": {
            "limb claudication": 0.8, "absent or diminished pulses": 0.9,
            "BP discrepancy (>10 mmHg)": 0.85, "arterial bruit": 0.8,
            "elevated ESR/CRP": 0.65, "fever": 0.5,
            "young female": 0.7, "Asian descent": 0.65,
        },
        "contraindications": ["age > 50 at onset (consider GCA instead)"],
        "confirmatory_tests": [
            "CT angiography or MR angiography (aorta and branches)",
            "PET-CT (active vasculitis)",
            "ESR, CRP",
            "Conventional angiography (gold standard but invasive)",
        ],
        "specialist_type": "Rheumatology / Vascular Surgery",
        "urgency": "urgent",
        "mimics": ["Giant cell arteritis", "Fibromuscular dysplasia", "Atherosclerosis"],
    },
    {
        "name": "Cardiac Sarcoidosis",
        "icd10": "D86.85",
        "system": "vascular",
        "trigger_symptoms": [
            "complete heart block in young patient", "ventricular arrhythmia",
            "heart failure", "elevated ACE",
        ],
        "weighted_symptoms": {
            "complete heart block": 0.9, "ventricular arrhythmia": 0.8,
            "heart failure": 0.65, "elevated ACE": 0.65,
            "bilateral hilar adenopathy": 0.75, "noncaseating granulomas": 0.95,
            "positive cardiac 18-FDG PET": 0.9,
        },
        "contraindications": ["confirmed coronary artery disease explaining arrhythmia"],
        "confirmatory_tests": [
            "Cardiac MRI (gadolinium late enhancement)",
            "18-FDG PET-CT cardiac protocol",
            "ECG and Holter monitoring",
            "Echocardiography",
            "Serum ACE and lysozyme",
            "Endomyocardial biopsy (low yield; extracardiac biopsy if accessible site present)",
        ],
        "specialist_type": "Cardiology / Pulmonology",
        "urgency": "urgent",
        "mimics": ["Idiopathic dilated cardiomyopathy", "Arrhythmogenic right ventricular cardiomyopathy (ARVC)"],
    },
    {
        "name": "Buerger's Disease (Thromboangiitis Obliterans)",
        "icd10": "I73.1",
        "system": "vascular",
        "trigger_symptoms": [
            "rest pain in young smoker", "digital ischemia",
            "superficial thrombophlebitis", "absent distal pulses",
        ],
        "weighted_symptoms": {
            "rest pain": 0.8, "digital ischemia": 0.85,
            "superficial thrombophlebitis": 0.8, "absent distal pulses (normal proximal)": 0.9,
            "age < 45": 0.75, "heavy smoking": 0.85,
        },
        "contraindications": ["non-smoker (rarely diagnosed)", "age > 60"],
        "confirmatory_tests": [
            "ABI (ankle-brachial index)",
            "Arteriography (corkscrew collaterals)",
            "Complete vascular exam",
            "Hypercoagulable workup (to exclude)",
            "Echocardiography (to exclude cardiac emboli)",
        ],
        "specialist_type": "Vascular Surgery",
        "urgency": "urgent",
        "mimics": ["Atherosclerosis", "APS", "CREST syndrome"],
    },

    # ─────────────────────────────────────────────────────────────
    # HEPATIC / GI
    # ─────────────────────────────────────────────────────────────
    {
        "name": "Primary Sclerosing Cholangitis (PSC)",
        "icd10": "K83.01",
        "system": "hepatic",
        "trigger_symptoms": [
            "cholestatic liver disease", "inflammatory bowel disease",
            "stricturing of bile ducts", "elevated ALP",
        ],
        "weighted_symptoms": {
            "elevated ALP": 0.85, "cholestatic jaundice": 0.8,
            "inflammatory bowel disease (UC > CD)": 0.8,
            "MRCP beaded bile ducts": 0.95, "elevated bilirubin": 0.7,
            "fatigue": 0.4,
        },
        "contraindications": ["IgG4 level normal (excludes IgG4-SC)", "normal MRCP"],
        "confirmatory_tests": [
            "MRCP (beaded appearance of intra/extrahepatic bile ducts)",
            "ALP, GGT, bilirubin, ALT",
            "IgG4 level (to exclude IgG4-related sclerosing cholangitis)",
            "p-ANCA (positive in ~80% of PSC)",
            "Liver biopsy (onion-skin fibrosis; guides staging)",
            "Colonoscopy (associated IBD in ~70%)",
        ],
        "specialist_type": "Hepatology / Gastroenterology",
        "urgency": "elective",
        "mimics": ["IgG4-related sclerosing cholangitis", "Cholangiocarcinoma", "Secondary sclerosing cholangitis"],
    },
    {
        "name": "Autoimmune Hepatitis (AIH)",
        "icd10": "K75.4",
        "system": "hepatic",
        "trigger_symptoms": [
            "elevated transaminases", "hypergammaglobulinemia",
            "positive ANA or ASMA", "young woman",
        ],
        "weighted_symptoms": {
            "elevated transaminases": 0.75, "hypergammaglobulinemia": 0.8,
            "positive ANA": 0.75, "positive anti-smooth muscle (ASMA)": 0.85,
            "positive anti-LKM1": 0.9, "elevated IgG": 0.8,
            "interface hepatitis on biopsy": 0.95,
        },
        "contraindications": ["viral hepatitis confirmed as sole etiology"],
        "confirmatory_tests": [
            "ANA, ASMA, anti-LKM1, anti-SLA (simplified AIH score)",
            "Serum protein electrophoresis (SPEP) — elevated IgG",
            "Liver biopsy (interface hepatitis, rosette formation)",
            "Viral hepatitis panel (exclude HBV, HCV)",
            "Drug history (drug-induced hepatitis exclusion)",
        ],
        "specialist_type": "Hepatology",
        "urgency": "urgent",
        "mimics": ["DILI", "Wilson's disease (if young)", "NASH with ANA positivity"],
    },
    {
        "name": "Eosinophilic Esophagitis / Gastroenteritis",
        "icd10": "K20.0",
        "system": "hepatic",
        "trigger_symptoms": [
            "dysphagia", "food impaction", "eosinophilia",
            "abdominal pain", "allergic history",
        ],
        "weighted_symptoms": {
            "dysphagia": 0.8, "food bolus impaction": 0.85, "eosinophilia": 0.75,
            "atopic history": 0.65, "chest pain": 0.55,
            "≥15 eos/hpf on esophageal biopsy": 0.95,
        },
        "contraindications": ["responds to PPI alone (suggests GERD rather than EoE; reassess)"],
        "confirmatory_tests": [
            "Upper endoscopy with esophageal biopsies (≥15 eos/hpf at ≥2 levels)",
            "PPI trial (6–8 weeks) — if symptoms persist after PPI, EoE confirmed",
            "Allergy evaluation",
        ],
        "specialist_type": "Gastroenterology / Allergy",
        "urgency": "elective",
        "mimics": ["GERD", "Achalasia", "Eosinophilic granulomatosis with polyangiitis (GI manifestation)"],
    },
    {
        "name": "IgG4-Related Disease (IgG4-RD)",
        "icd10": "M35.08",
        "system": "hepatic",
        "trigger_symptoms": [
            "pancreatic mass", "salivary gland enlargement",
            "orbital involvement", "elevated IgG4",
            "sclerosing cholangitis",
        ],
        "weighted_symptoms": {
            "elevated serum IgG4": 0.85, "pancreatic mass/enlargement": 0.8,
            "salivary gland enlargement": 0.8, "orbital pseudotumor": 0.75,
            "sclerosing cholangitis": 0.75, "retroperitoneal fibrosis": 0.8,
            "storiform fibrosis on biopsy": 0.95, "obliterative phlebitis": 0.9,
        },
        "contraindications": ["malignancy confirmed as sole etiology"],
        "confirmatory_tests": [
            "Serum IgG4 (elevated in ~60–70%)",
            "CT/MRI of affected organ",
            "Tissue biopsy (IgG4+ plasma cells > 10/HPF, storiform fibrosis, obliterative phlebitis)",
            "PET-CT for systemic involvement",
        ],
        "specialist_type": "Rheumatology / Gastroenterology",
        "urgency": "elective",
        "mimics": ["Pancreatic adenocarcinoma", "Lymphoma", "PSC"],
    },

    # ─────────────────────────────────────────────────────────────
    # PULMONARY
    # ─────────────────────────────────────────────────────────────
    {
        "name": "Pulmonary Alveolar Proteinosis (PAP)",
        "icd10": "J84.01",
        "system": "pulmonary",
        "trigger_symptoms": [
            "progressive dyspnea", "ground-glass opacities",
            "crazy-paving pattern on CT", "normal spirometry early",
        ],
        "weighted_symptoms": {
            "progressive dyspnea": 0.75, "ground-glass opacities": 0.85,
            "crazy-paving pattern on HRCT": 0.95, "elevated LDH": 0.7,
            "PAS-positive material in BAL": 0.95,
            "anti-GM-CSF antibodies": 0.9,
        },
        "contraindications": [],
        "confirmatory_tests": [
            "HRCT chest (crazy-paving pattern)",
            "Bronchoalveolar lavage (milky fluid + PAS-positive material)",
            "Anti-GM-CSF antibodies (autoimmune PAP)",
            "Lung biopsy if diagnosis unclear",
        ],
        "specialist_type": "Pulmonology",
        "urgency": "elective",
        "mimics": ["Atypical pneumonia", "Alveolar hemorrhage", "Lipoid pneumonia"],
    },
    {
        "name": "Lymphangioleiomyomatosis (LAM)",
        "icd10": "J84.81",
        "system": "pulmonary",
        "trigger_symptoms": [
            "spontaneous pneumothorax in young woman",
            "progressive dyspnea", "chylothorax",
            "angiomyolipoma",
        ],
        "weighted_symptoms": {
            "spontaneous pneumothorax in premenopausal woman": 0.9,
            "progressive dyspnea": 0.7, "chylothorax": 0.9,
            "angiomyolipoma of kidney": 0.85,
            "cystic lung disease on HRCT": 0.9,
            "elevated VEGF-D": 0.85, "TSC mutations": 0.9,
        },
        "contraindications": ["post-menopausal onset without TSC history"],
        "confirmatory_tests": [
            "HRCT chest (thin-walled cysts diffusely)",
            "Serum VEGF-D (>800 pg/mL + compatible CT = diagnostic)",
            "Pulmonary function tests (obstructive pattern)",
            "Lung biopsy if VEGF-D non-diagnostic",
            "TSC1/TSC2 mutation analysis",
            "Abdominal/pelvic MRI (angiomyolipoma)",
        ],
        "specialist_type": "Pulmonology / Medical Genetics",
        "urgency": "elective",
        "mimics": ["COPD emphysema", "Histiocytosis X (PLCH)", "BHD syndrome"],
    },
]

# Build lookup indices
_NAME_INDEX: dict[str, dict] = {entry["name"]: entry for entry in _ONTOLOGY}

_SYSTEM_INDEX: dict[str, list[str]] = {}
for _entry in _ONTOLOGY:
    sys_ = _entry["system"]
    _SYSTEM_INDEX.setdefault(sys_, []).append(_entry["name"])


def get_seed_hypotheses(symptoms: list[str]) -> list[str]:
    """Return disease names that match ≥2 trigger symptoms from the input list.

    Uses case-insensitive substring matching so "elevated ferritin" matches
    "elevated ferritin" trigger and vice-versa.
    """
    lowered = [s.lower() for s in symptoms]
    matches: list[tuple[int, str]] = []
    for entry in _ONTOLOGY:
        score = 0
        for trigger in entry["trigger_symptoms"]:
            t = trigger.lower()
            if any(t in s or s in t for s in lowered):
                score += 1
        if score >= 2:
            matches.append((score, entry["name"]))
    # Sort by match count descending, return names
    matches.sort(key=lambda x: x[0], reverse=True)
    return [name for _, name in matches]


def get_adjacent_diseases(disease_name: str) -> list[str]:
    """Return diseases in the same organ system, plus known mimics."""
    entry = _NAME_INDEX.get(disease_name)
    if entry is None:
        return []
    system = entry["system"]
    adjacent = [n for n in _SYSTEM_INDEX.get(system, []) if n != disease_name]
    mimics = entry.get("mimics", [])
    # Include mimics that are in our ontology
    known_mimics = [m for m in mimics if m in _NAME_INDEX and m != disease_name]
    seen: set[str] = set()
    result: list[str] = []
    for name in known_mimics + adjacent:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def get_disease_details(name: str) -> dict | None:
    """Return full ontology entry for a disease by name, or None."""
    return _NAME_INDEX.get(name)


def list_all_diseases() -> list[str]:
    """Return all disease names in the ontology."""
    return list(_NAME_INDEX.keys())
