"""
TicketBrain Multi-Source Retrieval

Two separate embedding indexes — never mixed in the same result set:
  ml/models/kb_index.npz      — Knowledge Base articles  (built by build_rag_index.py)
  ml/models/ticket_index.npz  — Resolved historical tickets (grows via knowledge_extraction.py)

Legacy fallback: if kb_index.npz is absent, falls back to rag_index.npz (old single index).

Each .npz stores:
  embeddings  (N, 384)  — L2-normalised float32
  metadata    (N,)      — object array of dicts

Keeping indexes separate means KB hits and ticket hits are never interleaved,
giving the prompt builder and the LLM clean, independently-labelled context blocks.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

_MODELS_DIR          = Path(__file__).parent.parent / "ml" / "models"
_KB_INDEX_PATH       = _MODELS_DIR / "kb_index.npz"
_TICKET_INDEX_PATH   = _MODELS_DIR / "ticket_index.npz"
_FEEDBACK_INDEX_PATH = _MODELS_DIR / "feedback_index.npz"
_LEGACY_PATH         = _MODELS_DIR / "rag_index.npz"


# ── Index loading ─────────────────────────────────────────────────────────────

def _load_index(path: Path) -> tuple[np.ndarray, list[dict]] | None:
    target = path
    if not target.exists():
        if path == _KB_INDEX_PATH and _LEGACY_PATH.exists():
            target = _LEGACY_PATH   # graceful fallback to old rag_index
        else:
            return None
    data = np.load(str(target), allow_pickle=True)
    emb  = data["embeddings"]
    if "metadata" in data:
        meta = list(data["metadata"])
    else:
        meta = json.loads(data["articles"].item())
    return emb, meta


@lru_cache(maxsize=1)
def _kb_index() -> tuple[np.ndarray, list[dict]] | None:
    return _load_index(_KB_INDEX_PATH)


@lru_cache(maxsize=1)
def _ticket_index() -> tuple[np.ndarray, list[dict]] | None:
    return _load_index(_TICKET_INDEX_PATH)


@lru_cache(maxsize=1)
def _feedback_index() -> tuple[np.ndarray, list[dict]] | None:
    return _load_index(_FEEDBACK_INDEX_PATH)


def _cosine_search(
    index: tuple[np.ndarray, list[dict]],
    query: np.ndarray,
    top_k: int,
    min_score: float = 0.0,
) -> list[dict]:
    embs, metas = index
    q      = query / (np.linalg.norm(query) + 1e-10)
    scores = embs @ q
    order  = np.argsort(scores)[::-1][:top_k]
    out    = []
    for i in order:
        if scores[i] < min_score:
            break
        item = dict(metas[i]) if isinstance(metas[i], dict) else metas[i]
        item["_similarity"] = float(scores[i])
        out.append(item)
    return out


# ── Public retrieval API ──────────────────────────────────────────────────────

def search_kb(query_embedding: np.ndarray, top_k: int = 3) -> list[dict]:
    """Return top_k KB articles closest to query_embedding. Each result has _similarity."""
    idx = _kb_index()
    return _cosine_search(idx, query_embedding, top_k) if idx else []


def search_tickets(query_embedding: np.ndarray, top_k: int = 3) -> list[dict]:
    """Return top_k resolved tickets closest to query_embedding. Each result has _similarity."""
    idx = _ticket_index()
    return _cosine_search(idx, query_embedding, top_k) if idx else []


def search_feedback(query_embedding: np.ndarray, top_k: int = 2) -> list[dict]:
    """Return top_k past assignment corrections closest to query_embedding."""
    idx = _feedback_index()
    return _cosine_search(idx, query_embedding, top_k, min_score=0.60) if idx else []


def top_kb_score(query_embedding: np.ndarray) -> float:
    """Maximum cosine similarity against the KB index. Used by the evaluator."""
    idx = _kb_index()
    if idx is None:
        return 0.50
    embs, _ = idx
    q = query_embedding / (np.linalg.norm(query_embedding) + 1e-10)
    return float((embs @ q).max())


# ── Index mutation ────────────────────────────────────────────────────────────

def _append_to_index(path: Path, cache_clear_fn, metadata: dict, embedding: np.ndarray):
    """Generic atomic append to any .npz index file."""
    emb = (embedding / (np.linalg.norm(embedding) + 1e-10)).reshape(1, -1).astype(np.float32)
    if path.exists():
        data    = np.load(str(path), allow_pickle=True)
        ex_emb  = data["embeddings"]
        ex_meta = list(data["metadata"])
    else:
        ex_emb  = np.zeros((0, emb.shape[1]), dtype=np.float32)
        ex_meta = []
    all_emb  = np.vstack([ex_emb, emb])
    all_meta = ex_meta + [metadata]
    np.savez(str(path), embeddings=all_emb, metadata=np.array(all_meta, dtype=object))
    cache_clear_fn()


def append_to_ticket_index(metadata: dict, embedding: np.ndarray):
    """
    Append one resolved ticket to ticket_index.npz.
    Clears lru_cache so the next search sees the new entry immediately.
    """
    _append_to_index(_TICKET_INDEX_PATH, _ticket_index.cache_clear, metadata, embedding)


def append_to_kb_index(metadata: dict, embedding: np.ndarray):
    """
    Append one KB document / article chunk to kb_index.npz.
    Called automatically when:
      - An HD Article is published/updated
      - A TB Document (PDF/DOCX) is uploaded and processed
      - A TB Knowledge Draft is approved and converted to an HD Article
    Clears lru_cache so the next search sees the new entry immediately.
    """
    _append_to_index(_KB_INDEX_PATH, _kb_index.cache_clear, metadata, embedding)


def append_to_feedback_index(metadata: dict, embedding: np.ndarray):
    """
    Append one agent correction record to feedback_index.npz.
    Called immediately when an agent submits an assignment correction.
    Clears lru_cache so the next ticket immediately benefits from this correction.
    """
    _append_to_index(_FEEDBACK_INDEX_PATH, _feedback_index.cache_clear, metadata, embedding)


def clear_caches():
    """Force all indexes to reload from disk on next access."""
    _kb_index.cache_clear()
    _ticket_index.cache_clear()
    _feedback_index.cache_clear()
