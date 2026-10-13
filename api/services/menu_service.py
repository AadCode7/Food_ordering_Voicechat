"""Menu loading + fuzzy dish matching.

The menu source is deliberately pluggable: today it reads api/data/menu.json. Later, replace
`_load()` with a scraper/API (e.g. Spoonacular) that returns the same item shape.
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "menu.json"
_STOP = {"the", "some", "a", "an", "of", "with", "extra", "portion", "portions", "plate", "plates",
         "bowl", "bowls", "piece", "pieces", "please", "order", "glass", "cup"}
ACCEPT = 0.7


def _norm_tokens(text: str) -> list[str]:
    tokens = re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()
    out = []
    for tok in tokens:
        if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
            tok = tok[:-1]
        out.append(tok)
    return out


@lru_cache(maxsize=1)
def _load() -> tuple[dict, ...]:
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    items = []
    for it in raw["items"]:
        it = dict(it)
        names = [it["name"], *it.get("aliases", [])]
        it["_names"] = [(" ".join(_norm_tokens(n)), set(_norm_tokens(n))) for n in names]
        items.append(it)
    return tuple(items)


def public(item: dict) -> dict:
    return {k: v for k, v in item.items() if not k.startswith("_")}


def all_items() -> list[dict]:
    return [public(i) for i in _load()]


def get_item(item_id: str) -> dict | None:
    for it in _load():
        if it["id"] == item_id:
            return public(it)
    return None


def list_menu(category: str | None = None, diet: str | None = None) -> list[dict]:
    items = all_items()
    if category:
        items = [i for i in items if i["category"] == category]
    if diet == "veg":
        items = [i for i in items if i["veg"]]
    elif diet == "non-veg":
        items = [i for i in items if not i["veg"]] or items
    return items


def categories() -> list[str]:
    seen: list[str] = []
    for it in _load():
        if it["category"] not in seen:
            seen.append(it["category"])
    return seen


def match_item(phrase: str, diet: str = "any") -> tuple[dict | None, float]:
    """Best menu item for a spoken phrase. Ties prefer diet-compatible, then more popular."""
    ptoks = {t for t in _norm_tokens(phrase) if t not in _STOP}
    if not ptoks:
        return None, 0.0
    pnorm = " ".join(sorted(ptoks))
    best, best_key = None, (0.0, 0, 0.0)
    for it in _load():
        score = 0.0
        for name_norm, name_toks in it["_names"]:
            if ptoks <= name_toks:
                s = 0.8 + 0.2 * len(ptoks) / len(name_toks)
            else:
                jac = len(ptoks & name_toks) / len(ptoks | name_toks)
                ratio = SequenceMatcher(None, pnorm, " ".join(sorted(name_toks))).ratio()
                s = max(jac * 0.9, ratio * 0.95)
            score = max(score, s)
        diet_ok = 0 if (diet == "veg" and not it["veg"]) else 1
        key = (round(score, 3), diet_ok, it["popularity"])
        if key > best_key:
            best, best_key = it, key
    if best is None or best_key[0] < ACCEPT:
        return None, best_key[0]
    return public(best), best_key[0]


def resolve_items(entity_items: list[dict], diet: str = "any") -> tuple[list[tuple[dict, int | None]], list[str]]:
    """Map [{'phrase','qty'}] to [(menu_item, qty)] and a list of phrases we could not find."""
    matched: list[tuple[dict, int | None]] = []
    missing: list[str] = []
    for ent in entity_items:
        item, _ = match_item(ent["phrase"], diet)
        if item:
            matched.append((item, ent.get("qty")))
        else:
            missing.append(ent["phrase"])
    return matched, missing
