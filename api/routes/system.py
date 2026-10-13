from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.models.orm import User
from api.routes.deps import get_current_user, get_db
from config import settings
from utils.metrics import metrics

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
        "llm_enabled": settings.llm_enabled,
        "llm_provider": settings.llm_provider,
        "peak_mode": settings.peak_mode,
    }


@router.get("/metrics")
def get_metrics(user: User = Depends(get_current_user)):
    return metrics.snapshot()
