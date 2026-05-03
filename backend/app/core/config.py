import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── App ─────────────────────────────
    APP_NAME: str = "My API"
    DEBUG: bool = True
    API_PREFIX: str = "/api/v1"

    # ── URLs ────────────────────────────
    APP_BASE_URL: str = "http://localhost:8001"
    FRONTEND_BASE_URL: str = "http://localhost:5173"
    PASSWORD_RESET_PATH: str = "/reset-password"

    # ── SurrealDB ───────────────────────
    SURREAL_URL: str
    SURREAL_NAMESPACE: str
    SURREAL_DB: str
    SURREAL_USERNAME: str
    SURREAL_PASSWORD: str

    # ── Auth / JWT ──────────────────────
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int

    # ── Email (SMTP) ────────────────────
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str | None = None
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False

    # ── Tokens / TTL ────────────────────
    EMAIL_VERIFICATION_TTL_SECONDS: int = 3600
    PASSWORD_RESET_TTL_SECONDS: int = 1800

    # ── File Uploads ────────────────────
    MEDIA_DIR: str = "media"
    MAX_UPLOAD_MB: int = 20

    # ── CORS ────────────────────────────
    ALLOWED_ORIGINS: list[str] = ["*"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


settings = Settings()