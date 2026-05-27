from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    # ── Core ─────────────────────────────
    app_env: str = "development"
    debug: bool = True

    # ── API ──────────────────────────────
    react_app_api_url: str = "http://localhost:5173"

    # ── Auth ─────────────────────────────
    secret_key: str = "change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # ── Supabase ─────────────────────────
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None

    # ── CORS ─────────────────────────────
    allowed_origins: List[str] = []

    # ── Celery ───────────────────────────
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    # ── AI Keys ──────────────────────────
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None
    deepseek_api_key: str | None = None
    mistral_api_key: str | None = None

    # ── Drive ────────────────────────────
    google_drive_credentials_json: str | None = None
    drive_folder_id: str | None = None
    webhook_base_url: str | None = None

    disable_ssl_verification: bool = False

    # 🔥 IMPORTANT FIX
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"   # 👈 THIS FIXES YOUR ERROR
    )


def get_settings():
    return Settings()