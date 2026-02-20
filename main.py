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

# Store active sessions
sessions: dict[str, dict] = {}


def load_models_lazy():
    """Load models only when first needed (lazy loading)."""
    global agent, asr
    
    # Check environment flags
    use_simulated = os.environ.get("SIMULATED_MODE", "false").lower() == "true"
    use_vllm = os.environ.get("USE_VLLM", "false").lower() == "true"
    
    if agent is None:
        if use_simulated:
            logger.info("Running in SIMULATED mode - no GPU models loaded")
            agent = None  # Will use mock responses
        elif use_vllm:
            # Try vLLM backend (faster)
            try:
                from src.agent import MedGemmaVLLMAgent, is_vllm_available
                if is_vllm_available():
                    logger.info("Loading MedGemma with vLLM backend...")
                    agent = MedGemmaVLLMAgent()
                else:
                    raise ImportError("vLLM not available")
            except Exception as e:
                logger.warning(f"vLLM failed: {e}. Falling back to Transformers.")
                from src.agent import MedGemmaAgent
                agent = MedGemmaAgent(load_in_4bit=True)
        else:
            # Default: HuggingFace Transformers with 4-bit quantization
            try:
                from src.agent import MedGemmaAgent
                agent = MedGemmaAgent(load_in_4bit=True)
            except Exception as e:
                logger.warning(f"Could not load MedGemma: {e}. Using simulated mode.")
    
    if asr is None:
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
    
    # Initialize FHIR server and SOAP generator (lightweight, always load)
    fhir_server = get_fhir_server()
    soap_generator = SOAPGenerator()
    
    logger.info("FHIR server and SOAP generator initialized")
    logger.info("Models will load on first request (lazy loading)")
    
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
    
    patient = fhir_server.get_patient_summary(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "patient_id": patient_id,
        "patient_context": patient,
        "transcription": "",
        "image_path": None,
        "image_modality": None,
        "soap_note": None,
        "status": "active"
    }
    
    return {
        "session_id": session_id,
        "patient": patient,
        "status": "active"
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
            
            # Generate enhanced SOAP with clinical intelligence
            enhanced_soap = soap_generator.generate_enhanced_soap(
                transcription=transcription,
                patient_context=patient_context,
                image_findings=image_findings,
                raw_soap_text=result["soap_note"]
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
            logger.error(f"SOAP generation failed: {e}")
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
    
    # Accumulator for transcription
    full_transcription = []
    
    def on_transcription(text: str):
        """Callback for new transcription chunks."""
        full_transcription.append(text)
        sessions[session_id]["transcription"] = " ".join(full_transcription)
    
    # Start ASR listening
    if asr is not None:
        asr.start_listening(on_transcription)
    
    try:
        while True:
            # Receive audio data
            data = await websocket.receive_bytes()
            
            if asr is not None:
                # Add audio to ASR processing queue
                asr.add_audio_bytes(data, sample_rate=16000)
            
            # Send back current transcription
            await websocket.send_json({
                "type": "transcription",
                "text": sessions[session_id].get("transcription", "")
            })
            
    except WebSocketDisconnect:
        logger.info(f"Audio WebSocket disconnected for session {session_id}")
    finally:
        if asr is not None:
            asr.stop_listening()


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


# History API endpoints
@app.get("/api/history/{patient_id}/timeline")
async def get_patient_timeline(patient_id: str, days: int = 365):
    """Get patient history timeline."""
    from src.history import get_history_service
    
    history_service = get_history_service()
    timeline = history_service.get_patient_timeline(patient_id, days)
    
    # Get patient info
    patient_summary = fhir_server.get_patient_summary(patient_id)
    patient_info = None
    if patient_summary:
        patient_info = {
            "id": patient_id,
            "name": patient_summary.get("name", "Unknown"),
            "age": patient_summary.get("age", "Unknown"),
            "gender": patient_summary.get("gender", "Unknown")
        }
    
    return {"patient": patient_info, "timeline": timeline}


@app.get("/api/history/{patient_id}/medications")
async def get_patient_medications(patient_id: str):
    """Get patient medication history."""
    from src.history import get_history_service
    history_service = get_history_service()
    return {"medications": history_service.get_medication_history(patient_id)}


@app.get("/api/history/{patient_id}/imaging")
async def get_patient_imaging(patient_id: str, modality: str = None):
    """Get patient imaging studies."""
    from src.history import get_history_service
    history_service = get_history_service()
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
    
    council = get_diagnostic_council(num_rollouts=num_rollouts)
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
    council = get_diagnostic_council()
    return {"deliberations": council.get_deliberation_history()}


# Patient Portal API endpoints
@app.get("/api/portal/{patient_id}/summary")
async def get_portal_summary(patient_id: str):
    """Get patient appointment summary for portal."""
    from src.portal import get_patient_assistant
    assistant = get_patient_assistant()
    return assistant.get_appointment_summary(patient_id)


@app.post("/api/portal/ask")
async def portal_ask_question(request: Request):
    """Ask a question in patient portal."""
    from src.portal import get_patient_assistant
    
    data = await request.json()
    patient_id = data.get("patient_id", "P001")
    question = data.get("question", "")
    
    assistant = get_patient_assistant()
    query = assistant.ask(patient_id, question)
    
    return query.to_dict()


@app.get("/api/portal/{patient_id}/history")
async def get_portal_query_history(patient_id: str):
    """Get patient query history."""
    from src.portal import get_patient_assistant
    assistant = get_patient_assistant()
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
        "asr_loaded": asr is not None,
        "fhir_server": fhir_server is not None,
        "mem0_available": is_mem0_available()
    }


if __name__ == "__main__":
    import uvicorn
    
    # Check for simulated mode flag
    if "--simulated" in sys.argv:
        os.environ["SIMULATED_MODE"] = "true"
        print("Running in SIMULATED mode (no GPU models)")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
