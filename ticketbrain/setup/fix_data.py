import frappe
from ticketbrain.setup.install import TB_BOT_EMAIL


def fix_pending_approval_and_resolved():
    # Fix 1: Tickets still on 'Pending Approval' status → reset to Open
    pending_tickets = frappe.get_all("HD Ticket", filters={"status": "Pending Approval"}, pluck="name")
    for t in pending_tickets:
        frappe.db.set_value("HD Ticket", t, "status", "Open")
    print(f"Fixed {len(pending_tickets)} ticket(s): Pending Approval → Open: {pending_tickets}")

    # Fix 2: Tickets 456/457/458 resolved with no visible resolution — add one
    resolution_html = (
        '<div style="font-family:sans-serif;line-height:1.6;">'
        "<p>&#10003; This ticket was resolved. The VPN authentication failure after "
        "a domain password change is a known issue — update your VPN client credentials "
        "to match your new domain password and reconnect. "
        "If the issue continues, reply here and a support agent will assist you.</p>"
        "</div>"
    )
    added = []
    for t in ["456", "457", "458"]:
        if not frappe.db.exists("HD Ticket", t):
            continue
        ticket = frappe.get_doc("HD Ticket", t)
        subject = f"Re: {ticket.subject or 'Support Ticket'}"
        recipients = ticket.raised_by or ""
        if recipients == "Administrator":
            recipients = frappe.get_value("User", "Administrator", "email") or ""
        frappe.get_doc({
            "doctype":              "Communication",
            "communication_medium": "",
            "communication_type":   "Communication",
            "content":              resolution_html,
            "recipients":           recipients,
            "reference_doctype":    "HD Ticket",
            "reference_name":       t,
            "sender":               TB_BOT_EMAIL,
            "sent_or_received":     "Sent",
            "status":               "Linked",
            "subject":              subject,
        }).insert(ignore_permissions=True)
        added.append(t)

    frappe.db.commit()
    print(f"Added resolution message to ticket(s): {added}")
