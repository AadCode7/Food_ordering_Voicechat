from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from api.models.orm import User
from config import settings
from database import SessionLocal
from utils.rate_limit import limiter
from utils.security import decode_access_token

bearer = HTTPBearer(auto_error=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    if creds is None:
        raise unauthorized
    user_id = decode_access_token(creds.credentials)
    if user_id is None:
        raise unauthorized
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


def limit_auth(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    if not limiter.allow(f"auth:{ip}", settings.auth_rate_limit_per_min):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Please wait a minute.")


def limit_user(user: User = Depends(get_current_user)) -> User:
    if not limiter.allow(f"user:{user.id}", settings.rate_limit_per_min):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "You're going too fast. Please wait a moment.")
    return user
