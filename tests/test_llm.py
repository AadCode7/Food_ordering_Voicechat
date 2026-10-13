"""LLM path tests with a fake OpenAI-compatible server (no network, no paid model)."""
import json
import uuid

import httpx

from api.services import llm_service


class _Resp:
    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._content}}], "usage": {"total_tokens": 42}}


def _enable(monkeypatch, handler):
    monkeypatch.setattr(llm_service, "_endpoint", lambda: ("http://fake/v1", {}))
    monkeypatch.setattr(llm_service, "available", lambda: True)
    monkeypatch.setattr(httpx, "post", handler)
    llm_service._cache.clear()


def _say(client, headers, text):
    r = client.post("/api/chat", headers=headers, json={"message": text, "session_id": uuid.uuid4().hex})
    assert r.status_code == 200, r.text
    return r.json()


def test_llm_understands_unclear_message(client, auth, monkeypatch):
    seen = []

    def fake(url, **kw):
        seen.append(kw["json"]["model"])
        assert kw["json"]["max_tokens"] <= 120  # token budget is enforced
        return _Resp('Sure! {"intent":"add_item","items":[{"name":"paneer tikka","qty":2}],"tags":[]}')

    _enable(monkeypatch, fake)
    r = _say(client, auth[0], "i fancy that thing with the cottage cheese cubes")
    assert r["source"] == "llm" and r["intent"] == "add_item"
    assert r["cart"][0]["id"] == "paneer-tikka" and r["cart"][0]["qty"] == 2
    assert seen == ["Qwen/Qwen2.5-7B-Instruct"]  # open-source model only


def test_fallback_model_then_graceful_degradation(client, auth, monkeypatch):
    calls = []

    def flaky(url, **kw):
        calls.append(kw["json"]["model"])
        if "Qwen" in kw["json"]["model"]:
            raise httpx.ConnectError("down")
        return _Resp("Happy to help with your food order!")

    _enable(monkeypatch, flaky)
    r = _say(client, auth[0], "how is the weather in paris today")
    assert calls[:2] == ["Qwen/Qwen2.5-7B-Instruct", "mistralai/Mistral-7B-Instruct-v0.3"]
    assert r["intent"] == "chitchat"

    def dead(url, **kw):
        raise httpx.ConnectError("all down")

    _enable(monkeypatch, dead)
    r = _say(client, auth[0], "do you like jazz music honestly")
    assert r["reply"]  # canned reply, no crash




def test_openai_compatible_provider_requires_configuration(monkeypatch):
    from config.settings import load_settings

    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-api-key")
    configured = load_settings()
    assert configured.llm_enabled is True

    monkeypatch.setenv("LLM_API_KEY", "dummy_api_key")
    unconfigured = load_settings()
    assert unconfigured.llm_enabled is False

def test_garbage_llm_output_is_ignored(client, auth, monkeypatch):
    _enable(monkeypatch, lambda url, **kw: _Resp("not json at all"))
    r = _say(client, auth[0], "blorp glorp flibber")
    assert r["intent"] == "chitchat"
