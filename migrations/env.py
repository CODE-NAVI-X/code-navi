"""Alembic environment wired to the shared ``code_navi.db`` metadata."""

from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

# Import every model module so Base.metadata is complete before autogenerate.
from code_navi.context_transfer import models as context_transfer_models  # noqa: F401
from code_navi.db import DATABASE_URL as APP_DATABASE_URL
from code_navi.db import Base
from code_navi.learning import models as learning_models  # noqa: F401
from code_navi.research import models as research_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    # Without disable_existing_loggers=False, configuring Alembic's logging
    # silences every logger already set up by the application.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def database_url() -> str:
    """Prefer an explicitly configured URL over the app's import-time default.

    ``code_navi.db`` resolves its URL when the module is first imported, so a
    caller that sets the target afterwards (tests, ``alembic -x``) would
    otherwise be ignored.
    """
    return config.get_main_option("sqlalchemy.url") or APP_DATABASE_URL


def prepare_database_directory(url: str) -> None:
    """Create the parent directory for a file-backed SQLite database."""
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or parsed.database in (None, "", ":memory:"):
        return
    Path(parsed.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting to the database."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a connection built for the resolved URL."""
    url = database_url()
    prepare_database_directory(url)
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                # SQLite cannot ALTER most columns; batch mode rebuilds the table.
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
