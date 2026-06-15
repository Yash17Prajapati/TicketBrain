"""
TicketBrain AI Service — Classifier + RAG Resolution Generator

Architecture:
  Text (subject + description)
        ↓  sentence-transformers embedding (all-MiniLM-L6-v2)
  Logistic Regression classifier (trained on 1800 tickets)
        ↓  category + confidence score
  RAG: cosine similarity search over KB index → top-3 articles
        ↓
  Gemini 2.0 Flash → structured resolution steps
  (falls back to category templates if GEMINI_API_KEY not set)
        ↓
  Structured suggestion dict returned to ticket.py
"""

from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np

# ── Paths ─────────────────────────────────────────────────────────────────────

_MODELS_DIR    = Path(__file__).parent.parent / "ml" / "models"
_EMBEDDING_DIR = _MODELS_DIR / "embedding_model"

CONFIDENCE_THRESHOLD = 0.65

# ── Ticket Type keywords ───────────────────────────────────────────────────────

_TYPE_BUG = {
    "bug", "error", "crash", "broken", "glitch", "defect", "corrupt",
    "not working", "stopped working", "keeps crashing", "unexpected", "wrong output",
}
_TYPE_INCIDENT = {
    "cannot access", "locked out", "outage", "down", "blocked", "attack",
    "suspicious", "infected", "breach", "compromised", "no access",
    "can't login", "cannot login", "system down", "service down",
}
_TYPE_QUESTION = {
    "how to", "how do i", "what is", "what are", "explain", "help me understand",
    "where can i", "is it possible", "can i", "procedure", "policy", "guide",
}

# ── Priority keywords ──────────────────────────────────────────────────────────

_PRIORITY_CRITICAL = {
    "cannot work at all", "completely blocked", "business critical", "data loss",
    "security breach", "system down", "emergency", "production down",
    "all users affected", "revenue impact",
}
_PRIORITY_HIGH = {
    "urgent", "asap", "as soon as possible", "today", "important",
    "blocking my work", "can't meet deadline", "affecting my work",
    "multiple users", "team is blocked", "escalate",
}
_PRIORITY_LOW = {
    "when possible", "low priority", "not urgent", "minor", "small issue",
    "no rush", "whenever", "non critical", "cosmetic",
}

# ── Resolution step templates per category ────────────────────────────────────
# These are used until the RAG layer (FAISS + LLM) is wired in.
# Ordered from most general fix to most specific escalation path.

_CATEGORY_STEPS = {
    "Hardware & Infrastructure": [
        "Restart the affected device first — this resolves most hardware issues caused by temporary software locks or power glitches.",
        "Check all physical connections: power cable, display cable, USB ports, and docking station if used. Reseat any loose connections.",
        "If the device powers on but behaves incorrectly, boot into Safe Mode (hold Shift while restarting on Windows) to rule out software driver conflicts.",
        "Run the built-in hardware diagnostic: most company laptops have a pre-boot diagnostic accessible by pressing F2 or F12 at startup.",
        "If the issue persists, note the asset tag number (sticker on the device) and submit a hardware replacement request — include the asset tag in your ticket.",
    ],
    "Software & Applications": [
        "Close the application completely — right-click the taskbar icon and select 'Close window'. If it is unresponsive, open Task Manager (Ctrl+Shift+Esc) and end the process.",
        "Restart your computer to clear temporary files and reset the application state.",
        "If the application still fails, run the installer repair: Control Panel → Programs → select the application → Change → Repair.",
        "Check for pending software updates via the company software portal — outdated versions are the most common cause of crashes on managed systems.",
        "If the issue remains, collect the exact error message text and the application version (Help → About), then escalate your ticket with these details.",
    ],
    "Network & Connectivity": [
        "Verify your network adapter is enabled: click the network icon in the taskbar → Open Network & Internet Settings → check adapter status.",
        "Run the Windows Network Troubleshooter: Settings → System → Troubleshoot → Other troubleshooters → Internet Connections.",
        "Flush the DNS cache: open Command Prompt as Administrator and run `ipconfig /flushdns` followed by `ipconfig /renew`.",
        "If using a VPN: disconnect, wait 10 seconds, then reconnect. Ensure you are on the correct VPN profile for your location (office vs remote).",
        "If the problem is limited to one application (e.g. a browser but not another), the issue is app-specific rather than network-wide — reinstall or update that application.",
    ],
    "Account & Access": [
        "Confirm you are using your full corporate email as the username (e.g. name@company.com) — not just your first name or display name.",
        "After multiple failed login attempts accounts lock automatically for 30 minutes. Wait and try again, or call the IT helpdesk on extension 100 for an immediate manual unlock.",
        "To reset your password: navigate to the self-service portal at accounts.company.com → 'Forgot Password' → verify your identity via mobile OTP.",
        "If you need access to a new system or shared drive, your line manager must submit an access request via the IT portal — access is provisioned by IT after manager approval, not granted directly.",
    ],
    "Security & Threats": [
        "Do not click any links, open attachments, or reply to the suspicious communication. Isolate the threat before taking any other action.",
        "If this is a suspicious email: forward it as an attachment to security@company.com, then permanently delete it from your inbox and empty your trash.",
        "If you suspect your device has been compromised: disconnect from the network immediately (unplug ethernet and turn off WiFi) and call the IT Security team on the emergency line.",
        "Change passwords for any accounts you believe may have been exposed — start with your corporate account and email, then any external services.",
        "Document the incident with timestamps, what you clicked or received, and any unusual device behaviour — this information is critical for the security team to trace the attack.",
    ],
    "Data & Reports": [
        "Verify the date range, filters, and parameters on your report — incorrect filter selection is the most common cause of missing or wrong data.",
        "Clear your browser cache and cookies (Ctrl+Shift+Delete), then regenerate the report. Cached pages can display stale data from a previous run.",
        "If exporting to Excel produces a blank or corrupted file, export to CSV first — this bypasses formatting issues in the Excel export engine, then open the CSV in Excel.",
        "Cross-check a sample of records against the original source data (individual transactions or entries) to confirm whether the error is in the report logic or in the underlying data.",
        "If source data is genuinely incorrect, raise a data correction request with the relevant department owner with specific examples — do not edit records directly.",
    ],
}

_INFO_PHRASES = {
    "what is", "what are", "how do i", "how to", "explain",
    "clarify", "difference between", "what does", "policy for",
    "procedure", "guideline",
}

_QUICK_FIX_PHRASES = {
    "just restart", "just reboot", "simple fix", "quick fix",
    "how do i restart", "reboot my",
}


# ── Model loading (cached per worker process) ─────────────────────────────────

@lru_cache(maxsize=1)
def _load_models():
    """Load classifier, label encoder, and embedding model once per worker."""
    from sentence_transformers import SentenceTransformer

    classifier    = joblib.load(_MODELS_DIR / "classifier.joblib")
    label_encoder = joblib.load(_MODELS_DIR / "label_encoder.joblib")

    if _EMBEDDING_DIR.exists() and any(_EMBEDDING_DIR.iterdir()):
        embedder = SentenceTransformer(str(_EMBEDDING_DIR))
    else:
        embedder = SentenceTransformer("all-MiniLM-L6-v2")

    return classifier, label_encoder, embedder


# ── Public API ─────────────────────────────────────────────────────────────────

def classify_and_resolve(subject: str, description: str) -> dict:
    """
    Classify a ticket and return a structured resolution suggestion.

    Returns:
        dict with keys: category, confidence_score, resolution_type,
                        steps (list of {step_number, content}),
                        direct_answer, should_escalate, ticket_embedding
    """
    from ticketbrain.ai.rag import search_kb, generate_resolution
    from ticketbrain.ai.retrieval import search_tickets

    classifier, label_encoder, embedder = _load_models()

    text      = f"{subject} — {description}"
    embedding = embedder.encode([text], convert_to_numpy=True)
    emb_1d    = embedding[0]

    proba         = classifier.predict_proba(embedding)[0]
    predicted_idx = int(np.argmax(proba))
    confidence    = float(proba[predicted_idx])
    category      = label_encoder.inverse_transform([predicted_idx])[0]

    should_escalate = confidence < CONFIDENCE_THRESHOLD
    resolution_type = _infer_resolution_type(subject, description)

    # Retrieve from both indexes
    kb_docs         = search_kb(emb_1d)
    similar_tickets = search_tickets(emb_1d, top_k=3)

    llm_steps = generate_resolution(
        subject, description, category, kb_docs,
        similar_tickets=similar_tickets,
        ticket_embedding=emb_1d,
    )

    if llm_steps:
        selected_steps = llm_steps[:1] if resolution_type in ("quick_fix", "information") else llm_steps
    else:
        steps_pool     = _CATEGORY_STEPS.get(category, _CATEGORY_STEPS["Software & Applications"])
        selected_steps = steps_pool[:1] if resolution_type in ("quick_fix", "information") else steps_pool

    steps = [{"step_number": i + 1, "content": s} for i, s in enumerate(selected_steps)]

    return {
        "category":         category,
        "confidence_score": round(confidence, 4),
        "resolution_type":  resolution_type,
        "steps":            steps,
        "direct_answer":    steps[0]["content"] if resolution_type != "step_by_step" else "",
        "should_escalate":  should_escalate,
        "ticket_embedding": emb_1d,   # passed to evaluator to avoid re-encoding
    }


def generate_followup(subject: str, step_content: str, user_message: str, category: str = "") -> str:
    """
    Generate a contextual followup when the user needs more help.
    Queries both KB and ticket indexes for relevant context.
    Falls back to template matching when no LLM is configured.
    """
    from ticketbrain.ai.rag import search_kb, generate_followup as rag_followup
    from ticketbrain.ai.retrieval import search_tickets

    kb_docs         = []
    similar_tickets = []
    embedding       = None
    try:
        _, _, embedder = _load_models()
        query     = f"{subject} {user_message}"
        embedding = embedder.encode([query], convert_to_numpy=True)[0]
        kb_docs   = search_kb(embedding)
        similar_tickets = search_tickets(embedding, top_k=2)
    except Exception:
        pass

    return rag_followup(
        subject=subject,
        current_step=step_content,
        user_message=user_message,
        category=category,
        kb_docs=kb_docs,
        ticket_embedding=embedding,
    )


def classify_ticket_type(subject: str, description: str) -> str:
    """
    Classify ticket as Bug, Incident, or Question based on keywords.
    This is independent of the AI category (Network & Connectivity etc.)
    """
    text = f"{subject} {description}".lower()
    if any(phrase in text for phrase in _TYPE_QUESTION):
        return "Question"
    if any(phrase in text for phrase in _TYPE_BUG):
        return "Bug"
    if any(phrase in text for phrase in _TYPE_INCIDENT):
        return "Incident"
    return "Incident"  # most IT support tickets are incidents


def infer_priority(subject: str, description: str) -> str:
    """
    Infer ticket priority from urgency signals in the text.
    Agents can always override this in the Helpdesk desk view.
    """
    text = f"{subject} {description}".lower()
    if any(phrase in text for phrase in _PRIORITY_CRITICAL):
        return "Critical"
    if any(phrase in text for phrase in _PRIORITY_HIGH):
        return "High"
    if any(phrase in text for phrase in _PRIORITY_LOW):
        return "Low"
    return "Medium"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _infer_resolution_type(subject: str, description: str) -> str:
    text = f"{subject} {description}".lower()
    if any(phrase in text for phrase in _INFO_PHRASES):
        return "information"
    if any(phrase in text for phrase in _QUICK_FIX_PHRASES):
        return "quick_fix"
    return "step_by_step"
