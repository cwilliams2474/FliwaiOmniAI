import os
from dataclasses import dataclass


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(',') if item.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv('APP_NAME', 'FLIWAI OmniAI API')
    environment: str = os.getenv('ENVIRONMENT', 'development')
    database_url: str = os.getenv('DATABASE_URL', 'sqlite:///./omniai.db')
    jwt_secret: str = os.getenv('JWT_SECRET', 'change_this_secret')
    jwt_expire_minutes: int = int(os.getenv('JWT_EXPIRE_MINUTES', '480'))
    openai_api_key: str = os.getenv('OPENAI_API_KEY', '')
    openai_model: str = os.getenv('OPENAI_MODEL', 'gpt-5.6-luna')
    openai_code_model: str = os.getenv('OPENAI_CODE_MODEL', 'gpt-5.3-codex')
    upload_dir: str = os.getenv('UPLOAD_DIR', '/app/uploads')
    rate_limit_per_minute: int = int(os.getenv('RATE_LIMIT_PER_MINUTE', '120'))
    app_base_url: str = os.getenv('APP_BASE_URL', 'http://localhost:3000')
    smtp_host: str = os.getenv('SMTP_HOST', '')
    smtp_port: int = int(os.getenv('SMTP_PORT', '587'))
    smtp_username: str = os.getenv('SMTP_USERNAME', '')
    smtp_password: str = os.getenv('SMTP_PASSWORD', '')
    smtp_from: str = os.getenv('SMTP_FROM', 'no-reply@localhost')
    smtp_starttls: bool = os.getenv('SMTP_STARTTLS', 'true').lower() == 'true'
    stripe_secret_key: str = os.getenv('STRIPE_SECRET_KEY', '')
    stripe_webhook_secret: str = os.getenv('STRIPE_WEBHOOK_SECRET', '')
    stripe_price_starter: str = os.getenv('STRIPE_PRICE_STARTER', '')
    stripe_price_professional: str = os.getenv('STRIPE_PRICE_PROFESSIONAL', '')
    stripe_price_enterprise: str = os.getenv('STRIPE_PRICE_ENTERPRISE', '')
    oidc_issuer: str = os.getenv('OIDC_ISSUER', '').rstrip('/')
    oidc_client_id: str = os.getenv('OIDC_CLIENT_ID', '')
    oidc_client_secret: str = os.getenv('OIDC_CLIENT_SECRET', '')
    oidc_redirect_uri: str = os.getenv('OIDC_REDIRECT_URI', 'http://localhost:8000/auth/sso/callback')
    metrics_token: str = os.getenv('METRICS_TOKEN', '')
    cors_origins: list[str] = None  # type: ignore[assignment]
    admin_emails: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, 'cors_origins', _csv(os.getenv('CORS_ORIGINS', 'http://localhost:3000')))
        object.__setattr__(self, 'admin_emails', [email.lower() for email in _csv(os.getenv('ADMIN_EMAILS', ''))])


settings = Settings()
