from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.models.orm import User, UserProfile
from utils.security import hash_password, verify_password


class EmailTaken(Exception):
    pass


def create_user(db: Session, name: str, email: str, password: str) -> User:
    if db.scalar(select(User).where(User.email == email)):
        raise EmailTaken()
    user = User(name=name, email=email, password_hash=hash_password(password))
    db.add(user)
    try:
        db.flush()
        db.add(UserProfile(user_id=user.id))
        db.commit()
    except IntegrityError:  # race: two signups with the same email
        db.rollback()
        raise EmailTaken()
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email))
    if user and verify_password(password, user.password_hash):
        return user
    return None
