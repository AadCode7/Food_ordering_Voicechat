"""Optional LLM access through Ollama or an explicitly configured OpenAI-compatible endpoint.

The app defaults to deterministic rules. Hosted provider pricing, free-tier limits, and model
availability are provider-specific and must be checked before enabling the integration.
"""
from __future__ import annotations

import json
import re
import threading
import time

import httpx

from config import settings
from logger import get_logger, log_event, span
from prompt_lib import CHITCHAT_SYSTEM, UNDERSTAND_SYSTEM
from utils.cache import TTLCache
from utils.metrics import metrics
from utils.nlp import INTENTS, normalize

log = get_logger("llm")
_cache = TTLCache("llm", maxsize=1024, ttl=600)
_lock = threading.Lock()
_fail_until = 0.0
_failures = 0


def _endpoint() -> tuple[str, dict] | None:
    if settings.llm_provider == "ollama":
        return settings.ollama_base_url, {}
    if settings.llm_provider == "openai_compatible" and settings.llm_enabled:
        return settings.llm_base_url, {"Authorization": f"Bearer {settings.llm_api_key}"}
    return None


def available() -> bool:
    return settings.llm_enabled and time.monotonic() >= _fail_until


def _mark(ok: bool) -> None:
    """Tiny circuit breaker: after 3 straight failures pause LLM calls for 60 s."""
    global _fail_until, _failures
    with _lock:
        if ok:
            _failures = 0
            return
        _failures += 1
        if _failures >= 3:
            _fail_until = time.monotonic() + 60
            _failures = 0
            log_event(log, "llm_circuit_open", seconds=60)


def chat(messages: list[dict], max_tokens: int | None = None, temperature: float = 0.2) -> str | None:
    ep = _endpoint()
    if ep is None or not available():
        return None
    base, headers = ep
    for model in (settings.llm_model_primary, settings.llm_model_fallback):
        if not model:
            continue
        try:
            with span("llm.call", model=model):
                resp = httpx.post(
                    f"{base}/chat/completions",
                    headers=headers,
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": max_tokens or settings.llm_max_tokens,
                        "temperature": temperature,
                    },
                    timeout=settings.llm_timeout,
                )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            usage = resp.json().get("usage") or {}
            metrics.inc("llm.tokens", int(usage.get("total_tokens", 0)))
            _mark(True)
            return (text or "").strip() or None
        except Exception as exc:
            metrics.inc("llm.errors")
            log_event(log, "llm_call_failed", model=model, error=str(exc)[:200])
            _mark(False)
    return None


def understand(text: str) -> dict | None:
    """Ask the LLM to turn an unclear message into {intent, items, tags}."""
    key = ("u", normalize(text))
    cached = _cache.get(key)
    if cached is not None:
        return cached
    out = chat([{"role": "system", "content": UNDERSTAND_SYSTEM}, {"role": "user", "content": text[:300]}],
               max_tokens=120, temperature=0.0)
    if not out:
        return None
    match = re.search(r"\{.*\}", out, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("intent") not in INTENTS:
        return None
    items = []
    for it in data.get("items") or []:
        if isinstance(it, dict) and isinstance(it.get("name"), str) and it["name"].strip():
            try:
                qty = max(1, min(int(it.get("qty") or 1), 20))
            except (TypeError, ValueError):
                qty = 1
            items.append({"phrase": it["name"].strip()[:60], "qty": qty})
    tags = [t for t in (data.get("tags") or []) if isinstance(t, str)][:5]
    result = {"intent": data["intent"], "items": items, "tags": tags}
    _cache.set(key, result)
    return result


def chitchat(text: str) -> str | None:
    """Short conversational reply. Skipped in peak mode to protect latency."""
    if settings.peak_mode:
        return None
    key = ("c", normalize(text))
    cached = _cache.get(key)
    if cached is not None:
        return cached
    out = chat([{"role": "system", "content": CHITCHAT_SYSTEM}, {"role": "user", "content": text[:300]}],
               max_tokens=80, temperature=0.5)
    if out:
        _cache.set(key, out)
    return out
