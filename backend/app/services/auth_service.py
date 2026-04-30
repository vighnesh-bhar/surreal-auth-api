from datetime import datetime, timedelta
import secrets

from fastapi import HTTPException, status
from jose import JWTError

from app.db.surreal import DB
from app.core.config import settings
from app.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.messages import ErrorMessages, SuccessMessages
from app.services.email_service import send_email
import hashlib


# ── Helpers ─────────────────────────────

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ── Signup ──────────────────────────────

async def create_user(user, db: DB):
    hashed = hash_password(user.password)
    now = datetime.utcnow().isoformat()

    created = await db.create("user", {
        "name": user.name,
        "email": user.email.strip().lower(),
        "password": hashed,
        "status": "pending",
        "email_verified": False,
        "date_joined": now,
        "updated_at": now,
    })

    user_id = created["id"]

    await _create_and_send_email_verification(user.email, user_id, db)

    return created


async def _create_and_send_email_verification(email: str, user_id: str, db: DB):
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=settings.EMAIL_VERIFICATION_TTL_SECONDS)
    code = secrets.token_urlsafe(32)

    await db.create("email_verifications", {
        "code": code,
        "user_id": user_id,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    })

    verify_url = f"{settings.APP_BASE_URL}/auth/verify-email?code={code}"

    send_email(
        email,
        "Verify your email",
        f"Click to verify:\n{verify_url}"
    )


# ── Email Verification ─────────────────

async def verify_email_code(code: str, db: DB):
    rows = await db.query(
        "SELECT * FROM email_verifications WHERE code = $code LIMIT 1",
        {"code": code},
    )

    if not rows:
        return None

    record = rows[0]

    expires_at = record.get("expires_at")
    user_id = record.get("user_id")

    if not expires_at or not user_id:
        return None

    expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))

    if datetime.utcnow() > expires_dt.replace(tzinfo=None):
        return None

    now = datetime.utcnow().isoformat()

    await db.update("user", user_id, {
        "email_verified": True,
        "status": "active",
        "updated_at": now,
    })

    await db.query(
        "DELETE FROM email_verifications WHERE code = $code",
        {"code": code},
    )

    return {"verified": True}


# ── Login ─────────────────────────────

async def authenticate_user(email: str, password: str, db: DB):
    users = await db.query(
        "SELECT * FROM user WHERE email = $email LIMIT 1",
        {"email": email.strip().lower()},
    )

    if not users:
        return None

    user = users[0]

    if not verify_password(password, user["password"]):
        return None

    user_id = user["id"]

    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)

    await db.create("sessions", {
        "user_id": user_id,
        "refresh_token_hash": hash_token(refresh_token),
        "expires_at": (datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)).isoformat(),
        "revoked": False,
    })

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


# ── Refresh (ROTATING TOKENS) ─────────

async def refresh_access_token(refresh_token: str, db: DB):
    try:
        payload = decode_token(refresh_token)

        if payload["type"] != "refresh":
            return None

        user_id = payload["sub"]
        hashed = hash_token(refresh_token)

        sessions = await db.query(
            "SELECT * FROM sessions WHERE refresh_token_hash = $hash LIMIT 1",
            {"hash": hashed},
        )

        if not sessions:
            return None

        session = sessions[0]

        if session.get("revoked"):
            return None

        # revoke old
        await db.update("sessions", session["id"], {"revoked": True})

        # create new tokens
        new_access = create_access_token(user_id)
        new_refresh = create_refresh_token(user_id)

        await db.create("sessions", {
            "user_id": user_id,
            "refresh_token_hash": hash_token(new_refresh),
            "expires_at": (datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)).isoformat(),
            "revoked": False,
        })

        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
        }

    except JWTError:
        return None


# ── Logout ────────────────────────────

async def logout_user(refresh_token: str, db: DB):
    hashed = hash_token(refresh_token)

    sessions = await db.query(
        "SELECT * FROM sessions WHERE refresh_token_hash = $hash LIMIT 1",
        {"hash": hashed},
    )

    if not sessions:
        return {"success": True}

    session = sessions[0]

    await db.update("sessions", session["id"], {"revoked": True})

    return {"success": True}


async def reset_pass_request(request, db: DB):
    normalized_email = request.email.strip().lower()

    users = await db.query(
        "SELECT * FROM user WHERE email = $email LIMIT 1",
        {"email": normalized_email},
    )

    # Avoid email enumeration
    if not users:
        return {"success": True}

    user = users[0]
    user_id = (
        user["id"].id
        if hasattr(user.get("id"), "id")
        else str(user.get("id")).split(":")[-1]
    )

    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=settings.PASSWORD_RESET_TTL_SECONDS)
    code = secrets.token_urlsafe(32)

    await db.create(
        "password_resets",
        {
            "code": code,
            "user_id": user_id,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "used": False,
        },
    )

    reset_url = (
        f"{settings.FRONTEND_BASE_URL.rstrip('/')}"
        f"{settings.PASSWORD_RESET_PATH}?code={code}"
    )

    subject = "Reset your password"
    body = (
        "Click the link to reset your password:\n\n"
        f"{reset_url}\n\n"
        f"This link expires at {expires_at.isoformat()} UTC."
    )

    await send_email(normalized_email, subject, body)

    return {"success": True}

async def verify_reset_pass_code(code: str, db: DB):
    rows = await db.query(
        "SELECT * FROM password_resets WHERE code = $code LIMIT 1",
        {"code": code},
    )

    if not rows:
        return None

    record = rows[0]

    if record.get("used"):
        return None

    expires_at = record.get("expires_at")
    user_id = record.get("user_id")

    if not expires_at or not user_id:
        return None

    try:
        expires_dt = datetime.fromisoformat(
            str(expires_at).replace("Z", "+00:00")
        )
    except Exception:
        return None

    if datetime.utcnow() > expires_dt.replace(tzinfo=None):
        return None

    return {"valid": True}

async def reset_pass(request, db: DB):
    if request.password != request.confirmPass:
        return {"success": False, "message": ErrorMessages.PASSWORD_MISMATCH.value}

    rows = await db.query(
        "SELECT * FROM password_resets WHERE code = $code LIMIT 1",
        {"code": request.code},
    )

    if not rows:
        return {"success": False, "message": ErrorMessages.INVALID_RESET.value}

    record = rows[0]

    if record.get("used"):
        return {"success": False, "message": ErrorMessages.INVALID_RESET.value}

    expires_at = record.get("expires_at")
    user_id = record.get("user_id")

    if not expires_at or not user_id:
        return {"success": False, "message": ErrorMessages.INVALID_RESET.value}

    try:
        expires_dt = datetime.fromisoformat(
            str(expires_at).replace("Z", "+00:00")
        )
    except Exception:
        return {"success": False, "message": ErrorMessages.INVALID_RESET.value}

    if datetime.utcnow() > expires_dt.replace(tzinfo=None):
        return {"success": False, "message": ErrorMessages.INVALID_RESET.value}

    now = datetime.utcnow().isoformat()

    await db.query(
        "UPDATE type::record($table, $id) SET password = $password, updated_at = $now",
        {
            "table": "user",
            "id": str(user_id).split(":")[-1],
            "password": hash_password(request.password),
            "now": now,
        },
    )

    reset_record_id = str(record["id"]).split(":")[-1]

    await db.query(
        "UPDATE type::record($table, $id) SET used = true",
        {"table": "password_resets", "id": reset_record_id},
    )

    return {"success": True, "message": SuccessMessages.PASSWORD_RESET_SUCCESS.value}