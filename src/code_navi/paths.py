"""Portable runtime paths resolved for the current installation."""

from __future__ import annotations

import os
from pathlib import Path


def application_data_dir(project_root: Path | None = None) -> Path:
    """Return an absolute writable data directory without machine-specific paths."""
    configured = os.getenv("CODE_NAVI_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    configured_root = os.getenv("CODE_NAVI_PROJECT_ROOT")
    root = Path(configured_root).expanduser() if configured_root else project_root
    return ((root or Path.cwd()).resolve() / ".code-navi").resolve()


def sqlite_file_url(path: Path) -> str:
    """Build a cross-platform SQLAlchemy URL for an absolute SQLite file."""
    resolved = path.expanduser().resolve()
    return f"sqlite:///{resolved.as_posix()}"


__all__ = ["application_data_dir", "sqlite_file_url"]
