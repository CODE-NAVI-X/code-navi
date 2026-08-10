"""Repair only a recognised stale Alembic marker in the local demo database."""

import os
import sqlite3
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from code_navi.local_demo_migrations import infer_compatible_revision

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _sqlite_database_path(database_url: str) -> Path | None:
    parsed = make_url(database_url)
    if parsed.get_backend_name() != "sqlite" or parsed.database in (None, "", ":memory:"):
        return None
    return Path(parsed.database).expanduser().resolve()


def main() -> int:
    database_url = os.environ.get("CODE_NAVI_DATABASE_URL", "")
    database_path = _sqlite_database_path(database_url)
    if database_path is None or not database_path.is_file():
        print(
            "[ERROR] Only an existing SQLite local demo database can be repaired.",
            file=sys.stderr,
        )
        return 1

    with sqlite3.connect(database_path) as connection:
        revision = infer_compatible_revision(connection)
    if revision is None:
        print(
            "[ERROR] Local database schema is incomplete or unrecognised; "
            "no migration marker was changed.",
            file=sys.stderr,
        )
        return 1

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    print(f"[INFO] Recognised existing local schema; repairing Alembic marker to {revision}.")
    command.stamp(config, revision)
    command.upgrade(config, "head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
