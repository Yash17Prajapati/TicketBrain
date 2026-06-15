"""
TicketBrain RAG Pipeline

Thin orchestration layer on top of retrieval.py + prompt_builder.py + llm_provider.py.

Architecture:
  Ticket embedding
      ↓
  retrieval.search_kb()       — top-3 KB articles  (kb_index.npz)
  retrieval.search_tickets()  — top-3 similar tickets (ticket_index.npz)
      ↓
  prompt_builder.build_resolution_prompt()  — structured multi-source prompt
      ↓
  llm_provider.call_llm()     — configured provider (Gemini / OpenAI / Anthropic / ...)
      ↓
  Parsed resolution steps returned to service.py

Public API is unchanged so service.py, evaluator.py, and api/ticket.py are unaffected:
  search_kb(embedding, top_k)                      → list[dict]
  generate_resolution(subject, desc, cat, docs)    → list[str] | None
  generate_followup(subject, step, msg, cat, docs) → str
"""

from __future__ import annotations

import json
from typing import Optional

import numpy as np

from ticketbrain.ai import retrieval
from ticketbrain.ai import prompt_builder
from ticketbrain.ai import llm_provider


# ── Public retrieval API (unchanged interface) ─────────────────────────────────

def search_kb(query_embedding: np.ndarray, top_k: int = 3) -> list[dict]:
    """Return top_k KB articles for the query embedding."""
    return retrieval.search_kb(query_embedding, top_k)


# ── Resolution generation ─────────────────────────────────────────────────────

def generate_resolution(
    subject: str,
    description: str,
    category: str,
    docs: list[dict],
    *,
    similar_tickets: Optional[list[dict]] = None,
    ticket_embedding: Optional[np.ndarray] = None,
) -> list[str] | None:
    """
    Generate 3-5 resolution steps using multi-source context.

    docs             — KB articles retrieved by search_kb()
    similar_tickets  — pre-fetched similar tickets (optional; fetched if embedding provided)
    ticket_embedding — used to fetch similar tickets when similar_tickets not passed
    """
    if not llm_provider.is_available():
        return None

    # Fetch similar tickets if not already provided
    if similar_tickets is None and ticket_embedding is not None:
        similar_tickets = retrieval.search_tickets(ticket_embedding, top_k=3)
    elif similar_tickets is None:
        similar_tickets = []

    # Load business context
    try:
        from ticketbrain.ai.context_discovery import get_context_for_ai
        business_context = get_context_for_ai()
    except Exception:
        business_context = ""

    # Retrieve past assignment corrections for similar tickets
    feedback_corrections: list[dict] = []
    if ticket_embedding is not None:
        try:
            feedback_corrections = retrieval.search_feedback(ticket_embedding, top_k=2)
        except Exception:
            pass

    prompt = prompt_builder.build_resolution_prompt(
        subject=subject,
        description=description,
        category=category,
        business_context=business_context,
        kb_articles=docs,
        similar_tickets=similar_tickets,
        feedback_corrections=feedback_corrections,
    )

    raw = llm_provider.call_llm(prompt)
    if not raw:
        return None

    steps = [s.strip() for s in raw.split("\n\n") if s.strip()]
    return steps[:5] if steps else None


# ── Agentic followup ──────────────────────────────────────────────────────────

def generate_followup(
    subject: str,
    current_step: str,
    user_message: str,
    category: str,
    kb_docs: Optional[list[dict]] = None,
    *,
    ticket_embedding: Optional[np.ndarray] = None,
) -> str:
    """
    Generate a contextual followup when the user is stuck.
    Falls back to template logic if the LLM is unavailable.
    """
    if not llm_provider.is_available():
        return _template_followup(user_message, current_step, category)

    similar_tickets: list[dict] = []
    if ticket_embedding is not None:
        similar_tickets = retrieval.search_tickets(ticket_embedding, top_k=2)

    prompt = prompt_builder.build_followup_prompt(
        subject=subject,
        current_step=current_step,
        user_message=user_message,
        category=category,
        kb_articles=kb_docs or [],
        similar_tickets=similar_tickets,
    )

    raw = llm_provider.call_llm(prompt)
    if not raw:
        return _template_followup(user_message, current_step, category)

    try:
        clean  = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        parsed = json.loads(clean)
        response = parsed.get("response", "").strip()
        return response if response else _template_followup(user_message, current_step, category)
    except (json.JSONDecodeError, KeyError):
        if 20 < len(raw) < 800:
            return raw
        return _template_followup(user_message, current_step, category)


# ── Template fallback ─────────────────────────────────────────────────────────

def _template_followup(user_message: str, step_content: str, category: str) -> str:
    from ticketbrain.ai.knowledge_base import KB_ARTICLES
    msg = user_message.lower()

    if any(p in msg for p in ("other solution", "another", "alternative", "different", "something else")):
        alts = [a for a in KB_ARTICLES if a["category"] == category]
        if alts:
            return (
                f"Here is an alternative approach: {alts[-1]['content']} "
                "If this still does not resolve the issue, a support agent will help directly."
            )
        return "A support agent will investigate your specific configuration. Would you like me to escalate?"

    if any(p in msg for p in ("don't understand", "unclear", "how do i", "where", "can't find")):
        return (
            f"Let me clarify that step: {step_content} "
            "If you are unsure where to find a specific menu or setting, reply with exactly "
            "what you see on screen and I will guide you from there."
        )

    if any(p in msg for p in ("already tried", "tried that", "not working", "same problem", "still")):
        alts = [a for a in KB_ARTICLES if a["category"] == category]
        if len(alts) > 1:
            return (
                "Since that step did not resolve it, let's try a different approach: "
                f"{alts[len(alts) // 2]['content']} Please let me know the result."
            )

    if any(p in msg for p in ("error", "message", "it says", "shows", "warning", "code")):
        return (
            "Thank you for that detail. What is the exact text of the error message? "
            "And did this start after a specific action, update, or restart? "
            "That information will help identify the root cause quickly."
        )

    return (
        "Thank you for the update. Could you describe exactly what happens when you try this step? "
        "For example: does anything change on screen, do you receive a message, or does nothing happen? "
        "The more detail you share, the faster we can resolve this."
    )
