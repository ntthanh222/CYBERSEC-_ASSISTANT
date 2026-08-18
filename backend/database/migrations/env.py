"""Alembic environment: uses the same Settings-derived URL as the app.

Runs synchronously (Alembic's normal mode) via the psycopg3 driver, which
supports both sync and async use from the same connection string the
application uses for its async engine.
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.config.settings import get_settings  # noqa: E402
from backend.database.base import Base  # noqa: E402
from backend.database import models  # noqa: E402,F401 - registers models on Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
# get_settings() itself refuses to construct (raises) if APP_ENV is
# staging/production and either DATABASE_URL or DATABASE_MIGRATION_URL
# would not use verified TLS - see Settings._require_tls_for_staging_and_production
# and backend/core/tls.py. That is the single enforcement point; this
# module does not duplicate the check.
#
# Alembic always targets DATABASE_MIGRATION_URL when set (e.g. Supabase's
# direct, non-pooled connection) - never the pooled runtime DATABASE_URL.
#
# set_main_option() stores the value through configparser's
# BasicInterpolation, which treats a bare "%" as the start of an
# interpolation directive and raises ValueError. A percent-encoded password
# (e.g. "%22" for a literal '"') is exactly this shape, so it must be
# escaped as "%%" going in - configparser un-escapes it back to a single
# "%" on every subsequent get_main_option()/get_section() read.
config.set_main_option(
    "sqlalchemy.url", settings.database_migration_url.replace("%", "%%")
)

# Phase 2 introduced the ORM layer, so autogenerate has something to diff
# against. Migrations are still hand-reviewed; autogenerate is a drafting aid.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
