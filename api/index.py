"""FastAPI entrypoint. Local: `uvicorn api.index:app --reload`. Vercel serves `app` from here."""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

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


def restore_vercel_path(scope: dict) -> None:
    """Restore the original URL path after Vercel rewrites it to /api/index.

    vercel.json passes the incoming path in the internal __path query parameter.
    This keeps FastAPI routes and /static assets addressable behind the rewrite.
    """
    if scope.get("path") != "/api/index":
        return

    query_string = scope.get("query_string", b"").decode("latin-1")
    query_items = parse_qsl(query_string, keep_blank_values=True)
    original_paths = [value for key, value in query_items if key == "__path"]
    if not original_paths:
        return

    original_path = original_paths[0]
    # Only accept an absolute local path; never allow an authority or backslash.
    if not original_path.startswith("/") or original_path.startswith("//") or "\\" in original_path:
        return

    scope["path"] = original_path
    scope["raw_path"] = original_path.encode("utf-8")
    remaining = [(key, value) for key, value in query_items if key != "__path"]
    scope["query_string"] = urlencode(remaining, doseq=True).encode("latin-1")


@app.middleware("http")
async def request_logging(request: Request, call_next):
    # Vercel rewrites requests to the Python function URL. Restore the browser's
    # original path before Starlette performs route matching.
    restore_vercel_path(request.scope)

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
