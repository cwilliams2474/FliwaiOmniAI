from sqlalchemy import inspect, text

from app.database.session import Base, engine

LATEST_SCHEMA_VERSION = 201
LATEST_SCHEMA_NAME = 'v2.0-final'


def _add_column(table: str, column: str, ddl: str, inspector) -> None:
    columns = {item['name'] for item in inspector.get_columns(table)}
    if column not in columns:
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {ddl}'))


def current_schema_version() -> int:
    inspector = inspect(engine)
    if 'schema_migrations' not in inspector.get_table_names():
        return 0
    with engine.connect() as conn:
        value = conn.execute(text('SELECT MAX(version) FROM schema_migrations')).scalar()
    return int(value or 0)


def _ensure_migration_journal() -> None:
    with engine.begin() as conn:
        conn.execute(text(
            'CREATE TABLE IF NOT EXISTS schema_migrations ('
            'version INTEGER PRIMARY KEY, '
            'name VARCHAR(160) NOT NULL, '
            'applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)'
        ))


def _bootstrap_tenancy() -> None:
    """Backfill organization ownership for databases created before v1.7."""
    with engine.begin() as conn:
        org_id = conn.execute(text('SELECT id FROM organizations ORDER BY id LIMIT 1')).scalar()
        if org_id is None:
            org_id = conn.execute(text(
                "INSERT INTO organizations (name, slug, onboarding_complete, created_at) "
                "VALUES ('FLIWAI', 'fliwai', FALSE, CURRENT_TIMESTAMP) RETURNING id"
            )).scalar()

        users = conn.execute(text('SELECT id, is_admin FROM users')).fetchall()
        for user_id, is_admin in users:
            exists = conn.execute(
                text('SELECT id FROM organization_members WHERE organization_id=:o AND user_id=:u'),
                {'o': org_id, 'u': user_id},
            ).scalar()
            if exists is None:
                role = 'owner' if is_admin else 'member'
                conn.execute(
                    text('INSERT INTO organization_members (organization_id, user_id, role, created_at) '
                         'VALUES (:o,:u,:r,CURRENT_TIMESTAMP)'),
                    {'o': org_id, 'u': user_id, 'r': role},
                )
            conn.execute(
                text('UPDATE users SET current_organization_id=:o WHERE id=:u AND current_organization_id IS NULL'),
                {'o': org_id, 'u': user_id},
            )

        for table in ('documents', 'tickets', 'assets', 'workflows', 'integration_connections'):
            conn.execute(text(f'UPDATE {table} SET organization_id=:o WHERE organization_id IS NULL'), {'o': org_id})

        sub = conn.execute(text('SELECT id FROM subscriptions WHERE organization_id=:o'), {'o': org_id}).scalar()
        if sub is None:
            conn.execute(text(
                "INSERT INTO subscriptions (organization_id, plan, status, seats, external_customer_id, "
                "external_subscription_id, created_at, updated_at) "
                "VALUES (:o,'starter','active',5,'','',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            ), {'o': org_id})


def migrate_schema() -> None:
    """Backward-compatible, journaled migrations for local and production v1.x installations.

    v2.0 keeps the additive migration strategy for compatibility with existing installs,
    but records an explicit schema version so readiness checks and operators can detect
    incomplete upgrades.
    """
    Base.metadata.create_all(bind=engine)
    _ensure_migration_journal()
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if 'users' not in tables:
        return

    _add_column('users', 'is_active', 'is_active BOOLEAN NOT NULL DEFAULT TRUE', inspector)
    inspector = inspect(engine)
    _add_column('users', 'token_version', 'token_version INTEGER NOT NULL DEFAULT 0', inspector)
    inspector = inspect(engine)
    _add_column('users', 'current_organization_id', 'current_organization_id INTEGER NULL', inspector)
    inspector = inspect(engine)
    _add_column('users', 'mfa_enabled', 'mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE', inspector)
    inspector = inspect(engine)
    _add_column('users', 'mfa_secret', "mfa_secret VARCHAR(128) NOT NULL DEFAULT ''", inspector)

    for table in ('documents', 'tickets', 'assets', 'workflows', 'integration_connections'):
        inspector = inspect(engine)
        if table in inspector.get_table_names():
            _add_column(table, 'organization_id', 'organization_id INTEGER NULL', inspector)

    _bootstrap_tenancy()

    with engine.begin() as conn:
        exists = conn.execute(
            text('SELECT version FROM schema_migrations WHERE version=:v'),
            {'v': LATEST_SCHEMA_VERSION},
        ).scalar()
        if exists is None:
            conn.execute(
                text('INSERT INTO schema_migrations (version, name, applied_at) '
                     'VALUES (:v, :n, CURRENT_TIMESTAMP)'),
                {'v': LATEST_SCHEMA_VERSION, 'n': LATEST_SCHEMA_NAME},
            )
