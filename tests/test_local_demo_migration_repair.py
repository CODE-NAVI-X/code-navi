from __future__ import annotations

import sqlite3

from code_navi.local_demo_migrations import infer_compatible_revision


def _create_table(connection: sqlite3.Connection, name: str, columns: str) -> None:
    connection.execute(f"CREATE TABLE {name} ({columns})")


def test_infers_paper_workflow_revision_for_preexisting_workflow_tables() -> None:
    connection = sqlite3.connect(":memory:")
    _create_table(
        connection,
        "research_experiment_evidence_bundles",
        "id TEXT, conversation_id TEXT, bundle_data JSON, created_at DATETIME",
    )
    _create_table(
        connection,
        "research_paper_drafts",
        "id TEXT, conversation_id TEXT, draft_data JSON, created_at DATETIME",
    )
    _create_table(
        connection,
        "research_paper_reviews",
        "id TEXT, draft_id TEXT, conversation_id TEXT, review_data JSON, created_at DATETIME",
    )
    _create_table(
        connection,
        "research_paper_revisions",
        "id TEXT, parent_draft_id TEXT, review_id TEXT, revision_data JSON, created_at DATETIME",
    )

    assert infer_compatible_revision(connection) == "research_paper_workflow_v1"


def test_does_not_repair_unknown_partial_schema() -> None:
    connection = sqlite3.connect(":memory:")
    _create_table(
        connection,
        "research_experiment_evidence_bundles",
        "id TEXT, conversation_id TEXT, bundle_data JSON",
    )

    assert infer_compatible_revision(connection) is None
