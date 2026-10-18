from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, Depends
from bson import ObjectId
from app.models.user import User
from app.middleware.auth import get_current_user

FREE_DAILY_LIMIT = 1
STANDARD_DAILY_LIMIT = 20


async def plan_guard(user = Depends(get_current_user)):
    """
    Atomic daily query limit check.
    Uses find_one_and_update to guarantee no race condition.
    """
    user_id = user["_id"] if isinstance(user, dict) else user.id

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Load user doc for plan check
    user_doc = await User.find_one(User.id == ObjectId(user_id))
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")

    is_standard = bool(
        str(user_doc.plan).lower() in ("standard", "pro", "premium")
        and user_doc.subscriptionEndsAt
        and (user_doc.subscriptionEndsAt.replace(tzinfo=timezone.utc) if user_doc.subscriptionEndsAt.tzinfo is None else user_doc.subscriptionEndsAt) > now
    )

    # Lazy downgrade if subscription expired but cron missed it
    if str(user_doc.plan).lower() == "standard" and not is_standard:
        await User.find_one(User.id == user_doc.id).update(
            {"$set": {"plan": "Free"}}
        )

    daily_limit = STANDARD_DAILY_LIMIT if is_standard else FREE_DAILY_LIMIT

    # Reset counter if it's a new day
    dq = user_doc.dailyQueries or {"count": 0, "date": now}
    dq_date = dq.get("date", now)
    if dq_date and hasattr(dq_date, "replace") and dq_date.tzinfo is None:
        dq_date = dq_date.replace(tzinfo=timezone.utc)
    if not dq_date or dq_date < today_start:
        await User.find_one(User.id == user_doc.id).update(
            {"$set": {"dailyQueries": {"count": 0, "date": now}}}
        )

    # ✅ ATOMIC check+increment using collection directly
    collection = (
        User.get_pymongo_collection()
        if hasattr(User, "get_pymongo_collection")
        else User.get_motor_collection()
    )
    result = await collection.find_one_and_update(
        {
            "_id": ObjectId(user_id),
            "dailyQueries.count": {"$lt": daily_limit},
        },
        {"$inc": {"dailyQueries.count": 1}},
        return_document=True,
    )

    if not result:
        raise HTTPException(
            status_code=403,
            detail={
                "message": f"Daily limit reached ({daily_limit}/day).",
                "requiresUpgrade": not is_standard,
                "dailyLimit": daily_limit,
            },
        )

    return {
        "_id": user_id,
        "plan": "standard" if is_standard else "free",
        "refund_key": user_id,   # for refund on RAG failure
    }
