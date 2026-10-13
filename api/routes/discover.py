from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, Query

from api.models.orm import User
from api.routes.deps import limit_user
from api.services import external_apis

router = APIRouter(prefix="/discover", tags=["discover"])


@router.get("/places")
def places(q: str = Query(min_length=2, max_length=80), location: str = Query(default="Nashik", max_length=80),
           user: User = Depends(limit_user)):
    with ThreadPoolExecutor(max_workers=2) as pool:
        g = pool.submit(external_apis.google_places, f"{q} in {location}")
        y = pool.submit(external_apis.yelp, q, location)
        return {"google_places": g.result(), "yelp": y.result()}


@router.get("/recipes")
def recipes(q: str = Query(min_length=2, max_length=80), user: User = Depends(limit_user)):
    return external_apis.spoonacular(q)


@router.get("/buzz")
def buzz(q: str = Query(min_length=2, max_length=80), user: User = Depends(limit_user)):
    return external_apis.reddit(q)
