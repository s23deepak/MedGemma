# Demo Recording Script 🎬

## For the MedGemma Impact Challenge Video Demo

---

## Setup Checklist
- [ ] Server running: `SIMULATED_MODE=true uv run python main.py`
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
> "This is MedGemma Clinical Assistant — an AI-powered tool that helps physicians
> catch missed diagnoses, ground decisions in live literature, and generate
> documentation in real-time."

---

### Act 2: Select Patient (10 seconds)
1. Click on **Sarah Wilson** in the patient list
2. *(Show EHR data loading — conditions, medications, allergies)*

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

The chest X-ray shows increased interstitial markings in the
right lower lobe. I'm considering asthma exacerbation versus
early pneumonia. I want to make sure we're not missing anything.
```

Click **Stop Recording**

---

### Act 5: Generate SOAP Note & PubMed (25 seconds)
1. Click **Generate SOAP Note**
2. *(Watch the AI process and generate the note)*
3. **HIGHLIGHT** the "Potential Missed Diagnoses" section if it appears
4. *(After a few seconds, the **📚 PubMed Literature** card appears in the right panel)*
5. Click to expand it — show **rare diagnoses** and **citations** from actual PubMed articles
   - This is your key differentiator: real-time evidence grounding!

6. **Call out local trend correlation in response JSON/UI context**
   - Mention: “The assistant also correlates local health/environment trends with today’s symptoms.”
   - Example narrative: “If wildfire smoke events occurred in Florida this week, respiratory symptoms are surfaced with exposure-aware context.”

---

### Act 6: Diagnostic Council (30 seconds)
1. Navigate to **Diagnostic Council** in the nav
2. The patient information is pre-loaded — enter the symptoms: `chest pain, shortness of breath, cough`
3. Click **🧠 Start Council Deliberation**
4. *(5 independent AI opinions appear with consensus scoring)*
5. **HIGHLIGHT** the **📚 PubMed — Zebra Hunt Results** panel below the discussion
   - Show rare diagnoses the council flagged from literature that might otherwise be missed

---

### Act 7: AI Chat Portal (30 seconds)
1. Navigate to **AI Chat Portal**
2. Select **Sarah Wilson** in the left panel
3. Upload the same chest X-ray into the center panel
4. Draw an **annotation box** around the right lower lobe opacity
5. Type: `"What rare conditions could cause right lower lobe changes in a former smoker?"`
6. *(MedGemma responds with reasoning)*
7. *(The **📊 Evidence Check** pill appears below — click to expand PubMed literature)*

---

### Act 8: Review & Approve Encounter (15 seconds)
1. Return to the **Encounters** page
2. Scroll through the generated SOAP note
3. Show the Subjective/Objective/Assessment/Plan sections
4. Click **Approve & Save to EHR**
5. *(Show confirmation toast)*

---

### Act 9: Closing (10 seconds)
**[NARRATION]**
> "With MedGemma Clinical Assistant, physicians get real-time AI reasoning,
> live PubMed evidence, and multi-opinion consensus — all while keeping
> documentation automatic and the doctor in control."

---

## 🎯 Key Points to Emphasize

1. **Real-time transcription** — Show words appearing as you speak
2. **Multimodal understanding** — Image + voice + EHR context
3. **Missed diagnosis detection** — The AI catches what might be overlooked
4. **Live PubMed grounding** — Rare diagnoses backed by actual citations
5. **Location-aware trend context** — Local outbreaks/environment events correlated to symptoms
6. **Multi-opinion consensus** — Diagnostic Council with 5 independent analyses
7. **Human-in-the-loop** — Doctor approval required before EHR update
8. **Time savings** — Documentation generated automatically

---

## Alternative Dictation Scripts

### Shorter Version (30 seconds)
```
58-year-old female with three weeks of dry cough and dyspnea on exertion.
Former smoker, history of asthma and hypertension.
Vitals stable, SpO2 96 percent.
Exam shows bilateral expiratory wheezing.
Reviewing the chest X-ray — there are increased interstitial markings
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

## Feature Demo Sequence (Quick Reference)

| Feature | Page | What to Show |
|---------|------|--------------|
| Patient EHR | Home | Patient list → click patient → EHR loads |
| Dictation + SOAP | Home | Record → Generate SOAP → See missed diagnoses |
| PubMed in Encounter | Home | 📚 PubMed Literature card auto-appears post-SOAP |
| Diagnostic Council | /council | Enter symptoms → 5 opinions → PubMed Zebra Hunt |
| AI Chat Portal | /ai-portal | Select patient → annotate image → chat → Evidence Check |
| Compliance | /compliance | Run check → see flags and rates |
| Patient Portal | /patient-portal | Ask question → emergency detection demo |

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
> What if AI could help with both — and back every suggestion with
> real evidence from medical literature?"

**Outro:**
> "MedGemma Clinical Assistant: Real-time AI reasoning, live PubMed evidence,
> multi-opinion consensus — helping doctors focus on what matters most: their patients.
> Built with Google's Health AI Developer Foundations."
