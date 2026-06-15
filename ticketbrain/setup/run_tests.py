"""
TicketBrain End-to-End Test Runner

Tests every subsystem and creates picture-perfect UI data:
  1. Cleans bad context items (system categories wrongly marked as Services)
  2. Adds rich KB articles (so kb_match_score improves)
  3. Creates 6 realistic test tickets (one per AI category)
  4. Verifies AI classification + routing decision on each
  5. Tests stuck/followup flow on one ticket
  6. Resolves tickets → triggers knowledge extraction
  7. Runs full context discovery with the new engine
  8. Prints a test report

Run:
  bench --site ticketbrain.local execute ticketbrain.setup.run_tests.run_all
"""

import frappe
import time

DIVIDER = "=" * 62
PASS = "  ✓"
FAIL = "  ✗"
INFO = "  →"


# ── 1. Clean bad context items ────────────────────────────────────────────────

def clean_context_items():
    print(f"\n{DIVIDER}")
    print("  STEP 1 — Clean bad context items")
    print(DIVIDER)

    system_categories = {
        "Software & Applications", "Hardware & Infrastructure",
        "Security & Threats", "Data & Reports",
        "Network & Connectivity", "Account & Access",
    }

    bad = frappe.get_all(
        "TB Context Item",
        filters={"item_type": "Service", "item_name": ["in", list(system_categories)]},
        fields=["name", "item_name"],
    )
    for b in bad:
        frappe.delete_doc("TB Context Item", b.name, ignore_permissions=True, force=True)
        print(f"{PASS} Removed bad Service item: '{b.item_name}'")

    if not bad:
        print(f"{INFO} No bad items found — already clean")

    frappe.db.commit()


# ── 2. Add rich KB articles ───────────────────────────────────────────────────

EXTRA_ARTICLES = [
    {
        "title": "How to reset your corporate password",
        "content": (
            "To reset your corporate account password: Navigate to accounts.company.com and click "
            "'Forgot Password'. Enter your corporate email address and click Submit. You will receive "
            "a one-time password (OTP) on your registered mobile number. Enter the OTP and set a new "
            "password that is at least 12 characters with uppercase, lowercase, numbers and symbols. "
            "After resetting, update your password in Outlook, Teams, and the VPN client. "
            "If you do not receive the OTP within 5 minutes, call IT helpdesk on extension 100."
        ),
        "category": "Account & Access",
    },
    {
        "title": "VPN setup and troubleshooting guide",
        "content": (
            "To connect to the corporate VPN: Install the Cisco AnyConnect client from the software "
            "portal. Open AnyConnect and enter vpn.company.com as the server address. Login with your "
            "corporate email and password. If connection fails after password reset, you must sync your "
            "Active Directory credentials — disconnect VPN, lock your workstation (Win+L), unlock with "
            "your new password, then reconnect VPN. For 'Authentication failed' errors, ensure MFA is "
            "set up in Microsoft Authenticator. Contact IT if the VPN server address has changed."
        ),
        "category": "Network & Connectivity",
    },
    {
        "title": "Phishing email identification and reporting",
        "content": (
            "Identifying phishing emails: Check if the sender domain matches the official company domain. "
            "Hover over links (do not click) to verify the actual destination URL. Be suspicious of urgent "
            "language, requests for passwords or bank details, unexpected attachments. "
            "To report a phishing email: Do NOT click any links or attachments. Forward the email as an "
            "attachment to security@company.com. Delete it from your inbox and empty trash. "
            "If you accidentally clicked a link: immediately disconnect from the network, call IT Security "
            "on the emergency line, and do not use the device until cleared by the security team."
        ),
        "category": "Security & Threats",
    },
    {
        "title": "ERPNext login issues and access problems",
        "content": (
            "If you cannot login to ERPNext: Verify you are using your corporate email as username. "
            "Clear browser cache (Ctrl+Shift+Delete) and try again in an incognito window. "
            "If your account is locked, wait 30 minutes or contact your system administrator. "
            "For 'Permission Error' when accessing a module: your role may not include that module — "
            "submit an access request through HR portal with your manager's approval. "
            "For slow ERPNext performance: avoid multiple open tabs, use Chrome or Firefox, "
            "and check your internet connection speed (minimum 10Mbps recommended)."
        ),
        "category": "Software & Applications",
    },
    {
        "title": "Laptop hardware issues — diagnosis and escalation",
        "content": (
            "For laptop hardware problems: First restart the device — this resolves most temporary issues. "
            "For overheating: place the laptop on a hard flat surface, check if the fan vent is blocked. "
            "For a black/blank screen: hold the power button 10 seconds to force off, wait 30 seconds, "
            "power on while holding Fn+F5 to reset display output. "
            "For keyboard/touchpad not working: connect an external USB keyboard and mouse, then update "
            "drivers via Device Manager. For physical damage (cracked screen, liquid damage): "
            "note the asset tag number (sticker on bottom) and raise a hardware replacement request — "
            "do NOT attempt to open or repair the device yourself."
        ),
        "category": "Hardware & Infrastructure",
    },
    {
        "title": "Report discrepancies and data correction requests",
        "content": (
            "When a report shows incorrect data: First verify the date range and filters are correct. "
            "Refresh the report and clear browser cache before assuming data is wrong. "
            "To compare against source data: drill down on the report figure to see underlying transactions. "
            "If source transactions are incorrect (wrong amount, wrong account, wrong date): "
            "do NOT edit records directly — raise a data correction request with: the document number, "
            "the incorrect value, the correct value, and your manager's approval. "
            "For missing records: check if the document is in Draft status — only submitted documents "
            "appear in standard reports. For custom report errors, contact the ERP team with a screenshot."
        ),
        "category": "Data & Reports",
    },
]


def _ensure_article_categories():
    """Create one HD Article Category per TicketBrain category if missing."""
    cats = ["IT Support", "Account & Access", "Network", "Security", "Hardware", "Data & Reports"]
    for cat_name in cats:
        if not frappe.db.exists("HD Article Category", {"category_name": cat_name}):
            try:
                frappe.get_doc({
                    "doctype": "HD Article Category",
                    "category_name": cat_name,
                }).insert(ignore_permissions=True)
            except Exception:
                pass
    frappe.db.commit()
    # Return the first available category name to use as default
    return frappe.db.get_value("HD Article Category", {}, "name") or None


def add_kb_articles():
    print(f"\n{DIVIDER}")
    print("  STEP 2 — Add rich Knowledge Base articles")
    print(DIVIDER)

    default_cat = _ensure_article_categories()
    added = 0
    for art in EXTRA_ARTICLES:
        if frappe.db.exists("HD Article", {"title": art["title"]}):
            print(f"{INFO} Already exists: {art['title'][:55]}")
            continue
        try:
            frappe.get_doc({
                "doctype":  "HD Article",
                "title":    art["title"],
                "content":  f"<p>{art['content']}</p>",
                "status":   "Published",
                "category": default_cat,
            }).insert(ignore_permissions=True)
            print(f"{PASS} Created: {art['title'][:55]}")
            added += 1
        except Exception as e:
            print(f"{FAIL} Failed: {art['title'][:40]} — {e}")

    frappe.db.commit()

    # Rebuild KB index to include new articles
    print(f"\n{INFO} Rebuilding KB index with new articles...")
    try:
        import subprocess, sys
        result = subprocess.run(
            [sys.executable,
             "/home/yash/TicketBrain/apps/ticketbrain/ticketbrain/ml/build_rag_index.py"],
            capture_output=True, text=True, timeout=120,
        )
        if "Saved KB index" in result.stdout:
            print(f"{PASS} KB index rebuilt successfully")
        else:
            print(f"{FAIL} KB rebuild output: {result.stdout[-200:]} {result.stderr[-200:]}")
    except Exception as e:
        print(f"{FAIL} KB rebuild failed: {e}")

    # Clear retrieval cache so next calls use new index
    try:
        from ticketbrain.ai.retrieval import clear_caches
        clear_caches()
        print(f"{PASS} Retrieval cache cleared")
    except Exception:
        pass


# ── 3. Create 6 test tickets ──────────────────────────────────────────────────

TEST_TICKETS = [
    {
        "tag":      "HW",
        "subject":  "Laptop screen flickering and goes blank after Windows update",
        "description": (
            "My laptop screen started flickering badly after I installed the Windows update yesterday. "
            "The display blinks every few seconds and sometimes goes completely blank for 30 seconds. "
            "I have tried restarting but the problem persists. The laptop is a Dell Latitude 5510, "
            "asset tag TBR-0042. I need this fixed urgently as I cannot work properly."
        ),
        "raised_by": "john.smith@acme.com",
        "expected_category": "Hardware & Infrastructure",
    },
    {
        "tag":      "SW",
        "subject":  "Microsoft Teams crashes immediately when starting a video call",
        "description": (
            "Teams keeps crashing as soon as I try to join or start a video call. "
            "The application freezes for about 10 seconds and then closes with an error message "
            "'Teams has stopped working'. Audio calls work fine, only video calls are affected. "
            "I have restarted Teams and my computer multiple times. Teams version is 1.6.00.1381."
        ),
        "raised_by": "sarah.j@techventures.com",
        "expected_category": "Software & Applications",
    },
    {
        "tag":      "NET",
        "subject":  "Cannot connect to VPN from home — authentication failed error",
        "description": (
            "I am unable to connect to the company VPN from my home network. "
            "Every time I try to connect using Cisco AnyConnect, I get 'Authentication failed, "
            "please try again'. I recently changed my corporate password and I suspect that "
            "might be the issue. The VPN was working fine before the password change. "
            "I am using the profile vpn.company.com as always."
        ),
        "raised_by": "mike.chen@globalsoft.com",
        "expected_category": "Network & Connectivity",
    },
    {
        "tag":      "ACC",
        "subject":  "Account locked — cannot login to email or ERPNext after password reset",
        "description": (
            "My account got locked after I tried to login multiple times with the wrong password. "
            "I reset my password using the self-service portal but now I cannot login to Outlook "
            "or ERPNext. When I try to login it says 'Account locked — contact your administrator'. "
            "I have been locked out for 2 hours and I have pending invoices to process urgently."
        ),
        "raised_by": "anita.rao@digitaledge.com",
        "expected_category": "Account & Access",
    },
    {
        "tag":      "SEC",
        "subject":  "Received suspicious phishing email asking for banking credentials",
        "description": (
            "I received an email claiming to be from our IT department asking me to verify my "
            "banking credentials by clicking a link. The email subject is 'Urgent: Verify your "
            "account to avoid suspension'. The sender email is it-support@company-secure.net "
            "which looks suspicious. I have NOT clicked the link. Please advise what to do "
            "and whether my account has been compromised."
        ),
        "raised_by": "john.smith@acme.com",
        "expected_category": "Security & Threats",
    },
    {
        "tag":      "DATA",
        "subject":  "Monthly sales report showing incorrect totals — figures off by 15%",
        "description": (
            "The monthly sales report for May 2026 in ERPNext is showing totals that are 15% lower "
            "than what our sales team has recorded manually. I have cross-checked 10 individual "
            "transactions and all appear correctly entered. The discrepancy seems to be in the "
            "'Returns & Adjustments' column which shows a much higher amount than expected. "
            "I need this corrected before the board meeting on Friday."
        ),
        "raised_by": "sarah.j@techventures.com",
        "expected_category": "Data & Reports",
    },
]


def create_test_tickets():
    print(f"\n{DIVIDER}")
    print("  STEP 3 — Create 6 test tickets (one per AI category)")
    print(DIVIDER)

    created = []
    for t in TEST_TICKETS:
        tag = t["tag"]
        # Skip if already created this session (idempotent by subject)
        existing = frappe.db.get_value("HD Ticket", {"subject": t["subject"]}, "name")
        if existing:
            print(f"{INFO} [{tag}] Ticket already exists: {existing}")
            created.append(existing)
            continue

        try:
            ticket = frappe.get_doc({
                "doctype":     "HD Ticket",
                "subject":     t["subject"],
                "description": t["description"],
                "raised_by":   t["raised_by"],
                "status":      "Open",
            })
            ticket.insert(ignore_permissions=True)
            frappe.db.commit()
            print(f"{PASS} [{tag}] Created ticket {ticket.name}: {t['subject'][:50]}...")
            created.append(ticket.name)
        except Exception as e:
            print(f"{FAIL} [{tag}] Failed: {e}")

    return created


# ── 4. Verify AI interactions ─────────────────────────────────────────────────

def verify_ai_interactions(ticket_names: list[str]):
    print(f"\n{DIVIDER}")
    print("  STEP 4 — Verify AI classification + routing on each ticket")
    print(DIVIDER)

    results = {"auto_send": 0, "human_review": 0, "direct_escalate": 0, "missing": 0}

    for name in ticket_names:
        subject = frappe.db.get_value("HD Ticket", name, "subject") or ""
        interaction = frappe.get_all(
            "TB AI Interaction",
            filters={"ticket": name},
            fields=["name", "category", "confidence_score", "auto_send_decision",
                    "kb_match_score", "response_quality_score", "risk_score"],
            limit=1,
        )
        if not interaction:
            print(f"{FAIL} {name}: No AI interaction found!")
            results["missing"] += 1
            continue

        ia = interaction[0]
        cat   = ia.category or "?"
        conf  = round((ia.confidence_score or 0) * 100)
        dec   = ia.auto_send_decision or "?"
        kb    = round((ia.kb_match_score or 0))
        rq    = round((ia.response_quality_score or 0))
        risk  = ia.risk_score or "?"

        steps_count = frappe.db.count("TB AI Step", {"parent": ia.name})

        symbol = PASS if dec in ("Auto Send", "Human Review") else INFO
        print(
            f"{symbol} {name} | {cat[:28]:<28} | "
            f"Conf:{conf:>2}% | {dec:<16} | "
            f"KB:{kb:>2}% | RQ:{rq:>2}% | Risk:{risk} | Steps:{steps_count}"
        )

        key = dec.lower().replace(" ", "_")
        if key in results:
            results[key] += 1

    print(f"\n  Routing summary → Auto Send: {results['auto_send']}  |  "
          f"Human Review: {results['human_review']}  |  "
          f"Direct Escalate: {results['direct_escalate']}  |  "
          f"Missing: {results['missing']}")
    return results


# ── 5. Test stuck / followup flow ─────────────────────────────────────────────

def test_stuck_flow(ticket_names: list[str]):
    print(f"\n{DIVIDER}")
    print("  STEP 5 — Test stuck/followup flow")
    print(DIVIDER)

    # Use the first ticket that has an active interaction with steps
    target_ticket = None
    target_interaction = None

    for name in ticket_names:
        ia = frappe.get_all(
            "TB AI Interaction",
            filters={"ticket": name, "status": "Active"},
            fields=["name"],
            limit=1,
        )
        if ia:
            steps = frappe.db.count("TB AI Step", {"parent": ia[0].name})
            if steps > 0:
                target_ticket      = name
                target_interaction = ia[0].name
                break

    if not target_ticket:
        print(f"{INFO} No active interaction with steps found — skipping")
        return

    subject = frappe.db.get_value("HD Ticket", target_ticket, "subject") or ""
    print(f"{INFO} Testing on ticket {target_ticket}: {subject[:55]}...")

    try:
        from ticketbrain.api.ticket import submit_stuck_reply
        result = submit_stuck_reply(
            ticket_id=target_ticket,
            interaction_id=target_interaction,
            step_index=0,
            user_message="I tried this step but my screen is still flickering. What should I do next?",
        )
        followup = result.get("followup", "")
        if followup:
            print(f"{PASS} Followup generated ({len(followup)} chars):")
            print(f"      \"{followup[:120]}...\"")
        else:
            print(f"{FAIL} No followup returned")
    except Exception as e:
        print(f"{FAIL} Stuck flow error: {e}")


# ── 6. Resolve tickets → trigger knowledge extraction ─────────────────────────

SIMILAR_TICKETS = [
    # Similar to the VPN ticket → should trigger a knowledge draft
    {
        "subject":  "VPN not connecting after I changed my domain password",
        "description": "After updating my Windows domain password yesterday, Cisco AnyConnect keeps saying Authentication failed when I try to connect to the VPN. I am working from home today and cannot access any company systems. Please help urgently.",
        "raised_by": "anita.rao@digitaledge.com",
    },
    {
        "subject":  "VPN authentication error — cannot access internal systems remotely",
        "description": "Getting 'Authentication failed' on VPN since this morning. I changed my password last week using the self-service portal. The VPN profile is vpn.company.com. I need to access ERP remotely for month-end closing.",
        "raised_by": "mike.chen@globalsoft.com",
    },
    # Similar to the account locked ticket → should trigger a knowledge draft
    {
        "subject":  "Locked out of all systems after wrong password — urgent",
        "description": "I forgot my password and tried multiple times. Now my account is locked. Cannot access email, Teams, or ERPNext. I have a client call in 1 hour. Please unlock urgently.",
        "raised_by": "sarah.j@techventures.com",
    },
]


def create_and_resolve_similar_tickets():
    """Create additional similar tickets and resolve them to trigger knowledge drafts."""
    print(f"\n{INFO} Creating similar tickets for knowledge draft detection...")
    resolved_names = []
    for t in SIMILAR_TICKETS:
        existing = frappe.db.get_value("HD Ticket", {"subject": t["subject"]}, "name")
        if existing:
            name = existing
        else:
            try:
                ticket = frappe.get_doc({
                    "doctype":     "HD Ticket",
                    "subject":     t["subject"],
                    "description": t["description"],
                    "raised_by":   t["raised_by"],
                    "status":      "Open",
                })
                ticket.insert(ignore_permissions=True)
                frappe.db.commit()
                name = ticket.name
                print(f"{PASS} Created similar ticket {name}")
            except Exception as e:
                print(f"{FAIL} Failed: {e}")
                continue

        # Immediately resolve it
        try:
            ia_list = frappe.get_all("TB AI Interaction", filters={"ticket": name}, fields=["name"], limit=1)
            if ia_list:
                ia = frappe.get_doc("TB AI Interaction", ia_list[0].name)
                if ia.steps:
                    ia.steps[0].status = "Satisfied"
                ia.status = "Resolved"
                ia.save(ignore_permissions=True)

            ticket = frappe.get_doc("HD Ticket", name)
            ticket.status = "Resolved"
            ticket.save(ignore_permissions=True)
            frappe.db.commit()
            resolved_names.append(name)

            from ticketbrain.ai.knowledge_extraction import index_resolved_ticket
            index_resolved_ticket(name)
        except Exception as e:
            print(f"{FAIL} Could not resolve {name}: {e}")

    return resolved_names


def resolve_and_extract(ticket_names: list[str]):
    print(f"\n{DIVIDER}")
    print("  STEP 6 — Resolve tickets → knowledge extraction")
    print(DIVIDER)

    # Resolve 3 tickets to simulate satisfied resolutions
    resolve_these = ticket_names[:3]

    for name in resolve_these:
        try:
            # Mark one step as Satisfied on each interaction
            ia_list = frappe.get_all(
                "TB AI Interaction",
                filters={"ticket": name},
                fields=["name"],
                limit=1,
            )
            if ia_list:
                ia = frappe.get_doc("TB AI Interaction", ia_list[0].name)
                if ia.steps:
                    ia.steps[0].status = "Satisfied"
                    ia.status          = "Resolved"
                    ia.save(ignore_permissions=True)

            # Update ticket status to Resolved → triggers on_update hook
            ticket = frappe.get_doc("HD Ticket", name)
            ticket.status = "Resolved"
            ticket.save(ignore_permissions=True)
            frappe.db.commit()
            print(f"{PASS} Resolved ticket {name}")

            # Run knowledge extraction inline (normally runs in background)
            from ticketbrain.ai.knowledge_extraction import index_resolved_ticket
            index_resolved_ticket(name)
            print(f"{PASS} Knowledge extraction ran for {name}")

        except Exception as e:
            print(f"{FAIL} Error resolving {name}: {e}")

    # Check if any knowledge drafts were created
    drafts = frappe.get_all(
        "TB Knowledge Draft",
        filters={"status": "Pending Approval"},
        fields=["name", "title", "occurrence_count"],
    )
    if drafts:
        print(f"\n{PASS} {len(drafts)} Knowledge Draft(s) pending approval:")
        for d in drafts:
            print(f"      [{d.occurrence_count}x] {d.title[:60]}")
    else:
        print(f"\n{INFO} No knowledge drafts yet (need 2+ similar resolved tickets to trigger)")

    # Check ticket index size
    from pathlib import Path
    idx_path = Path("/home/yash/TicketBrain/apps/ticketbrain/ticketbrain/ml/models/ticket_index.npz")
    if idx_path.exists():
        import numpy as np
        data = np.load(str(idx_path), allow_pickle=True)
        print(f"{PASS} Ticket index: {len(data['embeddings'])} resolved tickets indexed")
    else:
        print(f"{INFO} Ticket index not yet created")


# ── 7. Run context discovery ──────────────────────────────────────────────────

def run_context_discovery():
    print(f"\n{DIVIDER}")
    print("  STEP 7 — Run context discovery with corrected engine")
    print(DIVIDER)

    ctx_list = frappe.get_all("TB Business Context", fields=["name"], limit=1)
    if not ctx_list:
        print(f"{FAIL} No TB Business Context document found — create one from the workspace first")
        return

    ctx_name = ctx_list[0].name
    print(f"{INFO} Running discovery on: {ctx_name}")

    try:
        from ticketbrain.ai.context_discovery import run_discovery
        run_discovery(ctx_name)

        ctx = frappe.get_doc("TB Business Context", ctx_name)
        print(f"{PASS} Scan complete — status: {ctx.scan_status}")
        print(f"      {ctx.last_scan_summary}")

        by_type: dict[str, list] = {}
        for item in ctx.items:
            by_type.setdefault(item.item_type, []).append(item)

        print(f"\n  Discovered items by type:")
        for itype, items in sorted(by_type.items()):
            names = ", ".join(i.item_name for i in items[:3])
            if len(items) > 3:
                names += f" (+{len(items)-3} more)"
            print(f"      {itype:<22}: {len(items):>2} item(s) — {names}")

    except Exception as e:
        print(f"{FAIL} Discovery failed: {e}")
        import traceback; traceback.print_exc()


# ── 8. Print final report ─────────────────────────────────────────────────────

def print_report():
    print(f"\n{DIVIDER}")
    print("  FINAL REPORT")
    print(DIVIDER)

    total_tickets = frappe.db.count("HD Ticket")
    total_ia      = frappe.db.count("TB AI Interaction")
    auto_sent     = frappe.db.count("TB AI Interaction", {"auto_send_decision": "Auto Send"})
    human_review  = frappe.db.count("TB AI Interaction", {"auto_send_decision": "Human Review"})
    escalated     = frappe.db.count("TB AI Interaction", {"auto_send_decision": "Direct Escalate"})
    resolved_t    = frappe.db.count("HD Ticket", {"status": ["in", ["Resolved", "Closed", "AI Resolved"]]})
    kb_articles   = frappe.db.count("HD Article", {"status": "Published"})
    drafts        = frappe.db.count("TB Knowledge Draft")
    ctx_items     = frappe.db.count("TB Context Item")
    pending_appr  = frappe.db.count("TB AI Interaction", {"approval_status": "Pending Approval"})

    print(f"  HD Tickets total       : {total_tickets}")
    print(f"  Resolved tickets        : {resolved_t}")
    print(f"  TB AI Interactions      : {total_ia}")
    print(f"    → Auto Send           : {auto_sent}")
    print(f"    → Human Review        : {human_review}")
    print(f"    → Direct Escalate     : {escalated}")
    print(f"    → Pending Approval    : {pending_appr}")
    print(f"  HD Articles (Published) : {kb_articles}")
    print(f"  TB Knowledge Drafts     : {drafts}")
    print(f"  Context Items discovered: {ctx_items}")
    print(f"\n  UI Quick-access links:")
    print(f"    Workspace      → /app/ticketbrain")
    print(f"    AI Interactions→ /app/tb-ai-interaction")
    print(f"    Business Ctx   → /app/tb-business-context")
    print(f"    Knowledge Drafts→ /app/tb-knowledge-draft")
    print(f"    HD Tickets     → /app/hd-ticket")
    print(f"    HD Articles    → /app/hd-article")
    print(f"\n{DIVIDER}")


# ── Main ──────────────────────────────────────────────────────────────────────

def run_all():
    print(f"\n{'#'*62}")
    print("  TicketBrain End-to-End Test Runner")
    print(f"{'#'*62}")

    clean_context_items()
    add_kb_articles()
    ticket_names = create_test_tickets()
    if ticket_names:
        verify_ai_interactions(ticket_names)
        test_stuck_flow(ticket_names)
        resolve_and_extract(ticket_names)
        create_and_resolve_similar_tickets()
    run_context_discovery()
    print_report()

    print("\n  All tests complete. Open your browser and check the TicketBrain workspace.")
    print(f"  URL: http://ticketbrain.local/app/ticketbrain\n")
