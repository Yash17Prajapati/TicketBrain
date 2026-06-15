import frappe
from frappe.desk.form.assign_to import add as assign_to

from ticketbrain.setup.install import TB_BOT_EMAIL


def on_ticket_created(doc, method):
    """
    Runs after every HD Ticket insert.
    Posts an immediate acknowledgment so the customer's browser returns instantly,
    then queues the heavy AI work (classifier + LLM + evaluator) as a background job.
    """
    try:
        _post_customer_reply(doc.name, _acknowledgment_html())
        frappe.enqueue(
            "ticketbrain.events.hd_ticket.process_ticket_async",
            ticket_name=doc.name,
            queue="default",
            timeout=300,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Ticket creation handler failed")


def process_ticket_async(ticket_name: str):
    """Background job: run AI classification, evaluation, and routing for a new ticket."""
    try:
        if not frappe.db.exists("HD Ticket", ticket_name):
            return
        doc = frappe.get_doc("HD Ticket", ticket_name)
        _auto_link_customer(doc)
        _process_ticket(doc)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Async AI processing failed")


def on_ticket_updated(doc, method):
    """
    Runs on every HD Ticket save. Detects Resolved/Closed transitions
    and triggers knowledge extraction in the background.
    """
    try:
        prev = doc.get_doc_before_save()
        if prev is None:
            return
        prev_status = getattr(prev, "status", "") or ""
        curr_status = doc.status or ""
        resolved_statuses = {"Resolved", "Closed", "AI Resolved"}

        if curr_status in resolved_statuses and prev_status not in resolved_statuses:
            frappe.enqueue(
                "ticketbrain.ai.knowledge_extraction.index_resolved_ticket",
                ticket_name=doc.name,
                queue="default",
                timeout=120,
            )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Knowledge extraction enqueue failed")


def _process_ticket(doc):
    from ticketbrain.ai.service import (
        classify_and_resolve,
        classify_ticket_type,
        infer_priority,
        _load_models,
    )
    from ticketbrain.ai.evaluator import evaluate

    subject     = doc.subject or ""
    description = doc.description or ""

    result      = classify_and_resolve(subject, description)
    ticket_type = classify_ticket_type(subject, description)
    priority    = infer_priority(subject, description)

    # Build the AI draft response
    ai_draft = _steps_comment_html(result)

    # Reuse ticket embedding for KB match scoring (avoids re-encoding)
    try:
        _, _, embedder = _load_models()
        ticket_embedding = embedder.encode(
            [f"{subject} — {description}"], convert_to_numpy=True
        )[0]
    except Exception:
        ticket_embedding = None

    # Evaluate all 5 metrics — decide: Auto Send / Human Review / Direct Escalate
    metrics = evaluate(
        subject=subject,
        description=description,
        classify_result=result,
        ai_draft_html=ai_draft,
        ticket_embedding=ticket_embedding,
        priority=priority,
    )

    decision = metrics["decision"]

    # Map decision → approval_status stored in TB AI Interaction
    approval_map = {
        "Auto Send":       "Auto Sent",
        "Human Review":    "Pending Approval",
        "Direct Escalate": "Pending Approval",
    }

    # Persist classification + metrics in TB AI Interaction
    interaction = frappe.get_doc({
        "doctype":                    "TB AI Interaction",
        "ticket":                     doc.name,
        "category":                   result["category"],
        "confidence_score":           result["confidence_score"],
        "status":                     "Active",
        "ai_draft_response":          ai_draft,
        "approval_status":            approval_map[decision],
        "classification_confidence":  round(metrics["classification_confidence"] * 100, 1),
        "priority_confidence":        round(metrics["priority_confidence"] * 100, 1),
        "kb_match_score":             round(metrics["kb_match_score"] * 100, 1),
        "response_quality_score":     round(metrics["response_quality_score"] * 100, 1),
        "risk_score":                 metrics["risk_score"],
        "auto_send_decision":         decision,
        "auto_send_reason":           metrics["reason"],
    })
    for step in result.get("steps", []):
        interaction.append("steps", {
            "step_number":  step["step_number"],
            "step_content": step["content"],
            "status":       "Pending",
        })
    interaction.insert(ignore_permissions=True)

    # Common ticket fields updated on every path
    ticket_updates = {
        "tb_category":         result["category"],
        "tb_confidence_score": result["confidence_score"],
        "tb_should_escalate":  1 if result.get("should_escalate") else 0,
        "ticket_type":         ticket_type,
        "priority":            priority,
    }

    if decision == "Auto Send":
        # All metrics passed — post AI response directly to customer
        _post_customer_reply(doc.name, ai_draft)
        ticket_updates["status"] = "Open"
        frappe.db.set_value("HD Ticket", doc.name, ticket_updates)
        _reapply_sla(doc.name)
        # Save the response to kb_index.npz so future similar tickets use it as reference
        from ticketbrain.ai.knowledge_extraction import auto_index_ai_resolution
        auto_index_ai_resolution(
            ticket_name=doc.name,
            subject=subject,
            description=description,
            ai_draft_html=ai_draft,
            category=result["category"],
        )

    elif decision == "Human Review":
        # Confidence is fine but a quality metric failed — agent reviews the AI draft.
        # Keep ticket status "Open" so the customer never sees the internal approval state.
        # The approval state lives in TB AI Interaction.approval_status only.
        ticket_updates["status"] = "Open"
        frappe.db.set_value("HD Ticket", doc.name, ticket_updates)
        _reapply_sla(doc.name)
        _assign_agent_internally(doc.name, interaction.name)

    else:  # Direct Escalate
        # Acknowledgment already sent in on_ticket_created — just route to an agent.
        ticket_updates["status"] = "Open"
        frappe.db.set_value("HD Ticket", doc.name, ticket_updates)
        frappe.db.set_value("TB AI Interaction", interaction.name, "status", "Escalated")
        _reapply_sla(doc.name)
        _auto_escalate(doc.name, result["category"], interaction.name)

    frappe.db.commit()


# ── Customer resolution ────────────────────────────────────────────────────────

# ── Agent assignment ───────────────────────────────────────────────────────────

def _assign_agent_internally(ticket_name: str, interaction_name: str):
    """
    Assign the least-loaded agent to review the AI draft.
    The customer is NOT notified — the ticket stays in 'Pending Approval'.
    The agent gets a desk notification so they know a draft is waiting for review.
    """
    agents = _get_all_agents()
    if not agents:
        return

    agent = _pick_least_loaded_agent(agents)
    try:
        assign_to({
            "assign_to":   [agent],
            "doctype":     "HD Ticket",
            "name":        ticket_name,
            "description": "TicketBrain AI has drafted a response — review and approve, or write a custom reply.",
            "notify":      1,
        })
        frappe.db.set_value("TB AI Interaction", interaction_name, "assigned_agent", agent)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Agent assignment failed")


# ── Auto-escalation (mid-conversation) ─────────────────────────────────────────

def _auto_escalate(ticket_name: str, category: str, interaction_name: str):
    """
    Escalate a ticket to the least-loaded available agent.
    Does NOT auto-assign a team — team assignment is left to agents/admins
    since we cannot reliably map AI categories to Helpdesk teams.
    """
    agents = _get_all_agents()

    frappe.db.set_value("HD Ticket", ticket_name, "status", "Open")
    frappe.db.set_value("TB AI Interaction", interaction_name, "status", "Escalated")

    if agents:
        agent = _pick_least_loaded_agent(agents)
        try:
            assign_to({
                "assign_to":   [agent],
                "doctype":     "HD Ticket",
                "name":        ticket_name,
                "description": "Auto-assigned by TicketBrain AI (escalation).",
                "notify":      1,
            })
        except Exception:
            frappe.log_error(frappe.get_traceback(), "TicketBrain: Agent assignment failed")

    # Re-apply SLA now that a human agent is handling the ticket
    _reapply_sla(ticket_name)


def _reapply_sla(ticket_name: str):
    """Re-enable SLA tracking when the ticket moves from AI to human agent."""
    try:
        ticket = frappe.get_doc("HD Ticket", ticket_name)
        from helpdesk.helpdesk.doctype.hd_service_level_agreement.utils import get_sla
        sla = get_sla(ticket)
        if sla:
            # save() triggers before_save → apply_sla() which sets response_by / resolution_by
            ticket.sla = sla.name if hasattr(sla, "name") else sla
            ticket.save(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: SLA re-apply failed")


def _get_all_agents() -> list[str]:
    """Return all active HD Agents as a fallback when no teams are configured."""
    rows = frappe.get_all("HD Agent", filters={"is_active": 1}, fields=["user"])
    return [r.user for r in rows]


def _pick_least_loaded_agent(agents: list[str]) -> str:
    """Return the agent with the fewest open tickets (workload round-robin)."""
    counts = {a: _open_ticket_count_for_agents([a]) for a in agents}
    return min(counts, key=counts.get)


def _open_ticket_count_for_agents(agents: list[str]) -> int:
    if not agents:
        return 0
    placeholders = ", ".join(["%s"] * len(agents))
    result = frappe.db.sql(
        f"""
        SELECT COUNT(*) AS cnt
        FROM `tabHD Ticket` t
        JOIN `tabToDo` td ON td.reference_name = t.name
            AND td.reference_type = 'HD Ticket'
            AND td.allocated_to IN ({placeholders})
            AND td.status = 'Open'
        WHERE t.status NOT IN ('Resolved', 'Closed')
        """,
        agents,
        as_dict=True,
    )
    return result[0].cnt if result else 0


# ── Customer auto-link ────────────────────────────────────────────────────────

def _auto_link_customer(doc):
    """
    Populate HD Ticket.customer from the ticket submitter's Contact → Customer link.
    HD Customer is Frappe Helpdesk's own doctype (separate from ERPNext Customer).
    Flow: raised_by email → tabContact → tabDynamic Link (link_doctype=Customer)
          → find or create HD Customer → set on ticket.
    """
    if doc.customer:
        return  # Already set — nothing to do

    email = doc.raised_by or ""
    if not email or email == "Administrator":
        return

    # Find the Contact for this email
    contact_name = frappe.db.get_value("Contact", {"email_id": email}, "name")
    if not contact_name:
        return

    # Find the ERPNext Customer linked to this contact via Dynamic Link
    customer_name = frappe.db.get_value(
        "Dynamic Link",
        {"parenttype": "Contact", "parent": contact_name, "link_doctype": "Customer"},
        "link_name",
    )
    if not customer_name:
        return

    # Find or create the matching HD Customer record
    hd_customer = frappe.db.get_value("HD Customer", {"customer_name": customer_name}, "name")
    if not hd_customer:
        try:
            hd_doc = frappe.get_doc({
                "doctype":       "HD Customer",
                "customer_name": customer_name,
            })
            hd_doc.insert(ignore_permissions=True)
            hd_customer = hd_doc.name
        except Exception:
            frappe.log_error(frappe.get_traceback(), "TicketBrain: HD Customer creation failed")
            return

    frappe.db.set_value("HD Ticket", doc.name, "customer", hd_customer)


# ── Comment HTML builders ──────────────────────────────────────────────────────

def _steps_comment_html(result: dict, metrics: dict | None = None) -> str:
    category        = result["category"]
    confidence      = int(result["confidence_score"] * 100)
    steps           = result.get("steps", [])
    resolution_type = result.get("resolution_type", "step_by_step")

    parts = [
        '<div style="font-family:sans-serif;line-height:1.6;">',
        f'<p><strong>TicketBrain AI Response</strong>'
        f' &nbsp;·&nbsp; Category: <em>{category}</em>'
        f' &nbsp;·&nbsp; Confidence: {confidence}%</p>',
    ]

    if resolution_type == "information" and steps:
        parts += [
            "<p><strong>Here is the information you need:</strong></p>",
            f'<p>{steps[0]["content"]}</p>',
            '<p style="color:#6b7280;font-size:12px;">'
            "If this did not answer your question, reply here and a support agent will assist you."
            "</p>",
        ]

    elif resolution_type == "quick_fix" and steps:
        parts += [
            "<p><strong>Quick fix:</strong></p>",
            f'<blockquote style="border-left:3px solid #2563eb;margin:0;padding:8px 16px;color:#1e40af;">'
            f'{steps[0]["content"]}</blockquote>',
            '<p style="color:#6b7280;font-size:12px;">'
            "Reply <strong>&#34;Resolved&#34;</strong> if this fixed your issue, "
            "or reply with what happened and we will help further."
            "</p>",
        ]

    else:
        parts += [
            "<p><strong>Suggested resolution steps — try them in order:</strong></p>",
            "<ol>",
        ]
        for step in steps:
            parts.append(f'<li style="margin-bottom:6px;">{step["content"]}</li>')
        parts += [
            "</ol>",
            '<p style="color:#6b7280;font-size:12px;">'
            "Try the steps above and reply here with any update — the AI will respond and guide you further."
            "</p>",
        ]

    parts.append("</div>")
    return "\n".join(parts)


def _acknowledgment_html() -> str:
    return (
        '<div style="font-family:sans-serif;line-height:1.6;">'
        "<p>Thank you for reaching out! We have received your request and "
        "a support agent will review it and get back to you shortly.</p>"
        "<p>In the meantime, feel free to add any additional details or context "
        "as a reply — the more information you provide, the faster we can help.</p>"
        "</div>"
    )


def _post_customer_reply(ticket_name: str, content: str):
    """
    Post a bot response visible to the customer in the portal.
    Creates a Communication record (same doctype as agent replies) so the
    customer portal can display it. No email is sent — this avoids requiring
    an outgoing email account and lets Frappe's notification system handle
    email separately if configured.
    """
    try:
        ticket  = frappe.get_doc("HD Ticket", ticket_name)
        subject = f"Re: {ticket.subject or 'Support Ticket'}"

        recipients = ticket.raised_by or ""
        if recipients == "Administrator":
            recipients = frappe.get_value("User", "Administrator", "email") or ""

        frappe.get_doc({
            "doctype":              "Communication",
            "communication_medium": "",   # portal-only — no email required
            "communication_type":   "Communication",
            "content":              content,
            "recipients":           recipients,
            "reference_doctype":    "HD Ticket",
            "reference_name":       ticket_name,
            "sender":               TB_BOT_EMAIL,
            "sent_or_received":     "Sent",
            "status":               "Linked",
            "subject":              subject,
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Customer reply failed")
