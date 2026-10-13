from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.models.orm import User
from api.models.schemas import ProfileIn, ProfileOut
from api.routes.deps import get_current_user, get_db
from api.services import profile_service

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileOut)
def read_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return profile_service.profile_dict(db, user)


@router.put("", response_model=ProfileOut)
def write_profile(body: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return profile_service.update_profile(db, user.id, **body.model_dump(exclude_unset=True))
