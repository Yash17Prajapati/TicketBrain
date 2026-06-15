"""
TicketBrain Document Processor

Extracts text from uploaded PDF / DOCX / TXT files, chunks it, embeds each chunk,
and appends everything to kb_index.npz so it is immediately searchable.

Called automatically from the TB Document after_insert hook — no manual step needed.
"""

from __future__ import annotations

import re
from pathlib import Path

import frappe

_CHUNK_SIZE    = 500   # characters per chunk
_CHUNK_OVERLAP = 80    # characters shared between consecutive chunks


# ── Public entry point ────────────────────────────────────────────────────────

def process_document(doc_name: str):
    """Extract, chunk, embed and index a TB Document. Run in background queue."""
    try:
        _do_process(doc_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Document processing failed")
        frappe.db.set_value("TB Document", doc_name, "status", "Failed")
        frappe.db.commit()


def _do_process(doc_name: str):
    doc = frappe.get_doc("TB Document", doc_name)
    frappe.db.set_value("TB Document", doc_name, "status", "Processing")
    frappe.db.commit()

    file_path = _resolve_file_path(doc.document_file)
    if not file_path or not file_path.exists():
        raise FileNotFoundError(f"Attached file not found: {doc.document_file}")

    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        text = _extract_pdf(file_path)
    elif suffix in (".docx", ".doc"):
        text = _extract_docx(file_path)
    else:
        text = file_path.read_text(errors="replace")

    text   = _clean(text)
    chunks = _chunk(text)
    if not chunks:
        raise ValueError("No text extracted from document")

    from ticketbrain.ai.service import _load_models
    from ticketbrain.ai.retrieval import append_to_kb_index

    _, _, embedder = _load_models()
    embeddings = embedder.encode(chunks, convert_to_numpy=True, show_progress_bar=False)

    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        metadata = {
            "source":    "tb_document",
            "doc_name":  doc_name,
            "title":     doc.title or doc_name,
            "chunk_idx": i,
            "content":   chunk[:500],
        }
        append_to_kb_index(metadata, emb)

    frappe.db.set_value("TB Document", doc_name, {
        "status":      "Indexed",
        "chunk_count": len(chunks),
    })
    frappe.db.commit()


# ── Text extraction ───────────────────────────────────────────────────────────

def _extract_pdf(path: Path) -> str:
    import pypdf
    reader = pypdf.PdfReader(str(path))
    pages  = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)


def _extract_docx(path: Path) -> str:
    import docx
    doc = docx.Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


# ── Text helpers ──────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _chunk(text: str) -> list[str]:
    """Split text into overlapping fixed-size chunks."""
    chunks = []
    start  = 0
    while start < len(text):
        end = start + _CHUNK_SIZE
        chunks.append(text[start:end].strip())
        start = end - _CHUNK_OVERLAP
    return [c for c in chunks if len(c) > 30]


# ── File path resolution ──────────────────────────────────────────────────────

def _resolve_file_path(file_url: str) -> Path | None:
    if not file_url:
        return None
    site_path = Path(frappe.get_site_path())
    # Frappe stores files as /files/... or /private/files/...
    rel = file_url.lstrip("/")
    candidate = site_path / rel
    if candidate.exists():
        return candidate
    # Try public files
    candidate2 = site_path / "public" / rel
    if candidate2.exists():
        return candidate2
    return candidate
