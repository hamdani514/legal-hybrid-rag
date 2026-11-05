"""
End-to-end check of the Stripe payment path.

    cd backend && DB_NAME=legal_rag_scratch_pay venv/Scripts/python.exe -m app.api.payments_selfcheck

It talks to Stripe for real, in TEST mode, with the keys in backend/.env: a
genuine Checkout session is created and its hosted URL returned. The webhook
is then driven with a correctly SIGNED payload built from the real webhook
secret, which is the only way to prove the signature check accepts a true
callback and rejects a forged one.

No live money can move: the run refuses unless the secret key is sk_test_.
Users are created in a scratch database, which is dropped at the end.
"""

import asyncio
import hashlib
import hmac
import json
import sys
import time

import httpx

from app.config import settings

SCRATCH = "legal_rag_scratch_pay"
assert settings.DB_NAME == SCRATCH, f"refusing to run against {settings.DB_NAME!r}"
assert (settings.STRIPE_SECRET_KEY or "").startswith("sk_test_"), \
    "refusing to run: STRIPE_SECRET_KEY is not a test key"

import main  # noqa: E402
from app.api.security import create_access_token  # noqa: E402
from app.database import close_db, connect_db, db  # noqa: E402

RESULTS = []


def check(name, cond, info=""):
    RESULTS.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({info})" if info else ""))


def signed_headers(payload: bytes) -> dict:
    """A Stripe-Signature header Stripe's own verifier will accept."""
    ts = int(time.time())
    secret = settings.STRIPE_WEBHOOK_SECRET.strip()
    signature = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return {"stripe-signature": f"t={ts},v1={signature}", "content-type": "application/json"}


def event(kind, obj, event_id):
    return {"id": event_id, "object": "event", "type": kind,
            "data": {"object": obj}, "created": int(time.time())}


async def run():
    await connect_db()
    await db.client.drop_database(SCRATCH)
    users = db.database.users
    await users.insert_one({"id": "USr-9001", "email": "payer@gmail.com", "name": "Test Payer",
                            "plan": "Free", "status": "Active"})

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as c:
        U = {"Authorization": f"Bearer {create_access_token('USr-9001', 'user')}"}

        r = await c.get("/api/payments/config")
        cfg = r.json()
        check("config says payments are enabled and in test mode",
              cfg["enabled"] and cfg["test_mode"] and cfg["paid_plan"] == settings.PAID_PLAN)
        check("config leaks no secret key", "sk_" not in json.dumps(cfg))

        r = await c.get("/api/payments/status", headers=U)
        check("a new user starts unpaid", r.status_code == 200 and r.json()["is_paid"] is False,
              r.json().get("plan"))

        # --- the real Stripe call -------------------------------------
        r = await c.post("/api/payments/create-checkout-session", json={}, headers=U)
        body = r.json()
        url = body.get("url", "")
        check("Stripe returned a hosted checkout URL",
              r.status_code == 200 and url.startswith("https://checkout.stripe.com"),
              url[:58] + "…" if url else str(body)[:90])
        session_id = body.get("session_id", "")

        # --- the webhook is what actually upgrades --------------------
        session_obj = {"id": session_id or "cs_test_x", "object": "checkout.session",
                       "payment_status": "paid", "client_reference_id": "USr-9001",
                       "customer": "cus_selfcheck", "subscription": "sub_selfcheck",
                       "metadata": {"user_id": "USr-9001", "email": "payer@gmail.com"}}
        payload = json.dumps(event("checkout.session.completed", session_obj, "evt_sc_1")).encode()

        r = await c.post("/api/payments/webhook", content=payload,
                         headers={"stripe-signature": "t=1,v1=deadbeef",
                                  "content-type": "application/json"})
        check("a forged signature is rejected", r.status_code == 400, str(r.status_code))

        doc = await users.find_one({"id": "USr-9001"})
        check("the forged call did NOT upgrade the plan", doc["plan"] == "Free", doc["plan"])

        r = await c.post("/api/payments/webhook", content=payload, headers=signed_headers(payload))
        check("a correctly signed webhook is accepted", r.status_code == 200, str(r.status_code))

        doc = await users.find_one({"id": "USr-9001"})
        check(f"the plan is now {settings.PAID_PLAN}", doc["plan"] == settings.PAID_PLAN, doc["plan"])
        check("the Stripe customer and subscription are recorded",
              doc.get("stripe_customer_id") == "cus_selfcheck"
              and doc.get("stripe_subscription_id") == "sub_selfcheck")
        check("the activation time is stored", doc.get("plan_activated_at") is not None)

        r = await c.get("/api/payments/status", headers=U)
        check("status now reports the paid plan", r.json()["is_paid"] is True)

        # --- a retry of the same event must not double-apply ----------
        r = await c.post("/api/payments/webhook", content=payload, headers=signed_headers(payload))
        check("a replayed event is recognised as a duplicate",
              r.status_code == 200 and r.json().get("duplicate") is True)

        r = await c.post("/api/payments/create-checkout-session", json={}, headers=U)
        check("an already-paid user cannot start a second subscription",
              r.status_code == 400, str(r.status_code))

        # --- a plan switch: the replaced subscription's events are ignored
        # Switching Standard <-> Premium opens a new subscription and cancels
        # the old one; Stripe's update/deletion events for the old one must
        # not move the user back or down to Free.
        old_sub = {"id": "sub_replaced_old", "object": "subscription", "customer": "cus_selfcheck"}
        for kind, eid in (("customer.subscription.updated", "evt_sc_old_1"),
                          ("customer.subscription.deleted", "evt_sc_old_2")):
            body = json.dumps(event(kind, old_sub, eid)).encode()
            await c.post("/api/payments/webhook", content=body, headers=signed_headers(body))
        doc = await users.find_one({"id": "USr-9001"})
        check("events for a replaced subscription leave the plan alone",
              doc["plan"] == settings.PAID_PLAN and doc.get("stripeSubscriptionId") == "sub_selfcheck",
              doc["plan"])

        # --- cancellation returns the user to free --------------------
        sub_obj = {"id": "sub_selfcheck", "object": "subscription", "customer": "cus_selfcheck"}
        payload2 = json.dumps(event("customer.subscription.deleted", sub_obj, "evt_sc_2")).encode()
        r = await c.post("/api/payments/webhook", content=payload2, headers=signed_headers(payload2))
        doc = await users.find_one({"id": "USr-9001"})
        check("cancelling the subscription returns the user to free",
              r.status_code == 200 and doc["plan"] == settings.FREE_PLAN, doc["plan"])

        r = await c.post("/api/payments/create-checkout-session", json={},
                         headers={"Authorization": f"Bearer {create_access_token('USr-does-not-exist', 'user')}"})
        check("an unknown account cannot pay", r.status_code == 401, str(r.status_code))

        # --- confirm-on-return: the path that works without a webhook ---
        await users.update_one({"id": "USr-9001"},
                               {"$set": {"plan": "Free"},
                                # cus_selfcheck was invented for the webhook test and
                                # is not a real Stripe customer.
                                "$unset": {"stripe_customer_id": ""}})
        await users.insert_one({"id": "USr-9002", "email": "other@gmail.com",
                                "plan": "Free", "status": "Active"})

        r = await c.post("/api/payments/confirm", json={"session_id": "cs_test_not_real"},
                         headers={"Authorization": f"Bearer {create_access_token('USr-9001', 'user')}"})
        check("confirm rejects an id Stripe does not know", r.status_code == 404, str(r.status_code))

        # A real, still-unpaid session: must not upgrade anyone.
        made = await c.post("/api/payments/create-checkout-session", json={},
                           headers={"Authorization": f"Bearer {create_access_token('USr-9001', 'user')}"})
        unpaid_id = made.json()["session_id"]
        r = await c.post("/api/payments/confirm", json={"session_id": unpaid_id},
                         headers={"Authorization": f"Bearer {create_access_token('USr-9001', 'user')}"})
        check("confirm refuses a session Stripe has not marked paid",
              r.status_code == 200 and r.json()["confirmed"] is False, str(r.json()))
        doc = await users.find_one({"id": "USr-9001"})
        check("that left the plan alone", doc["plan"] == "Free", doc["plan"])

        r = await c.post("/api/payments/confirm", json={"session_id": unpaid_id},
                         headers={"Authorization": f"Bearer {create_access_token('USr-9002', 'user')}"})
        check("one user cannot claim another user's payment",
              r.status_code == 403, str(r.status_code))

    await replay_checks(users)
    await db.client.drop_database(SCRATCH)
    await close_db()


async def replay_checks(users) -> None:
    """An old or repeated checkout must never move a plan back or cancel the
    current subscription. Stripe is stubbed here: these need exact states."""
    from datetime import datetime, timedelta, timezone

    from modules.payment import webhook

    cancelled: list = []
    statuses = {}

    class Sub:
        fail_cancel = set()

        @staticmethod
        def retrieve(sid, **kw):
            return {"id": sid, "status": statuses.get(sid, "active"), "metadata": {},
                    "default_payment_method": {"id": "pm_test", "card": {"last4": "4242", "brand": "visa"}},
                    "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
                    "items": {"data": [{"price": {"id": "price_x"}}]}}

        @staticmethod
        def cancel(sid, **kw):
            if sid in Sub.fail_cancel:
                raise RuntimeError("Stripe could not be reached")
            cancelled.append(sid)

    class Customer:
        @staticmethod
        def retrieve(*a, **k):
            return {"invoice_settings": {"default_payment_method": None}}

    class Fake:
        pass

    Fake.Subscription, Fake.Customer = Sub, Customer
    real_stripe = webhook._stripe
    webhook._stripe = lambda: Fake
    now = datetime.now(timezone.utc)
    ts = lambda d: int((now + timedelta(days=d)).timestamp())
    try:
        await users.delete_many({"id": "USr-R"})
        await users.insert_one({"id": "USr-R", "email": "r@example.com", "plan": "Premium", "stripeCustomerId": "cus_r",
                                "stripeSubscriptionId": "sub_premium", "planActivatedAt": now,
                                "subscriptionEndsAt": now + timedelta(days=30),
                                "subscription_history": [{"plan": "Standard", "status": "Changed", "reference": "sub_standard_applied"},
                                                         {"plan": "Premium", "status": "Active", "reference": "sub_premium"}]})
        doc = lambda: users.find_one({"id": "USr-R"})
        session = lambda sid, sub, plan, created, replaces="": {
            "id": sid, "client_reference_id": "USr-R", "customer": "cus_r", "subscription": sub, "created": created,
            "metadata": {"user_id": "USr-R", "plan": plan, "replaces_subscription": replaces}}

        await webhook.handle_checkout_completed(session("cs_old", "sub_standard_older", "standard", ts(-10)))
        d = await doc()
        check("reopening an old Standard success link: plan and subscription unchanged",
              d["plan"] == "Premium" and d["stripeSubscriptionId"] == "sub_premium" and not cancelled, f"{d['plan']} {cancelled}")
        await webhook.handle_checkout_completed(session("cs_applied", "sub_standard_applied", "standard", ts(1)))
        d = await doc()
        check("a checkout applied before and since replaced: ignored, even if it looks new",
              d["plan"] == "Premium" and not cancelled, f"{d['plan']} {cancelled}")
        statuses["sub_canceled"] = "canceled"
        await webhook.handle_checkout_completed(session("cs_dead", "sub_canceled", "standard", ts(1), replaces="sub_premium"))
        d = await doc()
        check("a checkout whose subscription has ended: ignored", d["plan"] == "Premium" and not cancelled)
        await webhook.handle_checkout_completed(session("cs_switch", "sub_standard_new", "standard", ts(1), replaces="sub_premium"))
        d = await doc()
        check("a real switch still works: new plan, the old subscription cancelled once",
              d["plan"] == "Standard" and d["stripeSubscriptionId"] == "sub_standard_new" and cancelled == ["sub_premium"],
              f"{d['plan']} {cancelled}")
        await webhook.handle_checkout_completed(session("cs_switch", "sub_standard_new", "standard", ts(1), replaces="sub_premium"))
        d = await doc()
        refs = [h.get("reference") for h in d["subscription_history"]]
        check("the same switch delivered again: nothing cancelled twice, recorded once",
              cancelled == ["sub_premium"] and refs.count("sub_standard_new") == 1, f"{cancelled} {refs}")
        await webhook.handle_checkout_completed(session("cs_switch_old", "sub_premium", "premium", ts(-1)))
        d = await doc()
        check("the old Premium link opened after switching to Standard: still Standard",
              d["plan"] == "Standard" and d["stripeSubscriptionId"] == "sub_standard_new" and cancelled == ["sub_premium"],
              f"{d['plan']} {d['stripeSubscriptionId']} {cancelled}")
        await users.insert_one({"id": "USr-F", "email": "f@example.com", "plan": "Free"})
        await webhook.handle_checkout_completed({"id": "cs_free", "client_reference_id": "USr-F", "customer": "cus_f",
                                                 "subscription": "sub_f", "created": ts(0), "metadata": {"plan": "premium"}})
        f = await users.find_one({"id": "USr-F"})
        check("a first subscription from Free still activates", f["plan"] == "Premium" and f["stripeSubscriptionId"] == "sub_f")
        check("the card is recorded from the subscription", f.get("cardLast4") == "4242" and f.get("cardBrand") == "visa"
              and f.get("stripePaymentMethodId") == "pm_test", f.get("cardLast4"))

        # Cancelling the old subscription fails during a switch: kept and retried.
        await users.insert_one({"id": "USr-C", "email": "c@example.com", "plan": "Standard", "stripeCustomerId": "cus_c",
                                "stripeSubscriptionId": "sub_c_old", "planActivatedAt": now})
        Sub.fail_cancel.add("sub_c_old")
        cancelled.clear()
        await webhook.handle_checkout_completed({"id": "cs_c", "client_reference_id": "USr-C", "customer": "cus_c",
                                                 "subscription": "sub_c_new", "created": ts(1),
                                                 "metadata": {"plan": "premium", "replaces_subscription": "sub_c_old"}})
        c = await users.find_one({"id": "USr-C"})
        check("a failed cancel during a switch is remembered, not just logged",
              c["plan"] == "Premium" and c.get("subscriptionsToCancel") == ["sub_c_old"], c.get("subscriptionsToCancel"))
        import scheduled_tasks
        real_sched_stripe = scheduled_tasks._stripe
        scheduled_tasks._stripe = lambda: Fake
        try:
            await scheduled_tasks.retry_replaced_cancellations()
            c = await users.find_one({"id": "USr-C"})
            check("while Stripe still fails, the retry keeps it", c.get("subscriptionsToCancel") == ["sub_c_old"] and not cancelled)
            Sub.fail_cancel.clear()
            await scheduled_tasks.retry_replaced_cancellations()
            c = await users.find_one({"id": "USr-C"})
            check("the hourly retry cancels it once Stripe answers, then forgets it",
                  cancelled == ["sub_c_old"] and not c.get("subscriptionsToCancel"), f"{cancelled} {c.get('subscriptionsToCancel')}")
            await users.update_one({"id": "USr-C"}, {"$set": {"subscriptionsToCancel": ["sub_c_new"]}})
            await scheduled_tasks.retry_replaced_cancellations()
            c = await users.find_one({"id": "USr-C"})
            check("the retry never cancels the subscription the user is on now",
                  cancelled == ["sub_c_old"] and not c.get("subscriptionsToCancel"))
        finally:
            scheduled_tasks._stripe = real_sched_stripe
    finally:
        webhook._stripe = real_stripe


if __name__ == "__main__":
    asyncio.run(run())
    passed = sum(RESULTS)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    sys.exit(0 if passed == len(RESULTS) else 1)
