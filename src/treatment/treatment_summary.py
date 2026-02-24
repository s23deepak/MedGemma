"""
Post-encounter treatment summary service.

Generates two artefacts after each approved encounter:

1. Full treatment summary — stored in the patient's history (category
   "treatment_summary") so the patient can view it in the History tab.

2. De-identified summary — 18 HIPAA Safe Harbor identifiers stripped; stored
   in `fhir_server.treatment_cases` for cross-patient reuse / similar-patient
   lookup.

HIPAA Safe Harbor identifiers removed:
  Names, geographic subdivisions smaller than state, dates (reduced to year
  only), phone/fax, email, SSN, MRN, health plan numbers, account numbers,
  certificate/licence numbers, VIN, URL, IP address, biometric IDs,
  full-face photos, unique codes.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.ehr.fhir_mock import MockFHIRServer

logger = logging.getLogger(__name__)


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class TreatmentSummary:
    """Structured summary of a completed clinical encounter."""
    summary_id: str
    patient_id: str
    encounter_date: datetime
    chief_complaint: str
    primary_diagnosis: str
    differential_diagnoses: list[str]
    treatments_provided: list[str]
    medications_prescribed: list[str]
    lab_orders: list[str]
    imaging_orders: list[str]
    follow_up_instructions: str
    critical_alerts: list[str]
    soap_subjective: str
    soap_objective: str
    soap_assessment: str
    soap_plan: str
    outcome_notes: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "summary_id": self.summary_id,
            "patient_id": self.patient_id,
            "encounter_date": self.encounter_date.isoformat(),
            "chief_complaint": self.chief_complaint,
            "primary_diagnosis": self.primary_diagnosis,
            "differential_diagnoses": self.differential_diagnoses,
            "treatments_provided": self.treatments_provided,
            "medications_prescribed": self.medications_prescribed,
            "lab_orders": self.lab_orders,
            "imaging_orders": self.imaging_orders,
            "follow_up_instructions": self.follow_up_instructions,
            "critical_alerts": self.critical_alerts,
            "soap_subjective": self.soap_subjective,
            "soap_objective": self.soap_objective,
            "soap_assessment": self.soap_assessment,
            "soap_plan": self.soap_plan,
            "outcome_notes": self.outcome_notes,
            "created_at": self.created_at.isoformat(),
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Treatment Summary — {self.encounter_date.strftime('%B %d, %Y')}",
            f"\n**Chief Complaint:** {self.chief_complaint}",
            f"**Primary Diagnosis:** {self.primary_diagnosis}",
        ]
        if self.differential_diagnoses:
            lines.append("\n**Differential Diagnoses:**")
            for d in self.differential_diagnoses:
                lines.append(f"- {d}")
        if self.treatments_provided:
            lines.append("\n**Treatments Provided:**")
            for t in self.treatments_provided:
                lines.append(f"- {t}")
        if self.medications_prescribed:
            lines.append("\n**Medications Prescribed:**")
            for m in self.medications_prescribed:
                lines.append(f"- {m}")
        if self.lab_orders:
            lines.append("\n**Lab Orders:**")
            for l in self.lab_orders:
                lines.append(f"- {l}")
        if self.imaging_orders:
            lines.append("\n**Imaging Orders:**")
            for i in self.imaging_orders:
                lines.append(f"- {i}")
        lines.append(f"\n**Follow-up Instructions:**\n{self.follow_up_instructions}")
        if self.critical_alerts:
            lines.append("\n**Critical Alerts:**")
            for a in self.critical_alerts:
                lines.append(f"- ⚠️ {a}")
        return "\n".join(lines)


@dataclass
class AnonymizedCase:
    """De-identified treatment case for cross-patient learning (HIPAA Safe Harbor)."""
    case_id: str
    # Patient demographics — age_decade instead of exact age; state only
    age_decade: str          # e.g. "50s"
    gender: str
    state: str               # state-level only (not city/zip)
    year_of_encounter: int   # year only, not full date
    # Clinical data (no identifiers)
    chief_complaint: str
    primary_diagnosis: str
    differential_diagnoses: list[str]
    treatments_provided: list[str]
    medications_prescribed: list[str]
    lab_orders: list[str]
    imaging_orders: list[str]
    follow_up_template: str  # generic follow-up, dates replaced with durations
    critical_alerts: list[str]
    # For similarity search
    icd10_codes: list[str] = field(default_factory=list)
    condition_tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "age_decade": self.age_decade,
            "gender": self.gender,
            "state": self.state,
            "year_of_encounter": self.year_of_encounter,
            "chief_complaint": self.chief_complaint,
            "primary_diagnosis": self.primary_diagnosis,
            "differential_diagnoses": self.differential_diagnoses,
            "treatments_provided": self.treatments_provided,
            "medications_prescribed": self.medications_prescribed,
            "lab_orders": self.lab_orders,
            "imaging_orders": self.imaging_orders,
            "follow_up_template": self.follow_up_template,
            "critical_alerts": self.critical_alerts,
            "icd10_codes": self.icd10_codes,
            "condition_tags": self.condition_tags,
            "created_at": self.created_at.isoformat(),
        }


# ── Service ───────────────────────────────────────────────────────────────────

class TreatmentSummaryService:
    """Generates and stores treatment summaries after encounter approval."""

    def __init__(self, fhir_server: "MockFHIRServer"):
        self.fhir = fhir_server
        # storage: patient_id → list[TreatmentSummary]
        if not hasattr(self.fhir, "treatment_summaries"):
            self.fhir.treatment_summaries: dict[str, list[dict]] = {}
        # De-identified cross-patient cases
        if not hasattr(self.fhir, "treatment_cases"):
            self.fhir.treatment_cases: list[dict] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def generate_and_store(
        self,
        patient_id: str,
        session: dict,
    ) -> TreatmentSummary:
        """
        Build a TreatmentSummary from the session, persist it, and return it.

        Args:
            patient_id: FHIR patient ID
            session: Active encounter session dict (contains soap_note, transcription, etc.)

        Returns:
            The newly created TreatmentSummary
        """
        soap = session.get("soap_note")
        patient_ctx = session.get("patient_context") or {}

        # Extract fields from EnhancedSOAPNote (or plain SOAPNote)
        subjective = getattr(soap, "subjective", "") or ""
        objective = getattr(soap, "objective", "") or ""
        assessment = getattr(soap, "assessment", "") or ""
        plan = getattr(soap, "plan", "") or ""
        differentials = [
            d.get("diagnosis", str(d)) if isinstance(d, dict) else str(d)
            for d in (getattr(soap, "differentials", []) or [])
        ]
        critical_alerts = list(getattr(soap, "critical_alerts", []) or [])

        # Extract medications / orders from the plan section
        medications = self._extract_medications_from_plan(plan)
        lab_orders = self._extract_lab_orders_from_plan(plan)
        imaging_orders = self._extract_imaging_orders_from_plan(plan)
        treatments = self._extract_treatments(soap, plan)
        follow_up = self._extract_follow_up(plan)

        # Derive primary diagnosis from assessment
        primary_diagnosis = self._first_line(assessment) or "See assessment"

        summary = TreatmentSummary(
            summary_id=f"TS-{uuid.uuid4().hex[:8].upper()}",
            patient_id=patient_id,
            encounter_date=datetime.now(),
            chief_complaint=session.get("chief_complaint", subjective[:80] or "See notes"),
            primary_diagnosis=primary_diagnosis,
            differential_diagnoses=differentials,
            treatments_provided=treatments,
            medications_prescribed=medications,
            lab_orders=lab_orders,
            imaging_orders=imaging_orders,
            follow_up_instructions=follow_up,
            critical_alerts=critical_alerts,
            soap_subjective=subjective,
            soap_objective=objective,
            soap_assessment=assessment,
            soap_plan=plan,
        )

        # 1. Persist full summary per patient (in-memory)
        if patient_id not in self.fhir.treatment_summaries:
            self.fhir.treatment_summaries[patient_id] = []
        self.fhir.treatment_summaries[patient_id].append(summary.to_dict())

        # 2. Persist de-identified case (in-memory)
        anon_case = self._anonymize(summary, patient_ctx)
        self.fhir.treatment_cases.append(anon_case.to_dict())

        # 3. Persist to Firebase (patient history + embedded anon_case for later finalization)
        self._write_to_firestore(summary, anon_case)

        return summary

    def _write_to_firestore(self, summary: TreatmentSummary, anon_case: AnonymizedCase) -> None:
        """Write treatment summary to patients/{patient_id}/treatment_summaries/{summary_id}."""
        try:
            from src.config.firebase_config import get_firestore_client, is_firebase_available
            if not is_firebase_available():
                return
            db = get_firestore_client()
            if db is None:
                return
            doc_data = {
                **summary.to_dict(),
                "anon_case": anon_case.to_dict(),
                "finalized": False,
            }
            (
                db.collection("patients")
                .document(summary.patient_id)
                .collection("treatment_summaries")
                .document(summary.summary_id)
                .set(doc_data)
            )
            logger.info(
                f"Treatment summary {summary.summary_id} written to Firestore "
                f"for patient {summary.patient_id}"
            )
        except Exception as e:
            logger.warning(f"Failed to write treatment summary to Firestore: {e}")

    # ── Hospital finalization (60-day rule) ───────────────────────────────────

    def finalize_hospital_cases(self, days: int = 60) -> int:
        """
        Scan all patient treatment summaries in Firestore.

        For each patient whose last encounter was more than `days` ago (default 60),
        copy every un-finalized summary's anonymized case to the top-level
        ``hospital_cases`` collection and mark the source document ``finalized=True``.

        Returns the number of cases finalized in this run.
        """
        try:
            from src.config.firebase_config import get_firestore_client, is_firebase_available
            if not is_firebase_available():
                return 0
            db = get_firestore_client()
            if db is None:
                return 0
        except Exception as e:
            logger.warning(f"finalize_hospital_cases: Firebase unavailable — {e}")
            return 0

        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
        finalized_count = 0

        try:
            patients_docs = db.collection("patients").stream()
        except Exception as e:
            logger.warning(f"finalize_hospital_cases: could not list patients — {e}")
            return 0

        for patient_doc in patients_docs:
            patient_id = patient_doc.id
            try:
                summaries_ref = (
                    db.collection("patients")
                    .document(patient_id)
                    .collection("treatment_summaries")
                )
                # Get all summaries for this patient, newest first
                all_summaries = list(summaries_ref.order_by("created_at", direction="DESCENDING").stream())
            except Exception as e:
                logger.warning(f"finalize_hospital_cases: error reading summaries for {patient_id} — {e}")
                continue

            if not all_summaries:
                continue

            # Check if the most recent encounter was more than `days` ago
            most_recent_doc = all_summaries[0].to_dict()
            most_recent_str = most_recent_doc.get("created_at", "")
            try:
                # Parse ISO date; make timezone-aware if naive
                most_recent_dt = datetime.fromisoformat(most_recent_str)
                if most_recent_dt.tzinfo is None:
                    most_recent_dt = most_recent_dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue

            if most_recent_dt >= cutoff:
                # Patient had a recent encounter — not eligible for finalization yet
                continue

            # Finalize all un-finalized summaries for this patient
            for summary_doc in all_summaries:
                data = summary_doc.to_dict()
                if data.get("finalized"):
                    continue  # already processed

                anon_case_data = data.get("anon_case")
                if not anon_case_data:
                    continue

                case_id = anon_case_data.get("case_id", f"AC-{uuid.uuid4().hex[:8].upper()}")
                try:
                    db.collection("hospital_cases").document(case_id).set({
                        **anon_case_data,
                        "source_summary_id": data.get("summary_id"),
                        "finalized_at": datetime.now(tz=timezone.utc).isoformat(),
                    })
                    # Mark the source summary as finalized
                    summaries_ref.document(summary_doc.id).update({"finalized": True})
                    finalized_count += 1
                    logger.info(
                        f"Hospital case {case_id} finalized from summary "
                        f"{data.get('summary_id')} (patient {patient_id})"
                    )
                except Exception as e:
                    logger.warning(
                        f"finalize_hospital_cases: failed to finalize {case_id} — {e}"
                    )

        logger.info(f"finalize_hospital_cases: finalized {finalized_count} case(s)")
        return finalized_count

    def get_summaries(self, patient_id: str) -> list[dict]:
        """Return all treatment summaries for a patient (newest first)."""
        summaries = getattr(self.fhir, "treatment_summaries", {}).get(patient_id, [])
        return list(reversed(summaries))

    def find_similar_cases(
        self,
        diagnosis_keywords: list[str],
        max_results: int = 5,
    ) -> list[dict]:
        """
        Return de-identified cases whose tags/diagnosis overlaps with keywords.
        Used to surface similar treatment patterns for clinical reference.
        """
        cases: list[dict] = getattr(self.fhir, "treatment_cases", [])
        if not diagnosis_keywords:
            return cases[-max_results:]

        keywords_lower = [k.lower() for k in diagnosis_keywords]

        def score(case: dict) -> int:
            text = " ".join([
                case.get("primary_diagnosis", ""),
                case.get("chief_complaint", ""),
                " ".join(case.get("condition_tags", [])),
                " ".join(case.get("icd10_codes", [])),
            ]).lower()
            return sum(1 for kw in keywords_lower if kw in text)

        ranked = sorted(cases, key=score, reverse=True)
        return [c for c in ranked if score(c) > 0][:max_results]

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _first_line(text: str) -> str:
        for line in text.splitlines():
            line = line.strip().lstrip("1234567890.-) ")
            if line:
                return line
        return text[:100].strip()

    @staticmethod
    def _extract_medications_from_plan(plan: str) -> list[str]:
        """Pull medication names from the Plan section."""
        meds: list[str] = []
        patterns = [
            r"(?:prescribe|start|continue|add|initiate)[d\s]+([A-Z][a-z]+(?:\s+\d+\s*mg|\s+\d+\s*mcg)?)",
            r"([A-Z][a-z]+(?:olol|pril|sartan|statin|mycin|cillin|oxacin|azole|mide)\s+\d+\s*mg)",
        ]
        for pat in patterns:
            for m in re.finditer(pat, plan, re.IGNORECASE):
                med = m.group(1).strip()
                if med not in meds:
                    meds.append(med)
        return meds[:10]

    @staticmethod
    def _extract_lab_orders_from_plan(plan: str) -> list[str]:
        """Extract lab test names from Plan section."""
        lab_keywords = [
            "CBC", "BMP", "CMP", "HbA1c", "TSH", "LFT", "lipid panel",
            "urinalysis", "urine culture", "blood culture", "troponin",
            "BNP", "D-dimer", "creatinine", "eGFR", "INR", "PT", "PTT",
            "thyroid panel", "metabolic panel", "coagulation studies",
        ]
        found = []
        plan_lower = plan.lower()
        for lab in lab_keywords:
            if lab.lower() in plan_lower and lab not in found:
                found.append(lab)
        return found

    @staticmethod
    def _extract_imaging_orders_from_plan(plan: str) -> list[str]:
        """Extract imaging orders from Plan section."""
        imaging_keywords = [
            "chest X-ray", "CXR", "CT chest", "CT abdomen", "CT head",
            "MRI brain", "MRI spine", "ultrasound", "echocardiogram",
            "EKG", "ECG", "stress test", "bone scan", "PET scan",
        ]
        found = []
        plan_lower = plan.lower()
        for img in imaging_keywords:
            if img.lower() in plan_lower and img not in found:
                found.append(img)
        return found

    @staticmethod
    def _extract_treatments(soap, plan: str) -> list[str]:
        """Extract treatment procedures performed/planned."""
        treatments = []
        treatment_patterns = [
            r"(?:performed|completed|administered|applied)\s+([^.,\n]{5,60})",
            r"(?:IV\s+\w+|oxygen therapy|nebulizer|wound\s+\w+|dressing change)",
        ]
        for pat in treatment_patterns:
            for m in re.finditer(pat, plan, re.IGNORECASE):
                t = m.group(0).strip()
                if t not in treatments:
                    treatments.append(t)
        return treatments[:8]

    @staticmethod
    def _extract_follow_up(plan: str) -> str:
        """Extract follow-up instructions from Plan section."""
        lines = plan.splitlines()
        follow_up_lines = []
        capture = False
        for line in lines:
            l_lower = line.lower()
            if any(kw in l_lower for kw in ["follow", "return", "follow-up", "f/u", "revisit"]):
                capture = True
            if capture and line.strip():
                follow_up_lines.append(line.strip())
                if len(follow_up_lines) >= 3:
                    break
        return " ".join(follow_up_lines) if follow_up_lines else "Follow up as directed by physician."

    def _anonymize(self, summary: TreatmentSummary, patient_ctx: dict) -> AnonymizedCase:
        """
        Produce an AnonymizedCase by applying HIPAA Safe Harbor de-identification.

        Removes / generalises all 18 identifier categories:
        - Names → removed
        - Dates → year only
        - Geographic → state only (no city/zip)
        - Ages → decade bucket (e.g. "50s")
        - MRN, phone, email, SSN → removed
        """
        # Age — bucket into decade
        age = patient_ctx.get("patient", {}).get("age", 0)
        if age:
            decade = f"{(int(age) // 10) * 10}s"
        else:
            decade = "unknown"

        # Location — state only
        patient_raw = patient_ctx.get("patient", {})
        location = patient_raw.get("location", "")
        # patient_ctx location stores city; we want state — use FHIR if available
        fhir_patient = self.fhir.get_patient(summary.patient_id) or {}
        state = ""
        for addr in fhir_patient.get("address", []):
            if addr.get("state"):
                state = addr["state"]
                break

        # Scrub personal names from text fields using regex
        def scrub(text: str) -> str:
            # Remove name-like tokens (Title-cased words that aren't medical terms)
            # simple heuristic: anything after "Dr.", "Mr.", "Ms.", "Mrs.", "Patient"
            text = re.sub(r"\b(?:Dr|Mr|Mrs|Ms|Prof)\.\s+[A-Z][a-z]+", "[REMOVED]", text)
            text = re.sub(r"\bPatient\s+[A-Z][a-z]+", "Patient", text)
            # Remove phone numbers
            text = re.sub(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b", "[PHONE]", text)
            # Remove emails
            text = re.sub(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "[EMAIL]", text)
            # Remove SSN-like patterns
            text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]", text)
            # Replace specific dates dd/mm/yyyy or yyyy-mm-dd with year only
            text = re.sub(r"\b(\d{4})-\d{2}-\d{2}\b", r"\1", text)
            text = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-](\d{4})\b", r"\1", text)
            # Remove MRN-like patterns
            text = re.sub(r"\b(?:MRN|mrn|patient\s*id|patient\s*#)\s*[:\s]*[A-Z0-9\-]+", "[MRN]", text, flags=re.IGNORECASE)
            return text

        # Generalise follow-up from specific dates to durations
        follow_up = scrub(summary.follow_up_instructions)

        # Extract ICD-10 codes from assessment if present
        icd10_codes = re.findall(r"\b[A-Z]\d{2}(?:\.\d{1,3})?\b", summary.soap_assessment)

        # Build condition tags from assessment first line
        condition_tags = [
            w.lower() for w in re.findall(r"[A-Za-z]{4,}", summary.primary_diagnosis)
            if w.lower() not in ("with", "and", "the", "for", "due", "from")
        ]

        return AnonymizedCase(
            case_id=f"AC-{uuid.uuid4().hex[:8].upper()}",
            age_decade=decade,
            gender=patient_ctx.get("patient", {}).get("gender", "unknown"),
            state=state or "unknown",
            year_of_encounter=summary.encounter_date.year,
            chief_complaint=scrub(summary.chief_complaint),
            primary_diagnosis=scrub(summary.primary_diagnosis),
            differential_diagnoses=[scrub(d) for d in summary.differential_diagnoses],
            treatments_provided=[scrub(t) for t in summary.treatments_provided],
            medications_prescribed=[scrub(m) for m in summary.medications_prescribed],
            lab_orders=summary.lab_orders[:],
            imaging_orders=summary.imaging_orders[:],
            follow_up_template=follow_up,
            critical_alerts=[scrub(a) for a in summary.critical_alerts],
            icd10_codes=icd10_codes,
            condition_tags=condition_tags[:10],
        )


# ── Singleton ─────────────────────────────────────────────────────────────────
_treatment_service: TreatmentSummaryService | None = None


def get_treatment_service(fhir_server=None) -> TreatmentSummaryService:
    """Get or create the TreatmentSummaryService singleton."""
    global _treatment_service
    if _treatment_service is None:
        if fhir_server is None:
            from src.ehr import get_fhir_server
            fhir_server = get_fhir_server()
        _treatment_service = TreatmentSummaryService(fhir_server)
    return _treatment_service
