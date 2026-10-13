from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.models.orm import User
from api.routes.deps import get_current_user, get_db
from api.services import menu_service, profile_service, recommend_service

router = APIRouter(tags=["menu"])


@router.get("/menu")
def menu(category: str | None = None, veg_only: bool = False):
    items = menu_service.list_menu(category=category, diet="veg" if veg_only else None)
    return {"categories": menu_service.categories(), "items": items}


@router.get("/recommendations")
def recommendations(
    tags: str = Query(default="", description="comma separated, e.g. spicy,dessert"),
    limit: int = Query(default=5, ge=1, le=10),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = profile_service.profile_dict(db, user)
    tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]
    return {"items": recommend_service.recommend(profile, tag_list, limit=limit)}
