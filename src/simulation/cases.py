"""
Clinical simulation case library.

Each case contains:
  - Presentation shown to the resident at the start
  - History data the AI patient reveals when asked
  - Physical exam findings by system
  - Investigation results unlocked on order
  - Ground truth for scoring (diagnosis + management)
  - Learning objectives and key teaching points
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ClinicalCase:
    case_id: str
    title: str
    specialty: str          # "Emergency Medicine" | "Internal Medicine" | "Surgery"
    difficulty: str         # "beginner" | "intermediate" | "advanced"
    learning_objectives: list[str]

    # Shown immediately
    presentation: str       # chief complaint + age/sex + initial vitals
    initial_vitals: dict    # displayed as a vitals card

    # Revealed on interaction
    history_data: dict      # keyword → patient response (MedGemma uses this as context)
    physical_exam: dict     # system → findings string
    investigations: dict    # test name → result string

    # Ground truth
    correct_diagnosis: str
    acceptable_diagnoses: list[str]   # partial credit
    correct_management: list[str]
    key_learning_points: list[str]

    # Scoring weights
    score_weights: dict = field(default_factory=lambda: {
        "history": 20,
        "exam": 20,
        "investigations": 20,
        "diagnosis": 25,
        "management": 15,
    })


# ── Case definitions ───────────────────────────────────────────────────────────

CASES: dict[str, ClinicalCase] = {}


def _register(case: ClinicalCase) -> ClinicalCase:
    CASES[case.case_id] = case
    return case


# ── Case 1: STEMI ──────────────────────────────────────────────────────────────
_register(ClinicalCase(
    case_id="SIM-001",
    title="Crushing Chest Pain in a 58-Year-Old Male",
    specialty="Emergency Medicine",
    difficulty="intermediate",
    learning_objectives=[
        "Recognise STEMI on a 12-lead ECG",
        "Initiate time-critical reperfusion within 90 minutes (door-to-balloon)",
        "Appropriate use of dual antiplatelet therapy and anticoagulation",
        "Identify and manage cardiogenic shock",
    ],
    presentation=(
        "A 58-year-old male is brought in by ambulance with a 45-minute history of "
        "severe crushing central chest pain radiating to his left arm and jaw. "
        "He is pale, diaphoretic, and looks unwell. A 12-lead ECG was performed in the ambulance."
    ),
    initial_vitals={
        "HR": "102 bpm",
        "BP": "88/60 mmHg",
        "RR": "22 /min",
        "SpO2": "94% on room air",
        "Temp": "36.8°C",
        "GCS": "15",
    },
    history_data={
        "pain": "The pain started about 45 minutes ago. It's a crushing, heavy pain, 9/10. It goes to my left arm and jaw.",
        "onset": "I was watching TV when it started suddenly.",
        "radiation": "Yes, to my left arm and jaw.",
        "associated": "I feel sick to my stomach and I'm sweating a lot.",
        "cardiac history": "I had a stent put in 3 years ago for a blocked artery.",
        "medications": "I take aspirin 75mg, atorvastatin, bisoprolol, and ramipril.",
        "allergies": "No known allergies.",
        "smoking": "I smoked for 30 years, quit 5 years ago.",
        "diabetes": "Yes, I have type 2 diabetes, controlled with metformin.",
        "family history": "My father died of a heart attack at 60.",
        "alcohol": "Occasional social drinker.",
        "vomiting": "I feel very nauseous. I vomited once on the way here.",
        "breathlessness": "A little short of breath, yes.",
        "previous episodes": "Nothing like this before, though I've had some mild chest tightness on exertion recently.",
    },
    physical_exam={
        "General": "Pale, diaphoretic, in obvious distress. Alert and oriented.",
        "Cardiovascular": "Heart sounds S1 S2 present, no murmurs. JVP elevated at 4 cm. Peripheral pulses weak bilaterally. Capillary refill >3 seconds.",
        "Respiratory": "Bilateral fine basal crackles. Reduced air entry at both bases.",
        "Abdomen": "Soft, non-tender, no organomegaly.",
        "Neurological": "GCS 15, moving all four limbs.",
        "Extremities": "Cool peripheries, no pitting oedema.",
    },
    investigations={
        "12-lead ECG": (
            "Sinus tachycardia at 102 bpm. ST elevation >2mm in leads II, III, aVF "
            "with reciprocal ST depression in I, aVL. ST elevation also in V4R (right-sided ECG). "
            "Consistent with inferior STEMI with right ventricular involvement."
        ),
        "Troponin I": "Troponin I: 4.2 ng/mL (reference <0.04). Markedly elevated.",
        "FBC": "Hb 13.8, WBC 14.2 (neutrophilia), Platelets 220.",
        "U&E": "Na 137, K 3.4, Urea 8.2, Creatinine 110. eGFR 62.",
        "LFTs": "Within normal limits.",
        "Glucose": "Random glucose 14.8 mmol/L.",
        "Clotting": "PT 12.1s, APTT 28s. Normal.",
        "CXR": "Cardiomegaly. Bilateral perihilar haziness consistent with pulmonary oedema.",
        "Echo (bedside)": "Inferior wall hypokinesia. EF estimated at 35-40%. RV dilation.",
        "ABG": "pH 7.31, pO2 8.1, pCO2 4.8, HCO3 18. Lactate 3.2. Mild metabolic acidosis.",
    },
    correct_diagnosis="Inferior STEMI with right ventricular involvement and cardiogenic shock",
    acceptable_diagnoses=["Inferior STEMI", "STEMI", "Acute MI", "Inferior MI"],
    correct_management=[
        "Activate cath lab immediately — door-to-balloon <90 minutes",
        "Dual antiplatelet: Aspirin 300mg + Ticagrelor 180mg (avoid clopidogrel with planned PCI)",
        "IV access x2, cardiac monitoring, defibrillator ready",
        "Anticoagulation: Unfractionated heparin IV bolus",
        "Avoid nitrates (RV infarct — preload dependent; nitrates cause profound hypotension)",
        "IV fluid challenge (250 mL 0.9% NaCl) carefully for RV support",
        "Supplemental oxygen to maintain SpO2 >94%",
        "Morphine 2-4mg IV for pain (caution: may worsen nausea)",
        "Metoclopramide 10mg IV for nausea",
        "Senior / cardiologist involvement immediately",
    ],
    key_learning_points=[
        "Inferior STEMI can involve the right ventricle — always do right-sided ECG leads",
        "RV infarction is preload-dependent: nitrates and diuretics are CONTRAINDICATED",
        "Cardiogenic shock complicates ~5-10% of STEMIs and requires immediate revascularisation",
        "Hypokalaemia in the context of MI increases arrhythmia risk — correct potassium",
        "Door-to-balloon time <90 minutes is the key quality metric",
    ],
))


# ── Case 2: DKA ───────────────────────────────────────────────────────────────
_register(ClinicalCase(
    case_id="SIM-002",
    title="Nausea, Vomiting and Confusion in a 24-Year-Old Female",
    specialty="Internal Medicine",
    difficulty="beginner",
    learning_objectives=[
        "Diagnose diabetic ketoacidosis using clinical and biochemical criteria",
        "Initiate fluid resuscitation and insulin therapy correctly",
        "Monitor and replace electrolytes, especially potassium",
        "Identify precipitating cause of DKA",
    ],
    presentation=(
        "A 24-year-old female with known type 1 diabetes mellitus is brought in by her "
        "flatmate. She has been vomiting for 2 days and is increasingly confused. "
        "Her flatmate says she has not eaten or taken her insulin properly in 3 days."
    ),
    initial_vitals={
        "HR": "118 bpm",
        "BP": "96/64 mmHg",
        "RR": "28 /min",
        "SpO2": "98% on room air",
        "Temp": "37.2°C",
        "GCS": "13 (E3V4M6)",
        "BGL": "32.4 mmol/L",
    },
    history_data={
        "diabetes": "I've had type 1 diabetes since I was 12. I use an insulin pump but I've had it disconnected for 2 days.",
        "insulin": "I haven't been taking my insulin properly. I felt sick and didn't eat so I thought I didn't need it.",
        "symptoms": "I've been vomiting every hour. I have stomach cramps. I've been really thirsty and peeing a lot.",
        "onset": "It started about 2 days ago when I started feeling unwell.",
        "infection": "I had a UTI last week. I was prescribed trimethoprim but I'm not sure I finished the course.",
        "confusion": "I feel really foggy. I can answer questions but I feel like I'm not all here.",
        "medications": "Insulin pump with NovoRapid. I also take levothyroxine for my thyroid.",
        "allergies": "Penicillin — I get a rash.",
        "last insulin": "The pump has been disconnected for about 48 hours because it was hurting at the site.",
        "alcohol": "I don't drink.",
        "breathing": "Yes, I feel like I'm breathing harder than normal.",
        "smell": "My flatmate said my breath smells sweet, like nail polish remover.",
    },
    physical_exam={
        "General": "Unwell-looking, lethargic, dry mucous membranes, sunken eyes. Kussmaul breathing pattern.",
        "Cardiovascular": "Tachycardic. BP low. Capillary refill 3 seconds. Cool peripheries.",
        "Respiratory": "Deep, rapid respirations (Kussmaul breathing). Clear chest on auscultation.",
        "Abdomen": "Diffuse tenderness throughout. No guarding or rigidity. Bowel sounds present.",
        "Neurological": "GCS 13. Confused, slow to respond. No focal motor deficits.",
        "Skin": "Abdomen shows multiple old insulin pump insertion sites. Skin turgor reduced.",
    },
    investigations={
        "ABG (venous)": "pH 7.16, pCO2 2.8, HCO3 8. Lactate 1.8. Severe metabolic acidosis.",
        "Blood ketones": "Ketones: 5.8 mmol/L (severe ketoacidosis).",
        "U&E": "Na 131, K 5.8 (before insulin), Urea 12.4, Creatinine 98. Glucose 32.4.",
        "FBC": "WBC 18.4 (leucocytosis — can be stress response in DKA). Hb 12.9. Platelets 310.",
        "Urine dip": "Ketones 4+, Glucose 4+, Nitrites positive, Leucocytes 3+.",
        "MSU (midstream urine)": "Pending. Likely UTI as precipitant.",
        "HbA1c": "12.8% — poor glycaemic control overall.",
        "CXR": "No consolidation. No pneumothorax.",
        "ECG": "Sinus tachycardia. Tall peaked T-waves consistent with hyperkalaemia.",
        "Cultures": "Blood cultures x2 sent. Urine culture sent.",
        "CRP": "42 mg/L — mild elevation.",
    },
    correct_diagnosis="Diabetic Ketoacidosis (DKA) precipitated by urinary tract infection and insulin omission",
    acceptable_diagnoses=["DKA", "Diabetic ketoacidosis", "DKA with UTI"],
    correct_management=[
        "IV access x2 — start aggressive fluid resuscitation: 1L 0.9% NaCl over first hour",
        "Fixed-rate IV insulin infusion 0.1 units/kg/hr (DO NOT give IV bolus insulin)",
        "Monitor potassium: DO NOT start insulin if K+ <3.5 — replace potassium first",
        "Potassium replacement: add 40mmol KCl to next litre of fluid (K 5.8 → monitor as insulin will lower K rapidly)",
        "Hourly blood glucose monitoring; switch to 5% glucose when BGL <14",
        "Urinary catheter for hourly urine output monitoring",
        "Treat precipitant: Trimethoprim/nitrofurantoin for UTI (avoid trimethoprim given hyperkalaemia risk — use nitrofurantoin or cefalexin)",
        "VTE prophylaxis once haemodynamically stable",
        "Diabetes specialist/endocrinology review for pump management",
        "Repeat ABG at 2 hours to assess response",
    ],
    key_learning_points=[
        "DKA diagnosis: glucose >11 + ketones >3 + pH <7.3 or bicarb <15",
        "NEVER give IV bolus insulin in DKA — can cause fatal cerebral oedema",
        "Potassium is critical — hyperkalaemia at presentation will become hypokalaemia with treatment",
        "Abdominal pain in DKA is often due to DKA itself, not a surgical cause — reassess once treatment starts",
        "Always identify the precipitant: infection, omission, new-onset T1DM",
    ],
))


# ── Case 3: Pulmonary Embolism ─────────────────────────────────────────────────
_register(ClinicalCase(
    case_id="SIM-003",
    title="Sudden Breathlessness 5 Days Post-Knee Surgery",
    specialty="Emergency Medicine",
    difficulty="intermediate",
    learning_objectives=[
        "Apply the Wells score to stratify PE probability",
        "Select appropriate imaging (CT-PA vs V/Q scan)",
        "Initiate anticoagulation in confirmed PE",
        "Identify massive PE requiring thrombolysis",
    ],
    presentation=(
        "A 45-year-old female is brought in by ambulance with sudden onset breathlessness "
        "and right-sided sharp chest pain that worsens on inspiration. She had a right total "
        "knee replacement 5 days ago and was discharged home yesterday."
    ),
    initial_vitals={
        "HR": "114 bpm",
        "BP": "108/72 mmHg",
        "RR": "26 /min",
        "SpO2": "91% on room air",
        "Temp": "37.6°C",
        "GCS": "15",
    },
    history_data={
        "breathlessness": "It came on very suddenly about an hour ago. I was just sitting and it hit me.",
        "chest pain": "Yes, right side. It's sharp and gets worse when I breathe in deeply.",
        "surgery": "I had my right knee replaced 5 days ago. Went home yesterday — I was doing well.",
        "mobilisation": "I've been mostly in bed or on the sofa. It hurts to walk.",
        "DVT prophylaxis": "They gave me injections in hospital but I haven't had one today.",
        "leg symptoms": "Actually now that you mention it, my right calf has been a bit sore and swollen since yesterday.",
        "haemoptysis": "A small amount of blood in my sputum this morning. I thought it was just from coughing.",
        "medications": "Oxycodone for pain, enoxaparin injections (once daily), metoprolol for my heart.",
        "cardiac history": "I have a slow heart rate normally — I take metoprolol. No heart failure.",
        "previous clots": "No, never had a clot before.",
        "family history": "My sister had a DVT in pregnancy.",
        "contraceptives": "I'm on the combined contraceptive pill.",
        "allergies": "No known drug allergies.",
        "cancer": "No history of cancer.",
    },
    physical_exam={
        "General": "Anxious, tachypnoeic, using accessory muscles. Mildly cyanosed peripherally.",
        "Cardiovascular": "Tachycardic. Loud P2. No S3. JVP elevated at 5 cm above sternal angle.",
        "Respiratory": "Reduced air entry right lower zone. Pleural rub right base. No wheeze.",
        "Abdomen": "Unremarkable.",
        "Right leg": "Right calf swollen, warm, tender. Calf circumference 3 cm greater than left. Homan's sign positive.",
        "Left leg": "Normal.",
        "Skin": "No rashes. Mucous membranes mildly cyanosed.",
    },
    investigations={
        "ECG": "Sinus tachycardia 114 bpm. S1Q3T3 pattern. Right bundle branch block. T-wave inversion V1-V4.",
        "CXR": "Hampton's hump — wedge-shaped opacity right lower zone. Oligaemia right lower zone (Westermark sign).",
        "ABG": "pH 7.47, pO2 7.2, pCO2 3.4, HCO3 22. Hypoxia with hyperventilation.",
        "D-dimer": "8,400 ng/mL (highly elevated — reference <500).",
        "CT Pulmonary Angiogram": "Large saddle embolus at the bifurcation of the main pulmonary artery. Bilateral pulmonary emboli. Right heart strain.",
        "Echo (bedside)": "Right ventricular dilation. RV:LV ratio >1. McConnell's sign present — RV free wall akinesia with preserved apex.",
        "FBC": "Hb 11.8, WBC 10.2, Platelets 218.",
        "U&E": "Normal.",
        "Troponin I": "0.34 ng/mL (mildly elevated — right heart strain marker).",
        "BNP": "680 pg/mL (elevated — right ventricular dysfunction).",
        "Lower limb doppler": "Right popliteal DVT confirmed.",
    },
    correct_diagnosis="Massive/submassive pulmonary embolism with right heart strain secondary to DVT",
    acceptable_diagnoses=["Pulmonary embolism", "PE", "Massive PE", "Submassive PE"],
    correct_management=[
        "High-flow oxygen — target SpO2 >94%",
        "IV access x2, urgent bloods",
        "Wells score: ≥6 — high probability PE → proceed directly to CT-PA",
        "Anticoagulation: LMWH (enoxaparin 1.5mg/kg SC) or IV unfractionated heparin for massive PE",
        "For massive PE with haemodynamic instability: consider systemic thrombolysis (alteplase 100mg over 2h)",
        "Senior/ICU involvement for haemodynamically unstable patient",
        "Continuous cardiac monitoring, defibrillator ready",
        "PE response team activation if available",
        "Stop COCP (contributing risk factor)",
        "Long-term anticoagulation: DOAC (rivaroxaban or apixaban) for minimum 3 months",
    ],
    key_learning_points=[
        "Wells criteria: Clinical DVT signs (3), alternative less likely (3), heart rate >100 (1.5), immobilisation >3d (1.5), prior DVT/PE (1.5), haemoptysis (1), malignancy (1)",
        "S1Q3T3 is classic but insensitive — sinus tachycardia is the most common ECG finding",
        "Combined OCP + post-surgical immobility = very high thrombotic risk",
        "Massive PE: haemodynamic instability → thrombolysis if no contraindications",
        "D-dimer is only useful to RULE OUT PE in low-probability patients",
    ],
))


# ── Case 4: Stroke ─────────────────────────────────────────────────────────────
_register(ClinicalCase(
    case_id="SIM-004",
    title="Sudden Slurred Speech and Left-Sided Weakness",
    specialty="Neurology",
    difficulty="intermediate",
    learning_objectives=[
        "Rapidly assess and diagnose ischaemic stroke using FAST/NIHSS",
        "Determine eligibility for IV thrombolysis (alteplase) within 4.5-hour window",
        "Identify contraindications to thrombolysis",
        "Initiate secondary prevention",
    ],
    presentation=(
        "A 68-year-old male is brought in by his wife at 10:45. She reports he suddenly "
        "developed slurred speech and left arm weakness while having breakfast at 10:00. "
        "She says 'he just wasn't making sense and his face looked droopy on one side.'"
    ),
    initial_vitals={
        "HR": "88 bpm (irregularly irregular)",
        "BP": "178/96 mmHg",
        "RR": "16 /min",
        "SpO2": "97% on room air",
        "Temp": "36.9°C",
        "BGL": "7.2 mmol/L",
        "Time since onset": "45 minutes (last seen well 10:00)",
    },
    history_data={
        "symptoms": "I can hear you but it's hard to get my words out. My left arm feels heavy and weak.",
        "onset": "My wife says it was at exactly 10am. She was watching me eat and noticed my face dropped.",
        "previous strokes": "I had a 'mini-stroke' about 2 years ago. I recovered fully within a day.",
        "medications": "I take ramipril, amlodipine, and atorvastatin. I was told to take aspirin but I stopped it 3 months ago because of stomach upset.",
        "anticoagulants": "No, I'm not on any blood thinners.",
        "atrial fibrillation": "They told me I had an irregular heartbeat at my last check-up but I wasn't put on any tablets for it. My GP said we'd 'watch and wait'.",
        "diabetes": "No diabetes.",
        "headache": "No headache at all.",
        "vomiting": "No vomiting.",
        "trauma": "No head injury.",
        "surgery": "I had a hip replacement 4 months ago.",
        "bleeding history": "No history of bleeding problems.",
        "allergies": "No known allergies.",
        "smoking": "Ex-smoker, quit 10 years ago. Smoked 20/day for 30 years.",
        "alcohol": "Two glasses of wine per night.",
    },
    physical_exam={
        "General": "Alert, anxious. Dysarthric speech (slurred). Follows commands.",
        "Cardiovascular": "Irregularly irregular pulse — consistent with AF. Normal heart sounds. BP 178/96.",
        "Facial exam": "Right facial droop. Left nasolabial fold preserved.",
        "Upper limbs": "Left arm pronator drift. Grip strength 2/5 left, 5/5 right.",
        "Lower limbs": "Left leg mild weakness 4/5. Right leg normal.",
        "Sensation": "Reduced light touch left arm and face.",
        "Speech": "Dysarthria — words are slurred but language comprehension intact.",
        "Vision": "No visual field defect on confrontation.",
        "NIHSS score": "NIHSS 8 — moderate stroke (facial palsy 1, left arm 2, left leg 1, sensory 1, dysarthria 1, best language 0).",
    },
    investigations={
        "CT head (non-contrast)": "No haemorrhage. No established infarction. No space-occupying lesion. No midline shift.",
        "ECG": "Atrial fibrillation. Rate ~88 bpm. No ST changes.",
        "FBC": "Hb 14.2, WBC 8.4, Platelets 224.",
        "Clotting": "INR 1.1 (not anticoagulated). APTT normal.",
        "U&E": "Na 139, K 4.1, Creatinine 92.",
        "Glucose": "7.2 mmol/L (normal).",
        "CXR": "Mild cardiomegaly. No consolidation.",
        "MRI brain (if ordered)": "Diffusion-weighted imaging: Restricted diffusion in right MCA territory — consistent with acute ischaemic stroke.",
        "Carotid Doppler": "Right carotid 30% stenosis. Left normal.",
        "Echo": "Dilated left atrium. Mild LVH. No thrombus visualised.",
    },
    correct_diagnosis="Acute ischaemic stroke (right MCA territory) secondary to cardioembolic mechanism (atrial fibrillation)",
    acceptable_diagnoses=["Ischaemic stroke", "Stroke", "MCA stroke", "Acute stroke"],
    correct_management=[
        "Stroke team activation — CODE STROKE",
        "CT head immediately to exclude haemorrhage before thrombolysis",
        "Patient ELIGIBLE for IV alteplase: onset <4.5h, no haemorrhage, no contraindications",
        "IV Alteplase 0.9mg/kg (max 90mg) — 10% as bolus, 90% over 60 min",
        "BP management: if >185/110 before thrombolysis — treat with labetalol or nitropaste",
        "Aspirin 300mg PO — DELAY 24 hours after thrombolysis",
        "Admit to stroke unit with continuous monitoring",
        "Swallow assessment before any oral medications",
        "Anticoagulation for AF: start DOAC after 4-14 days depending on stroke size",
        "Risk factor management: statin, antihypertensive, NOAC for AF long-term",
    ],
    key_learning_points=[
        "Atrial fibrillation without anticoagulation is the leading preventable cause of cardioembolic stroke",
        "Thrombolysis window is 4.5 hours from LAST SEEN WELL — not symptom onset",
        "Non-contrast CT head is mandatory before thrombolysis — to exclude haemorrhage",
        "BP must be <185/110 before giving alteplase",
        "NEVER give aspirin in the first 24 hours after thrombolysis",
        "CHA2DS2-VASc score ≥2 in males → anticoagulate for AF",
    ],
))


# ── Case 5: Appendicitis ──────────────────────────────────────────────────────
_register(ClinicalCase(
    case_id="SIM-005",
    title="Right Iliac Fossa Pain in a 22-Year-Old Male",
    specialty="Surgery",
    difficulty="beginner",
    learning_objectives=[
        "Clinically assess and diagnose acute appendicitis",
        "Use Alvarado/MANTRELS score to guide management",
        "Decide when to proceed to surgery vs. further imaging",
        "Identify perforated appendicitis and manage sepsis",
    ],
    presentation=(
        "A 22-year-old male presents to the ED with a 18-hour history of abdominal pain "
        "that started centrally and has now migrated to the right iliac fossa. "
        "He has not eaten since yesterday and feels nauseous."
    ),
    initial_vitals={
        "HR": "96 bpm",
        "BP": "122/74 mmHg",
        "RR": "18 /min",
        "SpO2": "99% on room air",
        "Temp": "38.1°C",
        "GCS": "15",
    },
    history_data={
        "pain": "It started around my belly button last night, not too bad. Now it's moved to the right lower side and it's much worse — 7/10.",
        "onset": "About 18 hours ago. It started gradually.",
        "migration": "Yes, it definitely moved. Started in the middle, now it's down on the right.",
        "nausea": "Very nauseous. I vomited once this morning.",
        "appetite": "No appetite at all. I haven't eaten since yesterday morning.",
        "bowels": "I haven't been to the toilet since yesterday. No diarrhoea.",
        "urinary symptoms": "No burning, normal colour urine.",
        "previous episodes": "Nothing like this before.",
        "medications": "I don't take any regular medications.",
        "allergies": "No known allergies.",
        "last menstrual period": "I'm male.",
        "trauma": "No injury to the area.",
        "fever": "Yes, I've felt hot and shivery since this morning.",
        "sexual health": "Not relevant.",
    },
    physical_exam={
        "General": "Uncomfortable-looking. Lying still, reluctant to move. Low-grade fever.",
        "Abdomen inspection": "No distension. No visible peristalsis. Moving normally with respiration.",
        "Palpation": "Maximal tenderness at McBurney's point (1/3 from ASIS to umbilicus). Guarding present. Rebound tenderness positive.",
        "Rovsing's sign": "Positive — palpation of LIF causes pain in RIF.",
        "Psoas sign": "Positive — pain on passive extension of right hip.",
        "Obturator sign": "Positive — pain on internal rotation of right hip.",
        "Rectal exam": "Right-sided rectal tenderness.",
        "Bowel sounds": "Slightly reduced but present.",
        "Hernia orifices": "No hernias.",
    },
    investigations={
        "FBC": "WBC 16.8 (neutrophilia 84%). Hb 14.8. Platelets 290.",
        "CRP": "82 mg/L (elevated — inflammatory response).",
        "U&E": "Normal. Creatinine 88.",
        "LFTs": "Normal.",
        "Amylase": "Normal (rules out pancreatitis).",
        "Urine dip": "Trace leucocytes only — no nitrites, no haematuria.",
        "Urine beta-hCG": "Negative (male patient).",
        "USS abdomen": "Non-compressible, aperistaltic appendix measuring 9mm in diameter. Increased echogenicity of surrounding fat. No free fluid. Appearance consistent with acute appendicitis.",
        "CT abdomen/pelvis": "If performed: Inflamed appendix with surrounding inflammatory fat stranding. No evidence of perforation or abscess. Alvarado score 9.",
        "ECG": "Normal sinus rhythm.",
    },
    correct_diagnosis="Acute appendicitis",
    acceptable_diagnoses=["Appendicitis", "Acute appendicitis", "Acute abdomen — appendicitis"],
    correct_management=[
        "NBM (nil by mouth) — patient is surgical",
        "IV access, IV fluids for rehydration",
        "IV analgesia: paracetamol 1g QID + morphine PCA or opioid",
        "IV antibiotics: co-amoxiclav or piperacillin-tazobactam (perioperative prophylaxis)",
        "Surgical consult — urgent appendicectomy (laparoscopic preferred)",
        "Alvarado score 9 — high likelihood, proceed to theatre without CT (USS sufficient)",
        "VTE prophylaxis: LMWH pre-operatively + TEDs",
        "Gain informed consent for laparoscopic +/- open appendicectomy",
        "Post-op: regular analgesia, early mobilisation, discharge in 24-48h if uncomplicated",
    ],
    key_learning_points=[
        "Classical migration of pain from umbilicus to RIF occurs in only 50-60% of appendicitis cases",
        "Alvarado score ≥7 is high probability — proceed to theatre without additional imaging",
        "USS is first-line imaging (no radiation). CT is reserved for diagnostic uncertainty",
        "Leukocytosis + elevated CRP strongly support surgical inflammatory pathology",
        "Rovsing's, psoas, and obturator signs increase specificity of clinical diagnosis",
    ],
))


def get_case(case_id: str) -> ClinicalCase | None:
    return CASES.get(case_id)


def list_cases() -> list[dict]:
    return [
        {
            "case_id": c.case_id,
            "title": c.title,
            "specialty": c.specialty,
            "difficulty": c.difficulty,
            "learning_objectives": c.learning_objectives,
        }
        for c in CASES.values()
    ]
