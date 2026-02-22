# MedGemma Clinical Assistant

AI-powered clinical decision support system using MedGemma and MedASR.

## Quick Start

```bash
# Simulated mode (no GPU required)
SIMULATED_MODE=true uv run python main.py

# Full mode (requires MedGemma + MedASR access)
uv run python main.py
```

Open: http://localhost:8000

## Features

- 🎤 **Real-time Speech Recognition** - MedASR listens to physician dictation
- 🩻 **Medical Image Analysis** - MedGemma analyzes X-rays, CT, MRI
- 📋 **SOAP Note Generation** - Automatic clinical documentation
- ⚠️ **Missed Diagnosis Detection** - AI highlights potential concerns
- 🏥 **EHR Integration** - FHIR-based patient data with approval workflow

## Next Steps

- [ ] Add EHR integration
- [ ] Add missed diagnosis detection
- [ ] Add SOAP note generation
- [ ] Add medical image analysis
- [ ] Add real-time speech recognition
- [ ] Add patient data approval workflow
- [ ] Patient to hospital data transfer(lets say for ER patient has to explain his symptoms to AI and AI will generate SOAP note and send to doctor)
- [] When a doctor says to look into other images AI will call MedGemma and generate a report
- [] Can MedGemma provide bounding box for the tumor in the image.
- [] Doctors or Residents should have an option to annotate the image and send it to MedGemma for further analysis.
- [] Connect to online Medical Dictionaries for better understanding of medical terms.
- [] Connect to online databases for scalability.
- [] Provide metadata of location of hosiptal the paitent has visited, because of different weather conditions, pollution levels, etc. the diagnosis might vary.

## To Ponder
- [] How to help nurse with less medical knowledge to understand the medical reports, or real time diagnosis. 
- [] Do patients talk with Insurance agents to get the best insurance plan for their medical needs or do the hospital do it?

## Architecture

```
MedASR (Speech) ─┐
                 ├─→ MedGemma 4B ─→ SOAP Generator ─→ Doctor Approval ─→ EHR Update
Medical Image ───┘         ↑
                           │
                   FHIR EHR Context
```

## Project Structure

```
├── main.py              # FastAPI server
├── AGENTS.md            # Agent definition
├── src/
│   ├── agent/           # MedGemma agent + tools
│   ├── asr/             # MedASR streaming
│   ├── ehr/             # Mock FHIR server
│   └── soap/            # SOAP note generation
└── static/              # Frontend UI
```

## Requirements

- Python 3.11+
- NVIDIA GPU with 8GB+ VRAM (for full mode)
- HuggingFace access to `google/medgemma-1.5-4b-it` and `google/medasr`

## Competition

Built for the [MedGemma Impact Challenge](https://www.kaggle.com/competitions/med-gemma-impact-challenge) on Kaggle.

## License

CC BY 4.0 (per competition requirements)
