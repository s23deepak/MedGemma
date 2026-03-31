"""
MedGemma Clinical Assistant - Main Application
FastAPI server for the AI-powered clinical decision support system.
"""

import argparse
import asyncio
import base64
import json
import logging
import os
import sys
import uvicorn
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.ehr import get_fhir_server, FirestoreFHIRServer
from src.soap import SOAPGenerator, SOAPNote, EnhancedSOAPNote
from src.treatment import get_treatment_service
from src.monitoring import get_discharge_monitor
from src.auth.prior_auth import get_prior_auth_service
from src.pubmed import get_synthesis_agent
from src.shift import get_shift_brief_service
from src.referral import get_referral_letter_service
from src.simulation import get_simulation_engine, list_cases as list_sim_cases
from src.trends import get_local_health_trends_service
from src.inpatient import (
    get_rounding_service,
    get_sbar_service,
    get_safety_service,
    get_discharge_planner,
)
from src.audit.audit_logger import get_audit_logger
from src.monitoring.perf_tracker import track_perf, get_stats as get_perf_stats
from src.config.hospital_config import get_hospital_registry, Hospital
from src.rare_disease import get_rare_disease_director, RareCaseInput

# Production hardening: async, monitoring, rate limiting, circuit breakers
from src.production.metrics import MetricsCollector, RequestMetricsMiddleware
from src.production.circuit_breaker import init_circuit_breakers, get_circuit_breaker_registry
from src.production.rate_limiter import RateLimitConfig, get_limiter

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
shift_brief_service = None
referral_service = None
simulation_engine = None
local_trends_service = None
trends_refresh_task: asyncio.Task | None = None

# Inpatient services
rounding_service = None
sbar_service = None
safety_service = None
discharge_planner = None

# Cross-cutting services
audit_logger = None
hospital_registry = None

# Rare disease director (TTT-inspired iterative diagnostic hunt)
rare_disease_director = None

# Store active sessions
sessions: dict[str, dict] = {}


def _extract_symptoms_for_trends(text: str) -> list[str]:
    """Extract high-signal symptom keywords for local trend correlation."""
    symptom_vocab = [
        "cough", "dyspnea", "shortness of breath", "wheezing", "chest pain",
        "fever", "chills", "fatigue", "nausea", "vomiting", "diarrhea",
        "headache", "dizziness", "rash",
    ]
    text_lower = (text or "").lower()
    return [symptom for symptom in symptom_vocab if symptom in text_lower]


async def _refresh_local_trends_loop():
    """Refresh trend cache for known patient/session locations every 12 hours."""
    while True:
        try:
            if local_trends_service is not None and fhir_server is not None:
                locations: set[str] = set()

                # Active session locations
                for session in sessions.values():
                    patient_location = ((session.get("patient_context") or {}).get("patient") or {}).get("location")
                    if patient_location:
                        locations.add(str(patient_location))

                # Known patient locations from EHR
                try:
                    for patient in fhir_server.list_patients():
                        patient_id = patient.get("id")
                        if not patient_id:
                            continue
                        summary = fhir_server.get_patient_summary(patient_id)
                        if summary:
                            location = (summary.get("patient") or {}).get("location")
                            if location:
                                locations.add(str(location))
                except Exception as exc:
                    logger.warning("Trend refresh patient scan failed: %s", exc)

                for location in locations:
                    try:
                        local_trends_service.refresh_location_trends(location=location)
                    except Exception as exc:
                        logger.warning("Trend refresh failed for %s: %s", location, exc)

                if locations:
                    logger.info("Local trend cache refreshed for %d location(s)", len(locations))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Local trend background refresh failed: %s", exc)

        await asyncio.sleep(60 * 60 * 12)


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
        elif os.environ.get("GEMINI_API_KEY"):
            # ── Gemini Cloud API: fast inference, no GPU required ──
            try:
                from src.agent.gemini_agent import GeminiAgent
                gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
                agent = GeminiAgent(
                    api_key=os.environ["GEMINI_API_KEY"],
                    model_name=gemini_model,
                )
                logger.info(f"Using Gemini Cloud API ({gemini_model})")
            except ImportError:
                logger.warning(
                    "google-generativeai not installed. "
                    "Run: uv pip install 'medgemma-assistant[gemini]'. "
                    "Falling back to local model."
                )
                # Fall through to vLLM or Transformers below
                if use_vllm:
                    try:
                        from src.agent.vllm_manager import get_vllm_manager, is_vllm_manager_available
                        if is_vllm_manager_available():
                            vllm_manager = get_vllm_manager()
                            agent = vllm_manager
                        else:
                            raise ImportError("vLLM not available")
                    except Exception as e:
                        logger.warning(f"VLLMModelManager failed: {e}. Falling back to Transformers.")
                        from src.agent import MedGemmaAgent
                        agent = MedGemmaAgent(load_in_4bit=True)
                else:
                    from src.agent import MedGemmaAgent
                    agent = MedGemmaAgent(load_in_4bit=True)
            except Exception as e:
                logger.error(f"Gemini initialization failed: {e}. Falling back to local model.")
                if use_vllm:
                    try:
                        from src.agent.vllm_manager import get_vllm_manager, is_vllm_manager_available
                        if is_vllm_manager_available():
                            vllm_manager = get_vllm_manager()
                            agent = vllm_manager
                        else:
                            raise ImportError("vLLM not available")
                    except Exception as e2:
                        logger.warning(f"VLLMModelManager failed: {e2}. Falling back to Transformers.")
                        from src.agent import MedGemmaAgent
                        agent = MedGemmaAgent(load_in_4bit=True)
                else:
                    from src.agent import MedGemmaAgent
                    agent = MedGemmaAgent(load_in_4bit=True)
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
    global fhir_server, soap_generator, treatment_service, discharge_monitor, prior_auth_service, pubmed_agent, shift_brief_service, referral_service, simulation_engine, local_trends_service, trends_refresh_task
    global rounding_service, sbar_service, safety_service, discharge_planner
    global audit_logger, hospital_registry, rare_disease_director
    
    logger.info("Starting MedGemma Clinical Assistant...")

    # Initialize FHIR server — use MockFHIRServer in simulated mode, Firestore otherwise
    _simulated = os.environ.get("SIMULATED_MODE", "false").lower() in ("1", "true", "yes")
    if _simulated:
        from src.ehr.fhir_mock import MockFHIRServer
        fhir_server = MockFHIRServer()
        logger.info("Using Mock FHIR server (SIMULATED_MODE=true)")
    else:
        try:
            fhir_server = FirestoreFHIRServer()
            logger.info("Using Firestore-backed FHIR server")
        except RuntimeError:
            logger.critical(
                "Firebase is not configured. Place firebase-key.json in the project root "
                "or set the FIREBASE_KEY_PATH environment variable. "
                "See docs/firebase_setup.md for instructions."
            )
            raise SystemExit(1)
        except Exception as e:
            logger.critical(f"Firestore initialisation failed: {e}")
            raise
    
    soap_generator = SOAPGenerator()

    # Initialize new feature services (depend on fhir_server being ready)
    treatment_service = get_treatment_service(fhir_server)
    discharge_monitor = get_discharge_monitor(fhir_server)
    prior_auth_service = get_prior_auth_service(fhir_server)
    pubmed_agent = get_synthesis_agent()   # MedGemma reference injected later in load_models_lazy
    shift_brief_service = get_shift_brief_service(fhir_server)
    referral_service = get_referral_letter_service(fhir_server)
    simulation_engine = get_simulation_engine()
    local_trends_service = get_local_health_trends_service()
    rounding_service  = get_rounding_service(fhir_server)
    sbar_service      = get_sbar_service(fhir_server)
    safety_service    = get_safety_service(fhir_server)
    discharge_planner = get_discharge_planner(fhir_server)
    audit_logger = get_audit_logger()
    hospital_registry = get_hospital_registry()
    rare_disease_director = get_rare_disease_director()
    logger.info("Treatment summary, discharge monitoring, prior auth, PubMed synthesis, shift brief, referral letter, simulation, and inpatient services initialized")

    # Run 60-day hospital-case finalization in background (non-blocking)
    import asyncio
    asyncio.get_running_loop().run_in_executor(
        None, treatment_service.finalize_hospital_cases
    )

    # Refresh local health trends every 12 hours in background
    trends_refresh_task = asyncio.create_task(_refresh_local_trends_loop())

    logger.info("FHIR server and SOAP generator initialized")
    
    # Load AI models at startup so they're ready for all endpoints
    load_models_lazy()
    if agent is not None:
        logger.info(f"Agent loaded: {type(agent).__name__}")
        simulation_engine.set_agent(agent)
        rare_disease_director.agent = agent
        rare_disease_director.pubmed_agent = pubmed_agent
    else:
        logger.info("No agent loaded (simulated mode or model unavailable)")
    
    yield
    
    if trends_refresh_task is not None:
        trends_refresh_task.cancel()
        try:
            await trends_refresh_task
        except asyncio.CancelledError:
            pass

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


# ── Production Hardening Middleware ───────────────────────────────────────
# Add metrics collection middleware for request tracking
app.add_middleware(RequestMetricsMiddleware)

# Add rate limiting if slowapi is available
limiter = get_limiter()
if limiter is not None:
    app.state.limiter = limiter
    # Register rate limit exception handler
    from slowapi.errors import RateLimitExceeded
    from src.production.rate_limiter import rate_limit_exception_handler
    app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)
    logger.info("Rate limiting enabled")
else:
    logger.warning("Rate limiting disabled - slowapi not installed")

# Initialize circuit breakers
try:
    init_circuit_breakers()
    logger.info("Circuit breakers initialized")
except Exception as e:
    logger.warning(f"Failed to initialize circuit breakers: {e}")

# Start Prometheus metrics server on port 8001
MetricsCollector.start_prometheus_server(port=8001)



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
        "status": "active",
        "local_trend_insights": None,
    }

    patient_location = ((patient_summary.get("patient") or {}).get("location") or "").strip()
    if local_trends_service is not None and patient_location:
        try:
            local_trends_service.refresh_location_trends(location=patient_location)
        except Exception as exc:
            logger.warning("Initial trend prefetch failed for %s: %s", patient_location, exc)
    
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
    patient_location = ((patient_context or {}).get("patient") or {}).get("location", "")

    symptoms_for_trends = _extract_symptoms_for_trends(transcription)
    trend_insights = None
    trend_context = ""
    if local_trends_service is not None and patient_location and symptoms_for_trends:
        try:
            trend_insights = local_trends_service.correlate(
                location=patient_location,
                symptoms=symptoms_for_trends,
            )
            session["local_trend_insights"] = trend_insights

            if trend_insights.get("matched_signal_count", 0) > 0:
                top_signals = [
                    m.get("signal", {}).get("title", "")
                    for m in trend_insights.get("matched_signals", [])[:3]
                ]
                top_signals = [s for s in top_signals if s]
                if top_signals:
                    trend_context = (
                        f"\n\nLocal Health Context ({patient_location}): "
                        f"Recent trend signals potentially related to today's symptoms include: "
                        f"{' | '.join(top_signals)}. "
                        "Use as supportive exposure context only; require physician validation."
                    )
        except Exception as exc:
            logger.warning("Local trend correlation failed: %s", exc)
    
    if agent is not None:
        try:
            # Use MedGemma to process encounter
            result = agent.process_encounter(
                transcription=f"{transcription}{trend_context}",
                patient_context=patient_context,
                image_path=session.get("image_path"),
                image_modality=session.get("image_modality", "xray")
            )

            # result must be a dict; guard against agents that return plain text
            if not isinstance(result, dict):
                result = {"soap_note": str(result), "alerts": []}

            # Generate enhanced SOAP with clinical intelligence
            enhanced_soap = soap_generator.generate_enhanced_soap(
                transcription=f"{transcription}{trend_context}",
                patient_context=patient_context,
                image_findings=image_findings,
                raw_soap_text=result.get("soap_note")
            )
            session["soap_note"] = enhanced_soap

            if audit_logger:
                _pid = (session.get("patient_context") or {}).get("patient", {}).get("id")
                audit_logger.log("SOAP_GENERATED", "generate_soap", patient_id=_pid,
                                 details={"session_id": session_id})

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
                "local_trend_insights": trend_insights,
            }
        except Exception as e:
            import traceback
            logger.error(f"SOAP generation failed: {e}\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # Simulated mode - still use enhanced SOAP with clinical intelligence
    enhanced_soap = soap_generator.generate_enhanced_soap(
        transcription=(transcription or f"Patient presents with: {chief_complaint or 'symptoms as dictated'}.") + trend_context,
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
        "local_trend_insights": trend_insights,
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
            # Generate AI medical-necessity narrative for each PA request
            patient_context = session.get("patient_context") or {}
            for pa_req in pa_list:
                try:
                    prior_auth_service.generate_narrative(
                        pa_request=pa_req,
                        patient_context=patient_context,
                        soap_note=soap_note,
                        agent=agent,
                    )
                except Exception as _e:
                    logger.warning(f"PA narrative generation skipped for {pa_req.auth_id}: {_e}")
            pa_requests = [p.to_dict() for p in pa_list]
            if pa_requests:
                logger.info(f"Auto-created {len(pa_requests)} prior auth request(s) for encounter {session_id}")
    except Exception as e:
        logger.warning(f"Prior auth auto-detection failed (non-fatal): {e}")

    # ── Generate referral letters for any specialist referral orders ───────────
    referral_letters: list[dict] = []
    try:
        referral_orders = session.get("pending_orders", {}).get("referrals", [])
        if referral_orders:
            # Pull patient memories for inclusion in the letter
            memories: list[dict] = []
            try:
                from src.memory.patient_memory import get_patient_memory
                pm = get_patient_memory()
                raw = pm.get_all(session["patient_id"])
                memories = raw if isinstance(raw, list) else []
            except Exception:
                pass  # memories are optional

            # Infer referring provider name from session if available
            referring_provider = session.get("provider_name", "")

            letters = referral_service.generate_letters_for_encounter(
                patient_id=session["patient_id"],
                encounter_id=session_id,
                referral_orders=referral_orders,
                soap_note=soap_note,
                patient_context=session.get("patient_context") or {},
                memories=memories,
                referring_provider=referring_provider,
                agent=agent,
            )
            referral_letters = [ltr.to_dict() for ltr in letters]
            if referral_letters:
                logger.info(f"Generated {len(referral_letters)} referral letter(s) for encounter {session_id}")
    except Exception as e:
        logger.warning(f"Referral letter generation failed (non-fatal): {e}")

    return {
        "status": "approved",
        "ehr_update": result,
        "treatment_summary": summary_data,
        "prior_auth_requests": pa_requests,
        "referral_letters": referral_letters,
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


# ── Health & Status Endpoints (Production) ───────────────────────────────


@app.get("/api/health")
async def health_check():
    """Health check endpoint for load balancers."""
    return {
        "status": "healthy",
        "timestamp": asyncio.get_event_loop().time(),
        "services": {
            "fhir_server": "ready" if fhir_server else "unavailable",
            "agent": "ready" if agent else "unavailable",
            "pubmed_agent": "ready" if pubmed_agent else "unavailable",
        }
    }


@app.get("/api/status")
async def get_status():
    """Get detailed system status including circuit breaker state."""
    from src.production.circuit_breaker import get_circuit_breaker_registry
    registry = get_circuit_breaker_registry()

    return {
        "active_sessions": len(sessions),
        "circuit_breakers": registry.get_status(),
        "model_status": vllm_manager.get_status() if vllm_manager else "not_initialized",
        "services": {
            "fhir_server": bool(fhir_server),
            "audit_logger": bool(audit_logger),
            "treatment_service": bool(treatment_service),
            "shift_brief_service": bool(shift_brief_service),
        }
    }


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


@app.get("/shift-brief", response_class=HTMLResponse)
async def shift_brief_page(request: Request):
    """Pre-shift briefing page for clinical staff."""
    return templates.TemplateResponse("shift_brief.html", {"request": request})


@app.post("/api/shift-brief")
async def api_shift_brief(payload: dict):
    """
    Generate a pre-shift briefing for a clinical provider.

    Body: { "provider_name": str, "role": str }
    Returns: { provider_name, role, shift_date, patients, ai_summary }
    """
    if shift_brief_service is None:
        raise HTTPException(status_code=503, detail="Shift brief service not initialized")

    provider_name = payload.get("provider_name", "").strip()
    role = payload.get("role", "doctor").strip().lower()

    if not provider_name:
        raise HTTPException(status_code=400, detail="provider_name is required")

    brief = shift_brief_service.generate_brief(
        provider_name=provider_name,
        role=role,
        agent=agent,
    )
    return JSONResponse(content=brief)


# ══════════════════════════════════════════════════════════════════════════════
# Clinical Simulation routes
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/simulation", response_class=HTMLResponse)
async def simulation_page(request: Request):
    """Clinical simulation lab for resident training."""
    return templates.TemplateResponse("simulation.html", {"request": request})


# ══════════════════════════════════════════════════════════════════════════════
# Rare Disease Hunt routes
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/rare-disease", response_class=HTMLResponse)
async def rare_disease_page(request: Request):
    """TTT-inspired rare disease directional diagnostic hunt."""
    return templates.TemplateResponse("rare_disease.html", {"request": request})


@app.get("/api/simulation/cases")
async def api_sim_cases():
    """Return the list of available simulation cases."""
    return JSONResponse(content=list_sim_cases())


@app.post("/api/simulation/start")
async def api_sim_start(payload: dict):
    """
    Start a new simulation session.
    Body: { "resident_name": str, "case_id": str }
    Returns full session dict.
    """
    resident_name = payload.get("resident_name", "Resident").strip()
    case_id = payload.get("case_id", "").strip()
    if not case_id:
        raise HTTPException(status_code=400, detail="case_id is required")
    try:
        session = simulation_engine.start_session(resident_name, case_id)
        return JSONResponse(content=session.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/simulation/history")
async def api_sim_history(payload: dict):
    """
    Resident asks the simulated patient a history question.
    Body: { "session_id": str, "question": str }
    Returns: { "question": str, "response": str, "ai": bool }
    """
    session_id = payload.get("session_id", "")
    question = payload.get("question", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    try:
        result = simulation_engine.ask_history(session_id, question)
        return JSONResponse(content=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/simulation/exam")
async def api_sim_exam(payload: dict):
    """
    Resident requests physical examination findings.
    Body: { "session_id": str, "system": str }
    Returns: { "system": str, "findings": str }
    """
    session_id = payload.get("session_id", "")
    system = payload.get("system", "").strip()
    if not system:
        raise HTTPException(status_code=400, detail="system is required")
    try:
        result = simulation_engine.view_exam(session_id, system)
        return JSONResponse(content=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/simulation/investigate")
async def api_sim_investigate(payload: dict):
    """
    Resident orders an investigation.
    Body: { "session_id": str, "investigation": str }
    Returns: { "investigation": str, "result": str }
    """
    session_id = payload.get("session_id", "")
    investigation = payload.get("investigation", "").strip()
    if not investigation:
        raise HTTPException(status_code=400, detail="investigation is required")
    try:
        result = simulation_engine.order_investigation(session_id, investigation)
        return JSONResponse(content=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/simulation/submit")
async def api_sim_submit(payload: dict):
    """
    Resident submits diagnosis and management for scoring.
    Body: { "session_id": str, "diagnosis": str, "management": list[str] }
    Returns full score object with AI feedback.
    """
    session_id = payload.get("session_id", "")
    diagnosis = payload.get("diagnosis", "").strip()
    management = payload.get("management", [])
    if not diagnosis:
        raise HTTPException(status_code=400, detail="diagnosis is required")
    try:
        score = simulation_engine.submit_assessment(session_id, diagnosis, management)
        return JSONResponse(content=score)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
@track_perf("council_deliberation")
async def council_deliberate(request: Request):
    """Run diagnostic council deliberation."""
    from src.council import get_diagnostic_council
    
    data = await request.json()
    symptoms = data.get("symptoms", [])
    patient_history = data.get("patient_history", "")
    imaging_findings = data.get("imaging_findings", "")
    num_rollouts = data.get("num_rollouts", 5)
    vitals = data.get("vitals")
    raw_note = data.get("raw_note", "")

    council = get_diagnostic_council(agent=agent, num_rollouts=num_rollouts, pubmed_agent=pubmed_agent)
    deliberation = council.deliberate(
        symptoms=symptoms,
        patient_history=patient_history,
        imaging_findings=imaging_findings,
        vitals=vitals,
        raw_note=raw_note,
    )

    if audit_logger:
        audit_logger.log("COUNCIL_DELIBERATION", "deliberate",
                         details={"symptom_count": len(symptoms)})
    return deliberation.to_dict()


@app.post("/api/council/iterative-deliberate")
@track_perf("council_iterative")
async def council_iterative_deliberate(request: Request):
    """Run 2-round iterative diagnostic council with PubMed evidence feedback."""
    from src.council import get_diagnostic_council

    data = await request.json()
    symptoms = data.get("symptoms", [])
    patient_history = data.get("patient_history", "")
    imaging_findings = data.get("imaging_findings", "")
    num_rollouts = min(int(data.get("num_rollouts", 5)), 10)
    vitals = data.get("vitals")
    raw_note = data.get("raw_note", "")

    if not symptoms:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "No symptoms provided"}, status_code=400)

    council = get_diagnostic_council(agent=agent, num_rollouts=num_rollouts, pubmed_agent=pubmed_agent)
    result = council.iterative_deliberate(
        symptoms=symptoms,
        patient_history=patient_history,
        imaging_findings=imaging_findings,
        vitals=vitals,
        raw_note=raw_note,
    )
    if audit_logger:
        audit_logger.log("COUNCIL_DELIBERATION", "iterative_deliberate",
                         details={"symptom_count": len(symptoms)})
    return result.to_dict()


@app.post("/api/council/deliberate/stream")
async def council_deliberate_stream(request: Request):
    """SSE streaming deliberation — emits specialist opinions one by one as they arrive."""
    from src.council import get_diagnostic_council
    data = await request.json()
    symptoms        = data.get("symptoms", [])
    patient_history = data.get("patient_history", "")
    imaging_findings= data.get("imaging_findings", "")
    num_rollouts    = data.get("num_rollouts", 5)
    vitals          = data.get("vitals")
    raw_note        = data.get("raw_note", "")

    async def event_stream():
        yield {"event": "start", "data": json.dumps({
            "message": f"Assembling {num_rollouts}-specialist council...",
            "num_rollouts": num_rollouts,
        })}

        council = get_diagnostic_council(agent=agent, num_rollouts=num_rollouts, pubmed_agent=pubmed_agent)
        result_holder: dict = {}
        error_holder: dict = {}

        def _run_deliberate():
            try:
                result_holder["result"] = council.deliberate(
                    symptoms=symptoms,
                    patient_history=patient_history,
                    imaging_findings=imaging_findings,
                    vitals=vitals,
                    raw_note=raw_note,
                )
            except Exception as exc:
                error_holder["error"] = exc

        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(None, _run_deliberate)

        heartbeat_messages = [
            "Analyzing clinical presentation...",
            "Generating specialist opinions...",
            "Cross-referencing differential diagnoses...",
            "Weighing clinical evidence...",
            "Calculating consensus...",
        ]
        elapsed = 0
        msg_idx = 0
        while not future.done():
            await asyncio.sleep(2)
            elapsed += 2
            msg = heartbeat_messages[min(msg_idx, len(heartbeat_messages) - 1)]
            msg_idx += 1
            yield {"event": "heartbeat", "data": json.dumps({"elapsed": elapsed, "message": msg})}

        await future

        if "error" in error_holder:
            yield {"event": "error", "data": json.dumps({"detail": str(error_holder["error"])})}
            yield {"event": "done", "data": "{}"}
            return

        d = result_holder["result"].to_dict()

        # Stream specialist opinions with a short visual delay between each
        for opinion in d.get("opinions", []):
            yield {"event": "specialist", "data": json.dumps(opinion)}
            await asyncio.sleep(0.15)

        yield {"event": "consensus", "data": json.dumps({
            "consensus_diagnosis":          d.get("consensus_diagnosis"),
            "consensus_strength":           d.get("consensus_strength"),
            "consensus_confidence":         d.get("consensus_confidence"),
            "consensus_confidence_percent": d.get("consensus_confidence_percent"),
            "discussion_summary":           d.get("discussion_summary"),
            "most_urgent":                  d.get("most_urgent"),
            "final_recommendation":         d.get("final_recommendation"),
            "pubmed_insights":              d.get("pubmed_insights"),
        })}

        if audit_logger:
            audit_logger.log("COUNCIL_DELIBERATION", "deliberate_stream",
                             details={"symptom_count": len(symptoms)})
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_stream())


@app.get("/api/council/history")
async def get_council_history():
    """Get deliberation history."""
    from src.council import get_diagnostic_council
    council = get_diagnostic_council(agent=agent, pubmed_agent=pubmed_agent)
    return {"deliberations": council.get_deliberation_history()}


# ──────────────────────────────────────────────────────────────────────────────────────
# Long-Horizon Diagnostic Council API Endpoints (Phase 1)
# ──────────────────────────────────────────────────────────────────────────────────────

@app.post("/api/council/initiate-workflow")
@track_perf("council_workflow_init")
async def initiate_long_horizon_workflow(request: Request):
    """
    Initiate a long-horizon diagnostic council workflow with checkpointing.

    Returns workflow_id for future reference and re-deliberations.
    """
    from src.council import get_diagnostic_council

    data = await request.json()
    symptoms = data.get("symptoms", [])
    patient_id = data.get("patient_id", "")
    created_by = data.get("created_by", "system")
    patient_history = data.get("patient_history", "")
    imaging_findings = data.get("imaging_findings", "")
    vitals = data.get("vitals")
    raw_note = data.get("raw_note", "")
    num_rollouts = min(int(data.get("num_rollouts", 5)), 10)

    if not symptoms or not patient_id:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"error": "symptoms and patient_id are required"},
            status_code=400
        )

    council = get_diagnostic_council(agent=agent, num_rollouts=num_rollouts, pubmed_agent=pubmed_agent)
    workflow_id = council.initiate_long_horizon_workflow(
        symptoms=symptoms,
        patient_id=patient_id,
        created_by=created_by,
        patient_history=patient_history,
        imaging_findings=imaging_findings,
        vitals=vitals,
        raw_note=raw_note,
    )

    if audit_logger:
        audit_logger.log("LONG_HORIZON_WORKFLOW", "initiate",
                        details={"workflow_id": workflow_id, "patient_id": patient_id})

    return {
        "workflow_id": workflow_id,
        "status": "initiated",
        "message": f"Workflow {workflow_id} initiated for long-horizon monitoring"
    }


@app.get("/api/council/workflow/{workflow_id}")
@track_perf("council_workflow_status")
async def get_workflow_status(workflow_id: str):
    """Fetch workflow status, checkpoint count, and current decision trail."""
    from src.council import get_diagnostic_council
    from src.council.workflow_store import get_workflow_store

    council = get_diagnostic_council(agent=agent, pubmed_agent=pubmed_agent)
    status = council.get_workflow_status(workflow_id)

    if audit_logger:
        audit_logger.log("LONG_HORIZON_WORKFLOW", "status_query",
                        details={"workflow_id": workflow_id})

    return status


@app.post("/api/council/workflow/{workflow_id}/trigger-redlib")
@track_perf("council_workflow_redlib")
async def trigger_re_deliberation(workflow_id: str, request: Request):
    """
    Trigger a re-deliberation based on new evidence (labs, imaging, vitals).
    Creates a new branch under the same workflow_id.
    """
    from src.council.workflow_engine import get_workflow_engine
    from src.council import get_diagnostic_council

    data = await request.json()
    new_case_info = data.get("case_info", {})  # {symptoms, labs, vitals, imaging_findings}
    triggered_by = data.get("triggered_by", "system")  # "auto" or "physician_request"

    try:
        engine = get_workflow_engine()
        new_workflow_id, resumed_state = engine.initiate_re_deliberation(
            workflow_id=workflow_id,
            new_case_info=new_case_info,
            triggered_by_escalation=(triggered_by == "escalation")
        )

        if audit_logger:
            audit_logger.log("LONG_HORIZON_WORKFLOW", "redlib_triggered",
                           details={"workflow_id": workflow_id, "new_workflow_id": new_workflow_id})

        return {
            "new_workflow_id": new_workflow_id,
            "status": "re_deliberation_initiated",
            "message": f"Re-deliberation initiated as {new_workflow_id}",
            "previous_consensus": resumed_state.get("consensus_diagnosis"),
            "case_info_merged": bool(new_case_info)
        }
    except ValueError as e:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(e)}, status_code=404)


@app.get("/api/council/workflow/{workflow_id}/decision-trail")
@track_perf("council_workflow_trail")
async def get_decision_trail(workflow_id: str):
    """Fetch the complete decision audit trail for a workflow."""
    from src.council.workflow_store import get_workflow_store

    store = get_workflow_store()
    trail = store.get_decision_trail(workflow_id)

    if audit_logger:
        audit_logger.log("LONG_HORIZON_WORKFLOW", "trail_query",
                        details={"workflow_id": workflow_id, "event_count": len(trail)})

    return {
        "workflow_id": workflow_id,
        "decision_events": trail,
        "event_count": len(trail)
    }


@app.post("/api/council/workflow/{workflow_id}/physician-override")
@track_perf("council_workflow_override")
async def physician_override(workflow_id: str, request: Request):
    """
    Record physician override of diagnostic consensus.
    Physician can exclude, promote, or accept diagnoses.
    """
    from src.council.long_horizon_state import HumanOverride
    from src.council.workflow_store import get_workflow_store
    from datetime import datetime

    data = await request.json()
    physician_id = data.get("physician_id", "unknown")
    action = data.get("action", "accept")  # exclude, promote, request_reeval, accept
    target_diagnosis = data.get("target_diagnosis", None)
    rationale = data.get("rationale", "")

    try:
        store = get_workflow_store()
        workshop = store.get_workflow(workflow_id)

        if not workshop:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": f"Workflow {workflow_id} not found"}, status_code=404)

        # Log override (in full implementation, would update state and trigger re-eval)
        if audit_logger:
            audit_logger.log("LONG_HORIZON_WORKFLOW", "physician_override",
                           details={
                               "workflow_id": workflow_id,
                               "physician_id": physician_id,
                               "action": action,
                               "target_diagnosis": target_diagnosis
                           })

        return {
            "status": "override_recorded",
            "workflow_id": workflow_id,
            "message": f"Physician override recorded: {action}",
            "override_details": {
                "physician_id": physician_id,
                "action": action,
                "target_diagnosis": target_diagnosis,
                "rationale": rationale
            }
        }
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(e)}, status_code=500)


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


# ── Health Belief Model profile routes ────────────────────────────────────────

@app.get("/api/portal/{patient_id}/hbm-profile")
async def get_hbm_profile(patient_id: str):
    """Return the current Health Belief Model profile for a patient."""
    from src.portal.hbm_profile import get_hbm_service
    profile = get_hbm_service().load(patient_id)
    return profile.to_dict()


@app.delete("/api/portal/{patient_id}/hbm-profile")
async def reset_hbm_profile(patient_id: str):
    """Reset a patient's HBM profile to neutral defaults."""
    from src.portal.hbm_profile import get_hbm_service, HealthBeliefProfile
    svc = get_hbm_service()
    fresh = HealthBeliefProfile(patient_id=patient_id)
    svc.save(fresh)
    return {"status": "reset", "patient_id": patient_id}


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
# AI Portal — AI-Generated Bounding Box Extraction
# ============================================================

def extract_ai_annotations(response_text: str) -> list[dict]:
    """
    Extract bounding box annotations from MedGemma response.

    Looks for a JSON block at the end of the response with findings + coordinates.
    If JSON is missing but findings are detected, creates default bounding boxes.
    Returns a list of annotation dicts with normalized [0-1] coordinates.
    """
    import re
    import uuid

    ai_annotations = []

    try:
        # Look for JSON block in response (typically near end)
        json_pattern = r'\{\s*"findings"\s*:\s*\[[\s\S]*?\]\s*\}'
        match = re.search(json_pattern, response_text)

        if match:
            json_str = match.group(0)
            parsed = json.loads(json_str)

            if "findings" in parsed and isinstance(parsed["findings"], list):
                for finding in parsed["findings"]:
                    try:
                        # Extract and validate bounding box
                        box = finding.get("normalized_box", {})
                        if not isinstance(box, dict):
                            continue

                        x = float(box.get("x", 0.0))
                        y = float(box.get("y", 0.0))
                        w = float(box.get("w", 0.1))
                        h = float(box.get("h", 0.1))

                        # Clamp to [0, 1]
                        x = max(0.0, min(1.0, x))
                        y = max(0.0, min(1.0, y))
                        w = max(0.01, min(1.0, w))
                        h = max(0.01, min(1.0, h))

                        # Ensure box doesn't exceed image bounds
                        if x + w > 1.0:
                            w = 1.0 - x
                        if y + h > 1.0:
                            h = 1.0 - y

                        description = finding.get("description", "Finding")
                        confidence = float(finding.get("confidence", 0.5))
                        confidence = max(0.0, min(1.0, confidence))
                        significance = finding.get("significance", "SIGNIFICANT")

                        annotation = {
                            "id": f"ai-{uuid.uuid4().hex[:8]}",
                            "x": round(x, 3),
                            "y": round(y, 3),
                            "w": round(w, 3),
                            "h": round(h, 3),
                            "label": description,
                            "source": "ai",
                            "confidence": round(confidence, 2),
                            "significance": significance,
                        }
                        ai_annotations.append(annotation)
                    except (ValueError, TypeError) as e:
                        logger.debug(f"Failed to parse annotation finding: {e}")
                        continue
        else:
            # FALLBACK: If no JSON found, detect findings mentioned in text and create default boxes
            # This handles cases where model talks about findings but didn't output JSON format
            finding_keywords = [
                'opacity', 'consolidation', 'infiltrate', 'nodule', 'mass', 'lesion',
                'effusion', 'pneumothorax', 'fracture', 'displacement', 'dislocation',
                'air-fluid', 'artifact', 'evidence of', 'presence of', 'concerning for',
                'suspicious for'
            ]

            mentions_findings = any(kw in response_text.lower() for kw in finding_keywords)
            if mentions_findings:
                # Extract finding locations mentioned in text
                location_patterns = [
                    r'(right|left|bilateral|upper|lower|middle|apical|basilar|anterior|posterior|medial|lateral)\s+(lobe|chest|lung|abdomen|heart)',
                    r'(right|left)\s+(lower|upper|middle)\s+field',
                    r'in\s+the\s+(right|left)\s+(lower|upper)',
                ]

                found_locations = set()
                for pattern in location_patterns:
                    matches = re.findall(pattern, response_text.lower())
                    found_locations.update(str(m) for m in matches)

                if found_locations:
                    # Create default bounding boxes for detected locations
                    location_boxes = {
                        'right lower': {'x': 0.55, 'y': 0.45, 'w': 0.35, 'h': 0.40},
                        'right upper': {'x': 0.55, 'y': 0.05, 'w': 0.35, 'h': 0.35},
                        'left lower': {'x': 0.10, 'y': 0.45, 'w': 0.35, 'h': 0.40},
                        'left upper': {'x': 0.10, 'y': 0.05, 'w': 0.35, 'h': 0.35},
                    }

                    for location in found_locations:
                        if 'lower' in location and 'right' in location:
                            box = location_boxes['right lower']
                            label = 'Right lower lobe finding'
                        elif 'lower' in location and 'left' in location:
                            box = location_boxes['left lower']
                            label = 'Left lower lobe finding'
                        elif 'upper' in location and 'right' in location:
                            box = location_boxes['right upper']
                            label = 'Right upper lobe finding'
                        elif 'upper' in location and 'left' in location:
                            box = location_boxes['left upper']
                            label = 'Left upper lobe finding'
                        else:
                            continue

                        annotation = {
                            "id": f"ai-{uuid.uuid4().hex[:8]}",
                            "x": round(box['x'], 3),
                            "y": round(box['y'], 3),
                            "w": round(box['w'], 3),
                            "h": round(box['h'], 3),
                            "label": label,
                            "source": "ai",
                            "confidence": 0.65,  # Lower confidence since we're inferring
                            "significance": "SIGNIFICANT",
                        }
                        ai_annotations.append(annotation)

    except json.JSONDecodeError as e:
        logger.debug(f"AI annotations JSON parse error: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error extracting AI annotations: {e}")

    return ai_annotations


def extract_clinical_meta(response_text: str) -> tuple[dict | None, str]:
    """
    Extract the clinical_meta JSON block appended by the model at the end of its response.

    Returns (clinical_meta_dict_or_None, cleaned_response_text).
    The JSON line is stripped from the visible text so users never see raw JSON.
    """
    import re

    meta = None
    cleaned = response_text

    try:
        # Match the clinical_meta JSON object — must contain the "clinical_meta" key
        pattern = r'\{[^{}]*"clinical_meta"\s*:\s*\{[^{}]*\}[^{}]*\}'
        match = re.search(pattern, response_text, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            inner = parsed.get("clinical_meta", {})
            # Validate expected fields
            meta = {
                "key_points": [str(p) for p in inner.get("key_points", []) if p and str(p).strip() != "..."],
                "warnings": [str(w) for w in inner.get("warnings", []) if w and str(w).strip() != "..."],
                "confidence": inner.get("confidence", "moderate") if inner.get("confidence") in ("high", "moderate", "low") else "moderate",
                "suggested_actions": [str(a) for a in inner.get("suggested_actions", []) if a and str(a).strip() != "..."],
            }
            # Strip ALL occurrences of the JSON block from visible response
            cleaned = re.sub(pattern, '', response_text, flags=re.DOTALL).rstrip()
    except (json.JSONDecodeError, Exception) as e:
        logger.debug(f"clinical_meta extraction failed: {e}")

    return meta, cleaned


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
        "Always note diagnostic uncertainty and recommend clinical correlation. "
        "IMPORTANT: Only analyze medical images when an actual image is provided in the current message. "
        "If the user asks about an image but none was uploaded, ask them to upload it first. "
        "Do NOT fabricate or hallucinate image analyses. "
        "RESPONSE FORMAT: Use ## headers for sections, bullet lists (-) for findings, and **bold** for key clinical terms. "
        "At the very end of your response, append exactly this JSON on its own line (no code fences): "
        '{"clinical_meta": {"key_points": ["..."], "warnings": [], "confidence": "high|moderate|low", "suggested_actions": ["..."]}}'
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
            content = turn['content']

            # FILTER: If current request has NO image but history has image analyses,
            # truncate verbose medical analyses to avoid model hallucination on past analyses
            if not image_data and role_label == "MedGemma":
                # Detect if this looks like a full image analysis (starts with image findings/impressions)
                is_image_analysis = any(
                    content.strip().startswith(prefix)
                    for prefix in ["Heart size:", "Findings:", "Overall Impression:",
                                   "The image shows", "Brain parenchyma:", "Liver:",
                                   "Rhythm:", "Ventricles:", "Image Analysis"]
                )
                if is_image_analysis:
                    # Replace with summary instead of full analysis
                    content = "[Previous image analysis — omitted to prevent model confusion when no current image provided]"

            parts.append(f"**{role_label}:** {content}")

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
                    max_tokens=768,
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

    # Extract AI-generated annotations from response
    ai_annotations = extract_ai_annotations(response_text)

    # Extract structured clinical metadata and strip JSON from visible text
    clinical_meta, response_text = extract_clinical_meta(response_text)

    return {
        "response": response_text,
        "ai_annotations": ai_annotations,
        "clinical_meta": clinical_meta,
        "simulated": agent is None,
        "pubmed_context": pubmed_context,
    }


# ── Shared helpers for AI portal prompt building & PubMed ──────────────────

def _build_ai_portal_prompt(message, history, patient_context, image_data, image_modality, annotations):
    """Build prompt and decode image for AI portal endpoints. Returns (prompt, pil_image)."""
    import base64 as _b64
    import io

    parts: list[str] = []

    parts.append(
        "You are MedGemma, a clinical AI assistant helping Doctors and Residents. "
        "Provide accurate, evidence-based clinical insights. "
        "Always note diagnostic uncertainty and recommend clinical correlation. "
        "IMPORTANT: Only analyze medical images when an actual image is provided in the current message. "
        "If the user asks about an image but none was uploaded, ask them to upload it first. "
        "Do NOT fabricate or hallucinate image analyses. "
        "RESPONSE FORMAT: Use ## headers for sections, bullet lists (-) for findings, and **bold** for key clinical terms. "
        "At the very end of your response, append exactly this JSON on its own line (no code fences): "
        '{"clinical_meta": {"key_points": ["..."], "warnings": [], "confidence": "high|moderate|low", "suggested_actions": ["..."]}}'
    )

    if patient_context:
        if isinstance(patient_context, dict) and "freeText" in patient_context:
            parts.append(f"\n## Patient Information (manual entry)\n{patient_context['freeText']}")
        elif isinstance(patient_context, dict):
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

    if history:
        parts.append("\n## Conversation History")
        for turn in history[-8:]:
            role_label = "Doctor" if turn["role"] == "user" else "MedGemma"
            content = turn['content']
            if not image_data and role_label == "MedGemma":
                is_image_analysis = any(
                    content.strip().startswith(prefix)
                    for prefix in ["Heart size:", "Findings:", "Overall Impression:",
                                   "The image shows", "Brain parenchyma:", "Liver:",
                                   "Rhythm:", "Ventricles:", "Image Analysis"]
                )
                if is_image_analysis:
                    content = "[Previous image analysis — omitted to prevent model confusion when no current image provided]"
            parts.append(f"**{role_label}:** {content}")

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

    # Decode image
    pil_image = None
    if image_data:
        try:
            raw = image_data
            if "," in raw:
                raw = raw.split(",", 1)[1]
            img_bytes = _b64.b64decode(raw)
            from PIL import Image as PILImage
            pil_image = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
        except Exception as e:
            logger.warning(f"AI portal — failed to decode image: {e}")

    return prompt, pil_image


def _run_pubmed_enrichment(message, patient_context):
    """Run PubMed enrichment based on message intent. Returns dict or None."""
    if pubmed_agent is None:
        return None
    try:
        msg_lower = message.lower()
        ddi_keywords   = {"interaction", "drug interaction", "drug-drug", "combine", "combining"}
        ebm_keywords   = {"treatment", "guideline", "therapy", "efficacy", "evidence", "management",
                          "recommend", "first-line", "second-line"}
        zebra_keywords = {"diagnosis", "diagnose", "rare", "unusual", "zebra", "atypical",
                          "differential", "rule out", "what could"}

        is_ddi   = any(k in msg_lower for k in ddi_keywords)
        is_ebm   = any(k in msg_lower for k in ebm_keywords)
        is_zebra = any(k in msg_lower for k in zebra_keywords)

        if is_ddi and patient_context and isinstance(patient_context, dict):
            meds = []
            for m in patient_context.get("medications", []):
                name = m.get("name", "") if isinstance(m, dict) else str(m)
                if name:
                    meds.append(name)
            if len(meds) >= 2:
                res = pubmed_agent.ddi_monitor(current_medications=meds, max_results_per_pair=1, date_years_back=3)
                return {"mode": "ddi_monitor", "summary": res.summary, "ddi_alerts": res.ddi_alerts,
                        "key_findings": res.key_findings[:4], "citation_list": res.citation_list[:4]}
        elif is_ebm:
            res = pubmed_agent.ebm_validator(assessment=message[:300], plan="", max_results=3, date_years_back=2)
            return {"mode": "ebm_validator", "summary": res.summary, "divergences": res.divergences,
                    "key_findings": res.key_findings[:4], "citation_list": res.citation_list[:4]}
        elif is_zebra or (not is_ddi and not is_ebm):
            symptom_vocab = [
                "cough", "dyspnea", "shortness of breath", "wheezing", "chest pain",
                "fever", "fatigue", "weight loss", "nausea", "vomiting", "headache",
                "dizziness", "palpitations", "edema", "rash", "pain", "syncope",
                "weakness", "numbness", "tingling", "abdominal pain",
            ]
            found_symptoms = [s for s in symptom_vocab if s in msg_lower]
            if found_symptoms:
                res = pubmed_agent.case_matcher(common_symptoms=found_symptoms[:3], atypical_markers=found_symptoms[3:], max_results=3)
                return {"mode": "case_matcher", "summary": res.summary, "rare_diagnoses": res.rare_diagnoses,
                        "key_findings": res.key_findings[:4], "citation_list": res.citation_list[:4]}
    except Exception as e:
        logger.debug("AI portal PubMed enrichment failed (non-fatal): %s", e)
    return None


# ── SSE Streaming endpoint for AI Chat Portal ─────────────────────────────

@app.post("/api/ai-portal/chat/stream")
async def ai_portal_chat_stream(request: Request):
    """SSE streaming version of the AI Chat Portal endpoint."""
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

    prompt, pil_image = _build_ai_portal_prompt(
        message, history, patient_context, image_data, image_modality, annotations
    )

    async def event_stream():
        full_response = ""

        try:
            if agent is not None and hasattr(agent, "generate_medgemma_stream"):
                # ── Streaming path (Gemini true streaming / vLLM simulated) ──
                # Use a queue to bridge sync generator → async yields
                chunk_queue = asyncio.Queue()
                _sentinel = object()

                def _run_stream():
                    try:
                        for chunk in agent.generate_medgemma_stream(
                            prompt=prompt, image=pil_image, temperature=0.4, max_tokens=768,
                        ):
                            chunk_queue.put_nowait(chunk)
                    except Exception as e:
                        chunk_queue.put_nowait(e)
                    finally:
                        chunk_queue.put_nowait(_sentinel)

                loop = asyncio.get_event_loop()
                loop.run_in_executor(None, _run_stream)

                while True:
                    item = await chunk_queue.get()
                    if item is _sentinel:
                        break
                    if isinstance(item, Exception):
                        raise item
                    full_response += item
                    yield {"event": "token", "data": json.dumps({"text": item})}

            elif agent is not None and hasattr(agent, "generate_medgemma"):
                # ── Non-streaming fallback: generate then chunk ──
                full_response = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: agent.generate_medgemma(
                        prompt=prompt, image=pil_image, temperature=0.4, max_tokens=768,
                    )
                )
                words = full_response.split(" ")
                for i in range(0, len(words), 4):
                    chunk = " ".join(words[i:i + 4])
                    if i > 0:
                        chunk = " " + chunk
                    yield {"event": "token", "data": json.dumps({"text": chunk})}
                    await asyncio.sleep(0.03)

            elif agent is not None and hasattr(agent, "chat"):
                # ── Transformers path ──
                full_response = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: agent.chat(prompt)
                )
                words = full_response.split(" ")
                for i in range(0, len(words), 4):
                    chunk = " ".join(words[i:i + 4])
                    if i > 0:
                        chunk = " " + chunk
                    yield {"event": "token", "data": json.dumps({"text": chunk})}
                    await asyncio.sleep(0.03)

            else:
                # Simulated
                full_response = (
                    f"[Simulated — no GPU] Regarding your question: \"{message}\"\n\n"
                    "In a production environment with MedGemma loaded, I would provide "
                    "detailed clinical insights based on the patient context and your question."
                )
                words = full_response.split(" ")
                for i in range(0, len(words), 3):
                    chunk = " ".join(words[i:i + 3])
                    if i > 0:
                        chunk = " " + chunk
                    yield {"event": "token", "data": json.dumps({"text": chunk})}
                    await asyncio.sleep(0.04)

        except Exception as e:
            logger.error(f"AI portal streaming failed: {e}")
            yield {"event": "error", "data": json.dumps({"detail": str(e)})}
            yield {"event": "done", "data": "{}"}
            return

        # ── Post-processing: extract structured data ──
        ai_annotations = extract_ai_annotations(full_response)
        clinical_meta, cleaned_response = extract_clinical_meta(full_response)

        yield {"event": "response_complete", "data": json.dumps({
            "full_response": cleaned_response,
            "ai_annotations": ai_annotations,
            "clinical_meta": clinical_meta,
        })}

        # ── PubMed enrichment (runs after main response) ──
        try:
            pubmed_context = await asyncio.get_event_loop().run_in_executor(
                None, _run_pubmed_enrichment, message, patient_context
            )
            if pubmed_context:
                yield {"event": "pubmed", "data": json.dumps(pubmed_context)}
        except Exception as e:
            logger.debug(f"Streaming PubMed enrichment failed: {e}")

        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_stream())


@app.get("/api/ai-portal/token-stats")
async def ai_portal_token_stats():
    """Return token usage statistics for the active inference backend."""
    if agent is None:
        return {"backend": "simulated", "requests": 0}
    if hasattr(agent, "get_inference_stats"):
        stats = agent.get_inference_stats()
        stats["backend"] = type(agent).__name__
        return stats
    return {"backend": type(agent).__name__, "requests": 0, "note": "stats not available for this backend"}


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
# Referral letter routes
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/patients/{patient_id}/referral-letters")
async def get_referral_letters(patient_id: str):
    """Return all referral letters for a patient (newest first)."""
    letters = referral_service.get_letters(patient_id)
    return {"patient_id": patient_id, "letters": letters, "count": len(letters)}


@app.get("/api/encounters/{session_id}/referral-letters")
async def get_encounter_referral_letters(session_id: str):
    """Return referral letters generated in a specific encounter (from session cache)."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    patient_id = sessions[session_id]["patient_id"]
    all_letters = referral_service.get_letters(patient_id)
    letters = [ltr for ltr in all_letters if ltr.get("encounter_id") == session_id]
    return {"session_id": session_id, "letters": letters, "count": len(letters)}

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


# ══════════════════════════════════════════════════════════════════════════════
# Inpatient workflow routes
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/rounding", response_class=HTMLResponse)
async def rounding_page(request: Request):
    """Inpatient rounding copilot page."""
    return templates.TemplateResponse("rounding.html", {"request": request})


@app.get("/handoff", response_class=HTMLResponse)
async def handoff_page(request: Request):
    """SBAR handoff generator page."""
    return templates.TemplateResponse("handoff.html", {"request": request})


@app.get("/safety-dashboard", response_class=HTMLResponse)
async def safety_dashboard_page(request: Request):
    """Inpatient safety watchlist dashboard."""
    return templates.TemplateResponse("safety_dashboard.html", {"request": request})


@app.get("/api/inpatient/ward")
async def api_inpatient_ward():
    """Return all currently admitted inpatients with basic status info."""
    if rounding_service is None:
        raise HTTPException(status_code=503, detail="Rounding service not initialized")
    patients = rounding_service.get_admitted_patients()
    return JSONResponse(content={"inpatients": patients})


@app.post("/api/inpatient/{patient_id}/rounding-note")
@track_perf("rounding")
async def api_rounding_note(patient_id: str):
    """Generate a 24-hour inpatient progress note for a patient."""
    if rounding_service is None:
        raise HTTPException(status_code=503, detail="Rounding service not initialized")
    result = rounding_service.generate_progress_note(patient_id, agent=agent)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    if audit_logger:
        audit_logger.log("HANDOFF_GENERATED", "rounding", patient_id=patient_id)
    return JSONResponse(content=result)


@app.post("/api/inpatient/{patient_id}/sbar")
@track_perf("handoff")
async def api_sbar(patient_id: str):
    """Generate an SBAR handoff packet with completeness audit."""
    if sbar_service is None:
        raise HTTPException(status_code=503, detail="SBAR service not initialized")
    result = sbar_service.generate_sbar(patient_id, agent=agent)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    if audit_logger:
        audit_logger.log("HANDOFF_GENERATED", "sbar", patient_id=patient_id)
    return JSONResponse(content=result)


@app.get("/api/inpatient/safety")
async def api_safety_dashboard(ward: str | None = None):
    """Run safety checks across all inpatients (optionally filtered by ward)."""
    if safety_service is None:
        raise HTTPException(status_code=503, detail="Safety service not initialized")
    result = safety_service.get_ward_safety_dashboard(ward=ward, agent=agent)
    return JSONResponse(content=result)


@app.get("/api/inpatient/{patient_id}/safety")
async def api_patient_safety(patient_id: str):
    """Run safety checks for a single inpatient, with AI explanations."""
    if safety_service is None:
        raise HTTPException(status_code=503, detail="Safety service not initialized")
    alerts = safety_service.run_safety_checks(patient_id, agent=agent)
    return JSONResponse(content={"patient_id": patient_id, "alerts": [a.to_dict() for a in alerts]})


@app.post("/api/inpatient/{patient_id}/discharge-summary")
@track_perf("discharge_summary")
async def api_discharge_summary(patient_id: str, request: Request):
    """Generate a patient-friendly discharge summary with readmission risk assessment."""
    if discharge_planner is None:
        raise HTTPException(status_code=503, detail="Discharge planner not initialized")
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    soap_note = payload.get("soap_note", "") if payload else ""
    result = discharge_planner.generate_discharge_summary(patient_id, soap_note=soap_note, agent=agent)
    if audit_logger:
        audit_logger.log("DISCHARGE_PLANNED", "discharge_summary", patient_id=patient_id)
    return JSONResponse(content=result.to_dict())


# ══════════════════════════════════════════════════════════════════════════════
# Audit log routes
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/audit/recent")
async def api_audit_recent(limit: int = 100):
    """Return the most recent audit events."""
    if audit_logger is None:
        raise HTTPException(status_code=503, detail="Audit logger not initialized")
    return {"events": audit_logger.get_recent(limit=limit), "count": limit}


@app.get("/api/audit/patient/{patient_id}")
async def api_audit_patient(patient_id: str, limit: int = 50):
    """Return audit events for a specific patient."""
    if audit_logger is None:
        raise HTTPException(status_code=503, detail="Audit logger not initialized")
    events = audit_logger.get_for_patient(patient_id, limit=limit)
    return {"patient_id": patient_id, "events": events, "count": len(events)}


# ══════════════════════════════════════════════════════════════════════════════
# Performance metrics route
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/metrics")
async def api_metrics():
    """Return latency statistics for tracked operations."""
    return get_perf_stats()


# ══════════════════════════════════════════════════════════════════════════════
# Prior auth routes (request/{auth_id} MUST come before /{patient_id})
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/prior-auth/request/{auth_id}")
async def api_get_prior_auth_by_id(auth_id: str):
    """Look up a prior auth request by auth_id (cross-patient)."""
    req = prior_auth_service.find_by_auth_id(auth_id)
    if not req:
        raise HTTPException(status_code=404, detail="Prior auth request not found")
    return req


@app.post("/api/prior-auth/request/{auth_id}/approve")
async def api_approve_prior_auth(auth_id: str, request: Request):
    """Approve a prior auth request."""
    payload = await request.json()
    req = prior_auth_service.find_by_auth_id(auth_id)
    if not req:
        raise HTTPException(status_code=404, detail="Prior auth request not found")
    result = prior_auth_service.approve(
        req["patient_id"], auth_id,
        approved_by=payload.get("approved_by", ""),
        notes=payload.get("notes", ""),
    )
    if not result:
        raise HTTPException(status_code=400, detail="Transition failed")
    return result


@app.post("/api/prior-auth/request/{auth_id}/deny")
async def api_deny_prior_auth(auth_id: str, request: Request):
    """Deny a prior auth request."""
    payload = await request.json()
    req = prior_auth_service.find_by_auth_id(auth_id)
    if not req:
        raise HTTPException(status_code=404, detail="Prior auth request not found")
    result = prior_auth_service.deny(
        req["patient_id"], auth_id,
        reason=payload.get("reason", "Not medically necessary"),
        notes=payload.get("notes", ""),
    )
    if not result:
        raise HTTPException(status_code=400, detail="Transition failed")
    return result


@app.get("/api/prior-auth/{patient_id}")
async def api_get_patient_prior_auths(patient_id: str):
    """Return all prior auth requests for a patient."""
    requests = prior_auth_service.get_all(patient_id)
    return {"patient_id": patient_id, "requests": requests, "count": len(requests)}


@app.post("/api/prior-auth/{patient_id}/detect")
async def api_detect_prior_auth(patient_id: str, request: Request):
    """Auto-detect and create prior auth requests from order text."""
    payload = await request.json()
    encounter_id = payload.get("encounter_id", "")
    orders_text = payload.get("orders_text", "")
    clinical_indication = payload.get("clinical_indication", "")
    orders = [o.strip() for o in orders_text.replace(",", "\n").splitlines() if o.strip()]
    created = prior_auth_service.detect_and_create(
        patient_id=patient_id,
        encounter_id=encounter_id,
        orders=orders,
        clinical_indication=clinical_indication,
    )
    return {"patient_id": patient_id, "created": [r.to_dict() for r in created], "count": len(created)}


# ══════════════════════════════════════════════════════════════════════════════
# Referral letter routes (inpatient-style API)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/referral/{patient_id}")
async def api_get_referral_letters(patient_id: str):
    """Return all referral letters for a patient."""
    letters = referral_service.get_letters(patient_id)
    return {"patient_id": patient_id, "letters": letters, "count": len(letters)}


@app.post("/api/referral/{patient_id}/generate")
async def api_generate_referral(patient_id: str, request: Request):
    """Generate referral letter(s) for a patient encounter."""
    payload = await request.json()
    encounter_id = payload.get("encounter_id", "")
    referral_orders = payload.get("referral_orders", [])
    soap_note = payload.get("soap_note")
    letters = referral_service.generate_letters_for_encounter(
        patient_id=patient_id,
        encounter_id=encounter_id,
        referral_orders=referral_orders,
        soap_note=soap_note,
        agent=agent,
    )
    return {"patient_id": patient_id, "letters": [l.to_dict() for l in letters], "count": len(letters)}


# ══════════════════════════════════════════════════════════════════════════════
# Medication reconciliation route
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/inpatient/{patient_id}/med-reconciliation")
async def api_med_reconciliation(patient_id: str):
    """Return medication reconciliation for an inpatient."""
    if discharge_planner is None:
        raise HTTPException(status_code=503, detail="Discharge planner not initialized")
    recon = discharge_planner.reconcile_medications(patient_id)
    if recon is None:
        raise HTTPException(status_code=404, detail="Patient not found or no medication data")
    return JSONResponse(content=recon.to_dict())


# ══════════════════════════════════════════════════════════════════════════════
# Hospital / multi-tenant routes
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/hospitals")
async def api_list_hospitals():
    """List all registered hospital profiles."""
    if hospital_registry is None:
        raise HTTPException(status_code=503, detail="Hospital registry not initialized")
    return {"hospitals": hospital_registry.list_all()}


@app.get("/api/hospitals/{hospital_id}")
async def api_get_hospital(hospital_id: str):
    """Get a single hospital profile."""
    if hospital_registry is None:
        raise HTTPException(status_code=503, detail="Hospital registry not initialized")
    hosp = hospital_registry.get(hospital_id)
    if not hosp:
        raise HTTPException(status_code=404, detail="Hospital not found")
    return hosp.to_dict()


@app.post("/api/hospitals")
async def api_add_hospital(request: Request):
    """Register a new hospital profile."""
    if hospital_registry is None:
        raise HTTPException(status_code=503, detail="Hospital registry not initialized")
    payload = await request.json()
    hospital_id = payload.get("hospital_id")
    name = payload.get("name")
    if not hospital_id or not name:
        raise HTTPException(status_code=400, detail="hospital_id and name are required")
    hosp = Hospital(
        hospital_id=hospital_id,
        name=name,
        timezone=payload.get("timezone", "UTC"),
        formulary_restrictions=payload.get("formulary_restrictions", []),
        branding=payload.get("branding", {"logo_url": "", "primary_color": "#2563eb"}),
        features_enabled=payload.get("features_enabled", {}),
        contact_info=payload.get("contact_info", {}),
    )
    registered = hospital_registry.add(hosp)
    return registered.to_dict()


@app.get("/api/hospitals/{hospital_id}/patients")
async def api_hospital_patients(hospital_id: str):
    """List patients belonging to a specific hospital."""
    if hospital_registry is None:
        raise HTTPException(status_code=503, detail="Hospital registry not initialized")
    if not hospital_registry.get(hospital_id):
        raise HTTPException(status_code=404, detail="Hospital not found")
    all_patients = fhir_server.list_patients()
    matched = [
        p for p in all_patients
        if fhir_server.patients.get(p["id"], {}).get("hospital_id") == hospital_id
    ]
    return {"hospital_id": hospital_id, "patients": matched, "count": len(matched)}


# ══════════════════════════════════════════════════════════════════════════════
# Rare Disease API
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/rare-disease/hunt")
@track_perf("rare_disease_hunt")
async def api_rare_disease_hunt(request: Request):
    """
    TTT-inspired rare disease diagnostic hunt.

    Body: RareCaseInput JSON
    Returns: RareDiseaseReport JSON

    The endpoint runs the pseudo-Test-Time-Training iterative refinement loop:
      1. Symptom fingerprinting + ontology seed hypotheses
      2. MedGemma LLM hypothesis generation (if agent available)
      3. PubMed evidence retrieval per hypothesis (if pubmed_agent available)
      4. Diagnostic reward scoring (symptom coverage × evidence × coherence)
      5. If reward < threshold → expand via ontology adjacency + LLM self-critique
      6. Repeat up to max_iterations
      7. Return ranked rare disease candidates with confirmatory tests and citations
    """
    if rare_disease_director is None:
        raise HTTPException(status_code=503, detail="Rare disease director not initialized")
    try:
        payload = await request.json()
        case = RareCaseInput(**payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid request body: {exc}")

    try:
        report = await rare_disease_director.hunt(case)
    except Exception as exc:
        logger.exception("Rare disease hunt failed")
        raise HTTPException(status_code=500, detail=str(exc))

    if audit_logger is not None:
        audit_logger.log(
            event_type="clinical_ai",
            action="rare_disease_hunt",
            patient_id=None,
            details={
                "symptoms_count": len(case.symptoms),
                "hypotheses_returned": len(report.hypotheses),
                "iterations": report.convergence.iterations_performed,
                "converged": report.convergence.converged,
                "top_hypothesis": report.hypotheses[0].name if report.hypotheses else None,
            },
        )

    return report.model_dump(mode="json")


@app.post("/api/rare-disease/hunt/stream")
@track_perf("rare_disease_hunt_stream")
async def api_rare_disease_hunt_stream(request: Request):
    """SSE streaming rare disease hunt — emits progress events and hypothesis cards as they're scored."""
    if rare_disease_director is None:
        raise HTTPException(status_code=503, detail="Rare disease director not initialized")
    try:
        payload = await request.json()
        case = RareCaseInput(**payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid request body: {exc}")

    async def event_stream():
        try:
            async for event in rare_disease_director.hunt_stream(case):
                event_name = event["event"]
                event_data = event["data"]
                data_str = json.dumps(event_data) if not isinstance(event_data, str) else event_data
                yield {"event": event_name, "data": data_str}
        except Exception as exc:
            logger.exception("Rare disease hunt stream failed")
            yield {"event": "error", "data": json.dumps({"detail": str(exc)})}
            yield {"event": "done", "data": "{}"}
            return

        if audit_logger is not None:
            audit_logger.log(
                event_type="clinical_ai",
                action="rare_disease_hunt_stream",
                patient_id=None,
                details={"symptoms_count": len(case.symptoms)},
            )

    return EventSourceResponse(event_stream())


if __name__ == "__main__":
    import multiprocessing

    parser = argparse.ArgumentParser(description="MedGemma Clinical Assistant")
    parser.add_argument("--use-vllm", action="store_true", help="Use vLLM backend for faster inference")
    parser.add_argument("--simulated", action="store_true", help="Run in simulated mode (no GPU)")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--workers", type=int, default=None, help="Number of worker processes (default: CPU count)")
    args = parser.parse_args()

    if args.simulated:
        os.environ["SIMULATED_MODE"] = "true"
        print("Running in SIMULATED mode (no GPU models)")

    if args.use_vllm:
        os.environ["USE_VLLM"] = "true"
        print("Using vLLM backend for inference")

    # Respect environment flag as well as CLI switch.
    use_vllm = os.environ.get("USE_VLLM", "false").lower() in ("1", "true", "yes")
    is_wsl = bool(os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"))

    # Configure workers conservatively for GPU/WSL stability.
    # vLLM and WSL are much more stable with a single worker process.
    if args.workers is not None:
        num_workers = args.workers
    elif use_vllm or is_wsl:
        num_workers = 1
    else:
        num_workers = max(2, multiprocessing.cpu_count())

    if use_vllm and num_workers > 1:
        print("WARNING: USE_VLLM=true with multiple workers can crash due to duplicated GPU model loads.")
        print("WARNING: Consider --workers 1 for stability.")

    if is_wsl and num_workers > 1:
        print("WARNING: WSL detected with multiple workers; this can increase memory pressure and instability.")
    print(f"Starting MedGemma with {num_workers} worker process(es)")

    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        workers=num_workers,
        reload=False,
        log_level="info",
        timeout_keep_alive=30,      # Force keepalive timeout every 30s
        # timeout_notify=60,           # 60s for graceful shutdown signal handling
        backlog=2048,                # Accept up to 2048 pending connections
        access_log=False,            # Disable access logs for performance (use middleware instead)
        loop="uvloop" if os.environ.get("ENABLE_UVLOOP", "true").lower() in ("1", "true") else "auto"
    )
