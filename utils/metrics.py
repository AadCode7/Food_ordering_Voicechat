"""Tiny thread-safe counters + latency stats exposed at /api/metrics."""
from __future__ import annotations

import threading
from collections import defaultdict


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._timings: dict[str, list[float]] = {}

    def inc(self, name: str, n: int = 1) -> None:
        with self._lock:
            self._counters[name] += n

    def observe(self, name: str, ms: float) -> None:
        with self._lock:
            t = self._timings.setdefault(name, [0, 0.0, 0.0])
            t[0] += 1
            t[1] += ms
            t[2] = max(t[2], ms)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "timings_ms": {
                    k: {"count": int(v[0]), "avg": round(v[1] / v[0], 2), "max": round(v[2], 2)}
                    for k, v in self._timings.items()
                    if v[0]
                },
            }


metrics = Metrics()
