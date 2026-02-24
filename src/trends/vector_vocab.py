"""Vector-based medical vocabulary enrichment utilities."""

from __future__ import annotations

import re
from collections import Counter

import numpy as np


class MedicalVocabVectorIndex:
    """Simple in-memory vector index for medical terms using hashed n-gram features."""

    def __init__(self, dimension: int = 512):
        self.dimension = dimension
        self._terms: list[str] = []
        self._matrix: np.ndarray | None = None

    def fit(self, terms: list[str]) -> None:
        cleaned = sorted({self._normalize_term(t) for t in terms if self._normalize_term(t)})
        self._terms = cleaned
        if not cleaned:
            self._matrix = None
            return

        vectors = [self._embed(term) for term in cleaned]
        matrix = np.vstack(vectors)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._matrix = matrix / norms

    def nearest(self, query_term: str, top_k: int = 6, min_score: float = 0.2) -> list[str]:
        if self._matrix is None or not self._terms:
            return []

        query = self._embed(self._normalize_term(query_term))
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            return []
        query = query / query_norm

        scores = self._matrix @ query
        sorted_idx = np.argsort(scores)[::-1]

        result: list[str] = []
        query_norm_term = self._normalize_term(query_term)
        for idx in sorted_idx:
            score = float(scores[idx])
            term = self._terms[int(idx)]
            if score < min_score:
                break
            if term == query_norm_term:
                continue
            result.append(term)
            if len(result) >= top_k:
                break
        return result

    def _embed(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dimension, dtype=np.float32)
        if not text:
            return vec

        tokens = self._tokenize(text)
        counts = Counter(tokens)
        for token, count in counts.items():
            idx = hash(token) % self.dimension
            vec[idx] += float(count)
        return vec

    def _tokenize(self, text: str) -> list[str]:
        words = re.findall(r"[a-z0-9]+", text.lower())
        grams: list[str] = []
        for word in words:
            grams.append(word)
            if len(word) >= 3:
                grams.extend(word[i : i + 3] for i in range(len(word) - 2))
        return grams

    def _normalize_term(self, text: str) -> str:
        return re.sub(r"\s+", " ", str(text).strip().lower())
