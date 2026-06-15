"""
TicketBrain Assignment Correction API

Agents call these endpoints from the HD Ticket form to either accept the AI's
assignment or correct it. Corrections are:
  1. Persisted as TB Assignment Correction records
  2. Embedded and appended to feedback_index.npz for immediate RAG retrieval
  3. Applied to the live ticket (team, priority, category fields)
"""

from __future__ import annotations

import frappe
from frappe.desk.form.assign_to import add as assign_to


@frappe.whitelist()
def get_teams() -> list:
    """Return all HD Team names for the correction dialog dropdown."""
    return [r.name for r in frappe.get_all("HD Team", fields=["name"], order_by="name asc")]


@frappe.whitelist()
def get_assignment_status(ticket_id: str) -> dict:
    """
    Return AI recommendation + whether the current agent should see Accept/Correct.
    Only the agent assigned to this specific ticket sees the panel.
    """
    current_user = frappe.session.user

    # Only show to the agent the ticket is actually assigned to
    is_assigned = frappe.db.exists("ToDo", {
        "reference_type": "HD Ticket",
        "reference_name": ticket_id,
        "allocated_to":   current_user,
        "status":         "Open",
    })
    if not is_assigned:
        return {"has_ai": False}

    interaction = frappe.db.get_value(
        "TB AI Interaction",
        {"ticket": ticket_id},
        ["name", "category", "confidence_score", "auto_send_decision", "status", "approval_status"],
        as_dict=True,
    )
    if not interaction:
        return {"has_ai": False}

    # Don't show if the agent has already acted on it
    if interaction.status in ("Accepted", "Corrected"):
        return {"has_ai": False}

    correction = frappe.db.get_value(
        "TB Assignment Correction",
        {"ticket": ticket_id},
        ["name", "human_category", "human_team", "human_priority", "correction_reason"],
        as_dict=True,
    )

    ticket = frappe.db.get_value(
        "HD Ticket",
        ticket_id,
        ["agent_group", "priority", "tb_category"],
        as_dict=True,
    )

    return {
        "has_ai":          True,
        "interaction":     interaction,
        "ai_category":     interaction.category or "",
        "ai_team":         ticket.agent_group or "",
        "ai_priority":     ticket.priority or "Medium",
        "confidence":      round((interaction.confidence_score or 0) * 100),
        "decision":        interaction.auto_send_decision or "",
        "already_acted":   bool(correction),
        "correction":      correction,
    }


@frappe.whitelist()
def accept_assignment(ticket_id: str) -> dict:
    """
    Agent accepts the AI assignment as-is. No correction record is created.
    Sets a flag on TB AI Interaction so the Accept button disappears.
    """
    frappe.db.set_value(
        "TB AI Interaction",
        {"ticket": ticket_id},
        "status",
        "Accepted",
    )
    frappe.db.commit()
    return {"ok": True}


@frappe.whitelist()
def submit_correction(
    ticket_id: str,
    human_category: str,
    human_team: str,
    human_priority: str,
    correction_reason: str,
) -> dict:
    """
    Agent corrects AI's assignment.
    1. Creates TB Assignment Correction record.
    2. Embeds and indexes the correction for future retrieval.
    3. Updates the live ticket fields.
    4. Reassigns the ticket to the new team if team changed.
    """
    ticket = frappe.get_doc("HD Ticket", ticket_id)

    ai_interaction = frappe.db.get_value(
        "TB AI Interaction",
        {"ticket": ticket_id},
        ["name", "category"],
        as_dict=True,
    )

    ai_category = ai_interaction.category if ai_interaction else (ticket.tb_category or "")
    ai_team     = ticket.agent_group or ""
    ai_priority = ticket.priority or "Medium"

    # Persist the correction record
    correction = frappe.get_doc({
        "doctype":           "TB Assignment Correction",
        "ticket":            ticket_id,
        "ai_category":       ai_category,
        "human_category":    human_category,
        "ai_team":           ai_team,
        "human_team":        human_team,
        "ai_priority":       ai_priority,
        "human_priority":    human_priority,
        "correction_reason": correction_reason,
        "corrected_by":      frappe.session.user,
        "corrected_at":      frappe.utils.now_datetime(),
        "ticket_subject":    (ticket.subject or "")[:200],
        "ticket_description": (ticket.description or "")[:1000],
    })
    correction.insert(ignore_permissions=True)

    # Apply corrections to the live ticket
    updates = {}
    if human_category and human_category != ai_category:
        updates["tb_category"] = human_category
    if human_priority and human_priority != ai_priority:
        updates["priority"] = human_priority
    if human_team and human_team != ai_team:
        updates["agent_group"] = human_team

    if updates:
        frappe.db.set_value("HD Ticket", ticket_id, updates)

    # Reassign agent if team changed
    if human_team and human_team != ai_team:
        _reassign_to_team(ticket_id, human_team)

    # Mark interaction as corrected
    if ai_interaction:
        frappe.db.set_value("TB AI Interaction", ai_interaction.name, "status", "Corrected")

    frappe.db.commit()

    # Index correction for future RAG retrieval (async so it doesn't block the response)
    frappe.enqueue(
        "ticketbrain.api.correction._index_correction",
        correction_name=correction.name,
        queue="default",
        timeout=60,
    )

    return {"ok": True, "correction": correction.name}


def _index_correction(correction_name: str):
    """Background job: embed and append correction to feedback_index.npz."""
    try:
        doc = frappe.get_doc("TB Assignment Correction", correction_name)

        text = " ".join(filter(None, [
            doc.ticket_subject,
            doc.ticket_description,
            doc.correction_reason,
            f"AI said {doc.ai_category} but correct is {doc.human_category}",
            f"AI team {doc.ai_team} but correct team is {doc.human_team}",
        ])).strip()

        if not text:
            return

        from ticketbrain.ai.service import _load_models
        from ticketbrain.ai.retrieval import append_to_feedback_index

        _, _, embedder = _load_models()
        embedding = embedder.encode([text], convert_to_numpy=True)[0]

        append_to_feedback_index(
            metadata={
                "correction_id":     correction_name,
                "ticket_id":         doc.ticket,
                "ticket_subject":    doc.ticket_subject or "",
                "ai_category":       doc.ai_category or "",
                "human_category":    doc.human_category or "",
                "ai_team":           doc.ai_team or "",
                "human_team":        doc.human_team or "",
                "ai_priority":       doc.ai_priority or "",
                "human_priority":    doc.human_priority or "",
                "correction_reason": doc.correction_reason or "",
                "corrected_by":      doc.corrected_by or "",
            },
            embedding=embedding,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Correction indexing failed")


def _reassign_to_team(ticket_id: str, team_name: str):
    """Assign the least-loaded agent in the new team."""
    try:
        agents = frappe.get_all(
            "HD Team Member",
            filters={"parent": team_name},
            fields=["user"],
        )
        if not agents:
            return

        from ticketbrain.events.hd_ticket import _pick_least_loaded_agent
        user_list = [a.user for a in agents if a.user]
        if not user_list:
            return

        agent = _pick_least_loaded_agent(user_list)
        assign_to({
            "assign_to":   [agent],
            "doctype":     "HD Ticket",
            "name":        ticket_id,
            "description": f"Re-assigned by agent correction to team: {team_name}",
            "notify":      1,
        })
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Team reassignment failed")
