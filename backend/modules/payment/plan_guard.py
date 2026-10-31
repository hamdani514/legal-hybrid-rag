"""
Tier-based rate limiting (Plan Guard).
Enforces daily query quotas (limits in modules/payment/plans.py):
  - Free plan: 2 queries/day
  - Standard plan: 20 queries/day (only while subscription is valid)
  - Premium plan: 50 queries/day (only while subscription is valid)
and the paid-only features (require_feature).
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
from modules.payment import plans

FREE_DAILY_LIMIT = plans.PLANS[plans.FREE]["daily_limit"]
STANDARD_DAILY_LIMIT = plans.PLANS[plans.STANDARD]["daily_limit"]
PREMIUM_DAILY_LIMIT = plans.PLANS[plans.PREMIUM]["daily_limit"]


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
    Free: 2/day. Standard: 20/day. Premium: 50/day (paid plans only while the
    subscription is active and not expired).
    Atomic increment prevents race conditions.
    """
    user = await get_current_user_from_request(request)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if not user:
        # Anonymous users: apply the Free tier limit, tracked by IP
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

    # Effective plan. A paid plan past its end date is Free: downgrade it
    # here too, in case the expiry job has not run yet.
    if plans.is_expired(user, now):
        await _users().update_one({"_id": user["_id"]}, {"$set": dict(plans.DOWNGRADE_FIELDS)})
        logger.info(f"Lazy downgrade applied for user {user.get('email') or user.get('id')}")
    plan_key = plans.effective_plan(user, now)
    daily_limit = plans.plan(plan_key)["daily_limit"]
    limit_message = (
        f"You have used all {daily_limit} searches on the {plans.plan(plan_key)['name']} plan today. "
        + ("Upgrade for more searches, or try again after midnight UTC."
           if plan_key != plans.PREMIUM else "Your searches reset at midnight UTC.")
    )

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
                "message": limit_message,
                "requiresUpgrade": plan_key != plans.PREMIUM,
                "plan": plan_key,
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
                "message": limit_message,
                "requiresUpgrade": plan_key != plans.PREMIUM,
                "plan": plan_key,
                "dailyLimit": daily_limit,
                "queriesUsed": daily_limit,
                "resetAt": reset_time
            }
        )

    # Save state on request for refund-on-failure
    request.state.plan_guard_incremented = True
    request.state.plan_guard_user_id = user["_id"]
    request.state.effective_plan = plan_key

    return user


async def current_plan(request: Request) -> str:
    """The caller's effective plan, without counting a search."""
    cached = getattr(request.state, "effective_plan", None)
    if cached:
        return cached
    principal = getattr(request.state, "principal", None)
    role = principal.get("role") if isinstance(principal, dict) else getattr(principal, "role", None)
    sub = principal.get("sub") if isinstance(principal, dict) else getattr(principal, "sub", None)
    # Admins are not on a plan; a signed-in admin token may use every tool.
    if role == "admin" and sub and sub != "anonymous":
        key = plans.PREMIUM
    else:
        key = plans.effective_plan(await get_current_user_from_request(request))
    request.state.effective_plan = key
    return key


async def require_feature(request: Request, feature: str) -> str:
    """403 unless the caller's plan includes ``feature``; returns the plan.

    The detail is a dict the frontend reads to show the upgrade prompt:
    ``{"message", "requiresUpgrade": true, "feature", "plan"}``.
    """
    key = await current_plan(request)
    if not plans.has_feature(key, feature):
        label = plans.FEATURE_LABELS.get(feature, "This feature")
        raise HTTPException(
            status_code=403,
            detail={
                "message": f"{label} is part of the Standard and Premium plans. Upgrade to unlock it.",
                "requiresUpgrade": True,
                "feature": feature,
                "plan": key,
            },
        )
    return key


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
