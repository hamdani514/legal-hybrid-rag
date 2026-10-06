"""
End-to-end self-check for authentication, route protection and per-user limits.

    cd backend && DB_NAME=legal_rag_scratch_auth venv/Scripts/python.exe -m app.api.auth_selfcheck

WHY it is shaped like this
--------------------------
* It runs the real FastAPI app in-process (httpx ASGITransport), so it never
  touches a running server on :5000 and does not run the lifespan (no model
  warm-up).
* It requires DB_NAME=legal_rag_scratch_auth in the environment (importing
  app.api already loads app.config, so it cannot be set from inside this
  module) and refuses to run if that did not reach Settings: seeding users and upgrading
  passwords must never happen in the live `legal_rag` database. The scratch DB
  is dropped at the end.
* Nothing reaches an LLM, SMTP or Google Drive: the search handler, the
  Ollama name check, the email senders and the Google verifier are stubbed,
  and no authorised DELETE is ever sent (delete_job also touches Chroma and
  Drive, which are not scoped by DB_NAME).
"""

import asyncio  # noqa: E402
import time  # noqa: E402

import httpx  # noqa: E402

from app.config import settings  # noqa: E402

SCRATCH = "legal_rag_scratch_auth"
assert settings.DB_NAME == SCRATCH, f"refusing to run against {settings.DB_NAME!r}"

import main  # noqa: E402
import app.api.admin as admin_mod  # noqa: E402
import app.api.auth as auth_mod  # noqa: E402
import app.api.routes.query as query_mod  # noqa: E402
from app.api import security  # noqa: E402
from app.database import close_db, connect_db, db  # noqa: E402

RESULTS: list = []


def check(name: str, cond: bool, info: str = "") -> None:
    RESULTS.append((name, bool(cond), info))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({info})" if info else ""))


async def _fake_search(**kwargs):
    q = kwargs.get("raw_query", "")
    return {"query": q, "cleaned_query": q, "intent": {}, "mode": kwargs.get("mode", "answer"),
            "judgments": [], "top_judgment_answer": None, "no_results": True, "message": "stub"}


async def _noop(*args, **kwargs):
    return None


async def _human(_name):
    return True


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def run() -> None:
    # ---- stubs: no LLM / SMTP / Google network ----
    query_mod.retrieve_and_answer = _fake_search
    admin_mod.validate_human_name = _human
    for name in ("send_password_changed_email", "send_deactivation_email"):
        setattr(auth_mod, name, _noop)

    original = {k: getattr(settings, k) for k in
                ("AUTH_REQUIRED", "JWT_SECRET", "USER_SEARCHES_PER_MINUTE", "USER_ANSWERS_PER_DAY", "GOOGLE_CLIENT_ID")}
    settings.JWT_SECRET = "selfcheck-" + "k" * 40

    await connect_db()
    assert db.database.name == SCRATCH, db.database.name
    await db.client.drop_database(SCRATCH)
    users, admins = db.database.users, db.database.admins
    await users.insert_many([
        {"id": "USr-1001", "username": "legacy", "name": "Legacy User", "email": "legacy@gmail.com",
         "plan": "Standard", "status": "Active", "password": "Legacy#Pass1"},
        {"id": "USr-1002", "username": "gone", "name": "Gone User", "email": "gone@gmail.com",
         "plan": "Standard", "status": "Inactive", "isActive": False, "password": "Gone#Pass12"},
    ])
    await admins.insert_one({"adminid": "root@example.com", "name": "Root", "role": "super_admin",
                             "password": "Admin#Pass1"})

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        search_body = {"query": "constable dismissed from service appeal"}

        # ================= AUTH_REQUIRED = False: behaves as before ============
        settings.AUTH_REQUIRED = False
        security.limiter.reset()
        r = await c.post("/query/search", json=search_body)
        check("auth off: anonymous /query/search works", r.status_code == 200, f"{r.status_code}")
        r = await c.get("/api/admin/users")
        check("auth off: anonymous admin GET /api/admin/users works", r.status_code == 200, f"{r.status_code}")
        r = await c.get("/api/admin/jobs", headers=_bearer("garbage"))
        check("auth off: an invalid token is ignored, not rejected", r.status_code == 200, f"{r.status_code}")
        r = await c.get("/api/health")
        check("auth off: health public", r.status_code == 200, f"{r.status_code}")

        # ================= logins ============================================
        r = await c.post("/api/auth/login", json={"email": "legacy@gmail.com", "password": "wrong"})
        check("wrong password -> 401", r.status_code == 401, f"{r.status_code}")
        doc = await users.find_one({"id": "USr-1001"})
        check("failed login leaves legacy password untouched", doc["password"] == "Legacy#Pass1")

        r = await c.post("/api/auth/login", json={"email": "legacy@gmail.com", "password": "Legacy#Pass1"})
        body = r.json()
        check("legacy plain-text user logs in", r.status_code == 200 and "token" in body, f"{r.status_code}")
        check("login returns the same user shape as before",
              set(body.get("user", {})) == {"id", "username", "name", "email", "plan", "message"},
              str(sorted(body.get("user", {}))))
        user_token = body["token"]
        doc = await users.find_one({"id": "USr-1001"})
        check("legacy password now stored as bcrypt hash", security.is_bcrypt_hash(doc["password"]),
              doc["password"][:7])
        r = await c.post("/api/auth/login", json={"email": "legacy@gmail.com", "password": "Legacy#Pass1"})
        check("upgraded password still works", r.status_code == 200, f"{r.status_code}")
        r = await c.post("/api/auth/login", json={"email": "Legacy@Gmail.com ", "password": "Legacy#Pass1"})
        check("email match tolerates case/space", r.status_code == 200, f"{r.status_code}")
        r = await c.post("/api/auth/login", json={"email": "gone@gmail.com", "password": "Gone#Pass12"})
        check("deactivated user -> 403 with is_deactivated", r.status_code == 403 and r.json().get("is_deactivated"),
              f"{r.status_code}")
        r = await c.post("/api/auth/login", json={"email": "nobody@gmail.com", "password": "x"})
        check("unknown user -> 401", r.status_code == 401, f"{r.status_code}")

        r = await c.post("/api/auth/admin/login", json={"adminid": "root@example.com", "password": "Admin#Pass1"})
        body = r.json()
        check("admin logs in", r.status_code == 200 and "token" in body, f"{r.status_code}")
        check("admin user shape unchanged", set(body.get("user", {})) == {"adminid", "name", "role", "message"})
        admin_token = body["token"]
        adoc = await admins.find_one({"adminid": "root@example.com"})
        check("admin legacy password upgraded to bcrypt", security.is_bcrypt_hash(adoc["password"]))
        r = await c.post("/api/auth/admin/login", json={"adminid": "root@example.com", "password": "nope"})
        check("admin wrong password -> 401", r.status_code == 401, f"{r.status_code}")
        check("token payload roles", security.decode_token(user_token)["role"] == "user"
              and security.decode_token(admin_token)["role"] == "admin"
              and security.decode_token(user_token)["sub"] == "USr-1001")

        # ================= signup stores a hash ==============================
        r = await c.post("/api/auth/signup", json={
            "username": "Ayesha", "name": "Ayesha Khan", "email": "ayesha@gmail.com", "org": "",
            "plan": "Pro", "password": "Strong#Pass9", "dob": "1990-01-01"})
        check("signup succeeds", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
        check("signup response omits password", "password" not in r.json())
        sdoc = await users.find_one({"email": "ayesha@gmail.com"})
        check("signup stores bcrypt hash", sdoc and security.is_bcrypt_hash(sdoc["password"]))
        check("signup cannot self-assign Pro", sdoc and sdoc["plan"] == "Standard", sdoc and sdoc["plan"])
        r = await c.post("/api/auth/login", json={"email": "ayesha@gmail.com", "password": "Strong#Pass9"})
        check("new signup logs in", r.status_code == 200, f"{r.status_code}")

        # ================= reset-password stores a hash =====================
        await users.update_one({"id": "USr-1001"}, {"$set": {
            "otp_hash": auth_mod._hash_otp("legacy@gmail.com", "123456"),
            "otp_expires": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            + __import__("datetime").timedelta(minutes=5), "otp_attempts": 0}})
        r = await c.post("/api/auth/reset-password",
                         json={"email": "legacy@gmail.com", "otp": "123456", "newPassword": "Reset#Pass77"})
        doc = await users.find_one({"id": "USr-1001"})
        check("reset-password stores bcrypt hash", r.status_code == 200 and security.is_bcrypt_hash(doc["password"]),
              f"{r.status_code}")
        r = await c.post("/api/auth/login", json={"email": "legacy@gmail.com", "password": "Reset#Pass77"})
        check("login with reset password", r.status_code == 200, f"{r.status_code}")

        # ================= deactivate: CONFIRM no longer bypasses ===========
        r = await c.post("/api/auth/deactivate", json={"email": "ayesha@gmail.com", "password": "CONFIRM"})
        check("deactivate with 'CONFIRM' on a password account -> 403", r.status_code == 403, f"{r.status_code}")

        # ================= AUTH_REQUIRED = True ==============================
        settings.AUTH_REQUIRED = True
        security.limiter.reset()
        r = await c.post("/query/search", json=search_body)
        check("auth on: unauthenticated /query/search -> 401", r.status_code == 401, f"{r.status_code}")
        r = await c.delete("/api/admin/jobs/x")
        check("auth on: unauthenticated DELETE /api/admin/jobs/x -> 401", r.status_code == 401, f"{r.status_code}")
        r = await c.delete("/api/admin/jobs/x", headers=_bearer(user_token))
        check("auth on: user token on DELETE /api/admin/jobs/x -> 403", r.status_code == 403, f"{r.status_code}")
        r = await c.get("/api/admin/users", headers=_bearer(user_token))
        check("auth on: user token on GET /api/admin/users -> 403", r.status_code == 403, f"{r.status_code}")
        r = await c.get("/api/admin/users", headers=_bearer(admin_token))
        check("auth on: admin token on GET /api/admin/users -> 200", r.status_code == 200, f"{r.status_code}")
        r = await c.get("/api/admin/jobs", headers=_bearer(admin_token))
        check("auth on: admin token on GET /api/admin/jobs -> 200", r.status_code == 200, f"{r.status_code}")
        r = await c.post("/embeddings/generate", json={}, headers=_bearer(user_token))
        check("auth on: user token on /embeddings/generate -> 403", r.status_code == 403, f"{r.status_code}")
        r = await c.post("/query/search", json=search_body, headers=_bearer("not.a.jwt"))
        check("auth on: garbage token -> 401", r.status_code == 401, f"{r.status_code}")
        expired = security.jwt.encode({"sub": "USr-1001", "role": "user", "exp": int(time.time()) - 1},
                                      settings.JWT_SECRET, algorithm="HS256")
        r = await c.post("/query/search", json=search_body, headers=_bearer(expired))
        check("auth on: expired token -> 401", r.status_code == 401, f"{r.status_code}")
        forged = security.jwt.encode({"sub": "x", "role": "admin", "exp": int(time.time()) + 600},
                                     "long_random_string_here", algorithm="HS256")
        r = await c.get("/api/admin/users", headers=_bearer(forged))
        check("auth on: token forged with the placeholder secret -> 401", r.status_code == 401, f"{r.status_code}")
        r = await c.post("/query/search", json=search_body, headers=_bearer(user_token))
        check("auth on: user token on /query/search -> 200", r.status_code == 200, f"{r.status_code}")
        r = await c.get("/api/auth/me", headers=_bearer(user_token))
        check("auth on: /api/auth/me returns principal", r.status_code == 200 and r.json()["principal"]["sub"] == "USr-1001")

        # public allowlist still reachable without a token
        for method, url, kw in [
            ("get", "/api/admin/users/check-username?username=zzz", {}),
            ("get", "/api/admin/users/check-email?email=zzz@gmail.com", {}),
            ("post", "/api/admin/support", {"json": {"full_name": "", "email": "a@x.com", "subject": "s", "message": "m"}}),
            ("post", "/api/auth/login", {"json": {"email": "legacy@gmail.com", "password": "Reset#Pass77"}}),
            ("post", "/api/auth/forgot-password", {"json": {"email": "nobody@gmail.com"}}),
            ("get", "/api/auth/google/config", {}),
            ("get", "/api/health", {}),
        ]:
            r = await getattr(c, method)(url, **kw)
            check(f"auth on: public {method.upper()} {url.split('?')[0]} not 401/403",
                  r.status_code not in (401, 403), f"{r.status_code}")
        r = await c.get("/api/admin/judgments/nope/download")
        check("auth on: download without token -> 401", r.status_code == 401, f"{r.status_code}")
        r = await c.get(f"/api/admin/judgments/nope/download?token={user_token}")
        check("auth on: download with ?token= passes the guard", r.status_code not in (401, 403), f"{r.status_code}")

        # ================= per-user limits ===================================
        security.limiter.reset()
        settings.USER_SEARCHES_PER_MINUTE = 10
        codes = [(await c.post("/query/search", json=search_body, headers=_bearer(user_token))).status_code
                 for _ in range(11)]
        check("10 searches/min allowed, 11th -> 429", codes[:10] == [200] * 10 and codes[10] == 429, str(codes))
        r = await c.post("/query/search", json=search_body, headers=_bearer(user_token))
        j = r.json()
        check("429 body is clear JSON with Retry-After",
              r.status_code == 429 and j.get("error") == "rate_limited" and "per minute" in j.get("detail", "")
              and int(r.headers.get("retry-after", 0)) >= 1, str(j)[:160])
        r = await c.post("/query/search", json=search_body, headers=_bearer(admin_token))
        check("limits are per user: another account unaffected", r.status_code == 200, f"{r.status_code}")
        security.limiter.reset()
        settings.USER_SEARCHES_PER_MINUTE = 0
        settings.USER_ANSWERS_PER_DAY = 3
        codes = [(await c.post("/query/search", json=search_body, headers=_bearer(user_token))).status_code
                 for _ in range(4)]
        check("daily answer limit -> 429 after 3", codes == [200, 200, 200, 429], str(codes))
        settings.USER_ANSWERS_PER_DAY = original["USER_ANSWERS_PER_DAY"]

        # Anonymous limiting is opt-in (RATE_LIMIT_ANONYMOUS, default False):
        # behind the dev proxy every browser is 127.0.0.1, so an IP limit with
        # auth off would make all users share one allowance. Test both modes.
        settings.AUTH_REQUIRED = False
        original_anon = getattr(settings, "RATE_LIMIT_ANONYMOUS", False)
        settings.USER_SEARCHES_PER_MINUTE = 2

        settings.RATE_LIMIT_ANONYMOUS = False
        security.limiter.reset()
        codes = [(await c.post("/query/search", json=search_body)).status_code for _ in range(3)]
        check("auth off, anonymous limit off (default): no 429", codes == [200, 200, 200], str(codes))

        settings.RATE_LIMIT_ANONYMOUS = True
        security.limiter.reset()
        codes = [(await c.post("/query/search", json=search_body)).status_code for _ in range(3)]
        check("auth off, anonymous limit on: limited by IP", codes == [200, 200, 429], str(codes))

        settings.RATE_LIMIT_ANONYMOUS = original_anon
        settings.USER_SEARCHES_PER_MINUTE = original["USER_SEARCHES_PER_MINUTE"]
        security.limiter.reset()

        # ================= Google sign-in ====================================
        settings.GOOGLE_CLIENT_ID = ""
        r = await c.get("/api/auth/google/config")
        check("google: unconfigured -> enabled false", r.json() == {"enabled": False, "client_id": ""})
        r = await c.post("/api/auth/google", json={"credential": "x"})
        check("google: unconfigured -> 503, no token issued", r.status_code == 503 and "token" not in r.json())
        settings.GOOGLE_CLIENT_ID = "1234-abc.apps.googleusercontent.com"

        async def fake_verify(credential, client_id):
            if credential != "good":
                raise ValueError("bad token")
            return {"email": "newgoogle@gmail.com", "email_verified": True, "name": "New Google",
                    "given_name": "New", "sub": "g-1", "aud": client_id}
        auth_mod.verify_google_id_token = fake_verify
        r = await c.post("/api/auth/google", json={"credential": "bad"})
        check("google: invalid credential -> 401", r.status_code == 401, f"{r.status_code}")
        r = await c.post("/api/auth/google", json={"credential": "good"})
        check("google: verified credential -> token + user", r.status_code == 200 and "token" in r.json(), f"{r.status_code}")
        gdoc = await users.find_one({"email": "newgoogle@gmail.com"})
        check("google: account created without password", gdoc is not None and not gdoc.get("password"))

        # ================= admin account routes: hashes in, never out =========
        settings.AUTH_REQUIRED = False
        for path in ("/api/admin/users/login", "/api/admin/login"):
            r = await c.post(path, json={"email": "legacy@gmail.com", "adminid": "x", "password": "x"})
            check(f"legacy plain-text login {path} removed", r.status_code in (404, 405), f"{r.status_code}")

        r = await c.get("/api/admin/users")
        check("GET /users returns no passwords",
              r.status_code == 200 and all("password" not in u for u in r.json()["users"]))
        r = await c.post("/api/admin/users", json={
            "username": "bilal", "email": "bilal@gmail.com", "name": "Bilal Khan", "org": "Firm",
            "plan": "Standard", "password": "Admin#Made1", "dob": "1990-01-01"})
        check("POST /users: 200, no password in response", r.status_code == 200 and "password" not in r.json(),
              f"{r.status_code}")
        bdoc = await users.find_one({"email": "bilal@gmail.com"})
        check("POST /users stores bcrypt hash", bdoc and security.is_bcrypt_hash(bdoc.get("password")))
        r = await c.post("/api/auth/login", json={"email": "bilal@gmail.com", "password": "Admin#Made1"})
        check("admin-created user can log in", r.status_code == 200, f"{r.status_code}")
        edit = {k: bdoc.get(k) for k in ("username", "email", "name", "org", "plan", "dob")}
        r = await c.put(f"/api/admin/users/{bdoc['id']}", json={**edit, "org": "New Firm", "password": ""})
        after = await users.find_one({"email": "bilal@gmail.com"})
        check("PUT /users blank password keeps the hash, no password in response",
              r.status_code == 200 and "password" not in r.json() and after["password"] == bdoc["password"]
              and after["org"] == "New Firm", f"{r.status_code}")
        r = await c.put(f"/api/admin/users/{bdoc['id']}", json={**edit, "password": "weak"})
        check("PUT /users weak password -> 400", r.status_code == 400, f"{r.status_code}")
        r = await c.put(f"/api/admin/users/{bdoc['id']}", json={**edit, "password": "Changed#Pw2"})
        after = await users.find_one({"email": "bilal@gmail.com"})
        check("PUT /users new password stored as a new bcrypt hash",
              r.status_code == 200 and security.is_bcrypt_hash(after["password"])
              and after["password"] != bdoc["password"])

        admin_body = {"adminid": "ops@example.com", "name": "Ops", "email": "ops@gmail.com",
                      "role": "admin", "dob": "1985-05-05"}
        r = await c.post("/api/admin/admins", json={**admin_body, "password": "Ops#Pass123"})
        odoc = await admins.find_one({"adminid": "ops@example.com"})
        check("POST /admins stores bcrypt hash", r.status_code == 200 and odoc
              and security.is_bcrypt_hash(odoc.get("password")), f"{r.status_code}")
        r = await c.get("/api/admin/admins")
        check("GET /admins returns no passwords",
              r.status_code == 200 and all("password" not in a for a in r.json()["admins"]))
        r = await c.get("/api/admin/profile", params={"adminid": "ops@example.com"})
        check("GET /profile returns no password", r.status_code == 200 and "password" not in r.json())
        r = await c.put("/api/admin/admins/ops@example.com", json={**admin_body, "name": "Ops Two", "password": ""})
        after = await admins.find_one({"adminid": "ops@example.com"})
        check("PUT /admins blank password keeps the hash",
              r.status_code == 200 and after["password"] == odoc["password"] and after["name"] == "Ops Two")
        r = await c.put("/api/admin/profile", json={"original_adminid": "ops@example.com", "adminid": "ops@example.com",
                                                    "password": "Prof#Pass99", "dob": "1985-05-05", "name": "Ops"})
        r2 = await c.post("/api/auth/admin/login", json={"adminid": "ops@example.com", "password": "Prof#Pass99"})
        check("PUT /profile new password -> admin can log in with it",
              r.status_code == 200 and r2.status_code == 200, f"{r.status_code}/{r2.status_code}")

    # ================= startup gate ========================================
    settings.AUTH_REQUIRED = True
    settings.JWT_SECRET = "long_random_string_here"
    try:
        security.check_security_config()
        refused = False
    except RuntimeError:
        refused = True
    check("startup refuses placeholder secret when AUTH_REQUIRED", refused)
    settings.AUTH_REQUIRED = False
    security.check_security_config()  # only warns
    check("startup with placeholder secret allowed when AUTH_REQUIRED is False", True)

    for k, v in original.items():
        setattr(settings, k, v)
    await db.client.drop_database(SCRATCH)
    names = await db.client.list_database_names()
    check("scratch DB dropped", SCRATCH not in names)
    await close_db()


if __name__ == "__main__":
    asyncio.run(run())
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    assert not failed, failed
