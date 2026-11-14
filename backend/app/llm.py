"""LLM providers for the assistant: Google Gemini (preferred when GEMINI_API_KEY is set) or Anthropic.

* Keys are read from the environment (local_keys.bat) and sent only in request HEADERS, never in a
  URL, so they cannot leak into error messages.
* Gemini model: GEMINI_MODEL if set; otherwise the newest "flash" model that the key can use for
  generateContent, found by listing the models through the API (nothing is guessed).
* Temperature 0: the answer should follow the sources, not be creative.
"""
from __future__ import annotations

import re

import httpx

from . import config

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
_model_cache: dict = {}
PER_CALL_S = 25.0      # one Gemini request
TOTAL_BUDGET_S = 45.0  # all retries and fallbacks together; then the assistant quotes the sources


class LLMError(Exception):
    pass


def _clean(msg: str) -> str:
    return re.sub(r"(key|api_key)=[^\s&'\"]+", r"\1=<hidden>", str(msg)).splitlines()[0][:200]


def gemini_models() -> list[str]:
    """Candidate models, best first: GEMINI_MODEL if set, then current flash models available to the key."""
    if "gemini" in _model_cache:
        return _model_cache["gemini"]
    try:
        r = httpx.get(f"{GEMINI_BASE}/models", params={"pageSize": 200}, timeout=20,
                      headers={"x-goog-api-key": config.GEMINI_API_KEY})
        r.raise_for_status()
        models = r.json().get("models", [])
    except Exception as e:
        raise LLMError(f"could not list Gemini models: {_clean(e)}")
    usable = [m["name"].split("/", 1)[-1] for m in models
              if "generateContent" in m.get("supportedGenerationMethods", [])]
    flash = [m for m in usable if "flash" in m and not re.search(r"(lite|image|tts|audio|live|exp|preview)", m)]
    pick = sorted(flash or usable, key=lambda n: [int(x) if x.isdigit() else 0 for x in re.findall(r"\d+", n)],
                  reverse=True)
    if config.GEMINI_MODEL:
        pick = [config.GEMINI_MODEL] + [m for m in pick if m != config.GEMINI_MODEL]
    if not pick:
        raise LLMError("no Gemini model with generateContent is available for this key")
    _model_cache["gemini"] = pick[:3]
    return _model_cache["gemini"]


def gemini_model() -> str:
    return gemini_models()[0]


def generate(system: str, user: str, max_tokens: int = 500) -> tuple[str, str, str]:
    """Return (text, provider, model). Raises LLMError."""
    if config.GEMINI_API_KEY:
        import time
        d, model, errors = None, None, []
        deadline = time.monotonic() + TOTAL_BUDGET_S  # never keep the user waiting longer than this
        for model in gemini_models():
            for attempt in range(2):  # retry once per model, then fall back to the next model
                left = deadline - time.monotonic()
                if left < 5:
                    break
                try:
                    r = httpx.post(f"{GEMINI_BASE}/models/{model}:generateContent",
                                   timeout=httpx.Timeout(min(PER_CALL_S, left), connect=8),
                                   headers={"x-goog-api-key": config.GEMINI_API_KEY, "content-type": "application/json"},
                                   json={"systemInstruction": {"parts": [{"text": system}]},
                                         "contents": [{"role": "user", "parts": [{"text": user}]}],
                                         "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens}})
                    if r.status_code in (429, 500, 502, 503, 504):
                        raise httpx.HTTPStatusError(f"{r.status_code} from Gemini", request=r.request, response=r)
                    r.raise_for_status()
                    d = r.json()
                    break
                except Exception as e:
                    errors.append(f"{model}: {_clean(e)}")
                    time.sleep(1.0)
            if d is not None or deadline - time.monotonic() < 5:
                break
        if d is None:
            raise LLMError("Gemini request failed: " + " | ".join(errors[-3:]))
        cands = d.get("candidates") or []
        if not cands:
            raise LLMError(f"Gemini returned no answer ({(d.get('promptFeedback') or {}).get('blockReason', 'no reason')})")
        text = "".join(p.get("text", "") for p in (cands[0].get("content") or {}).get("parts", []))
        return text.strip(), "gemini", model
    if config.ANTHROPIC_API_KEY:
        try:
            r = httpx.post("https://api.anthropic.com/v1/messages", timeout=60,
                           headers={"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                                    "content-type": "application/json"},
                           json={"model": config.LLM_MODEL, "max_tokens": max_tokens, "temperature": 0,
                                 "system": system, "messages": [{"role": "user", "content": user}]})
            r.raise_for_status()
        except Exception as e:
            raise LLMError(f"Anthropic request failed: {_clean(e)}")
        text = "".join(b.get("text", "") for b in r.json().get("content", []))
        return text.strip(), "anthropic", config.LLM_MODEL
    raise LLMError("no LLM key configured")
