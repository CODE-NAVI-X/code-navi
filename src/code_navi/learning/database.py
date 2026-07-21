"""SQLAlchemy engine, session factory, and FastAPI dependency for the learning module.

Uses SQLite by default (file-based for PoC; ``sqlite:///:memory:`` for tests).
Switch to PostgreSQL by changing only ``DATABASE_URL`` — no model or service code
changes are required.
"""

from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

DATABASE_URL: str = os.environ.get(
    "LEARNING_DATABASE_URL",
    "sqlite:///.code-navi/learning_poc.db",
)

_engine_kwargs: dict = {}
if DATABASE_URL.startswith("sqlite") and DATABASE_URL == "sqlite:///:memory:":
    # For in-memory SQLite, use StaticPool so every session shares the same
    # connection (and therefore the same database).
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
    _engine_kwargs["poolclass"] = StaticPool
elif DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, echo=False, **_engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a per-request SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
