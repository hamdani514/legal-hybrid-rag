"""
Deleting an account deletes everything that belongs to it, and stops its billing.

Used by both "delete my account" (app/api/auth.py) and an admin deleting a
user (app/api/admin.py). Before this, the first removed the account and its
chats only, and the second only the account record, so:

* a paid subscription kept charging the card every month after the account
  was gone (nothing told Stripe);
* the search log kept every query with the user's id, support messages kept
  the email, and the profile picture stayed on Drive.

Order matters: billing first. If Stripe cannot confirm the subscription is
cancelled, nothing is deleted and the caller is told why (otherwise the person
would keep paying for an account that no longer exists, with no way to sign in
and cancel). Everything after that is best effort and logged.
"""

from __future__ import annotations

import asyncio
import re

from fastapi import HTTPException
from loguru import logger

from app.config import settings
from app.database import db

BILLING_FAILED = ("Your subscription could not be cancelled just now, so your account was not deleted "
                  "(you would otherwise keep being charged). Please try again in a few minutes or contact support.")


def _ids(user: dict) -> tuple[set[str], str]:
    subs = {user.get("stripeSubscriptionId"), user.get("stripe_subscription_id")}
    subs |= set(user.get("subscriptionsToCancel") or [])
    customer = user.get("stripeCustomerId") or user.get("stripe_customer_id") or ""
    return {s for s in subs if s}, customer


def _end_billing_sync(user: dict) -> dict:
    """Cancel every subscription this account pays for and delete the Stripe
    customer (its saved cards go with it; invoices stay in Stripe as records)."""
    subs, customer = _ids(user)
    if not subs and not customer:
        return {"cancelled": [], "customer_deleted": False}
    key = (settings.STRIPE_SECRET_KEY or "").strip()
    if not key:
        raise RuntimeError("payments are not configured, so a subscription cannot be cancelled")
    import stripe
    stripe.api_key = key
    if customer:
        # Also any subscription the account record does not know about.
        for sub in stripe.Subscription.list(customer=customer, status="all", limit=100).auto_paging_iter():
            if sub["status"] not in ("canceled", "incomplete_expired"):
                subs.add(sub["id"])
    cancelled = []
    for sub_id in sorted(subs):
        try:
            stripe.Subscription.cancel(sub_id)
            cancelled.append(sub_id)
        except Exception as e:  # noqa: BLE001
            text = str(e).lower()
            if "no such subscription" in text or "canceled" in text or "cancelled" in text:
                continue  # already over
            raise
    deleted = False
    if customer:
        try:
            stripe.Customer.delete(customer)
            deleted = True
        except Exception as e:  # noqa: BLE001 - the subscriptions are already cancelled
            logger.warning(f"Stripe customer could not be deleted (subscriptions are cancelled): {type(e).__name__}")
    return {"cancelled": cancelled, "customer_deleted": deleted}


async def remove_account(user: dict) -> dict:
    """Stop billing, then delete the account and everything stored for it.
    Raises 502 (and deletes nothing) if billing cannot be stopped."""
    user_id = str(user.get("id") or "")
    email = (user.get("email") or "").strip().lower()
    try:
        billing = await asyncio.to_thread(_end_billing_sync, user)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Account {user_id}: subscription could not be cancelled, account kept: {type(e).__name__}: {e}")
        raise HTTPException(status_code=502, detail=BILLING_FAILED) from None

    report = {"billing": billing}
    d = db.database
    report["account"] = (await d.users.delete_one({"_id": user["_id"]})).deleted_count
    keys = [k for k in (user_id, email) if k]
    steps = {
        "chats": lambda: d.chat_sessions.delete_many({"user_key": {"$in": keys}}),
        "support_messages": lambda: d.support_queries.delete_many({"email": email}) if email else None,
        "pending_signup": lambda: d.pending_registrations.delete_many({"email": email}) if email else None,
        "signin_attempts": lambda: d.auth_throttle.delete_many(
            {"_id": {"$regex": f":{re.escape(email)}$"}}) if email else None,
    }
    for name, run in steps.items():
        try:
            result = run()
            report[name] = (await result).deleted_count if result is not None else 0
        except Exception as e:  # noqa: BLE001
            logger.error(f"Account {user_id}: could not remove {name}: {type(e).__name__}")
    if user.get("avatar_file_id"):
        try:
            from app.services.google_drive_service import google_drive_service
            report["avatar"] = await google_drive_service.delete_avatar(user["avatar_file_id"])
        except Exception as e:  # noqa: BLE001
            logger.error(f"Account {user_id}: profile picture not removed: {type(e).__name__}")
    try:
        from app.retrieval.query_recorder import forget_user
        report["search_log"] = await asyncio.to_thread(forget_user, user_id) if user_id else 0
    except Exception as e:  # noqa: BLE001
        logger.error(f"Account {user_id}: search log entries not removed: {type(e).__name__}")
    logger.info(f"Account {user_id} deleted with its data: {report}")
    return report
