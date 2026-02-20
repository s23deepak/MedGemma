# Demo Recording Script 🎬

## For the MedGemma Impact Challenge Video Demo

---

## Setup Checklist
- [ ] Server running: `uv run python main.py`
- [ ] Browser at: http://localhost:8000
- [ ] Sample X-ray ready: `data/sample_images/chest_xray_demo.png`
- [ ] Microphone working
- [ ] Screen recording software ready (OBS, Loom, etc.)

---

## Demo Scenario: Patient Sarah Wilson (P001)

### Patient Background
- **Name**: Sarah Wilson, 58-year-old female
- **History**: Asthma, hypertension, former smoker (quit 2019)
- **Current Meds**: Albuterol inhaler, Lisinopril 10mg
- **Allergy**: Penicillin

---

## 🎬 RECORDING SCRIPT

### Act 1: Open the Application (15 seconds)
*(Show the clean UI loading)*

**[NARRATION]** (optional voiceover)
> "This is MedGemma Clinical Assistant - an AI-powered tool that helps physicians 
> catch missed diagnoses and generate documentation in real-time."

---

### Act 2: Select Patient (10 seconds)
1. Click on **Sarah Wilson** in the patient list
2. *(Show EHR data loading - conditions, medications, allergies)*

---

### Act 3: Upload Medical Image (15 seconds)
1. Click/drag the chest X-ray image into the upload area
2. Select modality: **X-ray**
3. *(Wait for AI analysis to appear)*

---

### Act 4: Doctor Dictation (60-90 seconds)
Click **Start Recording** and speak naturally:

```
Patient is a 58-year-old female presenting today with a 
three-week history of persistent dry cough and mild shortness 
of breath on exertion.

She reports the cough started after a cold about a month ago 
and has not improved. She denies fever, chills, or night sweats. 
No hemoptysis. She quit smoking seven years ago after a 
20-pack-year history.

On examination, vital signs are stable. Blood pressure 138 over 82. 
Heart rate 78. Oxygen saturation 96 percent on room air.

Lungs: Mild expiratory wheezing bilaterally, no crackles or rhonchi.
Heart: Regular rate and rhythm, no murmurs.
No peripheral edema.

The chest X-ray shows... let me review the image...

[PAUSE - look at the screen as if reviewing]

There appears to be some increased interstitial markings in the 
right lower lobe. I'm considering asthma exacerbation versus 
early pneumonia versus... I want to make sure we're not missing 
anything here.
```

Click **Stop Recording**

---

### Act 5: Generate SOAP Note (20 seconds)
1. Click **Generate SOAP Note**
2. *(Watch the AI process and generate the note)*
3. **HIGHLIGHT** the "Potential Missed Diagnoses" section if it appears
   - This is your key differentiator!

---

### Act 6: Review & Approve (15 seconds)
1. Scroll through the generated SOAP note
2. Show the Subjective/Objective/Assessment/Plan sections
3. Click **Approve & Save to EHR**
4. *(Show confirmation toast)*

---

### Act 7: Closing (10 seconds)
**[NARRATION]**
> "With MedGemma Clinical Assistant, physicians can focus on patients 
> while AI handles documentation and ensures nothing is missed."

---

## 🎯 Key Points to Emphasize

1. **Real-time transcription** - Show words appearing as you speak
2. **Multimodal understanding** - Image + voice + EHR context
3. **Missed diagnosis detection** - The AI catches what might be overlooked
4. **Human-in-the-loop** - Doctor approval required before EHR update
5. **Time savings** - Documentation generated automatically

---

## Alternative Dictation Scripts

### Shorter Version (30 seconds)
```
58-year-old female with three weeks of dry cough and dyspnea on exertion.
Former smoker, history of asthma and hypertension.
Vitals stable, SpO2 96 percent.
Exam shows bilateral expiratory wheezing.
Reviewing the chest X-ray - there are increased interstitial markings 
in the right lower lobe that I want to investigate further.
```

### Emergency Scenario (for demo impact)
```
65-year-old male presenting with acute onset chest pain and shortness 
of breath for the past two hours. Pain is substernal, radiating to the 
left arm. He has a history of diabetes and coronary artery disease.
Vitals show elevated heart rate at 110, blood pressure 160 over 95.
The chest X-ray shows... [AI should flag potential cardiac emergency]
```

---

## Technical Tips

- Speak clearly at a moderate pace
- Pause briefly between sentences (helps ASR accuracy)
- Use medical terminology naturally
- If the transcription misses something, you can continue speaking
- The demo should feel natural, not scripted

---

## Video Production Tips

1. **Lighting**: Good face lighting if showing yourself
2. **Audio**: Use a good microphone, minimize background noise
3. **Screen**: 1080p or higher, clean browser window
4. **Length**: Keep under 3 minutes (competition requirement)
5. **Story**: Problem → Solution → Impact

---

## Sample Intro/Outro

**Intro:**
> "Every day, physicians spend over 2 hours on documentation. 
> Meanwhile, diagnostic errors affect 12 million Americans annually. 
> What if AI could help with both?"

**Outro:**
> "MedGemma Clinical Assistant: Helping doctors focus on what matters - 
> their patients. Built with Google's Health AI Developer Foundations."
