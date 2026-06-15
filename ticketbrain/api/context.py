import json

import frappe


# ── Scan lifecycle ────────────────────────────────────────────────────────────

@frappe.whitelist()
def run_scan(doc_name: str):
    """Trigger a background context discovery scan (first scan or after rejection)."""
    frappe.db.set_value("TB Business Context", doc_name, {
        "scan_status":      "Running",
        "lifecycle_status": "Scanning",
        "last_scan_summary": "Scan queued…",
    })
    frappe.db.commit()
    frappe.enqueue(
        "ticketbrain.ai.context_discovery.run_discovery",
        doc_name=doc_name,
        queue="long",
        timeout=1800,
    )
    return {"ok": True}


@frappe.whitelist()
def refresh_context(doc_name: str):
    """Trigger a refresh scan while keeping the current Active context in use."""
    frappe.db.set_value("TB Business Context", doc_name, {
        "scan_status":      "Running",
        "lifecycle_status": "Scanning",
        "last_scan_summary": "Refresh scan queued…",
        "update_available": 0,
        "update_notes":     "",
    })
    frappe.db.commit()
    frappe.enqueue(
        "ticketbrain.ai.context_discovery.run_discovery",
        doc_name=doc_name,
        queue="long",
        timeout=1800,
    )
    return {"ok": True}


@frappe.whitelist()
def abort_scan(doc_name: str):
    """Cancel a running scan and revert to the previous state."""
    # If there was a previous active version, restore Active state; otherwise go back to Not Generated
    has_active_version = frappe.db.exists(
        "TB Business Context Version",
        {"business_context": doc_name, "status": "Active"},
    )
    revert_status = "Active" if has_active_version else "Not Generated"

    frappe.db.set_value("TB Business Context", doc_name, {
        "scan_status":       "Idle",
        "lifecycle_status":  revert_status,
        "last_scan_summary": "Scan aborted by user.",
    })
    frappe.db.commit()
    return {"ok": True, "reverted_to": revert_status}


# ── Approval / Activation ─────────────────────────────────────────────────────

@frappe.whitelist()
def approve_context(doc_name: str):
    """
    Approve all reviewed items and activate this context version.
    Replaces finalise_context — the user is approving AI-discovered knowledge.
    """
    from ticketbrain.ai.context_discovery import update_rag_with_context

    ctx = frappe.get_doc("TB Business Context", doc_name)
    approved_count = 0
    for item in ctx.items:
        if item.review_status == "Pending Review":
            item.review_status = "Approved"
            approved_count += 1

    new_version_num = (ctx.current_version or 0) + 1
    ctx.approval_status  = "Approved"
    ctx.lifecycle_status = "Active"
    ctx.items_pending    = 0
    ctx.current_version  = new_version_num
    ctx.save(ignore_permissions=True)

    # Archive any currently Active version, promote the latest Pending Review one
    frappe.db.sql(
        "UPDATE `tabTB Business Context Version` SET status='Archived' "
        "WHERE business_context=%s AND status='Active'",
        doc_name,
    )
    pending_ver = frappe.db.get_value(
        "TB Business Context Version",
        {"business_context": doc_name, "status": "Pending Review"},
        "name",
        order_by="version_number desc",
    )
    if pending_ver:
        frappe.db.set_value("TB Business Context Version", pending_ver, {
            "status":      "Active",
            "approved_at": frappe.utils.now(),
            "approved_by": frappe.session.user,
        })
    else:
        # First-time approval with no version record — create one now
        _create_version_record(ctx, approved_count, 0, 0, {})

    frappe.db.commit()
    rag = update_rag_with_context(doc_name)
    return {"approved": approved_count, "version": new_version_num, "rag": rag}


@frappe.whitelist()
def reject_and_rescan(doc_name: str):
    """Reject the current Review Required context and immediately start a fresh scan."""
    # Mark the pending version as Rejected
    pending_ver = frappe.db.get_value(
        "TB Business Context Version",
        {"business_context": doc_name, "status": "Pending Review"},
        "name",
        order_by="version_number desc",
    )
    if pending_ver:
        frappe.db.set_value("TB Business Context Version", pending_ver, "status", "Rejected")

    # Decide what state to return to after the new scan
    has_active_version = frappe.db.exists(
        "TB Business Context Version",
        {"business_context": doc_name, "status": "Active"},
    )

    # Wipe pending items from the main doc (keep approved ones if any active version)
    ctx = frappe.get_doc("TB Business Context", doc_name)
    ctx.items = [i for i in ctx.items if i.review_status == "Approved"]
    ctx.items_pending = 0
    ctx.save(ignore_permissions=True)
    frappe.db.commit()

    # Queue fresh scan
    return run_scan(doc_name)


# ── Backward compat (old JS calls this) ──────────────────────────────────────

@frappe.whitelist()
def finalise_context(doc_name: str):
    return approve_context(doc_name)


# ── Version management ────────────────────────────────────────────────────────

@frappe.whitelist()
def get_versions(doc_name: str):
    """Return version history for a business context, newest first."""
    return frappe.get_all(
        "TB Business Context Version",
        filters={"business_context": doc_name},
        fields=[
            "name", "version_label", "version_number", "status",
            "scanned_at", "approved_at", "approved_by",
            "scan_summary", "items_added", "items_removed", "items_changed",
        ],
        order_by="version_number desc",
    )


@frappe.whitelist()
def get_version_diff(version_name: str):
    """Return the structured change diff for a version."""
    ver = frappe.get_doc("TB Business Context Version", version_name)
    change_summary = {}
    if ver.change_summary:
        try:
            change_summary = json.loads(ver.change_summary)
        except Exception:
            pass
    return {
        "version_label":  ver.version_label,
        "status":         ver.status,
        "items_added":    ver.items_added or 0,
        "items_removed":  ver.items_removed or 0,
        "items_changed":  ver.items_changed or 0,
        "change_summary": change_summary,
        "scan_summary":   ver.scan_summary or "",
    }


@frappe.whitelist()
def rollback_to_version(version_name: str):
    """Restore a previously archived version as the active context."""
    from ticketbrain.ai.context_discovery import update_rag_with_context

    ver = frappe.get_doc("TB Business Context Version", version_name)
    doc_name = ver.business_context
    if not ver.items_snapshot:
        frappe.throw("No snapshot stored for this version — cannot rollback.")

    snapshot = json.loads(ver.items_snapshot)

    ctx = frappe.get_doc("TB Business Context", doc_name)
    ctx.items = []
    for item in snapshot:
        ctx.append("items", {
            "item_type":        item.get("item_type", ""),
            "item_name":        item.get("item_name", ""),
            "description":      item.get("description", ""),
            "related_team":     item.get("related_team", ""),
            "evidence":         item.get("evidence", ""),
            "confidence_score": item.get("confidence_score", 0),
            "review_status":    "Approved",
            "agent_notes":      item.get("agent_notes", ""),
        })
    ctx.lifecycle_status = "Active"
    ctx.approval_status  = "Approved"
    ctx.items_pending    = 0
    ctx.current_version  = ver.version_number
    ctx.save(ignore_permissions=True)

    frappe.db.sql(
        "UPDATE `tabTB Business Context Version` SET status='Archived' "
        "WHERE business_context=%s AND status='Active'",
        doc_name,
    )
    frappe.db.set_value("TB Business Context Version", version_name, {
        "status":      "Active",
        "approved_at": frappe.utils.now(),
        "approved_by": frappe.session.user,
    })
    frappe.db.commit()

    update_rag_with_context(doc_name)
    return {"ok": True, "restored_version": ver.version_label}


# ── Existing secondary actions (kept as-is) ───────────────────────────────────

@frappe.whitelist()
def update_rag(doc_name: str):
    from ticketbrain.ai.context_discovery import update_rag_with_context
    return update_rag_with_context(doc_name)


@frappe.whitelist()
def create_kb_articles(doc_name: str):
    from ticketbrain.ai.context_discovery import create_kb_articles_from_context
    count = create_kb_articles_from_context(doc_name)
    return {"created": count}


@frappe.whitelist()
def approve_all_pending(doc_name: str):
    ctx = frappe.get_doc("TB Business Context", doc_name)
    changed = 0
    for item in ctx.items:
        if item.review_status == "Pending Review":
            item.review_status = "Approved"
            changed += 1
    ctx.approval_status = "Approved"
    ctx.items_pending   = 0
    ctx.save(ignore_permissions=True)
    frappe.db.commit()
    return {"approved": changed}


@frappe.whitelist()
def get_scan_status(doc_name: str):
    """Poll current scan status from the JS poller."""
    return frappe.db.get_value(
        "TB Business Context", doc_name,
        ["scan_status", "lifecycle_status", "last_scan_date", "last_scan_summary",
         "items_pending", "current_version", "update_available"],
        as_dict=True,
    ) or {}


@frappe.whitelist()
def ensure_context_exists():
    """Create the TB Business Context record if it doesn't exist yet."""
    company = (
        frappe.db.get_single_value("Global Defaults", "default_company")
        or frappe.db.get_value("Company", {}, "name")
    )
    if not company:
        return {"error": "No company found"}
    if not frappe.db.exists("TB Business Context", company):
        frappe.get_doc({
            "doctype":          "TB Business Context",
            "company":          company,
            "scan_status":      "Idle",
            "lifecycle_status": "Not Generated",
            "schedule_days":    7,
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    return {"name": company}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _create_version_record(ctx, items_added: int, items_removed: int, items_changed: int, change_summary: dict):
    """Create a TB Business Context Version marked Active immediately (first approval path)."""
    last = frappe.db.get_value(
        "TB Business Context Version",
        {"business_context": ctx.name},
        "version_number",
        order_by="version_number desc",
    ) or 0
    ver_num = (last or 0) + 1
    snapshot = [
        {
            "item_type":        i.item_type,
            "item_name":        i.item_name,
            "description":      i.description,
            "related_team":     i.related_team,
            "evidence":         i.evidence,
            "confidence_score": i.confidence_score,
            "agent_notes":      i.agent_notes,
        }
        for i in ctx.items
    ]
    ver = frappe.get_doc({
        "doctype":          "TB Business Context Version",
        "business_context": ctx.name,
        "version_number":   ver_num,
        "version_label":    f"v{ver_num}",
        "status":           "Active",
        "scanned_at":       ctx.last_scan_date or frappe.utils.now(),
        "approved_at":      frappe.utils.now(),
        "approved_by":      frappe.session.user,
        "scan_summary":     ctx.last_scan_summary or "",
        "items_added":      items_added,
        "items_removed":    items_removed,
        "items_changed":    items_changed,
        "change_summary":   json.dumps(change_summary, default=str)[:5000],
        "items_snapshot":   json.dumps(snapshot, default=str)[:30000],
    })
    ver.insert(ignore_permissions=True)
    return ver.name
