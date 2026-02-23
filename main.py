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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.ehr import get_fhir_server
from src.soap import SOAPGenerator, SOAPNote, EnhancedSOAPNote
from src.treatment import get_treatment_service
from src.monitoring import get_discharge_monitor
from src.auth.prior_auth import get_prior_auth_service
from src.pubmed import get_synthesis_agent

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

# New services (initialised in lifespan once fhir_server is ready)
treatment_service = None
discharge_monitor = None
prior_auth_service = None
pubmed_agent = None

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
    global fhir_server, soap_generator, treatment_service, discharge_monitor, prior_auth_service, pubmed_agent
    
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

    # Initialize new feature services (depend on fhir_server being ready)
    treatment_service = get_treatment_service(fhir_server)
    discharge_monitor = get_discharge_monitor(fhir_server)
    prior_auth_service = get_prior_auth_service(fhir_server)
    pubmed_agent = get_synthesis_agent()   # MedGemma reference injected later in load_models_lazy
    logger.info("Treatment summary, discharge monitoring, prior auth, and PubMed synthesis services initialized")

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


# ── PubMed background task helper ─────────────────────────────────────────────

def _run_pubmed_background(
    session_id: str,
    soap_note,
    transcription: str,
    patient_context: dict | None,
) -> None:
    """
    Synchronous worker called via FastAPI BackgroundTasks after SOAP generation.
    Runs all three PubMed synthesis modes and stores results in the session dict.
    Called in a thread pool so it never blocks the event loop.
    """
    if session_id not in sessions:
        return

    try:
        assessment = getattr(soap_note, "assessment", "") or ""
        plan = getattr(soap_note, "plan", "") or ""

        medications: list[str] = []
        if patient_context and isinstance(patient_context, dict):
            for m in patient_context.get("medications", []):
                name = m.get("name", "") if isinstance(m, dict) else str(m)
                if name:
                    medications.append(name)

        # Extract symptoms from transcription + subjective
        subjective = getattr(soap_note, "subjective", "") or ""
        combined_text = f"{transcription} {subjective}".lower()
        symptom_vocab = [
            "cough", "dyspnea", "shortness of breath", "wheezing", "chest pain",
            "fever", "fatigue", "weight loss", "nausea", "vomiting", "headache",
            "dizziness", "palpitations", "edema", "rash", "pain", "syncope",
            "weakness", "numbness", "tingling", "abdominal pain",
        ]
        symptoms = [s for s in symptom_vocab if s in combined_text]

        # Derive atypical markers: symptoms present but rare for the chief diagnosis
        # Simple heuristic: short symptom list means presentation may be unusual
        atypical = symptoms[3:] if len(symptoms) > 3 else []
        common = symptoms[:3] if len(symptoms) >= 3 else symptoms

        results: dict = {}

        # Case Matcher
        if symptoms:
            try:
                r = pubmed_agent.case_matcher(
                    common_symptoms=common or symptoms,
                    atypical_markers=atypical,
                    max_results=4,
                )
                results["case_matcher"] = r.to_dict()
            except Exception as e:
                logger.warning("PubMed case_matcher failed: %s", e)
                results["case_matcher"] = {"error": str(e)}

        # EBM Validator
        if assessment or plan:
            try:
                r = pubmed_agent.ebm_validator(
                    assessment=assessment,
                    plan=plan,
                    max_results=4,
                    date_years_back=2,
                )
                results["ebm_validator"] = r.to_dict()
            except Exception as e:
                logger.warning("PubMed ebm_validator failed: %s", e)
                results["ebm_validator"] = {"error": str(e)}

        # DDI Monitor (only if patient has ≥ 2 medications)
        if len(medications) >= 2:
            try:
                r = pubmed_agent.ddi_monitor(
                    current_medications=medications,
                    max_results_per_pair=1,
                    date_years_back=3,
                )
                results["ddi_monitor"] = r.to_dict()
            except Exception as e:
                logger.warning("PubMed ddi_monitor failed: %s", e)
                results["ddi_monitor"] = {"error": str(e)}

        sessions[session_id]["pubmed_insights"] = {
            "status": "completed",
            "results": results,
        }
        logger.info("PubMed analysis completed for session %s", session_id)

    except Exception as e:
        logger.error("PubMed background task failed for session %s: %s", session_id, e)
        sessions[session_id]["pubmed_insights"] = {
            "status": "error",
            "error": str(e),
        }


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
async def generate_soap(
    session_id: str,
    background_tasks: BackgroundTasks,
    chief_complaint: str = Form(""),
):
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

            # Extract clinical orders for HITL approval
            pending_orders = soap_generator.extract_clinical_orders(enhanced_soap, transcription)
            session["pending_orders"] = pending_orders

            # Schedule PubMed literature analysis in background (non-blocking)
            session["pubmed_insights"] = {"status": "running"}
            background_tasks.add_task(
                _run_pubmed_background,
                session_id=session_id,
                soap_note=enhanced_soap,
                transcription=transcription,
                patient_context=patient_context,
            )

            return {
                "status": "generated",
                "soap": enhanced_soap.to_dict(),
                "soap_html": enhanced_soap.to_html(),
                "alerts": enhanced_soap.critical_alerts,
                "drug_interactions": enhanced_soap.drug_interactions,
                "differentials": enhanced_soap.differentials,
                "pending_orders": pending_orders,
                "pubmed_insights_status": "running",
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

    # Extract clinical orders for HITL approval
    pending_orders = soap_generator.extract_clinical_orders(enhanced_soap, transcription)
    session["pending_orders"] = pending_orders

    # Schedule PubMed literature analysis in background (non-blocking)
    session["pubmed_insights"] = {"status": "running"}
    background_tasks.add_task(
        _run_pubmed_background,
        session_id=session_id,
        soap_note=enhanced_soap,
        transcription=transcription,
        patient_context=patient_context,
    )

    return {
        "status": "generated",
        "soap": enhanced_soap.to_dict(),
        "soap_html": enhanced_soap.to_html(),
        "alerts": enhanced_soap.critical_alerts,
        "drug_interactions": enhanced_soap.drug_interactions,
        "differentials": enhanced_soap.differentials,
        "pending_orders": pending_orders,
        "pubmed_insights_status": "running",
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

    # ── Generate & store treatment summary ───────────────────────────────────
    summary_data: dict = {}
    try:
        summary = treatment_service.generate_and_store(
            patient_id=session["patient_id"],
            session=session,
        )
        session["treatment_summary"] = summary.to_dict()
        summary_data = summary.to_dict()
        logger.info(f"Treatment summary {summary.summary_id} generated for patient {session['patient_id']}")
    except Exception as e:
        logger.warning(f"Treatment summary generation failed (non-fatal): {e}")

    # ── Auto-detect prior auth requirements from pending orders ───────────────
    pa_requests: list[dict] = []
    try:
        all_orders = session.get("pending_orders", {})
        combined_orders = (
            all_orders.get("lab_orders", [])
            + all_orders.get("imaging_orders", [])
            + all_orders.get("medications", [])
            + all_orders.get("referrals", [])
        )
        if combined_orders:
            indication = getattr(soap_note, "assessment", "") or ""
            pa_list = prior_auth_service.detect_and_create(
                patient_id=session["patient_id"],
                encounter_id=session_id,
                orders=combined_orders,
                clinical_indication=indication,
            )
            pa_requests = [p.to_dict() for p in pa_list]
            if pa_requests:
                logger.info(f"Auto-created {len(pa_requests)} prior auth request(s) for encounter {session_id}")
    except Exception as e:
        logger.warning(f"Prior auth auto-detection failed (non-fatal): {e}")

    return {
        "status": "approved",
        "ehr_update": result,
        "treatment_summary": summary_data,
        "prior_auth_requests": pa_requests,
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
    
    council = get_diagnostic_council(agent=agent, num_rollouts=num_rollouts, pubmed_agent=pubmed_agent)
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
    council = get_diagnostic_council(agent=agent, pubmed_agent=pubmed_agent)
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

    # ── Optional PubMed context enrichment ───────────────────────────────────
    pubmed_context: dict | None = None
    if pubmed_agent is not None:
        try:
            msg_lower = message.lower()

            # Detect intent from message keywords
            ddi_keywords   = {"interaction", "drug interaction", "drug-drug", "combine", "combining"}
            ebm_keywords   = {"treatment", "guideline", "therapy", "efficacy", "evidence", "management",
                              "recommend", "first-line", "second-line"}
            zebra_keywords = {"diagnosis", "diagnose", "rare", "unusual", "zebra", "atypical",
                              "differential", "rule out", "what could"}

            is_ddi   = any(k in msg_lower for k in ddi_keywords)
            is_ebm   = any(k in msg_lower for k in ebm_keywords)
            is_zebra = any(k in msg_lower for k in zebra_keywords)

            if is_ddi and patient_context and isinstance(patient_context, dict):
                # Run DDI scan on the patient's medications
                meds: list[str] = []
                for m in patient_context.get("medications", []):
                    name = m.get("name", "") if isinstance(m, dict) else str(m)
                    if name:
                        meds.append(name)
                if len(meds) >= 2:
                    res = pubmed_agent.ddi_monitor(
                        current_medications=meds,
                        max_results_per_pair=1,
                        date_years_back=3,
                    )
                    pubmed_context = {
                        "mode": "ddi_monitor",
                        "summary": res.summary,
                        "ddi_alerts": res.ddi_alerts,
                        "key_findings": res.key_findings[:4],
                        "citation_list": res.citation_list[:4],
                    }
            elif is_ebm:
                # EBM: use the raw message as assessment proxy
                res = pubmed_agent.ebm_validator(
                    assessment=message[:300],
                    plan="",
                    max_results=3,
                    date_years_back=2,
                )
                pubmed_context = {
                    "mode": "ebm_validator",
                    "summary": res.summary,
                    "divergences": res.divergences,
                    "key_findings": res.key_findings[:4],
                    "citation_list": res.citation_list[:4],
                }
            elif is_zebra or (not is_ddi and not is_ebm):
                # Case matcher: extract symptom-like words from the message
                symptom_vocab = [
                    "cough", "dyspnea", "shortness of breath", "wheezing", "chest pain",
                    "fever", "fatigue", "weight loss", "nausea", "vomiting", "headache",
                    "dizziness", "palpitations", "edema", "rash", "pain", "syncope",
                    "weakness", "numbness", "tingling", "abdominal pain",
                ]
                found_symptoms = [s for s in symptom_vocab if s in msg_lower]
                if found_symptoms:
                    res = pubmed_agent.case_matcher(
                        common_symptoms=found_symptoms[:3],
                        atypical_markers=found_symptoms[3:],
                        max_results=3,
                    )
                    pubmed_context = {
                        "mode": "case_matcher",
                        "summary": res.summary,
                        "rare_diagnoses": res.rare_diagnoses,
                        "key_findings": res.key_findings[:4],
                        "citation_list": res.citation_list[:4],
                    }
        except Exception as _pm_e:
            logger.debug("AI portal PubMed enrichment failed (non-fatal): %s", _pm_e)

    return {"response": response_text, "simulated": agent is None, "pubmed_context": pubmed_context}


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


# ══════════════════════════════════════════════════════════════════════════════
# Treatment Summary routes
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/patients/{patient_id}/treatment-summaries")
async def get_treatment_summaries(patient_id: str):
    """Return all treatment summaries for a patient (newest first)."""
    summaries = treatment_service.get_summaries(patient_id)
    return {"patient_id": patient_id, "summaries": summaries, "count": len(summaries)}


@app.get("/api/encounters/{session_id}/treatment-summary")
async def get_encounter_treatment_summary(session_id: str):
    """Return the treatment summary generated for a specific encounter."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    summary = sessions[session_id].get("treatment_summary")
    if not summary:
        raise HTTPException(status_code=404, detail="Treatment summary not available — has the encounter been approved?")
    return summary


@app.post("/api/treatment-cases/search")
async def search_similar_cases(body: dict):
    """
    Search anonymised treatment cases similar to given diagnosis keywords.
    Body: {"keywords": ["hypertension", "diabetes"], "max_results": 5}
    """
    keywords = body.get("keywords", [])
    max_results = min(int(body.get("max_results", 5)), 20)
    cases = treatment_service.find_similar_cases(keywords, max_results)
    return {"cases": cases, "count": len(cases)}


# ══════════════════════════════════════════════════════════════════════════════
# Lab order HITL approval routes
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/encounters/{session_id}/pending-orders")
async def get_pending_orders(session_id: str):
    """Return orders extracted from the SOAP note awaiting physician approval."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "pending_orders": sessions[session_id].get("pending_orders", {}),
    }


@app.post("/api/encounters/{session_id}/orders/approve")
async def approve_orders(session_id: str, body: dict):
    """
    Physician approves a subset of extracted orders.
    Body: {"approved": {"lab_orders": [...], "imaging_orders": [...], "medications": [...]}}
    Approved orders replace pending_orders in the session.
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    approved = body.get("approved", {})
    sessions[session_id]["approved_orders"] = approved
    sessions[session_id]["pending_orders"] = approved
    return {"status": "orders_approved", "approved_orders": approved}


# ══════════════════════════════════════════════════════════════════════════════
# Post-discharge monitoring routes
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/patients/{patient_id}/discharge-plan")
async def create_discharge_plan(patient_id: str, body: dict):
    """
    Physician creates a post-discharge monitoring plan.
    Body: {
      "encounter_id": "session_id",
      "instructions": "...",
      "monitor_days": 14,
      "thresholds": { ... optional overrides ... },
      "notify_on_warning": true,
      "notify_on_critical": true
    }
    """
    encounter_id = body.get("encounter_id", "")
    instructions = body.get("instructions", "")
    if not instructions:
        raise HTTPException(status_code=400, detail="instructions is required")

    plan = discharge_monitor.create_plan(
        patient_id=patient_id,
        encounter_id=encounter_id,
        instructions=instructions,
        monitor_days=int(body.get("monitor_days", 14)),
        thresholds=body.get("thresholds"),
        notify_on_warning=bool(body.get("notify_on_warning", True)),
        notify_on_critical=bool(body.get("notify_on_critical", True)),
    )
    return {"status": "created", "plan": plan.to_dict()}


@app.get("/api/patients/{patient_id}/discharge-plan")
async def get_discharge_plan(patient_id: str):
    """Return the active discharge monitoring plan for a patient."""
    plan = discharge_monitor.get_active_plan(patient_id)
    if plan is None:
        return {"active_plan": None, "message": "No active discharge monitoring plan"}
    return {"active_plan": plan}


@app.post("/api/patients/{patient_id}/vitals")
async def submit_vitals(patient_id: str, body: dict):
    """
    Patient submits vitals readings for post-discharge monitoring.
    Body: {
      "vitals": {"systolic_bp": 145, "heart_rate": 88, "oxygen_saturation": 95},
      "notes": "Felt slightly dizzy this morning"
    }
    Returns immediate alert feedback.
    """
    vitals = body.get("vitals", {})
    if not vitals:
        raise HTTPException(status_code=400, detail="vitals object is required")

    for k, v in list(vitals.items()):
        try:
            vitals[k] = float(v)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"Non-numeric value for {k}")

    submission = discharge_monitor.submit_vitals(
        patient_id=patient_id,
        vitals=vitals,
        notes=body.get("notes", ""),
    )
    return submission.to_dict()


@app.get("/api/patients/{patient_id}/vitals")
async def get_vitals_history(patient_id: str):
    """Return all vitals submissions for a patient (newest first)."""
    return {
        "patient_id": patient_id,
        "submissions": discharge_monitor.get_vitals_history(patient_id),
    }


@app.get("/api/patients/{patient_id}/discharge-alerts")
async def get_discharge_alerts(patient_id: str):
    """Return unresolved discharge alerts for care team review."""
    return {
        "patient_id": patient_id,
        "alerts": discharge_monitor.get_pending_alerts(patient_id),
    }


@app.post("/api/patients/{patient_id}/discharge-alerts/{submission_id}/resolve")
async def resolve_discharge_alert(patient_id: str, submission_id: str):
    """Care team resolves a discharge alert."""
    ok = discharge_monitor.resolve_alert(patient_id, submission_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "resolved", "submission_id": submission_id}


# ══════════════════════════════════════════════════════════════════════════════
# Prior authorization routes
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/patients/{patient_id}/prior-auth")
async def create_prior_auth(patient_id: str, body: dict):
    """
    Manually create a prior authorization request.
    Body: {
      "encounter_id": "...",
      "service_type": "lab|imaging|medication|procedure|specialist_referral",
      "service_description": "MRI brain with contrast",
      "clinical_indication": "...",
      "urgency": "routine|urgent|emergency",
      "auto_submit": true
    }
    """
    service_description = body.get("service_description", "")
    clinical_indication = body.get("clinical_indication", "")
    if not service_description or not clinical_indication:
        raise HTTPException(status_code=400, detail="service_description and clinical_indication are required")

    req = prior_auth_service.create(
        patient_id=patient_id,
        encounter_id=body.get("encounter_id", ""),
        service_type=body.get("service_type", "procedure"),
        service_description=service_description,
        clinical_indication=clinical_indication,
        urgency=body.get("urgency", "routine"),
        auto_submit=bool(body.get("auto_submit", True)),
    )
    return {"status": "created", "prior_auth": req.to_dict()}


@app.get("/api/patients/{patient_id}/prior-auth")
async def list_prior_auths(patient_id: str, status: str | None = None):
    """List prior authorization requests for a patient. Optional ?status=pending filter."""
    if status == "pending":
        requests = prior_auth_service.get_pending(patient_id)
    else:
        requests = prior_auth_service.get_all(patient_id)
    return {"patient_id": patient_id, "requests": requests, "count": len(requests)}


@app.get("/api/patients/{patient_id}/prior-auth/{auth_id}")
async def get_prior_auth(patient_id: str, auth_id: str):
    """Get a specific prior authorization request."""
    req = prior_auth_service.get_by_id(patient_id, auth_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Prior auth request not found")
    return req


@app.post("/api/patients/{patient_id}/prior-auth/{auth_id}/status")
async def update_prior_auth_status(patient_id: str, auth_id: str, body: dict):
    """
    Update the status of a prior auth request.
    Body: {
      "action": "submit|approve|deny|pending|more_info",
      "notes": "...",
      "insurer_ref": "...",
      "approved_by": "...",
      "denial_reason": "...",
    }
    """
    action = body.get("action", "").lower()
    notes = body.get("notes", "")

    action_map = {
        "submit": lambda: prior_auth_service.submit(patient_id, auth_id, notes),
        "pending": lambda: prior_auth_service.mark_pending(patient_id, auth_id, body.get("insurer_ref", ""), notes),
        "approve": lambda: prior_auth_service.approve(patient_id, auth_id, body.get("approved_by", ""), notes),
        "deny": lambda: prior_auth_service.deny(patient_id, auth_id, body.get("denial_reason", notes or "No reason provided"), notes),
        "more_info": lambda: prior_auth_service.request_more_info(patient_id, auth_id, notes),
    }

    handler = action_map.get(action)
    if handler is None:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action!r}. Use: submit|approve|deny|pending|more_info")

    result = handler()
    if result is None:
        raise HTTPException(status_code=404, detail="Prior auth request not found")
    return result


@app.post("/api/patients/{patient_id}/prior-auth/{auth_id}/doc")
async def add_prior_auth_doc(patient_id: str, auth_id: str, body: dict):
    """Attach a supporting document (text) to a prior auth request. Body: {"doc_text": "..."}"""
    doc_text = body.get("doc_text", "").strip()
    if not doc_text:
        raise HTTPException(status_code=400, detail="doc_text is required")
    ok = prior_auth_service.add_supporting_doc(patient_id, auth_id, doc_text)
    if not ok:
        raise HTTPException(status_code=404, detail="Prior auth request not found")
    return {"status": "added"}


@app.get("/api/encounters/{session_id}/prior-auth")
async def get_encounter_prior_auths(session_id: str):
    """Return all prior auth requests linked to a specific encounter."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    patient_id = sessions[session_id]["patient_id"]
    requests = prior_auth_service.get_by_encounter(patient_id, session_id)
    return {"session_id": session_id, "requests": requests, "count": len(requests)}


# ══════════════════════════════════════════════════════════════════════════════
# PubMed synthesis routes
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/encounters/{session_id}/pubmed-insights")
async def get_pubmed_insights(session_id: str):
    """
    Poll for the PubMed background analysis triggered after SOAP generation.
    Returns status: 'running' | 'completed' | 'error' with results when done.
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    insights = sessions[session_id].get("pubmed_insights")
    if insights is None:
        return {"status": "not_started", "message": "Generate a SOAP note first to trigger PubMed analysis."}
    return {"session_id": session_id, **insights}


@app.post("/api/pubmed/search")
async def pubmed_search(request: Request):
    """
    Direct PubMed search in one of three modes.

    Body:
      mode: 'case_matcher' | 'ebm_validator' | 'ddi_monitor'
      --- case_matcher ---
      symptoms: list[str]
      atypical_markers: list[str]  (optional)
      max_results: int             (default 5)
      --- ebm_validator ---
      assessment: str
      plan: str
      max_results: int
      date_years_back: int         (default 2)
      --- ddi_monitor ---
      medications: list[str]
      new_medications: list[str]   (optional)
      max_results_per_pair: int    (default 2)
      date_years_back: int         (default 3)
    """
    data = await request.json()
    mode = data.get("mode", "")

    if mode not in ("case_matcher", "ebm_validator", "ddi_monitor"):
        raise HTTPException(
            status_code=400,
            detail="mode must be one of: case_matcher, ebm_validator, ddi_monitor"
        )

    try:
        if mode == "case_matcher":
            symptoms = data.get("symptoms", [])
            if not symptoms:
                raise HTTPException(status_code=400, detail="symptoms list is required for case_matcher")
            result = pubmed_agent.case_matcher(
                common_symptoms=symptoms,
                atypical_markers=data.get("atypical_markers", []),
                max_results=int(data.get("max_results", 5)),
            )
        elif mode == "ebm_validator":
            assessment = data.get("assessment", "")
            plan = data.get("plan", "")
            if not assessment and not plan:
                raise HTTPException(status_code=400, detail="assessment or plan is required for ebm_validator")
            result = pubmed_agent.ebm_validator(
                assessment=assessment,
                plan=plan,
                max_results=int(data.get("max_results", 5)),
                date_years_back=int(data.get("date_years_back", 2)),
            )
        else:  # ddi_monitor
            medications = data.get("medications", [])
            if not medications:
                raise HTTPException(status_code=400, detail="medications list is required for ddi_monitor")
            result = pubmed_agent.ddi_monitor(
                current_medications=medications,
                new_medications=data.get("new_medications"),
                max_results_per_pair=int(data.get("max_results_per_pair", 2)),
                date_years_back=int(data.get("date_years_back", 3)),
            )
        return result.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PubMed search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pubmed/zebra-hunt")
async def pubmed_zebra_hunt(request: Request):
    """
    Zebra Hunt — find rare diagnoses matching an unusual symptom cluster.

    Body:
      common_symptoms: list[str]   e.g. ["cough", "fatigue"]
      atypical_markers: list[str]  e.g. ["tongue discoloration", "night sweats"]
      patient_age: int             (optional)
      patient_gender: str          (optional, "male"/"female")
      max_results: int             (default 5)
    """
    data = await request.json()
    common = data.get("common_symptoms", [])
    atypical = data.get("atypical_markers", [])
    if not common and not atypical:
        raise HTTPException(status_code=400, detail="common_symptoms or atypical_markers required")
    try:
        result = pubmed_agent.case_matcher(
            common_symptoms=common,
            atypical_markers=atypical,
            patient_age=data.get("patient_age"),
            patient_gender=data.get("patient_gender"),
            max_results=int(data.get("max_results", 5)),
        )
        return result.to_dict()
    except Exception as e:
        logger.error(f"Zebra hunt failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pubmed/validate-plan")
async def pubmed_validate_plan(request: Request):
    """
    EBM Validator — cross-check a physician's plan against recent guidelines.

    Body:
      assessment: str              SOAP Assessment section text
      plan: str                    SOAP Plan section text
      max_results: int             (default 5)
      date_years_back: int         (default 2)
    """
    data = await request.json()
    assessment = data.get("assessment", "")
    plan = data.get("plan", "")
    if not assessment and not plan:
        raise HTTPException(status_code=400, detail="assessment or plan is required")
    try:
        result = pubmed_agent.ebm_validator(
            assessment=assessment,
            plan=plan,
            max_results=int(data.get("max_results", 5)),
            date_years_back=int(data.get("date_years_back", 2)),
        )
        return result.to_dict()
    except Exception as e:
        logger.error(f"EBM validation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/pubmed/ddi-monitor/{patient_id}")
async def pubmed_ddi_monitor(
    patient_id: str,
    new_med: str | None = None,
    date_years_back: int = 3,
):
    """
    DDI Monitor — scan PubMed for novel drug-drug interactions for a patient.

    Query params:
      new_med:          Optional new medication being added (triggers priority scan)
      date_years_back:  Recency window (default 3 years)
    """
    patient_summary = fhir_server.get_patient_summary(patient_id)
    if patient_summary is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    medications: list[str] = []
    for m in patient_summary.get("medications", []):
        name = m.get("name", "") if isinstance(m, dict) else str(m)
        if name:
            medications.append(name)

    if len(medications) < 2 and not new_med:
        return {
            "patient_id": patient_id,
            "message": "Patient has fewer than 2 medications — DDI scan skipped.",
            "medications": medications,
        }

    new_meds = [new_med] if new_med else None
    try:
        result = pubmed_agent.ddi_monitor(
            current_medications=medications,
            new_medications=new_meds,
            max_results_per_pair=2,
            date_years_back=date_years_back,
        )
        return {"patient_id": patient_id, "medications_scanned": medications, **result.to_dict()}
    except Exception as e:
        logger.error(f"DDI monitor failed for {patient_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    
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
