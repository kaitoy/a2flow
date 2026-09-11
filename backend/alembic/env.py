import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

import models  # noqa: F401 -- registers every table on SQLModel.metadata
from alembic import context
from config import get_settings
from infrastructure.database import to_async_url

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
#
# Skipped when the caller sets ``configure_logger`` to False -- the app runs
# migrations from its startup hook (infrastructure/migrations.py), by which
# point setup_logging() has already configured the root logger. fileConfig()
# defaults to disable_existing_loggers=True, so letting it run there would
# disable every logger that already exists (uvicorn's included, and they
# propagate to root with no handlers of their own) and swap root's handler for
# alembic.ini's WARNING-level console one -- silencing the app for the rest of
# the process.
if config.config_file_name is not None and config.attributes.get(
    "configure_logger", True
):
    fileConfig(config.config_file_name)

# ``import models`` above registers every table class onto SQLModel.metadata.
target_metadata = SQLModel.metadata

# Follow the same DB_URL the running app uses (config.Settings.db_url),
# normalized to its async-driver form, instead of a hardcoded/ini-file URL.
config.set_main_option("sqlalchemy.url", to_async_url(get_settings().db_url))


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
