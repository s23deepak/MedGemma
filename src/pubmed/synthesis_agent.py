"""
PubMed Synthesis Agent

Three operating modes, mapped to the three clinical use-cases:

  CASE_MATCHER   — "Zebra Hunt"
    Input : symptom cluster (common + atypical markers)
    Search: PubMed Case Reports with that exact combination
    Output: Ranked rare diagnoses with supporting case evidence
    Rationale: Standard models default to common diagnoses ("horses").
               Case reports contain the rare presentations ("zebras").

  EBM_VALIDATOR  — Evidence-Based Medicine coach for residents
    Input : SOAP assessment + plan sections
    Search: Systematic Reviews / Meta-analyses / RCTs (last 24 months)
    Output: Latest evidence with divergence callouts vs the proposed plan
    Rationale: Textbooks go stale; PubMed tracks evidence in real time.

  DDI_MONITOR    — Drug-Drug Interaction surveillance
    Input : current medication list (+ optional new medications)
    Search: Recent case reports + pharmacology studies for each pair
    Output: Novel/rare interactions not yet in standard DDI databases
    Rationale: Genomics & off-label combinations produce new DDIs faster
               than DrugBank / Epocrates stay current.

All queries are assembled as valid PubMed query syntax so the user can
copy-paste them into PubMed directly for verification.
"""

from __future__ import annotations

import itertools
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from .pubmed_client import PubMedClient, PubMedArticle

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class SearchMode(str, Enum):
    CASE_MATCHER = "case_matcher"
    EBM_VALIDATOR = "ebm_validator"
    DDI_MONITOR = "ddi_monitor"


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class PubMedSearchResult:
    """Structured result from any synthesis agent search."""
    mode: SearchMode
    query_used: str               # exact PubMed query string
    articles: list[PubMedArticle]
    summary: str                  # 2–4 sentence plain-language synthesis
    key_findings: list[str]       # bullet points extracted from abstracts
    divergences: list[str]        # for EBM_VALIDATOR: where plan differs from evidence
    rare_diagnoses: list[str]     # for CASE_MATCHER: candidate rare diagnoses surfaced
    ddi_alerts: list[str]         # for DDI_MONITOR: novel interaction signals
    citation_list: list[str]      # APA-ish citations

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "query_used": self.query_used,
            "articles": [a.to_dict() for a in self.articles],
            "summary": self.summary,
            "key_findings": self.key_findings,
            "divergences": self.divergences,
            "rare_diagnoses": self.rare_diagnoses,
            "ddi_alerts": self.ddi_alerts,
            "citation_list": self.citation_list,
        }


# ── Synthesis Agent ───────────────────────────────────────────────────────────

class PubMedSynthesisAgent:
    """
    Translates clinical data into targeted PubMed queries and synthesises results.

    Heavy lifting (abstract NLU) is delegated to MedGemma when available;
    when not available the agent uses deterministic heuristics so it degrades
    gracefully with zero extra dependencies.
    """

    def __init__(self, medgemma_agent=None):
        """
        Args:
            medgemma_agent: optional MedGemmaAgent / VLLMModelManager instance.
                            When present, abstracts are summarised by MedGemma.
                            When None, a keyword extraction heuristic is used.
        """
        self.client = PubMedClient()
        self.medgemma = medgemma_agent

    # ══════════════════════════════════════════════════════════════════════════
    # Mode 1 — Case Matcher (Zebra Hunt)
    # ══════════════════════════════════════════════════════════════════════════

    def case_matcher(
        self,
        common_symptoms: list[str],
        atypical_markers: list[str],
        patient_age: int | None = None,
        patient_gender: str | None = None,
        max_results: int = 5,
    ) -> PubMedSearchResult:
        """
        Search PubMed Case Reports for rare diagnoses matching an unusual
        symptom combination.

        Strategy:
          1. Build a PubMed query combining all symptoms + "Case Reports" filter
          2. If too granular (zero results), progressively relax by removing
             low-frequency atypical markers one at a time
          3. Parse returned abstracts for candidate diagnoses
          4. Optionally ask MedGemma to rank and explain them

        Args:
            common_symptoms  : Frequent complaints (e.g. ["cough", "fatigue"])
            atypical_markers : The "weird" flags (e.g. ["tongue discoloration", "night sweats"])
            patient_age      : Used to add age context to query
            patient_gender   : "male" / "female" — adds demographic filter
            max_results      : Max articles to fetch

        Returns:
            PubMedSearchResult with rare_diagnoses list populated
        """
        all_symptoms = common_symptoms + atypical_markers

        # Build primary query
        query = self._build_symptom_query(all_symptoms, pub_type="Case Reports")
        articles = self.client.search_and_fetch(
            query, max_results=max_results, pub_type_filter="Case Reports"
        )

        # Progressive relaxation if no results
        if not articles and atypical_markers:
            logger.info("Zebra hunt: relaxing query — removing atypical markers one-by-one")
            for i in range(len(atypical_markers) - 1, -1, -1):
                relaxed_symptoms = common_symptoms + atypical_markers[:i]
                if not relaxed_symptoms:
                    break
                query = self._build_symptom_query(relaxed_symptoms, pub_type="Case Reports")
                articles = self.client.search_and_fetch(
                    query, max_results=max_results, pub_type_filter="Case Reports"
                )
                if articles:
                    break

        # If still nothing, try without pub_type filter but add "rare" or "unusual"
        if not articles:
            query = self._build_symptom_query(
                common_symptoms + atypical_markers[:2], pub_type=None
            ) + ' AND (rare OR unusual OR atypical)'
            articles = self.client.search_and_fetch(query, max_results=max_results)

        rare_diagnoses = self._extract_diagnoses_from_articles(articles)
        key_findings = self._extract_key_sentences(articles, keywords=atypical_markers)
        summary = self._synthesise_summary(articles, mode=SearchMode.CASE_MATCHER)

        return PubMedSearchResult(
            mode=SearchMode.CASE_MATCHER,
            query_used=query,
            articles=articles,
            summary=summary,
            key_findings=key_findings,
            divergences=[],
            rare_diagnoses=rare_diagnoses,
            ddi_alerts=[],
            citation_list=[a.to_citation() for a in articles],
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Mode 2 — EBM Validator
    # ══════════════════════════════════════════════════════════════════════════

    def ebm_validator(
        self,
        assessment: str,
        plan: str,
        max_results: int = 5,
        date_years_back: int = 2,
    ) -> PubMedSearchResult:
        """
        Validate a physician's / resident's treatment plan against the latest
        PubMed evidence (Systematic Reviews, Meta-analyses, RCTs).

        Args:
            assessment  : SOAP Assessment section text
            plan        : SOAP Plan section text
            max_results : Max articles to return
            date_years_back: Only look at papers from the last N years

        Returns:
            PubMedSearchResult with divergences list populated
        """
        # Extract conditions and treatments from text
        conditions = self._extract_conditions(assessment)
        interventions = self._extract_interventions(plan)

        query = self._build_ebm_query(conditions, interventions)
        articles = self.client.search_and_fetch(
            query,
            max_results=max_results,
            date_years_back=date_years_back,
            sort="pub+date",
        )

        # Fallback: broader query on conditions only
        if not articles and conditions:
            query = self._build_ebm_query(conditions[:2], [])
            articles = self.client.search_and_fetch(
                query,
                max_results=max_results,
                date_years_back=date_years_back,
                sort="pub+date",
            )

        divergences = self._detect_plan_divergences(plan, articles)
        key_findings = self._extract_key_sentences(articles, keywords=conditions + interventions)
        summary = self._synthesise_summary(articles, mode=SearchMode.EBM_VALIDATOR)

        return PubMedSearchResult(
            mode=SearchMode.EBM_VALIDATOR,
            query_used=query,
            articles=articles,
            summary=summary,
            key_findings=key_findings,
            divergences=divergences,
            rare_diagnoses=[],
            ddi_alerts=[],
            citation_list=[a.to_citation() for a in articles],
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Mode 3 — DDI Monitor
    # ══════════════════════════════════════════════════════════════════════════

    def ddi_monitor(
        self,
        current_medications: list[str],
        new_medications: list[str] | None = None,
        max_results_per_pair: int = 2,
        date_years_back: int = 3,
    ) -> PubMedSearchResult:
        """
        Scan PubMed for novel / rare drug-drug interactions not yet captured
        in standard DDI databases.

        Args:
            current_medications  : Patient's existing medication list
            new_medications      : Newly added medications (higher priority scan)
            max_results_per_pair : Articles fetched for each drug pair
            date_years_back      : Recency window (newer = more novel)

        Returns:
            PubMedSearchResult with ddi_alerts list populated
        """
        new_meds = new_medications or []
        all_meds_clean = [self._clean_drug_name(m) for m in current_medications + new_meds]
        all_meds_clean = list(dict.fromkeys(m for m in all_meds_clean if m))  # deduplicate

        # Prioritise pairs involving new medications
        if new_meds:
            new_clean = [self._clean_drug_name(m) for m in new_meds]
            priority_pairs = [
                (n, c) for n in new_clean
                for c in all_meds_clean if c != n
            ]
            other_pairs = list(itertools.combinations(
                [m for m in all_meds_clean if m not in new_clean], 2
            ))
            pairs = priority_pairs + other_pairs
        else:
            pairs = list(itertools.combinations(all_meds_clean, 2))

        # Cap total pairs to avoid excessive API calls
        pairs = pairs[:12]

        all_articles: list[PubMedArticle] = []
        queries_used: list[str] = []
        seen_pmids: set[str] = set()

        for drug_a, drug_b in pairs:
            query = self._build_ddi_query(drug_a, drug_b)
            articles = self.client.search_and_fetch(
                query,
                max_results=max_results_per_pair,
                date_years_back=date_years_back,
                sort="pub+date",
            )
            for art in articles:
                if art.pmid not in seen_pmids:
                    all_articles.append(art)
                    seen_pmids.add(art.pmid)
            queries_used.append(query)

        ddi_alerts = self._extract_ddi_signals(all_articles, all_meds_clean)
        key_findings = self._extract_key_sentences(all_articles, keywords=all_meds_clean)
        summary = self._synthesise_summary(all_articles, mode=SearchMode.DDI_MONITOR)

        return PubMedSearchResult(
            mode=SearchMode.DDI_MONITOR,
            query_used=" | ".join(queries_used[:3]) + ("..." if len(queries_used) > 3 else ""),
            articles=all_articles,
            summary=summary,
            key_findings=key_findings,
            divergences=[],
            rare_diagnoses=[],
            ddi_alerts=ddi_alerts,
            citation_list=[a.to_citation() for a in all_articles],
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Convenience: run all three modes in one call
    # ══════════════════════════════════════════════════════════════════════════

    def full_analysis(
        self,
        symptoms: list[str],
        assessment: str,
        plan: str,
        medications: list[str],
        new_medications: list[str] | None = None,
        atypical_markers: list[str] | None = None,
        max_results: int = 3,
    ) -> dict[str, PubMedSearchResult]:
        """
        Run all three modes and return their results in a single dict.
        Designed to be called after SOAP generation to enrich the note.
        """
        results: dict[str, PubMedSearchResult] = {}

        if symptoms:
            atypical = atypical_markers or []
            common = [s for s in symptoms if s not in atypical]
            results["case_matcher"] = self.case_matcher(
                common_symptoms=common or symptoms,
                atypical_markers=atypical,
                max_results=max_results,
            )

        if assessment or plan:
            results["ebm_validator"] = self.ebm_validator(
                assessment=assessment,
                plan=plan,
                max_results=max_results,
            )

        if medications:
            results["ddi_monitor"] = self.ddi_monitor(
                current_medications=medications,
                new_medications=new_medications,
                max_results_per_pair=1,
            )

        return results

    # ══════════════════════════════════════════════════════════════════════════
    # Query builders
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _build_symptom_query(symptoms: list[str], pub_type: str | None) -> str:
        """Build a PubMed query from a symptom list."""
        # Quote multi-word symptoms and add Title/Abstract field tag
        terms = [
            f'"{s.strip()}"[Title/Abstract]' if " " in s.strip() else f'{s.strip()}[Title/Abstract]'
            for s in symptoms[:6]   # cap to avoid overly narrow queries
        ]
        q = " AND ".join(terms)
        if pub_type:
            q += f' AND "{pub_type}"[Publication Type]'
        return q

    @staticmethod
    def _build_ebm_query(conditions: list[str], interventions: list[str]) -> str:
        """Build an EBM query from conditions + interventions."""
        condition_terms = [
            f'"{c}"[MeSH Terms] OR "{c}"[Title/Abstract]'
            for c in conditions[:3]
        ]
        interv_terms = [
            f'"{i}"[Title/Abstract]'
            for i in interventions[:3]
        ]
        pub_types = (
            '"Systematic Review"[Publication Type] OR '
            '"Meta-Analysis"[Publication Type] OR '
            '"Randomized Controlled Trial"[Publication Type]'
        )
        parts = []
        if condition_terms:
            parts.append("(" + " OR ".join(condition_terms) + ")")
        if interv_terms:
            parts.append("(" + " OR ".join(interv_terms) + ")")
        parts.append(f"({pub_types})")
        return " AND ".join(parts)

    @staticmethod
    def _build_ddi_query(drug_a: str, drug_b: str) -> str:
        """Build a DDI query for a pair of drugs."""
        return (
            f'"{drug_a}"[Title/Abstract] AND "{drug_b}"[Title/Abstract] '
            f'AND ("drug interaction"[MeSH Terms] OR "adverse effects"[Subheading] '
            f'OR "drug-drug interaction"[Title/Abstract])'
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Extraction heuristics
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _clean_drug_name(drug: str) -> str:
        """Strip dosage info from medication strings, return generic name."""
        # Remove dosage: "Metformin 1000mg" → "Metformin"
        cleaned = re.sub(r'\s+\d+\s*(?:mg|mcg|g|units?|ml|mg/ml).*', '', drug, flags=re.IGNORECASE)
        # Remove route: "Lisinopril oral" → "Lisinopril"
        cleaned = re.sub(r'\s+(?:oral|iv|im|sc|topical|inhaler|tablet|capsule).*', '', cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    @staticmethod
    def _extract_conditions(text: str) -> list[str]:
        """Extract medical conditions from SOAP assessment text."""
        # Common patterns: "diagnosis of X", "X diagnosed", "known X", proper-noun conditions
        conditions: list[str] = []
        # Capitalised multi-word medical terms (2-4 words)
        for m in re.finditer(r'\b([A-Z][a-z]+(?:\s+[a-z]+){0,3})\b', text):
            term = m.group(1).strip()
            if len(term) > 4 and term not in conditions:
                conditions.append(term)
        # Common acronyms
        for m in re.finditer(r'\b(COPD|CHF|CAD|DM2?|HTN|CKD|GERD|IBD|AF|PE|DVT|UTI|URTI|URI)\b', text):
            term = m.group(1)
            if term not in conditions:
                conditions.append(term)
        return conditions[:8]

    @staticmethod
    def _extract_interventions(plan: str) -> list[str]:
        """Extract treatments / tests / medications from SOAP plan text."""
        interventions: list[str] = []
        # Keywords following order/start/continue
        for m in re.finditer(
            r'(?:order|start|prescribe|continue|initiate|obtain|perform)\s+([\w\s\-]+?)(?:[.,\n]|$)',
            plan, re.IGNORECASE
        ):
            item = m.group(1).strip()[:60]
            if 3 < len(item) < 60 and item not in interventions:
                interventions.append(item)
        return interventions[:6]

    @staticmethod
    def _extract_diagnoses_from_articles(articles: list[PubMedArticle]) -> list[str]:
        """
        Heuristically extract rare disease names from case report titles/abstracts.
        Looks for patterns like "diagnosis of X", "consistent with X", "rare case of X".
        """
        diagnoses: list[str] = []
        patterns = [
            r'(?:diagnosis|diagnose[ds]|presenting\s+as|consistent\s+with|'
            r'rare\s+case\s+of|unusual\s+case\s+of|report\s+of|'
            r'manifestation\s+of)\s+(?:a\s+|an\s+|the\s+)?([A-Z][^.,:;\n]{3,60})',
            r'(?:final\s+diagnosis|confirmed\s+diagnosis)[:\s]+([A-Z][^.,:;\n]{3,60})',
        ]
        for article in articles:
            text = f"{article.title} {article.abstract}"
            for pat in patterns:
                for m in re.finditer(pat, text, re.IGNORECASE):
                    diag = m.group(1).strip()
                    if diag not in diagnoses and len(diag) > 5:
                        diagnoses.append(diag)
            # Also pull MeSH descriptors that look like diagnoses
            for mesh in article.mesh_terms:
                if (len(mesh) > 5 and mesh not in diagnoses
                        and not mesh.lower().startswith(("symptoms", "humans", "male", "female", "adult"))):
                    diagnoses.append(mesh)
        return diagnoses[:10]

    @staticmethod
    def _extract_key_sentences(
        articles: list[PubMedArticle],
        keywords: list[str],
        max_sentences: int = 8,
    ) -> list[str]:
        """
        Extract the most relevant sentences from abstracts containing any keyword.
        """
        key_sents: list[str] = []
        kw_lower = [k.lower() for k in keywords if k]
        for article in articles:
            for sentence in re.split(r'(?<=[.!?])\s+', article.abstract):
                sent_lower = sentence.lower()
                if any(kw in sent_lower for kw in kw_lower):
                    cleaned = sentence.strip()
                    if len(cleaned) > 30 and cleaned not in key_sents:
                        key_sents.append(f"[PMID {article.pmid}] {cleaned}")
                        if len(key_sents) >= max_sentences:
                            return key_sents
        return key_sents

    @staticmethod
    def _detect_plan_divergences(plan: str, articles: list[PubMedArticle]) -> list[str]:
        """
        Heuristic: look for evidence in abstracts that contradicts or updates
        common plan elements.
        """
        divergences: list[str] = []
        outdated_signals = [
            # (old practice keyword, newer recommendation signal)
            ("bedrest", "early mobilisation"),
            ("bed rest", "early mobilisation"),
            ("long-term antibiotics", "short-course"),
            ("prolonged", "short-course antibiotic"),
            ("low-fat diet", "Mediterranean diet"),
            ("routine", "evidence suggests avoiding"),
        ]
        plan_lower = plan.lower()
        for art in articles:
            abs_lower = art.abstract.lower()
            for old_kw, new_kw in outdated_signals:
                if old_kw in plan_lower and new_kw in abs_lower:
                    divergences.append(
                        f"Plan mentions '{old_kw}' but PMID {art.pmid} suggests "
                        f"'{new_kw}' may be more current. Review: {art.pubmed_url}"
                    )
        # Flag if standard of care update words appear
        for art in articles:
            for phrase in ("updated guideline", "new guideline", "revised recommendation",
                           "no longer recommended", "not recommended"):
                if phrase in art.abstract.lower():
                    divergences.append(
                        f"Guideline update signal in PMID {art.pmid}: "
                        f"\"{art.title[:80]}\" — verify against current plan."
                    )
                    break
        return list(dict.fromkeys(divergences))[:6]   # deduplicate, cap at 6

    @staticmethod
    def _extract_ddi_signals(
        articles: list[PubMedArticle],
        medications: list[str],
    ) -> list[str]:
        """Extract drug interaction alert sentences from DDI articles."""
        alerts: list[str] = []
        signal_phrases = [
            "increased risk", "elevated levels", "toxicity", "contraindicated",
            "avoid concomitant", "reduce dose", "monitor closely", "QT prolongation",
            "serotonin syndrome", "bleeding risk", "nephrotoxicity", "hepatotoxicity",
            "interaction between", "co-administration", "adverse event",
        ]
        med_lower = [m.lower() for m in medications if m]
        for art in articles:
            for sentence in re.split(r'(?<=[.!?])\s+', art.abstract):
                sent_lower = sentence.lower()
                meds_in_sent = sum(1 for m in med_lower if m in sent_lower)
                signals_in_sent = sum(1 for s in signal_phrases if s in sent_lower)
                if meds_in_sent >= 2 and signals_in_sent >= 1:
                    cleaned = sentence.strip()
                    if len(cleaned) > 30:
                        alerts.append(f"[PMID {art.pmid}] {cleaned}")
        return alerts[:8]

    def _synthesise_summary(
        self,
        articles: list[PubMedArticle],
        mode: SearchMode,
    ) -> str:
        """
        Generate a 2–4 sentence plain-language summary.
        Uses MedGemma if available; falls back to a deterministic template summary.
        """
        if not articles:
            return f"No relevant PubMed literature found for this {mode.value.replace('_', ' ')} query."

        count = len(articles)
        years = sorted({a.pub_year for a in articles if a.pub_year}, reverse=True)
        year_range = f"{years[-1]}–{years[0]}" if len(years) > 1 else (years[0] if years else "unknown")
        journals = list(dict.fromkeys(a.journal for a in articles if a.journal))[:3]
        titles_preview = "; ".join(a.title[:60] for a in articles[:3])

        if mode == SearchMode.CASE_MATCHER:
            base = (
                f"Found {count} case report(s) ({year_range}) from {', '.join(journals[:2])} "
                f"matching the symptom cluster. "
                f"Representative cases include: {titles_preview}. "
                f"These may offer diagnostic clues for atypical presentations. "
                f"Review abstracts for clinical parallels before ruling out rare conditions."
            )
        elif mode == SearchMode.EBM_VALIDATOR:
            base = (
                f"Retrieved {count} high-level evidence article(s) ({year_range}). "
                f"Publications include: {titles_preview}. "
                f"Cross-reference the plan sections flagged below with these findings "
                f"to ensure alignment with current guidelines."
            )
        else:  # DDI_MONITOR
            base = (
                f"Scanned {count} pharmacology/case article(s) ({year_range}) for novel interactions. "
                f"Articles: {titles_preview}. "
                f"Check the DDI alerts below for signals not yet in standard interaction databases."
            )

        # If MedGemma is available, ask it to improve the summary
        if self.medgemma is not None:
            try:
                abstracts_text = "\n\n".join(
                    f"Title: {a.title}\nAbstract: {a.abstract[:400]}"
                    for a in articles[:3]
                )
                prompt = (
                    f"You are a clinical librarian. Summarise the following PubMed abstracts "
                    f"in 3 sentences for a physician (mode: {mode.value}). "
                    f"Focus on actionable clinical takeaways. Do not add information not in the abstracts.\n\n"
                    f"{abstracts_text}"
                )
                if hasattr(self.medgemma, "chat"):
                    summary = self.medgemma.chat(prompt)
                    if summary and len(summary) > 50:
                        return summary.strip()
            except Exception as e:
                logger.debug("MedGemma summary fallback: %s", e)

        return base


# ── Singleton ─────────────────────────────────────────────────────────────────
_synthesis_agent: PubMedSynthesisAgent | None = None


def get_synthesis_agent(medgemma_agent=None) -> PubMedSynthesisAgent:
    """Get or create the PubMedSynthesisAgent singleton."""
    global _synthesis_agent
    if _synthesis_agent is None:
        _synthesis_agent = PubMedSynthesisAgent(medgemma_agent=medgemma_agent)
    elif medgemma_agent is not None and _synthesis_agent.medgemma is None:
        _synthesis_agent.medgemma = medgemma_agent
    return _synthesis_agent
