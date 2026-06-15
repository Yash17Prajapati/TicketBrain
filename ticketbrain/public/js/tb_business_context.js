/**
 * TicketBrain — Business Context Lifecycle Controller
 *
 * States:
 *   Not Generated → [Run Context Discovery]
 *   Scanning      → [Abort Scan] · read-only form
 *   Review Required → [Approve Context] [Reject & Re-Scan] [Compare Changes]
 *   Active        → [Refresh Context] [View History] + update-available banner
 */

frappe.ui.form.on("TB Business Context", {
    refresh(frm) {
        _setupForm(frm);
    },
});

// ── Main setup ────────────────────────────────────────────────────────────────

function _setupForm(frm) {
    const status = _getStatus(frm);

    _lockForm(frm, status === "Scanning" || status === "Active");
    _renderBanners(frm, status);
    _renderButtons(frm, status);
    _styleConfidenceScores(frm);

    if (status === "Scanning") {
        _pollScan(frm);
    }
}

function _getStatus(frm) {
    // Use lifecycle_status if set; fall back to legacy scan_status / approval_status
    if (frm.doc.lifecycle_status && frm.doc.lifecycle_status !== "Not Generated") {
        return frm.doc.lifecycle_status;
    }
    if (frm.doc.scan_status === "Running") return "Scanning";
    if (frm.doc.approval_status === "Approved") return "Active";
    if (frm.doc.items && frm.doc.items.length > 0) return "Review Required";
    return frm.doc.lifecycle_status || "Not Generated";
}

function _lockForm(frm, locked) {
    const editableFields = ["industry", "company_type", "business_description",
                            "schedule_enabled", "schedule_days"];
    editableFields.forEach(f => {
        if (frm.fields_dict[f]) frm.set_df_property(f, "read_only", locked ? 1 : 0);
    });
    frm.set_df_property("items", "read_only", locked ? 1 : 0);
}

// ── Banners ───────────────────────────────────────────────────────────────────

function _renderBanners(frm, status) {
    frm.dashboard.clear_comment();

    const vLabel = frm.doc.current_version ? ` (v${frm.doc.current_version})` : "";
    const pending = frm.doc.items_pending || 0;
    const isRefresh = status === "Review Required" && !!frm.doc.current_version;

    switch (status) {
        case "Not Generated":
            frm.dashboard.add_comment(
                __("No business context has been discovered yet. Click <strong>Run Context Discovery</strong> to let AI analyse your organisation."),
                "blue", true
            );
            break;

        case "Scanning":
            frm.dashboard.add_comment(
                __("Scanning in progress — AI is analysing ERPNext, Helpdesk, Knowledge Base, and ticket history. This page will refresh automatically when done."),
                "blue", true
            );
            break;

        case "Review Required":
            if (isRefresh) {
                frm.dashboard.add_comment(
                    __("Refresh complete — <strong>%d items</strong> are awaiting your review. Your previous context%s remains active until you approve this version.", [pending, vLabel]),
                    "yellow", true
                );
            } else {
                frm.dashboard.add_comment(
                    __("Discovery complete — <strong>%d items</strong> discovered. Review them below and click <strong>Approve Context</strong> to activate.", [pending]),
                    "yellow", true
                );
            }
            break;

        case "Active":
            frm.dashboard.add_comment(
                __("Business Context Active%s — TicketBrain is using this context for all AI responses.", [vLabel]),
                "green", true
            );
            if (frm.doc.update_available) {
                frm.dashboard.add_comment(
                    __("⚠ Context Update Detected: <em>%s</em> — Click <strong>Refresh Context</strong> to run a new discovery scan.", [frm.doc.update_notes || "Organisation data has changed."]),
                    "yellow", true
                );
            }
            break;

        default:
            if (frm.doc.scan_status === "Failed") {
                frm.dashboard.add_comment(__("Last scan failed. Check the Error Log for details."), "red", true);
            }
    }
}

// ── Buttons by state ──────────────────────────────────────────────────────────

function _renderButtons(frm, status) {
    switch (status) {
        case "Not Generated":
            _addDiscoverButton(frm);
            break;

        case "Scanning":
            _addAbortButton(frm);
            break;

        case "Review Required":
            _addApproveContextButton(frm);
            _addRejectRescanButton(frm);
            _addApproveAllButton(frm);
            if (frm.doc.current_version) {
                _addCompareChangesButton(frm);
            }
            break;

        case "Active":
            _addRefreshContextButton(frm);
            _addViewHistoryButton(frm);
            _addApproveAllButton(frm);
            _addGenerateKBButton(frm);
            break;

        default:
            // Legacy fallback for old records
            _addLegacyButtons(frm);
    }
}

// ── Individual button implementations ─────────────────────────────────────────

function _addDiscoverButton(frm) {
    frm.add_custom_button(__("Run Context Discovery"), () => {
        frappe.confirm(
            `<div style="font-size:13px;line-height:1.8;">
                <p><strong>Context Discovery will:</strong></p>
                <ul style="margin:6px 0 12px 18px;color:#374151;">
                    <li>Analyse your ERPNext company data — departments, projects, assets</li>
                    <li>Discover support teams with ticket evidence from Frappe Helpdesk</li>
                    <li>Identify services, applications, and ticket categories from history</li>
                    <li>Build a structured intelligence map of your organisation</li>
                </ul>
                <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;padding:10px 14px;font-size:12px;color:#1e40af;">
                    <strong>What happens next:</strong> Results appear here for your review.
                    Nothing is applied until you click <em>Approve Context</em>.
                </div>
            </div>`,
            () => {
                frappe.call({
                    method: "ticketbrain.api.context.run_scan",
                    args: { doc_name: frm.doc.name },
                    callback() {
                        frappe.show_alert({ message: __("Discovery started."), indicator: "blue" });
                        frm.reload_doc();
                        setTimeout(() => _pollScan(frm), 2000);
                    },
                });
            }
        );
    }, null, "primary");
}

function _addAbortButton(frm) {
    frm.add_custom_button(__("Abort Scan"), () => {
        frappe.confirm(
            `<div style="font-size:13px;line-height:1.8;">
                <p><strong>Abort the current scan?</strong></p>
                <ul style="margin:6px 0 12px 18px;color:#6b7280;">
                    <li>The scan will be stopped immediately</li>
                    <li>Previously approved items (if any) will be preserved</li>
                    <li>You can run a fresh scan any time</li>
                </ul>
            </div>`,
            () => {
                frappe.call({
                    method: "ticketbrain.api.context.abort_scan",
                    args: { doc_name: frm.doc.name },
                    callback(r) {
                        const msg = r.message?.reverted_to === "Active"
                            ? __("Scan aborted. Previous context is still active.")
                            : __("Scan aborted.");
                        frappe.show_alert({ message: msg, indicator: "orange" });
                        frm.reload_doc();
                    },
                });
            }
        );
    }, null, "danger");
}

function _addApproveContextButton(frm) {
    const pendingCount  = frm.doc.items_pending || 0;
    const approvedCount = (frm.doc.items || []).filter(i => i.review_status === "Approved").length;
    const isRefresh     = !!frm.doc.current_version;

    frm.add_custom_button(__("Approve Context"), () => {
        const isDirty = frm.is_dirty();
        const editWarning = isDirty
            ? `<div style="background:#fef9c3;border:1px solid #fde047;border-radius:6px;padding:8px 12px;margin-bottom:12px;font-size:12px;">
                   ⚠ <strong>You have unsaved edits.</strong> They will be saved as part of the approval.
               </div>`
            : "";
        const refreshNote = isRefresh
            ? `<p style="color:#6b7280;font-size:12px;margin-top:8px;">This will replace <strong>v${frm.doc.current_version}</strong> and become the new active context.</p>`
            : "";

        frappe.confirm(
            `<div style="font-size:13px;line-height:1.8;">
                ${editWarning}
                <p><strong>Approve and activate this business context?</strong></p>
                <ul style="margin:6px 0 10px 18px;color:#374151;">
                    ${pendingCount > 0 ? `<li><strong>${pendingCount} pending item(s)</strong> will be automatically approved</li>` : ""}
                    <li><strong>${approvedCount + pendingCount} item(s)</strong> will be pushed to the AI knowledge base</li>
                    <li>All future AI ticket responses will use this context</li>
                </ul>
                ${refreshNote}
                <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:6px;padding:10px 14px;font-size:12px;color:#166534;margin-top:10px;">
                    <strong>Where this context is used:</strong><br>
                    <span style="display:block;margin-top:4px;">
                        Ticket Classifier · Resolution Generator · Followup Engine · KB Draft Generator
                    </span>
                </div>
            </div>`,
            () => {
                const doApprove = () => {
                    frappe.call({
                        method: "ticketbrain.api.context.approve_context",
                        args: { doc_name: frm.doc.name },
                        callback(r) {
                            frappe.show_alert({
                                message: __("Context approved — TicketBrain is now using v%s.", [r.message?.version || 1]),
                                indicator: "green",
                            });
                            frm.reload_doc();
                        },
                    });
                };
                isDirty ? frm.save("Save", doApprove) : doApprove();
            }
        );
    }, null, "primary");
}

function _addRejectRescanButton(frm) {
    frm.add_custom_button(__("Reject & Re-Scan"), () => {
        frappe.confirm(
            `<div style="font-size:13px;line-height:1.8;">
                <p><strong>Reject this discovery and start a fresh scan?</strong></p>
                <ul style="margin:6px 0 10px 18px;color:#6b7280;">
                    <li>Pending items will be discarded</li>
                    <li>Previously approved items will be kept</li>
                    <li>A fresh scan will begin immediately</li>
                </ul>
            </div>`,
            () => {
                frappe.call({
                    method: "ticketbrain.api.context.reject_and_rescan",
                    args: { doc_name: frm.doc.name },
                    callback() {
                        frappe.show_alert({ message: __("Rejected. Fresh scan started."), indicator: "blue" });
                        frm.reload_doc();
                        setTimeout(() => _pollScan(frm), 2000);
                    },
                });
            }
        );
    }, null, "danger");
}

function _addRefreshContextButton(frm) {
    frm.add_custom_button(__("Refresh Context"), () => {
        frappe.confirm(
            `<div style="font-size:13px;line-height:1.8;">
                <p><strong>Run a context refresh scan?</strong></p>
                <ul style="margin:6px 0 10px 18px;color:#374151;">
                    <li>AI will re-analyse your organisation for new teams, services, and patterns</li>
                    <li>Your current context (v${frm.doc.current_version || 1}) stays active during the scan</li>
                    <li>You will review and approve changes before they take effect</li>
                </ul>
                <p style="font-size:12px;color:#6b7280;margin:0;">
                    Recommended when: new departments created, new applications deployed, or support patterns have changed.
                </p>
            </div>`,
            () => {
                frappe.call({
                    method: "ticketbrain.api.context.refresh_context",
                    args: { doc_name: frm.doc.name },
                    callback() {
                        frappe.show_alert({ message: __("Refresh scan started."), indicator: "blue" });
                        frm.reload_doc();
                        setTimeout(() => _pollScan(frm), 2000);
                    },
                });
            }
        );
    }, null, "primary");
}

function _addViewHistoryButton(frm) {
    frm.add_custom_button(__("View History"), () => {
        frappe.call({
            method: "ticketbrain.api.context.get_versions",
            args: { doc_name: frm.doc.name },
            callback(r) {
                _showVersionHistoryDialog(frm, r.message || []);
            },
        });
    });
}

function _addCompareChangesButton(frm) {
    frm.add_custom_button(__("Compare Changes"), () => {
        // Find the latest Pending Review version
        frappe.call({
            method: "ticketbrain.api.context.get_versions",
            args: { doc_name: frm.doc.name },
            callback(r) {
                const versions = r.message || [];
                const pending  = versions.find(v => v.status === "Pending Review");
                if (!pending) {
                    frappe.show_alert({ message: __("No pending version to compare."), indicator: "orange" });
                    return;
                }
                frappe.call({
                    method: "ticketbrain.api.context.get_version_diff",
                    args: { version_name: pending.name },
                    callback(r2) {
                        _showDiffDialog(r2.message || {});
                    },
                });
            },
        });
    });
}

function _addApproveAllButton(frm) {
    const pendingCount = frm.doc.items_pending || 0;
    if (pendingCount <= 0) return;
    frm.add_custom_button(__("Approve All (%d)", [pendingCount]), () => {
        frappe.call({
            method: "ticketbrain.api.context.approve_all_pending",
            args: { doc_name: frm.doc.name },
            callback(r) {
                frappe.show_alert({
                    message: __("%d items approved.", [r.message?.approved]),
                    indicator: "green",
                });
                frm.reload_doc();
            },
        });
    });
}

function _addGenerateKBButton(frm) {
    const approvedCount = (frm.doc.items || []).filter(i => i.review_status === "Approved").length;
    if (approvedCount <= 0) return;
    frm.add_custom_button(__("Generate KB Articles"), () => {
        frappe.call({
            method: "ticketbrain.api.context.create_kb_articles",
            args: { doc_name: frm.doc.name },
            callback(r) {
                const count = r.message?.created || 0;
                frappe.show_alert({
                    message: count > 0
                        ? __("%d Knowledge Base articles created.", [count])
                        : __("No new articles to create — all approved items are already in the KB."),
                    indicator: count > 0 ? "green" : "orange",
                });
            },
        });
    }, __("Knowledge Base"));
}

function _addLegacyButtons(frm) {
    // For old records that don't have lifecycle_status set yet
    const scanning = frm.doc.scan_status === "Running";
    if (scanning) {
        _addAbortButton(frm);
    } else {
        frm.add_custom_button(__("Scan Organisation"), () => {
            frappe.call({
                method: "ticketbrain.api.context.run_scan",
                args: { doc_name: frm.doc.name },
                callback() { frm.reload_doc(); setTimeout(() => _pollScan(frm), 2000); },
            });
        });
    }
    if ((frm.doc.items || []).length > 0) {
        _addApproveContextButton(frm);
        _addApproveAllButton(frm);
    }
}

// ── Version History Dialog ────────────────────────────────────────────────────

function _showVersionHistoryDialog(frm, versions) {
    if (!versions.length) {
        frappe.msgprint(__("No version history available yet."));
        return;
    }

    const statusColors = {
        Active:         "#16a34a",
        Archived:       "#6b7280",
        "Pending Review": "#d97706",
        Rejected:       "#dc2626",
    };
    const statusBadge = (s) =>
        `<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;background:${statusColors[s] || "#6b7280"}22;color:${statusColors[s] || "#6b7280"};">${s}</span>`;

    const rows = versions.map(v => {
        const date     = v.scanned_at ? frappe.datetime.str_to_user(v.scanned_at) : "—";
        const approver = v.approved_by ? `<span style="color:#6b7280;font-size:11px;">by ${v.approved_by}</span>` : "";
        const diff     = v.items_added || v.items_removed
            ? `<span style="color:#6b7280;font-size:11px;">+${v.items_added||0} / -${v.items_removed||0}</span>`
            : "";
        const rollbackBtn = v.status === "Archived"
            ? `<button class="btn btn-xs btn-default rollback-btn" data-version="${v.name}" data-label="${v.version_label}" style="margin-left:6px;">Rollback</button>`
            : "";

        return `
            <tr>
                <td style="font-weight:600;color:#111827;">${v.version_label || "—"}</td>
                <td>${statusBadge(v.status)}</td>
                <td style="font-size:12px;color:#374151;">${date}</td>
                <td style="font-size:12px;">${diff}</td>
                <td style="font-size:12px;color:#6b7280;max-width:200px;overflow:hidden;text-overflow:ellipsis;">${v.scan_summary || "—"}</td>
                <td>${approver}${rollbackBtn}</td>
            </tr>`;
    }).join("");

    const table = `
        <table class="table table-bordered table-sm" style="font-size:13px;">
            <thead style="background:#f9fafb;">
                <tr>
                    <th>Version</th><th>Status</th><th>Scanned</th>
                    <th>Changes</th><th>Summary</th><th>Actions</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>`;

    const d = new frappe.ui.Dialog({
        title: __("Business Context Version History"),
        fields: [{ fieldtype: "HTML", fieldname: "history_html", options: table }],
        size: "extra-large",
    });
    d.show();

    // Wire up rollback buttons inside the dialog
    d.$wrapper.find(".rollback-btn").on("click", function () {
        const vName  = $(this).data("version");
        const vLabel = $(this).data("label");
        frappe.confirm(
            __("Roll back to <strong>%s</strong>? This will overwrite the current active context.", [vLabel]),
            () => {
                frappe.call({
                    method: "ticketbrain.api.context.rollback_to_version",
                    args: { version_name: vName },
                    callback(r) {
                        d.hide();
                        frappe.show_alert({
                            message: __("Rolled back to %s.", [r.message?.restored_version]),
                            indicator: "green",
                        });
                        frm.reload_doc();
                    },
                });
            }
        );
    });
}

// ── Context Comparison Dialog ─────────────────────────────────────────────────

function _showDiffDialog(diff) {
    const added   = (diff.change_summary?.added   || []);
    const removed = (diff.change_summary?.removed || []);

    const renderList = (items, color, icon) => {
        if (!items.length) return `<p style="color:#9ca3af;font-size:12px;">None</p>`;
        return items.map(i =>
            `<div style="display:flex;gap:8px;align-items:center;padding:4px 0;font-size:13px;">
                <span style="color:${color};font-weight:700;">${icon}</span>
                <span><strong>${i.item_type}</strong>: ${i.item_name}</span>
            </div>`
        ).join("");
    };

    const html = `
        <div style="font-size:13px;line-height:1.7;">
            <p style="color:#6b7280;margin-bottom:14px;">${diff.scan_summary || ""}</p>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
                <div>
                    <h6 style="color:#16a34a;margin:0 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;">
                        Added (${diff.items_added || added.length})
                    </h6>
                    ${renderList(added, "#16a34a", "+")}
                </div>
                <div>
                    <h6 style="color:#dc2626;margin:0 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;">
                        Removed (${diff.items_removed || removed.length})
                    </h6>
                    ${renderList(removed, "#dc2626", "−")}
                </div>
            </div>
        </div>`;

    new frappe.ui.Dialog({
        title: __("Context Changes — %s", [diff.version_label || "New Version"]),
        fields: [{ fieldtype: "HTML", fieldname: "diff_html", options: html }],
        size: "large",
    }).show();
}

// ── Scan poller ───────────────────────────────────────────────────────────────

function _pollScan(frm) {
    const interval = setInterval(async () => {
        try {
            const r = await frappe.call({
                method: "ticketbrain.api.context.get_scan_status",
                args: { doc_name: frm.doc.name },
            });
            const data   = r.message || {};
            const status = data.lifecycle_status || data.scan_status;

            if (status && status !== "Scanning" && status !== "Running") {
                clearInterval(interval);
                frm.reload_doc();

                if (status === "Review Required") {
                    frappe.show_alert({
                        message: __("Scan complete — %d items ready for review. Click Approve Context when done.", [data.items_pending || 0]),
                        indicator: "green",
                    });
                } else if (status === "Not Generated" || data.scan_status === "Failed") {
                    frappe.show_alert({ message: __("Scan failed. Check the Error Log."), indicator: "red" });
                }
            }
        } catch (e) {
            clearInterval(interval);
        }
    }, 4000);
}

// ── Confidence score colouring ────────────────────────────────────────────────

function _styleConfidenceScores(frm) {
    setTimeout(() => {
        frm.fields_dict.items?.grid?.wrapper?.find(".grid-row").each(function () {
            const cell = $(this).find("[data-fieldname='confidence_score'] .static-area");
            const val  = parseFloat(cell.text());
            if (!isNaN(val)) {
                cell.css({
                    "font-weight": "600",
                    "color": val >= 85 ? "#16a34a" : val >= 60 ? "#d97706" : "#dc2626",
                });
            }
        });
    }, 600);
}
