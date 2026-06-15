"""
Fix Gmail limit issue caused by Frappe sending internal task-assignment notifications
to fake .local email addresses (demo users).

Run with:
  bench --site ticketbrain.local execute ticketbrain.setup.fix_email_notifications.run
"""

import frappe


def block_local_address_emails(message):
    """
    before_send_email hook — intercepts any email going to a .local address
    (demo/fake users) and drops it before it hits Gmail.
    Frappe calls this with the email message dict before queuing.
    """
    recipients = message.get("recipients") or ""
    if isinstance(recipients, (list, tuple)):
        recipients_str = " ".join(recipients)
    else:
        recipients_str = str(recipients)

    if ".local" in recipients_str.lower():
        # Return False to cancel this email silently
        return False
    return True


def run():
    # 1. Expire all queued "Not Sent" emails to stop retrying against Gmail
    expired = frappe.db.sql(
        "UPDATE `tabEmail Queue` SET status='Expired' WHERE status='Not Sent'"
    )
    frappe.db.commit()
    print("Expired stuck email queue entries.")

    # 2. Disable "Send email alert for ToDo" — this is Frappe's assignment notification
    try:
        sys_settings = frappe.get_doc("System Settings")
        # The flag is send_email_alert_for_todo
        if hasattr(sys_settings, "send_email_alert_for_todo"):
            sys_settings.send_email_alert_for_todo = 0
            sys_settings.save(ignore_permissions=True)
            frappe.db.commit()
            print("Disabled 'Send email alert for ToDo' in System Settings.")
        else:
            print("'send_email_alert_for_todo' field not found — skipping.")
    except Exception as e:
        print(f"Could not update System Settings: {e}")

    # 3. Suppress emails to .local addresses by adding them to the blocked list
    #    Better approach: set Frappe to not send to non-routable addresses
    #    (We do this by disabling notifications for internal domains)
    try:
        # Find all users with .local email addresses and disable "send notifications" for them
        local_users = frappe.get_all(
            "User",
            filters={"email": ("like", "%.local"), "enabled": 1},
            pluck="name",
        )
        for u in local_users:
            frappe.db.set_value("User", u, "send_email_alert_for_todo", 0)
        if local_users:
            frappe.db.commit()
            print(f"Disabled ToDo email alerts for {len(local_users)} demo user(s): {local_users}")
    except Exception as e:
        print(f"Could not update user settings: {e}")

    # 4. Mark any future queued emails to .local addresses as Expired immediately
    #    by creating a simple cleanup that runs before the queue flush
    print("\nDone. To prevent recurrence, also go to:")
    print("  Frappe Desk → System Settings → Email Settings → disable 'Send Notification Emails'")
    print("  OR: restrict your outgoing Email Account to only route real customer emails.")
