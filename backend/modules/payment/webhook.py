"""
Stripe Webhook Handler:
  1. checkout.session.completed: new subscription activated via checkout
  2. customer.subscription.updated: updates cancellation tracking without downgrading
  3. customer.subscription.deleted: subscription ended; detaches payment method, purges card, downgrades to Free
  4. invoice.payment_succeeded: extends subscription window on cycle renewal
  5. invoice.payment_failed: enters 24h grace period
Features:
  - Raw body signature verification
  - Idempotency via processed_events collection with 30-day TTL index
  - Version-agnostic period_end extraction (Stripe Basil 2025 API items.data[0] + legacy)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Optional

import stripe
from bson import ObjectId
from fastapi import APIRouter, Header, HTTPException, Request, Response
from loguru import logger

from app.config import settings
from app.database import db

router = APIRouter()

PROCESSED_COLLECTION = "processed_events"
EVENT_TTL_SECONDS = 86400 * 30  # 30 days


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


def _processed_events():
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    return db.database[PROCESSED_COLLECTION]


def _extract_period_end_raw(subscription) -> Optional[int]:
    """Extract Unix timestamp for current_period_end.
    Version-agnostic: Handles both new Basil API (items.data[0].current_period_end)
    and legacy (subscription.current_period_end)."""
    # Try new location first (Basil API, March 2025)
    try:
        items = getattr(subscription, "items", None) or (subscription.get("items") if isinstance(subscription, dict) else None)
        data = getattr(items, "data", None) or (items.get("data") if isinstance(items, dict) else None)
        if data and len(data) > 0:
            first_item = data[0]
            ts = getattr(first_item, "current_period_end", None) or (first_item.get("current_period_end") if isinstance(first_item, dict) else None)
            if ts:
                return int(ts)
    except (AttributeError, IndexError, TypeError):
        pass

    # Fallback to legacy location
    try:
        ts = getattr(subscription, "current_period_end", None) or (subscription.get("current_period_end") if isinstance(subscription, dict) else None)
        if ts:
            return int(ts)
    except (AttributeError, TypeError):
        pass

    return None


def _extract_period_end(subscription) -> datetime:
    """Version-agnostic: returns a timezone-aware UTC datetime."""
    ts = _extract_period_end_raw(subscription)
    if ts:
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    return datetime.now(timezone.utc) + timedelta(days=30)


# ============================================================
# HANDLER 1 — checkout.session.completed (initial subscribe)
# ============================================================
async def handle_checkout_completed(session: dict) -> None:
    client = _stripe()
    user_id = session.get("client_reference_id") or (session.get("metadata") or {}).get("user_id")
    email = (session.get("metadata") or {}).get("email") or session.get("customer_email")

    query = None
    if user_id:
        clauses = [{"id": str(user_id)}, {"email": str(user_id).strip().lower()}]
        try:
            if ObjectId.is_valid(str(user_id)):
                clauses.append({"_id": ObjectId(str(user_id))})
        except Exception:
            pass
        query = {"$or": clauses}
    elif email:
        query = {"email": email.strip().lower()}

    if not query:
        logger.warning(f"checkout.session.completed {session.get('id')} has no user reference; cannot upgrade")
        return

    user = await _users().find_one(query)
    if not user:
        logger.warning(f"User for checkout session {session.get('id')} not found in DB")
        return

    customer_id = session.get("customer")
    subscription_id = session.get("subscription")

    period_end = None
    if subscription_id:
        try:
            sub = client.Subscription.retrieve(subscription_id)
            period_end = _extract_period_end(sub)
        except Exception as e:
            logger.warning(f"Could not retrieve subscription {subscription_id}: {e}")

    if not period_end:
        period_end = datetime.now(timezone.utc) + timedelta(days=30)

    # Fetch default payment method details
    pm_id = None
    card_last4 = None
    card_brand = None
    if customer_id:
        try:
            customer = client.Customer.retrieve(customer_id, expand=["invoice_settings.default_payment_method"])
            inv_settings = getattr(customer, "invoice_settings", None) or (customer.get("invoice_settings") if isinstance(customer, dict) else None)
            pm = getattr(inv_settings, "default_payment_method", None) if inv_settings else None
            if pm:
                pm_id = getattr(pm, "id", None) or (pm.get("id") if isinstance(pm, dict) else None)
                card = getattr(pm, "card", None) or (pm.get("card") if isinstance(pm, dict) else None)
                if card:
                    card_last4 = getattr(card, "last4", None) or (card.get("last4") if isinstance(card, dict) else None)
                    card_brand = getattr(card, "brand", None) or (card.get("brand") if isinstance(card, dict) else None)
        except Exception as e:
            logger.warning(f"Could not retrieve default payment method for customer {customer_id}: {e}")

    now = datetime.now(timezone.utc)
    update = {
        "plan": "Standard",
        "planColor": "bg-[#CFE6FF] text-[#0B3B6F]",
        "stripeCustomerId": customer_id,
        "stripe_customer_id": customer_id,
        "stripeSubscriptionId": subscription_id,
        "stripe_subscription_id": subscription_id,
        "stripePaymentMethodId": pm_id,
        "cardLast4": card_last4,
        "cardBrand": card_brand,
        "planActivatedAt": now,
        "plan_activated_at": now,
        "subscriptionEndsAt": period_end,
        "subscription_ends_at": period_end,
        "plan_cancels_at": None,
        "autoRenew": True,
        "auto_renew": True,
        "cancelAtPeriodEnd": False,
        "cancel_at_period_end": False,
        "dailyQueries": {"count": 0, "date": now},
    }

    history_item = {
        "id": f"sub_hist_{session.get('id', 'pay')[-8:]}",
        "plan": "Standard",
        "tier_name": "Standard Plan",
        "amount": "$10.00 / month",
        "status": "Active",
        "started_at": now.isoformat(),
        "ended_at": None,
        "payment_method": f"{card_brand or 'Card'} •••• {card_last4}" if card_last4 else "Stripe Card",
        "reference": subscription_id or session.get("id"),
    }

    await _users().update_one(
        {"_id": user["_id"]},
        {
            "$set": update,
            "$push": {"subscription_history": history_item}
        }
    )
    logger.info(f"✅ Activated Standard plan for user {user.get('email')}")


# ============================================================
# HANDLER 2 — customer.subscription.updated (fires on cancel)
# ============================================================
async def handle_subscription_updated(subscription: dict) -> None:
    """
    Subscription updated — could be cancellation or reactivation.
    DO NOT downgrade here. User still has paid access until period end.
    """
    customer_id = subscription.get("customer")
    if not customer_id:
        return

    user = await _users().find_one({
        "$or": [{"stripeCustomerId": customer_id}, {"stripe_customer_id": customer_id}]
    })
    if not user:
        return

    cancel_at_period_end = bool(
        subscription.get("cancel_at_period_end")
        or subscription.get("cancel_at")
    )
    period_end = _extract_period_end(subscription)

    await _users().update_one(
        {"_id": user["_id"]},
        {"$set": {
            "cancelAtPeriodEnd": cancel_at_period_end,
            "cancel_at_period_end": cancel_at_period_end,
            "subscriptionEndsAt": period_end,
            "subscription_ends_at": period_end,
            "autoRenew": not cancel_at_period_end,
            "auto_renew": not cancel_at_period_end,
            "plan_cancels_at": period_end if cancel_at_period_end else None
        }}
    )
    logger.info(f"🔄 Subscription updated for {user.get('email')}: cancel_at_period_end={cancel_at_period_end}")


# ============================================================
# HANDLER 3 — customer.subscription.deleted (period end)
# ============================================================
async def handle_subscription_deleted(subscription: dict) -> None:
    """
    Subscription has fully ended. NOW we:
    1. Detach the card (allowed now that subscription is inactive)
    2. Downgrade user to Free
    3. Reset daily quota and purge card details
    """
    client = _stripe()
    customer_id = subscription.get("customer")
    if not customer_id:
        return

    user = await _users().find_one({
        "$or": [{"stripeCustomerId": customer_id}, {"stripe_customer_id": customer_id}]
    })
    if not user:
        return

    card_purged = False
    pm_id = user.get("stripePaymentMethodId")

    # Step 1: Unset as default and Step 2: Detach
    if pm_id and customer_id:
        try:
            client.Customer.modify(
                customer_id,
                invoice_settings={"default_payment_method": None}
            )
            client.PaymentMethod.detach(pm_id)
            card_purged = True
            logger.info(f"✅ Card {pm_id} detached for {user.get('email')}")
        except stripe.error.StripeError as e:
            logger.warning(f"⚠️ Card detach error for {user.get('email')}: {e}")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    update = {
        "plan": "free",
        "planColor": "bg-[#E7E8EA] text-[#44474D]",
        "stripeSubscriptionId": None,
        "stripe_subscription_id": None,
        "cancelAtPeriodEnd": False,
        "cancel_at_period_end": False,
        "subscriptionEndsAt": None,
        "subscription_ends_at": None,
        "plan_cancels_at": None,
        "autoRenew": False,
        "auto_renew": False,
        "cancellationRequestedAt": None,
        "dailyQueries": {"count": 0, "date": now}
    }

    if card_purged or not pm_id:
        update.update({
            "stripePaymentMethodId": None,
            "cardLast4": None,
            "cardBrand": None
        })

    await _users().update_one(
        {"_id": user["_id"]},
        {"$set": update}
    )

    # Update subscription history record if active
    await _users().update_one(
        {"_id": user["_id"], "subscription_history.status": "Active"},
        {"$set": {"subscription_history.$.status": "Canceled", "subscription_history.$.ended_at": now_iso}}
    )
    logger.info(f"⬇️ Downgraded to Free: {user.get('email')}")


# ============================================================
# HANDLER 4 — invoice.payment_succeeded (Renewal)
# ============================================================
async def handle_invoice_paid(invoice: dict) -> None:
    """Successful renewal — extend subscription window."""
    if invoice.get("billing_reason") != "subscription_cycle":
        return

    customer_id = invoice.get("customer")
    if not customer_id:
        return

    user = await _users().find_one({
        "$or": [{"stripeCustomerId": customer_id}, {"stripe_customer_id": customer_id}]
    })
    if not user:
        return

    sub_id = invoice.get("subscription")
    period_end = None
    if sub_id:
        try:
            client = _stripe()
            sub = client.Subscription.retrieve(sub_id)
            period_end = _extract_period_end(sub)
        except Exception as e:
            logger.warning(f"Could not retrieve subscription {sub_id} on invoice paid: {e}")

    if not period_end:
        period_end = datetime.now(timezone.utc) + timedelta(days=30)

    now = datetime.now(timezone.utc)
    await _users().update_one(
        {"_id": user["_id"]},
        {"$set": {
            "plan": "Standard",
            "subscriptionEndsAt": period_end,
            "subscription_ends_at": period_end,
            "planActivatedAt": now,
            "plan_activated_at": now
        }}
    )
    logger.info(f"✅ Renewed subscription for {user.get('email')} until {period_end}")


# ============================================================
# HANDLER 5 — invoice.payment_failed (dunning / grace period)
# ============================================================
async def handle_invoice_failed(invoice: dict) -> None:
    """Payment failed on renewal — grant 24h grace period."""
    customer_id = invoice.get("customer")
    if not customer_id:
        return

    user = await _users().find_one({
        "$or": [{"stripeCustomerId": customer_id}, {"stripe_customer_id": customer_id}]
    })
    if not user:
        return

    now = datetime.now(timezone.utc)
    grace_end = now + timedelta(hours=24)
    await _users().update_one(
        {"_id": user["_id"]},
        {"$set": {
            "subscriptionEndsAt": grace_end,
            "subscription_ends_at": grace_end,
            "paymentFailedAt": now
        }}
    )
    logger.warning(f"⚠️ Payment failed for {user.get('email')} — granted 24h grace period")


HANDLERS = {
    "checkout.session.completed": handle_checkout_completed,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
    "invoice.payment_succeeded": handle_invoice_paid,
    "invoice.payment_failed": handle_invoice_failed,
}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="stripe-signature")
):
    """
    Stripe webhook handler with raw body verification and idempotency check.
    """
    client = _stripe()
    raw_body = await request.body()
    secret = (settings.STRIPE_WEBHOOK_SECRET or "").strip()

    if not secret:
        logger.error("STRIPE_WEBHOOK_SECRET is not configured")
        raise HTTPException(status_code=503, detail="Webhook is not configured.")

    sig_header = stripe_signature or request.headers.get("stripe-signature", "")
    try:
        event = client.Webhook.construct_event(
            payload=raw_body,
            sig_header=sig_header,
            secret=secret
        )
    except Exception as e:
        logger.warning(f"Stripe signature verification failed: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid webhook signature: {e}")

    # Idempotency check with processed_events collection
    events_col = _processed_events()
    event_id = event.get("id") or (json.loads(raw_body).get("id"))
    event_type = event.get("type") or (json.loads(raw_body).get("type"))

    try:
        await events_col.create_index("eventId", unique=True)
        await events_col.create_index("processedAt", expireAfterSeconds=EVENT_TTL_SECONDS)
        await events_col.insert_one({
            "eventId": event_id,
            "type": event_type,
            "processedAt": datetime.now(timezone.utc)
        })
    except Exception as e:
        if "duplicate key" in str(e).lower() or "e11000" in str(e).lower():
            logger.info(f"Duplicate event {event_id} skipped")
            return {"received": True, "duplicate": True}
        logger.warning(f"Idempotency recording error: {e}")

    # Route event to handler
    handler = HANDLERS.get(event_type)
    if handler:
        try:
            obj = event.get("data", {}).get("object") or json.loads(raw_body).get("data", {}).get("object")
            await handler(obj)
        except Exception as e:
            logger.error(f"Webhook handler error for {event_type}: {e}")
            # Release idempotency marker so Stripe retries can be processed if desired
            try:
                await events_col.delete_one({"eventId": event_id})
            except Exception:
                pass
            raise HTTPException(status_code=500, detail="Webhook handler processing failed.")

    return {"received": True}
