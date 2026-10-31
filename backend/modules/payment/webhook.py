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


from modules.payment import plans

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


def _current_subscription(user: dict) -> Optional[str]:
    return user.get("stripeSubscriptionId") or user.get("stripe_subscription_id")


def _is_replaced(user: dict, subscription_id: Optional[str]) -> bool:
    """An event about a subscription the user has since replaced.

    Switching Standard <-> Premium opens a new subscription and cancels the
    old one. Stripe then reports the old one as updated and deleted; those
    events must not move the user back to the old plan or down to Free.
    """
    current = _current_subscription(user)
    return bool(subscription_id and current and subscription_id != current)


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
    # The plan bought: named in the session metadata by create_checkout_session;
    # else read from the subscription's price; else Standard (older sessions).
    bought = plans.plan_key((session.get("metadata") or {}).get("plan"))
    if subscription_id:
        try:
            sub = client.Subscription.retrieve(subscription_id)
            period_end = _extract_period_end(sub)
            bought = plans.plan_of_subscription(sub) or bought
        except Exception as e:
            logger.warning(f"Could not retrieve subscription {subscription_id}: {e}")
    if bought not in plans.PAID_PLANS:
        bought = plans.STANDARD
    bought_plan = plans.plan(bought)

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
        "plan": bought_plan["name"],
        "planColor": bought_plan["color"],
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

    # A plan switch: the subscription this one replaces (named at checkout,
    # else the one on record). It is cancelled once the new one is in place.
    replaced = (session.get("metadata") or {}).get("replaces_subscription") or _current_subscription(user)
    if replaced == subscription_id:
        replaced = None

    history_item = {
        "id": f"sub_hist_{session.get('id', 'pay')[-8:]}",
        "plan": bought_plan["name"],
        "tier_name": f"{bought_plan['name']} Plan",
        "amount": plans.price_label(bought),
        "status": "Active",
        "started_at": now.isoformat(),
        "ended_at": None,
        "payment_method": f"{card_brand or 'Card'} •••• {card_last4}" if card_last4 else "Stripe Card",
        "reference": subscription_id or session.get("id"),
    }

    # Close the history entries of earlier subscriptions, then record this one
    # once (the browser's confirm and the webhook may both deliver it).
    if subscription_id and isinstance(user.get("subscription_history"), list):
        await _users().update_one(
            {"_id": user["_id"]},
            {"$set": {"subscription_history.$[old].status": "Changed",
                      "subscription_history.$[old].ended_at": now.isoformat()}},
            array_filters=[{"old.status": "Active", "old.reference": {"$ne": subscription_id}}],
        )
    await _users().update_one({"_id": user["_id"]}, {"$set": update})
    await _users().update_one(
        {"_id": user["_id"], "subscription_history.reference": {"$ne": history_item["reference"]}},
        {"$push": {"subscription_history": history_item}},
    )
    logger.info(f"✅ Activated {bought_plan['name']} plan for user {user.get('email')}")

    if replaced:
        # The new subscription is recorded first, so the deletion event this
        # triggers is recognised as a replaced subscription and ignored.
        # Prorated: the unused days of the old plan become a credit on the
        # customer's balance, taken off their next invoice.
        try:
            client.Subscription.cancel(replaced, prorate=True)
            logger.info(f"Cancelled replaced subscription {replaced} for {user.get('email')}")
        except Exception as e:
            # Already cancelled (a repeat delivery) or not found: nothing to do.
            logger.warning(f"Could not cancel replaced subscription {replaced}: {e}")


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

    if _is_replaced(user, subscription.get("id")):
        logger.info(f"Ignoring update for replaced subscription {subscription.get('id')}")
        return

    cancel_at_period_end = bool(
        subscription.get("cancel_at_period_end")
        or subscription.get("cancel_at")
    )
    period_end = _extract_period_end(subscription)

    # A price change (Standard <-> Premium) moves the user to that plan.
    changes = {}
    moved_to = plans.plan_of_subscription(subscription)
    if moved_to:
        changes = {"plan": plans.plan(moved_to)["name"], "planColor": plans.plan(moved_to)["color"]}

    await _users().update_one(
        {"_id": user["_id"]},
        {"$set": {
            **changes,
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

    if _is_replaced(user, subscription.get("id")):
        logger.info(f"Ignoring deletion for replaced subscription {subscription.get('id')}")
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
        "plan": plans.PLANS[plans.FREE]["name"],
        "planColor": plans.PLANS[plans.FREE]["color"],
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
    if _is_replaced(user, sub_id):
        logger.info(f"Ignoring renewal for replaced subscription {sub_id}")
        return
    period_end = None
    # The plan renewed: the subscription's price, else what the user is on.
    renewed = plans.plan_key(user.get("plan"))
    if sub_id:
        try:
            client = _stripe()
            sub = client.Subscription.retrieve(sub_id)
            period_end = _extract_period_end(sub)
            renewed = plans.plan_of_subscription(sub) or renewed
        except Exception as e:
            logger.warning(f"Could not retrieve subscription {sub_id} on invoice paid: {e}")
    if renewed not in plans.PAID_PLANS:
        renewed = plans.STANDARD

    if not period_end:
        period_end = datetime.now(timezone.utc) + timedelta(days=30)

    now = datetime.now(timezone.utc)
    await _users().update_one(
        {"_id": user["_id"]},
        {"$set": {
            "plan": plans.plan(renewed)["name"],
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
    if _is_replaced(user, invoice.get("subscription")):
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

    # The signature is verified, so the body is Stripe's. Work on it as plain
    # dicts: from stripe-python 8 on, an Event is not a dict and has no .get(),
    # and every handler below reads its object with .get().
    event = json.loads(raw_body)

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
