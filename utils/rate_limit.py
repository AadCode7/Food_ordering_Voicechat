"""Rate limiter with optional cross-instance Upstash coordination and local fallback."""
from __future__ import annotations

import hashlib
import threading
import time
from collections import defaultdict, deque

import httpx

from config import settings
from .metrics import metrics

_REMOTE_TIMEOUT = 0.30
_RATE_LIMIT_SCRIPT = (
    "local n=redis.call('INCR',KEYS[1]); "
    "if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]); end; "
    "return n"
)


class RateLimiter:
    def __init__(self, window_seconds: int = 60) -> None:
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _shared_allow(self, key: str, limit: int) -> bool | None:
        if not settings.shared_rate_limit_enabled:
            return None
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        redis_key = f"bitevoice:rate:{digest}:{self.window}"
        try:
            response = httpx.post(
                settings.upstash_redis_rest_url,
                headers={"Authorization": f"Bearer {settings.upstash_redis_rest_token}"},
                json=["EVAL", _RATE_LIMIT_SCRIPT, "1", redis_key, str(self.window)],
                timeout=_REMOTE_TIMEOUT,
            )
            response.raise_for_status()
            count = int(response.json()["result"])
            metrics.inc("rate_limit.shared_check")
            return count <= limit
        except Exception:
            metrics.inc("rate_limit.shared_error")
            return None

    def allow(self, key: str, limit: int) -> bool:
        shared = self._shared_allow(key, limit)
        if shared is not None:
            return shared

        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - self.window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            if len(self._hits) > 20000:
                for k in [k for k, v in self._hits.items() if not v][:5000]:
                    self._hits.pop(k, None)
            return True


limiter = RateLimiter()
