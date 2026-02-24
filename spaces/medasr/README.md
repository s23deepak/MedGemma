---
title: MedASR
emoji: 🏥
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: "4.44.0"
app_file: app.py
pinned: false
license: apache-2.0
---

# MedASR — Medical Speech Recognition

Runs `google/medasr`, a 105M-parameter CTC model trained on medical audio.

## Interactive use
Upload or record audio using the Microphone/Upload tab.

## Programmatic API
This Space exposes an HTTP endpoint callable from any application.
See `src/asr/medasr_streaming.py` in the MedGemma project for the client code.

Set `MEDASR_SPACE_ID=your-username/medasr` in your `.env` to route transcription here.

In the main MedGemma app, transcriptions can be combined with EHR location and local health trend context during SOAP generation.
