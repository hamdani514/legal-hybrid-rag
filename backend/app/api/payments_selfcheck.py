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
        U = {"user_id": "USr-9001"}

        r = await c.get("/api/payments/config")
        cfg = r.json()
        check("config says payments are enabled and in test mode",
              cfg["enabled"] and cfg["test_mode"] and cfg["paid_plan"] == settings.PAID_PLAN)
        check("config leaks no secret key", "sk_" not in json.dumps(cfg))

        r = await c.get("/api/payments/status", params=U)
        check("a new user starts unpaid", r.status_code == 200 and r.json()["is_paid"] is False,
              r.json().get("plan"))

        # --- the real Stripe call -------------------------------------
        r = await c.post("/api/payments/create-checkout-session", json=U)
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

        r = await c.get("/api/payments/status", params=U)
        check("status now reports the paid plan", r.json()["is_paid"] is True)

        # --- a retry of the same event must not double-apply ----------
        r = await c.post("/api/payments/webhook", content=payload, headers=signed_headers(payload))
        check("a replayed event is recognised as a duplicate",
              r.status_code == 200 and r.json().get("duplicate") is True)

        r = await c.post("/api/payments/create-checkout-session", json=U)
        check("an already-paid user cannot start a second subscription",
              r.status_code == 400, str(r.status_code))

        # --- cancellation returns the user to free --------------------
        sub_obj = {"id": "sub_selfcheck", "object": "subscription", "customer": "cus_selfcheck"}
        payload2 = json.dumps(event("customer.subscription.deleted", sub_obj, "evt_sc_2")).encode()
        r = await c.post("/api/payments/webhook", content=payload2, headers=signed_headers(payload2))
        doc = await users.find_one({"id": "USr-9001"})
        check("cancelling the subscription returns the user to free",
              r.status_code == 200 and doc["plan"] == settings.FREE_PLAN, doc["plan"])

        r = await c.post("/api/payments/create-checkout-session", json={"user_id": "USr-does-not-exist"})
        check("an unknown account cannot pay", r.status_code == 404, str(r.status_code))

        # --- confirm-on-return: the path that works without a webhook ---
        await users.update_one({"id": "USr-9001"},
                               {"$set": {"plan": "Free"},
                                # cus_selfcheck was invented for the webhook test and
                                # is not a real Stripe customer.
                                "$unset": {"stripe_customer_id": ""}})
        await users.insert_one({"id": "USr-9002", "email": "other@gmail.com",
                                "plan": "Free", "status": "Active"})

        r = await c.post("/api/payments/confirm", json={"session_id": "cs_test_not_real",
                                                        "user_id": "USr-9001"})
        check("confirm rejects an id Stripe does not know", r.status_code == 404, str(r.status_code))

        # A real, still-unpaid session: must not upgrade anyone.
        made = await c.post("/api/payments/create-checkout-session", json={"user_id": "USr-9001"})
        unpaid_id = made.json()["session_id"]
        r = await c.post("/api/payments/confirm", json={"session_id": unpaid_id,
                                                        "user_id": "USr-9001"})
        check("confirm refuses a session Stripe has not marked paid",
              r.status_code == 200 and r.json()["confirmed"] is False, str(r.json()))
        doc = await users.find_one({"id": "USr-9001"})
        check("that left the plan alone", doc["plan"] == "Free", doc["plan"])

        r = await c.post("/api/payments/confirm", json={"session_id": unpaid_id,
                                                        "user_id": "USr-9002"})
        check("one user cannot claim another user's payment",
              r.status_code == 403, str(r.status_code))

    await db.client.drop_database(SCRATCH)
    await close_db()


if __name__ == "__main__":
    asyncio.run(run())
    passed = sum(RESULTS)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    sys.exit(0 if passed == len(RESULTS) else 1)
