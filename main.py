"""
MedGemma Clinical Assistant - Main Application
FastAPI server for the AI-powered clinical decision support system.
"""

import asyncio
import base64
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.ehr import get_fhir_server
from src.soap import SOAPGenerator, SOAPNote, EnhancedSOAPNote

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global state
agent = None
asr = None
fhir_server = None
soap_generator = None
vllm_manager = None  # VLLMModelManager instance 

# Store active sessions
sessions: dict[str, dict] = {}


def load_models_lazy():
    """Load models only when first needed (lazy loading)."""
    global agent, asr, vllm_manager

    # Check environment flags
    use_simulated = os.environ.get("SIMULATED_MODE", "false").lower() == "true"
    use_vllm = os.environ.get("USE_VLLM", "false").lower() == "true"

    if agent is None:
        if use_simulated:
            logger.info("Running in SIMULATED mode - no GPU models loaded")
            agent = None  # Will use mock responses
        elif use_vllm:
            # ── vLLM sleep-mode manager: FunctionGemma + MedGemma + MedASR ──
            try:
                from src.agent.vllm_manager import get_vllm_manager, is_vllm_manager_available
                if is_vllm_manager_available():
                    logger.info("Initialising VLLMModelManager (sleep-mode for 3 models)…")
                    vllm_manager = get_vllm_manager()
                    agent = vllm_manager   # Compatible API: .analyze_image() / .process_encounter()
                    logger.info("VLLMModelManager ready — FunctionGemma, MedGemma, MedASR loaded & sleeping")
                else:
                    raise ImportError("vLLM not available")
            except Exception as e:
                logger.warning(f"VLLMModelManager failed: {e}. Falling back to Transformers.")
                from src.agent import MedGemmaAgent
                agent = MedGemmaAgent(load_in_4bit=True)
        else:
            # Default: HuggingFace Transformers with 4-bit quantization
            try:
                from src.agent import MedGemmaAgent
                agent = MedGemmaAgent(load_in_4bit=True)
            except Exception as e:
                logger.warning(f"Could not load MedGemma: {e}. Using simulated mode.")

    if asr is None and vllm_manager is None:
        # Only load a standalone ASR when NOT using the manager
        # (manager owns MedASR internally)
        if use_simulated:
            from src.asr import SimulatedMedASR
            asr = SimulatedMedASR()
        else:
            try:
                from src.asr import MedASRStreaming
                asr = MedASRStreaming()
            except Exception as e:
                logger.warning(f"Could not load MedASR: {e}. Using simulated mode.")
                from src.asr import SimulatedMedASR
                asr = SimulatedMedASR()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global fhir_server, soap_generator
    
    logger.info("Starting MedGemma Clinical Assistant...")
    
    # Initialize FHIR server: Firestore if configured
    try:
        from src.config.firebase_config import is_firebase_available
        if is_firebase_available():
            from src.ehr.firestore_server import FirestoreFHIRServer
            fhir_server = FirestoreFHIRServer()
            logger.info("Using Firestore-backed FHIR server")
        else:
            fhir_server = get_fhir_server()
            logger.info("Firebase not configured — using mock FHIR server")
    except Exception as e:
        logger.warning(f"Firestore init failed: {e} — using mock FHIR server")
        fhir_server = get_fhir_server()
    
    soap_generator = SOAPGenerator()
    
    logger.info("FHIR server and SOAP generator initialized")
    
    # Load AI models at startup so they're ready for all endpoints
    load_models_lazy()
    if agent is not None:
        logger.info(f"Agent loaded: {type(agent).__name__}")
    else:
        logger.info("No agent loaded (simulated mode or model unavailable)")
    
    yield
    
    logger.info("Shutting down MedGemma Clinical Assistant...")


# Create FastAPI app
app = FastAPI(
    title="MedGemma Clinical Assistant",
    description="AI-powered clinical decision support with MedGemma and MedASR",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=static_path), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main application page."""
    index_path = static_path / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text())
    return HTMLResponse(content="<h1>MedGemma Clinical Assistant</h1><p>Static files not found.</p>")


@app.get("/api/patients")
async def list_patients():
    """List available patients for demo."""
    return {"patients": fhir_server.list_patients()}


@app.get("/api/patients/{patient_id}")
async def get_patient(patient_id: str):
    """Get patient summary from EHR."""
    summary = fhir_server.get_patient_summary(patient_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return summary


@app.post("/api/encounters/start")
async def start_encounter(patient_id: str = Form(...)):
    """Start a new clinical encounter session."""
    import uuid
    
    patient_summary = fhir_server.get_patient_summary(patient_id)
    if patient_summary is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "patient_id": patient_id,
        "patient_context": patient_summary,
        "transcription": "",
        "image_path": None,
        "image_modality": None,
        "soap_note": None,
        "status": "active"
    }
    
    # Return everything from get_patient_summary plus session status
    return {
        "session_id": session_id,
        "status": "active",
        **patient_summary
    }


@app.post("/api/encounters/{session_id}/image")
async def upload_image(
    session_id: str,
    image: UploadFile = File(...),
    modality: str = Form("xray")
):
    """Upload a medical image for the encounter."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Save uploaded image
    upload_dir = Path(__file__).parent / "uploads"
    upload_dir.mkdir(exist_ok=True)
    
    image_path = upload_dir / f"{session_id}_{image.filename}"
    content = await image.read()
    image_path.write_bytes(content)
    
    sessions[session_id]["image_path"] = str(image_path)
    sessions[session_id]["image_modality"] = modality
    
    # If agent is loaded, analyze image
    load_models_lazy()
    
    if agent is not None:
        try:
            analysis = agent.analyze_image(
                image_path,
                clinical_context=sessions[session_id].get("transcription", ""),
                modality=modality
            )
            sessions[session_id]["image_analysis"] = analysis
            return {
                "status": "analyzed",
                "image_path": str(image_path),
                "analysis": analysis["analysis"]
            }
        except Exception as e:
            logger.error(f"Image analysis failed: {e}")
            return {
                "status": "uploaded",
                "image_path": str(image_path),
                "analysis": None,
                "error": str(e)
            }
    
    return {
        "status": "uploaded",
        "image_path": str(image_path),
        "analysis": None
    }


@app.post("/api/encounters/{session_id}/transcription")
async def update_transcription(
    session_id: str,
    text: str = Form(...)
):
    """Update encounter transcription."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    sessions[session_id]["transcription"] += " " + text
    return {
        "status": "updated",
        "transcription": sessions[session_id]["transcription"]
    }


@app.post("/api/encounters/{session_id}/generate-soap")
async def generate_soap(session_id: str, chief_complaint: str = Form("")):
    """Generate enhanced SOAP note with clinical intelligence."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    load_models_lazy()
    
    # Get transcription and image findings
    transcription = session.get("transcription", "")
    image_findings = session.get("image_analysis", {}).get("analysis", None) if session.get("image_analysis") else None
    patient_context = session.get("patient_context")
    
    if agent is not None:
        try:
            # Use MedGemma to process encounter
            result = agent.process_encounter(
                transcription=transcription,
                patient_context=patient_context,
                image_path=session.get("image_path"),
                image_modality=session.get("image_modality", "xray")
            )

            # result must be a dict; guard against agents that return plain text
            if not isinstance(result, dict):
                result = {"soap_note": str(result), "alerts": []}

            # Generate enhanced SOAP with clinical intelligence
            enhanced_soap = soap_generator.generate_enhanced_soap(
                transcription=transcription,
                patient_context=patient_context,
                image_findings=image_findings,
                raw_soap_text=result.get("soap_note")
            )
            session["soap_note"] = enhanced_soap
            
            return {
                "status": "generated",
                "soap": enhanced_soap.to_dict(),
                "soap_html": enhanced_soap.to_html(),
                "alerts": enhanced_soap.critical_alerts,
                "drug_interactions": enhanced_soap.drug_interactions,
                "differentials": enhanced_soap.differentials
            }
        except Exception as e:
            import traceback
            logger.error(f"SOAP generation failed: {e}\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # Simulated mode - still use enhanced SOAP with clinical intelligence
    enhanced_soap = soap_generator.generate_enhanced_soap(
        transcription=transcription or f"Patient presents with: {chief_complaint or 'symptoms as dictated'}.",
        patient_context=patient_context,
        image_findings=image_findings
    )
    
    # Override with simulated content if no transcription
    if not transcription:
        enhanced_soap.subjective = f"Patient presents with: {chief_complaint or 'symptoms as dictated'}."
        enhanced_soap.objective = "Vital signs stable. Physical examination findings pending review."
        enhanced_soap.assessment = "Clinical assessment pending MedGemma analysis."
        enhanced_soap.plan = "1. Review findings\n2. Order additional tests as needed\n3. Follow up in 2 weeks"
    
    session["soap_note"] = enhanced_soap
    
    return {
        "status": "generated",
        "soap": enhanced_soap.to_dict(),
        "soap_html": enhanced_soap.to_html(),
        "alerts": enhanced_soap.critical_alerts,
        "drug_interactions": enhanced_soap.drug_interactions,
        "differentials": enhanced_soap.differentials,
        "simulated": True
    }


@app.post("/api/encounters/{session_id}/approve")
async def approve_soap(session_id: str):
    """Approve SOAP note and update EHR."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    if session.get("soap_note") is None:
        raise HTTPException(status_code=400, detail="No SOAP note to approve")
    
    # Update EHR
    soap_note = session["soap_note"]
    result = fhir_server.update_patient_record(
        patient_id=session["patient_id"],
        encounter_note=soap_note.to_markdown()
    )
    
    session["status"] = "completed"
    
    return {
        "status": "approved",
        "ehr_update": result
    }


@app.websocket("/ws/audio/{session_id}")
async def audio_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time audio streaming."""
    await websocket.accept()

    if session_id not in sessions:
        await websocket.close(code=4004, reason="Session not found")
        return

    load_models_lazy()

    # Resolve the ASR instance:
    # - manager mode: wake up MedASR through the manager
    # - standalone mode: use the global asr
    if vllm_manager is not None:
        active_asr = vllm_manager.get_medasr()
    else:
        active_asr = asr

    # Accumulator for transcription
    full_transcription = []

    def on_transcription(text: str):
        """Callback for new transcription chunks."""
        full_transcription.append(text)
        sessions[session_id]["transcription"] = " ".join(full_transcription)

    # Start ASR listening
    if active_asr is not None:
        active_asr.start_listening(on_transcription)

    try:
        while True:
            # Receive audio data
            data = await websocket.receive_bytes()

            if active_asr is not None:
                active_asr.add_audio_bytes(data, sample_rate=16000)

            # Send back current transcription
            await websocket.send_json({
                "type": "transcription",
                "text": sessions[session_id].get("transcription", "")
            })

    except WebSocketDisconnect:
        logger.info(f"Audio WebSocket disconnected for session {session_id}")
    finally:
        if active_asr is not None:
            active_asr.stop_listening()


@app.get("/api/model-status")
async def get_model_status():
    """Return current sleep/wake status of all managed models."""
    if vllm_manager is not None:
        return vllm_manager.get_status()
    # Standalone (non-manager) mode
    return {
        "active": "medgemma" if agent is not None else None,
        "models": {
            "medgemma": {"status": "awake" if agent is not None else "unloaded"},
            "medasr": {"status": "awake" if asr is not None else "unloaded"},
        },
    }


@app.post("/api/encounters/{session_id}/transcribe-audio")
async def transcribe_audio_file(
    session_id: str,
    audio: UploadFile = File(...),
):
    """
    Upload an audio file and transcribe it with MedASR.
    The resulting transcription is appended to the encounter session.
    Useful for testing dictation without a live microphone.
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    load_models_lazy()

    # Save audio to a temp file
    upload_dir = Path(__file__).parent / "uploads"
    upload_dir.mkdir(exist_ok=True)
    audio_path = upload_dir / f"{session_id}_audio_{audio.filename}"
    content = await audio.read()
    audio_path.write_bytes(content)

    try:
        if vllm_manager is not None:
            text = vllm_manager.transcribe_audio_file(str(audio_path))
        elif asr is not None and hasattr(asr, "transcribe_file"):
            text = asr.transcribe_file(str(audio_path))
        else:
            raise HTTPException(status_code=503, detail="ASR model not available")

        # Append to session transcription
        existing = sessions[session_id].get("transcription", "")
        sessions[session_id]["transcription"] = (existing + " " + text).strip()

        return {
            "status": "transcribed",
            "text": text,
            "full_transcription": sessions[session_id]["transcription"],
        }
    except Exception as e:
        logger.error(f"Audio transcription failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up temp file
        try:
            audio_path.unlink(missing_ok=True)
        except Exception:
            pass


# ============================================================
# NEW FEATURE ROUTES - History, Compliance, Council, Portal
# ============================================================

from fastapi.templating import Jinja2Templates
from starlette.requests import Request

templates_path = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))


@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    """Patient History page."""
    return templates.TemplateResponse("history.html", {"request": request})


@app.get("/compliance", response_class=HTMLResponse)
async def compliance_page(request: Request):
    """SOAP Compliance Monitor page."""
    return templates.TemplateResponse("compliance.html", {"request": request})


@app.get("/council", response_class=HTMLResponse)
async def council_page(request: Request):
    """Diagnostic Council page."""
    return templates.TemplateResponse("council.html", {"request": request})


@app.get("/patient-portal", response_class=HTMLResponse)
async def patient_portal_page(request: Request):
    """Patient Portal page."""
    return templates.TemplateResponse("patient_portal.html", {"request": request})


@app.get("/ai-portal", response_class=HTMLResponse)
async def ai_portal_page(request: Request):
    """AI Chat Portal page for Doctors and Residents."""
    return templates.TemplateResponse("ai_portal.html", {"request": request})


# History API endpoints
@app.get("/api/history/{patient_id}/timeline")
async def get_patient_timeline(patient_id: str, days: int = 365):
    """Get patient history timeline."""
    from src.history import get_history_service
    
    history_service = get_history_service(fhir_server)
    timeline = history_service.get_patient_timeline(patient_id, days)
    
    # Get patient info
    patient_summary = fhir_server.get_patient_summary(patient_id)
    patient_info = None
    if patient_summary:
        p_data = patient_summary.get("patient", {})
        patient_info = {
            "id": patient_id,
            "name": p_data.get("name", "Unknown"),
            "age": p_data.get("age", "Unknown"),
            "gender": p_data.get("gender", "Unknown")
        }
    
    return {"patient": patient_info, "timeline": timeline}


@app.get("/api/history/{patient_id}/medications")
async def get_patient_medications(patient_id: str):
    """Get patient medication history."""
    from src.history import get_history_service
    history_service = get_history_service(fhir_server)
    return {"medications": history_service.get_medication_history(patient_id)}


@app.get("/api/history/{patient_id}/imaging")
async def get_patient_imaging(patient_id: str, modality: str = None):
    """Get patient imaging studies."""
    from src.history import get_history_service
    history_service = get_history_service(fhir_server)
    return {"studies": history_service.get_imaging_studies(patient_id, modality)}


# Compliance API endpoints
@app.post("/api/compliance/check")
async def run_compliance_check():
    """Run SOAP compliance check."""
    from src.compliance import get_compliance_checker
    
    checker = get_compliance_checker()
    report = checker.run_compliance_check()
    
    # Add compliant documents to response
    compliant_docs = checker.get_compliant_documents()
    result = report.to_dict()
    result["compliant_documents"] = compliant_docs
    
    return result


@app.get("/api/compliance/report")
async def get_compliance_report():
    """Get last compliance report."""
    from src.compliance import get_compliance_checker
    
    checker = get_compliance_checker()
    report = checker.get_last_report()
    if report:
        return report.to_dict()
    return {"error": "No compliance check has been run yet"}


# Diagnostic Council API endpoints
@app.post("/api/council/deliberate")
async def council_deliberate(request: Request):
    """Run diagnostic council deliberation."""
    from src.council import get_diagnostic_council
    
    data = await request.json()
    symptoms = data.get("symptoms", [])
    patient_history = data.get("patient_history", "")
    imaging_findings = data.get("imaging_findings", "")
    num_rollouts = data.get("num_rollouts", 5)
    vitals = data.get("vitals")
    
    council = get_diagnostic_council(agent=agent, num_rollouts=num_rollouts)
    deliberation = council.deliberate(
        symptoms=symptoms,
        patient_history=patient_history,
        imaging_findings=imaging_findings,
        vitals=vitals
    )
    
    return deliberation.to_dict()


@app.get("/api/council/history")
async def get_council_history():
    """Get deliberation history."""
    from src.council import get_diagnostic_council
    council = get_diagnostic_council(agent=agent)
    return {"deliberations": council.get_deliberation_history()}


# Patient Portal API endpoints
@app.get("/api/portal/{patient_id}/summary")
async def get_portal_summary(patient_id: str):
    """Get patient appointment summary for portal."""
    from src.portal import get_patient_assistant
    assistant = get_patient_assistant(fhir_server=fhir_server)
    return assistant.get_appointment_summary(patient_id)


@app.post("/api/portal/ask")
async def portal_ask_question(request: Request):
    """Ask a question in patient portal."""
    from src.portal import get_patient_assistant
    
    data = await request.json()
    patient_id = data.get("patient_id", "P001")
    question = data.get("question", "")
    
    # Pass the global agent so MedGemma can answer questions
    assistant = get_patient_assistant(agent=agent, fhir_server=fhir_server)
    
    # Fetch patient context from FHIR for personalized responses
    patient_context = None
    if fhir_server:
        patient_context = fhir_server.get_patient_summary(patient_id)
    
    query = assistant.ask(patient_id, question, patient_context=patient_context)
    
    return query.to_dict()


@app.get("/api/portal/{patient_id}/history")
async def get_portal_query_history(patient_id: str):
    """Get patient query history."""
    from src.portal import get_patient_assistant
    assistant = get_patient_assistant(fhir_server=fhir_server)
    return {"queries": assistant.get_query_history(patient_id)}


# ============================================================
# Patient Memory API endpoints (Mem0)
# ============================================================

@app.get("/api/memory/{patient_id}")
async def get_patient_memories(patient_id: str):
    """Get all persistent memories for a patient."""
    try:
        from src.memory.patient_memory import get_patient_memory
        pm = get_patient_memory()
        memories = pm.get_all(patient_id)
        return {
            "patient_id": patient_id,
            "memories": memories,
            "count": len(memories)
        }
    except Exception as e:
        return {"error": str(e), "memories": []}


@app.post("/api/memory/{patient_id}/search")
async def search_patient_memories(patient_id: str, request: Request):
    """Semantic search through patient memories."""
    try:
        body = await request.json()
        query = body.get("query", "")
        limit = body.get("limit", 10)
        
        from src.memory.patient_memory import get_patient_memory
        pm = get_patient_memory()
        results = pm.recall(patient_id, query, limit=limit)
        return {
            "patient_id": patient_id,
            "query": query,
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        return {"error": str(e), "results": []}


@app.post("/api/memory/{patient_id}/add")
async def add_patient_memory(patient_id: str, request: Request):
    """Add a clinical note to patient memory."""
    try:
        body = await request.json()
        note = body.get("note", "")
        category = body.get("category", "general")
        
        from src.memory.patient_memory import get_patient_memory
        pm = get_patient_memory()
        result = pm.add_clinical_note(patient_id, note, category=category)
        return {
            "status": "saved",
            "patient_id": patient_id,
            "category": category,
            "result": result
        }
    except Exception as e:
        return {"error": str(e)}


@app.delete("/api/memory/{patient_id}/{memory_id}")
async def delete_patient_memory(patient_id: str, memory_id: str):
    """Delete a specific patient memory."""
    try:
        from src.memory.patient_memory import get_patient_memory
        pm = get_patient_memory()
        result = pm.delete_memory(memory_id)
        return result
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    from src.memory.patient_memory import is_mem0_available
    return {
        "status": "healthy",
        "agent_loaded": agent is not None,
        "asr_loaded": asr is not None or vllm_manager is not None,
        "vllm_manager": vllm_manager is not None,
        "fhir_server": fhir_server is not None,
        "mem0_available": is_mem0_available()
    }


# ============================================================
# AI Chat Portal API endpoints
# ============================================================

@app.post("/api/ai-portal/chat")
async def ai_portal_chat(request: Request):
    """
    MedGemma chat endpoint for the AI Chat Portal.

    Accepts:
      - message: str — the user's question
      - history: list[{role, content}] — prior turns (text only)
      - patient_context: dict | {freeText: str} | None
      - image_data: str | None — base64 data URL (data:image/...;base64,...)
      - image_modality: str — e.g. 'xray'
      - image_name: str
      - annotations: list[{id, x, y, w, h, label}] — normalised 0-1 boxes
    """
    data = await request.json()
    message: str = data.get("message", "")
    history: list = data.get("history", [])
    patient_context = data.get("patient_context")
    image_data: str | None = data.get("image_data")
    image_modality: str = data.get("image_modality", "xray")
    annotations: list = data.get("annotations", [])

    if not message and not image_data:
        raise HTTPException(status_code=400, detail="message or image_data required")

    load_models_lazy()

    # ── Build prompt ──────────────────────────────────────────────────────────
    import json as _json
    import base64 as _b64
    import io

    parts: list[str] = []

    # System context
    parts.append(
        "You are MedGemma, a clinical AI assistant helping Doctors and Residents. "
        "Provide accurate, evidence-based clinical insights. "
        "Always note diagnostic uncertainty and recommend clinical correlation."
    )

    # Patient context
    if patient_context:
        if isinstance(patient_context, dict) and "freeText" in patient_context:
            parts.append(f"\n## Patient Information (manual entry)\n{patient_context['freeText']}")
        elif isinstance(patient_context, dict):
            # Structured FHIR summary
            p = patient_context.get("patient", {})
            if p:
                parts.append(
                    f"\n## Patient\n{p.get('name','Unknown')}, "
                    f"{p.get('age','?')} yr, {p.get('gender','?')}"
                )
            conditions = patient_context.get("conditions", [])
            if conditions:
                cond_names = ", ".join(c.get("name", "") for c in conditions if c.get("name"))
                parts.append(f"**Conditions:** {cond_names}")
            medications = patient_context.get("medications", [])
            if medications:
                med_names = ", ".join(m.get("name", "") for m in medications if m.get("name"))
                parts.append(f"**Medications:** {med_names}")
            allergies = patient_context.get("allergies", [])
            if allergies:
                allergy_names = ", ".join(a.get("substance", "") for a in allergies if a.get("substance"))
                parts.append(f"**Allergies:** {allergy_names}")

    # Chat history
    if history:
        parts.append("\n## Conversation History")
        for turn in history[-8:]:  # keep last 8 turns for context window
            role_label = "Doctor" if turn["role"] == "user" else "MedGemma"
            parts.append(f"**{role_label}:** {turn['content']}")

    # Annotation context
    if annotations:
        ann_desc = "; ".join(
            f"{a.get('label','Region')} at ({a['x']:.2f},{a['y']:.2f}) "
            f"size {a['w']:.2f}x{a['h']:.2f}"
            for a in annotations
        )
        parts.append(
            f"\n## Image Annotations\n"
            f"The physician has annotated the following region(s) for focused analysis:\n{ann_desc}\n"
            f"Please pay particular attention to these marked areas in your analysis."
        )

    # Current question
    if image_data and not annotations:
        parts.append(f"\n## Current Question\nAnalyze this {image_modality.upper()} image. {message}")
    elif image_data and annotations:
        parts.append(
            f"\n## Current Question\nAnalyze this {image_modality.upper()} image, "
            f"focusing on the annotated region(s). {message}"
        )
    else:
        parts.append(f"\n## Current Question\n{message}")

    prompt = "\n".join(parts)

    # ── Decode image (if any) ─────────────────────────────────────────────────
    pil_image = None
    img_bytes_raw = None
    if image_data:
        try:
            if "," in image_data:
                image_data = image_data.split(",", 1)[1]
            img_bytes_raw = _b64.b64decode(image_data)
            from PIL import Image as PILImage
            pil_image = PILImage.open(io.BytesIO(img_bytes_raw)).convert("RGB")
        except Exception as e:
            logger.warning(f"AI portal — failed to decode image: {e}")

    response_text = ""

    if agent is not None:
        try:
            if hasattr(agent, "generate_medgemma"):
                # ── VLLMModelManager path ──────────────────────────────────
                response_text = agent.generate_medgemma(
                    prompt=prompt,
                    image=pil_image,
                    temperature=0.4,
                    max_tokens=1536,
                )
            elif hasattr(agent, "chat"):
                # ── Transformers MedGemmaAgent path ───────────────────────
                if pil_image is not None and img_bytes_raw is not None:
                    # Save image to temp file so analyze_image() can use it
                    import tempfile
                    suffix = ".jpg"
                    with tempfile.NamedTemporaryFile(
                        suffix=suffix,
                        dir=Path(__file__).parent / "uploads",
                        delete=False
                    ) as tmp:
                        tmp_path = Path(tmp.name)
                        pil_image.save(tmp_path, format="JPEG")
                    try:
                        analysis = agent.analyze_image(
                            tmp_path,
                            clinical_context=prompt,
                            modality=image_modality,
                        )
                        response_text = analysis.get("analysis", "")
                    finally:
                        try:
                            tmp_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                else:
                    # Text-only chat
                    response_text = agent.chat(prompt)
            else:
                raise AttributeError(
                    f"Agent type {type(agent).__name__!r} has no recognized "
                    "generation method (generate_medgemma / chat)"
                )
        except Exception as e:
            logger.error(f"AI portal chat generation failed: {e}")
            raise HTTPException(status_code=500, detail=f"Model error: {e}")
    else:
        # Simulated fallback
        ctx_name = ""
        if patient_context and isinstance(patient_context, dict):
            p = patient_context.get("patient", {})
            ctx_name = p.get("name", "the patient") if p else "the patient"
        elif patient_context and isinstance(patient_context, dict) and "freeText" in patient_context:
            ctx_name = "the patient (manual entry)"

        if pil_image:
            response_text = (
                f"[Simulated — no GPU] I would analyze this {image_modality.upper()} image"
                + (f" for {ctx_name}" if ctx_name else "")
                + ".\n\nKey findings would be assessed based on image quality, visible structures, "
                "and clinical correlation with the provided history. "
                "Please load MedGemma for actual image analysis."
            )
        else:
            response_text = (
                f"[Simulated — no GPU] Regarding your question: \"{message}\"\n\n"
                "In a production environment with MedGemma loaded, I would provide detailed "
                "clinical insights based on the patient context and your question."
            )

    return {"response": response_text, "simulated": agent is None}


@app.post("/api/ai-portal/transcribe")
async def ai_portal_transcribe(audio: UploadFile = File(...)):
    """Transcribe an audio blob for the AI Chat Portal (recording or file upload)."""
    load_models_lazy()

    upload_dir = Path(__file__).parent / "uploads"
    upload_dir.mkdir(exist_ok=True)
    audio_path = upload_dir / f"portal_audio_{audio.filename or 'blob.webm'}"
    content = await audio.read()
    audio_path.write_bytes(content)

    try:
        if vllm_manager is not None:
            text = vllm_manager.transcribe_audio_file(str(audio_path))
        elif asr is not None and hasattr(asr, "transcribe_file"):
            text = asr.transcribe_file(str(audio_path))
        else:
            raise HTTPException(status_code=503, detail="ASR model not available")
        return {"text": text}
    except Exception as e:
        logger.error(f"AI portal transcription failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            audio_path.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    import argparse
    import uvicorn
    
    parser = argparse.ArgumentParser(description="MedGemma Clinical Assistant")
    parser.add_argument("--use-vllm", action="store_true", help="Use vLLM backend for faster inference")
    parser.add_argument("--simulated", action="store_true", help="Run in simulated mode (no GPU)")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    args = parser.parse_args()
    
    if args.simulated:
        os.environ["SIMULATED_MODE"] = "true"
        print("Running in SIMULATED mode (no GPU models)")
    
    if args.use_vllm:
        os.environ["USE_VLLM"] = "true"
        print("Using vLLM backend for inference")
    
    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=False,
        log_level="info"
    )
