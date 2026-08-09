"""Safe compatibility checks for the local, one-click demonstration database."""

import sqlite3

_EXPERIMENT_EVIDENCE_COLUMNS = {
    "id",
    "conversation_id",
    "bundle_data",
    "created_at",
}
_PAPER_WORKFLOW_COLUMNS = {
    "research_paper_drafts": {"id", "conversation_id", "draft_data", "created_at"},
    "research_paper_reviews": {
        "id",
        "draft_id",
        "conversation_id",
        "review_data",
        "created_at",
    },
    "research_paper_revisions": {
        "id",
        "parent_draft_id",
        "review_id",
        "revision_data",
        "created_at",
    },
}


def _columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table_name})")}


def infer_compatible_revision(connection: sqlite3.Connection) -> str | None:
    """Return a safe Alembic revision for a known, already-created local schema.

    Older local demo databases could receive tables through development startup
    before their Alembic version row was advanced.  The caller must not stamp an
    unknown or incomplete schema, because that could hide a real migration error.
    """
    if _columns(connection, "research_experiment_evidence_bundles") != _EXPERIMENT_EVIDENCE_COLUMNS:
        return None

    if all(
        _columns(connection, table_name) == expected_columns
        for table_name, expected_columns in _PAPER_WORKFLOW_COLUMNS.items()
    ):
        return "research_paper_workflow_v1"

    if not any(_columns(connection, table_name) for table_name in _PAPER_WORKFLOW_COLUMNS):
        return "research_experiment_evidence_v1"

    return None
