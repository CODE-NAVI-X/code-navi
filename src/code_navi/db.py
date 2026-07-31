"""Shared persistence layer for every ``code_navi`` business module.

Business modules (``learning``, ``research``, …) must import ``Base`` and
``get_db`` from here rather than from one another, so no module owns another
module's engine.  Switching to PostgreSQL only requires changing
``CODE_NAVI_DATABASE_URL`` — no model or service code changes.
"""

from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

# ``LEARNING_DATABASE_URL`` is the historical name kept for compatibility with
# existing local setups; prefer ``CODE_NAVI_DATABASE_URL`` for new deployments.
DATABASE_URL: str = (
    os.environ.get("CODE_NAVI_DATABASE_URL")
    or os.environ.get("LEARNING_DATABASE_URL")
    or "sqlite:///.code-navi/learning_poc.db"
)

_engine_kwargs: dict = {}
if DATABASE_URL == "sqlite:///:memory:":
    # For in-memory SQLite, use StaticPool so every session shares the same
    # connection (and therefore the same database).
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
    _engine_kwargs["poolclass"] = StaticPool
elif DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, echo=False, **_engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

#: Single declarative base shared by all business-module ORM models.
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a per-request SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


__all__ = ["DATABASE_URL", "Base", "SessionLocal", "engine", "get_db"]
