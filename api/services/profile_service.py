"""Long-term, distilled user memory (diet, address, taste, frequent items) + a small cache."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from api.models.orm import User, UserProfile, utcnow
from utils.cache import TTLCache

_cache = TTLCache("profile", maxsize=2048, ttl=30)
MAX_FREQUENT = 30


def _loads(value: str | None, default):
    try:
        return json.loads(value) if value else default
    except (TypeError, ValueError):
        return default


def clear_cache() -> None:
    _cache.clear()


def get_profile(db: Session, user_id: int) -> UserProfile:
    profile = db.get(UserProfile, user_id)
    if profile is None:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
        db.commit()
    return profile


def _to_dict(profile: UserProfile) -> dict:
    return {
        "address": profile.address,
        "diet": profile.diet or "any",
        "spice_level": profile.spice_level if profile.spice_level is not None else 1,
        "cuisines": _loads(profile.cuisines, []),
        "frequent_items": _loads(profile.frequent_items, {}),
    }


def profile_dict(db: Session, user: User) -> dict:
    cached = _cache.get(user.id)
    if cached is not None:
        return dict(cached)
    data = _to_dict(get_profile(db, user.id))
    _cache.set(user.id, data)
    return dict(data)


def update_profile(db: Session, user_id: int, **fields) -> dict:
    profile = get_profile(db, user_id)
    if fields.get("address") is not None:
        profile.address = fields["address"].strip() or None
    if fields.get("diet") is not None:
        profile.diet = fields["diet"]
    if fields.get("spice_level") is not None:
        profile.spice_level = int(fields["spice_level"])
    if fields.get("cuisines") is not None:
        cleaned = [c.strip().lower() for c in fields["cuisines"] if c and c.strip()][:10]
        profile.cuisines = json.dumps(cleaned)
    profile.updated_at = utcnow()
    db.commit()
    _cache.delete(user_id)
    return _to_dict(profile)


def bump_frequent_items(db: Session, user_id: int, cart: list[dict]) -> None:
    """Distil an order into 'frequently bought' counts (we never store the conversation)."""
    profile = get_profile(db, user_id)
    counts: dict[str, int] = _loads(profile.frequent_items, {})
    for line in cart:
        counts[line["id"]] = counts.get(line["id"], 0) + int(line.get("qty", 1))
    top = dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:MAX_FREQUENT])
    profile.frequent_items = json.dumps(top)
    profile.updated_at = utcnow()
    db.commit()
    _cache.delete(user_id)
