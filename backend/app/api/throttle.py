"""
Attempt limits for logins, codes and emails, kept in MongoDB.

Without them a password could be guessed at full speed, and anyone could make
the server send an unlimited number of emails to any address. The per-minute
search limits in security.py live in memory; these are stored in the database
(collection auth_throttle) so a restart does not hand an attacker a fresh
allowance, and they expire on their own (TTL index on expires_at).

Each rule counts events per key in a fixed window. When the count reaches the
limit, the key is locked for `lock_s`: every attempt is refused with 429, even a
correct password, until the lock ends. Two kinds of key:

  account  the email or admin id being tried: stops guessing one account's
           password, however many machines the guesses come from
  ip       the caller's address: stops one machine spraying many accounts
           (generous, since users behind one proxy share an address)

A successful login clears its account key.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from loguru import logger

from app.api.security import RateLimitExceeded
from app.database import db

COLLECTION = "auth_throttle"


@dataclass(frozen=True)
class Rule:
    name: str
    limit: int        # events allowed in the window
    window_s: int
    lock_s: int       # how long the key stays locked once the limit is reached
    message: str


MINUTE, HOUR = 60, 3600
LOGIN_ACCOUNT = Rule("login-account", 5, 15 * MINUTE, 15 * MINUTE,
                     "Too many failed sign-in attempts for this account. Please wait 15 minutes or reset your password.")
LOGIN_IP = Rule("login-ip", 30, 15 * MINUTE, 15 * MINUTE,
                "Too many failed sign-in attempts from this network. Please wait 15 minutes.")
ADMIN_ACCOUNT = Rule("admin-account", 5, 15 * MINUTE, 30 * MINUTE,
                     "Too many failed sign-in attempts for this admin account. Please wait 30 minutes.")
ADMIN_IP = Rule("admin-ip", 20, 15 * MINUTE, 30 * MINUTE,
                "Too many failed admin sign-in attempts from this network. Please wait 30 minutes.")
CODE_EMAIL = Rule("code-email", 3, HOUR, HOUR,
                  "Too many codes requested for this email. Please wait an hour before asking for another.")
CODE_IP = Rule("code-ip", 20, HOUR, HOUR,
               "Too many codes requested from this network. Please try again in an hour.")
CODE_CHECK = Rule("code-check", 10, HOUR, HOUR,
                  "Too many incorrect codes. Please wait an hour before trying again.")
FORM_IP = Rule("form-ip", 10, HOUR, HOUR,
               "Too many messages sent from this network. Please try again in an hour.")


def client_ip(request: Request) -> str:
    """The caller's address. Behind a proxy, uvicorn's --proxy-headers fills
    request.client from X-Forwarded-For (see the Dockerfile)."""
    return request.client.host if request.client else "unknown"


def _collection():
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    return db.database[COLLECTION]


def _key(rule: Rule, value: str) -> str:
    return f"{rule.name}:{(value or '').strip().lower()}"


def _refuse(rule: Rule, locked_until: datetime, now: datetime) -> None:
    retry = max(1, int((locked_until - now).total_seconds()))
    raise RateLimitExceeded(rule.name, rule.limit, retry, rule.message)


def _aware(value):
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def ensure_indexes() -> None:
    try:
        await _collection().create_index("expires_at", expireAfterSeconds=0)
    except Exception as e:  # noqa: BLE001 - limits still work, entries just linger
        logger.warning(f"auth_throttle TTL index: {e}")


async def check(rule: Rule, value: str) -> None:
    """429 if this key is locked. Call before doing the work."""
    now = datetime.now(timezone.utc)
    doc = await _collection().find_one({"_id": _key(rule, value)}, {"locked_until": 1})
    locked_until = _aware((doc or {}).get("locked_until"))
    if locked_until and locked_until > now:
        _refuse(rule, locked_until, now)


async def record(rule: Rule, value: str) -> int:
    """Count one event; lock the key once the limit is reached. Returns the count."""
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(seconds=rule.window_s)
    lock_end = now + timedelta(seconds=rule.lock_s)
    in_window = {"$gt": [{"$ifNull": ["$window_end", now]}, now]}
    doc = await _collection().find_one_and_update(
        {"_id": _key(rule, value)},
        [
            {"$set": {
                "count": {"$cond": [in_window, {"$add": [{"$ifNull": ["$count", 0]}, 1]}, 1]},
                "window_end": {"$cond": [in_window, "$window_end", window_end]},
            }},
            {"$set": {
                "locked_until": {"$cond": [{"$gte": ["$count", rule.limit]}, lock_end, "$locked_until"]},
            }},
            {"$set": {"expires_at": {"$max": ["$window_end", {"$ifNull": ["$locked_until", now]}]}}},
        ],
        upsert=True,
        return_document=True,
    )
    return int((doc or {}).get("count") or 1)


async def spend(rule: Rule, value: str) -> None:
    """For actions that are limited every time (sending a code, a form): refuse
    when locked, otherwise count it, refusing the one that reaches past the limit."""
    await check(rule, value)
    count = await record(rule, value)
    if count > rule.limit:
        now = datetime.now(timezone.utc)
        _refuse(rule, now + timedelta(seconds=rule.lock_s), now)


async def clear(rule: Rule, value: str) -> None:
    await _collection().delete_one({"_id": _key(rule, value)})
