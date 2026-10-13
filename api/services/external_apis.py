"""External discovery APIs: Google Places, Yelp Fusion, Spoonacular, Reddit.

Every call is cached, time-limited and fails soft: with placeholder ("dummy") keys a source simply
reports available=False, so nothing here can break ordering.
"""
from __future__ import annotations

import time

import httpx

from config import is_real_key, settings
from logger import get_logger, log_event, span
from utils.cache import TTLCache

log = get_logger("external")
_cache = TTLCache("external", maxsize=512, ttl=300)
_reddit_token: dict = {"value": None, "exp": 0.0}
TIMEOUT = 6.0


def _off(source: str, reason: str = "API key not configured") -> dict:
    return {"source": source, "available": False, "reason": reason, "results": []}


def _cached(key: tuple, source: str, fn):
    hit = _cache.get(key)
    if hit is not None:
        return hit
    try:
        with span(f"external.{source}"):
            data = {"source": source, "available": True, "results": fn()}
    except Exception as exc:
        log_event(log, "external_call_failed", source=source, error=str(exc)[:200])
        return _off(source, "Upstream service error")
    _cache.set(key, data, ttl=settings.effective_cache_ttl)
    return data


def google_places(query: str, limit: int = 5) -> dict:
    if not is_real_key(settings.google_places_api_key):
        return _off("google_places")

    def run():
        r = httpx.post(
            "https://places.googleapis.com/v1/places:searchText",
            headers={
                "X-Goog-Api-Key": settings.google_places_api_key,
                "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating",
            },
            json={"textQuery": query, "maxResultCount": limit},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return [
            {"name": p.get("displayName", {}).get("text"), "address": p.get("formattedAddress"), "rating": p.get("rating")}
            for p in r.json().get("places", [])
        ]

    return _cached(("g", query, limit), "google_places", run)


def yelp(term: str, location: str, limit: int = 5) -> dict:
    if not is_real_key(settings.yelp_api_key):
        return _off("yelp")

    def run():
        r = httpx.get(
            "https://api.yelp.com/v3/businesses/search",
            headers={"Authorization": f"Bearer {settings.yelp_api_key}"},
            params={"term": term, "location": location, "limit": limit},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return [
            {"name": b.get("name"), "rating": b.get("rating"), "price": b.get("price"),
             "address": ", ".join(b.get("location", {}).get("display_address", []))}
            for b in r.json().get("businesses", [])
        ]

    return _cached(("y", term, location, limit), "yelp", run)


def spoonacular(query: str, limit: int = 5) -> dict:
    if not is_real_key(settings.spoonacular_api_key):
        return _off("spoonacular")

    def run():
        r = httpx.get(
            "https://api.spoonacular.com/recipes/complexSearch",
            params={"query": query, "number": limit, "apiKey": settings.spoonacular_api_key},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return [{"id": x.get("id"), "title": x.get("title"), "image": x.get("image")} for x in r.json().get("results", [])]

    return _cached(("s", query, limit), "spoonacular", run)


def _reddit_access_token() -> str:
    if _reddit_token["value"] and _reddit_token["exp"] > time.time() + 30:
        return _reddit_token["value"]
    r = httpx.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=(settings.reddit_client_id, settings.reddit_client_secret),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": settings.reddit_user_agent},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    body = r.json()
    _reddit_token.update(value=body["access_token"], exp=time.time() + int(body.get("expires_in", 3600)))
    return _reddit_token["value"]


def reddit(query: str, subreddit: str = "IndianFood", limit: int = 5) -> dict:
    if not (is_real_key(settings.reddit_client_id) and is_real_key(settings.reddit_client_secret)):
        return _off("reddit")

    def run():
        token = _reddit_access_token()
        r = httpx.get(
            f"https://oauth.reddit.com/r/{subreddit}/search",
            params={"q": query, "restrict_sr": 1, "limit": limit, "sort": "top", "t": "year"},
            headers={"Authorization": f"Bearer {token}", "User-Agent": settings.reddit_user_agent},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return [
            {"title": c["data"].get("title"), "score": c["data"].get("score"),
             "url": "https://www.reddit.com" + c["data"].get("permalink", "")}
            for c in r.json().get("data", {}).get("children", [])
        ]

    return _cached(("r", query, subreddit, limit), "reddit", run)
