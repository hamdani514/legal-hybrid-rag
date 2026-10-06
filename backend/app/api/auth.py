"""
Account endpoints under /api/auth: sign-in, signup, Google sign-in, password
recovery, deactivation/reactivation and the contact form.

WHY the sign-in routes live here (and not in admin.py, where the old ones are)
----------------------------------------------------------------------------
The original /api/admin/users/login and /api/admin/login compared plain-text
passwords and returned a user object with no credential, so every other route
had to be left open. The routes below verify with bcrypt, transparently
upgrade a legacy plain-text password to a bcrypt hash on the first successful
login, and return {token, user}: `user` keeps exactly the shape the frontend
already stores (currentUser / currentAdmin), `token` is the JWT the rest of
the API checks (see app/api/security.py). Every route in this router is
public by design — each one authenticates its caller itself (password, OTP,
emailed token or Google ID token).
"""

from datetime import datetime, timezone, timedelta
import asyncio
import hashlib
import re
import random
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from loguru import logger

from app.api.security import (
    TokenError,
    auth_required,
    create_access_token,
    decode_token,
    hash_password,
    require_user,
    verify_password,
)
from app.config import settings
from app.database import db
from app.retrieval.contracts import TokenPayload
from app.services.email_service import (
    send_otp_email,
    send_password_changed_email,
    send_deactivation_email,
    send_reactivation_link_email,
    send_reactivation_confirmation_email,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# -------------------------------------------------------------
# Request Schemas
# -------------------------------------------------------------

class ForgotPasswordRequest(BaseModel):
    email: str
    captchaToken: Optional[str] = None


class VerifyOtpRequest(BaseModel):
    email: str
    otp: str


class ResetPasswordRequest(BaseModel):
    email: str
    otp: str
    newPassword: Optional[str] = None
    new_password: Optional[str] = None
    captchaToken: Optional[str] = None

    @property
    def password_val(self) -> str:
        return self.newPassword or self.new_password or ""


class DeactivateAccountRequest(BaseModel):
    email: str
    password: str


# -------------------------------------------------------------
# Helpers
# -------------------------------------------------------------

import httpx

async def verify_recaptcha(captcha_token: Optional[str], expected_action: str = None) -> bool:
    secret = (settings.RECAPTCHA_SECRET_KEY or "").strip()
    if not secret or not captcha_token:
        return True
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                "https://www.google.com/recaptcha/api/siteverify",
                data={"secret": secret, "response": captcha_token},
            )
            data = resp.json()
            if not data.get("success"):
                logger.warning(f"reCAPTCHA failed: {data.get('error-codes')}")
                return False
            score = data.get("score")
            threshold = float(settings.RECAPTCHA_SCORE_THRESHOLD or 0.5)
            if score is not None and score < threshold:
                logger.warning(f"reCAPTCHA score {score} < threshold {threshold}")
                return False
            return True
    except Exception as e:
        logger.warning(f"reCAPTCHA verification service error ({e}). Proceeding gracefully.")
        return True

def _hash_otp(email: str, otp: str) -> str:
    salt = "legal_rag_otp_salt"
    return hashlib.sha256(f"{email.lower().strip()}:{otp.strip()}:{salt}".encode("utf-8")).hexdigest()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


# -------------------------------------------------------------
# 1. POST /api/auth/forgot-password
# -------------------------------------------------------------
@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    clean_email = body.email.lower().strip()
    if not clean_email:
        raise HTTPException(status_code=400, detail="Email is required.")

    if not await verify_recaptcha(body.captchaToken, "forgot_password"):
        raise HTTPException(status_code=403, detail="Captcha verification failed. Please try again.")

    user = await db.database.users.find_one({"email": clean_email})
    
    # Generic message to prevent email enumeration
    generic_msg = "If that email is registered, an OTP has been sent."
    if not user:
        return {"message": generic_msg}

    # Generate 6-digit numeric OTP
    otp = f"{random.randint(100000, 999999)}"
    otp_hash = _hash_otp(clean_email, otp)
    otp_expires = datetime.now(timezone.utc) + timedelta(minutes=1)

    # Save to MongoDB user document
    await db.database.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "otp_hash": otp_hash,
                "otp_expires": otp_expires,
                "otp_attempts": 0,
            }
        },
    )

    # Send email (Real SMTP if configured, else console simulation preview)
    user_name = user.get("name") or user.get("username") or "Counselor"
    try:
        await send_otp_email(user_name, clean_email, otp)
    except Exception as e:
        logger.error(f"Failed to dispatch OTP email: {e}")
        # Clear OTP if email dispatch completely threw
        await db.database.users.update_one(
            {"_id": user["_id"]},
            {"$unset": {"otp_hash": "", "otp_expires": "", "otp_attempts": ""}},
        )
        raise HTTPException(
            status_code=500, detail="Unable to send email right now. Please try again later."
        )

    return {"message": generic_msg}


# -------------------------------------------------------------
# 2. POST /api/auth/verify-otp
# -------------------------------------------------------------
@router.post("/verify-otp")
async def verify_otp(body: VerifyOtpRequest):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    clean_email = body.email.lower().strip()
    clean_otp = body.otp.strip()

    if not clean_email or not clean_otp:
        raise HTTPException(status_code=400, detail="Email and OTP are required.")

    user = await db.database.users.find_one({"email": clean_email})
    if not user or not user.get("otp_hash"):
        raise HTTPException(status_code=400, detail="No OTP request found. Please request a new code.")

    # Expiry check
    expires = user.get("otp_expires")
    if not expires:
        raise HTTPException(status_code=400, detail="OTP has expired. Please request a new code.")
    
    # Ensure timezone awareness for comparison
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > expires:
        raise HTTPException(status_code=400, detail="OTP has expired. Please request a new code.")

    # Rate limiting: max 5 attempts
    attempts = user.get("otp_attempts", 0)
    if attempts >= 5:
        raise HTTPException(
            status_code=429, detail="Too many incorrect attempts. Please request a new code."
        )

    computed_hash = _hash_otp(clean_email, clean_otp)
    if computed_hash != user.get("otp_hash"):
        await db.database.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"otp_attempts": attempts + 1}},
        )
        raise HTTPException(status_code=400, detail="Invalid OTP code.")

    # Reset attempts on valid code and grant 5-minute password reset session
    await db.database.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "otp_attempts": 0,
                "otp_verified": True,
                "reset_window_expires": datetime.now(timezone.utc) + timedelta(minutes=5),
            }
        },
    )

    return {"message": "OTP verified successfully."}


# -------------------------------------------------------------
# 3. POST /api/auth/reset-password
# -------------------------------------------------------------
@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    clean_email = body.email.lower().strip()
    clean_otp = body.otp.strip()
    new_password = body.password_val.strip()

    if not clean_email or not clean_otp or not new_password:
        raise HTTPException(status_code=400, detail="Email, OTP, and new password are required.")

    if not await verify_recaptcha(body.captchaToken, "reset_password"):
        raise HTTPException(status_code=403, detail="Captcha verification failed. Please try again.")

    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")
    try:
        hashed_password = hash_password(new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    user = await db.database.users.find_one({"email": clean_email})
    if not user or not user.get("otp_hash"):
        raise HTTPException(status_code=400, detail="No active OTP request found. Please request a new code.")

    expires = user.get("otp_expires")
    if not expires:
        raise HTTPException(status_code=400, detail="OTP has expired. Please request a new code.")

    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    reset_window = user.get("reset_window_expires")
    if reset_window and reset_window.tzinfo is None:
        reset_window = reset_window.replace(tzinfo=timezone.utc)

    is_verified_session = bool(
        user.get("otp_verified") is True
        and reset_window
        and datetime.now(timezone.utc) <= reset_window
    )

    if not is_verified_session and datetime.now(timezone.utc) > expires:
        raise HTTPException(status_code=400, detail="OTP has expired. Please request a new code.")

    attempts = user.get("otp_attempts", 0)
    if attempts >= 5:
        raise HTTPException(
            status_code=429, detail="Too many incorrect attempts. Please request a new code."
        )

    computed_hash = _hash_otp(clean_email, clean_otp)
    if computed_hash != user.get("otp_hash"):
        await db.database.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"otp_attempts": attempts + 1}},
        )
        raise HTTPException(status_code=400, detail="Invalid OTP code.")

    # Update password and clear OTP fields
    await db.database.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "password": hashed_password,
                "updated_at": datetime.now(timezone.utc),
            },
            "$unset": {
                "otp_hash": "",
                "otp_expires": "",
                "otp_attempts": "",
                "otp_verified": "",
                "reset_window_expires": "",
            },
        },
    )

    # Dispatch confirmation email asynchronously
    user_name = user.get("name") or user.get("username") or "Counselor"
    try:
        await send_password_changed_email(user_name, clean_email)
    except Exception as e:
        logger.warning(f"Failed to dispatch password changed email: {e}")

    return {"message": "Password reset successful. You can now log in."}


# -------------------------------------------------------------
# 4. POST /api/auth/deactivate
# -------------------------------------------------------------
@router.post("/deactivate")
async def deactivate_account(body: DeactivateAccountRequest, request: Request):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    clean_email = body.email.lower().strip()
    password = body.password.strip()

    if not clean_email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required.")

    user = await db.database.users.find_one({"email": clean_email})
    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")

    if user.get("status") == "Inactive" or user.get("isActive") is False:
        raise HTTPException(status_code=400, detail="Account is already deactivated.")

    # Verify the caller owns the account. "CONFIRM" is accepted ONLY for
    # password-less (Google) accounts — it used to be accepted for every
    # account, so anyone knowing an email address could deactivate it.
    user_pass = user.get("password")
    if not user_pass:
        if password != "CONFIRM":
            raise HTTPException(
                status_code=400,
                detail='This account was created with Google. Type "CONFIRM" as password to deactivate.',
            )
        if auth_required():
            # No password to check, so the session must belong to this account.
            principal = _principal_or_none(request)
            if not principal or principal["sub"] not in _user_subs(user):
                raise HTTPException(status_code=401, detail="Please sign in to deactivate this account.")
    else:
        ok, _ = verify_password(password, user_pass)
        if not ok:
            # 403, not 401: the session is fine, the confirmation failed (a 401
            # makes the frontend treat the user as signed out).
            raise HTTPException(status_code=403, detail="Incorrect password.")

    # Generate 32-byte hex cryptographic reactivation token
    raw_token = secrets.token_hex(32)
    hashed_token = _hash_token(raw_token)
    days = int(settings.REACTIVATION_TOKEN_EXPIRY_DAYS or 30)
    expires = datetime.now(timezone.utc) + timedelta(days=days)

    frontend_base = (settings.FRONTEND_URL or "http://localhost:5173").rstrip("/")
    reactivate_url = f"{frontend_base}/reactivate/{raw_token}"

    user_name = user.get("name") or user.get("username") or "Counselor"

    # Send deactivation email FIRST
    try:
        await send_deactivation_email(user_name, clean_email, reactivate_url, days=days)
    except Exception as e:
        logger.error(f"Failed to send deactivation email: {e}")
        raise HTTPException(
            status_code=500,
            detail="Unable to send deactivation email. Account NOT deactivated. Try again.",
        )

    # Deactivate user in MongoDB
    await db.database.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "status": "Inactive",
                "statusColor": "bg-[#EF4444]",
                "isActive": False,
                "deactivated_at": datetime.now(timezone.utc),
                "reactivation_token_hash": hashed_token,
                "reactivation_token_expires": expires,
            }
        },
    )

    return {
        "message": "Account deactivated. Check your email for the reactivation link.",
        "reactivation_url": reactivate_url if not settings.SMTP_USER else None,
    }


# -------------------------------------------------------------
# 5. POST /api/auth/reactivate/{token}
# -------------------------------------------------------------
@router.post("/reactivate/{token}")
async def reactivate_account(token: str):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    if not token or len(token) < 32:
        raise HTTPException(status_code=400, detail="Reactivation token is invalid.")

    hashed_token = _hash_token(token)
    now = datetime.now(timezone.utc)

    user = await db.database.users.find_one({"reactivation_token_hash": hashed_token})
    if not user:
        raise HTTPException(status_code=400, detail="Reactivation link is invalid or has expired.")

    token_expires = user.get("reactivation_token_expires")
    if not token_expires:
        raise HTTPException(status_code=400, detail="Reactivation link is invalid or has expired.")

    if token_expires.tzinfo is None:
        token_expires = token_expires.replace(tzinfo=timezone.utc)

    if now > token_expires:
        raise HTTPException(status_code=400, detail="Reactivation link has expired.")

    if user.get("status") == "Active" and user.get("isActive") is True:
        return {"message": "Account is already active. You can now log in."}

    # Restore user to Active status
    plan = user.get("plan", "Standard")
    plan_color = "bg-[#E9C176] text-[#261900]" if plan == "Pro" else "bg-[#E7E8EA] text-[#44474D]"

    await db.database.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "status": "Active",
                "statusColor": "bg-[#22C55E]",
                "planColor": plan_color,
                "isActive": True,
                "deactivated_at": None,
            },
            "$unset": {
                "reactivation_token_hash": "",
                "reactivation_token_expires": "",
            },
        },
    )

    user_name = user.get("name") or user.get("username") or "Counselor"
    user_email = user.get("email")
    if user_email:
        try:
            await send_reactivation_confirmation_email(user_name, user_email)
        except Exception as e:
            logger.warning(f"Failed to send reactivation confirmation email: {e}")

    return {"message": "Account reactivated successfully. You can now log in."}


# -------------------------------------------------------------
# 5b. POST /api/auth/send-reactivation-link
# -------------------------------------------------------------
class RequestReactivationRequest(BaseModel):
    email: str


@router.post("/send-reactivation-link")
async def request_reactivation_link(body: RequestReactivationRequest):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    clean_email = body.email.strip().lower()
    if not clean_email:
        raise HTTPException(status_code=400, detail="Email is required.")

    user = await db.database.users.find_one({"email": clean_email})
    if not user:
        return {
            "message": "If that account is registered and deactivated, a reactivation link has been sent to your email."
        }

    if user.get("status") == "Active" and user.get("isActive") is True:
        return {
            "message": "This account is already active. You can proceed to log in.",
            "already_active": True,
        }

    # Generate fresh 32-byte cryptographic token
    raw_token = secrets.token_hex(32)
    hashed_token = _hash_token(raw_token)
    days = int(settings.REACTIVATION_TOKEN_EXPIRY_DAYS or 30)
    expires = datetime.now(timezone.utc) + timedelta(days=days)

    frontend_base = (settings.FRONTEND_URL or "http://localhost:5173").rstrip("/")
    reactivate_url = f"{frontend_base}/reactivate/{raw_token}"
    user_name = user.get("name") or user.get("username") or "Counselor"

    # Save fresh reactivation token to MongoDB
    await db.database.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "reactivation_token_hash": hashed_token,
                "reactivation_token_expires": expires,
            }
        },
    )

    # Dispatch email via real SMTP
    try:
        await send_reactivation_link_email(user_name, clean_email, reactivate_url, days=days)
    except Exception as e:
        logger.error(f"Failed to dispatch reactivation email: {e}")
        raise HTTPException(
            status_code=500,
            detail="Unable to send reactivation email right now. Please try again later.",
        )

    return {
        "message": f"A reactivation link has been dispatched to {clean_email}.",
        "email": clean_email,
    }


# -------------------------------------------------------------
# 6. POST /api/auth/contact
# -------------------------------------------------------------

class ContactFormRequest(BaseModel):
    name: Optional[str] = None
    full_name: Optional[str] = None
    email: str
    subject: Optional[str] = "No Subject"
    message: str
    captchaToken: Optional[str] = None

    @property
    def sender_name(self) -> str:
        return self.name or self.full_name or "Counselor"


@router.post("/contact")
async def submit_contact_form(body: ContactFormRequest):
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")

    clean_email = body.email.strip().lower()
    if not clean_email:
        raise HTTPException(status_code=400, detail="Email is required.")
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message is required.")

    if not await verify_recaptcha(body.captchaToken, "contact"):
        raise HTTPException(status_code=403, detail="Captcha verification failed. Please try again.")

    now = datetime.now(timezone.utc)
    query_ids = []
    async for doc in db.database.support_queries.find({}, {"query_id": 1}):
        val = doc.get("query_id", "")
        if val.startswith("CQ"):
            try:
                query_ids.append(int(val[2:]))
            except Exception:
                pass
    next_num = max(query_ids) + 1 if query_ids else 1
    query_id = f"CQ{next_num:04d}"

    new_query = {
        "query_id": query_id,
        "full_name": body.sender_name,
        "email": clean_email,
        "subject": body.subject.strip(),
        "message": body.message.strip(),
        "status": "Pending",
        "created_at": now,
    }

    await db.database.support_queries.insert_one(new_query)

    from app.services.email_service import send_contact_notification, send_contact_acknowledgement
    try:
        await send_contact_notification(
            name=body.sender_name,
            email=clean_email,
            subject=body.subject.strip(),
            message=body.message.strip(),
            query_id=query_id
        )
    except Exception as e:
        logger.warning(f"Failed to dispatch contact notification to admin: {e}")

    try:
        await send_contact_acknowledgement(
            name=body.sender_name,
            email=clean_email,
            subject=body.subject.strip(),
            query_id=query_id
        )
    except Exception as e:
        logger.warning(f"Failed to dispatch contact acknowledgement to user: {e}")

    return {
        "message": "Message sent successfully. We will get back to you within 24 to 48 hours.",
        "query_id": query_id
    }


# =============================================================
# Sign-in, signup and Google sign-in (token-issuing)
# =============================================================

PLAN_COLORS = {
    "Pro": "bg-[#E9C176] text-[#261900]",
    "Standard": "bg-[#E7E8EA] text-[#44474D]",
}
DEACTIVATED_DETAIL = "Your account has been deactivated. Do you want to reactivate your account?"


class LoginRequest(BaseModel):
    email: str
    password: str


class AdminLoginBody(BaseModel):
    adminid: str
    password: str


class SignupRequest(BaseModel):
    # Mirrors admin.py's UserCreate so SignupForm sends the same payload.
    username: str
    email: str
    name: str
    org: str = ""
    plan: Optional[str] = None  # ignored: self-signup is always Standard
    password: str
    dob: str
    gender: str = "Male"
    phone_no: str = ""
    created_at: Optional[str] = None


class GoogleLoginRequest(BaseModel):
    credential: str  # the Google ID token (JWT) from @react-oauth/google


def _require_db() -> None:
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")


def _principal_or_none(request: Request) -> Optional[TokenPayload]:
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    try:
        return decode_token(token.strip())
    except TokenError:
        return None


def _user_sub(user: dict) -> str:
    """Token subject for a users-collection document: its public id (USr-####)."""
    return str(user.get("id") or user.get("_id"))


def _user_subs(user: dict) -> set:
    return {str(v) for v in (user.get("id"), user.get("_id")) if v}


def _user_view(user: dict) -> dict:
    """Exactly the object LoginForm stored as currentUser before tokens existed."""
    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "name": user.get("name"),
        "email": user.get("email"),
        "plan": user.get("plan"),
        "message": "Login successful",
    }


def _admin_view(admin: dict) -> dict:
    """Exactly the object AdminLoginForm stored as currentAdmin before tokens existed."""
    return {
        "adminid": admin.get("adminid"),
        "name": admin.get("name", "Admin"),
        "role": admin.get("role", "admin"),
        "message": "Login successful",
    }


def _is_deactivated(user: dict) -> bool:
    return user.get("status") != "Active" or user.get("isActive") is False


def _deactivated_response(user: dict) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={"detail": DEACTIVATED_DETAIL, "is_deactivated": True, "email": user.get("email")},
    )


async def _find_user_by_email(email: str) -> Optional[dict]:
    raw = (email or "").strip()
    if not raw:
        return None
    # Older signups stored the email as typed; recovery flows lower-case it.
    return await db.database.users.find_one({"email": {"$in": list({raw, raw.lower()})}})


async def _upgrade_password(collection, doc: dict, plain: str) -> None:
    """Replace a legacy plain-text password with a bcrypt hash (only if it is unchanged)."""
    try:
        new_hash = hash_password(plain)
        result = await collection.update_one(
            {"_id": doc["_id"], "password": doc.get("password")},
            {"$set": {"password": new_hash, "password_upgraded_at": datetime.now(timezone.utc)}},
        )
        if result.modified_count:
            logger.info(f"Upgraded legacy plain-text password to bcrypt ({collection.name} {doc.get('_id')})")
    except Exception as e:  # the login itself already succeeded; retried next time
        logger.warning(f"Password hash upgrade failed for {doc.get('_id')}: {e}")


# -------------------------------------------------------------
# POST /api/auth/login  - user sign-in
# -------------------------------------------------------------
@router.post("/login")
async def login(body: LoginRequest):
    _require_db()
    user = await _find_user_by_email(body.email)
    ok, needs_upgrade = verify_password(body.password, user.get("password") if user else None)
    if not user or not ok:
        raise HTTPException(status_code=401, detail="Invalid Email or Password.")
    if needs_upgrade:
        await _upgrade_password(db.database.users, user, body.password)
    if _is_deactivated(user):
        return _deactivated_response(user)
    return {"token": create_access_token(_user_sub(user), "user"), "user": _user_view(user)}


# -------------------------------------------------------------
# POST /api/auth/admin/login  - administrator sign-in
# -------------------------------------------------------------
@router.post("/admin/login")
async def admin_login(body: AdminLoginBody):
    _require_db()
    admin = await db.database.admins.find_one({"adminid": (body.adminid or "").strip()})
    ok, needs_upgrade = verify_password(body.password, admin.get("password") if admin else None)
    if not admin or not ok:
        raise HTTPException(status_code=401, detail="Invalid Admin ID or Password.")
    if needs_upgrade:
        await _upgrade_password(db.database.admins, admin, body.password)
    return {"token": create_access_token(str(admin.get("adminid")), "admin"), "user": _admin_view(admin)}


# -------------------------------------------------------------
# POST /api/auth/signup  - self-registration with a hashed password
# -------------------------------------------------------------
async def _next_user_id() -> str:
    nums = []
    async for doc in db.database.users.find({"id": {"$regex": "^USr-"}}, {"id": 1}):
        try:
            nums.append(int(str(doc.get("id", "")).split("-")[1]))
        except (IndexError, ValueError):
            pass
    return f"USr-{max(nums) + 1 if nums else 1001}"


@router.post("/signup")
async def signup(body: SignupRequest):
    """
    Same validation as POST /api/admin/users (reused from admin.py), but the
    password is stored as a bcrypt hash, the plan is always Standard (the old
    endpoint let a caller self-assign "Pro"), and the response never echoes
    the password.
    """
    _require_db()
    from app.api.admin import (  # lazy: admin.py is under concurrent edit elsewhere
        validate_age_limit,
        validate_email_domain,
        validate_human_name,
        validate_password_strength,
    )

    email = body.email.strip()
    username = body.username.strip()
    try:
        validate_email_domain(email)
        validate_password_strength(body.password)
        password_hash = hash_password(body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    now = datetime.now(timezone.utc)
    if body.created_at:
        try:
            now = datetime.fromisoformat(body.created_at.replace("Z", "+00:00"))
        except ValueError:
            logger.warning(f"Unparseable signup created_at {body.created_at!r}; using server time")
    try:
        validate_age_limit(body.dob, now)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not await validate_human_name(username):
        raise HTTPException(
            status_code=400,
            detail="Username must be a human name (non-living things, animals, etc. are not allowed).",
        )

    existing = await db.database.users.find_one(
        {"$or": [{"username": username}, {"email": {"$in": list({email, email.lower()})}}]}
    )
    if existing:
        if existing.get("username") == username:
            raise HTTPException(status_code=409, detail="Username is already taken.")
        raise HTTPException(status_code=409, detail="Email is already registered.")

    new_user = {
        "id": await _next_user_id(),
        "username": username,
        "name": body.name,
        "email": email,
        "org": body.org,
        "plan": "Standard",
        "planColor": PLAN_COLORS["Standard"],
        "status": "Active",
        "statusColor": "bg-[#22C55E]",
        "dob": body.dob,
        "gender": body.gender,
        "password": password_hash,
        "phone_no": body.phone_no,
        "created_at": now,
    }
    await db.database.users.insert_one(new_user)
    view = {k: v for k, v in new_user.items() if k not in ("password", "_id")}
    view["created_at"] = now.isoformat()
    return view


# -------------------------------------------------------------
# Google sign-in
# -------------------------------------------------------------
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


def _google_client_id() -> str:
    cid = (getattr(settings, "GOOGLE_CLIENT_ID", "") or "").strip()
    if not cid or "your_google_client_id" in cid or not cid.endswith(".apps.googleusercontent.com"):
        return ""
    return cid


async def verify_google_id_token(credential: str, client_id: str) -> dict:
    """
    Verify a Google ID token's signature, issuer, expiry and audience.

    Uses google-auth (installed) with Google's public certs; falls back to
    Google's tokeninfo endpoint if google-auth is unavailable. Raises
    ValueError for an invalid token, ConnectionError if Google is unreachable.
    """
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token
    except ImportError:
        google_id_token = None

    if google_id_token is not None:
        try:
            return await asyncio.to_thread(
                google_id_token.verify_oauth2_token, credential, google_requests.Request(), client_id
            )
        except ValueError:
            raise
        except Exception as e:  # transport errors fetching Google's certs
            raise ConnectionError(str(e)) from e

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": credential})
    except httpx.HTTPError as e:
        raise ConnectionError(str(e)) from e
    if resp.status_code != 200:
        raise ValueError("Google rejected the token")
    info = resp.json()
    if info.get("aud") != client_id or info.get("iss") not in GOOGLE_ISSUERS:
        raise ValueError("Token was not issued for this application")
    if int(info.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
        raise ValueError("Token expired")
    return info


async def _unique_username(base: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_]", "", base.replace(" ", "_"))[:24] or "user"
    candidate, n = stem, 1
    while await db.database.users.find_one({"username": candidate}):
        n += 1
        candidate = f"{stem}{n}"
    return candidate


@router.get("/google/config")
async def google_config():
    """Public: lets the frontend render real Google sign-in only when it is configured."""
    cid = _google_client_id()
    return {"enabled": bool(cid), "client_id": cid}


@router.post("/google")
async def google_login(body: GoogleLoginRequest):
    _require_db()
    client_id = _google_client_id()
    if not client_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured.")
    try:
        info = await verify_google_id_token(body.credential, client_id)
    except ValueError as e:
        logger.warning(f"Rejected Google ID token: {e}")
        raise HTTPException(status_code=401, detail="Google sign-in could not be verified.")
    except ConnectionError as e:
        logger.error(f"Google token verification unavailable: {e}")
        raise HTTPException(status_code=503, detail="Google sign-in is temporarily unavailable.")

    email = (info.get("email") or "").strip().lower()
    verified = info.get("email_verified") in (True, "true", "True")
    if not email or not verified:
        raise HTTPException(status_code=401, detail="Your Google account email is not verified.")

    user = await _find_user_by_email(email)
    if user is None:
        name = info.get("name") or email.split("@")[0]
        user = {
            "id": await _next_user_id(),
            "username": await _unique_username(info.get("given_name") or name),
            "name": name,
            "email": email,
            "org": "",
            "plan": "Standard",
            "planColor": PLAN_COLORS["Standard"],
            "status": "Active",
            "statusColor": "bg-[#22C55E]",
            "dob": "",
            "gender": "",
            "password": None,  # Google-only account (deactivation accepts "CONFIRM")
            "phone_no": "",
            "auth_provider": "google",
            "google_sub": info.get("sub"),
            "created_at": datetime.now(timezone.utc),
        }
        await db.database.users.insert_one(user)
        logger.info(f"Created Google account {user['id']}")
    elif _is_deactivated(user):
        return _deactivated_response(user)

    return {"token": create_access_token(_user_sub(user), "user"), "user": _user_view(user)}


# -------------------------------------------------------------
# GET /api/auth/me - who does this token belong to?
# -------------------------------------------------------------
@router.get("/me")
async def me(principal: TokenPayload = Depends(require_user)):
    return {"principal": principal, "auth_required": auth_required()}
