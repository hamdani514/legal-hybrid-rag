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
from fastapi import HTTPException, Request
from loguru import logger

from app.api.security import caller_id, caller_is_admin
from app.database import db
from modules.payment import plans

FREE_DAILY_LIMIT = plans.PLANS[plans.FREE]["daily_limit"]
STANDARD_DAILY_LIMIT = plans.PLANS[plans.STANDARD]["daily_limit"]
PREMIUM_DAILY_LIMIT = plans.PLANS[plans.PREMIUM]["daily_limit"]


def _users():
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    return db.database.users


async def caller_user(request: Request) -> Optional[dict]:
    """The caller's account, from the verified token only (security.caller_id)."""
    sub = caller_id(request)
    or_clauses = [{"id": sub}, {"email": sub.strip().lower()}]
    if ObjectId.is_valid(sub):
        or_clauses.append({"_id": ObjectId(sub)})
    return await _users().find_one({"$or": or_clauses})


async def plan_guard(request: Request):
    """
    Enforce daily query limits.
    Free: 2/day. Standard: 20/day. Premium: 50/day (paid plans only while the
    subscription is active and not expired).
    Atomic increment prevents race conditions.
    """
    # Admins are not on a plan, and have no searches to count.
    if caller_is_admin(request):
        request.state.effective_plan = plans.PREMIUM
        return None

    user = await caller_user(request)
    if not user:
        # A valid token for an account that no longer exists.
        raise HTTPException(status_code=401, detail="This account no longer exists. Please sign in again.")
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

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

    # No counter on the record yet (older and some Google accounts): create it, or
    # the atomic update below finds no field to compare and reports the limit reached.
    if not last_reset or last_reset < today_start or "count" not in (user.get("dailyQueries") or {}):
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
    # Admins are not on a plan; a signed-in admin may use every tool.
    key = plans.PREMIUM if caller_is_admin(request) else plans.effective_plan(await caller_user(request))
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
