import re

import frappe

from ticketbrain.setup.install import TB_BOT_EMAIL

# Positive: standalone words that reliably mean "it worked"
_POSITIVE_WORDS = {"fixed", "resolved", "done", "works", "worked", "perfect", "solved"}
# Negative: must be a phrase — never a single ambiguous word like "still" or "no"
_NEGATIVE_PHRASES = {
    "not working", "doesn't work", "didn't work", "didnt work",
    "not work", "still not", "still the same", "same issue",
    "same problem", "tried that", "already tried", "tried this",
    "no luck", "failed", "not resolved", "not fixed", "not helping",
    "doesn't help", "didn't help", "no change",
}


def on_comment_created(doc, method):
    """
    Fires on HD Ticket Comment insert (agent internal comments / old API).
    Customer portal messages come in as Communication — see on_communication_created.
    """
    if doc.commented_by == TB_BOT_EMAIL:
        return

    raised_by = frappe.db.get_value("HD Ticket", doc.reference_ticket, "raised_by")
    if doc.commented_by != raised_by:
        try:
            _handle_agent_reply_on_pending(doc)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "TicketBrain: Agent pending reply handling failed")
        return

    try:
        _handle_customer_reply(doc)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Step tracking failed")


def on_communication_created(doc, method):
    """
    Fires on Communication insert.
    Customer portal replies use create_communication_via_contact which creates
    a Communication (sent_or_received=Received), not an HD Ticket Comment.
    """
    if doc.reference_doctype != "HD Ticket" or not doc.reference_name:
        return
    if doc.sender == TB_BOT_EMAIL:
        return

    if doc.sent_or_received == "Received":
        # Customer message from the portal
        try:
            _handle_customer_reply_from_communication(doc)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "TicketBrain: Communication step tracking failed")
    elif doc.sent_or_received == "Sent":
        # Agent sent a reply directly (not via Approve button) on a Pending Approval ticket
        try:
            _handle_agent_comm_on_pending(doc)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "TicketBrain: Agent communication handling failed")


def _handle_agent_reply_on_pending(doc):
    """
    Agent writes an HD Ticket Comment on a Pending Approval ticket — treat as custom response.
    """
    _mark_agent_override(doc.reference_ticket, doc.content)


def _handle_agent_comm_on_pending(doc):
    """
    Agent sends a Communication reply on a Pending Approval ticket — treat as custom response.
    """
    _mark_agent_override(doc.reference_name, doc.content)


def _mark_agent_override(ticket_id: str, content: str):
    """Mark the pending AI draft as overridden by an agent reply."""
    existing = frappe.get_all(
        "TB AI Interaction",
        filters={"ticket": ticket_id, "approval_status": "Pending Approval"},
        fields=["name"],
        limit=1,
    )
    if not existing:
        return

    interaction = frappe.get_doc("TB AI Interaction", existing[0]["name"])
    interaction.approval_status = "Modified"
    interaction.agent_response  = _strip_html(content or "")
    interaction.status          = "Escalated"
    interaction.save(ignore_permissions=True)

    from ticketbrain.events.hd_ticket import _reapply_sla
    frappe.db.set_value("HD Ticket", ticket_id, "status", "Open")
    _reapply_sla(ticket_id)
    frappe.db.commit()


def _handle_customer_reply_from_communication(doc):
    """Step-tracking for customer messages that arrive as Communication records (portal)."""

    class _CommAdapter:
        reference_ticket = doc.reference_name
        commented_by     = doc.sender
        content          = doc.content

    _handle_customer_reply(_CommAdapter())


def _handle_customer_reply(doc):
    ticket_id = doc.reference_ticket
    message   = _strip_html(doc.content or "")

    existing = frappe.get_all(
        "TB AI Interaction",
        filters={"ticket": ticket_id, "status": "Active"},
        fields=["name"],
        limit=1,
    )
    if not existing:
        return  # Already escalated or resolved — nothing to do

    interaction = frappe.get_doc("TB AI Interaction", existing[0]["name"])

    # Agent hasn't reviewed the AI draft yet — no response was sent to the customer,
    # so there is nothing for the customer to be replying about step-wise.
    if interaction.approval_status == "Pending Approval":
        return
    steps       = interaction.steps

    # Check if the customer explicitly mentioned a step number (e.g. "step 2 not working")
    mentioned_idx = _extract_mentioned_step(message, len(steps))

    # Current active step = first Pending/Stuck
    current_idx = next(
        (i for i, s in enumerate(steps) if s.status in ("Pending", "Stuck")),
        None,
    )

    # Use the explicitly mentioned step if given, else fall back to current
    target_idx = mentioned_idx if mentioned_idx is not None else current_idx

    sentiment = _detect_sentiment(message)

    if target_idx is None:
        # No active step — all done, check if resolved
        if sentiment == "positive":
            _mark_resolved(ticket_id, interaction)
        else:
            _trigger_escalation(ticket_id, interaction)
        frappe.db.commit()
        return

    step = steps[target_idx]

    if sentiment == "positive":
        step.status = "Satisfied"
        interaction.save(ignore_permissions=True)

        # Find next unsatisfied step
        next_idx = next(
            (i for i in range(target_idx + 1, len(steps)) if steps[i].status != "Satisfied"),
            None,
        )
        if next_idx is not None:
            _post_customer_reply(ticket_id, _next_step_html(next_idx, len(steps), steps[next_idx].step_content))
        else:
            _post_customer_reply(ticket_id, _all_steps_done_html())

    elif sentiment == "negative":
        step.status       = "Stuck"
        step.user_message = message
        ticket   = frappe.get_doc("HD Ticket", ticket_id)
        followup = _get_followup(ticket.subject, step.step_content, message, interaction.category or "")
        step.ai_followup = followup
        interaction.save(ignore_permissions=True)
        _post_customer_reply(ticket_id, _followup_html(followup, target_idx))

    else:
        interaction.save(ignore_permissions=True)
        _post_customer_reply(ticket_id, _nudge_html(target_idx, step.step_content))

    frappe.db.commit()


def _mark_resolved(ticket_id: str, interaction):
    interaction.status = "Resolved"
    interaction.save(ignore_permissions=True)
    frappe.db.set_value("HD Ticket", ticket_id, "status", "AI Resolved")
    _post_customer_reply(ticket_id, _resolved_html())


def _trigger_escalation(ticket_id: str, interaction):
    from ticketbrain.events.hd_ticket import _auto_escalate
    interaction.status = "Escalated"
    interaction.save(ignore_permissions=True)
    _auto_escalate(ticket_id, interaction.category or "", interaction.name)
    _post_customer_reply(ticket_id, _manual_escalation_html())


# ── Step number extraction ──────────────────────────────────────────────────────

def _extract_mentioned_step(text: str, total: int) -> int | None:
    """
    Parse the customer's message for an explicit step reference.
    'step 2 not working', '2nd step', '#3' etc. → 0-indexed integer.
    """
    lower = text.lower()
    patterns = [
        r'\bstep\s*(\d+)\b',
        r'\b(\d+)(?:st|nd|rd|th)?\s+step\b',
        r'#(\d+)',
    ]
    for p in patterns:
        m = re.search(p, lower)
        if m:
            n = int(m.group(1))
            if 1 <= n <= total:
                return n - 1  # convert to 0-indexed
    return None


# ── Sentiment detection ────────────────────────────────────────────────────────

def _detect_sentiment(text: str) -> str:
    lower = text.lower()
    # Phrases first — must match as substrings (e.g. "still not working")
    if any(phrase in lower for phrase in _NEGATIVE_PHRASES):
        return "negative"
    # Positive only on whole words to avoid false positives
    words = set(lower.split())
    if any(word in words for word in _POSITIVE_WORDS):
        return "positive"
    return "neutral"


# ── HTML builders ──────────────────────────────────────────────────────────────

def _next_step_html(idx: int, total: int, content: str) -> str:
    return (
        '<div style="font-family:sans-serif;line-height:1.6;">'
        f"<p>&#10003; Got it — here is <strong>Step {idx + 1} of {total}</strong>:</p>"
        f'<blockquote style="border-left:3px solid #2563eb;margin:4px 0;padding:8px 16px;color:#1e40af;">'
        f"{content}</blockquote>"
        "</div>"
    )


def _all_steps_done_html() -> str:
    return (
        '<div style="font-family:sans-serif;line-height:1.6;">'
        "<p>&#10003; You have gone through all the steps. Did it fix your issue? "
        "Reply <strong>yes</strong> to close the ticket, or let us know what is still happening.</p>"
        "</div>"
    )


def _resolved_html() -> str:
    return (
        '<div style="font-family:sans-serif;line-height:1.6;">'
        "<p>&#127881; Glad to hear it is resolved! This ticket has been marked <strong>AI Resolved</strong>. "
        "Feel free to open a new ticket if you need help again.</p>"
        "</div>"
    )


def _followup_html(followup: str, step_idx: int) -> str:
    return (
        '<div style="font-family:sans-serif;line-height:1.6;">'
        f"<p><strong>TicketBrain AI</strong> — Additional guidance for Step {step_idx + 1}:</p>"
        f"<p>{followup}</p>"
        "</div>"
    )


def _nudge_html(idx: int, content: str) -> str:
    return (
        '<div style="font-family:sans-serif;line-height:1.6;">'
        f"<p>Thanks for the update. Give <strong>Step {idx + 1}</strong> a try:</p>"
        f'<blockquote style="border-left:3px solid #2563eb;margin:4px 0;padding:8px 16px;color:#1e40af;">'
        f"{content}</blockquote>"
        "</div>"
    )


def _manual_escalation_html() -> str:
    return (
        '<div style="font-family:sans-serif;line-height:1.6;">'
        "<p>&#9888; It looks like the issue is still unresolved after all steps. "
        "This ticket has been <strong>escalated to a support agent</strong> who will follow up shortly. "
        "Please add any additional details about what you have already tried.</p>"
        "</div>"
    )


# ── Utilities ──────────────────────────────────────────────────────────────────

def _post_customer_reply(ticket_id: str, content: str):
    """Post a bot response visible to the customer in the portal (creates Communication)."""
    from ticketbrain.events.hd_ticket import _post_customer_reply as _reply
    _reply(ticket_id, content)


def _get_followup(subject: str, step_content: str, user_message: str, category: str = "") -> str:
    try:
        from ticketbrain.ai.service import generate_followup
        return generate_followup(subject, step_content, user_message, category)
    except Exception:
        return (
            "Thank you for the update. Could you describe exactly what happens when you try this step? "
            "The more detail you share, the faster we can resolve this."
        )


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html).strip()
