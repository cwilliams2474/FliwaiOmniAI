from sqlalchemy import create_engine, text

from app.database import migrations
from app.models import core  # noqa: F401 - populate metadata


def test_migration_is_idempotent_and_records_release_version(monkeypatch):
    test_engine = create_engine('sqlite:///:memory:')
    monkeypatch.setattr(migrations, 'engine', test_engine)
    migrations.migrate_schema()
    migrations.migrate_schema()
    with test_engine.connect() as conn:
        versions = conn.execute(text('SELECT version, name FROM schema_migrations')).fetchall()
        orgs = conn.execute(text('SELECT COUNT(*) FROM organizations')).scalar()
        subscriptions = conn.execute(text('SELECT COUNT(*) FROM subscriptions')).scalar()
    assert versions == [(migrations.LATEST_SCHEMA_VERSION, migrations.LATEST_SCHEMA_NAME)]
    assert orgs == 1
    assert subscriptions == 1
