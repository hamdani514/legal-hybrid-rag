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
        "plan": {"$regex": "^(standard|premium|pro)$", "$options": "i"},
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
            "plan": "Free",
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


@scheduler.scheduled_job("cron", minute=30)  # every hour, at half past
async def retry_replaced_cancellations():
    """Cancel subscriptions a plan switch replaced, where cancelling failed at the
    time: otherwise the user would keep paying for both plans."""
    if db.database is None:
        return
    from modules.payment.webhook import cancel_replaced

    client = _stripe()
    async for user in db.database.users.find({"subscriptionsToCancel.0": {"$exists": True}}):
        for subscription_id in list(user.get("subscriptionsToCancel") or []):
            if subscription_id == (user.get("stripeSubscriptionId") or user.get("stripe_subscription_id")):
                # Never the one they are on now.
                await db.database.users.update_one({"_id": user["_id"]}, {"$pull": {"subscriptionsToCancel": subscription_id}})
                continue
            await cancel_replaced(client, user, subscription_id)


async def _backup(full: bool) -> None:
    """The scheduled backup (scripts/backup_db.py), off the event loop. A failure is
    logged as an ERROR, so it reaches errors.log and Sentry (app/monitoring.py)."""
    import asyncio

    from scripts import backup_db

    kind = "full (with search indexes)" if full else "daily"
    try:
        summary = await asyncio.to_thread(backup_db.run_scheduled, full)
        logger.info(f"Backup, {kind}: {summary}")
    except Exception as e:  # noqa: BLE001
        logger.exception(f"Backup, {kind}, FAILED: {e}")


@scheduler.scheduled_job("cron", minute=15)  # hourly
async def check_google_drive():
    """Refresh the Drive sign-in, so an expiry is noticed (and alerted) within the
    hour instead of when someone wonders why files are missing from Drive."""
    import asyncio

    from app.services.google_drive_service import google_drive_service

    google_drive_service.health = await asyncio.to_thread(google_drive_service.check_health)


@scheduler.scheduled_job("cron", hour=4, minute=30)  # daily
async def prune_search_log():
    """Delete search-log records past QUERY_LOG_RETENTION_DAYS."""
    import asyncio

    from app.retrieval.query_recorder import prune_older_than

    days = float(getattr(settings, "QUERY_LOG_RETENTION_DAYS", 30) or 0)
    removed = await asyncio.to_thread(prune_older_than, days)
    if removed:
        logger.info(f"Search log: removed {removed} records older than {days:.0f} days")


def _schedule_backups() -> None:
    if not getattr(settings, "BACKUP_ENABLED", True):
        logger.info("Scheduled backups are off (BACKUP_ENABLED=false).")
        return
    hour = int(getattr(settings, "BACKUP_HOUR_UTC", 2)) % 24
    weekday = (getattr(settings, "BACKUP_FULL_WEEKDAY", "sun") or "").strip().lower()
    scheduler.add_job(_backup, "cron", hour=hour, minute=0, timezone="UTC", args=[False],
                      id="backup_daily", replace_existing=True, misfire_grace_time=3600, coalesce=True)
    if weekday:
        # An hour later than the daily one, so the two never run together.
        scheduler.add_job(_backup, "cron", day_of_week=weekday, hour=(hour + 1) % 24, minute=0, timezone="UTC",
                          args=[True], id="backup_full", replace_existing=True, misfire_grace_time=3600, coalesce=True)
    logger.info(f"Backups scheduled: daily at {hour:02d}:00 UTC" + (f", with search indexes on {weekday}" if weekday else "")
                + (f"; copies to {settings.BACKUP_COPY_DIR}" if getattr(settings, "BACKUP_COPY_DIR", "") else
                   "; no second copy (set BACKUP_COPY_DIR)"))


def start_scheduler():
    if not scheduler.running:
        _schedule_backups()
        # Also once right after startup, so the admin page has a status at once.
        from datetime import timedelta
        scheduler.add_job(check_google_drive, "date", run_date=datetime.now(timezone.utc) + timedelta(seconds=20),
                          id="drive_check_startup", replace_existing=True)
        scheduler.start()
        logger.info("🕒 Background subscription scheduler started.")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("🛑 Background subscription scheduler stopped.")
