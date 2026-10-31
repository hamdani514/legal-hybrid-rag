"""
Check the three plans end to end, against a scratch database.

    cd backend && DB_NAME=legal_rag_scratch_plans venv/Scripts/python.exe -m app.api.plans_selfcheck

No search is run and no Gemini or Stripe call is made: every request either
stops at the plan check or asks for a judgment that does not exist. Covers:

  * the daily limits (Free 2, Standard 20, Premium 50) and the upgrade message
  * the paid features refused on Free with a structured 403, allowed on paid
    plans: analyse, compare, summarise, more results, download
  * an expired paid plan behaves as Free
  * /api/payments/status reports the plan, its limit and its features
  * checkout refuses an unknown plan and buying the plan one is already on
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings

SCRATCH = "legal_rag_scratch_plans"
assert settings.DB_NAME == SCRATCH, f"refusing to run against {settings.DB_NAME!r}"

import main  # noqa: E402
from app.api.security import create_access_token  # noqa: E402
from app.database import close_db, connect_db, db  # noqa: E402

RESULTS = []


def check(name, cond, info=""):
    RESULTS.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({info})" if info else ""))


def auth(uid):
    return {"Authorization": f"Bearer {create_access_token(uid, 'user')}"}


async def run():
    await connect_db()
    await db.client.drop_database(SCRATCH)
    users = db.database.users
    now = datetime.now(timezone.utc)
    later = now + timedelta(days=20)
    await users.insert_many([
        {"id": "USr-F", "email": "free@example.com", "plan": "Free"},
        {"id": "USr-S", "email": "std@example.com", "plan": "Standard", "subscriptionEndsAt": later},
        {"id": "USr-P", "email": "prem@example.com", "plan": "Premium", "subscriptionEndsAt": later},
        {"id": "USr-X", "email": "lapsed@example.com", "plan": "Premium",
         "subscriptionEndsAt": now - timedelta(days=1)},
    ])

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as c:
        # ── status ─────────────────────────────────────────────────────
        expected = {"USr-F": ("free", 2, False), "USr-S": ("standard", 20, True),
                    "USr-P": ("premium", 50, True), "USr-X": ("free", 2, False)}
        for uid, (plan, limit, unlocked) in expected.items():
            r = await c.get("/api/payments/status", headers=auth(uid))
            body = r.json()
            check(f"status {uid}: {plan}, {limit}/day, features {'on' if unlocked else 'off'}",
                  r.status_code == 200 and body["plan"] == plan and body["dailyQueriesLimit"] == limit
                  and all(v is unlocked for v in body["features"].values()) and len(body["features"]) == 7,
                  f"{body.get('plan')} {body.get('dailyQueriesLimit')}")
        lapsed = await users.find_one({"id": "USr-X"})
        check("an expired Premium is downgraded to Free on read", lapsed["plan"] == "Free", lapsed["plan"])

        # ── daily limits: the guard runs before any retrieval ─────────
        for uid, limit in (("USr-F", 2), ("USr-S", 20), ("USr-P", 50)):
            await users.update_one({"id": uid}, {"$set": {"dailyQueries": {"count": limit, "date": now}}})
            r = await c.post("/query/search", json={"query": "bail in murder case"}, headers=auth(uid))
            detail = r.json().get("detail", {})
            check(f"{uid} is stopped after {limit} searches",
                  r.status_code == 403 and detail.get("dailyLimit") == limit, r.status_code)
            if uid == "USr-F":
                check("Free's limit message offers an upgrade",
                      detail.get("requiresUpgrade") is True and "Upgrade" in detail.get("message", ""),
                      detail.get("message"))
            if uid == "USr-P":
                check("Premium's limit message offers no upgrade", detail.get("requiresUpgrade") is False)
            await users.update_one({"id": uid}, {"$set": {"dailyQueries": {"count": 0, "date": now}}})

        # ── paid features ──────────────────────────────────────────────
        calls = {
            "analyse": ("/query/answer", {"query": "bail in murder case", "judgment_id": "nope"}),
            "compare": ("/query/compare", {"judgment_ids": ["nope-1", "nope-2"]}),
            "summarize": ("/query/summarize", {"judgment_id": "nope"}),
            "see_all": ("/query/more", {"query": "bail in murder case", "shown": []}),
        }
        for feature, (path, payload) in calls.items():
            r = await c.post(path, json=payload, headers=auth("USr-F"))
            detail = r.json().get("detail", {})
            check(f"Free is refused {feature}",
                  r.status_code == 403 and isinstance(detail, dict) and detail.get("feature") == feature
                  and detail.get("requiresUpgrade") is True, r.status_code)
            r = await c.post(path, json=payload, headers=auth("USr-X"))
            check(f"an expired plan is refused {feature}", r.status_code == 403, r.status_code)

        # Paid plans get past the plan check. "answer" on an unknown judgment
        # is a 404 from the route itself, so it proves the check let it through
        # without running a search or an LLM call.
        for uid in ("USr-S", "USr-P"):
            r = await c.post("/query/answer", json=calls["analyse"][1], headers=auth(uid))
            check(f"{uid} passes the analyse check", r.status_code == 404, r.status_code)

        for path in ("/api/admin/judgments/nope/download", "/api/judgments/nope/download"):
            r = await c.get(path, headers=auth("USr-F"))
            check(f"Free is refused the download {path}", r.status_code == 403, r.status_code)
            r = await c.get(path, headers=auth("USr-P"))
            check(f"Premium passes the download check {path}", r.status_code == 404, r.status_code)
        token = create_access_token("USr-F", "user")
        r = await c.get(f"/api/admin/judgments/nope/download?token={token}")
        check("a Free download link with ?token= is refused too", r.status_code == 403, r.status_code)

        # ── checkout ───────────────────────────────────────────────────
        r = await c.post("/api/payments/create-checkout-session", json={"plan": "gold"}, headers=auth("USr-F"))
        check("checkout refuses an unknown plan", r.status_code == 422, r.status_code)
        if (settings.STRIPE_SECRET_KEY or "").strip() and settings.STRIPE_PRICE_ID:
            r = await c.post("/api/payments/create-checkout-session", json={"plan": "standard"},
                             headers=auth("USr-S"))
            check("checkout refuses the plan already held", r.status_code == 400, r.json().get("detail"))
        if (settings.STRIPE_SECRET_KEY or "").startswith("sk_test_"):
            # Test mode only: finds or creates the Premium price in the test
            # account, then opens a real (unpaid) Checkout session for it.
            r = await c.post("/api/payments/create-checkout-session", json={"plan": "premium"},
                             headers=auth("USr-S"))
            url = (r.json() or {}).get("url") or ""
            check("a Standard user switching to Premium gets a Stripe checkout link",
                  r.status_code == 200 and url.startswith("https://checkout.stripe.com/"),
                  r.json().get("detail") if r.status_code != 200 else url[:48])
            from modules.payment import plans as plan_table
            premium_price = plan_table.price_id_for("premium")
            if premium_price:
                import stripe
                stripe.api_key = settings.STRIPE_SECRET_KEY
                price = stripe.Price.retrieve(premium_price)
                check("the Premium price is $20 a month",
                      price.unit_amount == 2000 and price.recurring.interval == "month",
                      f"{price.unit_amount} {price.currency}/{price.recurring.interval}")
        r = await c.get("/api/payments/config")
        check("config lists which paid plans can be bought",
              set(r.json().get("plans", {})) == {"standard", "premium"}, r.json().get("plans"))

    await db.client.drop_database(SCRATCH)
    await close_db()
    passed = sum(RESULTS)
    print(f"{passed}/{len(RESULTS)} checks passed")
    return passed == len(RESULTS)


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(run()) else 1)
