"""
TicketBrain Knowledge Extraction — Continuous Learning Pipeline

Triggered on every ticket resolution. Does three things:
  1. Embeds the resolved ticket and appends it to ticket_index.npz
  2. Searches for similar previously-resolved tickets (cluster detection)
  3. If a pattern repeats >= CLUSTER_MIN_COUNT times, generates a TB Knowledge Draft

No model retraining. Intelligence accumulates through retrieval.

Entry points:
  index_resolved_ticket(ticket_name)  — run in background queue on ticket close
  rebuild_ticket_index()              — one-shot backfill from all existing resolved tickets
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import frappe
import numpy as np

_CLUSTER_THRESHOLD = 0.82   # cosine similarity to treat two tickets as the "same issue"
_CLUSTER_MIN_COUNT = 2      # occurrences before generating a KB draft


# ── Main entry point ──────────────────────────────────────────────────────────

def index_resolved_ticket(ticket_name: str):
    """Embed a resolved ticket and check for recurring patterns. Run in background."""
    try:
        _do_index(ticket_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Knowledge extraction failed")


def _do_index(ticket_name: str):
    ticket = frappe.get_doc("HD Ticket", ticket_name)
    if not ticket.subject:
        return

    resolution = _get_resolution_text(ticket_name)
    full_text  = f"{ticket.subject} {ticket.description or ''} {resolution}".strip()
    if not full_text:
        return

    embedding = _embed(full_text)
    if embedding is None:
        return

    metadata = {
        "ticket_id":   ticket_name,
        "subject":     (ticket.subject or "")[:200],
        "description": (ticket.description or "")[:400],
        "resolution":  resolution[:400],
        "category":    frappe.db.get_value("HD Ticket", ticket_name, "tb_category") or "",
        "team":        ticket.agent_group or "",
        "resolved_at": str(datetime.now().date()),
    }

    from ticketbrain.ai.retrieval import append_to_ticket_index
    append_to_ticket_index(metadata, embedding)

    _maybe_create_draft(metadata, embedding)


# ── Cluster detection ─────────────────────────────────────────────────────────

def _maybe_create_draft(metadata: dict, embedding: np.ndarray):
    from pathlib import Path as _Path
    _MODELS_DIR = _Path(__file__).parent.parent / "ml" / "models"
    index_path  = _MODELS_DIR / "ticket_index.npz"

    if not index_path.exists():
        return

    data   = np.load(str(index_path), allow_pickle=True)
    embs   = data["embeddings"]
    metas  = list(data["metadata"])

    if len(embs) < _CLUSTER_MIN_COUNT:
        return

    q      = embedding / (np.linalg.norm(embedding) + 1e-10)
    scores = embs @ q

    # Exclude the entry we just appended (last row)
    similar_pairs = [
        (i, float(scores[i])) for i in range(len(scores) - 1)
        if scores[i] >= _CLUSTER_THRESHOLD
    ]

    if len(similar_pairs) < _CLUSTER_MIN_COUNT - 1:
        return

    similar     = [(metas[i], sc) for i, sc in similar_pairs]
    title       = f"[Auto] {metadata['subject'][:80]}"
    occurrences = len(similar) + 1

    if frappe.db.exists("TB Knowledge Draft", {"title": title}):
        frappe.db.set_value(
            "TB Knowledge Draft", {"title": title}, "occurrence_count", occurrences
        )
        frappe.db.commit()
        return

    resolutions = list({m.get("resolution", "") for m, _ in similar if m.get("resolution")})
    resolutions = [r for r in resolutions if r][:3]

    # Most common team across similar tickets
    teams = [m.get("team", "") for m, _ in similar if m.get("team")]
    related_team_name = max(set(teams), key=teams.count) if teams else (metadata.get("team") or "")
    hd_team = frappe.db.get_value("HD Team", {"name": related_team_name}, "name") if related_team_name else None

    structured = _generate_draft_content(
        issue=metadata["subject"],
        category=metadata.get("category", ""),
        resolutions=resolutions,
        sample_subjects=[m.get("subject", "") for m, _ in similar[:3]],
        occurrences=occurrences,
    )

    # Build ticket_references child table rows
    ticket_refs = [{"doctype": "TB Draft Ticket Reference", "ticket": metadata["ticket_id"], "similarity": 1.0}]
    for m, sc in similar[:9]:
        tid = m.get("ticket_id")
        if tid:
            ticket_refs.append({"doctype": "TB Draft Ticket Reference", "ticket": tid, "similarity": round(sc, 2)})

    try:
        doc_data = {
            "doctype":           "TB Knowledge Draft",
            "title":             title,
            "category":          metadata.get("category", ""),
            "content":           structured["content"],
            "root_cause":        structured.get("root_cause", ""),
            "resolution_steps":  structured.get("resolution_steps", ""),
            "occurrence_count":  occurrences,
            "source_ticket":     metadata["ticket_id"],
            "status":            "Pending Approval",
            "ticket_references": ticket_refs,
        }
        if hd_team:
            doc_data["related_team"] = hd_team
        frappe.get_doc(doc_data).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Knowledge draft creation failed")


def _generate_draft_content(
    issue: str,
    category: str,
    resolutions: list[str],
    sample_subjects: list[str],
    occurrences: int,
) -> dict:
    """Return dict with keys: content, root_cause, resolution_steps."""
    from ticketbrain.ai.llm_provider import is_available, call_llm
    import json as _json

    if is_available() and resolutions:
        res_text = "\n".join(f"- {r}" for r in resolutions)
        prompt = (
            f"You are an IT knowledge base writer. Respond ONLY with a JSON object.\n\n"
            f"Issue pattern: {issue}\n"
            f"Category: {category}\n"
            f"Observed resolutions from {occurrences} similar tickets:\n{res_text}\n\n"
            'Return JSON with keys: "content" (200-400 word KB article, plain text), '
            '"root_cause" (1-2 sentence diagnosis), "resolution_steps" (numbered steps as plain text).'
        )
        try:
            raw = call_llm(prompt, json_mode=True)
            if raw:
                parsed = _json.loads(raw)
                return {
                    "content":          parsed.get("content", ""),
                    "root_cause":       parsed.get("root_cause", ""),
                    "resolution_steps": parsed.get("resolution_steps", ""),
                }
        except Exception:
            pass

    # Fallback: template-based draft
    samples_block     = "\n".join(f"  - {s}" for s in sample_subjects if s)
    res_block         = "\n".join(f"  {i+1}. {r}" for i, r in enumerate(resolutions))
    resolution_steps  = "\n".join(f"{i+1}. {r}" for i, r in enumerate(resolutions))
    content = (
        f"This issue has appeared {occurrences} time(s).\n\n"
        f"Similar tickets:\n{samples_block}\n\n"
        f"Common resolutions observed:\n{res_block}"
    )
    return {
        "content":          content,
        "root_cause":       "",
        "resolution_steps": resolution_steps,
    }


# ── Resolution text collection ────────────────────────────────────────────────

def _get_resolution_text(ticket_name: str) -> str:
    """Collect resolution from satisfied AI steps."""
    interaction = frappe.get_all(
        "TB AI Interaction",
        filters={"ticket": ticket_name},
        fields=["name"],
        limit=1,
    )
    if not interaction:
        return ""

    doc = frappe.get_doc("TB AI Interaction", interaction[0].name)
    satisfied = [
        s.step_content
        for s in doc.steps
        if s.status == "Satisfied" and s.step_content
    ]
    return " | ".join(satisfied)


# ── Embedding helper ──────────────────────────────────────────────────────────

def _embed(text: str) -> np.ndarray | None:
    try:
        from ticketbrain.ai.service import _load_models
        _, _, embedder = _load_models()
        return embedder.encode([text], convert_to_numpy=True)[0].astype(np.float32)
    except Exception:
        return None


# ── Auto-learn from AI-resolved tickets ───────────────────────────────────────

def auto_index_ai_resolution(
    ticket_name: str,
    subject: str,
    description: str,
    ai_draft_html: str,
    category: str,
):
    """
    Index a successful AI auto-send response directly into kb_index.npz.
    Called only when decision == 'Auto Send' (all confidence + quality gates passed).
    The AI response is treated as a KB article so future similar tickets can
    retrieve it without waiting for cluster detection or agent approval.
    """
    try:
        import re
        clean_draft = re.sub(r"<[^>]+>", " ", ai_draft_html).strip()
        text = f"{subject} {description} {clean_draft}".strip()
        if not text:
            return

        embedding = _embed(text)
        if embedding is None:
            return

        from ticketbrain.ai.retrieval import append_to_kb_index
        append_to_kb_index(
            metadata={
                "source":      "auto_learned",
                "ticket_id":   ticket_name,
                "title":       subject[:200],
                "content":     clean_draft[:800],
                "category":    category,
                "description": description[:400],
            },
            embedding=embedding,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Auto KB indexing failed")


# ── Backfill ──────────────────────────────────────────────────────────────────

def rebuild_ticket_index():
    """
    Backfill ticket_index.npz from all existing resolved/closed tickets.
    Run once manually from bench console:
      bench --site ticketbrain.local execute ticketbrain.ai.knowledge_extraction.rebuild_ticket_index
    """
    from ticketbrain.ai.retrieval import _TICKET_INDEX_PATH

    tickets = frappe.db.sql(
        """SELECT name, subject, description, agent_group, tb_category
           FROM `tabHD Ticket`
           WHERE status IN ('Resolved', 'Closed', 'AI Resolved')
           ORDER BY modified DESC
           LIMIT 2000""",
        as_dict=True,
    )

    if not tickets:
        print("No resolved tickets found.")
        return

    try:
        from ticketbrain.ai.service import _load_models
        from ticketbrain.ai.retrieval import append_to_ticket_index
        _, _, embedder = _load_models()
    except Exception as e:
        print(f"Could not load embedder: {e}")
        return

    # Clear existing ticket index
    if _TICKET_INDEX_PATH.exists():
        _TICKET_INDEX_PATH.unlink()

    processed = 0
    for t in tickets:
        resolution = _get_resolution_text(t.name)
        full_text  = f"{t.subject or ''} {t.description or ''} {resolution}".strip()
        if not full_text:
            continue

        emb = embedder.encode([full_text], convert_to_numpy=True)[0].astype(np.float32)
        append_to_ticket_index(
            metadata={
                "ticket_id":   t.name,
                "subject":     (t.subject or "")[:200],
                "description": (t.description or "")[:400],
                "resolution":  resolution[:400],
                "category":    t.tb_category or "",
                "team":        t.agent_group or "",
                "resolved_at": str(datetime.now().date()),
            },
            embedding=emb,
        )
        processed += 1
        if processed % 100 == 0:
            print(f"  Indexed {processed}/{len(tickets)} tickets...")

    print(f"Done — indexed {processed} resolved tickets into ticket_index.npz")
