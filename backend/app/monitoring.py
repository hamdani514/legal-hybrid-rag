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

import re
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger

from app.config import settings

SERVER_ERROR = "Something went wrong on our side. Please try again in a moment."

# Email addresses are personal data. Log lines used to carry them in full (about
# 25 places: payments, sign-up, account deletion) into errors.log, kept 30
# days, and Sentry. Every line is now masked on the way out, whichever code
# wrote it: someone@gmail.com -> s***@gmail.com.
_EMAIL = re.compile(r"([A-Za-z0-9])[A-Za-z0-9._%+-]*@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")


def mask_emails(text):
    return _EMAIL.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", text) if isinstance(text, str) else text


def _mask_record(record) -> None:
    record["message"] = mask_emails(record["message"])


def _mask_event(event, _hint):
    """Sentry: mask emails in the message, exception texts and breadcrumbs."""
    try:
        if event.get("message"):
            event["message"] = mask_emails(event["message"])
        if isinstance(event.get("logentry"), dict):
            for k in ("message", "formatted"):
                if event["logentry"].get(k):
                    event["logentry"][k] = mask_emails(event["logentry"][k])
        for exc in (event.get("exception") or {}).get("values") or []:
            if exc.get("value"):
                exc["value"] = mask_emails(exc["value"])
        for crumb in (event.get("breadcrumbs") or {}).get("values") or []:
            if crumb.get("message"):
                crumb["message"] = mask_emails(crumb["message"])
    except Exception:  # noqa: BLE001 - never lose an error report over masking
        pass
    return event

_ready = False


def error_log_dir() -> Path:
    return Path(settings.ERROR_LOG_DIR or Path(__file__).resolve().parents[1] / "logs")


# Measured: one search alone holds the process at ~1.6 GB, a few at once ~2 GB,
# and an upload being OCR'd adds more. Below this the server runs out of memory.
MIN_MEMORY_GB = 4
MIN_CORES = 4


def warn_if_undersized() -> None:
    """Say in the log, at startup, when the machine is smaller than the app needs."""
    try:
        import psutil
        memory_gb = psutil.virtual_memory().total / 1024 ** 3
        cores = psutil.cpu_count() or 1
        # In a container, a memory limit lower than the machine's is what counts.
        for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
            try:
                raw = Path(path).read_text().strip()
                if raw.isdigit():
                    memory_gb = min(memory_gb, int(raw) / 1024 ** 3)
                break
            except OSError:
                continue
    except Exception:  # noqa: BLE001 - a missing reading must not stop startup
        return
    if memory_gb < MIN_MEMORY_GB - 0.3 or cores < MIN_CORES:
        logger.warning(
            f"This server has {memory_gb:.1f} GB of memory and {cores} CPU cores; the app needs at least "
            f"{MIN_MEMORY_GB} GB and {MIN_CORES} cores. Expect slow searches and out-of-memory restarts."
        )


def setup_monitoring() -> None:
    global _ready
    if _ready:
        return
    _ready = True
    logger.configure(patcher=_mask_record)
    warn_if_undersized()

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
        before_send=_mask_event,
    )
    logger.info("Error reporting to Sentry is on.")


async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    """Last resort for an exception no route handled."""
    logger.opt(exception=exc).error(f"Unhandled error on {request.method} {request.url.path}")
    return JSONResponse(status_code=500, content={"detail": SERVER_ERROR})
