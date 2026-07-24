"""Alembic migration environment.

The database URL comes from the DATABASE_URL environment variable (never
hardcoded in alembic.ini), matching how the apps connect. target_metadata is the
single shared Base.metadata; importing each app's models below registers their
tables on it so autogenerate sees the full schema.
"""

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

import apps.projects.models  # noqa: F401

# Importing the model modules registers their tables on Base.metadata.
# (n8n has no models, so it is intentionally absent.)
import apps.strava.models  # noqa: F401
import apps.wakatime.models  # noqa: F401
from alembic import context

# Shared declarative Base — every app's models attach their tables to this.
from apps.shared.database import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Inject the runtime DATABASE_URL so the connection string lives in the
# environment, not in version control.
database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise RuntimeError(
        "DATABASE_URL environment variable must be set to run migrations."
    )
config.set_main_option("sqlalchemy.url", database_url)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a live connection)."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
