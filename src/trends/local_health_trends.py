"""Location-aware health trend signals for clinical context enrichment."""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .external_vocab import ExternalMedicalVocabProvider

logger = logging.getLogger(__name__)


@dataclass
class TrendSignal:
    """Represents one local health-relevant trend signal."""

    title: str
    source: str
    published: str
    link: str
    categories: list[str]

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "source": self.source,
            "published": self.published,
            "link": self.link,
            "categories": self.categories,
        }


class LocalHealthTrendsService:
    """Fetches local health/environment trend signals and correlates with symptoms."""

    _RSS_BASE = "https://news.google.com/rss/search"
    _CACHE_TTL = timedelta(hours=12)
    _LEXICON_PATH = Path(__file__).resolve().parents[2] / "data" / "medical_dictionary_terms.json"

    def __init__(self):
        self._cache: dict[str, dict] = {}
        self._external_vocab_provider = ExternalMedicalVocabProvider()
        lexicon = self._load_medical_lexicon()
        self._category_keywords = lexicon["event_categories"]
        self._symptom_category_map = lexicon["symptom_to_categories"]

    def refresh_location_trends(self, location: str, force: bool = False, max_items: int = 12) -> list[dict]:
        """Fetch latest trends for a location, using cache when fresh."""
        location_key = (location or "unknown").strip().lower()
        if not location_key:
            location_key = "unknown"

        now = datetime.now(timezone.utc)
        if not force and location_key in self._cache:
            cached_at = self._cache[location_key].get("fetched_at")
            if isinstance(cached_at, datetime) and now - cached_at <= self._CACHE_TTL:
                return self._cache[location_key]["signals"]

        signals = self._fetch_signals(location=location_key, max_items=max_items)
        self._cache[location_key] = {
            "fetched_at": now,
            "signals": signals,
        }
        return signals

    def correlate(self, location: str, symptoms: list[str], force_refresh: bool = False) -> dict:
        """
        Correlate patient symptoms with latest local trend signals.

        Suggestions only. Not diagnostic.
        """
        location_key = (location or "unknown").strip().lower()
        if not location_key:
            location_key = "unknown"

        signals = self.refresh_location_trends(location, force=force_refresh)
        normalized_symptoms = [s.strip().lower() for s in symptoms if s and s.strip()]

        symptom_categories: set[str] = set()
        for symptom in normalized_symptoms:
            for known_symptom, categories in self._symptom_category_map.items():
                if known_symptom in symptom or symptom in known_symptom:
                    symptom_categories.update(categories)

        matched_signals = []
        for signal in signals:
            categories = signal.get("categories", [])
            overlap = [category for category in categories if category in symptom_categories]
            if overlap:
                matched_signals.append(
                    {
                        "signal": signal,
                        "matched_categories": overlap,
                    }
                )

        matched_signals = matched_signals[:5]

        recommendation = None
        if matched_signals:
            recommendation = (
                "Local trend overlap identified. Consider exposure history, onset timeline, "
                "and objective testing to validate relevance before clinical decisions."
            )

        return {
            "location": location,
            "symptoms": normalized_symptoms,
            "matched_signal_count": len(matched_signals),
            "matched_signals": matched_signals,
            "recommendation": recommendation,
            "last_updated": self._cache.get(location_key, {}).get("fetched_at", datetime.now(timezone.utc)).isoformat(),
            "disclaimer": "Environmental/news correlations are supportive context only and require physician validation.",
        }

    def _fetch_signals(self, location: str, max_items: int = 12) -> list[dict]:
        """Fetch health-relevant signals from RSS for a location."""
        queries = self._build_location_queries(location)
        seen_keys: set[str] = set()
        signals: list[dict] = []

        for query in queries:
            items = self._fetch_rss_items(query)
            for item in items:
                title = (item.findtext("title") or "").strip()
                source = (item.findtext("source") or "Google News").strip()
                published = (item.findtext("pubDate") or "").strip()
                link = (item.findtext("link") or "").strip()
                description = self._clean_description(item.findtext("description") or "")

                if not self._is_location_relevant(
                    location=location,
                    title=title,
                    source=source,
                    description=description,
                    link=link,
                ):
                    continue

                categories = self._classify_categories(f"{title} {description}")
                if not categories:
                    continue

                item_key = link or f"{title}-{published}"
                if item_key in seen_keys:
                    continue
                seen_keys.add(item_key)

                signal = TrendSignal(
                    title=title,
                    source=source,
                    published=published,
                    link=link,
                    categories=categories,
                )
                signals.append(signal.to_dict())
                if len(signals) >= max_items:
                    return signals

        return signals

    def _classify_categories(self, text: str) -> list[str]:
        text_lower = text.lower()
        matched = []
        for category, keywords in self._category_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                matched.append(category)
        return matched

    def _build_location_queries(self, location: str) -> list[str]:
        location = (location or "unknown").strip()
        quoted_location = f'"{location}"'
        return [
            f"{quoted_location} (public health OR hospital OR clinic OR advisory OR emergency)",
            f"{quoted_location} (outbreak OR influenza OR covid OR rsv OR dengue OR measles)",
            f"{quoted_location} (wildfire OR smoke OR air quality OR heatwave OR boil water OR contamination)",
        ]

    def _fetch_rss_items(self, query: str) -> list[ET.Element]:
        params = {
            "q": query,
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        }
        url = f"{self._RSS_BASE}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=8) as response:
                raw_xml = response.read()
        except Exception as exc:
            logger.warning("Trend RSS fetch failed for query '%s': %s", query, exc)
            return []

        try:
            root = ET.fromstring(raw_xml)
        except ET.ParseError:
            logger.warning("Trend RSS parse failed for query '%s'", query)
            return []

        return root.findall(".//item")

    def _is_location_relevant(self, location: str, title: str, source: str, description: str, link: str) -> bool:
        location_text = (location or "").lower().strip()
        if not location_text:
            return True

        combined = f"{title} {source} {description} {link}".lower()
        if location_text in combined:
            return True

        parts = [part.strip() for part in re.split(r"[,\s]+", location_text) if len(part.strip()) >= 4]
        return any(part in combined for part in parts)

    def _clean_description(self, description: str) -> str:
        return re.sub(r"<[^>]+>", " ", description).strip()

    def _load_medical_lexicon(self) -> dict:
        default_lexicon = {
            "event_categories": {
                "respiratory_irritant": [],
                "infectious_outbreak": [],
                "heat_risk": [],
                "water_contamination": [],
            },
            "symptom_to_categories": {},
        }

        if self._LEXICON_PATH.exists():
            try:
                with self._LEXICON_PATH.open("r", encoding="utf-8") as handle:
                    lexicon = json.load(handle)
                default_lexicon["event_categories"].update(lexicon.get("event_categories", {}))
                default_lexicon["symptom_to_categories"].update(lexicon.get("symptom_to_categories", {}))
            except Exception as exc:
                logger.warning("Failed to load medical lexicon '%s': %s", self._LEXICON_PATH, exc)

        # External vocab source (NLM MeSH) - primary enrichment for real-world coverage.
        try:
            external_vocab = self._external_vocab_provider.get_vocab()
            external_categories = external_vocab.get("event_categories", {})
            for category, words in external_categories.items():
                existing = set(default_lexicon["event_categories"].get(category, []))
                existing.update(w.lower() for w in words if isinstance(w, str) and w.strip())
                default_lexicon["event_categories"][category] = sorted(existing)

            external_symptoms = external_vocab.get("symptom_synonyms", {})
            for symptom, synonyms in external_symptoms.items():
                symptom_key = symptom.lower().strip()
                if not symptom_key:
                    continue

                if symptom_key not in default_lexicon["symptom_to_categories"]:
                    if any(token in symptom_key for token in ["cough", "dyspnea", "breath", "wheez"]):
                        default_lexicon["symptom_to_categories"][symptom_key] = ["respiratory_irritant", "infectious_outbreak"]
                    elif any(token in symptom_key for token in ["fever", "chill"]):
                        default_lexicon["symptom_to_categories"][symptom_key] = ["infectious_outbreak"]
                    elif any(token in symptom_key for token in ["nausea", "vomit", "diarrhea", "gastro"]):
                        default_lexicon["symptom_to_categories"][symptom_key] = ["infectious_outbreak", "water_contamination"]
                    elif any(token in symptom_key for token in ["heat", "dehydration", "dizziness", "headache"]):
                        default_lexicon["symptom_to_categories"][symptom_key] = ["heat_risk"]

                base_categories = default_lexicon["symptom_to_categories"].get(symptom_key, [])
                for synonym in synonyms:
                    synonym_key = str(synonym).lower().strip()
                    if synonym_key and synonym_key not in default_lexicon["symptom_to_categories"]:
                        default_lexicon["symptom_to_categories"][synonym_key] = list(base_categories)
        except Exception as exc:
            logger.debug("External medical vocab enrichment unavailable: %s", exc)

        # Augment with ICD-10 dictionary terms from clinical intelligence
        try:
            from src.clinical.intelligence import ICD10_CODES

            for term in ICD10_CODES.keys():
                term_lower = term.lower()
                if any(token in term_lower for token in ["cough", "dyspnea", "shortness of breath", "wheez", "asthma", "copd"]):
                    default_lexicon["symptom_to_categories"].setdefault(term_lower, ["respiratory_irritant", "infectious_outbreak"])
                elif any(token in term_lower for token in ["fever", "fatigue"]):
                    default_lexicon["symptom_to_categories"].setdefault(term_lower, ["infectious_outbreak"])
                elif any(token in term_lower for token in ["nausea", "vomit", "diarrhea"]):
                    default_lexicon["symptom_to_categories"].setdefault(term_lower, ["infectious_outbreak", "water_contamination"])
        except Exception as exc:
            logger.debug("ICD10 lexicon augmentation unavailable: %s", exc)

        return default_lexicon


_trends_service: LocalHealthTrendsService | None = None


def get_local_health_trends_service() -> LocalHealthTrendsService:
    """Singleton accessor."""
    global _trends_service
    if _trends_service is None:
        _trends_service = LocalHealthTrendsService()
    return _trends_service
