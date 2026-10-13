import httpx
from types import SimpleNamespace

import utils.cache as cache_module
import utils.rate_limit as rate_limit_module
from utils.cache import TTLCache
from utils.rate_limit import RateLimiter


class FakeRedisResponse:
    def __init__(self, result):
        self.result = result

    def raise_for_status(self):
        return None

    def json(self):
        return {"result": self.result}


def test_shared_cache_is_read_by_another_instance(monkeypatch):
    store = {}
    monkeypatch.setattr(cache_module, "settings", SimpleNamespace(
        shared_cache_enabled=True,
        upstash_redis_rest_url="https://redis.example",
        upstash_redis_rest_token="test-token",
    ))

    def fake_post(url, *, headers, json, timeout):
        command = json[0]
        key = json[1]
        if command == "SET":
            store[key] = json[2]
            return FakeRedisResponse("OK")
        if command == "GET":
            return FakeRedisResponse(store.get(key))
        if command == "DEL":
            store.pop(key, None)
            return FakeRedisResponse(1)
        raise AssertionError(f"Unexpected Redis command: {command}")

    monkeypatch.setattr(cache_module.httpx, "post", fake_post)
    first = TTLCache("external", ttl=30)
    first.set(("query", "pizza"), {"results": [{"name": "Example"}]})
    second = TTLCache("external", ttl=30)
    assert second.get(("query", "pizza")) == {"results": [{"name": "Example"}]}


def test_cache_falls_back_to_local_memory_when_redis_fails(monkeypatch):
    monkeypatch.setattr(cache_module, "settings", SimpleNamespace(
        shared_cache_enabled=True,
        upstash_redis_rest_url="https://redis.example",
        upstash_redis_rest_token="test-token",
    ))

    def fail(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(cache_module.httpx, "post", fail)
    cache = TTLCache("external", ttl=30)
    cache.set("local-key", {"safe": True})
    assert cache.get("local-key") == {"safe": True}


def test_distributed_rate_limit_uses_shared_counter(monkeypatch):
    counts = {}
    monkeypatch.setattr(rate_limit_module, "settings", SimpleNamespace(
        shared_rate_limit_enabled=True,
        upstash_redis_rest_url="https://redis.example",
        upstash_redis_rest_token="test-token",
    ))

    def fake_post(url, *, headers, json, timeout):
        assert json[0] == "EVAL"
        key = json[3]
        counts[key] = counts.get(key, 0) + 1
        return FakeRedisResponse(counts[key])

    monkeypatch.setattr(rate_limit_module.httpx, "post", fake_post)
    limiter = RateLimiter(window_seconds=60)
    assert limiter.allow("user-123", 2) is True
    assert limiter.allow("user-123", 2) is True
    assert limiter.allow("user-123", 2) is False
