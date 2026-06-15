import frappe


INSTALL_LOGGER = frappe.logger("ticketbrain_setup")

def _log(message, level="info"):
    getattr(INSTALL_LOGGER, level, INSTALL_LOGGER.info)(message)


def after_install():
    setup_customizations()


def after_migrate():
    setup_customizations()
    migrate_business_context_lifecycle()


def setup_customizations():
    _log("Setting up TicketBrain customizations...")
    setup_custom_fields()

    from ticketbrain.setup.roles import create_custom_roles
    create_custom_roles()

    from ticketbrain.setup.role_permission import setup_all_custom_role_permissions
    setup_all_custom_role_permissions()

    setup_ai_resolved_status()
    setup_pending_approval_status()
    setup_ticketbrain_bot_user()
    cleanup_ai_ticket_types()
    setup_ticketbrain_form_script()
    setup_business_context()
    setup_workspace()

    frappe.db.commit()
    _log("TicketBrain customizations completed!")


def setup_custom_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    create_custom_fields(
        {
            "HD Ticket": [
                {
                    "fieldname": "tb_section",
                    "label": "TicketBrain AI",
                    "fieldtype": "Section Break",
                    "insert_after": "status",
                    "collapsible": 1,
                },
                {
                    "fieldname": "tb_category",
                    "label": "AI Category",
                    "fieldtype": "Data",
                    "insert_after": "tb_section",
                    "read_only": 1,
                    "in_list_view": 1,
                },
                {
                    "fieldname": "tb_col",
                    "fieldtype": "Column Break",
                    "insert_after": "tb_category",
                },
                {
                    "fieldname": "tb_confidence_score",
                    "label": "AI Confidence",
                    "fieldtype": "Percent",
                    "insert_after": "tb_col",
                    "read_only": 1,
                },
                {
                    "fieldname": "tb_col2",
                    "fieldtype": "Column Break",
                    "insert_after": "tb_confidence_score",
                },
                {
                    "fieldname": "tb_should_escalate",
                    "label": "AI Recommends Escalation",
                    "fieldtype": "Check",
                    "insert_after": "tb_col2",
                    "read_only": 1,
                },
            ]
        },
        update=True,
    )
    _log("Custom fields setup completed")
    frappe.db.commit()


TB_BOT_EMAIL = "ticketbrain-ai@ticketbrain.local"
TB_BOT_NAME  = "TicketBrain AI"

# AI categories — also used as Ticket Types
AI_CATEGORIES = [
    "Hardware & Infrastructure",
    "Software & Applications",
    "Network & Connectivity",
    "Account & Access",
    "Security & Threats",
    "Data & Reports",
]


def setup_ticketbrain_bot_user():
    if frappe.db.exists("User", TB_BOT_EMAIL):
        return
    try:
        user = frappe.get_doc({
            "doctype":           "User",
            "email":             TB_BOT_EMAIL,
            "first_name":        "TicketBrain",
            "last_name":         "AI",
            "user_type":         "System User",
            "enabled":           1,
            "send_welcome_email": 0,
        })
        user.insert(ignore_permissions=True)
        _log(f"Created bot user {TB_BOT_EMAIL}")
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Could not create bot user")


def cleanup_ai_ticket_types():
    """Remove any AI categories that were accidentally created as Ticket Types."""
    for cat in AI_CATEGORIES:
        if frappe.db.exists("HD Ticket Type", cat):
            try:
                frappe.delete_doc("HD Ticket Type", cat, ignore_permissions=True, force=True)
                _log(f"Removed incorrect ticket type: {cat}")
            except Exception:
                pass
    frappe.db.commit()


def setup_pending_approval_status():
    if frappe.db.exists("HD Ticket Status", "Pending Approval"):
        return

    try:
        frappe.get_doc({
            "doctype": "HD Ticket Status",
            "name": "Pending Approval",
            "label_agent": "Pending Approval",
            "label_customer": "Under Review",
            "color": "Orange",
            "category": "Open",
            "order": 4,
            "enabled": 1,
        }).insert(ignore_permissions=True)
        _log("Created 'Pending Approval' ticket status")
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Could not create Pending Approval status")


_TB_FORM_SCRIPT_NAME = "TicketBrain Approval Actions"

_TB_FORM_SCRIPT = r"""
async function setupForm({ doc, call, createToast }) {
    if (doc.status !== "Pending Approval") return { actions: [] };

    async function getInteraction() {
        const rows = await call("frappe.client.get_list", {
            doctype: "TB AI Interaction",
            filters: { ticket: doc.name, approval_status: "Pending Approval" },
            fields: ["name", "ai_draft_response", "auto_send_reason"],
            limit: 1,
        });
        return rows && rows.length ? rows[0] : null;
    }

    function openReviewModal(interaction) {
        const existing = document.getElementById("tb-review-modal");
        if (existing) existing.remove();

        const overlay = document.createElement("div");
        overlay.id = "tb-review-modal";
        overlay.style.cssText = [
            "position:fixed", "inset:0", "background:rgba(17,24,39,0.45)",
            "display:flex", "align-items:center", "justify-content:center",
            "z-index:10000", "padding:16px",
        ].join(";");

        const reasonBanner = interaction.auto_send_reason ? `
            <div style="display:flex;align-items:flex-start;gap:8px;background:#fffbeb;border:1px solid #fcd34d;border-radius:8px;padding:10px 14px;margin-bottom:16px;">
                <span style="color:#d97706;font-size:15px;flex-shrink:0;">⚠</span>
                <div>
                    <div style="font-size:12px;font-weight:600;color:#92400e;margin-bottom:2px;">Held for review</div>
                    <div style="font-size:12px;color:#b45309;">${interaction.auto_send_reason}</div>
                </div>
            </div>` : "";

        overlay.innerHTML = `
        <div style="background:#fff;border-radius:12px;width:600px;max-width:95vw;max-height:88vh;display:flex;flex-direction:column;box-shadow:0 24px 64px rgba(0,0,0,0.18);overflow:hidden;">

            <!-- Header -->
            <div style="display:flex;align-items:center;justify-content:space-between;padding:18px 22px 14px;border-bottom:1px solid #f1f5f9;">
                <div>
                    <div style="font-size:15px;font-weight:600;color:#0f172a;">Review AI Draft</div>
                    <div style="font-size:12px;color:#64748b;margin-top:1px;">Approve the AI response or write your own before sending to the customer.</div>
                </div>
                <button id="tb-close" style="width:28px;height:28px;border:none;background:#f1f5f9;border-radius:6px;cursor:pointer;font-size:16px;color:#64748b;display:flex;align-items:center;justify-content:center;">✕</button>
            </div>

            <!-- Scrollable body -->
            <div style="flex:1;overflow-y:auto;padding:18px 22px;">
                ${reasonBanner}

                <!-- Tabs -->
                <div id="tb-tabs" style="display:flex;gap:0;border-bottom:1px solid #e2e8f0;margin-bottom:16px;">
                    <button id="tb-tab-ai" data-tab="ai" style="padding:8px 16px;border:none;background:none;cursor:pointer;font-size:13px;font-weight:600;color:#6366f1;border-bottom:2px solid #6366f1;margin-bottom:-1px;">AI Draft</button>
                    <button id="tb-tab-custom" data-tab="custom" style="padding:8px 16px;border:none;background:none;cursor:pointer;font-size:13px;font-weight:500;color:#64748b;border-bottom:2px solid transparent;margin-bottom:-1px;">Write Custom Reply</button>
                </div>

                <!-- AI Draft panel -->
                <div id="tb-panel-ai">
                    <div style="font-size:11px;font-weight:600;color:#94a3b8;letter-spacing:0.06em;text-transform:uppercase;margin-bottom:8px;">What the customer will receive</div>
                    <div style="border:1px solid #e2e8f0;border-radius:8px;padding:16px;max-height:260px;overflow-y:auto;background:#f8fafc;font-size:13px;line-height:1.7;color:#1e293b;">
                        ${interaction.ai_draft_response || "<em style='color:#94a3b8'>No draft content</em>"}
                    </div>
                </div>

                <!-- Custom reply panel (hidden by default) -->
                <div id="tb-panel-custom" style="display:none;">
                    <div style="font-size:11px;font-weight:600;color:#94a3b8;letter-spacing:0.06em;text-transform:uppercase;margin-bottom:8px;">Your message to the customer</div>
                    <textarea id="tb-custom-msg" placeholder="Type your reply here..." style="width:100%;min-height:160px;border:1px solid #d1d5db;border-radius:8px;padding:12px;font-size:13px;line-height:1.6;color:#1e293b;resize:vertical;box-sizing:border-box;font-family:inherit;outline:none;transition:border-color 0.15s;" onfocus="this.style.borderColor='#6366f1'" onblur="this.style.borderColor='#d1d5db'"></textarea>
                    <div style="font-size:11px;color:#94a3b8;margin-top:6px;">The AI draft will be discarded and your message will be sent instead.</div>
                </div>
            </div>

            <!-- Footer -->
            <div style="display:flex;align-items:center;justify-content:flex-end;gap:10px;padding:14px 22px;border-top:1px solid #f1f5f9;background:#fafafa;">
                <button id="tb-cancel" style="padding:8px 18px;border:1px solid #e2e8f0;border-radius:8px;background:#fff;font-size:13px;font-weight:500;cursor:pointer;color:#374151;">Cancel</button>
                <button id="tb-send" style="padding:8px 22px;border:none;border-radius:8px;background:#16a34a;color:#fff;font-size:13px;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:6px;">
                    <span>✓</span><span id="tb-send-label">Approve &amp; Send</span>
                </button>
            </div>
        </div>`;

        document.body.appendChild(overlay);

        let activeTab = "ai";

        function switchTab(tab) {
            activeTab = tab;
            const isAI = tab === "ai";

            overlay.querySelector("#tb-panel-ai").style.display    = isAI ? "block" : "none";
            overlay.querySelector("#tb-panel-custom").style.display = isAI ? "none"  : "block";

            overlay.querySelector("#tb-tab-ai").style.color        = isAI ? "#6366f1" : "#64748b";
            overlay.querySelector("#tb-tab-ai").style.fontWeight   = isAI ? "600" : "500";
            overlay.querySelector("#tb-tab-ai").style.borderBottomColor = isAI ? "#6366f1" : "transparent";

            overlay.querySelector("#tb-tab-custom").style.color        = !isAI ? "#6366f1" : "#64748b";
            overlay.querySelector("#tb-tab-custom").style.fontWeight   = !isAI ? "600" : "500";
            overlay.querySelector("#tb-tab-custom").style.borderBottomColor = !isAI ? "#6366f1" : "transparent";

            const btn   = overlay.querySelector("#tb-send");
            const label = overlay.querySelector("#tb-send-label");
            btn.style.background = isAI ? "#16a34a" : "#2563eb";
            label.textContent    = isAI ? "Approve & Send" : "Send Custom Reply";
        }

        overlay.querySelector("#tb-tab-ai").onclick     = () => switchTab("ai");
        overlay.querySelector("#tb-tab-custom").onclick = () => switchTab("custom");

        const close = () => overlay.remove();
        overlay.querySelector("#tb-close").onclick  = close;
        overlay.querySelector("#tb-cancel").onclick = close;
        overlay.onclick = (e) => { if (e.target === overlay) close(); };

        overlay.querySelector("#tb-send").onclick = async () => {
            const btn   = overlay.querySelector("#tb-send");
            const label = overlay.querySelector("#tb-send-label");
            btn.disabled = true;
            label.textContent = "Sending…";

            try {
                if (activeTab === "ai") {
                    await call("ticketbrain.api.ticket.approve_ai_response", {
                        ticket_id: doc.name,
                        interaction_id: interaction.name,
                    });
                    createToast({ title: "AI draft sent to customer. Ticket is now Open.", type: "success" });
                } else {
                    const msg = (overlay.querySelector("#tb-custom-msg").value || "").trim();
                    if (!msg) {
                        createToast({ title: "Please enter a message before sending.", type: "error" });
                        btn.disabled = false;
                        label.textContent = "Send Custom Reply";
                        return;
                    }
                    await call("ticketbrain.api.ticket.submit_agent_response", {
                        ticket_id: doc.name,
                        interaction_id: interaction.name,
                        custom_message: msg,
                    });
                    createToast({ title: "Custom reply sent to customer. Ticket is now Open.", type: "success" });
                }
                close();
                // Reload so the button disappears and the ticket reflects its new Open status
                setTimeout(() => window.location.reload(), 800);
            } catch (e) {
                createToast({ title: "Failed to send. Please try again.", type: "error" });
                btn.disabled = false;
                label.textContent = activeTab === "ai" ? "Approve & Send" : "Send Custom Reply";
            }
        };
    }

    return {
        actions: [
            {
                label: "Review AI Draft",
                onClick: async () => {
                    const interaction = await getInteraction();
                    if (!interaction) {
                        createToast({ title: "No pending AI draft found.", type: "error" });
                        return;
                    }
                    openReviewModal(interaction);
                },
            },
        ],
    };
}
""".strip()


def setup_ticketbrain_form_script():
    """Create (or update) the HD Form Script that adds Approve buttons to the Helpdesk portal."""
    existing = frappe.db.get_value("HD Form Script", _TB_FORM_SCRIPT_NAME, "name")
    if existing:
        frappe.db.set_value("HD Form Script", _TB_FORM_SCRIPT_NAME, {
            "script":  _TB_FORM_SCRIPT,
            "enabled": 1,
        })
        _log("Updated TicketBrain HD Form Script")
    else:
        try:
            frappe.get_doc({
                "doctype":                    "HD Form Script",
                "name":                       _TB_FORM_SCRIPT_NAME,
                "dt":                         "HD Ticket",
                "apply_to":                   "Form",
                "enabled":                    1,
                "apply_on_new_page":          0,
                "apply_to_customer_portal":   0,
                "script":                     _TB_FORM_SCRIPT,
            }).insert(ignore_permissions=True)
            _log("Created TicketBrain HD Form Script")
        except Exception:
            frappe.log_error(frappe.get_traceback(), "TicketBrain: Could not create HD Form Script")
    frappe.db.commit()


def setup_ai_resolved_status():
    if frappe.db.exists("HD Ticket Status", "AI Resolved"):
        return

    try:
        frappe.get_doc({
            "doctype": "HD Ticket Status",
            "name": "AI Resolved",
            "label_agent": "AI Resolved",
            "label_customer": "Resolved by AI",
            "color": "Green",
            "category": "Resolved",
            "order": 10,
            "enabled": 1,
        }).insert(ignore_permissions=True)
        _log("Created 'AI Resolved' ticket status")
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Could not create AI Resolved status")


def setup_workspace():
    """Create (or refresh) the TicketBrain workspace in Frappe Desk."""
    import json as _json

    ws_name = "TicketBrain"

    shortcuts, links, content = _build_workspace_data()

    if frappe.db.exists("Workspace", ws_name):
        try:
            ws = frappe.get_doc("Workspace", ws_name)
            ws.shortcuts = []
            ws.links     = []
            for s in shortcuts:
                ws.append("shortcuts", s)
            for l in links:
                ws.append("links", l)
            ws.content = _json.dumps(content)
            ws.save(ignore_permissions=True)
            _log("Updated TicketBrain workspace")
        except Exception:
            frappe.log_error(frappe.get_traceback(), "TicketBrain: Could not update workspace")
        return

    try:
        ws = frappe.get_doc({
            "doctype":         "Workspace",
            "label":           ws_name,
            "title":           ws_name,
            "public":          1,
            "module":          "Ticketbrain",
            "icon":            "ticketbrain",
            "indicator_color": "blue",
            "shortcuts":       shortcuts,
            "links":           links,
            "content":         _json.dumps(content),
        })
        ws.insert(ignore_permissions=True)
        _log("Created TicketBrain workspace")
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Could not create workspace")


def _build_workspace_data():
    """Return (shortcuts, links, content) for the TicketBrain workspace."""
    shortcuts = [
        {"type": "DocType", "link_to": "TB AI Interaction",   "label": "AI Interactions",  "color": "#6366f1"},
        {"type": "DocType", "link_to": "TB Business Context", "label": "Business Context",  "color": "#10b981"},
        {"type": "DocType", "link_to": "HD Ticket",           "label": "Support Tickets",   "color": "#f59e0b"},
        {"type": "DocType", "link_to": "HD Article",          "label": "Knowledge Base",    "color": "#3b82f6"},
    ]

    sections = [
        {
            "card_name": "AI Operations",
            "items": [
                {"link_type": "DocType", "link_to": "TB AI Interaction",   "label": "AI Interactions",  "onboard": 1},
            ],
        },
        {
            "card_name": "Context & Knowledge",
            "items": [
                {"link_type": "DocType", "link_to": "TB Business Context", "label": "Business Context", "onboard": 1},
                {"link_type": "DocType", "link_to": "HD Article",          "label": "KB Articles"},
            ],
        },
        {
            "card_name": "Helpdesk",
            "items": [
                {"link_type": "DocType", "link_to": "HD Ticket",           "label": "Tickets",       "onboard": 1},
                {"link_type": "DocType", "link_to": "HD Team",             "label": "Teams"},
                {"link_type": "DocType", "link_to": "HD Ticket Type",      "label": "Ticket Types"},
            ],
        },
        {
            "card_name": "Monitoring",
            "items": [
                {"link_type": "DocType", "link_to": "Error Log",           "label": "Error Log"},
                {"link_type": "DocType", "link_to": "Scheduled Job Log",   "label": "Scheduled Jobs"},
            ],
        },
    ]

    links = []
    for section in sections:
        links.append({"type": "Card Break", "label": section["card_name"], "hidden": 0})
        for item in section["items"]:
            links.append({
                "type":      "Link",
                "link_type": item["link_type"],
                "link_to":   item["link_to"],
                "label":     item["label"],
                "onboard":   item.get("onboard", 0),
                "hidden":    0,
            })

    # Content JSON — the layout Frappe 15 uses to render the workspace page
    content = [
        {"id": "tb_h1", "type": "header", "data": {
            "text": '<span style="font-size:18px;letter-spacing:0.18px;"><b>TicketBrain AI</b></span>',
            "col": 12,
        }},
        {"id": "tb_s1", "type": "shortcut", "data": {"shortcut_name": "AI Interactions",  "col": 3}},
        {"id": "tb_s2", "type": "shortcut", "data": {"shortcut_name": "Business Context",  "col": 3}},
        {"id": "tb_s3", "type": "shortcut", "data": {"shortcut_name": "Support Tickets",   "col": 3}},
        {"id": "tb_s4", "type": "shortcut", "data": {"shortcut_name": "Knowledge Base",    "col": 3}},
        {"id": "tb_sp", "type": "spacer",   "data": {"col": 12}},
        {"id": "tb_h2", "type": "header",   "data": {
            "text": '<span style="font-size:18px;letter-spacing:0.18px;"><b>Modules</b></span>',
            "col": 12,
        }},
        {"id": "tb_c1", "type": "card", "data": {"card_name": "AI Operations",       "col": 4}},
        {"id": "tb_c2", "type": "card", "data": {"card_name": "Context & Knowledge", "col": 4}},
        {"id": "tb_c3", "type": "card", "data": {"card_name": "Helpdesk",            "col": 4}},
        {"id": "tb_c4", "type": "card", "data": {"card_name": "Monitoring",          "col": 4}},
    ]

    return shortcuts, links, content


def setup_business_context():
    """Create the initial TB Business Context record for this company."""
    company = (
        frappe.db.get_single_value("Global Defaults", "default_company")
        or frappe.db.get_value("Company", {}, "name")
    )
    if not company:
        return
    if frappe.db.exists("TB Business Context", company):
        return
    try:
        frappe.get_doc({
            "doctype":          "TB Business Context",
            "company":          company,
            "scan_status":      "Idle",
            "lifecycle_status": "Not Generated",
            "schedule_days":    7,
        }).insert(ignore_permissions=True)
        _log(f"Created TB Business Context for {company}")
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Could not create TB Business Context")


def migrate_business_context_lifecycle():
    """
    Migration: correct lifecycle_status on all TB Business Context records
    that may have received the wrong default ("Not Generated") when the column was added.
    """
    try:
        # Fix records that are actually Approved but got default "Not Generated"
        frappe.db.sql(
            "UPDATE `tabTB Business Context` SET lifecycle_status='Active' "
            "WHERE approval_status='Approved' AND lifecycle_status != 'Active'"
        )
        # Fix records that completed a scan but aren't approved yet
        frappe.db.sql(
            "UPDATE `tabTB Business Context` SET lifecycle_status='Review Required' "
            "WHERE scan_status IN ('Completed','Failed') AND approval_status='Pending Review' "
            "AND lifecycle_status = 'Not Generated'"
        )
        frappe.db.commit()
        _log("Lifecycle status migration completed")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Lifecycle migration failed")
