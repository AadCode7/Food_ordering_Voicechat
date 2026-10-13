from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.models.orm import User
from api.models.schemas import SignInIn, SignUpIn, TokenOut, UserOut
from api.routes.deps import get_current_user, get_db, limit_auth
from api.services import auth_service
from logger import get_logger, log_event
from utils.metrics import metrics
from utils.security import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger("auth")


def _token(user: User) -> TokenOut:
    return TokenOut(access_token=create_access_token(user.id), user=UserOut(id=user.id, name=user.name, email=user.email))


@router.post("/signup", response_model=TokenOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(limit_auth)])
def signup(body: SignUpIn, db: Session = Depends(get_db)):
    try:
        user = auth_service.create_user(db, body.name, body.email, body.password)
    except auth_service.EmailTaken:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    metrics.inc("auth.signup")
    log_event(log, "signup", user_id=user.id)
    return _token(user)


@router.post("/signin", response_model=TokenOut, dependencies=[Depends(limit_auth)])
def signin(body: SignInIn, db: Session = Depends(get_db)):
    user = auth_service.authenticate(db, body.email, body.password)
    if user is None:
        metrics.inc("auth.signin_failed")
        log_event(log, "signin_failed")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    metrics.inc("auth.signin")
    log_event(log, "signin", user_id=user.id)
    return _token(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut(id=user.id, name=user.name, email=user.email)
