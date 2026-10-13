"""Short-lived conversation state (cart, pending confirmation) stored with an expiry.

We deliberately do NOT keep the chat transcript. Only what the next turn needs lives here and
it disappears after SESSION_TTL_MINUTES. Stored in the DB so it survives serverless cold starts.
"""
from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from api.models.orm import SessionState, utcnow
from config import settings


def _key(user_id: int, session_id: str) -> str:
    return f"u{user_id}-{session_id}"[:100]


def default_state() -> dict:
    return {"cart": [], "pending_confirm": False}


def load(db: Session, user_id: int, session_id: str) -> dict:
    row = db.get(SessionState, _key(user_id, session_id))
    if row is None or row.expires_at < utcnow():
        return default_state()
    try:
        data = json.loads(row.data)
    except ValueError:
        return default_state()
    state = default_state()
    state.update(data)
    return state


def save(db: Session, user_id: int, session_id: str, state: dict) -> None:
    now = utcnow()
    db.execute(delete(SessionState).where(SessionState.expires_at < now))  # purge expired rows
    key = _key(user_id, session_id)
    row = db.get(SessionState, key)
    payload = json.dumps({"cart": state.get("cart", []), "pending_confirm": bool(state.get("pending_confirm"))})
    expires = now + timedelta(minutes=settings.session_ttl_minutes)
    if row is None:
        db.add(SessionState(session_key=key, user_id=user_id, data=payload, expires_at=expires))
    else:
        row.data, row.expires_at = payload, expires
    db.commit()


def delete_session(db: Session, user_id: int, session_id: str) -> None:
    db.execute(delete(SessionState).where(SessionState.session_key == _key(user_id, session_id)))
    db.commit()
