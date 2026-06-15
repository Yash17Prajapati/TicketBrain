frappe.ui.form.on("HD Ticket", {
    refresh(frm) {
        if (frm.doc.__islocal) return;

        _maybeShowEvaluatingOverlay(frm);
        _maybeShowAssignmentPanel(frm);

        if (frm.doc.status !== "Pending Approval") return;

        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "TB AI Interaction",
                filters: { ticket: frm.doc.name, approval_status: "Pending Approval" },
                fields: ["name", "ai_draft_response", "auto_send_reason"],
                limit: 1,
            },
            callback(r) {
                if (!r.message || !r.message.length) return;
                const interaction = r.message[0];

                if (interaction.auto_send_reason) {
                    frm.dashboard.add_comment(
                        `<b>TicketBrain AI:</b> ${interaction.auto_send_reason}`,
                        "yellow",
                        true
                    );
                }

                frm.add_custom_button(__("Approve & Send AI Draft"), () => {
                    frappe.confirm(
                        __("Send the AI draft response to the customer as-is?"),
                        () => {
                            frappe.call({
                                method: "ticketbrain.api.ticket.approve_ai_response",
                                args: { ticket_id: frm.doc.name, interaction_id: interaction.name },
                                callback() {
                                    frappe.show_alert({ message: __("AI response sent to customer."), indicator: "green" });
                                    frm.reload_doc();
                                },
                            });
                        }
                    );
                }, __("TicketBrain"));

                frm.add_custom_button(__("Write Custom Reply"), () => {
                    const d = new frappe.ui.Dialog({
                        title: __("Write Custom Reply"),
                        fields: [
                            {
                                fieldtype: "HTML",
                                fieldname: "draft_preview_label",
                                options: `<p style="color:#6b7280;font-size:12px;margin-bottom:4px;">
                                    AI draft (for reference — edit or replace below):
                                </p>`,
                            },
                            {
                                fieldtype: "Long Text",
                                fieldname: "custom_message",
                                label: __("Your Reply to Customer"),
                                reqd: 1,
                            },
                        ],
                        primary_action_label: __("Send to Customer"),
                        primary_action(values) {
                            frappe.call({
                                method: "ticketbrain.api.ticket.submit_agent_response",
                                args: {
                                    ticket_id: frm.doc.name,
                                    interaction_id: interaction.name,
                                    custom_message: values.custom_message,
                                },
                                callback() {
                                    frappe.show_alert({ message: __("Reply sent to customer."), indicator: "green" });
                                    d.hide();
                                    frm.reload_doc();
                                },
                            });
                        },
                    });

                    if (interaction.ai_draft_response) {
                        const tmp = document.createElement("div");
                        tmp.innerHTML = interaction.ai_draft_response;
                        d.set_value("custom_message", tmp.textContent || tmp.innerText || "");
                    }
                    d.show();
                }, __("TicketBrain"));

                frm.add_custom_button(__("View AI Analysis"), () => {
                    frappe.set_route("Form", "TB AI Interaction", interaction.name);
                }, __("TicketBrain"));
            },
        });
    },
});

// ── Evaluating Overlay ────────────────────────────────────────────────────────

function _maybeShowEvaluatingOverlay(frm) {
    // Only show for recently created tickets (within 3 minutes)
    const created = frm.doc.creation;
    if (!created) return;

    const ageSeconds = (new Date() - new Date(created)) / 1000;
    if (ageSeconds > 180) return;

    // Check if AI already finished (TB AI Interaction exists)
    frappe.call({
        method: "ticketbrain.api.ticket.get_ai_processing_status",
        args: { ticket_name: frm.doc.name },
        callback(r) {
            if (r.message?.done) return; // Already processed — no overlay needed
            _showOverlay(frm);
        },
    });
}

function _showOverlay(frm) {
    if (document.getElementById("tb-evaluating-overlay")) return; // Already showing

    const overlay = document.createElement("div");
    overlay.id = "tb-evaluating-overlay";
    overlay.innerHTML = `
        <div style="
            position:fixed;top:0;left:0;right:0;bottom:0;
            background:rgba(255,255,255,0.82);
            backdrop-filter:blur(3px);
            -webkit-backdrop-filter:blur(3px);
            z-index:1050;
            display:flex;align-items:center;justify-content:center;
            animation:tb-fadein 0.25s ease;
        ">
            <div style="
                text-align:center;
                background:#fff;
                border:1px solid #e5e7eb;
                border-radius:12px;
                padding:36px 48px;
                box-shadow:0 8px 32px rgba(0,0,0,0.10);
                max-width:420px;
                width:90%;
            ">
                <div style="margin-bottom:20px;">
                    <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"
                         style="animation:tb-spin 1.2s linear infinite;display:inline-block;">
                        <circle cx="24" cy="24" r="20" stroke="#e5e7eb" stroke-width="4"/>
                        <path d="M44 24 A20 20 0 0 0 24 4" stroke="#6366f1" stroke-width="4" stroke-linecap="round"/>
                    </svg>
                </div>
                <div style="font-size:17px;font-weight:600;color:#111827;margin-bottom:8px;">
                    Evaluating your ticket…
                </div>
                <div style="font-size:13px;color:#6b7280;line-height:1.6;">
                    TicketBrain AI is analysing your issue, finding the best resolution,
                    and routing it to the right team.<br>
                    <span style="color:#9ca3af;font-size:12px;margin-top:6px;display:block;">
                        This usually takes a few seconds.
                    </span>
                </div>
                <div style="margin-top:20px;">
                    <div style="
                        display:flex;gap:6px;justify-content:center;align-items:center;
                    ">
                        <span style="width:8px;height:8px;border-radius:50%;background:#6366f1;animation:tb-pulse 1.4s ease-in-out 0s infinite;display:inline-block;"></span>
                        <span style="width:8px;height:8px;border-radius:50%;background:#6366f1;animation:tb-pulse 1.4s ease-in-out 0.2s infinite;display:inline-block;"></span>
                        <span style="width:8px;height:8px;border-radius:50%;background:#6366f1;animation:tb-pulse 1.4s ease-in-out 0.4s infinite;display:inline-block;"></span>
                    </div>
                </div>
            </div>
        </div>
        <style>
            @keyframes tb-spin { to { transform: rotate(360deg); } }
            @keyframes tb-fadein { from { opacity:0; } to { opacity:1; } }
            @keyframes tb-pulse {
                0%,80%,100% { opacity:0.3; transform:scale(0.85); }
                40%          { opacity:1;   transform:scale(1.15); }
            }
        </style>
    `;
    document.body.appendChild(overlay);

    // Start polling
    let polls = 0;
    const maxPolls = 40; // 40 × 3s = 2 min max
    const timer = setInterval(() => {
        polls++;
        frappe.call({
            method: "ticketbrain.api.ticket.get_ai_processing_status",
            args: { ticket_name: frm.doc.name },
            callback(r) {
                if (r.message?.done || polls >= maxPolls) {
                    clearInterval(timer);
                    _hideOverlay();
                    frm.reload_doc();

                    if (r.message?.timed_out) {
                        frappe.show_alert({
                            message: __("AI evaluation is taking longer than usual. The ticket has been queued for review."),
                            indicator: "orange",
                        });
                    } else if (r.message?.done) {
                        const cat = r.message?.interaction?.category;
                        frappe.show_alert({
                            message: cat
                                ? __("Ticket evaluated — categorised as <strong>%s</strong>.", [cat])
                                : __("Ticket evaluated by TicketBrain AI."),
                            indicator: "green",
                        });
                    }
                }
            },
        });
    }, 3000);
}

function _hideOverlay() {
    const el = document.getElementById("tb-evaluating-overlay");
    if (el) {
        el.style.animation = "tb-fadein 0.2s ease reverse";
        setTimeout(() => el.remove(), 200);
    }
}


// ── AI Assignment Panel ────────────────────────────────────────────────────────

function _maybeShowAssignmentPanel(frm) {
    frappe.call({
        method: "ticketbrain.api.correction.get_assignment_status",
        args: { ticket_id: frm.doc.name },
        callback(r) {
            const data = r.message;
            if (!data || !data.has_ai || data.already_acted) return;

            _renderAssignmentPanel(frm, data);
        },
    });
}

function _renderAssignmentPanel(frm, data) {
    const confColor = data.confidence >= 80 ? "#16a34a" : data.confidence >= 65 ? "#ca8a04" : "#dc2626";
    const html = `
        <div id="tb-assignment-panel" style="
            border:1px solid #e5e7eb;border-radius:8px;padding:16px 20px;
            margin-bottom:12px;background:#f9fafb;
        ">
            <div style="font-size:13px;font-weight:600;color:#374151;margin-bottom:10px;">
                TicketBrain AI Recommendation
            </div>
            <div style="display:flex;gap:24px;flex-wrap:wrap;margin-bottom:12px;">
                <div>
                    <span style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;">Category</span><br>
                    <span style="font-size:13px;font-weight:500;color:#111827;">${data.ai_category || "—"}</span>
                </div>
                <div>
                    <span style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;">Team</span><br>
                    <span style="font-size:13px;font-weight:500;color:#111827;">${data.ai_team || "—"}</span>
                </div>
                <div>
                    <span style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;">Priority</span><br>
                    <span style="font-size:13px;font-weight:500;color:#111827;">${data.ai_priority || "—"}</span>
                </div>
                <div>
                    <span style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;">Confidence</span><br>
                    <span style="font-size:13px;font-weight:600;color:${confColor};">${data.confidence}%</span>
                </div>
            </div>
            <div style="display:flex;gap:8px;">
                <button id="tb-accept-btn" class="btn btn-xs btn-success">✓ Accept Assignment</button>
                <button id="tb-correct-btn" class="btn btn-xs btn-default">✎ Correct Assignment</button>
            </div>
        </div>
    `;

    // Inject above the form body
    const wrapper = frm.layout && frm.layout.wrapper
        ? frm.layout.wrapper[0]
        : document.querySelector(".form-page");
    if (!wrapper) return;

    const existing = document.getElementById("tb-assignment-panel");
    if (existing) existing.remove();

    wrapper.insertAdjacentHTML("afterbegin", html);

    document.getElementById("tb-accept-btn").addEventListener("click", () => {
        frappe.confirm(
            __("Accept AI assignment? This records your approval and removes this panel."),
            () => {
                frappe.call({
                    method: "ticketbrain.api.correction.accept_assignment",
                    args: { ticket_id: frm.doc.name },
                    callback() {
                        document.getElementById("tb-assignment-panel")?.remove();
                        frappe.show_alert({ message: __("Assignment accepted."), indicator: "green" });
                    },
                });
            }
        );
    });

    document.getElementById("tb-correct-btn").addEventListener("click", () => {
        _showCorrectionDialog(frm, data);
    });
}

function _showCorrectionDialog(frm, data) {
    const d = new frappe.ui.Dialog({
        title: __("Correct AI Assignment"),
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "ai_summary",
                options: `<div style="background:#fef3c7;border:1px solid #fde68a;border-radius:6px;
                    padding:10px 14px;margin-bottom:4px;font-size:12px;color:#92400e;">
                    <strong>AI predicted:</strong> Category = ${data.ai_category || "—"} &nbsp;|&nbsp;
                    Team = ${data.ai_team || "—"} &nbsp;|&nbsp; Priority = ${data.ai_priority || "—"}
                    (${data.confidence}% confidence)
                </div>`,
            },
            {
                fieldtype: "Data",
                fieldname: "human_category",
                label: __("Correct Category"),
                default: data.ai_category || "",
            },
            {
                fieldtype: "Link",
                fieldname: "human_team",
                label: __("Correct Team"),
                options: "HD Team",
                default: data.ai_team || "",
            },
            {
                fieldtype: "Select",
                fieldname: "human_priority",
                label: __("Correct Priority"),
                options: ["Low", "Medium", "High", "Critical"],
                default: data.ai_priority || "Medium",
            },
            {
                fieldtype: "Data",
                fieldname: "correction_reason",
                label: __("Correction Reason"),
                reqd: 1,
                description: __("e.g. Wrong Team, ERP Issue Not Network Issue, Wrong Category"),
            },
        ],
        primary_action_label: __("Submit Correction"),
        primary_action(values) {
            if (!values.correction_reason) {
                frappe.msgprint(__("Correction reason is required."));
                return;
            }
            frappe.call({
                method: "ticketbrain.api.correction.submit_correction",
                args: {
                    ticket_id:        frm.doc.name,
                    human_category:   values.human_category || "",
                    human_team:       values.human_team || "",
                    human_priority:   values.human_priority || "",
                    correction_reason: values.correction_reason,
                },
                callback(r) {
                    if (r.message?.ok) {
                        d.hide();
                        document.getElementById("tb-assignment-panel")?.remove();
                        frappe.show_alert({
                            message: __("Correction saved and indexed for future AI learning."),
                            indicator: "blue",
                        });
                        frm.reload_doc();
                    }
                },
            });
        },
    });
    d.show();
}
