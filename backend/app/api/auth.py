from datetime import datetime, timezone, timedelta
import hashlib
import random
import secrets
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from loguru import logger

from app.config import settings
from app.database import db
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
                "password": new_password,
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
async def deactivate_account(body: DeactivateAccountRequest):
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

    # Verify password (support "CONFIRM" for Google auth users or match user.password)
    user_pass = user.get("password")
    if not user_pass:
        if password != "CONFIRM":
            raise HTTPException(
                status_code=400,
                detail='This account was created with Google. Type "CONFIRM" as password to deactivate.',
            )
    else:
        if password != user_pass and password != "CONFIRM":
            raise HTTPException(status_code=401, detail="Incorrect password.")

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
