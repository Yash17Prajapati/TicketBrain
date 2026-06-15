"""
Auto-index HD Articles into kb_index.npz whenever they are published or updated.
No manual "Update RAG" button required.
"""

from __future__ import annotations
import frappe


def on_article_save(doc, method):
    """Fires on HD Article after_insert and on_update."""
    if doc.status != "Published":
        return
    try:
        frappe.enqueue(
            "ticketbrain.events.hd_article.index_article",
            article_name=doc.name,
            queue="long",
            timeout=120,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: KB article index enqueue failed")


def index_article(article_name: str):
    """Embed an HD Article and append it to kb_index.npz."""
    try:
        doc = frappe.get_doc("HD Article", article_name)
        if doc.status != "Published":
            return

        import re
        clean = re.sub(r"<[^>]+>", " ", doc.content or "")
        text  = f"{doc.title} — {clean}".strip()
        if not text:
            return

        from ticketbrain.ai.service import _load_models
        from ticketbrain.ai.retrieval import append_to_kb_index

        _, _, embedder = _load_models()
        emb = embedder.encode([text], convert_to_numpy=True)[0]

        metadata = {
            "source":   "hd_article",
            "name":     article_name,
            "title":    doc.title or "",
            "content":  clean[:500],
            "category": doc.category or "",
        }
        append_to_kb_index(metadata, emb)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: KB article indexing failed")
