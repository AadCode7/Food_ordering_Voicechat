"""FastAPI entrypoint. Local: `uvicorn api.index:app --reload`. Vercel serves `app` from here."""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # make top-level packages importable on Vercel
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from api.routes import auth, chat, discover, menu, pages, profile, system  # noqa: E402
from config import settings  # noqa: E402
from database import init_db  # noqa: E402
from logger import get_logger, log_event, request_id_var, setup_logging, setup_telemetry  # noqa: E402
from utils.metrics import metrics  # noqa: E402

setup_logging()
log = get_logger("app")

app = FastAPI(title=settings.app_name, version="1.0.0")

try:
    init_db()
except Exception:  # keep the app up so /api/health can report the problem
    log.exception("init_db failed")

setup_telemetry(app)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request_id_var.set(rid)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("unhandled_error")
        metrics.inc("http.500")
        return JSONResponse({"detail": "Internal server error", "request_id": rid}, status_code=500,
                            headers={"X-Request-ID": rid})
    ms = round((time.perf_counter() - start) * 1000, 1)
    metrics.inc(f"http.{response.status_code}")
    metrics.observe("http.request", ms)
    response.headers["X-Request-ID"] = rid
    if not request.url.path.startswith("/static"):
        log_event(log, "http_request", method=request.method, path=request.url.path,
                  status=response.status_code, duration_ms=ms)
    return response


app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")
for router in (auth.router, profile.router, menu.router, chat.router, discover.router, system.router):
    app.include_router(router, prefix="/api")
app.include_router(pages.router)
