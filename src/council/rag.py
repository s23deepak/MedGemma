"""
Clinical note chunking and semantic retrieval for Diagnostic Council context compression.

Uses sentence-transformers (if installed) for semantic embeddings.
Falls back to TF-IDF with numpy (always available) if sentence-transformers is absent.

Optional install:
    uv pip install "sentence-transformers>=2.2.0"
Or add the rag extra:
    uv pip install "medgemma-assistant[rag]"

Enhanced features (metadata, recency re-ranking, source provenance)
--------------------------------------------------------------------
- NoteMetadata: structured provenance for each clinical note
- chunk_note_with_metadata(): yield (chunk_text, NoteMetadata) pairs
- retrieve_with_provenance(): return RankedChunk list with scores and source info
- Recency re-ranking: notes authored more recently receive a configurable score
  boost so the last physician note surfaces above a week-old nursing note
- Author-role weighting: physician/attending notes ranked above nursing/aide notes
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np

# ── Embedder singleton ────────────────────────────────────────────────────────

_embedder = None
_embedder_checked = False

# ── Embedding cache (sentence-transformers only; TF-IDF is batch-dependent) ───

_embedding_cache: OrderedDict[str, list] = OrderedDict()
_MAX_CACHE_SIZE = 500


# ── Metadata and provenance types ─────────────────────────────────────────────

# Author-role priority weights (higher = more authoritative)
_ROLE_WEIGHTS: dict[str, float] = {
    "attending":   1.0,
    "physician":   1.0,
    "hospitalist": 1.0,
    "resident":    0.85,
    "fellow":      0.85,
    "np":          0.75,
    "pa":          0.75,
    "nursing":     0.60,
    "nurse":       0.60,
    "aide":        0.40,
    "tech":        0.40,
}


@dataclass
class NoteMetadata:
    """Provenance information for a single clinical note."""
    source:      str = "unknown"   # e.g. "Admission H&P", "Progress Note 2024-03-12"
    author_role: str = "unknown"   # one of _ROLE_WEIGHTS keys or freetext
    note_date:   str = ""          # ISO-8601 date string (YYYY-MM-DD) or ""
    note_type:   str = "note"      # "admission", "progress", "discharge", "consult", "nursing"

    @property
    def role_weight(self) -> float:
        """Return the authority weight for this author's role."""
        role_lower = self.author_role.lower()
        for key, weight in _ROLE_WEIGHTS.items():
            if key in role_lower:
                return weight
        return 0.70  # default for unknown roles

    @property
    def recency_days(self) -> float | None:
        """
        Days elapsed since note_date relative to today.
        Returns None if note_date is empty or unparseable.
        """
        if not self.note_date:
            return None
        try:
            dt = datetime.strptime(self.note_date, "%Y-%m-%d")
            today = datetime.now(timezone.utc).replace(tzinfo=None)
            return max(0.0, (today - dt).days)
        except ValueError:
            return None


@dataclass
class RankedChunk:
    """A retrieved chunk with its relevance score and source provenance."""
    text:      str
    score:     float            # combined semantic + recency + role score
    position:  int              # original position in the source note
    metadata:  NoteMetadata = field(default_factory=NoteMetadata)

    def to_cited_text(self) -> str:
        """Return the chunk text prefixed with a compact source citation."""
        parts = []
        if self.metadata.source and self.metadata.source != "unknown":
            parts.append(self.metadata.source)
        if self.metadata.note_date:
            parts.append(self.metadata.note_date)
        if self.metadata.author_role and self.metadata.author_role != "unknown":
            parts.append(self.metadata.author_role)
        citation = " | ".join(parts)
        if citation:
            return f"[{citation}]\n{self.text}"
        return self.text


def _sha256_hex(text: str) -> str:
    """Return a SHA-256 hex digest of the given text (used as cache key)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _get_embedder():
    """Try to load a SentenceTransformer once; cache result (None if unavailable)."""
    global _embedder, _embedder_checked
    if _embedder_checked:
        return _embedder
    _embedder_checked = True
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
        print("[RAG] sentence-transformers loaded (all-MiniLM-L6-v2)")
    except Exception as exc:
        print(f"[RAG] sentence-transformers unavailable ({exc}); using TF-IDF fallback")
        _embedder = None
    return _embedder


# ── Chunking ──────────────────────────────────────────────────────────────────

def chunk_note(text: str, chunk_size: int = 250, overlap: int = 50) -> list[str]:
    """
    Split a clinical note into overlapping sentence-aware chunks.

    Args:
        text:       Raw clinical note text (admission H&P, progress note, etc.).
        chunk_size: Approximate maximum words per chunk.
        overlap:    Words carried over from the previous chunk to preserve context.

    Returns:
        List of text chunks (at least one element).
    """
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sentence in sentences:
        words = sentence.split()
        if current_len + len(words) > chunk_size and current:
            chunks.append(" ".join(current))
            # Carry tail of current chunk into next for continuity
            tail = current[-overlap:] if len(current) > overlap else current[:]
            current = tail
            current_len = len(current)
        current.extend(words)
        current_len += len(words)

    if current:
        chunks.append(" ".join(current))

    return chunks or [text]


# ── Embedding ─────────────────────────────────────────────────────────────────

def _tfidf_embed(texts: list[str]) -> np.ndarray:
    """
    Compute L2-normalised TF-IDF vectors using only numpy (zero extra deps).
    Effective for medical text because clinical terminology is highly distinctive.
    """
    tokenized = [t.lower().split() for t in texts]
    vocab = sorted({w for doc in tokenized for w in doc})
    if not vocab:
        return np.zeros((len(texts), 1), dtype=np.float32)

    v2i = {w: i for i, w in enumerate(vocab)}
    tf = np.zeros((len(texts), len(vocab)), dtype=np.float32)
    for i, doc in enumerate(tokenized):
        for w in doc:
            if w in v2i:
                tf[i, v2i[w]] += 1.0
        if doc:
            tf[i] /= len(doc)  # term frequency normalisation

    # Inverse document frequency
    df = (tf > 0).sum(axis=0)
    idf = np.log((len(texts) + 1.0) / (df + 1.0)) + 1.0
    mat = tf * idf

    # L2 normalise so cosine similarity == dot product
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def embed(texts: list[str]) -> np.ndarray:
    """
    Embed a list of texts.

    Returns L2-normalised vectors so that cosine similarity == dot product.
    Uses sentence-transformers (semantic) if installed, else TF-IDF (lexical).

    When sentence-transformers is available, results are cached per-text using
    SHA-256 keys with an LRU eviction policy (max _MAX_CACHE_SIZE entries).
    TF-IDF embeddings are NOT cached because they are batch-dependent (the
    vocabulary is built from all texts together, so the same text produces a
    different vector in different batches).
    """
    enc = _get_embedder()
    if enc is None:
        # TF-IDF path: batch-dependent, cannot cache per text
        return _tfidf_embed(texts)

    # sentence-transformers path: stable per-text embeddings → cacheable
    keys = [_sha256_hex(t) for t in texts]
    uncached_indices = [i for i, k in enumerate(keys) if k not in _embedding_cache]

    if uncached_indices:
        uncached_texts = [texts[i] for i in uncached_indices]
        new_embeddings = enc.encode(
            uncached_texts, convert_to_numpy=True, normalize_embeddings=True
        )
        for pos, idx in enumerate(uncached_indices):
            key = keys[idx]
            if len(_embedding_cache) >= _MAX_CACHE_SIZE:
                _embedding_cache.popitem(last=False)  # evict oldest (LRU)
            _embedding_cache[key] = new_embeddings[pos].tolist()

    # Reassemble in original order from cache
    return np.array([_embedding_cache[k] for k in keys], dtype=np.float32)


# ── Retrieval ─────────────────────────────────────────────────────────────────

def retrieve(query: str, chunks: list[str], top_k: int = 5) -> list[str]:
    """
    Retrieve the top-k most relevant chunks for a diagnostic query.

    Chunks are returned in their original narrative order (not score order) so
    the assembled context reads as a coherent clinical excerpt rather than
    a list of disconnected fragments.

    Args:
        query:  The retrieval query, typically the joined symptom list.
        chunks: Candidate chunks produced by chunk_note().
        top_k:  Maximum number of chunks to return.

    Returns:
        Up to top_k chunks sorted by original position.
    """
    if not chunks:
        return []
    if len(chunks) <= top_k:
        return chunks

    # Embed query + all chunks in one batch (efficient for both backends)
    all_texts = [query] + chunks
    embeddings = embed(all_texts)
    query_emb = embeddings[0]
    chunk_embs = embeddings[1:]

    # Cosine similarity (vectors are already L2-normalised  →  sim = dot product)
    scores = chunk_embs @ query_emb
    top_idx = np.argsort(scores)[::-1][:top_k]

    # Re-sort by original position to preserve clinical narrative flow
    return [chunks[i] for i in sorted(top_idx)]


def compress_note(
    raw_note: str,
    symptoms: list[str],
    top_k: int = 5,
    chunk_size: int = 250,
    overlap: int = 50,
) -> str:
    """
    High-level helper: chunk a clinical note and retrieve the most relevant excerpts.

    Returns a single string of concatenated relevant chunks separated by '---'.
    Returns empty string if raw_note is empty.
    """
    if not raw_note or not raw_note.strip():
        return ""
    query = " ".join(symptoms)
    chunks = chunk_note(raw_note, chunk_size=chunk_size, overlap=overlap)
    selected = retrieve(query, chunks, top_k=top_k)
    return "\n---\n".join(selected)


# ── Negation-aware retrieval ───────────────────────────────────────────────────

try:
    from src.clinical.negation import get_negation_detector as _get_neg_detector
    _NEGATION_AVAILABLE = True
except ImportError:
    _NEGATION_AVAILABLE = False
    _get_neg_detector = None  # type: ignore[assignment]


def _extract_findings_with_model(
    raw_note: str,
    agent,
) -> tuple[list[str], list[str]] | None:
    """
    Ask the model to extract clinical findings and their assertion status
    directly from the raw note.

    Returns (affirmed, negated) lists, or None if the call or JSON parsing
    fails — the caller falls back to NegEx on None.

    Supports both agent types:
    - VLLMModelManager  → agent.generate_medgemma(prompt, ...)
    - MedGemmaAgent     → agent.chat(prompt)
    """
    prompt = (
        "Extract every clinical symptom and finding mentioned in the note below.\n"
        "For each item, classify it as 'affirmed' (present/positive) or "
        "'negated' (denied/absent/negative).\n"
        "Return ONLY valid JSON — no prose, no markdown — in this exact format:\n"
        '{"findings": [{"term": "chest pain", "status": "affirmed"}, ...]}\n\n'
        f"Note:\n{raw_note}"
    )
    try:
        if hasattr(agent, "generate_medgemma"):
            raw = agent.generate_medgemma(prompt, temperature=0.0, max_tokens=512)
        elif hasattr(agent, "chat"):
            raw = agent.chat(prompt)
        else:
            return None

        # Model may wrap JSON in prose — fish out the first {...} block
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None

        data = json.loads(match.group())
        findings = data.get("findings", [])
        affirmed = [f["term"] for f in findings if f.get("status") == "affirmed"]
        negated  = [f["term"] for f in findings if f.get("status") == "negated"]
        return affirmed, negated

    except Exception:
        return None


def compress_note_negation_aware(
    raw_note: str,
    symptoms: list[str],
    top_k: int = 5,
    chunk_size: int = 250,
    overlap: int = 50,
    agent=None,
) -> str:
    """
    Negation-aware variant of compress_note().

    Polarity detection priority
    ---------------------------
    1. Model extraction (agent provided): MedGemma extracts every finding
       directly from the raw note with affirmed/negated labels — handles
       clinical shorthand, abbreviations, and contextual negation that
       regex-based NegEx misses.
    2. NegEx fallback: deterministic pipeline when no agent is available
       (SIMULATED_MODE, offline, or if the model extraction call fails).
    3. Bare fallback: compress_note() when neither is available.

    Steps after polarity is resolved
    ---------------------------------
    3. Build the embedding query from affirmed terms only.
    4. Over-fetch (top_k × 2) chunks from the note.
    5. Post-filter: drop chunks that assertively mention a negated term
       (NegEx applied per-chunk; skipped when NegEx is unavailable).
    6. Return top_k surviving chunks in original narrative order.
    """
    if not raw_note or not raw_note.strip():
        return ""
    if not symptoms:
        return compress_note(raw_note, symptoms, top_k=top_k,
                             chunk_size=chunk_size, overlap=overlap)

    # ── Step 1+2: resolve polarity ────────────────────────────────────────────
    affirmed: list[str] = []
    negated:  list[str] = []

    extracted = _extract_findings_with_model(raw_note, agent) if agent is not None else None

    if extracted is not None:
        affirmed, negated = extracted
    elif _NEGATION_AVAILABLE:
        detector = _get_neg_detector()
        affirmed = detector.filter_affirmed(raw_note, symptoms)
        negated  = [s for s in symptoms if s not in set(affirmed)]
    else:
        return compress_note(raw_note, symptoms, top_k=top_k,
                             chunk_size=chunk_size, overlap=overlap)

    # ── Step 3: build query — fallback to all symptoms if nothing affirmed ────
    query = " ".join(affirmed) if affirmed else " ".join(symptoms)

    # ── Step 4: chunk + over-fetch ────────────────────────────────────────────
    chunks = chunk_note(raw_note, chunk_size=chunk_size, overlap=overlap)
    fetch_k = min(len(chunks), top_k * 2)
    candidates = retrieve(query, chunks, top_k=fetch_k)

    # ── Step 5: post-filter chunks that assertively mention a negated term ────
    #    NegEx is applied per-chunk regardless of which polarity source was used.
    if negated and _NEGATION_AVAILABLE:
        detector = _get_neg_detector()
        clean: list[str] = []
        for chunk in candidates:
            falsely_affirmed = detector.filter_affirmed(chunk, negated)
            if not falsely_affirmed:
                clean.append(chunk)
        # Safety: never return empty
        candidates = clean if clean else candidates

    # ── Step 6: take top_k in narrative order ─────────────────────────────────
    return "\n---\n".join(candidates[:top_k])


# ── Metadata-aware chunking ────────────────────────────────────────────────────

def chunk_note_with_metadata(
    raw_note: str,
    metadata: NoteMetadata,
    chunk_size: int = 250,
    overlap: int = 50,
) -> list[tuple[str, NoteMetadata]]:
    """
    Chunk a clinical note and attach the same NoteMetadata to every chunk.

    Returns:
        List of (chunk_text, metadata) pairs.
    """
    chunks = chunk_note(raw_note, chunk_size=chunk_size, overlap=overlap)
    return [(chunk, metadata) for chunk in chunks]


# ── Re-ranked provenance-aware retrieval ──────────────────────────────────────

def retrieve_with_provenance(
    query: str,
    chunks_with_meta: list[tuple[str, NoteMetadata]],
    top_k: int = 5,
    recency_weight: float = 0.15,
    role_weight: float = 0.10,
) -> list[RankedChunk]:
    """
    Retrieve the most relevant chunks with recency and author-role re-ranking.

    Scoring formula per chunk:
        final_score = semantic_sim
                      + recency_weight * recency_boost(days_old)
                      + role_weight   * role_authority(author_role)

    Recency boost decays from 1.0 (today) to 0.0 at 365 days:
        recency_boost = max(0.0, 1.0 - days_old / 365)

    Retrieved chunks are returned in original narrative order (re-sorted by
    position) to preserve clinical coherence.

    Args:
        query:             Diagnostic query (typically joined symptom list).
        chunks_with_meta:  List of (chunk_text, NoteMetadata) pairs.
        top_k:             Maximum chunks to return.
        recency_weight:    Additive weight applied to recency boost component.
        role_weight:       Additive weight applied to author-role authority.

    Returns:
        Up to top_k RankedChunk objects sorted by original note position.
    """
    if not chunks_with_meta:
        return []
    if len(chunks_with_meta) <= top_k:
        return [
            RankedChunk(text=c, score=1.0, position=i, metadata=m)
            for i, (c, m) in enumerate(chunks_with_meta)
        ]

    texts = [c for c, _ in chunks_with_meta]
    metas = [m for _, m in chunks_with_meta]

    # Semantic similarity
    all_texts = [query] + texts
    embeddings = embed(all_texts)
    query_emb  = embeddings[0]
    chunk_embs = embeddings[1:]
    sem_scores = chunk_embs @ query_emb  # shape (N,), already L2-normalised

    # Build combined scores
    combined = np.array(sem_scores, dtype=np.float64)
    for i, meta in enumerate(metas):
        # Recency boost
        days = meta.recency_days
        if days is not None:
            recency_boost = max(0.0, 1.0 - days / 365.0)
            combined[i] += recency_weight * recency_boost

        # Authority boost
        combined[i] += role_weight * meta.role_weight

    top_idx = np.argsort(combined)[::-1][:top_k]

    # Re-sort by original position to maintain narrative flow
    selected = sorted(top_idx)
    return [
        RankedChunk(
            text=texts[i],
            score=float(combined[i]),
            position=i,
            metadata=metas[i],
        )
        for i in selected
    ]


def compress_note_with_provenance(
    raw_note: str,
    symptoms: list[str],
    metadata: NoteMetadata | None = None,
    top_k: int = 5,
    chunk_size: int = 250,
    overlap: int = 50,
    recency_weight: float = 0.15,
    role_weight: float = 0.10,
) -> str:
    """
    High-level helper: chunk, re-rank, and assemble context with source citations.

    Each retrieved chunk is prefixed with a [source | date | role] citation so
    the downstream LLM can link every claim to a source document.

    Returns empty string if raw_note is empty.
    """
    if not raw_note or not raw_note.strip():
        return ""

    meta = metadata or NoteMetadata()
    query = " ".join(symptoms)
    pairs = chunk_note_with_metadata(raw_note, meta, chunk_size=chunk_size, overlap=overlap)
    ranked = retrieve_with_provenance(
        query, pairs, top_k=top_k,
        recency_weight=recency_weight, role_weight=role_weight,
    )
    return "\n---\n".join(r.to_cited_text() for r in ranked)


def build_multi_note_context(
    notes: list[tuple[str, NoteMetadata]],
    symptoms: list[str],
    top_k: int = 5,
    chunk_size: int = 250,
    overlap: int = 50,
    recency_weight: float = 0.15,
    role_weight: float = 0.10,
) -> str:
    """
    Compress and rank chunks across multiple clinical notes simultaneously.

    Use this when a patient has several notes (admission H&P, daily progress notes,
    consult notes) and you want the top-K most relevant chunks across all of them,
    with recency and author-role re-ranking.

    Args:
        notes:   List of (raw_note_text, NoteMetadata) pairs — one per note.
        symptoms: Diagnostic query symptoms.
        top_k:   Total chunks to select across all notes combined.

    Returns:
        Single string of cited chunks, ready for prompt injection.
    """
    if not notes:
        return ""

    all_pairs: list[tuple[str, NoteMetadata]] = []
    for raw, meta in notes:
        if raw and raw.strip():
            all_pairs.extend(
                chunk_note_with_metadata(raw, meta, chunk_size=chunk_size, overlap=overlap)
            )

    if not all_pairs:
        return ""

    query = " ".join(symptoms)
    ranked = retrieve_with_provenance(
        query, all_pairs, top_k=top_k,
        recency_weight=recency_weight, role_weight=role_weight,
    )
    return "\n---\n".join(r.to_cited_text() for r in ranked)
