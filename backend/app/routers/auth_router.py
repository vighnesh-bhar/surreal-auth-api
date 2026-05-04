from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.auth import get_current_user
from app.core.messages import ErrorMessages, SuccessMessages
from app.db.surreal import DB, get_db
from app.schemas.user import (
    RefreshTokenRequest,
    ResetPassword,
    ResetPasswordRequest,
    UserCreate,
    UserLogin,
    UserRegister,
)
from app.services.auth_service import (
    authenticate_user,
    create_user,
    logout_user,
    refresh_access_token,
    register_user,
    reset_pass,
    reset_pass_request,
    verify_email_code,
    verify_reset_pass_code,
)

router = APIRouter()


class LogoutRequest(BaseModel):
    refresh_token: str


@router.post("/signup")
async def signup(user: UserCreate, db: DB = Depends(get_db)):
    return await create_user(user, db)


@router.post("/login")
async def login(user: UserLogin, db: DB = Depends(get_db)):
    result = await authenticate_user(user.email, user.password, db)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ErrorMessages.INVALID_CREDENTIALS.value,
        )
    return result


@router.post("/refresh")
async def refresh_token(payload: RefreshTokenRequest, db: DB = Depends(get_db)):
    result = await refresh_access_token(payload.refresh_token, db)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ErrorMessages.INVALID_REFRESH_TOKEN.value,
        )
    return {
        "access_token": result["access_token"],
        "refresh_token": result["refresh_token"],
        "token_type": "bearer",
    }


@router.get("/verify-email")
async def verify_email(code: str = Query(..., min_length=8), db: DB = Depends(get_db)):
    result = await verify_email_code(code, db)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessages.INVALID_VERIFICATION_CODE.value,
        )
    return result


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister, db: DB = Depends(get_db)):
    return await register_user(payload, db)


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    sanitized = dict(current_user)
    sanitized.pop("password_hash", None)
    sanitized.pop("password", None)
    return sanitized


@router.post("/reset-password/request")
async def reset_pass_request_endpoint(request: ResetPasswordRequest, db: DB = Depends(get_db)):
    result = await reset_pass_request(request, db)
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessages.RESET_LINK_SEND_FAILED.value,
        )
    return {"message": SuccessMessages.RESET_LINK_SENT.value}


@router.get("/reset-password/verify")
async def verify_reset_password(code: str = Query(..., min_length=8), db: DB = Depends(get_db)):
    result = await verify_reset_pass_code(code, db)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessages.INVALID_RESET_LINK.value,
        )
    return result


@router.post("/reset-password/confirm")
async def reset_password(request: ResetPassword, db: DB = Depends(get_db)):
    result = await reset_pass(request, db)
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", ErrorMessages.RESET_FAILED.value),
        )
    return result


@router.post("/logout")
async def logout(request: LogoutRequest, db: DB = Depends(get_db)):
    result = await logout_user(request.refresh_token, db)
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorMessages.LOGOUT_FAILED.value,
        )
    return {"message": SuccessMessages.LOGGED_OUT.value}
