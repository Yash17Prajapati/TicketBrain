"""
Build TicketBrain embedding indexes.

Usage (run from bench root):
  # Build the KB index (from knowledge_base.py articles)
  ./env/bin/python apps/ticketbrain/ticketbrain/ml/build_rag_index.py

  # Backfill the ticket index from existing resolved tickets (needs Frappe context):
  bench --site ticketbrain.local execute ticketbrain.ai.knowledge_extraction.rebuild_ticket_index

Outputs:
  ticketbrain/ml/models/kb_index.npz     — Knowledge Base articles
  ticketbrain/ml/models/rag_index.npz    — legacy copy (kept for backward compat)
"""

import sys
from pathlib import Path

import numpy as np

_ROOT      = Path(__file__).parent.parent
_MODELS_DIR = _ROOT / "ml" / "models"
_EMBEDDING_DIR = _MODELS_DIR / "embedding_model"

sys.path.insert(0, str(_ROOT.parent.parent))


def build_kb_index():
    from ticketbrain.ai.knowledge_base import KB_ARTICLES
    from sentence_transformers import SentenceTransformer

    print(f"Loading embedding model from {_EMBEDDING_DIR} ...")
    if _EMBEDDING_DIR.exists() and any(_EMBEDDING_DIR.iterdir()):
        embedder = SentenceTransformer(str(_EMBEDDING_DIR))
    else:
        print("  (model dir empty — downloading all-MiniLM-L6-v2)")
        embedder = SentenceTransformer("all-MiniLM-L6-v2")

    texts = [f"{a['title']} — {a['content']}" for a in KB_ARTICLES]
    print(f"Embedding {len(texts)} KB articles ...")
    embeddings = embedder.encode(texts, convert_to_numpy=True, show_progress_bar=True)

    # L2-normalise so dot product == cosine similarity
    norms      = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = (embeddings / (norms + 1e-10)).astype(np.float32)

    # Write to kb_index.npz (primary) and rag_index.npz (legacy fallback)
    kb_path     = _MODELS_DIR / "kb_index.npz"
    legacy_path = _MODELS_DIR / "rag_index.npz"

    meta = np.array(KB_ARTICLES, dtype=object)
    np.savez_compressed(str(kb_path),     embeddings=embeddings, metadata=meta)
    np.savez_compressed(str(legacy_path), embeddings=embeddings, metadata=meta)

    print(f"Saved KB index  → {kb_path}  (shape: {embeddings.shape})")
    print(f"Saved legacy    → {legacy_path}")
    print(f"\nTotal KB articles indexed: {len(KB_ARTICLES)}")


if __name__ == "__main__":
    build_kb_index()
