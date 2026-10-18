"""
Scheduled background tasks (Cron jobs).
Backup sweep for expired or cancelled subscriptions where webhook may have been missed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import stripe
from loguru import logger

from app.config import settings
from app.database import db

scheduler = AsyncIOScheduler()


def _stripe():
    key = (settings.STRIPE_SECRET_KEY or "").strip()
    if key:
        stripe.api_key = key
    return stripe


@scheduler.scheduled_job("cron", minute=0)  # Runs every hour on the hour
async def expire_canceled_subscriptions():
    """
    Backup sweep: find users whose subscription ended but webhook was missed.
    Also detaches payment methods for these users.
    """
    if db.database is None:
        return

    now = datetime.now(timezone.utc)
    now_naive = now.replace(tzinfo=None)
    client = _stripe()

    cursor = db.database.users.find({
        "plan": {"$regex": "^standard$", "$options": "i"},
        "$or": [
            {"autoRenew": False},
            {"auto_renew": False},
            {"cancelAtPeriodEnd": True},
            {"cancel_at_period_end": True}
        ],
        "$and": [
            {
                "$or": [
                    {"subscriptionEndsAt": {"$lt": now}},
                    {"subscriptionEndsAt": {"$lt": now_naive}},
                    {"subscription_ends_at": {"$lt": now}},
                    {"subscription_ends_at": {"$lt": now_naive}},
                    {"plan_cancels_at": {"$lt": now}},
                    {"plan_cancels_at": {"$lt": now_naive}}
                ]
            }
        ]
    })

    expired_count = 0
    async for user in cursor:
        card_purged = False
        pm_id = user.get("stripePaymentMethodId")
        customer_id = user.get("stripeCustomerId") or user.get("stripe_customer_id")

        if pm_id and customer_id and settings.STRIPE_SECRET_KEY:
            try:
                # Step 1: Unset as default
                client.Customer.modify(
                    customer_id,
                    invoice_settings={"default_payment_method": None}
                )
                # Step 2: Detach
                client.PaymentMethod.detach(pm_id)
                card_purged = True
                logger.info(f"✅ Cron detached card {pm_id} for user {user.get('email')}")
            except Exception as e:
                logger.warning(f"Cron card detach failed for {user.get('email')}: {e}")

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

        await db.database.users.update_one(
            {"_id": user["_id"]},
            {"$set": update}
        )

        # Update active history record
        await db.database.users.update_one(
            {"_id": user["_id"], "subscription_history.status": "Active"},
            {"$set": {"subscription_history.$.status": "Canceled", "subscription_history.$.ended_at": now_iso}}
        )

        expired_count += 1
        logger.info(f"🕐 Cron expired subscription for user: {user.get('email')}")

    if expired_count > 0:
        logger.info(f"Completed subscription expiration sweep: {expired_count} users reverted to Free.")


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        logger.info("🕒 Background subscription scheduler started.")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("🛑 Background subscription scheduler stopped.")
