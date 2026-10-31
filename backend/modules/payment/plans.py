"""
The three subscription plans, in one place.

Every limit and every feature a plan unlocks is read from PLANS: the daily
search guard, the feature checks on /query/*, the download route, the status
endpoint the frontend reads, checkout and the Stripe webhook. Change a number
here and all of them follow; frontend/src/user/lib/plan.js mirrors this table
only as a fallback for the moment before /api/payments/status answers.

  Free      2 searches a day. The relevant judgments (at most 10), each shown
            as its case-card summary. No LLM analysis, so a Free search spends
            no Gemini quota. Every other tool is visible in the UI but locked.
  Standard  20 searches a day, $10/month. Every relevant judgment, ten at a
            time, and every tool: analyse, summarise, filter, download,
            compare, see all, copy.
  Premium   50 searches a day, $20/month. Everything in Standard.

What is stored on the user is the display name ("Free", "Standard",
"Premium"); older records also hold "free", "pro" or "advocate". plan_key()
reads all of them, so no migration is needed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.config import settings

FREE = "free"
STANDARD = "standard"
PREMIUM = "premium"
PAID_PLANS = (STANDARD, PREMIUM)

# Every gated capability. The keys are the contract with the frontend.
FEATURES = ("analyse", "summarize", "compare", "download", "filter", "see_all", "copy")

# How a locked feature is named in the 403 message and the upgrade prompt.
FEATURE_LABELS = {
    "analyse": "Case analysis",
    "summarize": "Judgment summaries",
    "compare": "Comparing judgments",
    "download": "Downloading judgments",
    "filter": "Filtering results",
    "see_all": "Seeing every relevant judgment",
    "copy": "Copying text",
}

PLANS: dict[str, dict] = {
    FREE: {
        "key": FREE,
        "name": "Free",
        "daily_limit": 2,
        # A Free search shows at most this many judgments and no "more" pages.
        "max_results": 10,
        "price_usd": 0,
        "features": frozenset(),
        "color": "bg-[#E7E8EA] text-[#44474D]",
    },
    STANDARD: {
        "key": STANDARD,
        "name": "Standard",
        "daily_limit": 20,
        "max_results": None,
        "price_usd": 10,
        "features": frozenset(FEATURES),
        "color": "bg-[#CFE6FF] text-[#0B3B6F]",
    },
    PREMIUM: {
        "key": PREMIUM,
        "name": "Premium",
        "daily_limit": 50,
        "max_results": None,
        "price_usd": 20,
        "features": frozenset(FEATURES),
        "color": "bg-[#E9C176] text-[#261900]",
    },
}

# Older names for the paid plans, read as the plan they became.
_ALIASES = {"pro": STANDARD, "advocate": STANDARD, "standard": STANDARD, "premium": PREMIUM}


def plan_key(raw) -> str:
    """The plan a stored value names: "free", "standard" or "premium"."""
    return _ALIASES.get(str(raw or "").strip().lower(), FREE)


def plan(key: str) -> dict:
    return PLANS.get(key, PLANS[FREE])


def has_feature(key: str, feature: str) -> bool:
    return feature in plan(key)["features"]


def price_label(key: str) -> str:
    return f"${plan(key)['price_usd']:.2f} / month"


def _as_utc(value) -> Optional[datetime]:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def subscription_end(user: dict) -> Optional[datetime]:
    return _as_utc(
        user.get("subscriptionEndsAt")
        or user.get("subscription_ends_at")
        or user.get("plan_cancels_at")
    )


def is_expired(user: dict, now: Optional[datetime] = None) -> bool:
    """A paid plan whose paid-up period has ended (the cron may not have run yet)."""
    if plan_key(user.get("plan")) == FREE:
        return False
    ends = subscription_end(user)
    return bool(ends and ends <= (now or datetime.now(timezone.utc)))


def effective_plan(user: Optional[dict], now: Optional[datetime] = None) -> str:
    """The plan the user may use right now. An expired paid plan is Free."""
    if not user:
        return FREE
    return FREE if is_expired(user, now) else plan_key(user.get("plan"))


# The fields that put a user back on Free when a paid period has ended.
DOWNGRADE_FIELDS = {
    "plan": PLANS[FREE]["name"],
    "planColor": PLANS[FREE]["color"],
    "subscriptionEndsAt": None,
    "subscription_ends_at": None,
    "autoRenew": False,
    "cancelAtPeriodEnd": False,
}


def describe(key: str) -> dict:
    """What the frontend needs to know about a plan: its limits and features."""
    p = plan(key)
    return {
        "plan": p["key"],
        "plan_name": p["name"],
        "daily_limit": p["daily_limit"],
        "max_results": p["max_results"],
        "features": {f: f in p["features"] for f in FEATURES},
    }


# ── Stripe prices ────────────────────────────────────────────────────────────
def price_id_for(key: str) -> str:
    """The Stripe recurring price a paid plan is billed with ("" if not known yet)."""
    if key == STANDARD:
        return (settings.STRIPE_PRICE_ID or "").strip()
    if key == PREMIUM:
        configured = (getattr(settings, "STRIPE_PREMIUM_PRICE_ID", "") or "").strip()
        return configured or _resolved.get(PREMIUM, "")
    return ""


# The Premium price needs no manual setup. When STRIPE_PREMIUM_PRICE_ID is not
# set, ensure_premium_price() finds the price tagged with this lookup key in
# the Stripe account, or creates it once ($20/month, in the Standard price's
# currency). The lookup key is how it is found again after a restart and how
# the webhook recognises it on a subscription.
PREMIUM_LOOKUP_KEY = "verdict_ai_premium_monthly"
PREMIUM_PRODUCT_NAME = "Verdict AI Premium"
_resolved: dict[str, str] = {}


def ensure_premium_price(client) -> str:
    """The Premium price id, found by lookup key or created on first use."""
    existing = price_id_for(PREMIUM)
    if existing:
        return existing
    found = client.Price.list(lookup_keys=[PREMIUM_LOOKUP_KEY], active=True, limit=1)
    if found.data:
        price_id = found.data[0].id
    else:
        currency = "usd"
        standard = price_id_for(STANDARD)
        if standard:
            try:
                currency = client.Price.retrieve(standard).currency or currency
            except Exception:
                pass
        price_id = client.Price.create(
            unit_amount=PLANS[PREMIUM]["price_usd"] * 100,
            currency=currency,
            recurring={"interval": "month"},
            product_data={"name": PREMIUM_PRODUCT_NAME},
            lookup_key=PREMIUM_LOOKUP_KEY,
            metadata={"plan": PREMIUM},
        ).id
    _resolved[PREMIUM] = price_id
    return price_id


def plan_for_price(price_id: Optional[str]) -> Optional[str]:
    """The plan a Stripe price bills, or None when it is neither of ours."""
    if not price_id:
        return None
    for key in PAID_PLANS:
        if price_id_for(key) and price_id_for(key) == price_id:
            return key
    return None


def price_of_subscription(subscription) -> Optional[str]:
    """The price id of a subscription's first item (Stripe object or dict)."""
    try:
        items = subscription["items"]["data"]
        return items[0]["price"]["id"] if items else None
    except (KeyError, IndexError, TypeError, AttributeError):
        return None


def _field(obj, *path):
    """obj[path[0]][path[1]]…, or None — for Stripe objects and plain dicts."""
    try:
        for key in path:
            obj = obj[key]
        return obj
    except (KeyError, IndexError, TypeError, AttributeError):
        return None


def plan_of_subscription(subscription) -> Optional[str]:
    """The paid plan a subscription bills, or None when it cannot be told.

    By the price id (configured or resolved), then the Premium lookup key,
    then the plan written into the subscription's metadata at checkout.
    """
    by_price = plan_for_price(price_of_subscription(subscription))
    if by_price:
        return by_price
    if _field(subscription, "items", "data", 0, "price", "lookup_key") == PREMIUM_LOOKUP_KEY:
        return PREMIUM
    from_meta = plan_key(_field(subscription, "metadata", "plan"))
    return from_meta if from_meta in PAID_PLANS else None


if __name__ == "__main__":
    # Self-check, no DB or network: python -m modules.payment.plans
    from datetime import timedelta

    assert plan_key("Standard") == plan_key("pro") == STANDARD
    assert plan_key("Premium") == PREMIUM and plan_key(None) == plan_key("Free") == FREE
    now = datetime.now(timezone.utc)
    assert effective_plan({"plan": "Premium", "subscriptionEndsAt": now + timedelta(days=3)}) == PREMIUM
    assert effective_plan({"plan": "Premium", "subscriptionEndsAt": now - timedelta(days=1)}) == FREE
    assert effective_plan({"plan": "Standard"}) == STANDARD  # no end date: still paid
    assert effective_plan(None) == FREE
    assert [plan(k)["daily_limit"] for k in (FREE, STANDARD, PREMIUM)] == [2, 20, 50]
    assert not any(describe(FREE)["features"].values())
    assert all(describe(PREMIUM)["features"].values()) and describe(PREMIUM)["features"] == describe(STANDARD)["features"]
    assert price_label(PREMIUM) == "$20.00 / month"
    assert price_of_subscription({"items": {"data": [{"price": {"id": "price_x"}}]}}) == "price_x"
    assert price_of_subscription({}) is None
    print("OK: plans")
