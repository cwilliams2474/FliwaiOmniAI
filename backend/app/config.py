from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration comes from environment variables (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "OmniAI"
    environment: str = "production"  # production | development | test
    public_url: str = "http://localhost"

    database_url: str = "postgresql+psycopg://omniai:omniai@db:5432/omniai"

    # Signing key for session tokens. Must be long and random in production.
    secret_key: str = Field(default="change-me", min_length=8)
    # Separate key for encrypting stored secrets (integration credentials, MFA seeds).
    # Generate with: python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
    encryption_key: str = ""

    session_hours: int = 12
    cookie_secure: bool = True
    login_max_attempts: int = 5
    login_window_seconds: int = 300

    upload_dir: Path = Path("/data/uploads")
    max_upload_mb: int = 25

    # AI provider: "openai" (any OpenAI-compatible API, incl. Ollama / vLLM / LM Studio),
    # "anthropic", or "none" (search-only answers, no model calls).
    ai_provider: str = "none"
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str = ""
    ai_model: str = "gpt-4o-mini"
    ai_max_tokens: int = 1200
    ai_timeout_seconds: int = 90

    # Scheduled workflows. Cron times are read in this time zone.
    scheduler_enabled: bool = True
    scheduler_timezone: str = "America/New_York"
    scheduler_interval_seconds: int = 30

    # Optional SMTP for password reset emails. If unset, reset links are written to the server log.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "omniai@localhost"
    smtp_starttls: bool = True

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
