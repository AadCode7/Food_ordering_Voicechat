"""Thread-safe local TTL/LRU cache with optional Upstash Redis sharing.

Redis is an optimization, not a dependency: requests fall back to local memory if the
remote cache is not configured, times out, or returns an invalid response.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any

import httpx

from config import settings
from .metrics import metrics

_MISSING = object()
_SHARED_CACHE_NAMES = {"external", "recommend", "menu"}
_REMOTE_TIMEOUT = 0.30


class TTLCache:
    def __init__(self, name: str, maxsize: int = 1024, ttl: float = 60.0) -> None:
        self.name, self.maxsize, self.ttl = name, maxsize, ttl
        self._data: OrderedDict[Any, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def _remote_key(self, key: Any) -> str:
        serialized = json.dumps(key, sort_keys=True, default=str, separators=(",", ":"))
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return f"bitevoice:cache:{self.name}:{digest}"

    def _remote_enabled(self) -> bool:
        return self.name in _SHARED_CACHE_NAMES and settings.shared_cache_enabled

    def _remote_get(self, key: Any) -> Any:
        if not self._remote_enabled():
            return _MISSING
        try:
            response = httpx.post(
                settings.upstash_redis_rest_url,
                headers={"Authorization": f"Bearer {settings.upstash_redis_rest_token}"},
                json=["GET", self._remote_key(key)],
                timeout=_REMOTE_TIMEOUT,
            )
            response.raise_for_status()
            raw = response.json().get("result")
            if raw is None:
                return _MISSING
            return json.loads(raw)
        except Exception:
            metrics.inc(f"cache.{self.name}.shared_error")
            return _MISSING

    def _remote_set(self, key: Any, value: Any, ttl: float) -> None:
        if not self._remote_enabled():
            return
        try:
            serialized = json.dumps(value, separators=(",", ":"))
            response = httpx.post(
                settings.upstash_redis_rest_url,
                headers={"Authorization": f"Bearer {settings.upstash_redis_rest_token}"},
                json=["SET", self._remote_key(key), serialized, "EX", str(max(1, int(ttl)))],
                timeout=_REMOTE_TIMEOUT,
            )
            response.raise_for_status()
        except Exception:
            metrics.inc(f"cache.{self.name}.shared_error")

    def _remote_delete(self, key: Any) -> None:
        if not self._remote_enabled():
            return
        try:
            response = httpx.post(
                settings.upstash_redis_rest_url,
                headers={"Authorization": f"Bearer {settings.upstash_redis_rest_token}"},
                json=["DEL", self._remote_key(key)],
                timeout=_REMOTE_TIMEOUT,
            )
            response.raise_for_status()
        except Exception:
            metrics.inc(f"cache.{self.name}.shared_error")

    def get(self, key: Any, default: Any = None) -> Any:
        now = time.monotonic()
        with self._lock:
            item = self._data.get(key, _MISSING)
            if item is not _MISSING and item[0] >= now:
                self._data.move_to_end(key)
                metrics.inc(f"cache.{self.name}.hit")
                return item[1]
            self._data.pop(key, None)

        value = self._remote_get(key)
        if value is not _MISSING:
            with self._lock:
                self._data[key] = (time.monotonic() + self.ttl, value)
                self._data.move_to_end(key)
                while len(self._data) > self.maxsize:
                    self._data.popitem(last=False)
            metrics.inc(f"cache.{self.name}.hit")
            metrics.inc(f"cache.{self.name}.shared_hit")
            return value

        metrics.inc(f"cache.{self.name}.miss")
        return default

    def set(self, key: Any, value: Any, ttl: float | None = None) -> None:
        lifetime = self.ttl if ttl is None else max(0.0, ttl)
        with self._lock:
            self._data[key] = (time.monotonic() + lifetime, value)
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)
        self._remote_set(key, value, lifetime)

    def delete(self, key: Any) -> None:
        with self._lock:
            self._data.pop(key, None)
        self._remote_delete(key)

    def clear(self) -> None:
        # Deliberately local-only: a cache instance must not flush shared data for all workers.
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
