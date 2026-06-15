frappe.ui.form.on("TB AI Interaction", {
    refresh(frm) {
        _render_draft_preview(frm);

        if (frm.doc.approval_status !== "Pending Approval") return;

        // "Approve & Send"
        frm.add_custom_button(__("Approve & Send"), () => {
            frappe.confirm(
                __("Send the AI draft response to the customer as-is?"),
                () => {
                    frappe.call({
                        method: "ticketbrain.api.ticket.approve_ai_response",
                        args: {
                            ticket_id: frm.doc.ticket,
                            interaction_id: frm.doc.name,
                        },
                        callback() {
                            frappe.show_alert({ message: __("AI response sent to customer."), indicator: "green" });
                            frm.reload_doc();
                        },
                    });
                }
            );
        }, __("Actions")).addClass("btn-primary");

        // "Write Custom Reply"
        frm.add_custom_button(__("Write Custom Reply"), () => {
            const d = new frappe.ui.Dialog({
                title: __("Write Custom Reply"),
                fields: [
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
                            ticket_id: frm.doc.ticket,
                            interaction_id: frm.doc.name,
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

            // Pre-fill with stripped AI draft
            if (frm.doc.ai_draft_response) {
                const tmp = document.createElement("div");
                tmp.innerHTML = frm.doc.ai_draft_response;
                d.set_value("custom_message", tmp.textContent || tmp.innerText || "");
            }
            d.show();
        }, __("Actions"));

        // "Open Ticket"
        frm.add_custom_button(__("Open Ticket"), () => {
            frappe.set_route("Form", "HD Ticket", frm.doc.ticket);
        }, __("Navigate"));
    },
});


function _render_draft_preview(frm) {
    if (!frm.doc.ai_draft_response) return;

    // Render the HTML draft in the ai_draft_response field area as a styled preview
    frm.get_field("ai_draft_response").$wrapper.find(".control-value").html(
        `<div style="
            background:#f8fafc;
            border:1px solid #e2e8f0;
            border-radius:6px;
            padding:14px 18px;
            font-family:sans-serif;
            line-height:1.6;
            max-height:360px;
            overflow-y:auto;
        ">${frm.doc.ai_draft_response}</div>`
    );
}
