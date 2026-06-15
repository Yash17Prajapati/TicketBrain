import frappe


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_interaction(ticket_id: str) -> dict | None:
    results = frappe.get_all(
        "TB AI Interaction",
        filters={"ticket": ticket_id},
        fields=["name", "category", "confidence_score", "status"],
        limit=1,
    )
    return results[0] if results else None


# ── AI Processing Status ──────────────────────────────────────────────────────

@frappe.whitelist()
def get_ai_processing_status(ticket_name: str):
    """
    Poll endpoint for the 'Evaluating' overlay on the HD Ticket form.
    Returns whether AI has finished processing a newly created ticket.
    """
    interaction = frappe.db.get_value(
        "TB AI Interaction",
        {"ticket": ticket_name},
        ["name", "status", "category", "confidence_score", "approval_status"],
        as_dict=True,
    )
    if interaction:
        return {"done": True, "interaction": interaction}

    # Check if the ticket was created > 3 minutes ago — give up waiting
    created = frappe.db.get_value("HD Ticket", ticket_name, "creation")
    if created:
        age_seconds = (frappe.utils.now_datetime() - frappe.utils.get_datetime(created)).total_seconds()
        if age_seconds > 180:
            return {"done": True, "timed_out": True}

    return {"done": False}


# ── AI Step APIs ───────────────────────────────────────────────────────────────
# These are called from any frontend (Helpdesk client script, custom page, etc.)
# The AI analysis itself runs automatically via doc_events on HD Ticket.after_insert.

@frappe.whitelist()
def get_ai_suggestion(ticket_id, interaction_id=None):
    """
    Return the AI classification and step state for a ticket.
    Uses cached result from TB AI Interaction if already classified.
    """
    ticket = frappe.get_doc("HD Ticket", ticket_id)

    if interaction_id:
        interaction = frappe.get_doc("TB AI Interaction", interaction_id)
    else:
        existing = _get_interaction(ticket_id)
        if existing:
            interaction = frappe.get_doc("TB AI Interaction", existing["name"])
        else:
            # Ticket was created before TicketBrain was installed — run AI now
            interaction = _create_interaction(ticket)

    steps = [
        {
            "step_number":  s.step_number,
            "content":      s.step_content,
            "status":       s.status or "Pending",
            "user_message": s.user_message or "",
            "ai_followup":  s.ai_followup or "",
        }
        for s in interaction.steps
    ]

    return {
        "interaction_id":     interaction.name,
        "category":           interaction.category,
        "confidence_score":   interaction.confidence_score or 0.0,
        "resolution_type":    "quick_fix" if len(steps) == 1 else "step_by_step",
        "steps":              steps,
        "direct_answer":      steps[0]["content"] if len(steps) == 1 else "",
        "interaction_status": interaction.status or "Active",
        "should_escalate":    bool(frappe.db.get_value("HD Ticket", ticket_id, "tb_should_escalate")),
    }


@frappe.whitelist()
def submit_stuck_reply(ticket_id, interaction_id, step_index, user_message):
    """User is stuck on a step — generate and return AI followup."""
    step_index  = int(step_index)
    interaction = frappe.get_doc("TB AI Interaction", interaction_id)

    if step_index < len(interaction.steps):
        step = interaction.steps[step_index]
        step.user_message = user_message
        step.status       = "Stuck"
        interaction.save(ignore_permissions=True)
        frappe.db.commit()

    ticket       = frappe.get_doc("HD Ticket", ticket_id)
    step_content = interaction.steps[step_index].step_content if step_index < len(interaction.steps) else ""
    followup     = _get_followup(ticket.subject, step_content, user_message, interaction.category or "")

    if step_index < len(interaction.steps):
        interaction.steps[step_index].ai_followup = followup
        interaction.save(ignore_permissions=True)
        frappe.db.commit()

    return {"followup": followup}


@frappe.whitelist()
def record_step_feedback(interaction_id, step_index, status):
    """Record whether a step helped (Satisfied / Stuck)."""
    step_index  = int(step_index)
    interaction = frappe.get_doc("TB AI Interaction", interaction_id)

    if step_index < len(interaction.steps):
        interaction.steps[step_index].status = status.capitalize()
        interaction.save(ignore_permissions=True)
        frappe.db.commit()

    return {"ok": True}


@frappe.whitelist()
def resolve_ticket(ticket_id, interaction_id=None):
    """Mark the ticket as AI Resolved and close the interaction."""
    frappe.db.set_value("HD Ticket", ticket_id, "status", "AI Resolved")

    if interaction_id:
        frappe.db.set_value("TB AI Interaction", interaction_id, "status", "Resolved")
    else:
        existing = _get_interaction(ticket_id)
        if existing:
            frappe.db.set_value("TB AI Interaction", existing["name"], "status", "Resolved")

    frappe.db.commit()
    return {"ok": True}


@frappe.whitelist()
def escalate_ticket(ticket_id, interaction_id=None):
    """Escalate ticket to a human agent."""
    frappe.db.set_value("HD Ticket", ticket_id, "status", "Open")

    if interaction_id:
        frappe.db.set_value("TB AI Interaction", interaction_id, "status", "Escalated")
    else:
        existing = _get_interaction(ticket_id)
        if existing:
            frappe.db.set_value("TB AI Interaction", existing["name"], "status", "Escalated")

    frappe.db.commit()
    return {"ok": True}


# ── Agent approval APIs ────────────────────────────────────────────────────────

@frappe.whitelist()
def get_pending_approvals():
    """
    Return tickets assigned to the current agent that are waiting for response approval.
    Each row includes the AI draft so the agent can preview it before deciding.
    """
    user = frappe.session.user
    return frappe.db.sql("""
        SELECT
            t.name          AS ticket_id,
            t.subject,
            t.creation,
            t.tb_category   AS category,
            t.tb_confidence_score AS confidence_score,
            t.tb_should_escalate  AS ai_recommends_escalation,
            i.name              AS interaction_id,
            i.ai_draft_response,
            i.assigned_agent
        FROM `tabHD Ticket` t
        JOIN `tabTB AI Interaction` i ON i.ticket = t.name
        JOIN `tabToDo` td
            ON td.reference_name = t.name
            AND td.reference_type = 'HD Ticket'
            AND td.allocated_to = %s
            AND td.status = 'Open'
        WHERE i.approval_status = 'Pending Approval'
          AND t.status NOT IN ('Resolved', 'Closed', 'AI Resolved')
        ORDER BY t.creation ASC
    """, [user], as_dict=True)


@frappe.whitelist()
def approve_ai_response(ticket_id, interaction_id):
    """
    Agent approves the AI draft — send it to the customer as-is.
    The customer sees the AI response; no escalation is visible.
    """
    interaction = frappe.get_doc("TB AI Interaction", interaction_id)
    ai_draft = interaction.ai_draft_response

    if not ai_draft:
        frappe.throw("No AI draft response found for this interaction.")

    from ticketbrain.events.hd_ticket import _post_customer_reply, _reapply_sla
    _post_customer_reply(ticket_id, ai_draft)

    interaction.approval_status = "Approved"
    interaction.save(ignore_permissions=True)

    frappe.db.set_value("HD Ticket", ticket_id, "status", "Open")
    _reapply_sla(ticket_id)
    frappe.db.commit()
    return {"ok": True}


@frappe.whitelist()
def submit_agent_response(ticket_id, interaction_id, custom_message):
    """
    Agent writes a custom response instead of approving the AI draft.
    Uses reply_via_agent() so the reply appears in the customer portal
    (and sends email if an outgoing email account is configured).
    """
    agent_email = frappe.session.user

    # Update interaction and open ticket BEFORE sending the reply so that
    # on_communication_created sees "Open" status and skips double-processing.
    interaction = frappe.get_doc("TB AI Interaction", interaction_id)
    interaction.approval_status = "Modified"
    interaction.agent_response  = custom_message
    interaction.status          = "Escalated"
    interaction.save(ignore_permissions=True)

    frappe.db.set_value("HD Ticket", ticket_id, "status", "Open")

    # Send via Helpdesk's standard reply path → creates a Communication
    # visible to the customer in the portal (and emails them if configured).
    ticket = frappe.get_doc("HD Ticket", ticket_id)
    try:
        ticket.reply_via_agent(message=custom_message)
    except Exception:
        # Fallback: create Communication directly (no email) so the customer
        # still sees the reply in the portal even without an email account.
        from ticketbrain.events.hd_ticket import _post_customer_reply
        _post_customer_reply(ticket_id, custom_message)

    # Internal audit note — visible only to agents in the ticket timeline
    frappe.get_doc({
        "doctype":           "Comment",
        "comment_type":      "Info",
        "reference_doctype": "HD Ticket",
        "reference_name":    ticket_id,
        "content":           (
            f"[TicketBrain] Agent {agent_email} reviewed the AI draft "
            "and sent a custom response."
        ),
    }).insert(ignore_permissions=True)

    from ticketbrain.events.hd_ticket import _reapply_sla
    _reapply_sla(ticket_id)
    frappe.db.commit()
    return {"ok": True, "escalated": True}


# ── Internal helpers ───────────────────────────────────────────────────────────

def _create_interaction(ticket):
    """Create a TB AI Interaction for a ticket that missed the after_insert hook."""
    from ticketbrain.ai.service import classify_and_resolve
    from ticketbrain.events.hd_ticket import _steps_comment_html

    result = classify_and_resolve(ticket.subject or "", ticket.description or "")
    ai_draft = _steps_comment_html(result)

    interaction = frappe.get_doc({
        "doctype":           "TB AI Interaction",
        "ticket":            ticket.name,
        "category":          result["category"],
        "confidence_score":  result["confidence_score"],
        "status":            "Active",
        "ai_draft_response": ai_draft,
        "approval_status":   "Pending Approval",
    })
    for step in result.get("steps", []):
        interaction.append("steps", {
            "step_number":  step["step_number"],
            "step_content": step["content"],
            "status":       "Pending",
        })
    interaction.insert(ignore_permissions=True)
    frappe.db.commit()
    return interaction


def _get_followup(subject: str, step_content: str, user_message: str, category: str = "") -> str:
    try:
        from ticketbrain.ai.service import generate_followup
        return generate_followup(subject, step_content, user_message, category)
    except Exception:
        return (
            "Thank you for the details. Please try restarting the relevant service "
            "and attempt the step again. If the issue persists, an agent will assist you shortly."
        )
