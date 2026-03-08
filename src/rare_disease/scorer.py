"""
Diagnostic reward scorer for the TTT-inspired rare disease director.

Implements the three reward dimensions:
  - symptom_coverage  : fraction of patient symptoms explained by this disease
  - evidence_strength : quality/quantity of PubMed evidence returned
  - coherence_score   : lab and imaging keyword alignment with disease profile

Final reward = 0.40 × symptom_coverage
             + 0.40 × evidence_strength
             + 0.20 × coherence_score
"""
from __future__ import annotations

import re

from .ontology import get_disease_details

_REWARD_WEIGHTS = (0.40, 0.40, 0.20)  # (coverage, evidence, coherence)


class DiagnosticRewardScorer:
    """Computes a [0, 1] diagnostic reward for a disease hypothesis."""

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def score(
        self,
        hypothesis_name: str,
        symptoms: list[str],
        pubmed_result: dict,
        imaging: str,
        labs: dict[str, str],
    ) -> tuple[float, float, float]:
        """Return (symptom_coverage, evidence_strength, coherence_score)."""
        details = get_disease_details(hypothesis_name)
        sc = self._symptom_coverage(symptoms, details, pubmed_result)
        es = self._evidence_strength(pubmed_result)
        co = self._coherence_score(details, imaging, labs)
        return round(sc, 3), round(es, 3), round(co, 3)

    def compute_reward(self, sc: float, es: float, co: float) -> float:
        """Weighted combination of the three score dimensions."""
        w_sc, w_es, w_co = _REWARD_WEIGHTS
        return round(w_sc * sc + w_es * es + w_co * co, 3)

    def score_and_reward(
        self,
        hypothesis_name: str,
        symptoms: list[str],
        pubmed_result: dict,
        imaging: str,
        labs: dict[str, str],
    ) -> tuple[float, float, float, float]:
        """Convenience: returns (sc, es, co, reward)."""
        sc, es, co = self.score(hypothesis_name, symptoms, pubmed_result, imaging, labs)
        return sc, es, co, self.compute_reward(sc, es, co)

    # ------------------------------------------------------------------ #
    # Symptom coverage                                                     #
    # ------------------------------------------------------------------ #

    def _symptom_coverage(
        self,
        patient_symptoms: list[str],
        details: dict | None,
        pubmed_result: dict,
    ) -> float:
        """Fraction of patient symptoms covered by the disease profile + PubMed text."""
        if not patient_symptoms:
            return 0.0

        # Build a bag of words from known disease symptom keywords
        disease_keywords: set[str] = set()
        if details:
            for sym in details.get("weighted_symptoms", {}):
                disease_keywords.update(sym.lower().split())
            for sym in details.get("trigger_symptoms", []):
                disease_keywords.update(sym.lower().split())

        # Also mine PubMed abstract text
        pubmed_text = _extract_pubmed_text(pubmed_result).lower()

        matched = 0
        for sym in patient_symptoms:
            sym_lower = sym.lower()
            sym_tokens = set(sym_lower.split())
            # Match against disease word bag
            if sym_tokens & disease_keywords:
                matched += 1
                continue
            # Match in PubMed text
            if sym_lower in pubmed_text or any(tok in pubmed_text for tok in sym_tokens if len(tok) > 4):
                matched += 1

        return matched / len(patient_symptoms)

    # ------------------------------------------------------------------ #
    # Evidence strength                                                    #
    # ------------------------------------------------------------------ #

    def _evidence_strength(self, pubmed_result: dict) -> float:
        """Evaluate quality/quantity of PubMed evidence.

        Scoring table:
          ≥5 articles with abstracts  → 0.90
          3–4 articles                → 0.75
          1–2 articles                → 0.55
          articles found but no abstracts → 0.30
          rare_diagnoses list returned → +0.05 bonus
          no results                  → 0.05
        """
        if not pubmed_result:
            return 0.05

        articles: list[dict] = pubmed_result.get("articles", [])
        n = len(articles)

        if n == 0:
            base = 0.05
        elif n >= 5:
            base = 0.90
        elif n >= 3:
            base = 0.75
        else:
            base = 0.55

        # Articles with non-empty abstract are higher quality
        with_abstract = sum(1 for a in articles if a.get("abstract", "").strip())
        if n > 0 and with_abstract < n / 2:
            base = max(0.05, base - 0.20)

        # Bonus if the zebra-hunt returned this as an explicit rare diagnosis
        rare_dx: list[str] = pubmed_result.get("rare_diagnoses", [])
        if rare_dx:
            base = min(1.0, base + 0.05)

        return round(base, 3)

    # ------------------------------------------------------------------ #
    # Coherence score                                                      #
    # ------------------------------------------------------------------ #

    def _coherence_score(
        self,
        details: dict | None,
        imaging: str,
        labs: dict[str, str],
    ) -> float:
        """How well do imaging/lab findings fit this disease's known profile?

        Strategy:
          - Extract mention keywords from imaging string and lab dict
          - Compare to weighted_symptoms in the ontology entry
          - Penalise for contraindication keywords present
        """
        if details is None:
            return 0.3  # unknown disease — neutral prior

        weighted_syms: dict[str, float] = details.get("weighted_symptoms", {})
        contraindications: list[str] = details.get("contraindications", [])

        # Build a combined clinical text from imaging + labs
        clinical_text = imaging.lower()
        for k, v in labs.items():
            clinical_text += f" {k.lower()} {v.lower()}"

        # Positive signal: weighted symptoms found in clinical text
        total_weight = 0.0
        matched_weight = 0.0
        for sym, weight in weighted_syms.items():
            total_weight += weight
            sym_lower = sym.lower()
            # Tokenised match
            tokens = [t for t in re.split(r"\W+", sym_lower) if len(t) > 3]
            if any(tok in clinical_text for tok in tokens):
                matched_weight += weight

        positive_signal = (matched_weight / total_weight) if total_weight > 0 else 0.3

        # Negative signal: contraindications present → penalise
        penalty = 0.0
        for contra in contraindications:
            c_tokens = [t for t in re.split(r"\W+", contra.lower()) if len(t) > 3]
            if c_tokens and all(tok in clinical_text for tok in c_tokens[:2]):
                penalty += 0.20  # each contra hit = −0.20

        return max(0.0, min(1.0, positive_signal - penalty))

    # ------------------------------------------------------------------ #
    # Feature extraction helpers                                           #
    # ------------------------------------------------------------------ #

    def get_matching_features(
        self,
        hypothesis_name: str,
        symptoms: list[str],
        imaging: str,
        labs: dict[str, str],
    ) -> list[str]:
        """Return which known disease features are present in the patient's data."""
        details = get_disease_details(hypothesis_name)
        if details is None:
            return []
        clinical_text = (
            " ".join(symptoms).lower()
            + " " + imaging.lower()
            + " " + " ".join(f"{k} {v}" for k, v in labs.items()).lower()
        )
        matched = []
        for sym in list(details.get("weighted_symptoms", {})) + details.get("trigger_symptoms", []):
            tokens = [t for t in re.split(r"\W+", sym.lower()) if len(t) > 3]
            if tokens and any(tok in clinical_text for tok in tokens):
                if sym not in matched:
                    matched.append(sym)
        return matched[:8]  # cap for readability

    def get_anti_features(
        self,
        hypothesis_name: str,
        symptoms: list[str],
        imaging: str,
        labs: dict[str, str],
    ) -> list[str]:
        """Return expected disease features that are absent (gaps) — the anti-features.

        Returns up to 4 high-weight symptoms from the ontology that are NOT
        present in the patient's data.
        """
        details = get_disease_details(hypothesis_name)
        if details is None:
            return []
        clinical_text = (
            " ".join(symptoms).lower()
            + " " + imaging.lower()
            + " " + " ".join(f"{k} {v}" for k, v in labs.items()).lower()
        )
        # Sort by weight descending, look for absent high-weight features
        weighted = sorted(
            details.get("weighted_symptoms", {}).items(),
            key=lambda kv: kv[1],
            reverse=True,
        )
        absent = []
        for sym, weight in weighted:
            if weight < 0.7:
                break  # only surface high-weight absent features
            tokens = [t for t in re.split(r"\W+", sym.lower()) if len(t) > 3]
            if tokens and not any(tok in clinical_text for tok in tokens):
                absent.append(f"{sym} (not documented)")
            if len(absent) >= 4:
                break
        return absent


# ------------------------------------------------------------------ #
# Helper                                                               #
# ------------------------------------------------------------------ #

def _extract_pubmed_text(pubmed_result: dict) -> str:
    """Flatten all article titles + abstracts into a single string."""
    if not pubmed_result:
        return ""
    parts = []
    for article in pubmed_result.get("articles", []):
        if article.get("title"):
            parts.append(article["title"])
        if article.get("abstract"):
            parts.append(article["abstract"])
    summary = pubmed_result.get("summary", "")
    if summary:
        parts.append(summary)
    return " ".join(parts)
