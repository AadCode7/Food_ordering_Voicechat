"""Lightweight food recommender: popularity + personal history + taste + request tags.

Pure Python (no heavy ML dependency) so it runs in microseconds on a serverless function.
"""
from __future__ import annotations

import json

from config import settings
from utils.cache import TTLCache

from . import menu_service

_cache = TTLCache("recommend", maxsize=2048, ttl=60)


def recommend(user: dict, tags: list[str] | None = None, limit: int = 5, exclude: set[str] | None = None) -> list[dict]:
    tags = [t for t in (tags or []) if t]
    exclude = exclude or set()
    diet = user.get("diet", "any")
    freq: dict[str, int] = user.get("frequent_items") or {}
    key = json.dumps(
        [diet, user.get("spice_level", 1), sorted(user.get("cuisines") or []),
         sorted(freq.items()), sorted(tags), limit, sorted(exclude)],
        default=str,
    )
    cached = _cache.get(key)
    if cached is not None:
        return cached

    max_count = max(freq.values()) if freq else 0
    cuisines = set(user.get("cuisines") or [])
    spice = user.get("spice_level", 1)
    scored: list[tuple[float, dict]] = []
    for item in menu_service.list_menu(diet=diet):
        if item["id"] in exclude:
            continue
        freq_score = freq.get(item["id"], 0) / max_count if max_count else 0.0
        item_tags = set(item["tags"]) | {item["category"], item["cuisine"]}
        tag_score = len(set(tags) & item_tags) / len(tags) if tags else 0.0
        score = (
            0.30 * item["popularity"]
            + 0.30 * freq_score
            + 0.15 * (1.0 if item["cuisine"] in cuisines else 0.0)
            + 0.10 * (1 - abs(item["spice"] - spice) / 3)
            + (0.45 * tag_score if tags else 0.0)
        )
        if tags and tag_score == 0:
            score *= 0.4
        if freq_score > 0:
            reason = "You order this often"
        elif tags and tag_score > 0:
            reason = "Matches " + ", ".join(sorted(set(tags) & item_tags))
        else:
            reason = "Popular pick"
        scored.append((score, {
            "id": item["id"], "name": item["name"], "price": item["price"],
            "veg": item["veg"], "category": item["category"], "reason": reason,
        }))
    scored.sort(key=lambda s: s[0], reverse=True)
    result = [entry for _, entry in scored[:limit]]
    _cache.set(key, result, ttl=settings.effective_cache_ttl if not freq else 60)
    return result
