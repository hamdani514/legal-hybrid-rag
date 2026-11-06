"""
FastAPI entry point: lifespan (DB, model warm-up), routers, and route protection.

Route protection: api_guard (app/api/security.py) runs before every route in the
application. A route needs a valid token unless it is listed in PUBLIC_ROUTES
there, so a new route is protected without anyone remembering to protect it.
"""

import os
from pathlib import Path
from contextlib import asynccontextmanager
import logging

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.payments import router as payments_router
from app.api.embedding_routes import router as embedding_router
from app.api.routes.query import router as query_router
from app.api.security import (
    RateLimitExceeded,
    api_guard,
    check_security_config,
)
from app.database import connect_db, close_db, db
from app.config import settings

# ----------------------------
# Logging setup
# ----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("legal-rag")


# ----------------------------
# Lifespan (startup/shutdown)
# ----------------------------
def _warn_about_deployment() -> None:
    """Problems that do not stop the app but would hurt real users: loud in the log."""
    backend = Path(__file__).resolve().parent
    lexical = Path(settings.LEXICAL_DB_PATH or backend / "lexical.db")
    if not lexical.exists():
        logger.error(f"Keyword search index missing at {lexical}: search will miss results. Copy lexical.db in.")
    if not (backend / "chroma_db").exists():
        logger.error("Vector store missing at backend/chroma_db: search will find nothing. Copy chroma_db in.")
    if "localhost" in (settings.FRONTEND_URL or "") or "127.0.0.1" in (settings.FRONTEND_URL or ""):
        logger.warning(f"FRONTEND_URL is {settings.FRONTEND_URL}: links in emails point to this machine. "
                       "Set it to the site's public address in production.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting application...")

    # Refuses to start with a weak JWT_SECRET.
    check_security_config()
    _warn_about_deployment()

    try:
        logger.info("🔌 Connecting to database...")
        await connect_db()
        logger.info("✅ Database connection initialized successfully")

        # Initialize MongoDB indexes for embeddings
        from app.database.mongodb import init_mongodb_indexes
        await init_mongodb_indexes()
        from app.api.throttle import ensure_indexes as _throttle_indexes
        await _throttle_indexes()

        # Initialize Beanie ODM and compound unique indexes
        from beanie import init_beanie
        from app.models.user import User
        from app.models.chat import Chat, Message
        from app.models.blog import Blog

        await init_beanie(
            database=db.database,
            document_models=[User, Chat, Message, Blog],
        )

        conversations = (
            Chat.get_pymongo_collection()
            if hasattr(Chat, "get_pymongo_collection")
            else Chat.get_motor_collection()
        )
        await conversations.create_index(
            [("userId", 1), ("slug", 1)],
            unique=True,
            name="userId_slug_unique",
        )
        logger.info("✅ Beanie initialized, unique compound index (userId, slug) created")

        # Optional real ping check
        if db.client:
            try:
                await db.client.admin.command("ping")
                logger.info("🏓 MongoDB ping successful")
            except Exception as e:
                logger.error(f"❌ MongoDB ping failed: {e}")

    except Exception as e:
        logger.exception(f"❌ Fatal error during DB startup: {e}")
        raise e

    # Warm the retrieval models in the background. Both load lazily, so the
    # first search after every start used to pay ~15s of model loading — the
    # one search a demo audience is guaranteed to watch. Run off the event loop
    # so the server accepts requests immediately; a failure here only means the
    # first search loads them itself, as before.
    def _warm_models() -> None:
        import time

        started = time.perf_counter()
        try:
            from app.embeddings.embedding_generator import EmbeddingGenerator
            from app.retrieval.reranker import Reranker

            EmbeddingGenerator().model.encode("warm-up", normalize_embeddings=True)
            Reranker().score("warm-up", ["warm-up"])
            logger.info(f"🔥 Retrieval models warm in {time.perf_counter() - started:.1f}s")
        except Exception as e:
            logger.warning(f"Model warm-up skipped: {e}")

    import asyncio

    async def _warm() -> None:
        await asyncio.to_thread(_warm_models)
        # Then one throwaway query through the v2 pipeline, on this event loop,
        # so its one-off setup (lexical index, exact-match table, card and root
        # caches, the motor client exact match binds to) is also paid here.
        # No LLM calls: the analyzer and judge are off by default, and
        # retrieve_v2 does not record queries.
        try:
            
            if getattr(settings, "USE_V2_PIPELINE", False):
                from app.retrieval.pipeline_v2 import retrieve_v2

                await retrieve_v2("warm-up query", top_k_judgments=1)
                logger.info("🔥 Pipeline v2 warm")
        except Exception as e:
            logger.warning(f"Pipeline warm-up skipped: {e}")

    app.state.warmup = asyncio.create_task(_warm())

    # Start background subscription expiration scheduler
    try:
        from scheduled_tasks import start_scheduler, stop_scheduler
        start_scheduler()
    except Exception as e:
        logger.warning(f"Could not start background scheduler: {e}")

    yield

    logger.info("🛑 Shutting down application...")
    try:
        from scheduled_tasks import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    try:
        await close_db()
        logger.info("✅ Database connection closed")
    except Exception as e:
        logger.exception(f"⚠️ Error during shutdown: {e}")


# ----------------------------
# FastAPI app
# ----------------------------
from fastapi.middleware.cors import CORSMiddleware

from app.monitoring import setup_monitoring, unhandled_error

setup_monitoring()
app = FastAPI(lifespan=lifespan, dependencies=[Depends(api_guard)])
# Anything no route handled: the full error to the log (and Sentry), a plain
# sentence to the user.
app.add_exception_handler(Exception, unhandled_error)

def _allowed_origins() -> list[str]:
    """Sites allowed to call the API from a browser: the app's own address(es).

    In production the backend serves the frontend itself (same site), and in
    development the Vite proxy makes it the same site too, so cross-site calls are
    never needed by the app. Any other website is refused by the browser.
    """
    raw = [settings.FRONTEND_URL or ""] + (settings.FRONTEND_ORIGINS or "").split(",")
    return sorted({o.strip().rstrip("/") for o in raw if o.strip()})


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    # Sign-in travels in the Authorization header, never in cookies.
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


def _inline_script_hashes(index_file: Path) -> list[str]:
    """CSP hashes of the inline <script> blocks in the built index.html (the
    scroll-to-top and loading-skeleton scripts), so they run and nothing else does."""
    import base64
    import hashlib
    import re as _re

    try:
        html = index_file.read_text(encoding="utf-8")
    except OSError:
        return []
    return [
        "'sha256-" + base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode() + "'"
        for body in _re.findall(r"<script>(.*?)</script>", html, flags=_re.S)
    ]


def _content_security_policy(index_file: Path) -> str:
    google = "https://accounts.google.com"
    return "; ".join([
        "default-src 'self'",
        "script-src 'self' " + " ".join(_inline_script_hashes(index_file) + [f"{google}/gsi/client"]),
        f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com {google}/gsi/style",
        "font-src 'self' https://fonts.gstatic.com data:",
        "img-src 'self' data: blob: https:",
        f"connect-src 'self' {google}/gsi/",
        f"frame-src {google}/gsi/",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    ])


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin-allow-popups",  # Google sign-in opens a popup
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"
    if https:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers.setdefault("Content-Security-Policy", app.state.csp)
    return response


@app.exception_handler(RateLimitExceeded)
async def _rate_limited(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content=exc.to_body(),
        headers={"Retry-After": str(exc.retry_after)},
    )


# ----------------------------
# Frontend static files
# ----------------------------
# The built frontend. STATIC_DIR points elsewhere (tests serve frontend/dist).
frontend_dist = Path(os.getenv("STATIC_DIR") or Path(__file__).resolve().parent / "static")
app.state.csp = _content_security_policy(frontend_dist / "index.html")

if frontend_dist.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=frontend_dist / "assets"),
        name="assets"
    )
    logger.info("📦 Frontend static files mounted")


# ----------------------------
# Health check
# ----------------------------
@app.get("/api/health")
async def health():
    try:
        if not db.is_configured:
            db_status = "not configured"
        elif not db.is_connected:
            db_status = "disconnected"
        else:
            await db.client.admin.command("ping")
            db_status = "connected"
    except Exception as e:
        logger.error(f"Health check error: {e}")
        db_status = "error"

    return {
        "message": "Legal Hybrid RAG Running",
        "db_status": db_status
    }


# ----------------------------
# SPA fallback route
# ----------------------------
app.include_router(admin_router, prefix="")
app.include_router(auth_router, prefix="")
# Chat history belongs to one signed-in user; every route filters on that user.
app.include_router(chat_router, prefix="")
# Blog: public marketing content, read-only — no guard by design, see
# app/routes/blogs.py. Must stay registered before the SPA catch-all below.
from app.routes.blogs import router as blogs_router
app.include_router(blogs_router)
# Archive figures for the "How it works" page: public, counts only.
from app.api.stats import router as stats_router
app.include_router(stats_router)
# Authoring the same articles. Separate router so the public one stays
# read-only, and guarded like the rest of /api/admin.
from app.routes.admin_blogs import router as admin_blogs_router
app.include_router(admin_blogs_router)
# Payments: POST /api/payments/webhook is public (Stripe's signature authenticates
# it); every account route needs the caller's own token.
app.include_router(payments_router, prefix="")
app.include_router(embedding_router, prefix="")
app.include_router(query_router, prefix="/query", tags=["Query"])


@app.get("/api/judgments/{judgment_id}/download")
async def download_judgment_alias(judgment_id: str, request: Request):
    from app.api.admin import download_judgment
    return await download_judgment(judgment_id, request)


@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    try:
        if frontend_dist.exists():
            index_file = frontend_dist / "index.html"
            if index_file.exists():
                return FileResponse(index_file)

        return {
            "message": "Frontend build not found. Deploy with frontend build included."
        }

    except Exception as e:
        logger.error(f"SPA serve error: {e}")
        return {"error": "Internal server error"}
