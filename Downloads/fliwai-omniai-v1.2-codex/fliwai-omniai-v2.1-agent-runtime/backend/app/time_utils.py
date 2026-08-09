from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return naive UTC for legacy SQLAlchemy DateTime columns without using deprecated utcnow()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
