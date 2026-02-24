"""External medical vocabulary enrichment for trend correlation.

Primary source: NLM MeSH Lookup API.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .vector_vocab import MedicalVocabVectorIndex

logger = logging.getLogger(__name__)


class ExternalMedicalVocabProvider:
    """Fetches and caches medical vocabulary expansions from external sources."""

    _MESH_LOOKUP_URL = "https://id.nlm.nih.gov/mesh/lookup/term"
    _CACHE_TTL = timedelta(hours=24)
    _DEFAULT_TIMEOUT_SECONDS = 1.5
    _CACHE_BACKEND_ENV = "MEDICAL_VOCAB_CACHE_BACKEND"
    _VECTOR_BACKEND_ENV = "MEDICAL_VOCAB_VECTOR_BACKEND"

    def __init__(self):
        self._memory_cache: dict | None = None
        self._memory_cache_time: datetime | None = None
        self._cache_file = Path(__file__).resolve().parents[2] / "data" / "medical_vocab_cache.json"

    def get_vocab(self) -> dict:
        """Return external vocabulary (cached) or empty fallback."""
        if os.environ.get("DISABLE_EXTERNAL_MEDICAL_VOCAB", "").lower() in {"1", "true", "yes"}:
            return {"event_categories": {}, "symptom_synonyms": {}}

        now = datetime.now(timezone.utc)
        if self._memory_cache and self._memory_cache_time and now - self._memory_cache_time <= self._CACHE_TTL:
            return self._memory_cache

        backend = self._cache_backend()

        cached = None
        if backend in {"auto", "firestore"}:
            cached = self._read_firestore_cache()
        if cached is None and backend in {"auto", "local"}:
            cached = self._read_disk_cache()

        if cached is not None:
            self._memory_cache = cached
            self._memory_cache_time = now
            return cached

        fetched = self._fetch_mesh_vocab()
        fetched = self._enrich_with_vector_similarity(fetched)
        if backend in {"auto", "firestore"}:
            self._write_firestore_cache(fetched)
        if backend in {"auto", "local"}:
            self._write_disk_cache(fetched)
        self._memory_cache = fetched
        self._memory_cache_time = now
        return fetched

    def _cache_backend(self) -> str:
        """Return selected backend: auto | firestore | local."""
        selected = os.environ.get(self._CACHE_BACKEND_ENV, "auto").strip().lower()
        if selected in {"firestore", "local", "auto"}:
            return selected
        return "auto"

    def _vector_backend(self) -> str:
        """Return selected vector backend: in_memory | none."""
        selected = os.environ.get(self._VECTOR_BACKEND_ENV, "in_memory").strip().lower()
        if selected in {"in_memory", "none"}:
            return selected
        return "in_memory"

    def _fetch_mesh_vocab(self) -> dict:
        category_seeds = {
            "respiratory_irritant": [
                "asthma",
                "dyspnea",
                "bronchitis",
                "air pollution",
                "smoke inhalation injury",
            ],
            "infectious_outbreak": [
                "influenza",
                "communicable diseases",
                "covid-19",
                "norovirus infections",
                "respiratory syncytial virus infections",
            ],
            "heat_risk": [
                "heat stress disorders",
                "heat stroke",
                "dehydration",
            ],
            "water_contamination": [
                "water pollution",
                "waterborne infections",
                "legionellosis",
                "gastroenteritis",
            ],
        }
        symptom_seeds = [
            "cough",
            "dyspnea",
            "shortness of breath",
            "wheezing",
            "fever",
            "chills",
            "nausea",
            "vomiting",
            "diarrhea",
            "fatigue",
            "dizziness",
            "headache",
        ]

        event_categories: dict[str, list[str]] = {}
        for category, seeds in category_seeds.items():
            expanded: set[str] = set()
            for seed in seeds:
                expanded.add(seed.lower())
                expanded.update(self._mesh_lookup_terms(seed))
            event_categories[category] = sorted(expanded)

        symptom_synonyms: dict[str, list[str]] = {}
        for symptom in symptom_seeds:
            expanded: set[str] = {symptom.lower()}
            expanded.update(self._mesh_lookup_terms(symptom))
            symptom_synonyms[symptom.lower()] = sorted(expanded)

        return {
            "event_categories": event_categories,
            "symptom_synonyms": symptom_synonyms,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "NLM MeSH Lookup API",
        }

    def _enrich_with_vector_similarity(self, vocab: dict) -> dict:
        """Expand vocab semantically using a vector similarity index."""
        if self._vector_backend() == "none":
            return vocab

        event_categories: dict[str, list[str]] = vocab.get("event_categories", {})
        symptom_synonyms: dict[str, list[str]] = vocab.get("symptom_synonyms", {})

        all_terms: set[str] = set()
        for words in event_categories.values():
            all_terms.update(str(w).lower() for w in words if str(w).strip())
        for words in symptom_synonyms.values():
            all_terms.update(str(w).lower() for w in words if str(w).strip())

        if not all_terms:
            return vocab

        index = MedicalVocabVectorIndex(dimension=512)
        index.fit(sorted(all_terms))

        enriched_categories: dict[str, list[str]] = {}
        for category, words in event_categories.items():
            expanded = set(str(w).lower() for w in words if str(w).strip())
            for word in list(expanded):
                expanded.update(index.nearest(word, top_k=4, min_score=0.3))
            enriched_categories[category] = sorted(expanded)

        enriched_symptoms: dict[str, list[str]] = {}
        for symptom, words in symptom_synonyms.items():
            expanded = set(str(w).lower() for w in words if str(w).strip())
            for word in list(expanded):
                expanded.update(index.nearest(word, top_k=3, min_score=0.35))
            enriched_symptoms[symptom] = sorted(expanded)

        vocab["event_categories"] = enriched_categories
        vocab["symptom_synonyms"] = enriched_symptoms
        vocab["vector_enrichment"] = {
            "backend": self._vector_backend(),
            "enabled": True,
        }
        return vocab

    def _mesh_lookup_terms(self, term: str, limit: int = 8) -> set[str]:
        params = {
            "label": term,
            "match": "contains",
            "limit": str(limit),
        }
        url = f"{self._MESH_LOOKUP_URL}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=self._DEFAULT_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            logger.debug("MeSH lookup failed for '%s': %s", term, exc)
            return set()

        found: set[str] = set()
        for row in payload:
            if isinstance(row, list) and row:
                label = str(row[0]).strip().lower()
                if label:
                    found.add(label)
        return found

    def _read_disk_cache(self) -> dict | None:
        if not self._cache_file.exists():
            return None
        try:
            with self._cache_file.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            fetched_at = payload.get("fetched_at")
            if not fetched_at:
                return None
            fetched_dt = datetime.fromisoformat(fetched_at)
            if fetched_dt.tzinfo is None:
                fetched_dt = fetched_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - fetched_dt > self._CACHE_TTL:
                return None
            return payload
        except Exception as exc:
            logger.debug("Medical vocab cache read failed: %s", exc)
            return None

    def _read_firestore_cache(self) -> dict | None:
        """Read cache from Firestore shared store."""
        try:
            from src.config.firebase_config import get_firestore_client, is_firebase_available

            if not is_firebase_available():
                return None

            db = get_firestore_client()
            if db is None:
                return None

            doc = db.collection("system_cache").document("medical_vocab_mesh").get()
            if not doc.exists:
                return None

            payload = doc.to_dict() or {}
            fetched_at = payload.get("fetched_at")
            if not fetched_at:
                return None

            fetched_dt = datetime.fromisoformat(str(fetched_at))
            if fetched_dt.tzinfo is None:
                fetched_dt = fetched_dt.replace(tzinfo=timezone.utc)

            if datetime.now(timezone.utc) - fetched_dt > self._CACHE_TTL:
                return None

            return payload
        except Exception as exc:
            logger.debug("Medical vocab Firestore cache read failed: %s", exc)
            return None

    def _write_disk_cache(self, payload: dict) -> None:
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            with self._cache_file.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.debug("Medical vocab cache write failed: %s", exc)

    def _write_firestore_cache(self, payload: dict) -> None:
        """Write cache to Firestore shared store."""
        try:
            from src.config.firebase_config import get_firestore_client, is_firebase_available

            if not is_firebase_available():
                return

            db = get_firestore_client()
            if db is None:
                return

            db.collection("system_cache").document("medical_vocab_mesh").set(payload)
        except Exception as exc:
            logger.debug("Medical vocab Firestore cache write failed: %s", exc)
