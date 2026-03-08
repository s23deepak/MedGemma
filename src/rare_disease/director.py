"""
TTT-inspired Rare Disease Director.

Implements a pseudo-Test-Time-Training loop inspired by the 'discover' repo
(https://github.com/test-time-training/discover) — RL-at-test-time with a
reward-guided iterative search.

Instead of gradient updates, adaptation is performed through:
  1. Hypothesis generation (MedGemma LLM or ontology fallback)
  2. PubMed evidence retrieval per hypothesis
  3. Diagnostic reward computation (symptom coverage × evidence × coherence)
  4. If reward < threshold → expand search via ontology adjacency + LLM self-critique
  5. Repeat up to max_iterations → converge on best-supported rare disease candidates

The loop mimics TTT in that the "context" (retrieved evidence) adapts at
inference time to the specific case, guiding hypothesis refinement without
any weight update.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

from .models import (
    RareCaseInput,
    RareDiseaseHypothesis,
    RareDiseaseReport,
    TTTConvergenceMetadata,
)
from .ontology import (
    get_adjacent_diseases,
    get_disease_details,
    get_seed_hypotheses,
    list_all_diseases,
)
from .scorer import DiagnosticRewardScorer

logger = logging.getLogger(__name__)


@dataclass
class _CaseFingerprint:
    """Internal representation of clinical signals extracted from a case."""

    symptoms: list[str]
    atypical_markers: list[str]        # symptoms that stand out as unusual
    lab_anomalies: list[str]           # descriptive anomaly strings from labs dict
    imaging_keywords: list[str]        # key radiology terms
    demographics: dict[str, str]
    imaging_raw: str
    labs_raw: dict[str, str]


# ─────────────────────────────────────────────────────────────────────────── #
# Main director class                                                          #
# ─────────────────────────────────────────────────────────────────────────── #

class RareDiseaseDirector:
    """
    TTT-inspired iterative rare disease diagnostic director.

    Attributes:
        agent:             MedGemmaAgent or VLLMModelManager (or None for no-LLM mode)
        pubmed_agent:      PubMedSynthesisAgent (or None to skip PubMed)
        max_iterations:    Maximum TTT refinement loops (default 3)
        reward_threshold:  Convergence target reward (default 0.55)
    """

    DISCLAIMER = (
        "This analysis provides directional guidance only and does not constitute a "
        "diagnosis. All findings must be evaluated and validated by a qualified "
        "physician. Clinical context, physical examination, and physician judgment "
        "take precedence over AI suggestions."
    )

    def __init__(
        self,
        agent=None,
        pubmed_agent=None,
        max_iterations: int = 3,
        reward_threshold: float = 0.55,
    ) -> None:
        self.agent = agent
        self.pubmed_agent = pubmed_agent
        self.max_iterations = max_iterations
        self.reward_threshold = reward_threshold
        self._scorer = DiagnosticRewardScorer()

    # ------------------------------------------------------------------ #
    # Public entry point                                                   #
    # ------------------------------------------------------------------ #

    async def hunt(self, case: RareCaseInput) -> RareDiseaseReport:
        """Run the TTT-inspired rare disease hunt and return a direction report."""
        logger.info(
            "RareDiseaseDirector.hunt starting | symptoms=%d | iterations_max=%d",
            len(case.symptoms),
            self.max_iterations,
        )

        # Phase 0 — fingerprint
        fp = self._extract_fingerprint(case)

        # Phase 1 — seed hypotheses from ontology (fast, no API)
        seeds = get_seed_hypotheses(fp.symptoms)[:8]

        # Phase 2 — LLM hypothesis generation (merges with seeds)
        llm_hyps = await self._generate_hypotheses_llm(fp, seeds)
        all_hypotheses: list[str] = _dedup(seeds + llm_hyps)

        initial_count = len(all_hypotheses)
        expansion_rounds: list[str] = []
        evidence_cache: dict[str, dict] = {}
        scored: list[RareDiseaseHypothesis] = []
        converged = False
        iterations_done = 0

        # Phase 3 — TTT loop
        for iteration in range(self.max_iterations):
            iterations_done = iteration + 1
            logger.debug("TTT iteration %d | hypotheses=%d", iterations_done, len(all_hypotheses))

            # Fetch PubMed evidence for any new hypotheses
            new_names = [h for h in all_hypotheses if h not in evidence_cache]
            if new_names:
                new_evidence = await self._fetch_evidence_batch(new_names, fp)
                evidence_cache.update(new_evidence)

            # Score all hypotheses
            scored = self._score_all(all_hypotheses, evidence_cache, fp)

            best_reward = max(h.reward_score for h in scored) if scored else 0.0
            logger.debug("Best reward after iteration %d: %.3f", iterations_done, best_reward)

            if best_reward >= self.reward_threshold:
                converged = True
                break

            if iteration + 1 < self.max_iterations:
                # Expand search — the test-time adaptation step
                expanded, strategy = await self._expand_hypotheses(scored, fp, iteration)
                expansion_rounds.append(strategy)
                new_candidates = _dedup([h for h in expanded if h not in all_hypotheses])
                if not new_candidates:
                    converged = True  # nothing new to try
                    break
                all_hypotheses = all_hypotheses + new_candidates
            else:
                converged = best_reward >= self.reward_threshold

        # Final ranking — sort by reward desc, take top N
        top_n = case.max_hypotheses
        scored.sort(key=lambda h: h.reward_score, reverse=True)
        final = scored[:top_n]

        conv_reward = final[0].reward_score if final else 0.0

        return RareDiseaseReport(
            hypotheses=final,
            convergence=TTTConvergenceMetadata(
                iterations_performed=iterations_done,
                converged=converged,
                initial_hypotheses_count=initial_count,
                final_hypotheses_count=len(scored),
                convergence_reward=conv_reward,
                expansion_rounds=expansion_rounds,
            ),
            disclaimer=self.DISCLAIMER,
            generated_at=datetime.utcnow(),
        )

    # ------------------------------------------------------------------ #
    # Fingerprint extraction                                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_fingerprint(case: RareCaseInput) -> _CaseFingerprint:
        """Normalise and enrich the case into a structured fingerprint."""
        symptoms = [s.strip().lower() for s in case.symptoms if s.strip()]

        # Tag atypical markers: symptoms that sound unusual / unexpected
        atypical_keywords = {
            "unusual", "atypical", "rare", "unexpected", "young",
            "fluctuat", "recurrent", "relapsing", "episodic",
        }
        atypical = [
            s for s in symptoms
            if any(kw in s for kw in atypical_keywords)
        ]
        # Also flag demographics-based atypical markers
        age = case.demographics.get("age", "")
        sex = case.demographics.get("sex", "")
        if age and age.isdigit() and int(age) < 40:
            atypical.append(f"young patient (age {age})")

        # Extract lab anomalies as plain strings
        lab_anomalies: list[str] = []
        _ABNORMAL_HINTS = [
            "high", "low", "elevated", "decreased", "increased",
            "positive", "negative", "abnormal",
        ]
        for k, v in case.labs.items():
            v_lower = v.lower()
            if any(hint in v_lower for hint in _ABNORMAL_HINTS):
                lab_anomalies.append(f"{k}: {v}")
            else:
                # Try numeric detection — flag if looks non-normal
                nums = re.findall(r"[\d.]+", v)
                if nums:
                    lab_anomalies.append(f"{k}: {v}")

        # Imaging keywords (common radiology terms)
        imaging_raw = case.imaging_findings.lower()
        imaging_kws = [
            w for w in re.split(r"\W+", imaging_raw)
            if len(w) > 4
        ][:20]

        return _CaseFingerprint(
            symptoms=symptoms,
            atypical_markers=atypical[:6],
            lab_anomalies=lab_anomalies[:10],
            imaging_keywords=imaging_kws,
            demographics=case.demographics,
            imaging_raw=case.imaging_findings,
            labs_raw=case.labs,
        )

    # ------------------------------------------------------------------ #
    # LLM hypothesis generation                                            #
    # ------------------------------------------------------------------ #

    async def _generate_hypotheses_llm(
        self,
        fp: _CaseFingerprint,
        seeds: list[str],
    ) -> list[str]:
        """Ask MedGemma for additional rare disease hypotheses."""
        if self.agent is None:
            logger.debug("No agent available — skipping LLM hypothesis generation")
            return []

        seed_hint = ", ".join(seeds[:5]) if seeds else "none identified"
        demographic_str = (
            f"{fp.demographics.get('age', 'unknown')} y/o "
            f"{fp.demographics.get('sex', 'patient')}"
            if fp.demographics else "patient"
        )

        prompt = f"""You are a rare disease specialist. Given the following clinical presentation,
suggest up to 6 RARE diseases (incidence < 1:2000) that could explain the findings.
Focus on diseases that are commonly missed. Give only disease names as a JSON array.

Patient: {demographic_str}
Symptoms: {", ".join(fp.symptoms[:10])}
Atypical markers: {", ".join(fp.atypical_markers)}
Lab anomalies: {", ".join(fp.lab_anomalies[:5])}
Imaging: {fp.imaging_raw[:200] or "Not reported"}
Already considered: {seed_hint}

Respond with ONLY valid JSON, no explanation:
{{"rare_disease_candidates": ["Disease 1", "Disease 2", "Disease 3"]}}"""

        try:
            resp_raw = await asyncio.to_thread(self.agent.chat, prompt)
            resp_raw = resp_raw.strip()
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', resp_raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                candidates = data.get("rare_disease_candidates", [])
                if isinstance(candidates, list):
                    return [str(c).strip() for c in candidates if c]
        except Exception as exc:
            logger.warning("LLM hypothesis generation failed: %s", exc)

        return []

    # ------------------------------------------------------------------ #
    # PubMed evidence retrieval                                            #
    # ------------------------------------------------------------------ #

    async def _fetch_evidence_batch(
        self,
        hypothesis_names: list[str],
        fp: _CaseFingerprint,
    ) -> dict[str, dict]:
        """Fetch PubMed evidence for a batch of hypotheses."""
        if self.pubmed_agent is None:
            return {name: {} for name in hypothesis_names}

        results: dict[str, dict] = {}
        # Run sequentially to respect PubMed rate limits (3 req/s)
        for name in hypothesis_names:
            try:
                result = await asyncio.to_thread(
                    self.pubmed_agent.case_matcher,
                    symptoms=fp.symptoms[:6],
                    atypical_markers=[name] + fp.atypical_markers[:2],
                    max_results=5,
                )
                results[name] = result.__dict__ if hasattr(result, "__dict__") else result
            except Exception as exc:
                logger.warning("PubMed fetch failed for '%s': %s", name, exc)
                results[name] = {}
        return results

    # ------------------------------------------------------------------ #
    # Scoring                                                              #
    # ------------------------------------------------------------------ #

    def _score_all(
        self,
        hypothesis_names: list[str],
        evidence_cache: dict[str, dict],
        fp: _CaseFingerprint,
    ) -> list[RareDiseaseHypothesis]:
        """Score all hypotheses and return as RareDiseaseHypothesis objects."""
        scored: list[RareDiseaseHypothesis] = []
        for name in hypothesis_names:
            pubmed_result = evidence_cache.get(name, {})
            sc, es, co, reward = self._scorer.score_and_reward(
                hypothesis_name=name,
                symptoms=fp.symptoms,
                pubmed_result=pubmed_result,
                imaging=fp.imaging_raw,
                labs=fp.labs_raw,
            )
            matching = self._scorer.get_matching_features(
                name, fp.symptoms, fp.imaging_raw, fp.labs_raw
            )
            anti = self._scorer.get_anti_features(
                name, fp.symptoms, fp.imaging_raw, fp.labs_raw
            )
            details = get_disease_details(name)

            # Evidence tier based on evidence_strength
            if es >= 0.70:
                tier = "well-evidenced"
            elif es >= 0.40:
                tier = "some-evidence"
            else:
                tier = "speculative"

            # Pull citations from PubMed result
            citations: list[str] = []
            for article in (pubmed_result.get("articles") or [])[:3]:
                pmid = article.get("pubmed_id") or article.get("pmid", "")
                title = article.get("title", "")
                if pmid and title:
                    citations.append(f"PMID {pmid}: {title[:80]}")
                elif title:
                    citations.append(title[:80])

            # Reasoning string
            reasoning = _build_reasoning(name, sc, es, co, details, matching)

            scored.append(
                RareDiseaseHypothesis(
                    name=name,
                    icd10=details["icd10"] if details else "—",
                    reasoning=reasoning,
                    matching_features=matching,
                    anti_features=anti,
                    symptom_coverage=sc,
                    evidence_strength=es,
                    coherence_score=co,
                    reward_score=reward,
                    evidence_tier=tier,
                    confirmatory_tests=details["confirmatory_tests"] if details else [],
                    specialist_type=details["specialist_type"] if details else "Specialist",
                    urgency=details["urgency"] if details else "elective",
                    pubmed_citations=citations,
                )
            )
        return scored

    # ------------------------------------------------------------------ #
    # TTT expansion (the adaptation step)                                  #
    # ------------------------------------------------------------------ #

    async def _expand_hypotheses(
        self,
        scored: list[RareDiseaseHypothesis],
        fp: _CaseFingerprint,
        iteration: int,
    ) -> tuple[list[str], str]:
        """Expand the hypothesis pool when evidence is insufficient.

        iteration 0 → ontology adjacency expansion
        iteration 1+ → LLM self-critique expansion
        Returns (new_candidate_names, strategy_description)
        """
        if iteration == 0:
            # Round 1 expansion: adjacent diseases in the ontology
            top3 = [h.name for h in sorted(scored, key=lambda h: h.reward_score, reverse=True)[:3]]
            adjacent: list[str] = []
            for name in top3:
                adjacent.extend(get_adjacent_diseases(name))
            # Deduplicate against already-scored
            already = {h.name for h in scored}
            new = _dedup([a for a in adjacent if a not in already])
            strategy = f"iter{iteration + 1}:ontology-adjacency({','.join(top3[:2])})"
            return new[:6], strategy

        # Round 2+ expansion: LLM self-critique
        if self.agent is None:
            # Fallback: sample random ontology diseases
            all_known = set(h.name for h in scored)
            candidates = [d for d in list_all_diseases() if d not in all_known]
            strategy = f"iter{iteration + 1}:ontology-random-fallback"
            return candidates[:4], strategy

        top_scored = sorted(scored, key=lambda h: h.reward_score, reverse=True)[:3]
        top_summary = "\n".join(
            f"  - {h.name} (reward={h.reward_score:.2f}, "
            f"gaps={', '.join(h.anti_features[:2]) or 'none noted'})"
            for h in top_scored
        )
        unexplained = [s for s in fp.symptoms if not any(s in h.matching_features for h in top_scored)]
        unexplained_str = ", ".join(unexplained[:5]) or "all symptoms partially explained"

        prompt = f"""You are a rare disease specialist performing iterative test-time reasoning.
The following rare disease hypotheses were considered but have insufficient evidence or unexplained features:

{top_summary}

Unexplained symptoms: {unexplained_str}
Patient symptoms: {', '.join(fp.symptoms[:8])}
Lab anomalies: {', '.join(fp.lab_anomalies[:4])}

What OTHER rare diseases (incidence < 1:2000) could better explain these findings?
Respond with ONLY valid JSON:
{{"alternative_diseases": ["Disease A", "Disease B", "Disease C"]}}"""

        try:
            resp_raw = await asyncio.to_thread(self.agent.chat, prompt)
            json_match = re.search(r'\{.*\}', resp_raw, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                alternatives = data.get("alternative_diseases", [])
                if isinstance(alternatives, list):
                    already = {h.name for h in scored}
                    new = _dedup([str(a).strip() for a in alternatives if str(a).strip() not in already])
                    strategy = f"iter{iteration + 1}:llm-self-critique"
                    return new[:5], strategy
        except Exception as exc:
            logger.warning("LLM self-critique expansion failed: %s", exc)

        strategy = f"iter{iteration + 1}:expansion-failed"
        return [], strategy


# ─────────────────────────────────────────────────────────────────────────── #
# Helpers                                                                      #
# ─────────────────────────────────────────────────────────────────────────── #

def _dedup(names: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            result.append(n)
    return result


def _build_reasoning(
    name: str,
    sc: float,
    es: float,
    co: float,
    details: dict | None,
    matching: list[str],
) -> str:
    parts: list[str] = []
    if matching:
        parts.append(f"Consistent features: {', '.join(matching[:3])}.")
    if details:
        spec = details.get("specialist_type", "")
        if spec:
            parts.append(f"Specialist referral: {spec}.")
    parts.append(
        f"Diagnostic reward: {0.4 * sc + 0.4 * es + 0.2 * co:.2f} "
        f"(symptom coverage {sc:.0%}, evidence {es:.0%}, coherence {co:.0%})."
    )
    return " ".join(parts) if parts else f"Rare diagnosis {name} considered based on symptom cluster."


# ─────────────────────────────────────────────────────────────────────────── #
# Singleton                                                                    #
# ─────────────────────────────────────────────────────────────────────────── #

_director: RareDiseaseDirector | None = None


def get_rare_disease_director(
    max_iterations: int = 3,
    reward_threshold: float = 0.55,
) -> RareDiseaseDirector:
    """Return the module-level singleton RareDiseaseDirector."""
    global _director
    if _director is None:
        _director = RareDiseaseDirector(
            agent=None,
            pubmed_agent=None,
            max_iterations=max_iterations,
            reward_threshold=reward_threshold,
        )
    return _director
