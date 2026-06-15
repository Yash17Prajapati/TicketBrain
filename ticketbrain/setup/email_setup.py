import os
import frappe


def setup_outgoing_email():
    """
    bench --site ticketbrain.local execute ticketbrain.setup.email_setup.setup_outgoing_email

    Reads from env vars:
      TB_EMAIL_SENDER   — e.g. you@gmail.com
      TB_EMAIL_PASSWORD — Gmail App Password (16 chars)
      TB_EMAIL_SMTP_HOST — default smtp.gmail.com
      TB_EMAIL_SMTP_PORT — default 587
    """
    sender   = os.environ.get("TB_EMAIL_SENDER", "").strip()
    password = os.environ.get("TB_EMAIL_PASSWORD", "").strip()
    host     = os.environ.get("TB_EMAIL_SMTP_HOST", "smtp.gmail.com").strip()
    port     = int(os.environ.get("TB_EMAIL_SMTP_PORT", "587"))

    if not sender or not password:
        print("ERROR: TB_EMAIL_SENDER and TB_EMAIL_PASSWORD must be set.")
        return

    existing = frappe.db.exists("Email Account", sender)
    if existing:
        acc = frappe.get_doc("Email Account", sender)
        print(f"Updating existing Email Account: {sender}")
    else:
        acc = frappe.new_doc("Email Account")
        acc.email_account_name = sender
        print(f"Creating Email Account: {sender}")

    acc.email_id              = sender
    acc.password              = password
    acc.smtp_server           = host
    acc.smtp_port             = port
    acc.use_tls               = 1
    acc.enable_outgoing       = 1
    acc.default_outgoing      = 1
    acc.no_smtp_authentication = 0

    if existing:
        acc.save(ignore_permissions=True)
    else:
        acc.insert(ignore_permissions=True)

    # Wire up as Helpdesk default sender
    try:
        frappe.db.set_single_value("HD Settings", "sender_email", sender)
        print(f"Set HD Settings → sender_email = {sender}")
    except Exception as e:
        print(f"Note: HD Settings update skipped: {e}")

    frappe.db.commit()
    print("Email account configured. Run `bench --site ticketbrain.local restart` to apply.")
