from app.config import settings


def test_rate_limit_has_safe_floor():
    assert settings.rate_limit_per_minute >= 1
