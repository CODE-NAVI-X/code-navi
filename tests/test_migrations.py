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

from code_navi.context_transfer import models as context_transfer_models  # noqa: E402,F401
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


def test_confirmation_migration_preserves_existing_drafts_and_conversations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Revision 0005 must retain 0004 rows and mark existing transfers as drafts."""
    database_url = f"sqlite:///{tmp_path / 'context-upgrade.db'}"
    monkeypatch.setenv("CODE_NAVI_DATABASE_URL", database_url)
    config = _alembic_config(database_url)
    command.upgrade(config, "0004")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        from sqlalchemy import text

        connection.execute(
            text(
                "INSERT INTO research_conversations "
                "(id, profile_data, messages_data, created_at, updated_at) VALUES "
                "('conversation-before-confirm', '{}', '[]', CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO context_transfers "
                "(id, source_module, source_object_type, source_object_id, "
                "source_scope_id, target_module, topic, summary, selected_content, "
                "created_at, updated_at) VALUES "
                "('transfer-before-confirm', 'learning', 'notebook_item', 'note-1', "
                "'sess-1', 'research', 'topic', 'summary', '[]', CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP)"
            )
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            from sqlalchemy import text

            transfer = connection.execute(
                text(
                    "SELECT id, status, confirmed_conversation_id, confirmed_at "
                    "FROM context_transfers"
                )
            ).one()
            conversation = connection.execute(
                text("SELECT id, context_provenance FROM research_conversations")
            ).one()
    finally:
        engine.dispose()

    assert transfer == ("transfer-before-confirm", "draft", None, None)
    assert conversation == ("conversation-before-confirm", None)


def test_latest_migration_repairs_a_stale_conversation_context_column(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A database marked at the old head still gains a missing safe column."""
    database_url = f"sqlite:///{tmp_path / 'stale-context.db'}"
    monkeypatch.setenv("CODE_NAVI_DATABASE_URL", database_url)
    config = _alembic_config(database_url)
    command.upgrade(config, "research_citation_scaffold_v1")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        from sqlalchemy import text

        connection.execute(
            text(
                "CREATE TABLE research_conversations_repaired "
                "(id VARCHAR(36) PRIMARY KEY, profile_data JSON NOT NULL, "
                "messages_data JSON NOT NULL, created_at DATETIME NOT NULL, "
                "updated_at DATETIME NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO research_conversations_repaired "
                "(id, profile_data, messages_data, created_at, updated_at) "
                "SELECT id, profile_data, messages_data, created_at, updated_at "
                "FROM research_conversations"
            )
        )
        connection.execute(text("DROP TABLE research_conversations"))
        connection.execute(
            text("ALTER TABLE research_conversations_repaired RENAME TO research_conversations")
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            columns = {
                row[1]
                for row in connection.execute(
                    text("PRAGMA table_info(research_conversations)")
                )
            }
    finally:
        engine.dispose()

    assert "context_provenance" in columns
