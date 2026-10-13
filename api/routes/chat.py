from __future__ import annotations

import time
import uuid
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.models.orm import User
from api.models.schemas import ChatIn, ChatOut
from api.routes.deps import get_db, limit_user
from api.services import ordering_graph, profile_service, session_service
from logger import get_logger, log_event

router = APIRouter(prefix="/chat", tags=["chat"])
log = get_logger("chat")
_SID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


@router.post("", response_model=ChatOut)
def chat(body: ChatIn, user: User = Depends(limit_user), db: Session = Depends(get_db)):
    start = time.perf_counter()
    session_id = body.session_id or uuid.uuid4().hex
    state = session_service.load(db, user.id, session_id)
    profile = profile_service.profile_dict(db, user)
    user_ctx = {"id": user.id, "name": user.name, **profile}
    try:
        result = ordering_graph.run_turn(db, user_ctx, state, body.message.strip())
    except Exception:
        log.exception("chat_turn_failed")
        raise HTTPException(500, "Something went wrong while handling your request")
    session_service.save(db, user.id, session_id, result["session"])
    cart = result["session"]["cart"]
    latency = int((time.perf_counter() - start) * 1000)
    log_event(log, "chat_turn", user_id=user.id, intent=result["intent"], source=result["source"], latency_ms=latency)
    return ChatOut(
        reply=result["reply"], intent=result["intent"], source=result["source"], session_id=session_id,
        cart=cart, total=ordering_graph.total(cart), suggestions=result["suggestions"],
        order=result["order"], latency_ms=latency,
    )


@router.get("/cart")
def get_cart(session_id: str = Query(...), user: User = Depends(limit_user), db: Session = Depends(get_db)):
    if not _SID.match(session_id):
        raise HTTPException(422, "Invalid session_id")
    cart = session_service.load(db, user.id, session_id)["cart"]
    return {"cart": cart, "total": ordering_graph.total(cart)}


@router.delete("/session")
def end_session(session_id: str = Query(...), user: User = Depends(limit_user), db: Session = Depends(get_db)):
    if not _SID.match(session_id):
        raise HTTPException(422, "Invalid session_id")
    session_service.delete_session(db, user.id, session_id)
    return {"ok": True}
