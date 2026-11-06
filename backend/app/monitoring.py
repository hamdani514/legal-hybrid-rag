"""
Knowing when the server fails.

Two layers, both set up once at startup by ``setup_monitoring()``:

* An error log on disk, always on: every ERROR (and every unhandled exception,
  with its traceback) goes to ``logs/errors.log``, rotated at 10 MB and kept for
  30 days. Console logs vanish with the process or the container; this file
  does not (mount ``backend/logs`` as a volume in Docker to keep it across
  redeploys).
* Sentry, only when ``SENTRY_DSN`` is set: errors are sent with their stack
  trace so they can be alerted on and grouped. No personal data is sent
  (``send_default_pii=False``: no IP addresses, cookies or request bodies), and
  no performance tracing.

``unhandled_error`` is the app's catch-all exception handler: the full error
goes to the log (and Sentry), the user gets one plain sentence.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger

from app.config import settings

SERVER_ERROR = "Something went wrong on our side. Please try again in a moment."

_ready = False


def error_log_dir() -> Path:
    return Path(settings.ERROR_LOG_DIR or Path(__file__).resolve().parents[1] / "logs")


def setup_monitoring() -> None:
    global _ready
    if _ready:
        return
    _ready = True

    log_dir = error_log_dir()
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_dir / "errors.log",
            level="ERROR",
            rotation="10 MB",
            retention="30 days",
            compression="zip",
            enqueue=True,       # safe across threads and the ingestion workers
            backtrace=False,    # tracebacks, but not the variable values in them
            diagnose=False,
        )
    except OSError as e:  # a read-only disk must not stop the server
        logger.warning(f"Error log disabled: cannot write to {log_dir}: {e}")

    dsn = (settings.SENTRY_DSN or "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed; errors stay in the log only.")
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=settings.SENTRY_ENVIRONMENT or "production",
        send_default_pii=False,
        traces_sample_rate=0.0,
    )
    logger.info("Error reporting to Sentry is on.")


async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    """Last resort for an exception no route handled."""
    logger.opt(exception=exc).error(f"Unhandled error on {request.method} {request.url.path}")
    return JSONResponse(status_code=500, content={"detail": SERVER_ERROR})
