"""
TicketBrain AI Evaluator

Computes 5 quality metrics for every AI response and decides routing:

  Direct Escalate  → confidence below threshold (0.65) — AI can't help, go straight to agent
  Human Review     → confidence OK but another metric fails — agent reviews AI draft
  Auto Send        → ALL metrics pass — post resolution directly to customer

Decision chain (in order):
  1. If should_escalate (confidence < 0.65) → Direct Escalate  (skip all other checks)
  2. If risk_score in (High, Critical)       → Human Review
  3. If classification_confidence < 0.88     → Human Review
  4. If kb_match_score < 0.45               → Human Review
  5. If response_quality_score < 0.75       → Human Review
  6. All passed                             → Auto Send

Metrics
-------
classification_confidence  Classifier softmax probability for predicted category
priority_confidence        Strength of priority keyword signal (0-1)
kb_match_score             Top cosine similarity against KB index (0-1)
response_quality_score     LLM self-judge: does response answer the ticket? (0-1)
risk_score                 Business impact: Low / Medium / High / Critical
"""

from __future__ import annotations
import os
import re

# ── Risk matrix ────────────────────────────────────────────────────────────────

_BASE_RISK = {
    "Security & Threats":       "High",
    "Hardware & Infrastructure": "Medium",
    "Network & Connectivity":    "Medium",
    "Software & Applications":   "Low",
    "Account & Access":          "Low",
    "Data & Reports":            "Low",
}

_RISK_LEVELS = ["Low", "Medium", "High", "Critical"]


def _compute_risk(category: str, priority: str, should_escalate: bool) -> str:
    base = _BASE_RISK.get(category, "Medium")
    idx  = _RISK_LEVELS.index(base)

    if priority == "Critical":
        idx = 3
    elif priority == "High":
        idx = min(idx + 1, 3)
    elif priority == "Low":
        idx = max(idx - 1, 0)

    if should_escalate:
        idx = min(idx + 1, 3)

    return _RISK_LEVELS[idx]


# ── Priority confidence ────────────────────────────────────────────────────────

_PRIORITY_KEYWORDS = {
    "Critical": {
        "cannot work at all", "completely blocked", "business critical", "data loss",
        "security breach", "system down", "emergency", "production down",
        "all users affected", "revenue impact",
    },
    "High": {
        "urgent", "asap", "as soon as possible", "today", "important",
        "blocking my work", "can't meet deadline", "affecting my work",
        "multiple users", "team is blocked", "escalate",
    },
    "Low": {
        "when possible", "low priority", "not urgent", "minor", "small issue",
        "no rush", "whenever", "non critical", "cosmetic",
    },
}


def _priority_confidence(subject: str, description: str, priority: str) -> float:
    text = f"{subject} {description}".lower()
    pool = _PRIORITY_KEYWORDS.get(priority, {})
    if not pool:
        # Medium — default, no strong signals needed
        any_strong = any(
            kw in text
            for kws in _PRIORITY_KEYWORDS.values()
            for kw in kws
        )
        return 0.55 if not any_strong else 0.40

    matched = sum(1 for kw in pool if kw in text)
    return min(0.50 + matched * 0.12, 0.99)


# ── Response quality (LLM-as-judge) ───────────────────────────────────────────

def _response_quality_llm(subject: str, description: str, ai_response_html: str) -> float | None:
    """
    Ask the configured LLM to score how well the AI response addresses the ticket.
    Returns float 0-1, or None if LLM is unavailable.
    """
    from ticketbrain.ai.llm_provider import is_available, call_llm
    if not is_available():
        return None

    plain = re.sub(r"<[^>]+>", " ", ai_response_html).strip()
    prompt = (
        "You are a quality evaluator for IT support responses.\n\n"
        f"TICKET SUBJECT: {subject}\n"
        f"TICKET DESCRIPTION: {description}\n\n"
        f"AI RESPONSE:\n{plain}\n\n"
        "Score how well this response addresses the specific issue described in the ticket.\n"
        "Consider: Is the advice relevant? Is it actionable? Does it match the exact problem?\n"
        "Reply with ONLY a number from 0 to 100. Nothing else."
    )

    try:
        raw   = call_llm(prompt)
        score = float(re.search(r"\d+(?:\.\d+)?", raw).group())
        return min(max(score / 100.0, 0.0), 1.0)
    except Exception:
        return None


def _response_quality_heuristic(steps: list[dict], resolution_type: str) -> float:
    """Fallback when Gemini is not available."""
    if not steps:
        return 0.30
    count = len(steps)
    avg_len = sum(len(s.get("content", "")) for s in steps) / count
    base = 0.60
    if count >= 3:
        base += 0.10
    if avg_len >= 120:
        base += 0.10
    if resolution_type == "step_by_step" and count >= 3:
        base += 0.05
    return min(base, 0.85)


# ── KB match score ─────────────────────────────────────────────────────────────

def _kb_match_score(embedding) -> float:
    """Return the top cosine similarity score against the KB index."""
    try:
        from ticketbrain.ai.retrieval import top_kb_score
        return top_kb_score(embedding)
    except Exception:
        return 0.50


# ── Auto-send decision ─────────────────────────────────────────────────────────

_THRESHOLDS = {
    "classification_confidence": 0.88,
    "kb_match_score":            0.45,   # all-MiniLM-L6-v2 cosine scores peak ~0.55 for good matches
    "response_quality_score":    0.75,
}


def _decide(metrics: dict) -> tuple[str, str]:
    """
    Return (decision, reason) using the sequential evaluation chain.

    Chain (stops at first failure):
      1. Low confidence → Direct Escalate
      2. High/Critical risk → Human Review
      3. Classification confidence < threshold → Human Review
      4. KB match < threshold → Human Review
      5. Response quality < threshold → Human Review
      6. All passed → Auto Send
    """
    # Step 1 — confidence too low, AI cannot help reliably
    if metrics["should_escalate"]:
        conf = int(metrics["classification_confidence"] * 100)
        return (
            "Direct Escalate",
            f"Classification confidence {conf}% is below the 65% threshold — "
            "ticket routed directly to a support agent.",
        )

    # Step 2 — business risk too high for unsupervised AI response
    if metrics["risk_score"] in ("High", "Critical"):
        return (
            "Human Review",
            f"Risk score is {metrics['risk_score']} — agent must review before sending.",
        )

    # Steps 3-5 — check remaining thresholds one by one
    ordered_checks = [
        ("classification_confidence", "Classification confidence"),
        ("kb_match_score",            "Knowledge Match Score"),
        ("response_quality_score",    "Response Quality Score"),
    ]
    for key, label in ordered_checks:
        threshold = _THRESHOLDS[key]
        if metrics[key] < threshold:
            pct = int(metrics[key] * 100)
            req = int(threshold * 100)
            return (
                "Human Review",
                f"{label} {pct}% is below the required {req}% — agent review needed.",
            )

    # Step 6 — all checks passed
    return (
        "Auto Send",
        f"All metrics passed — Classification {int(metrics['classification_confidence']*100)}%, "
        f"KB Match {int(metrics['kb_match_score']*100)}%, "
        f"Quality {int(metrics['response_quality_score']*100)}%, "
        f"Risk {metrics['risk_score']}.",
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def evaluate(
    subject: str,
    description: str,
    classify_result: dict,
    ai_draft_html: str,
    ticket_embedding=None,
    priority: str = "Medium",
) -> dict:
    """
    Evaluate AI response quality and decide routing.

    Parameters
    ----------
    subject, description  : raw ticket text
    classify_result       : dict returned by classify_and_resolve()
    ai_draft_html         : HTML string of the draft response
    ticket_embedding      : numpy array (1D) — reuse from classify step to avoid re-encoding
    priority              : inferred priority string

    Returns
    -------
    dict with keys:
        classification_confidence, priority_confidence, kb_match_score,
        response_quality_score, risk_score, decision, reason
    """
    classification_confidence = classify_result.get("confidence_score", 0.0)
    category      = classify_result.get("category", "")
    steps         = classify_result.get("steps", [])
    resolution_type = classify_result.get("resolution_type", "step_by_step")
    should_escalate = classify_result.get("should_escalate", False)

    p_conf  = _priority_confidence(subject, description, priority)

    kb_score = _kb_match_score(ticket_embedding) if ticket_embedding is not None else 0.50

    rq_score = _response_quality_llm(subject, description, ai_draft_html)
    if rq_score is None:
        rq_score = _response_quality_heuristic(steps, resolution_type)

    risk = _compute_risk(category, priority, should_escalate)

    metrics = {
        "classification_confidence": classification_confidence,
        "priority_confidence":       p_conf,
        "kb_match_score":            kb_score,
        "response_quality_score":    rq_score,
        "risk_score":                risk,
        "should_escalate":           should_escalate,
    }

    decision, reason = _decide(metrics)
    metrics["decision"] = decision
    metrics["reason"]   = reason
    return metrics
