"""Sliding-window rate limiter (per process). Protects the LLM and DB during traffic spikes."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, window_seconds: int = 60) -> None:
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - self.window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            if len(self._hits) > 20000:  # keep memory bounded
                for k in [k for k, v in self._hits.items() if not v][:5000]:
                    self._hits.pop(k, None)
            return True


limiter = RateLimiter()
