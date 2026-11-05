"""
Proves who can reach what, so the holes this file was written for cannot return.

    cd backend && venv/Scripts/python.exe -m app.api.access_selfcheck --routes
    cd backend && DB_NAME=legal_rag_scratch_access venv/Scripts/python.exe -m app.api.access_selfcheck

--routes needs no database and runs in CI. It walks EVERY route the app serves, so
a route added next year is covered without anyone adding a test for it:

  * without a token, everything outside the public list answers 401
  * a user token on an admin route answers 403
  * forged, expired and garbage tokens are refused
  * the public list here matches the one in security.py, and every entry exists:
    making a route public takes two deliberate edits, in two files
  * only POST /query/search can start a search, so the daily limit has no way round
  * nothing reads a user id from a header or query string
  * the app refuses to start with a weak JWT_SECRET, and no secret has a default

The full run adds real accounts in a scratch database (dropped at the end), with
search, email and Stripe stubbed. It proves that a stranger, and another signed-in
user, cannot read or change an account, while the owner still can.
"""

import asyncio
import pathlib
import re
import sys
import time

import httpx
from fastapi.routing import APIRoute

from app.config import Settings, settings

# Must hold before anything below can sign or verify a token. Never the real one.
_TEST_SECRET = "access-selfcheck-" + "k" * 40
_REAL_SECRET = settings.JWT_SECRET
settings.JWT_SECRET = _TEST_SECRET

import main  # noqa: E402
from app.api import security  # noqa: E402

RESULTS: list = []

# Keep in step with security.PUBLIC_ROUTES. A mismatch fails this check on purpose.
EXPECTED_PUBLIC = {
    ("GET", "/api/health"),
    ("GET", "/{full_path:path}"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/admin/login"),
    ("POST", "/api/auth/signup"),
    ("POST", "/api/auth/verify-signup-otp"),
    ("POST", "/api/auth/resend-signup-otp"),
    ("POST", "/api/auth/forgot-password"),
    ("POST", "/api/auth/verify-otp"),
    ("POST", "/api/auth/reset-password"),
    ("POST", "/api/auth/reactivate/{token}"),
    ("POST", "/api/auth/send-reactivation-link"),
    ("GET", "/api/auth/google/config"),
    ("POST", "/api/auth/google"),
    ("GET", "/api/auth/avatar/{file_id}"),
    ("GET", "/api/blogs/cover/{file_id}"),
    ("POST", "/api/auth/contact"),
    ("POST", "/api/admin/support"),
    ("GET", "/api/admin/users/check-username"),
    ("GET", "/api/admin/users/check-email"),
    ("GET", "/api/blogs"),
    ("GET", "/api/blogs/{slug}"),
    ("GET", "/api/stats"),
    ("GET", "/api/payments/config"),
    ("POST", "/api/payments/webhook"),
}


def check(name: str, cond, info="") -> None:
    RESULTS.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({info})" if info != "" else ""))


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def token_for(sub: str, role: str = "user") -> dict:
    return bearer(security.create_access_token(sub, role))


def all_routes() -> list[tuple[str, str]]:
    keys = []
    for route in main.app.routes:
        if isinstance(route, APIRoute):
            keys += [(method, route.path) for method in sorted(route.methods)]
    return keys


async def call(c, method: str, path: str, headers=None):
    url = re.sub(r"\{[^}]+\}", "x", path)
    kwargs = {"headers": headers or {}}
    if method in ("POST", "PUT", "PATCH"):
        kwargs["json"] = {}
    return await c.request(method, url, **kwargs)


async def routes_part(c) -> None:
    routes = all_routes()
    check(f"the app serves routes to check ({len(routes)})", len(routes) > 50)

    # ── every route, no token ────────────────────────────────────────────
    protected = [k for k in routes if k not in security.PUBLIC_ROUTES]
    open_routes = []
    for method, path in protected:
        r = await call(c, method, path)
        if r.status_code != 401:
            open_routes.append(f"{method} {path} -> {r.status_code}")
    check(f"no token: all {len(protected)} protected routes answer 401", not open_routes, "; ".join(open_routes[:8]))

    claiming = {"x-user-id": "USr-VICTIM"}
    leaks = []
    for method, path in protected:
        r = await c.request(method, re.sub(r"\{[^}]+\}", "x", path) + "?user_id=USr-VICTIM", headers=claiming,
                            **({"json": {"user_id": "USr-VICTIM"}} if method in ("POST", "PUT", "PATCH") else {}))
        if r.status_code != 401:
            leaks.append(f"{method} {path} -> {r.status_code}")
    check("claiming to be someone (header, query, body) without a token: still 401 everywhere",
          not leaks, "; ".join(leaks[:8]))

    # ── every admin route, user token ────────────────────────────────────
    admin_routes = [k for k in routes if security.required_access(k) == "admin"]
    let_in = []
    for method, path in admin_routes:
        r = await call(c, method, path, token_for("USr-ANY"))
        if r.status_code != 403:
            let_in.append(f"{method} {path} -> {r.status_code}")
    check(f"user token: all {len(admin_routes)} admin routes answer 403", not let_in, "; ".join(let_in[:8]))

    # ── bad tokens ───────────────────────────────────────────────────────
    now = int(time.time())
    admin_claims = {"sub": "attacker", "role": "admin", "exp": now + 600}
    bad = {
        "signed with the old public placeholder": security.jwt.encode(admin_claims, "long_random_string_here", algorithm="HS256"),
        "signed with another secret": security.jwt.encode(admin_claims, "z" * 48, algorithm="HS256"),
        "expired": security.jwt.encode({**admin_claims, "exp": now - 5}, _TEST_SECRET, algorithm="HS256"),
        "with no signature (alg none)": ".".join(
            __import__("base64").urlsafe_b64encode(p.encode()).rstrip(b"=").decode()
            for p in ('{"alg":"none","typ":"JWT"}', '{"sub":"attacker","role":"admin","exp":%d}' % (now + 600))) + ".",
        "garbage": "not.a.jwt",
    }
    for label, token in bad.items():
        r = await c.get("/api/admin/users", headers=bearer(token))
        check(f"token {label}: refused", r.status_code == 401, r.status_code)
    r = await c.get("/api/payments/config", headers=bearer("not.a.jwt"))
    check("a stale token does not break a public route", r.status_code == 200, r.status_code)

    # ── the public list is reviewed, and real ────────────────────────────
    check("public routes match this file's reviewed list", set(security.PUBLIC_ROUTES) == EXPECTED_PUBLIC,
          sorted(set(security.PUBLIC_ROUTES) ^ EXPECTED_PUBLIC))
    missing = sorted(set(security.PUBLIC_ROUTES) - set(routes))
    check("every public entry is a real route (no stale exceptions)", not missing, missing)

    # ── only one way to run a search ─────────────────────────────────────
    gone = [("POST", "/embeddings/search"), ("POST", "/api/query"), ("POST", "/api/query/"),
            ("POST", "/api/chats"), ("GET", "/api/chats"), ("POST", "/api/chats/{slug}/messages")]
    check("the old routes round the daily limit are gone", not [k for k in gone if k in routes],
          [k for k in gone if k in routes])
    backend = pathlib.Path(__file__).resolve().parents[2]
    sources = [p for d in ("app", "modules") for p in (backend / d).rglob("*.py")] + [backend / "main.py"]
    this_file = pathlib.Path(__file__).resolve()
    callers = sorted(str(p.relative_to(backend)).replace("\\", "/") for p in sources
                     if p.resolve() != this_file and not p.name.endswith("selfcheck.py")
                     and "import retrieve_and_answer" in p.read_text(encoding="utf-8")
                     or (p.resolve() != this_file and not p.name.endswith("selfcheck.py")
                         and re.search(r"from app\.retrieval\.orchestrator import [^\n]*retrieve_and_answer", p.read_text(encoding="utf-8"))))
    check("only routes/query.py can start a search", callers == ["app/api/routes/query.py"], callers)
    query_src = (backend / "app/api/routes/query.py").read_text(encoding="utf-8")
    check("that search route enforces the plan limit", "await plan_guard(request)" in query_src)

    # ── identity comes only from the token ───────────────────────────────
    trusting = []
    for p in sources:
        if p.resolve() == this_file or p.name.endswith("selfcheck.py"):
            continue
        text = p.read_text(encoding="utf-8")
        if re.search(r"""["']x-user-id["']|query_params\.get\(\s*["']user_id["']""", text):
            trusting.append(p.name)
    check("nothing reads a user id from a header or query string", not trusting, trusting)
    for name, path in (("profile", "app/api/auth.py"), ("subscription", "modules/payment/controller.py"),
                       ("chat", "app/api/chat.py")):
        src = (backend / path).read_text(encoding="utf-8")
        check(f"{name} routes take no user_id parameter",
              not re.search(r"async def \w+\([^)]*\buser_id\s*:", src), path)

    # ── secrets ──────────────────────────────────────────────────────────
    for label, value in (("empty", ""), ("the old placeholder", "long_random_string_here"), ("short", "a" * 31)):
        settings.JWT_SECRET = value
        try:
            security.check_security_config()
            refused = False
        except RuntimeError:
            refused = True
        check(f"startup refuses a JWT_SECRET that is {label}", refused)
    settings.JWT_SECRET = _TEST_SECRET
    security.check_security_config()
    check("startup accepts a strong JWT_SECRET", True)
    settings.JWT_SECRET = "long_random_string_here"
    try:
        security.create_access_token("x", "admin")
        signed = True
    except RuntimeError:
        signed = False
    forged = security.jwt.encode(admin_claims, "long_random_string_here", algorithm="HS256")
    r = await c.get("/api/admin/users", headers=bearer(forged))
    settings.JWT_SECRET = _TEST_SECRET
    check("even if started by mistake, a weak secret neither signs nor verifies", not signed and r.status_code == 401)

    fields = Settings.model_fields
    check("no authentication off-switch exists", "AUTH_REQUIRED" not in fields and not hasattr(settings, "AUTH_REQUIRED"))
    check("JWT_SECRET has no default in the code", fields["JWT_SECRET"].default == "")
    check("SUPER_ADMIN_PASSWORD has no default in the code", fields["SUPER_ADMIN_PASSWORD"].default == "")


async def accounts_part(c) -> None:
    from datetime import datetime, timedelta, timezone

    from app.api import auth as auth_mod
    from app.api.routes import query as query_mod
    from app.database import db
    from modules.payment import controller

    searches = {"n": 0, "mode": None}

    async def fake_search(raw_query, top_k_judgments=5, top_k_sections=3, mode="answer", user_id=None):
        searches["n"] += 1
        searches["mode"] = mode
        return {"query": raw_query, "cleaned_query": raw_query, "intent": {}, "mode": mode, "judgments": [],
                "top_judgment_answer": None, "no_results": True, "message": "stub"}

    async def noop(*a, **k):
        return None

    query_mod.retrieve_and_answer = fake_search
    import inspect

    from app.api import admin as admin_mod
    for mod in (auth_mod, admin_mod):  # no email leaves a test
        for name in dir(mod):
            if name.startswith("send_") and inspect.iscoroutinefunction(getattr(mod, name)):
                setattr(mod, name, noop)

    stripe_calls: list = []

    class Sub:
        @staticmethod
        def modify(sid, **kw):
            stripe_calls.append(sid)
            return {"id": sid, "current_period_end": int(time.time()) + 86400}

    class FakeStripe:
        Subscription = Sub

    controller._stripe = lambda: FakeStripe

    users = db.database.users
    now = datetime.now(timezone.utc)
    pw = "Correct#Horse9"
    hashed = security.hash_password(pw)

    async def seed():
        await users.delete_many({})
        await db.database.chat_sessions.delete_many({})
        await db.database.auth_throttle.delete_many({})
        await db.database.admins.delete_many({})
        await db.database.admins.insert_one({"adminid": "root", "name": "Root", "role": "admin"})
        await users.insert_many([
            {"id": "USr-A", "email": "alice@example.com", "name": "Alice", "first_name": "Alice", "plan": "Free",
             "status": "Active", "password": hashed, "dailyQueries": {"count": 0, "date": now}},
            {"id": "USr-V", "email": "victim@example.com", "name": "Victim", "first_name": "Victim", "plan": "Premium",
             "status": "Active", "password": hashed, "stripeSubscriptionId": "sub_victim", "cardLast4": "1111",
             "subscriptionEndsAt": now + timedelta(days=20), "dailyQueries": {"count": 3, "date": now}},
            {"id": "USr-G", "email": "google@example.com", "name": "NoCounter", "first_name": "NoCounter", "plan": "Free",
             "status": "Active"},  # no password (Google) and no dailyQueries field
        ])
        await db.database.chat_sessions.insert_one(
            {"session_id": "sess-v", "user_key": "USr-V", "title": "Victim's private case", "pinned": False,
             "messages": [{"sender": "user", "text": "secret client facts"}], "created_at": now, "updated_at": now})

    async def victim():
        return await users.find_one({"id": "USr-V"})

    await seed()
    A, V = token_for("USr-A"), token_for("USr-V")

    # ── 1. admin area ────────────────────────────────────────────────────
    r = await c.delete("/api/admin/users/USr-V")
    check("stranger cannot delete a user", r.status_code == 401 and await victim(), r.status_code)
    r = await c.delete("/api/admin/users/USr-V", headers=A)
    check("ordinary user cannot delete a user", r.status_code == 403 and await victim(), r.status_code)
    r = await c.get("/api/admin/users", headers=A)
    check("ordinary user cannot list users", r.status_code == 403, r.status_code)
    r = await c.get("/api/admin/users", headers=token_for("root", "admin"))
    check("an admin still can", r.status_code == 200 and len(r.json()["users"]) == 3, r.status_code)

    # ── 3. subscriptions ─────────────────────────────────────────────────
    stripe_calls.clear()
    r = await c.post("/api/payments/cancel-subscription", json={"user_id": "USr-V"})
    check("stranger cannot cancel a subscription", r.status_code == 401 and not stripe_calls, r.status_code)
    r = await c.post("/api/payments/cancel-subscription", json={"user_id": "USr-V"}, headers=A)
    check("another user cannot cancel it, naming the victim: only their own is considered",
          r.status_code == 400 and not stripe_calls and not (await victim()).get("cancelAtPeriodEnd"), r.status_code)
    r = await c.post("/api/payments/reactivate-subscription", json={"user_id": "USr-V"})
    check("stranger cannot reactivate one", r.status_code == 401, r.status_code)
    r = await c.post("/api/payments/cancel-subscription", headers=V)
    check("the owner can cancel their own", r.status_code == 200 and stripe_calls == ["sub_victim"]
          and (await victim()).get("cancelAtPeriodEnd") is True, r.status_code)
    await seed()

    # ── 4. profiles and account details ──────────────────────────────────
    r = await c.get("/api/auth/profile", params={"user_id": "USr-V"})
    check("stranger cannot read a profile", r.status_code == 401, r.status_code)
    r = await c.get("/api/auth/profile", params={"user_id": "USr-V"}, headers=A)
    check("naming another user returns your own profile", r.status_code == 200 and r.json().get("email") == "alice@example.com")
    r = await c.put("/api/auth/profile", params={"user_id": "USr-V"}, json={"name": "HACKED", "first_name": "HACKED"})
    check("stranger cannot edit a profile", r.status_code == 401 and (await victim())["name"] == "Victim", r.status_code)
    r = await c.put("/api/auth/profile", params={"user_id": "USr-V"}, json={"name": "Alice B", "first_name": "Alice"}, headers=A)
    check("another user's edit lands on their own profile only", (await victim())["name"] == "Victim",
          f"{r.status_code}")
    r = await c.get("/api/payments/status", params={"user_id": "USr-V"})
    check("stranger cannot read plan or card", r.status_code == 401, r.status_code)
    r = await c.get("/api/payments/status", params={"user_id": "USr-V"}, headers=A)
    check("naming another user returns your own plan, not their card",
          r.status_code == 200 and r.json()["plan"] == "free" and r.json().get("cardLast4") != "1111")
    r = await c.get("/api/payments/status", headers=V)
    check("the owner sees their own plan and card",
          r.status_code == 200 and r.json()["plan"] == "premium" and r.json()["cardLast4"] == "1111")
    r = await c.delete("/api/auth/profile/avatar", params={"user_id": "USr-V"})
    check("stranger cannot remove an avatar", r.status_code == 401, r.status_code)

    body = {"email": "victim@example.com", "password": pw}
    r = await c.post("/api/auth/deactivate", json=body)
    check("stranger cannot deactivate, even with the password", r.status_code == 401, r.status_code)
    r = await c.post("/api/auth/deactivate", json=body, headers=A)
    check("another user cannot deactivate it, even with the password",
          r.status_code == 403 and (await victim()).get("status") == "Active", r.status_code)
    r = await c.post("/api/auth/delete-account", json=body, headers=A)
    check("another user cannot delete it, even with the password", r.status_code == 403 and await victim(), r.status_code)
    r = await c.post("/api/auth/delete-account", json={"email": "alice@example.com", "password": "wrong"}, headers=A)
    check("the owner still needs their own password", r.status_code == 403 and await users.find_one({"id": "USr-A"}), r.status_code)
    r = await c.post("/api/auth/delete-account", json={"email": "alice@example.com", "password": pw}, headers=A)
    check("the owner can delete their own account", r.status_code == 200 and not await users.find_one({"id": "USr-A"}), r.status_code)
    await seed()

    # ── 5. pretending to be someone else ─────────────────────────────────
    r = await c.post("/query/search", json={"query": "bail case"}, headers={"x-user-id": "USr-V"})
    check("x-user-id without a token: refused, no search spent",
          r.status_code == 401 and (await victim())["dailyQueries"]["count"] == 3, r.status_code)
    r = await c.post("/query/search", json={"query": "bail case"}, headers={**A, "x-user-id": "USr-V"})
    check("x-user-id with your own token: your plan, their searches untouched",
          r.status_code == 200 and r.json()["plan"] == "free" and (await victim())["dailyQueries"]["count"] == 3, r.status_code)
    r = await c.get("/api/judgments/x/download", headers={**A, "x-user-id": "USr-V"})
    check("x-user-id does not borrow a paid plan for downloads", r.status_code == 403, r.status_code)
    r = await c.get("/api/chat/sessions/sess-v", params={"user_id": "USr-V"})
    check("stranger cannot read a conversation", r.status_code == 401, r.status_code)
    r = await c.get("/api/chat/sessions/sess-v", params={"user_id": "USr-V"}, headers=A)
    check("another user cannot read a conversation", r.status_code == 404 and "secret client facts" not in r.text, r.status_code)
    r = await c.delete("/api/chat/sessions", params={"user_id": "USr-V"}, headers=A)
    left = await db.database.chat_sessions.count_documents({"user_key": "USr-V"})
    check("another user cannot delete a conversation", left == 1, left)
    r = await c.get("/api/chat/sessions/sess-v", headers=V)
    check("the owner can read their conversation", r.status_code == 200 and "secret client facts" in r.text, r.status_code)
    await seed()

    # ── 6. plan limits ───────────────────────────────────────────────────
    codes = []
    for _ in range(3):
        codes.append((await c.post("/query/search", json={"query": "bail case"}, headers=A)).status_code)
    check("Free: 2 searches, then blocked", codes == [200, 200, 403], codes)
    check("Free searches run without AI analysis", searches["mode"] == "retrieve_only", searches["mode"])
    before = searches["n"]
    for method, path in (("POST", "/embeddings/search"), ("POST", "/api/query"), ("POST", "/api/chats")):
        r = await c.request(method, path, json={"query": "bail case", "firstMessage": "bail case"}, headers=A)
        check(f"old route {path} no longer searches", r.status_code in (404, 405) and searches["n"] == before, r.status_code)
    r = await c.post("/query/search", json={"query": "bail case"}, headers=token_for("USr-G"))
    doc = await users.find_one({"id": "USr-G"})
    check("an account with no counter yet can search (it used to be told its limit was reached)",
          r.status_code == 200 and doc["dailyQueries"]["count"] == 1, r.status_code)
    r = await c.post("/query/search", json={"query": "bail case"}, headers=token_for("root", "admin"))
    check("an admin can search, with no plan or fake user created",
          r.status_code == 200 and not await users.find_one({"id": {"$regex": "^anon_"}}), r.status_code)

    # ── accounts that no longer exist ────────────────────────────────────
    gone = token_for("USr-DELETED")
    r = await c.post("/query/search", json={"query": "bail case"}, headers=gone)
    check("a deleted account's token cannot search, and no fake user is created",
          r.status_code == 401 and not await users.find_one({"id": {"$regex": "^anon_"}}), r.status_code)

    await seed()

    # ── 8. accounts that were deactivated or deleted ─────────────────────
    g = token_for("USr-G")
    r = await c.get("/api/auth/profile", headers=g)
    check("an active account's token works", r.status_code == 200, r.status_code)
    await users.update_one({"id": "USr-G"}, {"$set": {"status": "Inactive", "isActive": False}})
    for method, path in (("GET", "/api/auth/profile"), ("POST", "/query/search"), ("GET", "/api/chat/sessions"),
                         ("GET", "/api/judgments/x/download"), ("POST", "/api/auth/refresh")):
        r = await c.request(method, path, headers=g, **({"json": {"query": "bail case"}} if method == "POST" else {}))
        check(f"deactivated account's token refused at once: {method} {path}", r.status_code == 401, r.status_code)
    await users.update_one({"id": "USr-G"}, {"$set": {"status": "Active", "isActive": True}})
    r = await c.get("/api/auth/profile", headers=g)
    check("reactivated, the same account works again", r.status_code == 200, r.status_code)
    await users.delete_one({"id": "USr-G"})
    r = await c.get("/api/auth/profile", headers=g)
    check("deleted account's token refused at once", r.status_code == 401, r.status_code)
    r = await c.get(f"/api/judgments/x/download?token={security.create_access_token('USr-G', 'user')}")
    check("deleted account's download link refused", r.status_code == 401, r.status_code)
    root = token_for("root", "admin")
    await db.database.admins.delete_one({"adminid": "root"})
    r = await c.get("/api/admin/users", headers=root)
    check("removed admin's token refused at once", r.status_code == 401, r.status_code)
    check("no fake anon_ users were created along the way",
          not await users.find_one({"id": {"$regex": "^anon_"}}))
    await seed()

    # ── 11. guessing passwords, codes, and flooding email ────────────────
    bad = {"email": "alice@example.com", "password": "wrong"}
    codes = [(await c.post("/api/auth/login", json=bad)).status_code for _ in range(6)]
    check("5 wrong passwords, then the account is locked", codes == [401] * 5 + [429], codes)
    r = await c.post("/api/auth/login", json={"email": "alice@example.com", "password": pw})
    check("while locked, even the right password is refused", r.status_code == 429, r.status_code)
    check("the lock says how long to wait", "15 minutes" in r.json().get("detail", "") and int(r.headers.get("retry-after", 0)) > 0)
    r = await c.post("/api/auth/login", json={"email": "victim@example.com", "password": pw})
    check("other accounts are not locked by it", r.status_code == 200, r.status_code)
    await db.database.auth_throttle.delete_many({"_id": {"$regex": "^login-account:alice"}})  # the 15 minutes pass
    r = await c.post("/api/auth/login", json={"email": "alice@example.com", "password": pw})
    check("after the lock ends the right password works", r.status_code == 200, r.status_code)
    codes = [(await c.post("/api/auth/login", json=bad)).status_code for _ in range(4)]
    check("a successful login resets the account's count", codes == [401] * 4, codes)
    await db.database.auth_throttle.delete_many({})
    codes = [(await c.post("/api/auth/login", json={"email": f"spray{i}@example.com", "password": "x"})).status_code
             for i in range(31)]
    check("30 failures across many accounts from one network: that network is locked",
          codes[:30] == [401] * 30 and codes[30] == 429, codes[-3:])
    await db.database.auth_throttle.delete_many({})
    codes = [(await c.post("/api/auth/admin/login", json={"adminid": "root", "password": "x"})).status_code for _ in range(6)]
    check("admin sign-in locks too", codes == [401] * 5 + [429], codes)
    await db.database.auth_throttle.delete_many({})

    codes = [(await c.post("/api/auth/forgot-password", json={"email": "alice@example.com"})).status_code for _ in range(4)]
    check("reset codes: 3 per hour per email, then refused", codes == [200] * 3 + [429], codes)
    codes = [(await c.post("/api/auth/forgot-password", json={"email": f"x{i}@example.com"})).status_code for i in range(18)]
    check("reset codes from one network: 20 per hour in all", codes.count(429) == 1 and codes[-1] == 429, codes[-3:])
    await db.database.auth_throttle.delete_many({})
    wrong = {"email": "alice@example.com", "otp": "000000"}
    codes = []
    for i in range(11):
        if i == 5:  # what asking for a new code does to the per-code counter
            await users.update_one({"id": "USr-A"}, {"$set": {"otp_attempts": 0}})
        codes.append((await c.post("/api/auth/verify-otp", json=wrong)).status_code)
    check("code guesses: 10 per hour per email, and a new code does not reset that",
          codes[10] == 429 and 429 not in codes[:5], codes)
    await db.database.auth_throttle.delete_many({})
    form = {"full_name": "A", "name": "A", "email": "a@example.com", "subject": "s", "message": "hello there"}
    codes = [(await c.post("/api/admin/support", json=form)).status_code for _ in range(11)]
    check("contact form: 10 per hour per network, then refused", codes[-1] == 429 and 429 not in codes[:10], codes[-2:])
    await db.database.auth_throttle.delete_many({})
    ttl = [ix for ix in (await db.database.auth_throttle.index_information()).values() if "expireAfterSeconds" in ix]
    from app.api.throttle import ensure_indexes
    await ensure_indexes()
    ttl = [ix for ix in (await db.database.auth_throttle.index_information()).values() if "expireAfterSeconds" in ix]
    check("limit records expire on their own (TTL index)", len(ttl) == 1, ttl)

    # ── 12. browser protection ───────────────────────────────────────────
    evil = await c.options("/api/auth/login", headers={"Origin": "https://evil.example",
                                                      "Access-Control-Request-Method": "POST"})
    check("another website is not allowed to call the API", "access-control-allow-origin" not in evil.headers,
          evil.headers.get("access-control-allow-origin"))
    own = (settings.FRONTEND_URL or "").rstrip("/")
    mine = await c.options("/api/auth/login", headers={"Origin": own, "Access-Control-Request-Method": "POST"})
    check("the site's own address still is", mine.headers.get("access-control-allow-origin") == own,
          mine.headers.get("access-control-allow-origin"))
    check("credentials are never shared cross-site", mine.headers.get("access-control-allow-credentials") != "true")
    r = await c.get("/api/health")
    want = {"x-content-type-options": "nosniff", "x-frame-options": "DENY",
            "referrer-policy": "strict-origin-when-cross-origin"}
    check("security headers on every response", all(r.headers.get(k) == v for k, v in want.items()),
          {k: r.headers.get(k) for k in want})
    r = await c.get("/api/health", headers={"x-forwarded-proto": "https"})
    check("HSTS when served over HTTPS", "max-age" in r.headers.get("strict-transport-security", ""))
    csp = main.app.state.csp
    check("a content security policy is ready for the pages",
          "frame-ancestors 'none'" in csp and "object-src 'none'" in csp and "'unsafe-eval'" not in csp)

    # ── admin password ───────────────────────────────────────────────────
    original = settings.SUPER_ADMIN_PASSWORD
    settings.SUPER_ADMIN_PASSWORD = ""
    r = await c.post("/api/auth/admin/login", json={"adminid": settings.SUPER_ADMIN_EMAIL, "password": ""})
    check("with no admin password configured, an empty one does not log in", r.status_code != 200, r.status_code)
    settings.SUPER_ADMIN_PASSWORD = "Test#Admin#Pass1"
    r = await c.post("/api/auth/admin/login", json={"adminid": settings.SUPER_ADMIN_EMAIL, "password": "wrong"})
    check("wrong admin password refused", r.status_code == 401, r.status_code)
    await db.database.auth_throttle.delete_many({})
    r = await c.post("/api/auth/admin/login", json={"adminid": settings.SUPER_ADMIN_EMAIL, "password": "Test#Admin#Pass1"})
    check("right admin password works", r.status_code == 200 and "token" in r.json(), r.status_code)
    settings.SUPER_ADMIN_PASSWORD = original


async def run() -> bool:
    routes_only = "--routes" in sys.argv
    transport = httpx.ASGITransport(app=main.app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as c:
        await routes_part(c)
        if not routes_only:
            from app.database import close_db, connect_db, db

            assert settings.DB_NAME == "legal_rag_scratch_access", f"refusing to run against {settings.DB_NAME!r}"
            settings.USER_SEARCHES_PER_MINUTE = 100000
            settings.USER_ANSWERS_PER_DAY = 100000
            await connect_db()
            await db.client.drop_database(settings.DB_NAME)
            await accounts_part(c)
            await db.client.drop_database(settings.DB_NAME)
            await close_db()
    settings.JWT_SECRET = _REAL_SECRET
    passed = sum(RESULTS)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    return passed == len(RESULTS)


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(run()) else 1)
