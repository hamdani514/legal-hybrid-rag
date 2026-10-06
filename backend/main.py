"""
FastAPI entry point: lifespan (DB, model warm-up), routers, and route protection.

Route protection is applied HERE, as router-level dependencies, rather than as
decorators inside each route module. That makes the policy default-deny (a new
admin route is admin-only without anyone remembering to protect it) and keeps
it reviewable in one place: the guards and the public allowlist live in
app/api/security.py. Every guard is a no-op while settings.AUTH_REQUIRED is
False (anonymous callers behave exactly as before), apart from the per-user
search limits.

    /api/admin/*      admin, except ADMIN_PUBLIC_ROUTES (login, availability
                      checks, contact form) and the PDF download (any user)
    /api/auth/*       public — each route authenticates the caller itself
    /query/*          signed-in user + per-user limits
    /embeddings/*     /search: user + limits; /generate: admin
    /api/judgments/{id}/download   signed-in user (token may be ?token=)
    /api/health, SPA  public
"""

from pathlib import Path
from contextlib import asynccontextmanager
import logging

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.embedding_routes import router as embedding_router
from app.api.routes.query import router as query_router
from app.api.security import (
    RateLimitExceeded,
    admin_router_guard,
    check_security_config,
    embedding_router_guard,
    query_router_guard,
    require_user_download,
)
from app.database import connect_db, close_db, db

# ----------------------------
# Logging setup
# ----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("legal-rag")


# ----------------------------
# Lifespan (startup/shutdown)
# ----------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting application...")

    # Refuses to start with the placeholder JWT_SECRET when AUTH_REQUIRED=True.
    check_security_config()

    try:
        logger.info("🔌 Connecting to database...")
        await connect_db()
        logger.info("✅ Database connection initialized successfully")

        # Initialize MongoDB indexes for embeddings
        from app.database.mongodb import init_mongodb_indexes
        await init_mongodb_indexes()

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
            from app.config import settings

            if getattr(settings, "USE_V2_PIPELINE", False):
                from app.retrieval.pipeline_v2 import retrieve_v2

                await retrieve_v2("warm-up query", top_k_judgments=1)
                logger.info("🔥 Pipeline v2 warm")
        except Exception as e:
            logger.warning(f"Pipeline warm-up skipped: {e}")

    app.state.warmup = asyncio.create_task(_warm())

    yield

    logger.info("🛑 Shutting down application...")
    try:
        await close_db()
        logger.info("✅ Database connection closed")
    except Exception as e:
        logger.exception(f"⚠️ Error during shutdown: {e}")


# ----------------------------
# FastAPI app
# ----------------------------
app = FastAPI(lifespan=lifespan)


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
frontend_dist = Path(__file__).resolve().parent / "static"

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
app.include_router(admin_router, prefix="", dependencies=[Depends(admin_router_guard)])
app.include_router(auth_router, prefix="")  # public by design: see app/api/auth.py
app.include_router(embedding_router, prefix="", dependencies=[Depends(embedding_router_guard)])
app.include_router(
    query_router, prefix="/query", tags=["Query"], dependencies=[Depends(query_router_guard)]
)


@app.get("/api/judgments/{judgment_id}/download", dependencies=[Depends(require_user_download)])
async def download_judgment_alias(judgment_id: str):
    from app.api.admin import download_judgment
    return await download_judgment(judgment_id)


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
