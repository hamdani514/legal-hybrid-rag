"""
Authentication, authorisation and per-user limits — the one place they live.

WHY this module exists
----------------------
Before it, nothing in the API checked who was calling: /query/* and every
admin route (including DELETE /api/admin/jobs/{id}, which permanently removes
a judgment and its Drive copy) were open to anyone who could reach the port,
passwords were compared in plain text, and JWT_SECRET was never used.

The rules, all enforced here:

  * Default-deny. main.py installs api_guard on the whole application, so every
    route — including one added next year — needs a valid token unless it is
    listed in PUBLIC_ROUTES below. Nobody has to remember a decorator.
  * Identity comes from the verified token and nowhere else. A user id in a
    header, query string or body is never trusted: routes ask caller_id().
  * There is no "authentication off" mode. There used to be a switch, it was
    left off, and the whole API was open. A switch can be forgotten; this can't.
  * The app refuses to start with a weak JWT_SECRET, so a server cannot run with
    a signing key anyone can read in the repository.

app/api/access_selfcheck.py walks every route and fails if any of this stops
being true.

  * Passwords: bcrypt via the `bcrypt` package directly. passlib 1.7.4 is
    incompatible with the installed bcrypt 5.x (its backend self-test hashes a
    255-byte secret, which bcrypt 5 rejects), so CryptContext crashes on the
    first hash. The stored format ($2b$...) is the same one passlib writes, so
    nothing is lost. Legacy plain-text passwords still verify (constant-time)
    and are reported as needing an upgrade, which the login routes perform.
  * Per-user limits: two in-process sliding windows (searches per minute,
    answers per day) keyed by the token's `sub`, or by client IP for
    anonymous callers. One shared Gemini quota serves every user; without
    this, one user (or one script) could drain it for everyone. In-process is
    deliberate: the app runs as a single uvicorn worker. With several workers
    each would keep its own counters (limits become per-worker) — move the
    windows to Redis/Mongo before scaling out.
"""

from __future__ import annotations

import hmac
import threading
import time
from collections import deque
from typing import Deque, Dict, Literal, Optional, Tuple

import bcrypt
from fastapi import HTTPException, Request, status
from jose import ExpiredSignatureError, JWTError, jwt
from loguru import logger

from app.config import settings
from app.retrieval.contracts import TokenPayload

ALGORITHM = "HS256"
PLACEHOLDER_SECRET = "long_random_string_here"
ANONYMOUS_SUB = "anonymous"
MIN_SECRET_LENGTH = 32
BCRYPT_ROUNDS = 12
BCRYPT_MAX_BYTES = 72  # bcrypt ignores (bcrypt 5: rejects) anything past this

Role = Literal["user", "admin"]


# ─────────────────────────────────────────────────────────────────────────────
# Configuration checks
# ─────────────────────────────────────────────────────────────────────────────
def _secret() -> str:
    return (getattr(settings, "JWT_SECRET", "") or "").strip()


def secret_is_weak() -> bool:
    secret = _secret()
    return not secret or secret == PLACEHOLDER_SECRET or len(secret) < MIN_SECRET_LENGTH


def check_security_config() -> None:
    """Startup gate, called from main.py's lifespan.

    A placeholder, empty or short secret means anyone who has read the repository
    can mint an admin token, so the app refuses to start rather than run
    "protected" with a public key.
    """
    if secret_is_weak():
        logger.critical(
            "JWT_SECRET is missing, the placeholder, or under {} characters. Anyone could "
            "forge admin tokens. Set JWT_SECRET to a random value (python -c \"import secrets; "
            "print(secrets.token_urlsafe(48))\"). Refusing to start.",
            MIN_SECRET_LENGTH,
        )
        raise RuntimeError("Refusing to start: JWT_SECRET is weak.")
    logger.info(
        "Auth: limits {}/min searches, {}/day answers",
        _limit("USER_SEARCHES_PER_MINUTE"),
        _limit("USER_ANSWERS_PER_DAY"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Passwords
# ─────────────────────────────────────────────────────────────────────────────
def is_bcrypt_hash(value: Optional[str]) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 60
        and value[:4] in ("$2a$", "$2b$", "$2y$")
    )


def hash_password(plain: str) -> str:
    """bcrypt-hash a password. Raises ValueError for > 72 UTF-8 bytes (bcrypt's limit)."""
    raw = plain.encode("utf-8")
    if len(raw) > BCRYPT_MAX_BYTES:
        raise ValueError(f"Password must be at most {BCRYPT_MAX_BYTES} bytes long.")
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("ascii")


# A real hash of a random string, so a login for an unknown account costs the
# same bcrypt time as a wrong password (no account enumeration by timing).
_DUMMY_HASH = bcrypt.hashpw(b"timing-equaliser", bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("ascii")


def burn_password_check(plain: str) -> None:
    try:
        bcrypt.checkpw(plain.encode("utf-8")[:BCRYPT_MAX_BYTES], _DUMMY_HASH.encode("ascii"))
    except ValueError:
        pass


def verify_password(plain: str, stored: Optional[str]) -> Tuple[bool, bool]:
    """
    Returns (matches, needs_upgrade).

    needs_upgrade is True only for a legacy plain-text password that matched:
    the caller should then replace it with hash_password(plain). A legacy value
    longer than bcrypt's limit matches but cannot be upgraded (needs_upgrade
    False) — rare, logged by the caller's next attempt.
    """
    if not plain or not stored or not isinstance(stored, str):
        burn_password_check(plain or "")
        return False, False
    if is_bcrypt_hash(stored):
        try:
            return bcrypt.checkpw(plain.encode("utf-8"), stored.encode("ascii")), False
        except ValueError:  # > 72 bytes supplied, or a malformed hash
            return False, False
    burn_password_check(plain)  # keep timing similar to the hashed path
    matches = hmac.compare_digest(plain.encode("utf-8"), stored.encode("utf-8"))
    upgradable = matches and len(plain.encode("utf-8")) <= BCRYPT_MAX_BYTES
    if matches and not upgradable:
        logger.warning("Legacy password longer than 72 bytes cannot be bcrypt-upgraded")
    return matches, upgradable


# ─────────────────────────────────────────────────────────────────────────────
# Tokens
# ─────────────────────────────────────────────────────────────────────────────
def create_access_token(sub: str, role: Role, expires_minutes: Optional[int] = None) -> str:
    if not sub:
        raise ValueError("token subject must be non-empty")
    if role not in ("user", "admin"):
        raise ValueError(f"invalid role {role!r}")
    minutes = int(expires_minutes or getattr(settings, "JWT_EXPIRE_MINUTES", 1440) or 1440)
    now = int(time.time())
    claims = {"sub": str(sub), "role": role, "iat": now, "exp": now + minutes * 60}
    if secret_is_weak():
        raise RuntimeError("JWT_SECRET is weak: refusing to sign a token.")
    return jwt.encode(claims, _secret(), algorithm=ALGORITHM)


class TokenError(Exception):
    """Token present but unusable (bad signature, expired, malformed)."""


def decode_token(token: str) -> TokenPayload:
    if secret_is_weak():  # a token signed with a public key proves nothing
        raise TokenError("Invalid authentication token.")
    try:
        claims = jwt.decode(
            token,
            _secret(),
            algorithms=[ALGORITHM],  # pinned: never accept "none" or RS/HS confusion
            options={"require_exp": True, "require_sub": True},
        )
    except ExpiredSignatureError as e:
        raise TokenError("Session expired. Please sign in again.") from e
    except JWTError as e:
        raise TokenError("Invalid authentication token.") from e
    sub, role, exp = claims.get("sub"), claims.get("role"), claims.get("exp")
    if not isinstance(sub, str) or not sub or role not in ("user", "admin") or not isinstance(exp, int):
        raise TokenError("Invalid authentication token.")
    payload = TokenPayload(sub=sub, role=role, exp=exp)
    if isinstance(claims.get("iat"), int):
        payload["iat"] = claims["iat"]
    return payload


def anonymous(role: Role = "user") -> TokenPayload:
    return TokenPayload(sub=ANONYMOUS_SUB, role=role, exp=0)


def is_anonymous(principal: Optional[TokenPayload]) -> bool:
    return not principal or principal.get("sub") == ANONYMOUS_SUB


def _extract_token(request: Request, allow_query: bool = False) -> Optional[str]:
    header = request.headers.get("authorization") or ""
    scheme, _, value = header.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    if allow_query:
        # Only for file downloads: an <a href> cannot carry a header.
        q = request.query_params.get("token") or request.query_params.get("access_token")
        if q:
            return q.strip()
    return None


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _resolve(request: Request, need: Literal["any", "user", "admin"], allow_query: bool = False) -> TokenPayload:
    """The single decision function behind every dependency.

    "any" is for public routes: a valid token still identifies the caller, and an
    unusable one is ignored, since a public page must not fail over a stale token.
    Everything else needs a valid token, and "admin" needs an admin one.
    """
    token = _extract_token(request, allow_query=allow_query)
    principal: Optional[TokenPayload] = None
    error: Optional[str] = None
    if token:
        try:
            principal = decode_token(token)
        except TokenError as e:
            error = str(e)

    if need == "any":
        principal = principal or anonymous()
    else:
        if principal is None:
            raise _unauthorized(error or "Authentication required. Please sign in.")
        if need == "admin" and principal["role"] != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required.")
    request.state.principal = principal
    return principal


def caller_id(request: Request) -> str:
    """Who is calling: the verified token's subject. The only source of identity.

    Never read a user id from a header, query string or body to decide whose data
    to touch; that is how one user could act as another.
    """
    principal = getattr(request.state, "principal", None)
    sub = principal.get("sub") if isinstance(principal, dict) else None
    if not sub or sub == ANONYMOUS_SUB:
        raise _unauthorized("Please sign in.")
    return str(sub)


def caller_is_admin(request: Request) -> bool:
    principal = getattr(request.state, "principal", None)
    return isinstance(principal, dict) and principal.get("role") == "admin" and principal.get("sub") != ANONYMOUS_SUB


# FastAPI dependencies --------------------------------------------------------
async def require_user(request: Request) -> TokenPayload:
    """Any signed-in account (user or admin)."""
    return _resolve(request, "user")


async def require_admin(request: Request) -> TokenPayload:
    """Admin role. 401 without a valid token, 403 with a user token."""
    return _resolve(request, "admin")


# ─────────────────────────────────────────────────────────────────────────────
# Route policy: installed on the whole application by main.py
# ─────────────────────────────────────────────────────────────────────────────
# The ONLY routes reachable without signing in, as (METHOD, route path template).
# Anything not listed needs a token. Adding a line here is a security decision,
# and access_selfcheck.py fails until the same line is added to its own list.
PUBLIC_ROUTES = frozenset({
    ("GET", "/api/health"),
    ("GET", "/api/health/live"),
    ("GET", "/{full_path:path}"),                # the single-page app itself
    # Getting into an account: each proves itself with a password, code or token.
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/admin/login"),
    ("POST", "/api/auth/signup"),
    ("POST", "/api/auth/verify-signup-otp"),
    ("POST", "/api/auth/resend-signup-otp"),
    ("POST", "/api/auth/forgot-password"),
    ("POST", "/api/auth/verify-otp"),
    ("POST", "/api/auth/reset-password"),
    ("POST", "/api/auth/reactivate/{token}"),
    ("POST", "/api/auth/send-reactivation-link"),
    ("GET", "/api/auth/google/config"),
    ("POST", "/api/auth/google"),
    # Pictures an <img> loads, which cannot send a token.
    ("GET", "/api/auth/avatar/{file_id}"),
    ("GET", "/api/blogs/cover/{file_id}"),
    # Public pages and forms.
    ("POST", "/api/auth/contact"),
    ("POST", "/api/admin/support"),              # contact form
    ("GET", "/api/blogs"),
    ("GET", "/api/blogs/{slug}"),
    ("GET", "/api/stats"),
    ("GET", "/api/payments/config"),
    # Stripe is not a signed-in user; its signature authenticates the call.
    ("POST", "/api/payments/webhook"),
})

# Signed-in users, token also accepted as ?token= since an <a href> cannot send a
# header. Whether the caller's plan includes downloading is checked by the route.
DOWNLOAD_ROUTES = frozenset({
    ("GET", "/api/admin/judgments/{judgment_id}/download"),
    ("GET", "/api/judgments/{judgment_id}/download"),
})

# Admin only, outside /api/admin.
ADMIN_ROUTES = frozenset({("POST", "/embeddings/generate")})


def route_template(request: Request) -> str:
    """The full path template of the matched route, e.g. /api/payments/config.

    FastAPI 0.162+ keeps included routers nested, so scope["route"].path is the
    path INSIDE the router ("/config") and the full template lives on the
    per-request route context. Older versions flatten routes, so route.path is
    already full. A wrong template would misfile a route (a public one would
    answer 401), so both are read here and the self-check runs real requests
    through this on every build.
    """
    context = (request.scope.get("fastapi") or {}).get("effective_route_context")
    for source in (context, request.scope.get("route")):
        path = getattr(source, "path", None)
        if isinstance(path, str) and path:
            return path
    return request.url.path


def _route_key(request: Request) -> Tuple[str, str]:
    return request.method.upper(), route_template(request)


def required_access(key: Tuple[str, str]) -> Literal["public", "download", "admin", "user"]:
    """What a route needs. Default-deny: not listed means signed in."""
    if key in PUBLIC_ROUTES:
        return "public"
    if key in DOWNLOAD_ROUTES:
        return "download"
    if key in ADMIN_ROUTES or key[1].startswith("/api/admin"):
        return "admin"
    return "user"


async def account_is_active(principal: TokenPayload) -> bool:
    """Does the account a valid token names still exist, and is it active?

    A token is valid for its whole lifetime (JWT_EXPIRE_MINUTES), so without this
    a deleted or deactivated account kept working until its token ran out.

    A token issued before the account's password last changed is refused too
    (``tokens_valid_after``): resetting a password ends every other session,
    including one a thief holds.
    """
    from app.database import db

    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    sub = str(principal.get("sub") or "")
    if principal.get("role") == "admin":
        super_email = (getattr(settings, "SUPER_ADMIN_EMAIL", "") or "").strip().lower()
        if super_email and getattr(settings, "SUPER_ADMIN_PASSWORD", "") and sub.lower() == super_email:
            return True  # the super admin is configured, not stored
        doc = await db.database.admins.find_one({"adminid": sub}, {"status": 1, "isActive": 1, "tokens_valid_after": 1})
    else:
        clauses = [{"id": sub}, {"email": sub.lower()}]
        try:
            from bson import ObjectId
            if ObjectId.is_valid(sub):
                clauses.append({"_id": ObjectId(sub)})
        except Exception:  # noqa: BLE001
            pass
        doc = await db.database.users.find_one({"$or": clauses}, {"status": 1, "isActive": 1, "tokens_valid_after": 1})
    if not doc:
        return False
    valid_after = doc.get("tokens_valid_after")
    if isinstance(valid_after, (int, float)) and int(principal.get("iat") or 0) < int(valid_after):
        return False
    return doc.get("isActive") is not False and str(doc.get("status") or "Active").lower() not in ("inactive", "deactivated", "deleted")


async def api_guard(request: Request) -> TokenPayload:
    """Runs before every route in the application."""
    access = required_access(_route_key(request))
    if access == "public":
        return _resolve(request, "any")
    principal = _resolve(request, "user" if access == "download" else access, allow_query=access == "download")
    if not await account_is_active(principal):
        # 401: the frontend then ends the session, as it should.
        raise _unauthorized("This account is no longer active. Please sign in again.")
    if access != "download":
        enforce_limits(request, principal)
    return principal


# ─────────────────────────────────────────────────────────────────────────────
# Per-user limits
# ─────────────────────────────────────────────────────────────────────────────
# Paths that each run a search and/or an LLM answer. All count towards the
# per-minute window; all but /query/more count towards the daily answer budget,
# because each one spends shared Gemini quota (search answers its top case
# automatically). /query/more pages through a search already run: it uses the
# CPU (the cross-encoder) but no Gemini call.
SEARCH_PATHS = frozenset({
    "/query/search", "/query/more", "/query/answer", "/query/compare", "/query/summarize",
})
ANSWER_PATHS = SEARCH_PATHS - {"/query/more"}

MINUTE = 60.0
DAY = 86_400.0


class RateLimitExceeded(Exception):
    """Raised by enforce_limits; main.py renders it as a 429 JSON response."""

    def __init__(self, scope: str, limit: int, retry_after: int, message: str):
        super().__init__(message)
        self.scope = scope
        self.limit = limit
        self.retry_after = retry_after
        self.message = message

    def to_body(self) -> dict:
        # `detail` stays a plain string so existing `err.detail || ...` UI code shows it.
        return {
            "detail": self.message,
            "error": "rate_limited",
            "scope": self.scope,
            "limit": self.limit,
            "retry_after": self.retry_after,
        }


class SlidingWindow:
    """Exact sliding-window counter: timestamps per key, pruned on access."""

    def __init__(self, window_s: float):
        self.window_s = window_s
        self._hits: Dict[str, Deque[float]] = {}

    def _prune(self, key: str, now: float) -> Deque[float]:
        q = self._hits.get(key)
        if q is None:
            q = self._hits[key] = deque()
        cutoff = now - self.window_s
        while q and q[0] <= cutoff:
            q.popleft()
        return q

    def retry_after(self, key: str, limit: int, now: float) -> Optional[int]:
        """Seconds until a slot frees, or None if a hit is allowed now."""
        q = self._prune(key, now)
        if len(q) < limit:
            return None
        return max(1, int(q[0] + self.window_s - now + 0.999))

    def record(self, key: str, now: float) -> None:
        self._prune(key, now).append(now)

    def count(self, key: str, now: float) -> int:
        return len(self._prune(key, now))

    def sweep(self, now: float) -> None:
        for key in [k for k, q in self._hits.items() if not q or q[-1] <= now - self.window_s]:
            del self._hits[key]


class UserRateLimiter:
    """Both windows behind one lock, so a check-then-record is atomic across threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.minute = SlidingWindow(MINUTE)
        self.day = SlidingWindow(DAY)
        self._last_sweep = 0.0

    def reset(self) -> None:
        with self._lock:
            self.minute = SlidingWindow(MINUTE)
            self.day = SlidingWindow(DAY)

    def hit(self, key: str, per_minute: int, per_day: int, counts_answer: bool, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            if now - self._last_sweep > 300:  # keep memory bounded by active keys
                self.minute.sweep(now)
                self.day.sweep(now)
                self._last_sweep = now
            if per_minute > 0:
                wait = self.minute.retry_after(key, per_minute, now)
                if wait is not None:
                    raise RateLimitExceeded(
                        "per_minute", per_minute, wait,
                        f"You have reached the limit of {per_minute} searches per minute. "
                        f"Please wait {wait} seconds and try again.",
                    )
            if counts_answer and per_day > 0:
                wait = self.day.retry_after(key, per_day, now)
                if wait is not None:
                    hours = max(1, round(wait / 3600))
                    raise RateLimitExceeded(
                        "per_day", per_day, wait,
                        f"You have reached the daily limit of {per_day} answers. "
                        f"It resets in about {hours} hour{'s' if hours != 1 else ''}.",
                    )
            # Record only after both checks pass: a refused call costs nothing.
            if per_minute > 0:
                self.minute.record(key, now)
            if counts_answer and per_day > 0:
                self.day.record(key, now)


limiter = UserRateLimiter()


def _limit(name: str) -> int:
    try:
        return max(0, int(getattr(settings, name, 0) or 0))
    except (TypeError, ValueError):
        return 0


def limit_key(request: Request, principal: Optional[TokenPayload]) -> Optional[str]:
    if not is_anonymous(principal):
        return f"user:{principal['sub']}"
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"


def enforce_limits(request: Request, principal: Optional[TokenPayload]) -> None:
    path = request.url.path.rstrip("/") or "/"
    if path not in SEARCH_PATHS or request.method.upper() != "POST":
        return
    key = limit_key(request, principal)
    if key is None:
        return
    limiter.hit(
        key,
        per_minute=_limit("USER_SEARCHES_PER_MINUTE"),
        per_day=_limit("USER_ANSWERS_PER_DAY"),
        counts_answer=path in ANSWER_PATHS,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Self-check (no DB, no network): python -m app.api.security
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    original_secret = settings.JWT_SECRET
    settings.JWT_SECRET = "x" * 48
    try:
        h = hash_password("S3cret!pass")
        assert is_bcrypt_hash(h), h
        assert verify_password("S3cret!pass", h) == (True, False)
        assert verify_password("wrong", h) == (False, False)
        assert verify_password("legacy", "legacy") == (True, True)
        assert verify_password("legacyX", "legacy") == (False, False)
        assert verify_password("x", None) == (False, False)
        try:
            hash_password("a" * 73)
            raise AssertionError("73-byte password must be rejected")
        except ValueError:
            pass

        t = create_access_token("USr-1", "user")
        p = decode_token(t)
        assert p["sub"] == "USr-1" and p["role"] == "user" and p["exp"] > time.time()
        expired = jwt.encode({"sub": "a", "role": "user", "exp": int(time.time()) - 5}, _secret(), algorithm=ALGORITHM)
        for bad in (expired, t + "x", jwt.encode({"sub": "a", "role": "root", "exp": 9999999999}, _secret(), algorithm=ALGORITHM),
                    jwt.encode({"sub": "a", "role": "admin", "exp": 9999999999}, "other-secret-" * 4, algorithm=ALGORITHM)):
            try:
                decode_token(bad)
                raise AssertionError("bad token accepted")
            except TokenError:
                pass

        rl = UserRateLimiter()
        for i in range(3):
            rl.hit("k", per_minute=3, per_day=5, counts_answer=True, now=1000.0 + i)
        try:
            rl.hit("k", per_minute=3, per_day=5, counts_answer=True, now=1010.0)
            raise AssertionError("4th hit in a minute must be refused")
        except RateLimitExceeded as e:
            assert e.scope == "per_minute" and 1 <= e.retry_after <= 60, (e.scope, e.retry_after)
        rl.hit("k", per_minute=3, per_day=5, counts_answer=True, now=1061.0)  # window slid
        rl.hit("k", per_minute=3, per_day=5, counts_answer=True, now=1062.0)
        try:
            rl.hit("k", per_minute=3, per_day=5, counts_answer=True, now=1130.0)
            raise AssertionError("6th answer in a day must be refused")
        except RateLimitExceeded as e:
            assert e.scope == "per_day", e.scope
        assert rl.minute.count("k", 1130.0) == 0  # refused calls are not recorded
        rl.hit("other", per_minute=3, per_day=5, counts_answer=True, now=1130.0)  # keys independent
        print("security self-check: OK")
    finally:
        settings.JWT_SECRET = original_secret
