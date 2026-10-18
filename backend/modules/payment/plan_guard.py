"""
Tier-based rate limiting (Plan Guard).
Enforces daily query quotas:
  - Free plan: 1 query/day
  - Standard plan: 20 queries/day (only while subscription is valid)
Features:
  - Daily reset at midnight UTC
  - Lazy downgrade for expired subscriptions
  - Atomic $inc to prevent race conditions across concurrent requests
  - Refund on RAG / search pipeline failures
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional
from bson import ObjectId
from fastapi import HTTPException, Request, Depends
from loguru import logger

from app.database import db

FREE_DAILY_LIMIT = 1
STANDARD_DAILY_LIMIT = 20


def _users():
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    return db.database.users


async def get_current_user_from_request(request: Request) -> Optional[dict]:
    """Resolve the user from the JWT principal, Authorization header, or request state."""
    principal = getattr(request.state, "principal", None)
    sub = None
    if isinstance(principal, dict):
        sub = principal.get("sub")
    elif principal:
        sub = getattr(principal, "sub", None)

    if not sub or sub == "anonymous":
        # Check Authorization Bearer header directly
        auth_header = request.headers.get("authorization") or ""
        scheme, _, token = auth_header.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            try:
                from app.api.security import decode_token
                payload = decode_token(token.strip())
                sub = payload.get("sub")
            except Exception:
                pass

    if not sub or sub == "anonymous":
        # Also check x-user-id header or user_id query param
        sub = request.headers.get("x-user-id") or request.query_params.get("user_id")

    if not sub or sub == "anonymous":
        return None

    # Find user by id, email, or ObjectId
    or_clauses = [{"id": str(sub)}, {"email": str(sub).strip().lower()}]
    try:
        if ObjectId.is_valid(str(sub)):
            or_clauses.append({"_id": ObjectId(str(sub))})
    except Exception:
        pass

    return await _users().find_one({"$or": or_clauses})


async def plan_guard(request: Request):
    """
    Enforce daily query limits.
    Free: 1/day. Standard: 20/day (only while subscription is active and not expired).
    Atomic increment prevents race conditions.
    """
    user = await get_current_user_from_request(request)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if not user:
        # Anonymous users: apply Free tier limit (1/day) tracked by IP
        client_ip = request.client.host if request.client else "unknown"
        anon_key = f"anon_{client_ip}"
        anon_doc = await _users().find_one({"id": anon_key})
        if not anon_doc:
            await _users().insert_one({
                "id": anon_key,
                "email": f"{anon_key}@anonymous.local",
                "plan": "Free",
                "dailyQueries": {"count": 0, "date": now},
                "created_at": now
            })
            anon_doc = await _users().find_one({"id": anon_key})
        user = anon_doc

    # Check expiration date
    raw_ends = (
        user.get("subscriptionEndsAt")
        or user.get("subscription_ends_at")
        or user.get("plan_cancels_at")
    )
    if isinstance(raw_ends, str):
        try:
            raw_ends = datetime.fromisoformat(raw_ends.replace("Z", "+00:00"))
        except Exception:
            raw_ends = None
    if isinstance(raw_ends, datetime) and raw_ends.tzinfo is None:
        raw_ends = raw_ends.replace(tzinfo=timezone.utc)

    plan_name = str(user.get("plan") or "free").strip().lower()

    # Determine effective plan
    is_standard = (
        plan_name in ("standard", "pro", "premium")
        and (raw_ends is None or raw_ends > now)
    )

    # Lazy downgrade: if subscription has expired, revert to Free
    if plan_name in ("standard", "pro", "premium") and raw_ends and raw_ends <= now:
        await _users().update_one(
            {"_id": user["_id"]},
            {"$set": {
                "plan": "free",
                "planColor": "bg-[#E7E8EA] text-[#44474D]",
                "subscriptionEndsAt": None,
                "subscription_ends_at": None,
                "autoRenew": False,
                "cancelAtPeriodEnd": False
            }}
        )
        is_standard = False
        plan_name = "free"
        logger.info(f"Lazy downgrade applied for user {user.get('email') or user.get('id')}")

    daily_limit = STANDARD_DAILY_LIMIT if is_standard else FREE_DAILY_LIMIT

    # Daily reset check
    dq = user.get("dailyQueries") or {"count": 0, "date": now}
    last_reset = dq.get("date")
    if isinstance(last_reset, str):
        try:
            last_reset = datetime.fromisoformat(last_reset.replace("Z", "+00:00"))
        except Exception:
            last_reset = None
    if isinstance(last_reset, datetime) and last_reset.tzinfo is None:
        last_reset = last_reset.replace(tzinfo=timezone.utc)

    if not last_reset or last_reset < today_start:
        # Reset counter for a fresh day
        await _users().update_one(
            {"_id": user["_id"]},
            {"$set": {"dailyQueries": {"count": 0, "date": now}}}
        )
        current_count = 0
    else:
        current_count = int(dq.get("count", 0))

    reset_time = (today_start + timedelta(days=1)).isoformat()

    # Check limit before incrementing
    if current_count >= daily_limit:
        raise HTTPException(
            status_code=403,
            detail={
                "message": f"Daily limit reached ({daily_limit}/day).",
                "requiresUpgrade": not is_standard,
                "dailyLimit": daily_limit,
                "queriesUsed": current_count,
                "resetAt": reset_time
            }
        )

    # Atomic increment - prevents race conditions across tabs/requests
    result = await _users().update_one(
        {
            "_id": user["_id"],
            "dailyQueries.count": {"$lt": daily_limit}
        },
        {"$inc": {"dailyQueries.count": 1}}
    )

    if result.modified_count == 0:
        # Another concurrent request took the final slot
        raise HTTPException(
            status_code=403,
            detail={
                "message": f"Daily limit reached ({daily_limit}/day).",
                "requiresUpgrade": not is_standard,
                "dailyLimit": daily_limit,
                "queriesUsed": daily_limit,
                "resetAt": reset_time
            }
        )

    # Save state on request for refund-on-failure
    request.state.plan_guard_incremented = True
    request.state.plan_guard_user_id = user["_id"]
    request.state.effective_plan = "standard" if is_standard else "free"

    return user


async def refund_query(request: Request) -> None:
    """Refund a query counter if the RAG search pipeline failed."""
    if getattr(request.state, "plan_guard_incremented", False):
        user_id = getattr(request.state, "plan_guard_user_id", None) or getattr(request.state, "user_id", None)
        if user_id:
            try:
                target_id = ObjectId(str(user_id)) if ObjectId.is_valid(str(user_id)) else user_id
                await _users().update_one(
                    {"$or": [{"_id": target_id}, {"id": str(user_id)}], "dailyQueries.count": {"$gt": 0}},
                    {"$inc": {"dailyQueries.count": -1}}
                )
                logger.info(f"Query quota refunded for user {user_id} due to pipeline failure")
            except Exception as e:
                logger.warning(f"Could not refund query quota: {e}")
            finally:
                request.state.plan_guard_incremented = False
