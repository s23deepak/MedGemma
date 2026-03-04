"""
Clinical Negation Detector
==========================
Classifies clinical assertions using a simplified NegEx-style algorithm.

Every extracted symptom / finding is labelled with one of four statuses:

  AFFIRMED   — currently present  ("patient has chest pain")
  NEGATED    — explicitly absent   ("denies chest pain", "no fever")
  UNCERTAIN  — hedged / rule-out  ("possible pneumonia", "r/o PE")
  HISTORICAL — prior / resolved    ("history of MI", "no longer on Warfarin")
  FAMILY     — family, not patient ("FH of diabetes")

Usage
-----
    from src.clinical.negation import get_negation_detector

    detector = get_negation_detector()

    # Filter a raw symptom list to affirmed-only:
    affirmed = detector.filter_affirmed(transcription_text, extracted_symptoms)

    # Annotate every sentence in a note:
    spans = detector.annotate(note_text)
    for span in spans:
        print(span.text[:60], "→", span.status.value, f"(trigger: '{span.trigger}')")
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache


# ── Assertion status ──────────────────────────────────────────────────────────

class AssertionStatus(str, Enum):
    AFFIRMED   = "affirmed"
    NEGATED    = "negated"
    UNCERTAIN  = "uncertain"
    HISTORICAL = "historical"
    FAMILY     = "family"


@dataclass(frozen=True)
class NegationSpan:
    """One annotated sentence from a clinical note."""
    text:    str
    status:  AssertionStatus
    trigger: str  # The word/phrase that triggered the classification


# ── Pattern definitions ───────────────────────────────────────────────────────
#
# Order of evaluation (highest precedence first):
#   family → historical → uncertain → negated → affirmed
#
# All patterns are compiled once at import time.

_FAMILY_RAW = [
    r"\bfamily\s+history\s+of\b",
    r"\bfh\s*[:\-]\b",
    r"\bfather\s+(?:has|had|with)\b",
    r"\bmother\s+(?:has|had|with)\b",
    r"\bsibling\s+(?:has|had|with)\b",
    r"\bbrother\s+(?:has|had|with)\b",
    r"\bsister\s+(?:has|had|with)\b",
    r"\bhereditary\b",
]

_HISTORICAL_RAW = [
    r"\bhistory\s+of\b",
    r"\bh/o\b",
    r"\bpmh\s*[:\-]\b",
    r"\bpast\s+(?:medical\s+)?history\b",
    r"\bremote\s+history\b",
    r"\bprevious(?:ly)?\b",
    r"\bprior\s+(?:to\b|history\b)?\b",
    r"\bno\s+longer\b",           # "no longer on Warfarin" — past state
    r"\bformerly\b",
    r"\bonce\s+had\b",
    r"\bresolved\b",
    r"\bdiscontinued\b",
    r"\bin\s+remission\b",
    r"\bpost[-\s](?:op|operative|procedure|hospital)\b",
]

_UNCERTAIN_RAW = [
    r"\bpossible(?:ly)?\b",
    r"\bprobable(?:ly)?\b",
    r"\bsuspect(?:ed)?\b",
    r"\brule\s+out\b",
    r"\br/?o\s+\b",               # r/o, r-o, ro
    r"\bquestion(?:able)?\b",
    r"\bpossibly\b",
    r"\bconsider(?:ing)?\b",
    r"\bapparent(?:ly)?\b",
    r"\bseems?\s+to\b",
    r"\bappears?\s+to\b",
    r"\bcould\s+(?:be|represent)\b",
    r"\bmay\s+(?:be|represent|indicate)\b",
    r"\bmight\s+(?:be|represent)\b",
    r"\bnot\s+(?:yet\s+)?confirmed\b",
    r"\bpending\s+(?:workup|results?|confirmation)\b",
    r"\bworking\s+diagnosis\b",
    r"\bdifferential\s+includes?\b",
    r"\bcan(?:not)?\s+exclude\b",
    r"\bunlikely\b",
]

_NEGATED_RAW = [
    r"\bno\b",
    r"\bnot\b",
    r"\bnever\b",
    r"\bdenies?\b",
    r"\bdenied\b",
    r"\bwithout\b",
    r"\bfree\s+of\b",
    r"\babsent\b",
    r"\bnegative\s+for\b",
    r"\bnone\b",
    r"\bneither\b",
    r"\bnor\b",
    r"\babsence\s+of\b",
    r"\bno\s+evidence\s+of\b",
    r"\bno\s+sign(?:s)?\s+of\b",
    r"\bun(?:remarkable|eventful|complicated)\b",
    r"\bwithin\s+normal\s+limits?\b",
    r"\bwnl\b",
    r"\bnad\b",                   # no acute distress
    r"\bnac\b",                   # no apparent change
    r"\bcleared?\b",              # "cleared for discharge"
    r"\bexcludes?\b",
    r"\bnon[-\s]?\w+\b",          # non-productive, non-tender, etc.
]

# Compile all patterns once
_FAMILY_PATS    = [re.compile(p, re.IGNORECASE) for p in _FAMILY_RAW]
_HISTORICAL_PATS = [re.compile(p, re.IGNORECASE) for p in _HISTORICAL_RAW]
_UNCERTAIN_PATS  = [re.compile(p, re.IGNORECASE) for p in _UNCERTAIN_RAW]
_NEGATED_PATS    = [re.compile(p, re.IGNORECASE) for p in _NEGATED_RAW]

# Sentence splitter
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n")


# ── Core detector ─────────────────────────────────────────────────────────────

class ClinicalNegationDetector:
    """
    Lightweight rule-based negation detector for clinical free text.

    Design choices
    ~~~~~~~~~~~~~~
    * No external dependencies — pure stdlib.
    * Sentence-level classification: find the sentence(s) containing a given
      clinical concept, classify each sentence, then merge with a
      "any affirmed → keep" policy to avoid over-aggressive filtering.
    * Patterns respect clinical shorthand (r/o, h/o, PMH, WNL, NAD, non-*).
    """

    @staticmethod
    def _classify_sentence(sentence: str) -> tuple[AssertionStatus, str]:
        """
        Return (AssertionStatus, trigger_word) for a single sentence.
        Evaluation order: family > historical > uncertain > negated > affirmed.
        """
        for pat in _FAMILY_PATS:
            m = pat.search(sentence)
            if m:
                return AssertionStatus.FAMILY, m.group(0)

        for pat in _HISTORICAL_PATS:
            m = pat.search(sentence)
            if m:
                return AssertionStatus.HISTORICAL, m.group(0)

        for pat in _UNCERTAIN_PATS:
            m = pat.search(sentence)
            if m:
                return AssertionStatus.UNCERTAIN, m.group(0)

        for pat in _NEGATED_PATS:
            m = pat.search(sentence)
            if m:
                return AssertionStatus.NEGATED, m.group(0)

        return AssertionStatus.AFFIRMED, ""

    def filter_affirmed(
        self,
        text: str,
        concepts: list[str],
        *,
        keep_uncertain: bool = False,
    ) -> list[str]:
        """
        Given clinical free text and a list of extracted concepts (symptoms,
        diagnoses, findings), return only those that are genuinely AFFIRMED.

        Args:
            text:           Raw clinical note / transcription.
            concepts:       Candidate concept strings to evaluate.
            keep_uncertain: If True, retain UNCERTAIN concepts alongside AFFIRMED.

        Returns:
            Filtered list of affirmed (and optionally uncertain) concepts.

        Safety policy
        ~~~~~~~~~~~~~
        If a concept appears in multiple sentences with mixed statuses,
        "any affirmed → keep" prevents false negatives (missing a real finding
        is more dangerous clinically than including a borderline one).
        """
        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
        affirmed: list[str] = []

        for concept in concepts:
            concept_lower = concept.lower()
            # Find sentences that contain this concept
            relevant = [s for s in sentences if concept_lower in s.lower()]

            if not relevant:
                # Concept not found in any sentence → include conservatively
                affirmed.append(concept)
                continue

            statuses = [self._classify_sentence(s)[0] for s in relevant]

            keep_statuses = {AssertionStatus.AFFIRMED}
            if keep_uncertain:
                keep_statuses.add(AssertionStatus.UNCERTAIN)

            if any(s in keep_statuses for s in statuses):
                affirmed.append(concept)

        return affirmed

    def annotate(self, text: str) -> list[NegationSpan]:
        """
        Annotate every sentence in text with its assertion status.

        Returns:
            List of NegationSpan objects, one per non-empty sentence.
        """
        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
        spans: list[NegationSpan] = []
        for sent in sentences:
            status, trigger = self._classify_sentence(sent)
            spans.append(NegationSpan(text=sent, status=status, trigger=trigger))
        return spans

    def summarise(self, text: str) -> dict[str, list[str]]:
        """
        Return a dict grouping sentences by assertion status.
        Useful for building structured clinical summaries.

            {
              "affirmed":   [...],
              "negated":    [...],
              "uncertain":  [...],
              "historical": [...],
              "family":     [...],
            }
        """
        groups: dict[str, list[str]] = {s.value: [] for s in AssertionStatus}
        for span in self.annotate(text):
            groups[span.status.value].append(span.text)
        return groups


# ── Singleton ─────────────────────────────────────────────────────────────────

_detector: ClinicalNegationDetector | None = None


def get_negation_detector() -> ClinicalNegationDetector:
    """Return the process-wide singleton ClinicalNegationDetector."""
    global _detector
    if _detector is None:
        _detector = ClinicalNegationDetector()
    return _detector
