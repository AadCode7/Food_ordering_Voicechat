"""Thread-safe in-process TTL cache (LRU eviction)."""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any

from .metrics import metrics

_MISSING = object()


class TTLCache:
    def __init__(self, name: str, maxsize: int = 1024, ttl: float = 60.0) -> None:
        self.name, self.maxsize, self.ttl = name, maxsize, ttl
        self._data: OrderedDict[Any, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Any, default: Any = None) -> Any:
        with self._lock:
            item = self._data.get(key, _MISSING)
            if item is _MISSING or item[0] < time.monotonic():  # type: ignore[index]
                self._data.pop(key, None)
                metrics.inc(f"cache.{self.name}.miss")
                return default
            self._data.move_to_end(key)
            metrics.inc(f"cache.{self.name}.hit")
            return item[1]  # type: ignore[index]

    def set(self, key: Any, value: Any, ttl: float | None = None) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + (ttl if ttl is not None else self.ttl), value)
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def delete(self, key: Any) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        return len(self._data)
