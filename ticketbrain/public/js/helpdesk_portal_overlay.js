/**
 * TicketBrain — Helpdesk Portal Overlay + Assignment Panel
 *
 * Injected into the Helpdesk Vue.js SPA via web_include_js.
 * Handles two independent features:
 *   1. Evaluating overlay — dimmed screen while AI processes a new ticket.
 *   2. Assignment panel  — Accept / Correct AI assignment banner for agents.
 */
(function () {
    "use strict";

    var POLL_INTERVAL_MS  = 3000;
    var MAX_POLLS         = 40;
    var OVERLAY_ID        = "tb-portal-evaluating-overlay";
    var PANEL_ID          = "tb-assignment-panel";
    var DIALOG_ID         = "tb-correction-dialog";
    var _pollTimer        = null;
    var _lastTicketName   = null;

    // ── Route helper ─────────────────────────────────────────────────────────

    function _ticketNameFromPath() {
        var m = location.pathname.match(/\/helpdesk\/tickets\/([^\/]+)$/);
        if (!m || m[1] === "new") return null;
        return decodeURIComponent(m[1]);
    }

    // ── Generic API fetch ─────────────────────────────────────────────────────

    function _api(method, params, callback) {
        var qs = Object.keys(params).map(function (k) {
            return encodeURIComponent(k) + "=" + encodeURIComponent(params[k]);
        }).join("&");
        fetch("/api/method/" + method + "?" + qs, { credentials: "same-origin" })
            .then(function (r) { return r.json(); })
            .then(function (d) { callback(null, d.message || {}); })
            .catch(function (e) { callback(e, {}); });
    }

    function _apiPost(method, params, callback) {
        var body = new URLSearchParams(params);
        // Include CSRF token if frappe exposes it
        var csrf = (window.frappe && window.frappe.csrf_token) || "";
        fetch("/api/method/" + method, {
            method: "POST",
            credentials: "same-origin",
            headers: { "X-Frappe-CSRF-Token": csrf, "Content-Type": "application/x-www-form-urlencoded" },
            body: body.toString(),
        })
            .then(function (r) { return r.json(); })
            .then(function (d) { callback(null, d.message || {}); })
            .catch(function (e) { callback(e, {}); });
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // FEATURE 1 — Evaluating overlay
    // ═══════════════════════════════════════════════════════════════════════════

    function _showOverlay() {
        if (document.getElementById(OVERLAY_ID)) return;
        var el = document.createElement("div");
        el.id  = OVERLAY_ID;
        el.innerHTML =
            '<div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(255,255,255,0.82);' +
            'backdrop-filter:blur(3px);-webkit-backdrop-filter:blur(3px);z-index:9999;' +
            'display:flex;align-items:center;justify-content:center;animation:tb-fadein 0.25s ease;">' +
                '<div style="text-align:center;background:#fff;border:1px solid #e5e7eb;border-radius:12px;' +
                'padding:36px 48px;box-shadow:0 8px 32px rgba(0,0,0,.10);max-width:420px;width:90%;">' +
                    '<div style="margin-bottom:20px;">' +
                        '<svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"' +
                        ' style="animation:tb-spin 1.2s linear infinite;display:inline-block;">' +
                            '<circle cx="24" cy="24" r="20" stroke="#e5e7eb" stroke-width="4"/>' +
                            '<path d="M44 24 A20 20 0 0 0 24 4" stroke="#6366f1" stroke-width="4" stroke-linecap="round"/>' +
                        '</svg>' +
                    '</div>' +
                    '<div style="font-size:17px;font-weight:600;color:#111827;margin-bottom:8px;">Evaluating your ticket…</div>' +
                    '<div style="font-size:13px;color:#6b7280;line-height:1.6;">' +
                        'TicketBrain AI is analysing your issue, finding the best resolution, and routing it to the right team.<br>' +
                        '<span style="color:#9ca3af;font-size:12px;margin-top:6px;display:block;">This usually takes a few seconds.</span>' +
                    '</div>' +
                    '<div style="margin-top:20px;display:flex;gap:6px;justify-content:center;">' +
                        '<span style="width:8px;height:8px;border-radius:50%;background:#6366f1;animation:tb-pulse 1.4s ease-in-out 0s infinite;display:inline-block;"></span>' +
                        '<span style="width:8px;height:8px;border-radius:50%;background:#6366f1;animation:tb-pulse 1.4s ease-in-out 0.2s infinite;display:inline-block;"></span>' +
                        '<span style="width:8px;height:8px;border-radius:50%;background:#6366f1;animation:tb-pulse 1.4s ease-in-out 0.4s infinite;display:inline-block;"></span>' +
                    '</div>' +
                '</div>' +
            '</div>' +
            '<style>' +
                '@keyframes tb-spin{to{transform:rotate(360deg)}}' +
                '@keyframes tb-fadein{from{opacity:0}to{opacity:1}}' +
                '@keyframes tb-pulse{0%,80%,100%{opacity:.3;transform:scale(.85)}40%{opacity:1;transform:scale(1.15)}}' +
            '</style>';
        document.body.appendChild(el);
    }

    function _hideOverlay() {
        var el = document.getElementById(OVERLAY_ID);
        if (!el) return;
        el.style.animation = "tb-fadein 0.2s ease reverse";
        setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 220);
    }

    function _stopPolling() {
        if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
    }

    function _startPolling(ticketName) {
        _stopPolling();
        var polls = 0;
        _pollTimer = setInterval(function () {
            polls++;
            _api("ticketbrain.api.ticket.get_ai_processing_status", { ticket_name: ticketName }, function (err, msg) {
                if (err || msg.done || polls >= MAX_POLLS) {
                    _stopPolling();
                    _hideOverlay();
                    if (msg.done && !msg.timed_out) {
                        location.reload();
                    }
                }
            });
        }, POLL_INTERVAL_MS);
    }

    function _checkAndShowOverlay(ticketName) {
        _api("ticketbrain.api.ticket.get_ai_processing_status", { ticket_name: ticketName }, function (err, msg) {
            if (err || msg.done) return;
            _showOverlay();
            _startPolling(ticketName);
        });
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // FEATURE 2 — Assignment panel (Accept / Correct)
    // Only shown to the agent this ticket is assigned to.
    // ═══════════════════════════════════════════════════════════════════════════

    var _HD_TEAMS = [];   // cached team list for dialog dropdown

    function _removePanel() {
        var el = document.getElementById(PANEL_ID);
        if (el && el.parentNode) el.parentNode.removeChild(el);
    }

    function _removeDialog() {
        var el = document.getElementById(DIALOG_ID);
        if (el && el.parentNode) el.parentNode.removeChild(el);
    }

    function _findInjectionPoint() {
        // Frappe Helpdesk uses Tailwind utility classes; ".activities" is one of
        // the few explicit semantic class names in TicketAgentActivities.vue.
        var selectors = [
            ".activities",           // Helpdesk portal activity feed container
            ".ticket-conversation",
            ".activity-section",
            ".main-section main",
            "main",
        ];
        for (var i = 0; i < selectors.length; i++) {
            var el = document.querySelector(selectors[i]);
            if (el) return el;
        }
        return null;
    }

    // ── Panel ────────────────────────────────────────────────────────────────

    function _injectPanel(ticketName, data) {
        _removePanel();
        var target = _findInjectionPoint();
        if (!target) return;

        var confColor = data.confidence >= 80 ? "#16a34a" : data.confidence >= 65 ? "#e6a817" : "#e53e3e";
        var confBg    = data.confidence >= 80 ? "#f0fdf4" : data.confidence >= 65 ? "#fffbeb" : "#fff5f5";
        var teamLabel = data.ai_team || "Not assigned";

        var panel = document.createElement("div");
        panel.id  = PANEL_ID;
        panel.style.cssText = [
            "background:#fff",
            "border:1px solid #e2e8f0",
            "border-radius:8px",
            "padding:16px 20px",
            "margin:0 0 16px 0",
            "box-shadow:0 1px 3px rgba(0,0,0,.06)",
            "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif",
        ].join(";");

        panel.innerHTML =
            // Header row
            '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;">' +
                '<div style="display:flex;align-items:center;gap:7px;">' +
                    '<div style="width:7px;height:7px;border-radius:50%;background:#6366f1;flex-shrink:0;"></div>' +
                    '<span style="font-size:13px;font-weight:600;color:#1e293b;letter-spacing:-.01em;">TicketBrain AI Recommendation</span>' +
                '</div>' +
                '<span style="font-size:11px;color:#94a3b8;font-weight:500;">' + (data.decision || "") + '</span>' +
            '</div>' +
            // Info grid
            '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px;">' +
                _cell("Category", data.ai_category || "—", "#1e293b") +
                _cell("Team",     teamLabel,                "#1e293b") +
                _cell("Priority", data.ai_priority || "—", "#1e293b") +
                _cell("Confidence", data.confidence + "%", confColor, confBg) +
            '</div>' +
            // Divider
            '<div style="border-top:1px solid #f1f5f9;margin-bottom:14px;"></div>' +
            // Buttons
            '<div style="display:flex;gap:8px;">' +
                '<button id="tb-accept-btn" style="' + _btn("#22c55e", "#fff", true) + '">&#10003; Accept Assignment</button>' +
                '<button id="tb-correct-btn" style="' + _btn("#fff", "#475569", false) + '">&#9998; Correct Assignment</button>' +
            '</div>';

        target.parentNode.insertBefore(panel, target);

        document.getElementById("tb-accept-btn").onclick = function () {
            if (!confirm("Accept the AI assignment? This records your approval and removes this panel.")) return;
            this.disabled = true;
            this.textContent = "Accepting…";
            _apiPost("ticketbrain.api.correction.accept_assignment", { ticket_id: ticketName }, function (err, msg) {
                if (!err && msg.ok) {
                    _removePanel();
                    _toast("Assignment accepted.", "#22c55e");
                } else {
                    document.getElementById("tb-accept-btn") && (document.getElementById("tb-accept-btn").disabled = false);
                }
            });
        };

        document.getElementById("tb-correct-btn").onclick = function () {
            // Fetch teams first, then show dialog
            if (_HD_TEAMS.length > 0) {
                _showCorrectionDialog(ticketName, data);
            } else {
                _api("ticketbrain.api.correction.get_teams", {}, function (err, teams) {
                    _HD_TEAMS = Array.isArray(teams) ? teams : [];
                    _showCorrectionDialog(ticketName, data);
                });
            }
        };
    }

    function _cell(label, value, valueColor, valueBg) {
        var bgStyle = valueBg ? "background:" + valueBg + ";border-radius:4px;padding:2px 6px;display:inline-block;" : "";
        return '<div>' +
            '<div style="font-size:10px;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px;">' + label + '</div>' +
            '<div style="font-size:13px;font-weight:600;color:' + valueColor + ';"><span style="' + bgStyle + '">' + _esc(value) + '</span></div>' +
            '</div>';
    }

    function _btn(bg, color, filled) {
        return [
            "padding:7px 14px",
            "border-radius:6px",
            "border:1px solid " + (filled ? "transparent" : "#e2e8f0"),
            "background:" + bg,
            "color:" + color,
            "font-size:12px",
            "font-weight:500",
            "cursor:pointer",
            "font-family:inherit",
            "line-height:1.4",
            "transition:opacity .15s",
        ].join(";");
    }

    // ── Correction dialog ─────────────────────────────────────────────────────

    function _showCorrectionDialog(ticketName, data) {
        _removeDialog();

        var teamOptions = _HD_TEAMS.map(function (t) {
            return '<option value="' + _esc(t) + '"' + (t === data.ai_team ? " selected" : "") + '>' + _esc(t) + '</option>';
        }).join("");
        if (!data.ai_team) teamOptions = '<option value="" selected>— Select team —</option>' + teamOptions;

        var wrap = document.createElement("div");
        wrap.id  = DIALOG_ID;
        wrap.style.cssText = "position:fixed;inset:0;background:rgba(15,23,42,.35);z-index:10000;" +
            "display:flex;align-items:center;justify-content:center;padding:16px;";

        wrap.innerHTML =
            '<div style="background:#fff;border-radius:10px;width:100%;max-width:460px;' +
            'box-shadow:0 20px 60px rgba(15,23,42,.18);font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif;">' +
                // Dialog header
                '<div style="padding:18px 22px 14px;border-bottom:1px solid #f1f5f9;display:flex;justify-content:space-between;align-items:center;">' +
                    '<span style="font-size:14px;font-weight:600;color:#0f172a;">Correct AI Assignment</span>' +
                    '<button id="tb-dialog-close" style="background:none;border:none;cursor:pointer;color:#94a3b8;font-size:18px;line-height:1;padding:2px;">&#10005;</button>' +
                '</div>' +
                // AI summary banner
                '<div style="margin:14px 22px 0;background:#f8fafc;border:1px solid #e2e8f0;border-radius:7px;padding:10px 14px;">' +
                    '<div style="font-size:10px;font-weight:700;color:#6366f1;text-transform:uppercase;letter-spacing:.07em;margin-bottom:6px;">AI Predicted</div>' +
                    '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">' +
                        _miniCell("Category", data.ai_category || "—") +
                        _miniCell("Team",     data.ai_team     || "—") +
                        _miniCell("Priority (" + data.confidence + "%)", data.ai_priority || "—") +
                    '</div>' +
                '</div>' +
                // Form fields
                '<div style="padding:16px 22px;">' +
                    _dlgField("tb-human-category", "input", "Correct Category", data.ai_category || "", null, null) +
                    _dlgField("tb-human-team",     "select", "Correct Team", null, teamOptions, null) +
                    _dlgField("tb-human-priority", "select", "Correct Priority", null,
                        ["Low","Medium","High","Critical"].map(function(p){
                            return '<option' + (p===data.ai_priority?" selected":"") + '>' + p + '</option>';
                        }).join(""), null) +
                    _dlgField("tb-correction-reason", "input", "Correction Reason", "", null,
                        "e.g. Wrong Team, ERP Issue Not Network Issue, Wrong Priority") +
                    '<p style="font-size:11px;color:#94a3b8;margin:4px 0 0;">Required — this trains the AI for future tickets.</p>' +
                '</div>' +
                // Footer buttons
                '<div style="padding:12px 22px 18px;display:flex;justify-content:flex-end;gap:8px;border-top:1px solid #f1f5f9;">' +
                    '<button id="tb-dialog-cancel" style="' + _btn("#fff","#475569",false) + '">Cancel</button>' +
                    '<button id="tb-dialog-submit" style="' + _btn("#6366f1","#fff",true) + '">Submit Correction</button>' +
                '</div>' +
            '</div>';

        document.body.appendChild(wrap);

        document.getElementById("tb-dialog-close").onclick  = _removeDialog;
        document.getElementById("tb-dialog-cancel").onclick = _removeDialog;
        wrap.onclick = function (e) { if (e.target === wrap) _removeDialog(); };

        document.getElementById("tb-dialog-submit").onclick = function () {
            var reason = (document.getElementById("tb-correction-reason").value || "").trim();
            if (!reason) {
                document.getElementById("tb-correction-reason").style.borderColor = "#e53e3e";
                document.getElementById("tb-correction-reason").focus();
                return;
            }
            var btn = this;
            btn.disabled = true;
            btn.textContent = "Saving…";

            _apiPost("ticketbrain.api.correction.submit_correction", {
                ticket_id:         ticketName,
                human_category:    document.getElementById("tb-human-category").value  || "",
                human_team:        document.getElementById("tb-human-team").value      || "",
                human_priority:    document.getElementById("tb-human-priority").value  || "",
                correction_reason: reason,
            }, function (err, msg) {
                if (!err && msg.ok) {
                    _removeDialog();
                    _removePanel();
                    _toast("Correction saved — AI will learn from this for future tickets.", "#6366f1");
                } else {
                    btn.disabled = false;
                    btn.textContent = "Submit Correction";
                    _toast("Failed to save. Please try again.", "#e53e3e");
                }
            });
        };
    }

    function _miniCell(label, value) {
        return '<div><div style="font-size:10px;color:#94a3b8;margin-bottom:2px;">' + label + '</div>' +
            '<div style="font-size:12px;font-weight:600;color:#334155;">' + _esc(value) + '</div></div>';
    }

    function _dlgField(id, type, label, value, optionsHtml, placeholder) {
        var inputHtml;
        var inputStyle = "width:100%;box-sizing:border-box;border:1px solid #e2e8f0;border-radius:6px;" +
            "padding:8px 11px;font-size:13px;font-family:inherit;color:#0f172a;background:#fff;outline:none;";
        if (type === "select") {
            inputHtml = '<select id="' + id + '" style="' + inputStyle + '">' + optionsHtml + '</select>';
        } else {
            inputHtml = '<input id="' + id + '" type="text" value="' + _esc(value || "") + '"' +
                (placeholder ? ' placeholder="' + _esc(placeholder) + '"' : '') +
                ' style="' + inputStyle + '">';
        }
        return '<div style="margin-bottom:13px;">' +
            '<label for="' + id + '" style="display:block;font-size:11px;font-weight:600;color:#475569;' +
            'text-transform:uppercase;letter-spacing:.05em;margin-bottom:5px;">' + label + '</label>' +
            inputHtml + '</div>';
    }

    function _esc(s) { return String(s).replace(/"/g, "&quot;").replace(/</g, "&lt;"); }

    function _toast(msg, color) {
        var t = document.createElement("div");
        t.style.cssText = "position:fixed;bottom:24px;right:24px;background:" + color +
            ";color:#fff;padding:10px 18px;border-radius:8px;font-size:13px;z-index:10001;" +
            "box-shadow:0 4px 16px rgba(0,0,0,.15);animation:tb-fadein 0.2s ease;";
        t.textContent = msg;
        document.body.appendChild(t);
        setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 3500);
    }

    function _checkAndShowPanel(ticketName) {
        _api("ticketbrain.api.correction.get_assignment_status", { ticket_id: ticketName }, function (err, data) {
            if (err || !data.has_ai || data.already_acted) return;

            // Retry up to 5× if DOM injection point isn't ready yet
            var attempts = 0;
            function _tryInject() {
                attempts++;
                var target = _findInjectionPoint();
                if (target) {
                    _injectPanel(ticketName, data);
                } else if (attempts < 5) {
                    setTimeout(_tryInject, 400);
                }
            }
            _tryInject();
        });
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // Route change handler
    // ═══════════════════════════════════════════════════════════════════════════

    function _onRouteChange() {
        var name = _ticketNameFromPath();
        if (!name) return;

        // Clean up previous ticket state
        _stopPolling();
        _hideOverlay();
        _removePanel();
        _removeDialog();

        if (name === _lastTicketName) return;
        _lastTicketName = name;

        // Feature 1: evaluating overlay
        _checkAndShowOverlay(name);

        // Feature 2: assignment panel (give Vue 600ms to render ticket content)
        setTimeout(function () { _checkAndShowPanel(name); }, 600);
    }

    // ── Intercept SPA navigation ──────────────────────────────────────────────

    var _origPush = history.pushState.bind(history);
    history.pushState = function () {
        _origPush.apply(history, arguments);
        setTimeout(_onRouteChange, 400);
    };

    window.addEventListener("popstate", function () {
        setTimeout(_onRouteChange, 400);
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () { setTimeout(_onRouteChange, 800); });
    } else {
        setTimeout(_onRouteChange, 800);
    }
})();
