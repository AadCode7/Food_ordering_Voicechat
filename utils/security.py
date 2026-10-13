"""Our own JWT auth: PBKDF2 password hashing + signed HS256 access tokens."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from config import settings

_ITERATIONS = 210_000


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters, salt_b64, hash_b64 = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), base64.b64decode(salt_b64), int(iters)
        )
        return hmac.compare_digest(digest, base64.b64decode(hash_b64))
    except Exception:
        return False


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int | None:
    """Return the user id, or None when the token is invalid/expired."""
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        return int(data["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
