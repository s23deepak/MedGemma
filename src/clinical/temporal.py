"""
Clinical Temporal Context Tagger
=================================
Injects relative time markers into clinical text so that an AI model sees
events on a timeline rather than as a flat, unordered document.

Transformation example
----------------------
Input:
    "Patient admitted on 2024-03-10. On 2024-03-12 troponin rose to 2.4.
     Chest pain started 3 days ago. Echo performed yesterday showed EF 35%."

Output (with admission_date=2024-03-10):
    "[Hospital Day 1 | Admitted 2024-03-10]
     Patient admitted on [D+0]. On [D+2] troponin rose to 2.4.
     Chest pain started [D-3]. Echo performed [D-1] showed EF 35%."

Usage
-----
    from src.clinical.temporal import get_temporal_tagger

    tagger = get_temporal_tagger()

    # Tag with a known admission date
    result = tagger.tag(note_text, admission_date=datetime(2024, 3, 10))
    print(result.tagged_text)

    # Inject an LOS header into a prompt
    enriched_prompt = tagger.inject_los_context(prompt, admission_date, now=datetime.now())
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, date as date_type


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class TemporalTag:
    """Result of tagging one clinical text."""
    original_text: str
    tagged_text:   str
    anchor_date:   str              # ISO-8601 of the reference (admission) date
    events:        list[dict] = field(default_factory=list)


# ── Date patterns ─────────────────────────────────────────────────────────────
#
# Each entry: (compiled_regex, strptime_format_hint)
# The regex captures the date string; _parse_flexible then parses it.

_DATE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # ISO 8601:  2024-03-10
    (re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"), "%Y-%m-%d"),
    # US long:   03/10/2024
    (re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b"), "%m/%d/%Y"),
    # US short:  03/10/24
    (re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2})\b"), "%m/%d/%y"),
    # Written:   March 10, 2024  |  Mar 10 2024
    (re.compile(r"\b([A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4})\b"), None),
]

# Relative expressions → tag lambdas / strings
# Checked in order; first match wins per token.
_RELATIVE_PATTERNS: list[tuple[re.Pattern, object]] = [
    (re.compile(r"\b(\d+)\s+days?\s+ago\b",    re.IGNORECASE),
     lambda m: f"[D-{m.group(1)}]"),
    (re.compile(r"\b(\d+)\s+hours?\s+ago\b",   re.IGNORECASE),
     lambda m: f"[~{m.group(1)}h ago]"),
    (re.compile(r"\b(\d+)\s+weeks?\s+ago\b",   re.IGNORECASE),
     lambda m: f"[D-{int(m.group(1)) * 7}]"),
    (re.compile(r"\byesterday\b",              re.IGNORECASE), "[D-1]"),
    (re.compile(r"\bthis\s+morning\b",         re.IGNORECASE), "[~8h ago]"),
    (re.compile(r"\bthis\s+(?:afternoon|evening)\b", re.IGNORECASE), "[~4h ago]"),
    (re.compile(r"\blast\s+night\b",           re.IGNORECASE), "[~14h ago]"),
    (re.compile(r"\bon\s+admission\b",         re.IGNORECASE), "[D+0]"),
    (re.compile(r"\bon\s+presentation\b",      re.IGNORECASE), "[D+0]"),
    (re.compile(r"\bat\s+admission\b",         re.IGNORECASE), "[D+0]"),
    (re.compile(r"\btoday\b",                  re.IGNORECASE), "[D+0]"),
    (re.compile(r"\bnow\b",                    re.IGNORECASE), "[D+0]"),
    (re.compile(r"\bearlier\s+today\b",        re.IGNORECASE), "[~6h ago]"),
    (re.compile(r"\blast\s+week\b",            re.IGNORECASE), "[D-7]"),
    (re.compile(r"\btwo\s+weeks\s+ago\b",      re.IGNORECASE), "[D-14]"),
    (re.compile(r"\blast\s+month\b",           re.IGNORECASE), "[D-30]"),
    (re.compile(r"\bseveral\s+days?\s+ago\b",  re.IGNORECASE), "[D-3~7]"),
]

_STRPTIME_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%B %d %Y",   # March 10 2024
    "%B %d, %Y",  # March 10, 2024
    "%b %d %Y",   # Mar 10 2024
    "%b %d, %Y",  # Mar 10, 2024
    "%b. %d %Y",  # Mar. 10 2024
    "%b. %d, %Y", # Mar. 10, 2024
]


# ── Core tagger ───────────────────────────────────────────────────────────────

class ClinicalTemporalTagger:
    """
    Tags clinical free text with relative time markers anchored to a reference
    date (typically patient admission).

    Tagging strategy
    ~~~~~~~~~~~~~~~~
    1. Scan for all absolute date strings, parse them, compute delta from anchor.
       Replace with [D+N] or [D-N].
    2. Scan for relative expressions ("yesterday", "3 days ago") and replace with
       explicit [D-N] or [~Nh ago] markers.
    3. Prepend an LOS header: "[Hospital Day N | Admitted YYYY-MM-DD]".

    The anchor date defaults to the earliest date found in the text if not provided.
    """

    # ── Date parsing helpers ──────────────────────────────────────────────────

    @staticmethod
    def _parse_flexible(text: str) -> datetime | None:
        """Try all known strptime formats; return None on failure."""
        clean = text.strip().rstrip(",").replace(".", "").strip()
        for fmt in _STRPTIME_FORMATS:
            try:
                return datetime.strptime(clean, fmt)
            except ValueError:
                continue
        return None

    def _extract_dates(self, text: str) -> list[tuple[int, int, str, datetime]]:
        """
        Return a list of (start, end, matched_text, parsed_datetime) for every
        date found in text, sorted by position.
        """
        found: list[tuple[int, int, str, datetime]] = []
        seen_spans: set[tuple[int, int]] = set()

        for pattern, _ in _DATE_PATTERNS:
            for m in pattern.finditer(text):
                span = (m.start(), m.end())
                if span in seen_spans:
                    continue
                dt = self._parse_flexible(m.group(1))
                if dt:
                    found.append((m.start(), m.end(), m.group(1), dt))
                    seen_spans.add(span)

        return sorted(found, key=lambda x: x[0])

    # ── Public API ────────────────────────────────────────────────────────────

    def tag(
        self,
        text: str,
        admission_date: datetime | None = None,
    ) -> TemporalTag:
        """
        Tag clinical text with relative temporal markers.

        Args:
            text:           Raw clinical note, progress note, or dictation.
            admission_date: Patient admission datetime used as T=0.
                            If None, the earliest absolute date in the text
                            is used as the reference anchor.

        Returns:
            TemporalTag containing the transformed text and an event log.
        """
        date_occurrences = self._extract_dates(text)
        anchor = admission_date

        if anchor is None and date_occurrences:
            anchor = min(occ[3] for occ in date_occurrences)

        tagged = text
        events: list[dict] = []

        if anchor:
            # Replace absolute dates back-to-front to preserve character positions
            for start, end, raw, dt in reversed(date_occurrences):
                delta = (dt.date() - anchor.date()).days
                sign = "+" if delta >= 0 else ""
                tag = f"[D{sign}{delta}]"
                tagged = tagged[:start] + tag + tagged[end:]
                events.append({
                    "original": raw,
                    "parsed":   dt.strftime("%Y-%m-%d"),
                    "tag":      tag,
                    "delta_days": delta,
                })

        # Replace relative time expressions
        for pattern, replacement in _RELATIVE_PATTERNS:
            if callable(replacement):
                tagged = pattern.sub(replacement, tagged)
            else:
                tagged = pattern.sub(replacement, tagged)

        return TemporalTag(
            original_text=text,
            tagged_text=tagged,
            anchor_date=anchor.strftime("%Y-%m-%d") if anchor else "unknown",
            events=events,
        )

    def inject_los_context(
        self,
        text: str,
        admission_date: datetime,
        now: datetime | None = None,
    ) -> str:
        """
        Prepend a hospital-day header and run full temporal tagging.

        Example output prefix:
            [Hospital Day 3 | Admitted 2024-03-10 | Current: 2024-03-13]
        """
        now = now or datetime.now()
        los_days = (now.date() - admission_date.date()).days
        hd = los_days + 1  # Hospital Day 1 = admission day

        header = (
            f"[Hospital Day {hd} | "
            f"Admitted {admission_date.strftime('%Y-%m-%d')} | "
            f"Current: {now.strftime('%Y-%m-%d')}]\n"
        )
        result = self.tag(text, admission_date=admission_date)
        return header + result.tagged_text

    def build_timeline(
        self,
        events: list[dict],
        admission_date: datetime,
    ) -> str:
        """
        Build a concise chronological event string from a list of
        {"date": "YYYY-MM-DD", "description": "..."} dicts.

        Returns:
            A multi-line string ready to inject into a prompt.
        """
        lines: list[str] = []
        for ev in sorted(events, key=lambda e: e.get("date", "")):
            desc = ev.get("description", "")
            raw_date = ev.get("date", "")
            try:
                dt = datetime.strptime(raw_date, "%Y-%m-%d")
                delta = (dt.date() - admission_date.date()).days
                sign = "+" if delta >= 0 else ""
                tag = f"[D{sign}{delta}]"
            except ValueError:
                tag = f"[{raw_date}]"
            lines.append(f"  {tag}  {desc}")

        return "\n".join(lines) if lines else "  (no timeline events)"


# ── Singleton ─────────────────────────────────────────────────────────────────

_tagger: ClinicalTemporalTagger | None = None


def get_temporal_tagger() -> ClinicalTemporalTagger:
    """Return the process-wide singleton ClinicalTemporalTagger."""
    global _tagger
    if _tagger is None:
        _tagger = ClinicalTemporalTagger()
    return _tagger
