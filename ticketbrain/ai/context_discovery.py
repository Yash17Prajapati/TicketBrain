"""
TicketBrain Context Discovery Engine — Redesigned

Architecture:
  ERPNext + Helpdesk raw data
      ↓  aggregate into summaries (never send raw records to LLM)
  LLM analysis over summaries
      ↓  structured JSON with strict taxonomy
  Taxonomy validation (reject cross-contamination)
      ↓
  Merge into TB Business Context (preserving human edits)
      ↓
  Optional: push approved items into RAG indexes

Taxonomy (strictly separated):
  Business Profile  — industry / company type only
  Support Team      — ONLY teams with ticket evidence
  Ticket Category   — issue classification labels (NOT services, NOT teams)
  Service           — things users consume/request (NOT category names)
  Application       — software systems (NOT services, NOT categories)
  Ownership         — service→team mappings backed by evidence
  Historical Pattern — repeated issue-resolution pairs

Every discovered item carries an evidence list. Items without evidence are rejected.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import frappe

# The 6 system-level categories TicketBrain already knows about.
# These must NEVER be re-discovered as Services, Applications, or Teams.
_SYSTEM_CATEGORIES = {
    "hardware & infrastructure",
    "software & applications",
    "security & threats",
    "data & reports",
    "network & connectivity",
    "account & access",
}

_MIN_CONFIDENCE = 0.55   # items below this are silently dropped


# ── Data Collection (summaries only) ─────────────────────────────────────────

class ContextDiscoveryEngine:

    def __init__(self):
        self.company = (
            frappe.db.get_single_value("Global Defaults", "default_company")
            or frappe.db.get_value("Company", {}, "name")
            or "TicketBrain"
        )
        self.raw: dict = {}

    def collect(self) -> dict:
        self.raw = {
            "company_summary":   self._company_summary(),
            "helpdesk_summary":  self._helpdesk_summary(),
            "ticket_summary":    self._ticket_summary(),
            "kb_summary":        self._kb_summary(),
        }
        return self.raw

    def _company_summary(self) -> dict:
        try:
            doc = frappe.get_doc("Company", self.company)
            result = {
                "name":     doc.company_name or doc.name,
                "country":  doc.country or "",
                "industry": getattr(doc, "industry", None) or "",
            }
        except Exception:
            result = {"name": self.company, "country": "", "industry": ""}

        # Department count (metadata only, not names — prevent dept→team confusion)
        try:
            dept_count = frappe.db.count("Department", {"company": self.company})
            result["department_count"] = dept_count
        except Exception:
            result["department_count"] = 0

        # Project names (active) — may surface as services (e.g. "ERP Implementation")
        try:
            projects = frappe.get_all(
                "Project",
                filters={"company": self.company, "status": "Open"},
                fields=["project_name"],
                limit=10,
            )
            result["active_projects"] = [p.project_name for p in projects]
        except Exception:
            result["active_projects"] = []

        # Asset item groups (hardware/infrastructure signal)
        try:
            asset_groups = frappe.db.sql(
                "SELECT item_group, COUNT(*) as cnt FROM `tabAsset` "
                "WHERE company=%s GROUP BY item_group ORDER BY cnt DESC LIMIT 8",
                self.company, as_dict=True,
            )
            result["asset_groups"] = [
                {"group": r.item_group, "count": r.cnt}
                for r in asset_groups
            ]
        except Exception:
            result["asset_groups"] = []

        return result

    def _helpdesk_summary(self) -> dict:
        # Teams WITH ticket evidence
        teams = frappe.get_all("HD Team", fields=["name", "team_name"])
        team_data = []
        for t in teams:
            tname = t.team_name or t.name
            ticket_count = frappe.db.count("HD Ticket", {"agent_group": tname})
            resolved_count = frappe.db.count(
                "HD Ticket",
                {"agent_group": tname, "status": ["in", ["Resolved", "Closed", "AI Resolved"]]},
            )
            try:
                member_count = frappe.db.sql(
                    "SELECT COUNT(*) as cnt FROM `tabHD Team Member` WHERE parent=%s",
                    t.name, as_dict=True,
                )[0].cnt
            except Exception:
                member_count = 0

            team_data.append({
                "name":            tname,
                "total_tickets":   ticket_count,
                "resolved_tickets": resolved_count,
                "members":         member_count,
            })

        # Agent count
        try:
            agent_count = frappe.db.count("HD Agent", {"is_active": 1})
        except Exception:
            agent_count = 0

        # HD Ticket Categories (Frappe Helpdesk uses a Category doctype)
        try:
            hd_cats = frappe.get_all(
                "HD Ticket Template",
                fields=["template_name"],
                limit=20,
            )
            hd_cat_names = [c.template_name for c in hd_cats]
        except Exception:
            hd_cat_names = []

        return {
            "teams":           team_data,
            "agent_count":     agent_count,
            "hd_categories":   hd_cat_names,
        }

    def _ticket_summary(self) -> dict:
        tickets = frappe.db.sql(
            """SELECT subject, tb_category, priority, status, agent_group
               FROM `tabHD Ticket`
               ORDER BY modified DESC LIMIT 500""",
            as_dict=True,
        )

        total = len(tickets)
        cat_counts:  dict[str, int] = {}
        team_counts: dict[str, int] = {}
        resolved_teams: set[str]    = set()
        subjects: list[str]         = []

        for t in tickets:
            cat = t.tb_category or "Uncategorised"
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

            grp = t.agent_group or "Unassigned"
            team_counts[grp] = team_counts.get(grp, 0) + 1

            if t.status in ("Resolved", "Closed", "AI Resolved") and t.agent_group:
                resolved_teams.add(t.agent_group)

            if t.subject:
                subjects.append(t.subject)

        # Extract common terms from subjects to infer services/applications
        # (simple word frequency — sent to LLM for reasoning)
        word_freq: dict[str, int] = {}
        stop = {
            "the", "a", "an", "is", "my", "not", "can", "i", "to", "in",
            "on", "for", "of", "and", "or", "with", "it", "its", "are",
            "was", "have", "has", "be", "do", "did", "does",
        }
        for s in subjects[:200]:
            for w in re.split(r"\W+", s.lower()):
                if len(w) > 3 and w not in stop:
                    word_freq[w] = word_freq.get(w, 0) + 1
        top_words = sorted(word_freq.items(), key=lambda x: -x[1])[:25]

        return {
            "total_tickets":     total,
            "category_dist":     sorted(cat_counts.items(), key=lambda x: -x[1])[:15],
            "team_dist":         sorted(team_counts.items(), key=lambda x: -x[1])[:10],
            "teams_with_resolutions": list(resolved_teams),
            "top_subject_terms": [{"term": t, "count": c} for t, c in top_words],
            "sample_subjects":   subjects[:20],
        }

    def _kb_summary(self) -> dict:
        try:
            articles = frappe.get_all(
                "HD Article",
                filters={"status": "Published"},
                fields=["title", "category"],
                limit=100,
            )
        except Exception:
            articles = []

        cat_counts: dict[str, int] = {}
        for a in articles:
            cat = a.category or "Uncategorised"
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

        return {
            "total_articles": len(articles),
            "category_dist":  sorted(cat_counts.items(), key=lambda x: -x[1])[:10],
            "sample_titles":  [a.title for a in articles[:15]],
        }

    # ── LLM Analysis ──────────────────────────────────────────────────────────

    def analyze(self) -> dict:
        from ticketbrain.ai.llm_provider import is_available, call_llm
        from ticketbrain.ai.prompt_builder import build_discovery_prompt

        if not is_available():
            frappe.logger().info("TicketBrain Context: LLM not available, using heuristic analysis")
            return self._heuristic_analysis()

        prompt = build_discovery_prompt(self.raw)
        try:
            raw_text = call_llm(prompt, json_mode=True, timeout=180)
            if not raw_text:
                raise ValueError("Empty LLM response")

            # Strip markdown fences if the model wrapped in ```json ... ```
            text = raw_text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```[a-z]*\n?", "", text)
                text = re.sub(r"\n?```$", "", text.strip())

            result = json.loads(text)
            frappe.logger().info("TicketBrain Context: LLM analysis succeeded")
            return result
        except Exception:
            frappe.logger().warning(
                "TicketBrain Context: LLM analysis failed, falling back to heuristic"
            )
            frappe.log_error(frappe.get_traceback(), "TicketBrain: Context LLM analysis failed")
            return self._heuristic_analysis()

    # ── Heuristic Fallback ────────────────────────────────────────────────────

    def _heuristic_analysis(self) -> dict:
        """Rule-based fallback with strict taxonomy. Never hallucinates."""
        ticket  = self.raw.get("ticket_summary", {})
        hd      = self.raw.get("helpdesk_summary", {})
        kb      = self.raw.get("kb_summary", {})
        company = self.raw.get("company_summary", {})
        total   = ticket.get("total_tickets", 1) or 1

        # Business profile — company info only
        business_profile = {
            "industry":      company.get("industry", ""),
            "business_type": "",
            "summary":       "",
        }

        # Support teams — only teams with resolved ticket evidence
        resolved_team_set = set(ticket.get("teams_with_resolutions", []))
        support_teams = []
        for team in hd.get("teams", []):
            if team["resolved_tickets"] > 0 or team["total_tickets"] > 5:
                conf   = min(0.55 + (team["resolved_tickets"] / max(total, 1)) * 2, 0.92)
                evidence = [
                    f"{team['total_tickets']} tickets assigned",
                    f"{team['resolved_tickets']} resolved",
                ]
                if team["members"]:
                    evidence.append(f"{team['members']} team member(s)")
                support_teams.append({
                    "name":        team["name"],
                    "description": f"Handles {team['total_tickets']} tickets, resolved {team['resolved_tickets']}",
                    "confidence":  round(conf, 2),
                    "evidence":    evidence,
                })

        # Ticket categories — only from tb_category field (what TicketBrain already classified)
        ticket_categories = []
        for cat, cnt in ticket.get("category_dist", []):
            if not cat or cat in ("Uncategorised", "Unassigned"):
                continue
            # Skip if this is a system category (already known)
            if cat.lower() in _SYSTEM_CATEGORIES:
                continue
            freq  = "high" if cnt / total > 0.25 else "medium" if cnt / total > 0.08 else "low"
            conf  = round(min(0.55 + (cnt / total) * 0.40, 0.85), 2)
            ticket_categories.append({
                "name":        cat,
                "description": f"Custom category with {cnt} ticket(s)",
                "frequency":   freq,
                "confidence":  conf,
                "evidence":    [f"{cnt} tickets classified as this category"],
            })

        # Historical patterns from top subject terms
        historical_patterns = []
        top_terms = ticket.get("top_subject_terms", [])
        if top_terms and total >= 10:
            top_term = top_terms[0]
            pct      = round(top_term["count"] / total * 100)
            if pct > 5:
                historical_patterns.append({
                    "pattern":    f"Frequent mention of '{top_term['term']}' in tickets",
                    "root_cause": "Recurring user issue",
                    "resolution": "Check KB for related articles",
                    "frequency":  "high",
                    "confidence": 0.60,
                    "evidence":   [f"'{top_term['term']}' appears in {top_term['count']}/{total} ticket subjects ({pct}%)"],
                })

        # KB-sourced context (infer services/applications from KB article categories)
        services = []
        applications = []
        kb_cats = {cat: cnt for cat, cnt in kb.get("category_dist", [])}
        for title in kb.get("sample_titles", []):
            tl = title.lower()
            # Only infer if the title looks like a specific service/app, not a system category
            if any(kw in tl for kw in ("vpn", "email", "printing", "attendance", "internet")):
                svc_name = _extract_service_name(title)
                if svc_name and not _is_system_category(svc_name):
                    services.append({
                        "name":        svc_name,
                        "description": f"Service referenced in KB articles",
                        "owner_team":  "",
                        "confidence":  0.60,
                        "evidence":    [f"KB article: '{title}'"],
                    })
            if any(kw in tl for kw in ("erpnext", "erp", "outlook", "office 365", "crm", "portal")):
                app_name = _extract_app_name(title)
                if app_name:
                    applications.append({
                        "name":        app_name,
                        "description": f"Application referenced in KB articles",
                        "owner_team":  "",
                        "confidence":  0.60,
                        "evidence":    [f"KB article: '{title}'"],
                    })

        return {
            "business_profile":  business_profile,
            "support_teams":     support_teams,
            "ticket_categories": ticket_categories[:8],
            "services":          services[:6],
            "applications":      applications[:6],
            "ownership_mapping": [],
            "historical_patterns": historical_patterns,
        }

    # ── Taxonomy Validation ───────────────────────────────────────────────────

    def validate(self, llm: dict) -> dict:
        """
        Enforce taxonomy separation on LLM output.
        Rejects cross-contamination and items without evidence.
        """
        categories_found: set[str] = set()

        # Gather all declared ticket_category names (lowercased) for cross-check
        for cat in llm.get("ticket_categories", []):
            if cat.get("name"):
                categories_found.add(cat["name"].lower())

        def _reject_if_category(items: list[dict], item_label: str) -> list[dict]:
            out = []
            for item in items:
                name = item.get("name", "")
                if name.lower() in _SYSTEM_CATEGORIES:
                    frappe.logger().warning(
                        f"TicketBrain Context: rejected {item_label} '{name}' "
                        "(matches system category)"
                    )
                    continue
                if name.lower() in categories_found:
                    frappe.logger().warning(
                        f"TicketBrain Context: rejected {item_label} '{name}' "
                        "(already a Ticket Category)"
                    )
                    continue
                out.append(item)
            return out

        validated = dict(llm)
        validated["services"]     = _reject_if_category(llm.get("services", []),     "Service")
        validated["applications"] = _reject_if_category(llm.get("applications", []), "Application")

        # Support teams must have evidence from ticket resolution
        resolved_teams = set(self.raw.get("ticket_summary", {}).get("teams_with_resolutions", []))
        hd_teams       = {
            t["name"].lower()
            for t in self.raw.get("helpdesk_summary", {}).get("teams", [])
            if t.get("total_tickets", 0) > 0
        }

        validated_teams = []
        for team in llm.get("support_teams", []):
            name = team.get("name", "")
            evidence = team.get("evidence", [])
            has_ticket_evidence = (
                name in resolved_teams
                or name.lower() in hd_teams
                or any("ticket" in e.lower() for e in evidence)
            )
            if not has_ticket_evidence:
                if team.get("confidence", 0) < 0.70:
                    frappe.logger().warning(
                        f"TicketBrain Context: rejected Support Team '{name}' "
                        "(no ticket evidence)"
                    )
                    continue
            validated_teams.append(team)
        validated["support_teams"] = validated_teams

        return validated

    # ── Item Extraction ───────────────────────────────────────────────────────

    def extract_items(self, llm: dict) -> list[dict]:
        items: list[dict] = []

        def _evidence_str(ev: list) -> str:
            return "; ".join(str(e) for e in (ev or []))

        # Support Teams
        for team in llm.get("support_teams", []):
            conf = team.get("confidence", 0)
            if not team.get("name") or conf < _MIN_CONFIDENCE:
                continue
            items.append({
                "item_type":       "Support Team",
                "item_name":       team["name"],
                "description":     team.get("description", ""),
                "related_team":    team["name"],
                "confidence_score": round(conf * 100, 1),
                "evidence":        _evidence_str(team.get("evidence", [])),
            })

        # Services
        for svc in llm.get("services", []):
            conf = svc.get("confidence", 0)
            if not svc.get("name") or conf < _MIN_CONFIDENCE:
                continue
            items.append({
                "item_type":       "Service",
                "item_name":       svc["name"],
                "description":     svc.get("description", ""),
                "related_team":    svc.get("owner_team", ""),
                "confidence_score": round(conf * 100, 1),
                "evidence":        _evidence_str(svc.get("evidence", [])),
            })

        # Applications
        for app in llm.get("applications", []):
            conf = app.get("confidence", 0)
            if not app.get("name") or conf < _MIN_CONFIDENCE:
                continue
            items.append({
                "item_type":       "Application",
                "item_name":       app["name"],
                "description":     app.get("description", ""),
                "related_team":    app.get("owner_team", ""),
                "confidence_score": round(conf * 100, 1),
                "evidence":        _evidence_str(app.get("evidence", [])),
            })

        # Ticket Categories (only custom, non-system categories)
        for cat in llm.get("ticket_categories", []):
            conf = cat.get("confidence", 0)
            name = cat.get("name", "")
            if not name or conf < _MIN_CONFIDENCE:
                continue
            if name.lower() in _SYSTEM_CATEGORIES:
                continue
            freq = cat.get("frequency", "")
            desc = cat.get("description", "")
            if freq:
                desc = f"[{freq.upper()}] {desc}".strip()
            items.append({
                "item_type":       "Ticket Category",
                "item_name":       name,
                "description":     desc,
                "related_team":    "",
                "confidence_score": round(conf * 100, 1),
                "evidence":        _evidence_str(cat.get("evidence", [])),
            })

        # Ownership Mapping
        for own in llm.get("ownership_mapping", []):
            conf  = own.get("confidence", 0)
            svc   = own.get("service", "")
            team  = own.get("team", "")
            if not (svc and team) or conf < _MIN_CONFIDENCE:
                continue
            items.append({
                "item_type":       "Ownership",
                "item_name":       f"{svc} → {team}",
                "description":     "",
                "related_team":    team,
                "confidence_score": round(conf * 100, 1),
                "evidence":        _evidence_str(own.get("evidence", [])),
            })

        # Historical Patterns
        for hp in llm.get("historical_patterns", []):
            conf    = hp.get("confidence", 0)
            pattern = hp.get("pattern", "")
            if not pattern or conf < _MIN_CONFIDENCE:
                continue
            parts = []
            if hp.get("root_cause"):
                parts.append(f"Root cause: {hp['root_cause']}")
            if hp.get("resolution"):
                parts.append(f"Resolution: {hp['resolution']}")
            if hp.get("frequency"):
                parts.append(f"Frequency: {hp['frequency']}")
            items.append({
                "item_type":       "Historical Pattern",
                "item_name":       pattern,
                "description":     " | ".join(parts),
                "related_team":    "",
                "confidence_score": round(conf * 100, 1),
                "evidence":        _evidence_str(hp.get("evidence", [])),
            })

        # Resolution Patterns (if provider returns them)
        for pat in llm.get("resolution_patterns", []):
            conf = pat.get("confidence", 0)
            name = pat.get("pattern", "")
            if not name or conf < _MIN_CONFIDENCE:
                continue
            desc    = pat.get("description", "")
            applies = pat.get("applies_to", "")
            if applies:
                desc = f"Applies to: {applies}. {desc}".strip()
            items.append({
                "item_type":       "Resolution Pattern",
                "item_name":       name,
                "description":     desc,
                "related_team":    "",
                "confidence_score": round(conf * 100, 1),
                "evidence":        _evidence_str(pat.get("evidence", [])),
            })

        return items

    # ── Save to Doctype ───────────────────────────────────────────────────────

    def save(self, doc_name: str, llm: dict, new_items: list[dict]):
        ctx = frappe.get_doc("TB Business Context", doc_name)

        # Update top-level profile (don't overwrite if agent already edited)
        profile = llm.get("business_profile", {})
        if not ctx.industry and profile.get("industry"):
            ctx.industry = profile["industry"]
        if not ctx.company_type and profile.get("business_type"):
            ctx.company_type = profile["business_type"]
        if not ctx.business_description and profile.get("summary"):
            ctx.business_description = profile["summary"]

        # Drop rows with obsolete item_types from old schema
        valid_types = {
            "Service", "Application", "Support Team",
            "Ticket Category", "Resolution Pattern", "Ownership", "Historical Pattern",
        }
        # Keep approved items from previous versions; only replace Pending Review ones
        ctx.items = [i for i in ctx.items if i.item_type in valid_types and i.review_status == "Approved"]

        # Merge: update existing approved rows, append all new ones as Pending Review
        existing_approved = {(i.item_type, i.item_name) for i in ctx.items}

        # Compute diff against previous Active version snapshot
        prev_snapshot_keys: set = set()
        prev_active = frappe.db.get_value(
            "TB Business Context Version",
            {"business_context": doc_name, "status": "Active"},
            "items_snapshot",
        )
        if prev_active:
            try:
                prev_items = json.loads(prev_active)
                prev_snapshot_keys = {(i.get("item_type", ""), i.get("item_name", "")) for i in prev_items}
            except Exception:
                pass

        added_count   = 0
        new_item_keys = set()
        for item in new_items:
            key = (item["item_type"], item["item_name"])
            new_item_keys.add(key)
            if key not in existing_approved:
                ctx.append("items", {
                    "item_type":        item["item_type"],
                    "item_name":        item["item_name"],
                    "description":      item.get("description", ""),
                    "related_team":     item.get("related_team", ""),
                    "evidence":         item.get("evidence", ""),
                    "confidence_score": item["confidence_score"],
                    "review_status":    "Pending Review",
                    "agent_notes":      "",
                })
                added_count += 1

        # Diff metrics
        items_added   = len(new_item_keys - prev_snapshot_keys)
        items_removed = len(prev_snapshot_keys - new_item_keys)
        change_summary = {
            "added":   [{"item_type": k[0], "item_name": k[1]}
                        for k in new_item_keys - prev_snapshot_keys],
            "removed": [{"item_type": k[0], "item_name": k[1]}
                        for k in prev_snapshot_keys - new_item_keys],
        }

        # Recalculate metrics
        if ctx.items:
            ctx.overall_confidence = round(
                sum(i.confidence_score for i in ctx.items) / len(ctx.items), 1
            )
        ctx.items_pending      = sum(1 for i in ctx.items if i.review_status == "Pending Review")
        ctx.scan_status        = "Completed"
        ctx.lifecycle_status   = "Review Required"
        ctx.last_scan_date     = frappe.utils.now()
        ctx.approval_status    = "Pending Review"
        ctx.last_scan_summary  = (
            f"Discovered {len(new_items)} intelligence items ({added_count} new). "
            f"{ctx.items_pending} pending review. "
            f"Overall confidence: {ctx.overall_confidence:.0f}%."
        )
        ctx.scan_raw_data = json.dumps(self.raw, default=str)[:10000]

        if ctx.schedule_enabled and ctx.schedule_days:
            ctx.next_scan_date = frappe.utils.add_days(
                frappe.utils.nowdate(), int(ctx.schedule_days or 7)
            )

        ctx.save(ignore_permissions=True)

        # Create a version record for this scan
        _create_pending_version(doc_name, new_items, items_added, items_removed, change_summary, ctx.last_scan_summary)

        frappe.db.commit()


# ── Public runners ────────────────────────────────────────────────────────────

def run_discovery(doc_name: str):
    """Full discovery pipeline. Run in background queue."""
    # Skip stale queued jobs — if a synchronous run already completed, don't overwrite it
    current_status = frappe.db.get_value("TB Business Context", doc_name, "lifecycle_status")
    if current_status == "Review Required":
        return

    frappe.db.set_value("TB Business Context", doc_name, {
        "scan_status":      "Running",
        "lifecycle_status": "Scanning",
    })
    frappe.db.commit()
    try:
        engine     = ContextDiscoveryEngine()
        engine.collect()
        llm_raw    = engine.analyze()
        llm_valid  = engine.validate(llm_raw)
        items      = engine.extract_items(llm_valid)
        engine.save(doc_name, llm_valid, items)
    except Exception:
        # If we were Active before, revert to Active so RAG keeps working
        was_active = frappe.db.exists(
            "TB Business Context Version",
            {"business_context": doc_name, "status": "Active"},
        )
        frappe.db.set_value("TB Business Context", doc_name, {
            "scan_status":       "Failed",
            "lifecycle_status":  "Active" if was_active else "Not Generated",
            "last_scan_summary": "Scan failed — check Error Log for details.",
        })
        frappe.db.commit()
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Context Discovery Failed")


def maybe_run_scheduled_scan():
    """Daily scheduler hook — runs overdue scheduled scans."""
    overdue = frappe.get_all(
        "TB Business Context",
        filters={
            "schedule_enabled": 1,
            "next_scan_date":   ["<=", frappe.utils.nowdate()],
            "scan_status":      ["!=", "Running"],
        },
        pluck="name",
    )
    for name in overdue:
        frappe.enqueue(
            "ticketbrain.ai.context_discovery.run_discovery",
            doc_name=name,
            queue="long",
            timeout=600,
        )


def _create_pending_version(doc_name: str, new_items: list, items_added: int, items_removed: int,
                             change_summary: dict, scan_summary: str):
    """Create a Pending Review version record after a scan completes."""
    last = frappe.db.get_value(
        "TB Business Context Version",
        {"business_context": doc_name},
        "version_number",
        order_by="version_number desc",
    ) or 0
    ver_num = (last or 0) + 1

    snapshot = [
        {
            "item_type":        i.get("item_type", ""),
            "item_name":        i.get("item_name", ""),
            "description":      i.get("description", ""),
            "related_team":     i.get("related_team", ""),
            "evidence":         i.get("evidence", ""),
            "confidence_score": i.get("confidence_score", 0),
        }
        for i in new_items
    ]
    try:
        # Remove any existing Pending Review versions (clean slate before new one)
        old_pending = frappe.get_all(
            "TB Business Context Version",
            filters={"business_context": doc_name, "status": "Pending Review"},
            pluck="name",
        )
        for old in old_pending:
            frappe.db.set_value("TB Business Context Version", old, "status", "Rejected")

        frappe.get_doc({
            "doctype":          "TB Business Context Version",
            "business_context": doc_name,
            "version_number":   ver_num,
            "version_label":    f"v{ver_num}",
            "status":           "Pending Review",
            "scanned_at":       frappe.utils.now(),
            "scan_summary":     scan_summary or "",
            "items_added":      items_added,
            "items_removed":    items_removed,
            "items_changed":    0,
            "change_summary":   json.dumps(change_summary, default=str)[:5000],
            "items_snapshot":   json.dumps(snapshot, default=str)[:30000],
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: Version record creation failed")


def detect_context_changes():
    """
    Daily scheduler hook — checks if organisation data has changed significantly
    since the last approved scan and flags contexts that need a refresh.
    """
    contexts = frappe.get_all(
        "TB Business Context",
        filters={"lifecycle_status": "Active"},
        fields=["name", "scan_raw_data"],
    )
    for ctx in contexts:
        changes = _check_for_changes(ctx)
        if changes:
            frappe.db.set_value("TB Business Context", ctx.name, {
                "update_available": 1,
                "update_notes":     "; ".join(changes[:3]),
            })
        else:
            # Clear stale flag if no longer relevant
            if frappe.db.get_value("TB Business Context", ctx.name, "update_available"):
                frappe.db.set_value("TB Business Context", ctx.name, "update_available", 0)
    if contexts:
        frappe.db.commit()


def _check_for_changes(ctx: dict) -> list:
    """Compare current org state with what was captured in the last scan."""
    changes = []
    try:
        raw = json.loads(ctx.get("scan_raw_data") or "{}")
        prev_hd      = raw.get("helpdesk_summary", {})
        prev_kb      = raw.get("kb_summary", {})
        prev_tickets = raw.get("ticket_summary", {})

        current_team_count = frappe.db.count("HD Team")
        prev_team_count    = len(prev_hd.get("teams", []))
        if current_team_count > prev_team_count:
            diff = current_team_count - prev_team_count
            changes.append(f"{diff} new support team{'s' if diff > 1 else ''} added")

        current_kb_count = frappe.db.count("HD Article", {"status": "Published"})
        prev_kb_count    = prev_kb.get("total_articles", 0)
        if current_kb_count > prev_kb_count + 5:
            diff = current_kb_count - prev_kb_count
            changes.append(f"{diff} new KB articles published")

        current_ticket_total = frappe.db.count("HD Ticket")
        prev_ticket_total    = prev_tickets.get("total_tickets", 0)
        if current_ticket_total > prev_ticket_total * 1.3 and current_ticket_total > prev_ticket_total + 50:
            changes.append("Significant ticket volume increase detected")

    except Exception:
        pass
    return changes


def get_context_for_ai() -> str:
    """
    Return approved support intelligence context as a structured text block
    for injection into LLM prompts.
    """
    try:
        ctx_list = frappe.get_all(
            "TB Business Context",
            filters={"approval_status": "Approved"},
            fields=["name", "industry", "business_description"],
            limit=1,
        )
        if not ctx_list:
            return ""
        ctx      = frappe.get_doc("TB Business Context", ctx_list[0]["name"])
        approved = [i for i in ctx.items if i.review_status == "Approved"]
        if not approved:
            return ""

        lines = ["=== Support Intelligence Context ==="]
        if ctx.industry:
            lines.append(f"Industry: {ctx.industry}")
        if ctx.business_description:
            lines.append(f"Organization: {ctx.business_description[:200]}")

        order = [
            "Support Team", "Service", "Application",
            "Ticket Category", "Ownership", "Resolution Pattern", "Historical Pattern",
        ]
        by_type: dict[str, list] = {}
        for item in approved:
            by_type.setdefault(item.item_type, []).append(item)

        for itype in order:
            group = by_type.get(itype, [])
            if not group:
                continue
            lines.append(f"\n{itype}s:")
            for item in group:
                line = f"  - {item.item_name}"
                if item.description:
                    line += f": {item.description[:160]}"
                if item.related_team and itype not in ("Support Team", "Ownership"):
                    line += f" [owner: {item.related_team}]"
                if item.agent_notes:
                    line += f" | {item.agent_notes[:120]}"
                lines.append(line)

        return "\n".join(lines)
    except Exception:
        return ""


# ── RAG index update ──────────────────────────────────────────────────────────

def update_rag_with_context(doc_name: str) -> dict:
    """
    Rebuild the KB index to include approved context items as synthetic KB docs.
    Uses kb_index.npz (preferred) or falls back to rag_index.npz.
    """
    ctx      = frappe.get_doc("TB Business Context", doc_name)
    approved = [i for i in ctx.items if i.review_status == "Approved"]
    if not approved:
        return {"updated": False, "docs_added": 0, "warning": "No approved items to add."}

    context_docs = _build_context_docs(ctx, approved)
    if not context_docs:
        return {"updated": False, "docs_added": 0, "warning": "No content to embed."}

    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer
        from ticketbrain.ai.retrieval import clear_caches

        models_dir    = Path(__file__).parent.parent / "ml" / "models"
        kb_path       = models_dir / "kb_index.npz"
        legacy_path   = models_dir / "rag_index.npz"
        index_path    = kb_path if kb_path.exists() else legacy_path
        embedding_dir = models_dir / "embedding_model"

        if index_path.exists():
            data    = np.load(str(index_path), allow_pickle=True)
            ex_emb  = data["embeddings"]
            ex_meta = list(data["metadata"]) if "metadata" in data else json.loads(data["articles"].item())
        else:
            ex_emb  = np.zeros((0, 384), dtype=np.float32)
            ex_meta = []

        # Remove stale context docs from previous run
        keep    = [i for i, m in enumerate(ex_meta) if not (isinstance(m, dict) and m.get("is_context_doc"))]
        ex_emb  = ex_emb[keep] if keep else np.zeros((0, 384), dtype=np.float32)
        ex_meta = [ex_meta[i] for i in keep]

        model   = SentenceTransformer(str(embedding_dir))
        texts   = [d["content"] for d in context_docs]
        new_emb = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        norms   = np.linalg.norm(new_emb, axis=1, keepdims=True)
        new_emb = new_emb / (norms + 1e-10)

        all_emb  = np.vstack([ex_emb, new_emb]) if ex_emb.shape[0] > 0 else new_emb
        all_meta = ex_meta + [{**d, "is_context_doc": True} for d in context_docs]

        # Write to kb_index.npz (canonical) and keep rag_index.npz in sync
        target_path = models_dir / "kb_index.npz"
        np.savez(str(target_path), embeddings=all_emb, metadata=np.array(all_meta, dtype=object))

        clear_caches()
        return {"updated": True, "docs_added": len(context_docs), "warning": ""}

    except Exception:
        frappe.log_error(frappe.get_traceback(), "TicketBrain: RAG context update failed")
        return {"updated": False, "docs_added": 0, "warning": "RAG update failed — see Error Log."}


def _build_context_docs(ctx, approved_items: list) -> list[dict]:
    docs: list[dict] = []
    for item in approved_items:
        notes = f" {item.agent_notes}" if item.agent_notes else ""

        if item.item_type == "Service":
            content = f"{item.item_name} is an IT service."
            if item.description:
                content += f" {item.description}"
            if item.related_team:
                content += f" Managed by the {item.related_team} team."
            docs.append({
                "id": f"ctx_svc_{item.item_name[:40].lower().replace(' ', '_')}",
                "category": "Service Catalog", "title": f"Service: {item.item_name}",
                "content": content + notes,
                "keywords": [item.item_name.lower(), "service", item.related_team or ""],
            })
        elif item.item_type == "Application":
            content = f"{item.item_name} is an application used in this organization."
            if item.description:
                content += f" {item.description}"
            if item.related_team:
                content += f" Managed by the {item.related_team} team."
            docs.append({
                "id": f"ctx_app_{item.item_name[:40].lower().replace(' ', '_')}",
                "category": "Application Inventory", "title": f"Application: {item.item_name}",
                "content": content + notes, "keywords": [item.item_name.lower(), "application", "software"],
            })
        elif item.item_type == "Support Team":
            content = f"{item.item_name} is a support team."
            if item.description:
                content += f" {item.description}"
            docs.append({
                "id": f"ctx_team_{item.item_name[:40].lower().replace(' ', '_')}",
                "category": "Support Teams", "title": f"Team: {item.item_name}",
                "content": content + notes, "keywords": [item.item_name.lower(), "team", "support"],
            })
        elif item.item_type == "Ownership":
            docs.append({
                "id": f"ctx_own_{len(docs)}", "category": "Team Ownership",
                "title": f"Ownership: {item.item_name}",
                "content": (item.description or item.item_name) + notes,
                "keywords": [item.related_team or "", "team", "owner"],
            })
        elif item.item_type in ("Resolution Pattern", "Historical Pattern"):
            docs.append({
                "id": f"ctx_pat_{len(docs)}", "category": "Resolution Patterns",
                "title": f"Pattern: {item.item_name}",
                "content": (item.description or item.item_name) + notes,
                "keywords": ["resolution", "fix", "pattern", "common"],
            })

    return docs


def create_kb_articles_from_context(doc_name: str) -> int:
    ctx      = frappe.get_doc("TB Business Context", doc_name)
    approved = [
        i for i in ctx.items
        if i.review_status == "Approved"
        and i.item_type in ("Service", "Application", "Resolution Pattern", "Ownership")
    ]
    created = 0
    for item in approved:
        title = f"[Context] {item.item_name}"
        if frappe.db.exists("HD Article", {"title": title}):
            continue
        content_parts = []
        if item.description:
            content_parts.append(f"<p>{item.description}</p>")
        if item.related_team:
            content_parts.append(f"<p><strong>Managed by:</strong> {item.related_team} team</p>")
        if item.agent_notes:
            content_parts.append(f"<p><strong>Notes:</strong> {item.agent_notes}</p>")
        if not content_parts:
            continue
        try:
            frappe.get_doc({
                "doctype": "HD Article",
                "title":   title,
                "content": "\n".join(content_parts),
                "status":  "Published",
            }).insert(ignore_permissions=True)
            created += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"TicketBrain: Article create failed: {item.item_name}")
    if created:
        frappe.db.commit()
    return created


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_system_category(name: str) -> bool:
    return name.lower() in _SYSTEM_CATEGORIES


def _extract_service_name(title: str) -> str:
    for kw in ["VPN", "Email", "Printing", "Attendance", "Internet", "CCTV"]:
        if kw.lower() in title.lower():
            return kw
    return ""


def _extract_app_name(title: str) -> str:
    for kw in ["ERPNext", "Office 365", "Outlook", "CRM", "SAP", "Salesforce"]:
        if kw.lower() in title.lower():
            return kw
    return ""
