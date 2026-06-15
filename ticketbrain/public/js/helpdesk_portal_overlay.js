/**
 * TicketBrain — Helpdesk Portal Evaluating Overlay
 *
 * Shows a "Evaluating your ticket…" spinner while the AI pipeline processes a
 * new ticket. Injected into the Helpdesk Vue SPA via the <script> tag added to
 * helpdesk/www/helpdesk/index.html — this is the only way to reach customers
 * in the portal before they are logged in as agents.
 *
 * The Accept / Correct assignment panel is handled entirely via HD Form Script
 * (TicketBrain Approval Actions) — no source-code modification required for that.
 */
(function () {
    "use strict";

    var POLL_INTERVAL_MS = 3000;
    var MAX_POLLS        = 40;
    var OVERLAY_ID       = "tb-portal-evaluating-overlay";
    var _pollTimer       = null;
    var _lastTicketName  = null;

    // ── Route helper ──────────────────────────────────────────────────────────

    function _ticketNameFromPath() {
        var m = location.pathname.match(/\/helpdesk\/tickets\/([^\/]+)$/);
        if (!m || m[1] === "new") return null;
        return decodeURIComponent(m[1]);
    }

    // ── Lightweight GET API helper ─────────────────────────────────────────────

    function _api(method, params, callback) {
        var qs = Object.keys(params).map(function (k) {
            return encodeURIComponent(k) + "=" + encodeURIComponent(params[k]);
        }).join("&");
        fetch("/api/method/" + method + "?" + qs, { credentials: "same-origin" })
            .then(function (r) { return r.json(); })
            .then(function (d) { callback(null, d.message || {}); })
            .catch(function (e) { callback(e, {}); });
    }

    // ── Overlay ───────────────────────────────────────────────────────────────

    function _showOverlay() {
        if (document.getElementById(OVERLAY_ID)) return;
        var el = document.createElement("div");
        el.id  = OVERLAY_ID;
        el.innerHTML =
            '<div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(255,255,255,0.82);' +
            'backdrop-filter:blur(3px);-webkit-backdrop-filter:blur(3px);z-index:9999;' +
            'display:flex;align-items:center;justify-content:center;animation:tb-fadein 0.25s ease;">' +
                '<div style="position:relative;text-align:center;background:#fff;border:1px solid #e5e7eb;border-radius:12px;' +
                'padding:36px 48px 28px;box-shadow:0 8px 32px rgba(0,0,0,.10);max-width:420px;width:90%;">' +
                    '<button id="tb-overlay-close" aria-label="Close" style="position:absolute;top:12px;right:12px;' +
                    'width:28px;height:28px;border:none;border-radius:6px;background:#f8fafc;color:#64748b;' +
                    'cursor:pointer;font-size:18px;line-height:1;">&times;</button>' +
                    '<div style="margin-bottom:20px;">' +
                        '<svg width="48" height="48" viewBox="0 0 48 48" fill="none"' +
                        ' style="animation:tb-spin 1.2s linear infinite;display:inline-block;">' +
                            '<circle cx="24" cy="24" r="20" stroke="#e5e7eb" stroke-width="4"/>' +
                            '<path d="M44 24 A20 20 0 0 0 24 4" stroke="#6366f1" stroke-width="4" stroke-linecap="round"/>' +
                        '</svg>' +
                    '</div>' +
                    '<div style="font-size:17px;font-weight:600;color:#111827;margin-bottom:8px;">Evaluating your ticket…</div>' +
                    '<div style="font-size:13px;color:#6b7280;line-height:1.6;">' +
                        'TicketBrain AI is analysing your issue, finding the best resolution,<br>and routing it to the right team.' +
                        '<span style="display:block;color:#9ca3af;font-size:12px;margin-top:6px;">This usually takes a few seconds.</span>' +
                    '</div>' +
                    '<div style="margin-top:20px;display:flex;gap:6px;justify-content:center;margin-bottom:18px;">' +
                        '<span style="width:8px;height:8px;border-radius:50%;background:#a855f7;animation:tb-pulse 1.4s ease-in-out 0s infinite;display:inline-block;"></span>' +
                        '<span style="width:8px;height:8px;border-radius:50%;background:#a855f7;animation:tb-pulse 1.4s ease-in-out 0.2s infinite;display:inline-block;"></span>' +
                        '<span style="width:8px;height:8px;border-radius:50%;background:#7c3aed;animation:tb-pulse 1.4s ease-in-out 0.4s infinite;display:inline-block;"></span>' +
                    '</div>' +
                    '<button id="tb-overlay-continue" style="border:none;border-radius:8px;background:#eef2ff;' +
                    'color:#4f46e5;padding:9px 16px;font-size:13px;font-weight:600;cursor:pointer;">Continue browsing</button>' +
                '</div>' +
            '</div>' +
            '<style>' +
                '@keyframes tb-spin{to{transform:rotate(360deg)}}' +
                '@keyframes tb-fadein{from{opacity:0}to{opacity:1}}' +
                '@keyframes tb-pulse{0%,80%,100%{opacity:.3;transform:scale(.85)}40%{opacity:1;transform:scale(1.15)}}' +
            '</style>';
        document.body.appendChild(el);

        function dismiss() { _stopPolling(); _hideOverlay(); }
        var closeBtn    = document.getElementById("tb-overlay-close");
        var continueBtn = document.getElementById("tb-overlay-continue");
        if (closeBtn)    closeBtn.onclick    = dismiss;
        if (continueBtn) continueBtn.onclick = dismiss;
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
                    if (!err && msg.done && !msg.timed_out) {
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

    // ── Route change handler ──────────────────────────────────────────────────

    function _onRouteChange() {
        var name = _ticketNameFromPath();

        _stopPolling();
        _hideOverlay();

        if (!name || name === _lastTicketName) {
            if (!name) _lastTicketName = null;
            return;
        }
        _lastTicketName = name;

        _checkAndShowOverlay(name);
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
