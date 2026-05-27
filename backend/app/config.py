# backend/app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # JWT
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Gemini
    gemini_api_key: str

    # OPTIONAL (only if you use them)
    openrouter_api_key: str | None = None
    deepseek_api_key: str | None = None
    mistral_api_key: str | None = None

    # Google Drive
    google_drive_credentials_json: str = "credentials.json"
    drive_folder_id: str = ""
    webhook_base_url: str = "http://localhost:8000"

    # Celery / Redis / Valkey
    valkey_url: str = "valkey://localhost:6379/0"

    # App
    app_env: str = "development"
    allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    
    
@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    print(f"DEBUG: Loaded OpenRouter Key: {'Present' if settings.openrouter_api_key else 'MISSING'}")
    print(f"DEBUG: Loaded DeepSeek Key: {'Present' if settings.deepseek_api_key else 'MISSING'}")
    print(f"DEBUG: Loaded Mistral Key: {'Present' if settings.mistral_api_key else 'MISSING'}")
    return settings


@lru_cache
def get_settings() -> Settings:
    return Settings()