"""
TicketBrain Prompt Builder

Assembles structured multi-source prompts for every LLM call.
Each builder is a pure function — no I/O, no side effects.

Sources injected (in order of appearance in the prompt):
  1. Business Context   — from TB Business Context (text block)
  2. Similar Tickets    — from ticket_index (resolved historical tickets)
  3. KB Articles        — from kb_index (knowledge base)
  4. Current Ticket     — subject + description

Keeping sources in separate, clearly labelled blocks lets the LLM reason
about each independently and cite them in its response.
"""

from __future__ import annotations


# ── Resolution prompt ─────────────────────────────────────────────────────────

def build_resolution_prompt(
    subject: str,
    description: str,
    category: str,
    business_context: str,
    kb_articles: list[dict],
    similar_tickets: list[dict],
    feedback_corrections: list[dict] | None = None,
) -> str:
    """
    Prompt for generating 3-5 resolution steps for a new ticket.
    """
    parts: list[str] = [
        f'You are an IT support assistant. A user has raised a ticket in the category "{category}".\n',
    ]

    if business_context:
        parts.append(f"ORGANIZATION CONTEXT:\n{business_context}\n")

    parts.append(f"CURRENT TICKET\nSubject: {subject}\nDescription: {description or '(no description provided)'}\n")

    if similar_tickets:
        parts.append("SIMILAR RESOLVED TICKETS (learn from these resolutions):")
        for t in similar_tickets[:3]:
            if not t.get("resolution"):
                continue
            sim_pct = int(t.get("_similarity", 0) * 100)
            cat     = t.get("category", "Unknown")
            res     = t["resolution"][:300]
            parts.append(f"  [{sim_pct}% match | {cat}] {res}")
        parts.append("")

    if kb_articles:
        parts.append("RELEVANT KNOWLEDGE BASE ARTICLES:")
        for doc in kb_articles[:3]:
            title   = doc.get("title", "KB Article")
            content = doc.get("content", "")[:400]
            parts.append(f"[{title}]\n{content}")
        parts.append("")

    if feedback_corrections:
        parts.append("PREVIOUS AI ASSIGNMENT CORRECTIONS (agent-verified — use these to avoid the same mistakes):")
        for fb in feedback_corrections[:3]:
            sim_pct   = int(fb.get("_similarity", 0) * 100)
            ai_cat    = fb.get("ai_category", "?")
            human_cat = fb.get("human_category", "?")
            ai_team   = fb.get("ai_team", "?")
            human_team = fb.get("human_team", "?")
            reason    = fb.get("correction_reason", "")
            subj      = fb.get("ticket_subject", "")
            parts.append(
                f"  [{sim_pct}% match] Ticket: \"{subj}\"\n"
                f"    AI predicted: category={ai_cat}, team={ai_team}\n"
                f"    Agent corrected to: category={human_cat}, team={human_team}\n"
                f"    Reason: {reason}"
            )
        parts.append("")

    parts.append(
        "Generate exactly 3 to 5 concrete, actionable resolution steps for this user.\n"
        "Rules:\n"
        "- Each step must be a single self-contained instruction the user can follow right now.\n"
        "- Write for a non-technical end user — spell out exactly where to click.\n"
        "- Do NOT say 'contact IT' or 'raise a ticket' — the user is already in a support ticket.\n"
        "- Do NOT use markdown headers, bullets, or numbering — return plain text steps.\n"
        "- Separate each step with a single blank line.\n"
        "- Output ONLY the steps, nothing else."
    )

    return "\n".join(parts)


# ── Followup prompt ───────────────────────────────────────────────────────────

_FOLLOWUP_SYSTEM = (
    "You are a helpful IT support assistant inside a ticket system.\n"
    "The user is working through a step-by-step resolution guide and needs more help.\n"
    "Decide the best next action and respond with ONLY this JSON:\n"
    '{"action": "<clarify|suggest_alternative|provide_next_step|recommend_escalation>", '
    '"response": "<your response — plain text, no markdown>"}\n\n'
    "Action meanings:\n"
    "  clarify             — rephrase the current step more clearly\n"
    "  suggest_alternative — user tried it, didn't work — give a different approach\n"
    "  provide_next_step   — guide them to the next logical action\n"
    "  recommend_escalation — the issue needs a human agent\n\n"
    "Tone: professional, concise, empathetic. Never say 'I am an AI'."
)


def build_followup_prompt(
    subject: str,
    current_step: str,
    user_message: str,
    category: str,
    kb_articles: list[dict],
    similar_tickets: list[dict],
) -> str:
    """
    Prompt for generating an agentic followup when a user is stuck.
    """
    parts: list[str] = [
        _FOLLOWUP_SYSTEM,
        f"\nTICKET: {subject} (Category: {category})",
        f"CURRENT STEP THE USER IS ON: {current_step}",
        f"USER'S MESSAGE: {user_message}",
    ]

    if kb_articles:
        kb_block = "\n\n".join(
            f"[{d.get('title','KB')}]\n{d.get('content','')[:300]}"
            for d in kb_articles[:2]
        )
        parts.append(f"\nKNOWLEDGE BASE:\n{kb_block}")

    if similar_tickets:
        res_lines = [
            f"  - {t['resolution'][:200]}"
            for t in similar_tickets[:2]
            if t.get("resolution")
        ]
        if res_lines:
            parts.append("\nSIMILAR RESOLVED TICKETS:\n" + "\n".join(res_lines))

    parts.append("\nRespond with the JSON object only.")
    return "\n".join(parts)


# ── Classification assist prompt ──────────────────────────────────────────────

def build_classify_prompt(
    subject: str,
    description: str,
    business_context: str,
    similar_tickets: list[dict],
    categories: list[str],
) -> str:
    """
    LLM-assisted classification when the classifier confidence is borderline.
    Returns JSON: {"category": "...", "confidence": 0.0, "reasoning": "..."}
    """
    cat_list = "\n".join(f"  - {c}" for c in categories)
    parts: list[str] = [
        "You are an IT support ticket classifier.",
        f"\nAVAILABLE CATEGORIES:\n{cat_list}",
    ]

    if business_context:
        parts.append(f"\nORGANIZATION CONTEXT:\n{business_context}")

    if similar_tickets:
        lines = [
            f"  [{t.get('category','?')}] {t.get('subject','')[:100]}"
            for t in similar_tickets[:3]
        ]
        parts.append("\nSIMILAR HISTORICAL TICKETS:\n" + "\n".join(lines))

    parts += [
        f"\nTICKET SUBJECT: {subject}",
        f"TICKET DESCRIPTION: {description or '(none)'}",
        '\nRespond with ONLY this JSON (no other text):\n'
        '{"category": "<one of the categories above>", "confidence": 0.0, "reasoning": "<one sentence>"}',
    ]
    return "\n".join(parts)


# ── Context discovery prompt ──────────────────────────────────────────────────

def build_discovery_prompt(summaries: dict) -> str:
    """
    Prompt for the context discovery engine.
    summaries is a dict of pre-aggregated data (never raw ERP records).
    """
    import json as _json

    return f"""You are a Support Intelligence Analyzer for TicketBrain.

Your only goal is to extract information that helps an AI system:
  1. Classify IT support tickets accurately
  2. Route tickets to the right team
  3. Retrieve relevant knowledge
  4. Suggest resolutions

You MUST NOT generate organizational reports or business documentation.

---

## Input Summaries

{_json.dumps(summaries, indent=2, default=str)}

---

## Taxonomy Rules (STRICT)

### business_profile
  Industry and company type ONLY.
  Never put support data here.

### support_teams
  ONLY teams with EVIDENCE from ticket assignments or resolution history.
  If no ticket evidence exists, do NOT include the team.
  Never classify an HD Team as a Support Team based solely on its name.

### ticket_categories
  Issue classification labels only.
  Examples: Password Reset, VPN Access, Printer Issues, ERP Login.
  NEVER include: Network & Connectivity, Hardware & Infrastructure, Security & Threats.
  Those are TicketBrain system categories — do not rediscover them.

### services
  Things end users consume or request.
  Examples: VPN, Email, Internet, Printing, Attendance, ERP Access, CCTV.
  NEVER include: category names, team names, department names.

### applications
  Software systems. Examples: ERPNext, Office 365, Outlook, CRM.
  NEVER include: category names, service names, team names.

### ownership_mapping
  ONLY create a mapping when evidence exists (ticket assignments, KB articles).
  Format: {{"service": "VPN", "team": "Network Team", "evidence": ["145 tickets assigned to Network Team"]}}
  If ownership is unknown, omit the mapping entirely.

### historical_patterns
  Common issue-resolution pairs discovered from ticket history.
  Must be specific (e.g., "VPN fails after password reset → Sync AD credentials")
  Not generic (e.g., "Various end-user issues").

---

## Evidence Rules

Every item MUST include an evidence array.
Evidence must cite concrete data: ticket counts, KB article counts, team assignments.
If you cannot cite evidence, DO NOT include the item.

Bad: {{"name": "VPN", "evidence": ["Commonly used"]}}
Good: {{"name": "VPN", "evidence": ["145 historical tickets mention VPN", "12 KB articles on VPN"]}}

---

## Confidence Rules

>0.85 = strong evidence (multiple ticket counts + KB articles + team assignments)
0.60–0.85 = reasonable inference (some ticket evidence)
<0.60 = omit entirely — do not include weak or guessed items

---

## Output Format

Return ONLY valid JSON — no preamble, no markdown fences.

{{
  "business_profile": {{
    "industry": "<string or empty>",
    "business_type": "<SMB|Enterprise|Startup|NGO|Government or empty>",
    "summary": "<one sentence or empty>"
  }},
  "support_teams": [
    {{
      "name": "...",
      "description": "...",
      "confidence": 0.0,
      "evidence": ["...", "..."]
    }}
  ],
  "ticket_categories": [
    {{
      "name": "...",
      "description": "...",
      "frequency": "high|medium|low",
      "confidence": 0.0,
      "evidence": ["..."]
    }}
  ],
  "services": [
    {{
      "name": "...",
      "description": "...",
      "owner_team": "...",
      "confidence": 0.0,
      "evidence": ["..."]
    }}
  ],
  "applications": [
    {{
      "name": "...",
      "description": "...",
      "owner_team": "...",
      "confidence": 0.0,
      "evidence": ["..."]
    }}
  ],
  "ownership_mapping": [
    {{
      "service": "...",
      "team": "...",
      "confidence": 0.0,
      "evidence": ["..."]
    }}
  ],
  "historical_patterns": [
    {{
      "pattern": "...",
      "root_cause": "...",
      "resolution": "...",
      "frequency": "high|medium|low",
      "confidence": 0.0,
      "evidence": ["..."]
    }}
  ]
}}
"""
