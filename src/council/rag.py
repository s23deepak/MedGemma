"""
Clinical note chunking and semantic retrieval for Diagnostic Council context compression.

Uses sentence-transformers (if installed) for semantic embeddings.
Falls back to TF-IDF with numpy (always available) if sentence-transformers is absent.

Optional install:
    uv pip install "sentence-transformers>=2.2.0"
Or add the rag extra:
    uv pip install "medgemma-assistant[rag]"
"""
from __future__ import annotations

import re
import numpy as np

# ── Embedder singleton ────────────────────────────────────────────────────────

_embedder = None
_embedder_checked = False


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
    """
    enc = _get_embedder()
    if enc is not None:
        return enc.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return _tfidf_embed(texts)


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
