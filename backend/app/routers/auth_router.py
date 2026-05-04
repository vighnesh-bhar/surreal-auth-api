from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr

from app.core.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.core.messages import ErrorMessages, SuccessMessages
from app.db.surreal import DB, get_db
from app.schemas.user import (
    RefreshTokenRequest,
    ResetPassword,
    ResetPasswordRequest,
    UserCreate,
    UserLogin,
)
from app.services.auth_service import (
    create_user,
    logout_user,
    reset_pass,
    reset_pass_request,
    verify_email_code,
    verify_reset_pass_code,
)

router = APIRouter()

class LogoutRequest(BaseModel):
    refresh_token: str


@router.post("/signup")
async def signup(user: UserCreate):
    return await create_user(user)


@router.post("/login")
async def login(user: UserLogin, db: DB = Depends(get_db)):
    email = user.email.strip().lower()
    rows = await db.query("SELECT * FROM user WHERE email = $email LIMIT 1", {"email": email})
    if not rows:
        raise HTTPException(status_code=401, detail=ErrorMessages.INVALID_CREDENTIALS.value)

    u = rows[0]
    if u.get("is_active") is False:
        raise HTTPException(status_code=403, detail=ErrorMessages.ACCOUNT_DISABLED.value)

    if not verify_password(user.password, u.get("password_hash", "")):
        raise HTTPException(status_code=401, detail=ErrorMessages.INVALID_CREDENTIALS.value)

    user_id = u.get("id")
    return {
        "access_token": create_access_token(str(user_id)),
        "refresh_token": create_refresh_token(str(user_id)),
        "token_type": "bearer",
    }


@router.post("/refresh")
async def refresh_token(payload: RefreshTokenRequest, db: DB = Depends(get_db)):
    try:
        decoded = decode_token(payload.refresh_token)
    except HTTPException:
        raise HTTPException(status_code=401, detail=ErrorMessages.INVALID_REFRESH_TOKEN.value)

    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=401, detail=ErrorMessages.INVALID_REFRESH_TOKEN.value)

    user_id = str(decoded.get("sub") or "")
    user = await db.select_one("user", user_id)
    if not user:
        raise HTTPException(status_code=401, detail=ErrorMessages.INVALID_REFRESH_TOKEN.value)

    return {
        "access_token": create_access_token(user_id),
        "refresh_token": payload.refresh_token,
        "token_type": "bearer",
    }


@router.get("/verify-email")
async def verify_email(code: str = Query(..., min_length=8)):
    # Uses legacy service until verification is migrated.
    result = verify_email_code(code)
    if not result:
        raise HTTPException(status_code=400, detail=ErrorMessages.INVALID_VERIFICATION_CODE.value)
    return result


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "user"


@router.post("/register", status_code=201)
async def register(payload: RegisterRequest, db: DB = Depends(get_db)):
    now = datetime.now(timezone.utc).isoformat()
    email = payload.email.strip().lower()

    existing = await db.query("SELECT id FROM user WHERE email = $email LIMIT 1", {"email": email})
    if existing:
        raise HTTPException(status_code=409, detail=ErrorMessages.EMAIL_ALREADY_REGISTERED.value)

    user = await db.create(
        "user",
        {
            "email": email,
            "password_hash": hash_password(payload.password),
            "name": payload.name,
            "role": payload.role,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
    )

    user_id = str(user.get("id", ""))
    return {
        "access_token": create_access_token(user_id),
        "refresh_token": create_refresh_token(user_id),
        "token_type": "bearer",
    }


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    sanitized = dict(current_user)
    sanitized.pop("password_hash", None)
    return sanitized

@router.post("/reset-password/request")
async def reset_pass_request_endpoint(request: ResetPasswordRequest):
    result = reset_pass_request(request)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=ErrorMessages.RESET_LINK_SEND_FAILED.value)

    return {"message": SuccessMessages.RESET_LINK_SENT.value}


@router.get("/reset-password/verify")
async def verify_reset_password(code: str = Query(..., min_length=8)):
    result = verify_reset_pass_code(code)
    if not result:
        raise HTTPException(status_code=400, detail=ErrorMessages.INVALID_RESET_LINK.value)
    return result


@router.post("/reset-password/confirm")
async def reset_password(request: ResetPassword):
    result = reset_pass(request)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", ErrorMessages.RESET_FAILED.value))
    return result

@router.post("/logout")
def logout(request: LogoutRequest):
    result = logout_user(request.refresh_token)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=ErrorMessages.LOGOUT_FAILED.value)

    return {"message": SuccessMessages.LOGGED_OUT.value}