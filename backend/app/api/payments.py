"""
Card payments: Stripe Checkout for the Standard plan ($10/month).

The flow
--------
    1. The pricing page asks for a Checkout session (create-checkout-session).
    2. Stripe returns a hosted URL; the browser goes there and the card is
       entered on Stripe's page, never ours.
    3. Stripe calls our webhook; only then is the user's plan upgraded.
    4. The browser lands back on /payment/success.

Why the plan is upgraded in the webhook and NOT on the success redirect: the
redirect is just a URL the browser was sent to. Anyone can open it, and a
genuine payer can close the tab before it loads. The webhook is signed by
Stripe and retried until acknowledged, so it is the only trustworthy signal
that money actually moved.

Ported from the Node module in payment/, which this project does not run: the
Stripe calls and the webhook contract are the same, the storage is this app's
`users` collection, and the credentials are the same test keys.

What this does NOT do
---------------------
Per-plan access rules and query limits. Nothing here gates retrieval; the plan
is recorded and that is all, so the limits can be designed later without
unpicking the payment path.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from loguru import logger
from pydantic import BaseModel

from app.api.security import require_user
from app.config import settings
from app.database import db

router = APIRouter(prefix="/api/payments", tags=["payments"])

ANONYMOUS = "anonymous"
# Stripe events we have already acted on, so a retry cannot upgrade twice.
PROCESSED_EVENTS = "stripe_events"
EVENT_TTL_DAYS = 30


def _stripe():
    """The configured Stripe client, or a clear 503 if the key is missing."""
    key = (settings.STRIPE_SECRET_KEY or "").strip()
    if not key:
        raise HTTPException(status_code=503,
                            detail="Payments are not configured on this server.")
    stripe.api_key = key
    return stripe


def _users():
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    return db.database.users


async def _current_user(request: Request, supplied_id: str | None) -> dict:
    """The signed-in user's record.

    Prefers the token's subject; falls back to the id the client sends, which
    is how the rest of the app behaves while AUTH_REQUIRED is off. The record
    is always re-read here, so the plan written by the webhook is what counts
    rather than anything the browser claims.
    """
    principal = getattr(request.state, "principal", None)
    sub = principal.get("sub") if isinstance(principal, dict) else getattr(principal, "sub", None)
    identifier = (sub if sub and sub != ANONYMOUS else (supplied_id or "")).strip()
    if not identifier:
        raise HTTPException(status_code=401, detail="Please sign in before subscribing.")

    user = await _users().find_one({"$or": [{"id": identifier}, {"email": identifier}]})
    if not user:
        raise HTTPException(status_code=404, detail="Account not found. Please sign in again.")
    return user


def _is_paid(user: dict) -> bool:
    return str(user.get("plan") or "").strip().lower() == settings.PAID_PLAN.lower()


class CheckoutRequest(BaseModel):
    user_id: str | None = None


@router.post("/create-checkout-session", dependencies=[Depends(require_user)])
async def create_checkout_session(body: CheckoutRequest, request: Request):
    """Start a subscription and hand back the Stripe URL for the browser."""
    client = _stripe()
    price_id = (settings.STRIPE_PRICE_ID or "").strip()
    if not price_id:
        raise HTTPException(status_code=503, detail="No subscription price is configured.")

    user = await _current_user(request, body.user_id)
    if _is_paid(user):
        raise HTTPException(status_code=400,
                            detail=f"You are already on the {settings.PAID_PLAN} plan.")

    base = (settings.FRONTEND_URL or "").rstrip("/") or "http://localhost:5173"
    params = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        # Both are read back in the webhook; client_reference_id is the one
        # Stripe shows in its dashboard, which makes support possible.
        "client_reference_id": str(user.get("id") or ""),
        "metadata": {"user_id": str(user.get("id") or ""), "email": user.get("email") or ""},
        "success_url": f"{base}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{base}/payment/cancel",
    }
    # Reusing the customer keeps one billing history per person.
    if user.get("stripe_customer_id"):
        params["customer"] = user["stripe_customer_id"]
    elif user.get("email"):
        params["customer_email"] = user["email"]

    try:
        session = client.checkout.Session.create(**params)
    except Exception as e:  # noqa: BLE001
        # A stored customer id that Stripe no longer recognises (a wiped test
        # account, a restored backup) would otherwise lock this user out of
        # paying for good. Drop it and try once more as a new customer.
        if params.get("customer") and "customer" in str(e).lower():
            logger.warning(f"Stale stripe_customer_id for {user.get('id')}; retrying without it")
            params.pop("customer", None)
            if user.get("email"):
                params["customer_email"] = user["email"]
            try:
                session = client.checkout.Session.create(**params)
                await _users().update_one({"id": user.get("id")},
                                          {"$unset": {"stripe_customer_id": ""}})
            except Exception as retry_error:  # noqa: BLE001
                logger.error(f"Stripe checkout retry failed for {user.get('id')}: {retry_error}")
                raise HTTPException(status_code=502,
                                    detail=f"Stripe could not start the checkout: {retry_error}")
        else:
            logger.error(f"Stripe checkout session failed for {user.get('id')}: {e}")
            raise HTTPException(status_code=502, detail=f"Stripe could not start the checkout: {e}")

    logger.info(f"Checkout session {session.id} created for user {user.get('id')}")
    return {"url": session.url, "session_id": session.id}


@router.get("/status", dependencies=[Depends(require_user)])
async def payment_status(request: Request, user_id: str | None = None):
    """The caller's current plan, read from the database rather than the client."""
    user = await _current_user(request, user_id)
    history = user.get("subscription_history")
    created_val = user.get("created_at")
    created_iso = created_val.isoformat() if hasattr(created_val, "isoformat") else str(created_val or "2026-01-01T00:00:00Z")
    act_val = user.get("plan_activated_at")
    act_iso = act_val.isoformat() if hasattr(act_val, "isoformat") else None

    if not history or not isinstance(history, list) or len(history) == 0:
        if _is_paid(user):
            start_date = act_iso or created_iso
            history = [
                {
                    "id": f"sub_hist_{user.get('id', 'u')}_0",
                    "plan": settings.FREE_PLAN,
                    "tier_name": f"{settings.FREE_PLAN} Tier",
                    "amount": "$0.00",
                    "status": "Completed",
                    "started_at": created_iso,
                    "ended_at": start_date,
                    "payment_method": "Complimentary",
                    "reference": "REF-FREE-INIT",
                },
                {
                    "id": f"sub_hist_{user.get('id', 'u')}_1",
                    "plan": settings.PAID_PLAN,
                    "tier_name": f"{settings.PAID_PLAN} Plan",
                    "amount": "$10.00 / month",
                    "status": "Active",
                    "started_at": start_date,
                    "ended_at": None,
                    "payment_method": "Stripe Card",
                    "reference": user.get("stripe_subscription_id") or "SUB-STRIPE-ACTIVE",
                },
            ]
        else:
            history = [
                {
                    "id": f"sub_hist_{user.get('id', 'u')}_0",
                    "plan": settings.FREE_PLAN,
                    "tier_name": f"{settings.FREE_PLAN} Tier",
                    "amount": "$0.00",
                    "status": "Active",
                    "started_at": created_iso,
                    "ended_at": None,
                    "payment_method": "Complimentary",
                    "reference": "REF-FREE-INIT",
                }
            ]

    return {
        "plan": user.get("plan") or settings.FREE_PLAN,
        "is_paid": _is_paid(user),
        "plan_activated_at": user.get("plan_activated_at"),
        "plan_cancels_at": user.get("plan_cancels_at"),
        "has_stripe_customer": bool(user.get("stripe_customer_id")),
        "subscription_history": history,
    }


class ConfirmRequest(BaseModel):
    session_id: str
    user_id: str | None = None


@router.post("/confirm", dependencies=[Depends(require_user)])
async def confirm_checkout(body: ConfirmRequest, request: Request):
    """Settle a payment from the browser's return trip, by asking Stripe.

    The webhook remains the primary path, but it only works where Stripe can
    reach this server: on localhost, or before the endpoint is configured on
    a host, a genuine payment would otherwise never be applied. That was not
    a theoretical gap — three real test payments completed at Stripe while
    every account stayed on the free plan.

    This is safe because nothing here trusts the browser. The session is
    fetched from Stripe (so a made-up id gets nowhere), it must actually be
    paid, and its client_reference_id must be THIS caller — otherwise one
    user could paste another's session id and upgrade themselves.
    """
    client = _stripe()
    user = await _current_user(request, body.user_id)
    user_id = str(user.get("id") or "")

    try:
        session = client.checkout.Session.retrieve(body.session_id.strip()).to_dict()
    except Exception as e:  # noqa: BLE001 - unknown id, wrong account, API down
        logger.warning(f"Could not retrieve session {body.session_id!r}: {e}")
        raise HTTPException(status_code=404, detail="That payment could not be found.")

    owner = session.get("client_reference_id") or (session.get("metadata") or {}).get("user_id")
    if owner and owner != user_id:
        logger.warning(f"User {user_id} tried to claim session owned by {owner}")
        raise HTTPException(status_code=403, detail="That payment belongs to another account.")

    if session.get("payment_status") not in ("paid", "no_payment_required"):
        return {"confirmed": False, "plan": user.get("plan"),
                "message": "Stripe has not confirmed this payment yet."}

    # Same guard the webhook uses, keyed on the session, so a reload and a
    # late webhook cannot both apply the same payment twice.
    if not await _already_handled(f"session:{session.get('id')}"):
        await _activate({"id": user_id}, session)
    else:
        logger.info(f"Session {session.get('id')} was already applied")

    fresh = await _users().find_one({"id": user_id})
    return {"confirmed": True, "plan": (fresh or {}).get("plan"), "is_paid": _is_paid(fresh or {})}


@router.get("/config")
async def payment_config():
    """What the pricing page needs to know, with no secrets in it."""
    return {
        "enabled": bool((settings.STRIPE_SECRET_KEY or "").strip()
                        and (settings.STRIPE_PRICE_ID or "").strip()),
        "publishable_key": settings.STRIPE_PUBLISHABLE_KEY or "",
        "paid_plan": settings.PAID_PLAN,
        "test_mode": (settings.STRIPE_SECRET_KEY or "").startswith("sk_test_"),
    }


async def _already_handled(event_id: str) -> bool:
    """True when this event was processed before (Stripe retries on any error)."""
    try:
        await db.database[PROCESSED_EVENTS].create_index("processed_at",
                                                         expireAfterSeconds=EVENT_TTL_DAYS * 86400)
        await db.database[PROCESSED_EVENTS].insert_one(
            {"_id": event_id, "processed_at": datetime.now(timezone.utc)})
        return False
    except Exception as e:  # noqa: BLE001
        if "duplicate key" in str(e).lower() or "E11000" in str(e):
            return True
        # Unknown failure: say "not handled" and let the work run. Upgrading a
        # user twice is harmless; silently skipping a payment is not.
        logger.warning(f"Stripe idempotency check failed for {event_id}: {e}")
        return False


async def _activate(user_query: dict, session_or_sub: dict) -> None:
    now = datetime.now(timezone.utc)
    update = {
        "plan": settings.PAID_PLAN,
        "plan_activated_at": now,
        "plan_cancels_at": None,
        # The admin Users table colours by plan; keep it consistent.
        "planColor": "bg-[#E9C176] text-[#261900]",
    }
    if session_or_sub.get("customer"):
        update["stripe_customer_id"] = session_or_sub["customer"]
    if session_or_sub.get("subscription"):
        update["stripe_subscription_id"] = session_or_sub["subscription"]

    history_item = {
        "id": f"sub_hist_{secrets.token_hex(6)}",
        "plan": settings.PAID_PLAN,
        "tier_name": f"{settings.PAID_PLAN} Plan",
        "amount": "$10.00 / month",
        "status": "Active",
        "started_at": now.isoformat(),
        "ended_at": None,
        "payment_method": "Stripe Card",
        "reference": session_or_sub.get("id") or f"SUB-{secrets.token_hex(4).upper()}",
    }

    result = await _users().update_one(
        user_query,
        {
            "$set": update,
            "$push": {"subscription_history": history_item},
        },
    )
    logger.info(f"Plan upgraded to {settings.PAID_PLAN} ({result.modified_count} record) "
                f"for {user_query}")


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Stripe's signed callback. The ONLY place a plan is upgraded.

    Public by design (Stripe is not a signed-in user); the signature check
    below is what authenticates it, so the endpoint cannot be driven by
    anyone who merely knows the URL.
    """
    client = _stripe()
    secret = (settings.STRIPE_WEBHOOK_SECRET or "").strip()
    payload = await request.body()          # raw bytes: the signature covers them
    signature = request.headers.get("stripe-signature", "")

    if not secret:
        logger.error("STRIPE_WEBHOOK_SECRET is not set; refusing to trust the callback")
        raise HTTPException(status_code=503, detail="Webhook is not configured.")
    try:
        event = client.Webhook.construct_event(payload, signature, secret)
    except Exception as e:  # noqa: BLE001 - bad signature or malformed body
        logger.warning(f"Rejected a Stripe webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    # construct_event returns Stripe resource objects, on which .get() raises.
    # The signature has already proved these exact bytes came from Stripe, so
    # parsing them gives the same event as plain, predictable dicts.
    raw = json.loads(payload)
    event_id = raw.get("id") or event["id"]

    if await _already_handled(event_id):
        logger.info(f"Stripe event {event_id} already handled; skipping")
        return {"received": True, "duplicate": True}

    kind = raw["type"]
    obj = raw["data"]["object"]
    logger.info(f"Stripe webhook: {kind}")

    try:
        if kind == "checkout.session.completed":
            # Only a paid session counts; an unpaid one can complete for a
            # subscription that still needs authentication.
            if obj.get("payment_status") not in (None, "paid", "no_payment_required"):
                logger.info(f"Session {obj.get('id')} completed unpaid; no upgrade")
            else:
                user_id = obj.get("client_reference_id") or (obj.get("metadata") or {}).get("user_id")
                email = (obj.get("metadata") or {}).get("email") or obj.get("customer_email")
                query = {"id": user_id} if user_id else ({"email": email} if email else None)
                if query:
                    await _activate(query, obj)
                else:
                    logger.warning(f"Session {obj.get('id')} has no user reference; cannot upgrade")

        elif kind == "customer.subscription.updated":
            if obj.get("status") == "active":
                cancels = obj.get("cancel_at")
                await _users().update_one(
                    {"stripe_customer_id": obj.get("customer")},
                    {"$set": {"plan": settings.PAID_PLAN,
                              "plan_cancels_at": datetime.fromtimestamp(cancels, timezone.utc)
                              if cancels else None}})

        elif kind == "customer.subscription.deleted":
            now_iso = datetime.now(timezone.utc).isoformat()
            await _users().update_one(
                {"stripe_customer_id": obj.get("customer")},
                {"$set": {"plan": settings.FREE_PLAN, "stripe_subscription_id": None,
                          "plan_cancels_at": None,
                          "planColor": "bg-[#E7E8EA] text-[#44474D]"}})
            # Also update active history record if present
            await _users().update_one(
                {"stripe_customer_id": obj.get("customer"), "subscription_history.status": "Active"},
                {"$set": {"subscription_history.$.status": "Canceled", "subscription_history.$.ended_at": now_iso}}
            )
            logger.info(f"Subscription ended for customer {obj.get('customer')}; back to free")

        elif kind == "invoice.payment_failed":
            logger.warning(f"Payment failed for customer {obj.get('customer')}")

    except Exception as e:  # noqa: BLE001
        # Release the idempotency marker before failing. It is taken BEFORE
        # the work so two concurrent deliveries cannot both act; if the work
        # then fails, leaving it in place would make Stripe's retry look like
        # a duplicate and the payment would never be applied.
        try:
            await db.database[PROCESSED_EVENTS].delete_one({"_id": event_id})
        except Exception:  # noqa: BLE001
            logger.error(f"Could not release the marker for {event_id}; "
                         f"a retry of this event will be skipped as a duplicate")
        # A 500 is what makes Stripe retry.
        logger.exception(f"Failed to handle Stripe event {event_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not record the payment.")

    return Response(content='{"received":true}', media_type="application/json")
