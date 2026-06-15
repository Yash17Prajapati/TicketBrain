"""
TicketBrain LLM Provider Abstraction

Configure via environment variables:
  TICKETBRAIN_LLM_PROVIDER = gemini | openai | anthropic | openrouter | ollama
  TICKETBRAIN_LLM_MODEL    = override the default model for the chosen provider

API keys (set the one matching your provider):
  GEMINI_API_KEY
  OPENAI_API_KEY
  ANTHROPIC_API_KEY
  OPENROUTER_API_KEY
  OLLAMA_BASE_URL   (default: http://localhost:11434)

Default models:
  gemini      → gemini-2.0-flash
  openai      → gpt-4o-mini
  anthropic   → claude-haiku-4-5-20251001
  openrouter  → google/gemini-2.0-flash
  ollama      → llama3.2
"""

from __future__ import annotations

import os

_PROVIDER_ENV = "TICKETBRAIN_LLM_PROVIDER"
_MODEL_ENV    = "TICKETBRAIN_LLM_MODEL"

_DEFAULT_MODELS: dict[str, str] = {
    "gemini":     "gemini-2.0-flash",
    "openai":     "gpt-4o-mini",
    "anthropic":  "claude-haiku-4-5-20251001",
    "openrouter": "google/gemini-2.0-flash",
    "ollama":     "llama3.2",
}


def _conf(key: str, default: str = "") -> str:
    """Read from env first, then frappe.conf (set via bench set-config)."""
    val = os.environ.get(key, "")
    if val:
        return val
    try:
        import frappe
        return str(frappe.conf.get(key) or default)
    except Exception:
        return default


def get_provider() -> str:
    return _conf(_PROVIDER_ENV, "gemini").lower().strip()


def get_model() -> str:
    override = _conf(_MODEL_ENV, "").strip()
    return override or _DEFAULT_MODELS.get(get_provider(), "gemini-2.0-flash")


def is_available() -> bool:
    provider = get_provider()
    checks = {
        "gemini":     lambda: bool(_conf("GEMINI_API_KEY")),
        "openai":     lambda: bool(_conf("OPENAI_API_KEY")),
        "anthropic":  lambda: bool(_conf("ANTHROPIC_API_KEY")),
        "openrouter": lambda: bool(_conf("OPENROUTER_API_KEY")),
        "ollama":     lambda: True,
    }
    return checks.get(provider, lambda: False)()


def call_llm(prompt: str, *, json_mode: bool = False, timeout: int = 90) -> str:
    """
    Call the configured LLM provider with prompt. Returns response text or "" on failure.
    json_mode=True enables JSON output mode where the provider supports it.
    timeout controls the Ollama wall-clock + socket limit (ignored for cloud providers).
    """
    if not is_available():
        return ""
    provider = get_provider()
    model    = get_model()
    try:
        if provider == "gemini":
            return _call_gemini(prompt, model)
        if provider == "openai":
            return _call_openai(prompt, model, json_mode=json_mode)
        if provider == "anthropic":
            return _call_anthropic(prompt, model)
        if provider == "openrouter":
            return _call_openrouter(prompt, model, json_mode=json_mode)
        if provider == "ollama":
            return _call_ollama(prompt, model, timeout=timeout)
    except Exception:
        try:
            import frappe
            frappe.log_error(frappe.get_traceback(), f"TicketBrain: LLM call failed ({provider}/{model})")
        except Exception:
            pass
    return ""


# ── Provider implementations ──────────────────────────────────────────────────

def _call_gemini(prompt: str, model: str) -> str:
    import google.genai as genai
    client   = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text.strip()


def _call_openai(prompt: str, model: str, *, json_mode: bool = False) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    kwargs: dict = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        **kwargs,
    )
    return (response.choices[0].message.content or "").strip()


def _call_anthropic(prompt: str, model: str) -> str:
    import anthropic
    client  = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def _call_openrouter(prompt: str, model: str, *, json_mode: bool = False) -> str:
    from openai import OpenAI
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
    )
    kwargs: dict = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        **kwargs,
    )
    return (response.choices[0].message.content or "").strip()


def _call_ollama(prompt: str, model: str, *, timeout: int = 90) -> str:
    import json as _json
    import time
    import requests
    base_url = _conf("OLLAMA_BASE_URL", "http://localhost:11434")
    deadline = time.time() + timeout
    resp = requests.post(
        f"{base_url}/api/generate",
        json={"model": model, "prompt": prompt, "stream": True},
        timeout=(10, timeout),  # (connect, per-chunk read)
        stream=True,
    )
    resp.raise_for_status()
    parts: list[str] = []
    for line in resp.iter_lines():
        if time.time() > deadline:
            resp.close()
            raise TimeoutError(f"Ollama response exceeded {timeout}s wall-clock limit")
        if line:
            data = _json.loads(line)
            parts.append(data.get("response", ""))
            if data.get("done"):
                break
    return "".join(parts).strip()
