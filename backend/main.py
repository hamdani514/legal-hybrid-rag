from pathlib import Path
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.embedding_routes import router as embedding_router
from app.api.routes.query import router as query_router
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
app.include_router(admin_router, prefix="")
app.include_router(auth_router, prefix="")
app.include_router(embedding_router, prefix="")
app.include_router(query_router, prefix="/query", tags=["Query"])


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
