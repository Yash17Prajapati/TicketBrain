import frappe
from ticketbrain.ai.retrieval import append_to_kb_index


@frappe.whitelist()
def list_drafts():
    """Return all pending knowledge drafts for agent review."""
    return frappe.get_all(
        "TB Knowledge Draft",
        filters={"status": "Pending Approval"},
        fields=["name", "title", "category", "occurrence_count", "source_ticket", "modified"],
        order_by="occurrence_count desc",
    )


@frappe.whitelist()
def approve_draft(name: str):
    """
    Approve a TB Knowledge Draft and promote it to an HD Article.
    The draft content becomes the article body verbatim.
    """
    draft = frappe.get_doc("TB Knowledge Draft", name)
    if draft.status != "Pending Approval":
        frappe.throw(f"Draft is already {draft.status}.")

    title = draft.title.replace("[Auto] ", "").strip()

    if frappe.db.exists("HD Article", {"title": title}):
        frappe.throw(f"An HD Article with the title '{title}' already exists.")

    article = frappe.get_doc({
        "doctype": "HD Article",
        "title":   title,
        "content": f"<pre>{draft.content}</pre>",
        "status":  "Published",
    })
    article.insert(ignore_permissions=True)

    draft.status     = "Approved"
    draft.hd_article = article.name
    draft.save(ignore_permissions=True)
    frappe.db.commit()

    # Embed the new article immediately so RAG picks it up without waiting for the hook
    try:
        from ticketbrain.ai.service import _load_models
        _, _, embedder = _load_models()
        text = f"{title}\n\n{draft.content}"
        emb = embedder.encode([text], convert_to_numpy=True)[0]
        append_to_kb_index(
            metadata={"source": "hd_article", "name": article.name, "title": title, "content": draft.content},
            embedding=emb,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: failed to embed approved draft")

    return {"ok": True, "hd_article": article.name}


@frappe.whitelist()
def reject_draft(name: str):
    """Reject a TB Knowledge Draft."""
    frappe.db.set_value("TB Knowledge Draft", name, "status", "Rejected")
    frappe.db.commit()
    return {"ok": True}


@frappe.whitelist()
def get_draft(name: str):
    """Return full draft details for the review modal."""
    draft = frappe.get_doc("TB Knowledge Draft", name)
    return {
        "name":             draft.name,
        "title":            draft.title,
        "category":         draft.category,
        "content":          draft.content,
        "occurrence_count": draft.occurrence_count,
        "source_ticket":    draft.source_ticket,
        "status":           draft.status,
    }
