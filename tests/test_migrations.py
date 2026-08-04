"""Guard against ORM models drifting away from the Alembic migration chain."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine

alembic = pytest.importorskip("alembic")

from alembic import command  # noqa: E402
from alembic.autogenerate import compare_metadata  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.migration import MigrationContext  # noqa: E402

from code_navi.db import Base  # noqa: E402
from code_navi.learning import models as learning_models  # noqa: E402,F401
from code_navi.research import models as research_models  # noqa: E402,F401

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config(database_url: str) -> Config:
    config = Config(str(_REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_migrations_produce_the_current_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`alembic upgrade head` must yield exactly what the ORM declares."""
    database_url = f"sqlite:///{tmp_path / 'missing-parent' / 'migrated.db'}"
    # env.py builds its engine from code_navi.db, so point that at the temp file.
    monkeypatch.setenv("CODE_NAVI_DATABASE_URL", database_url)

    command.upgrade(_alembic_config(database_url), "head")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            drift = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    finally:
        engine.dispose()

    assert drift == [], f"models and migrations disagree: {drift}"


def test_legacy_rows_are_backfilled_not_dropped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Upgrading a pre-session_id database must preserve existing entries."""
    database_url = f"sqlite:///{tmp_path / 'legacy.db'}"
    monkeypatch.setenv("CODE_NAVI_DATABASE_URL", database_url)
    config = _alembic_config(database_url)

    command.upgrade(config, "0001")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        from sqlalchemy import text

        connection.execute(
            text(
                "INSERT INTO notebook_items "
                "(id, user_id, knowledge_id, item_type, content) "
                "VALUES ('legacy-1', 'poc-user', 'k', 'summary', 'old row')"
            )
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            from sqlalchemy import text

            rows = connection.execute(text("SELECT id, session_id FROM notebook_items")).fetchall()
    finally:
        engine.dispose()

    assert rows == [("legacy-1", "sess-legacy-import")]
