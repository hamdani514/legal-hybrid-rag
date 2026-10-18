"""
Payment Controller endpoints:
  - POST /api/payments/cancel-subscription
  - POST /api/payments/reactivate-subscription
  - GET  /api/payments/status
  - POST /api/payments/create-checkout-session
  - POST /api/payments/confirm
  - GET  /api/payments/config
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

import stripe
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel

from app.api.security import require_user
from app.config import settings
from app.database import db
from modules.payment.webhook import _extract_period_end

router = APIRouter()


def _stripe():
    key = (settings.STRIPE_SECRET_KEY or "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="Payments are not configured on this server.")
    stripe.api_key = key
    return stripe


def _users():
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    return db.database.users


async def _current_user(request: Request, supplied_id: Optional[str] = None) -> dict:
    principal = getattr(request.state, "principal", None)
    sub = principal.get("sub") if isinstance(principal, dict) else getattr(principal, "sub", None)
    identifier = (sub if sub and sub != "anonymous" else (supplied_id or "")).strip()

    if not identifier:
        # Fall back to Authorization Bearer header
        auth_header = request.headers.get("authorization") or ""
        scheme, _, token = auth_header.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            try:
                from app.api.security import decode_token
                payload = decode_token(token.strip())
                identifier = str(payload.get("sub") or "")
            except Exception:
                pass

    if not identifier:
        raise HTTPException(status_code=401, detail="Please sign in to manage subscriptions.")

    query = [{"id": identifier}, {"email": identifier.lower()}]
    try:
        if ObjectId.is_valid(identifier):
            query.append({"_id": ObjectId(identifier)})
    except Exception:
        pass

    user = await _users().find_one({"$or": query})
    if not user:
        raise HTTPException(status_code=404, detail="Account not found. Please sign in again.")
    return user


def _is_paid(user: dict) -> bool:
    plan = str(user.get("plan") or "").strip().lower()
    return plan in ("standard", "pro", "premium")


# ============================================================
# STEP 2 — Cancel Subscription Endpoint
# ============================================================
class CancelRequest(BaseModel):
    user_id: Optional[str] = None


@router.post("/cancel-subscription")
async def cancel_subscription(request: Request, body: Optional[CancelRequest] = None):
    """
    Cancel subscription at period end.
    User keeps access until period end. Card is NOT detached here.
    """
    client = _stripe()
    user = await _current_user(request, body.user_id if body else None)

    if not _is_paid(user):
        raise HTTPException(status_code=400, detail="Not on an active Standard plan.")

    subscription_id = user.get("stripeSubscriptionId") or user.get("stripe_subscription_id")
    if not subscription_id:
        raise HTTPException(status_code=400, detail="No active Stripe subscription found.")

    try:
        # Stripe recommended cancel_at with min_period_end (May 2025 deprecation replacement)
        subscription = client.Subscription.modify(
            subscription_id,
            cancel_at="min_period_end"
        )
    except stripe.error.StripeError as e:
        logger.warning(f"cancel_at='min_period_end' failed: {e}. Trying cancel_at_period_end=True fallback.")
        try:
            subscription = client.Subscription.modify(
                subscription_id,
                cancel_at_period_end=True
            )
        except stripe.error.StripeError as err:
            raise HTTPException(status_code=400, detail=str(err))

    # Version-agnostic period_end extraction (Stripe Basil API + legacy)
    period_end = _extract_period_end(subscription)
    now = datetime.now(timezone.utc)

    # Update local DB — do NOT touch plan, do NOT detach card
    await _users().update_one(
        {"_id": user["_id"]},
        {"$set": {
            "cancelAtPeriodEnd": True,
            "cancel_at_period_end": True,
            "cancellationRequestedAt": now,
            "subscriptionEndsAt": period_end,
            "subscription_ends_at": period_end,
            "plan_cancels_at": period_end,
            "autoRenew": False,
            "auto_renew": False
        }}
    )

    logger.info(f"Subscription cancelled at period end for user {user.get('email')}, ends at {period_end}")

    return {
        "message": "Subscription cancelled. Access until period end.",
        "endsAt": period_end.isoformat(),
        "note": "Card will be removed automatically at period end."
    }


# ============================================================
# STEP 3 — Reactivate Endpoint
# ============================================================
class ReactivateRequest(BaseModel):
    user_id: Optional[str] = None


@router.post("/reactivate-subscription")
async def reactivate_subscription(request: Request, body: Optional[ReactivateRequest] = None):
    """Reactivate a subscription that was scheduled for cancellation."""
    client = _stripe()
    user = await _current_user(request, body.user_id if body else None)

    subscription_id = user.get("stripeSubscriptionId") or user.get("stripe_subscription_id")
    if not subscription_id:
        raise HTTPException(status_code=400, detail="No active Stripe subscription to reactivate.")

    try:
        # Clear the scheduled cancellation
        subscription = client.Subscription.modify(
            subscription_id,
            cancel_at=""
        )
    except stripe.error.StripeError as e:
        logger.warning(f"cancel_at='' failed: {e}. Trying cancel_at_period_end=False fallback.")
        try:
            subscription = client.Subscription.modify(
                subscription_id,
                cancel_at_period_end=False
            )
        except stripe.error.StripeError as err:
            raise HTTPException(status_code=400, detail=str(err))

    period_end = _extract_period_end(subscription)

    await _users().update_one(
        {"_id": user["_id"]},
        {"$set": {
            "cancelAtPeriodEnd": False,
            "cancel_at_period_end": False,
            "cancellationRequestedAt": None,
            "autoRenew": True,
            "auto_renew": True,
            "subscriptionEndsAt": period_end,
            "subscription_ends_at": period_end,
            "plan_cancels_at": None,
        }}
    )

    logger.info(f"Subscription reactivated for user {user.get('email')}, renewed until {period_end}")

    return {
        "message": "Subscription reactivated. Will auto-renew.",
        "endsAt": period_end.isoformat()
    }


# ============================================================
# STEP 9 — Update Status Endpoint
# ============================================================
@router.get("/status")
async def get_status(request: Request, user_id: Optional[str] = None):
    """
    Returns user's real-time plan, auto-renewal, card info, and daily quota.
    Enforces lazy downgrade if expired.
    """
    user = await _current_user(request, user_id)
    now = datetime.now(timezone.utc)

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
    is_standard = (
        plan_name in ("standard", "pro", "premium")
        and (raw_ends is None or raw_ends > now)
    )

    # Lazy downgrade
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

    # Daily reset calculation
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
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
        current_count = 0
    else:
        current_count = int(dq.get("count", 0))

    daily_limit = 20 if is_standard else 1

    return {
        "plan": "standard" if is_standard else "free",
        "is_paid": is_standard,
        "cancelAtPeriodEnd": bool(user.get("cancelAtPeriodEnd") or user.get("cancel_at_period_end")),
        "subscriptionEndsAt": raw_ends.isoformat() if raw_ends else None,
        "cardLast4": user.get("cardLast4"),
        "cardBrand": user.get("cardBrand"),
        "dailyQueriesUsed": current_count,
        "dailyQueriesLimit": daily_limit,
        "autoRenew": bool(user.get("autoRenew", True) if user.get("autoRenew") is not None else user.get("auto_renew", True)),
        "subscription_history": user.get("subscription_history") or [],
    }


# ============================================================
# Checkout and Confirmation
# ============================================================
class CheckoutRequest(BaseModel):
    user_id: Optional[str] = None


@router.post("/create-checkout-session")
async def create_checkout_session(request: Request, body: Optional[CheckoutRequest] = None):
    client = _stripe()
    price_id = (settings.STRIPE_PRICE_ID or "").strip()
    if not price_id:
        raise HTTPException(status_code=503, detail="No subscription price is configured.")

    user = await _current_user(request, body.user_id if body else None)
    if _is_paid(user):
        raise HTTPException(status_code=400, detail="You are already on the Standard plan.")

    base = (settings.FRONTEND_URL or "").rstrip("/") or "http://localhost:5173"
    params = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "client_reference_id": str(user.get("id") or user.get("_id")),
        "metadata": {"user_id": str(user.get("id") or user.get("_id")), "email": user.get("email") or ""},
        "success_url": f"{base}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{base}/payment/cancel",
    }

    cust_id = user.get("stripeCustomerId") or user.get("stripe_customer_id")
    if cust_id:
        params["customer"] = cust_id
    elif user.get("email"):
        params["customer_email"] = user["email"]

    try:
        session = client.checkout.Session.create(**params)
    except Exception as e:
        if params.get("customer") and "customer" in str(e).lower():
            params.pop("customer", None)
            if user.get("email"):
                params["customer_email"] = user["email"]
            session = client.checkout.Session.create(**params)
        else:
            raise HTTPException(status_code=502, detail=f"Stripe checkout creation failed: {e}")

    return {"url": session.url, "session_id": session.id}


class ConfirmRequest(BaseModel):
    session_id: str
    user_id: Optional[str] = None


@router.post("/confirm")
async def confirm_checkout(request: Request, body: ConfirmRequest):
    client = _stripe()
    user = await _current_user(request, body.user_id)
    user_id = str(user.get("id") or user.get("_id"))

    try:
        session = client.checkout.Session.retrieve(body.session_id.strip()).to_dict()
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"That payment could not be found: {e}")

    owner = session.get("client_reference_id") or (session.get("metadata") or {}).get("user_id")
    if owner and owner != user_id:
        raise HTTPException(status_code=403, detail="That payment belongs to another account.")

    if session.get("payment_status") not in ("paid", "no_payment_required"):
        return {"confirmed": False, "plan": user.get("plan"), "message": "Stripe has not confirmed payment yet."}

    from modules.payment.webhook import handle_checkout_completed
    await handle_checkout_completed(session)

    fresh = await _users().find_one({"_id": user["_id"]})
    return {"confirmed": True, "plan": (fresh or {}).get("plan"), "is_paid": _is_paid(fresh or {})}


@router.get("/config")
async def payment_config():
    return {
        "enabled": bool((settings.STRIPE_SECRET_KEY or "").strip() and (settings.STRIPE_PRICE_ID or "").strip()),
        "publishable_key": settings.STRIPE_PUBLISHABLE_KEY or "",
        "paid_plan": settings.PAID_PLAN,
        "test_mode": (settings.STRIPE_SECRET_KEY or "").startswith("sk_test_"),
    }
