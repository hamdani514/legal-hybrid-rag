"""
How big a request may be.

Two layers, so one oversized request cannot take the server down:

* ``BodySizeLimit``: an ASGI middleware that refuses a request body above its
  route's limit with 413 BEFORE any of it is read into memory. A declared
  Content-Length over the limit is refused at once; a body sent without one
  (chunked) is counted as it arrives and cut off the moment it passes the
  limit. Without this, every route read whatever it was sent: a 60 MB login
  request grew the server by ~440 MB, and a few in parallel would exhaust it.
* Length-limited text types (``Email``, ``Password``...) for request models,
  so a field that does fit in the body still cannot carry megabytes into a
  database lookup or an attempt-limiter key.

Run the server behind a proxy with its own cap as well (nginx:
``client_max_body_size 55m;``) so oversized uploads are refused before they
reach Python at all.
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Optional

from pydantic import StringConstraints

from app.config import settings

MB = 1024 * 1024
DEFAULT_LIMIT = 1 * MB


def upload_limit() -> int:
    return int(float(getattr(settings, "MAX_PDF_UPLOAD_MB", 50) or 50) * MB)


# (method, path pattern, limit in bytes). Everything not listed gets DEFAULT_LIMIT.
# Each limit sits just above what the route itself accepts.
ROUTE_LIMITS: list[tuple[str, re.Pattern, object]] = [
    ("POST", re.compile(r"^/api/admin/upload$"), upload_limit),         # judgment PDFs
    ("POST", re.compile(r"^/api/auth/profile/avatar$"), 11 * MB),       # images, checked at 10 MB
    ("POST", re.compile(r"^/api/admin/blogs/cover$"), 6 * MB),          # images, checked at 5 MB
    ("POST", re.compile(r"^/api/admin/blogs$"), 4 * MB),                # 400,000-character article
    ("PUT", re.compile(r"^/api/admin/blogs/[^/]+$"), 4 * MB),
    ("POST", re.compile(r"^/api/chat/sessions/[^/]+/messages$"), 4 * MB),  # a conversation is capped at 4 MB
]


def limit_for(method: str, path: str) -> int:
    for m, pattern, limit in ROUTE_LIMITS:
        if m == method and pattern.match(path):
            return limit() if callable(limit) else limit
    return DEFAULT_LIMIT


class BodySizeLimit:
    """Pure ASGI (not BaseHTTPMiddleware), so the body is never buffered here."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            return await self.app(scope, receive, send)
        limit = limit_for(scope["method"], scope["path"])

        declared = None
        for name, value in scope.get("headers") or ():
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    return await _reply(send, 400, "Invalid Content-Length header.")
                break
        if declared is not None and declared > limit:
            return await _reply(send, 413, _message(limit))

        # No (or a lying) Content-Length: count as the body arrives. Past the
        # limit, answer 413 here and tell the app the client has gone, so it
        # stops reading; whatever it then tries to send is dropped. (Raising
        # instead would not work: FastAPI turns any error while reading the
        # body into its own 400.)
        received = 0
        started = False
        refused = False

        async def counting_receive():
            nonlocal received, refused
            if refused:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    refused = True
                    if not started:
                        await _reply(send, 413, _message(limit))
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message):
            nonlocal started
            if refused:
                return
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        await self.app(scope, counting_receive, guarded_send)


def _message(limit: int) -> str:
    size = f"{limit / MB:.0f} MB" if limit >= MB else f"{limit // 1024} KB"
    return f"This request is too large. The limit is {size}."


async def _reply(send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                            (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": body})


# ── Length-limited text for request models ──────────────────────────────
Email = Annotated[str, StringConstraints(max_length=254)]          # RFC 5321's longest address
Password = Annotated[str, StringConstraints(max_length=256)]       # bcrypt reads 72 bytes anyway
Code = Annotated[str, StringConstraints(max_length=16)]            # emailed 6-digit codes
Name = Annotated[str, StringConstraints(max_length=200)]
ShortText = Annotated[str, StringConstraints(max_length=300)]      # subjects, roles, dates, ids
Message = Annotated[str, StringConstraints(max_length=10_000)]     # contact and support messages
Token = Annotated[str, StringConstraints(max_length=8_192)]        # Google ID and reCAPTCHA tokens
Id = Annotated[str, StringConstraints(max_length=200)]

OptEmail = Optional[Email]
OptPassword = Optional[Password]
OptName = Optional[Name]
OptShortText = Optional[ShortText]
OptToken = Optional[Token]
