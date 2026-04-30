from pydantic import BaseModel, ConfigDict, EmailStr
from datetime import datetime

class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ResetPasswordRequest(BaseModel):
    email: EmailStr

class ResetPassword(BaseModel):
    code: str
    password: str
    confirmPass: str

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    status: str
    email_verified: bool
    date_joined: datetime
    updated_at: datetime