"""Add auth identity system: users, principals, sessions, tokens, events, and owner_principal_id.

Revision ID: auth_identity_system_v1
Revises: practice_launch_outcomes_v1
Create Date: 2026-08-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "auth_identity_system_v1"
down_revision: str | None = "practice_launch_outcomes_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email_normalized", sa.String(length=320), nullable=False),
        sa.Column("email_display", sa.String(length=320), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(), nullable=True),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="pending_verification"
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deletion_requested_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email_normalized"),
    )

    # 2. Create principals table
    op.create_table(
        "principals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("legacy_scope_id", sa.String(length=64), nullable=True),
        sa.Column("legacy_learner_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_principals_user_id", "principals", ["user_id"])
    op.create_index("ix_principals_legacy_scope_id", "principals", ["legacy_scope_id"])
    op.create_index("ix_principals_legacy_learner_id", "principals", ["legacy_learner_id"])

    # 3. Create password_credentials table
    op.create_table(
        "password_credentials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    # 4. Create auth_sessions table
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("principal_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column("remembered", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("user_agent_label", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(["principal_id"], ["principals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_auth_sessions_principal_id", "auth_sessions", ["principal_id"])

    # 5. Create auth_one_time_tokens table
    op.create_table(
        "auth_one_time_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("new_email_normalized", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_auth_one_time_tokens_user_purpose",
        "auth_one_time_tokens",
        ["user_id", "purpose"],
    )

    # 6. Create auth_events table
    op.create_table(
        "auth_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("principal_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["principal_id"], ["principals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_events_user_id", "auth_events", ["user_id"])
    op.create_index("ix_auth_events_principal_id", "auth_events", ["principal_id"])

    # 7. Add owner_principal_id to all relevant business tables (nullable for compat period)
    _tables_to_migrate = [
        "workspaces",
        "notebook_items",
        "research_conversations",
        "quiz_attempts",
        "confusion_marks",
        "practice_launches",
        "practice_outcomes",
        "context_transfers",
    ]
    for table in _tables_to_migrate:
        op.add_column(
            table,
            sa.Column(
                "owner_principal_id",
                sa.String(length=36),
                # Note: SQLite does not support ALTER TABLE ADD COLUMN with inline FK.
                # The application-level FK relationship is enforced via the ORM.
                nullable=True,
            ),
        )
        op.create_index(
            f"ix_{table}_owner_principal_id",
            table,
            ["owner_principal_id"],
        )

    # 8. Backfill: create legacy guest principals for existing rows
    # Use raw SQL via op.execute for compatibility
    _backfill_legacy_principals()


def _backfill_legacy_principals() -> None:
    """Create Legacy Guest Principals for existing data rows.

    Each unique legacy identifier gets one Principal with origin=''guest'',
    legacy_scope_id / legacy_learner_id set. Rows are then pointed to it
    via owner_principal_id.
    """
    import uuid
    from datetime import UTC, datetime

    conn = op.get_bind()
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    # Helper: upsert a legacy principal and return its id
    def _ensure_principal(legacy_scope_id=None, legacy_learner_id=None):
        if legacy_scope_id:
            row = conn.execute(
                sa.text(
                    "SELECT id FROM principals WHERE legacy_scope_id = :sid LIMIT 1"
                ),
                {"sid": legacy_scope_id},
            ).fetchone()
        elif legacy_learner_id:
            row = conn.execute(
                sa.text(
                    "SELECT id FROM principals WHERE legacy_learner_id = :lid LIMIT 1"
                ),
                {"lid": legacy_learner_id},
            ).fetchone()
        else:
            return None
        if row:
            return row[0]
        pid = str(uuid.uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO principals (id, user_id, origin, legacy_scope_id, "
                "legacy_learner_id, created_at) VALUES "
                "(:id, NULL, ''guest'', :sid, :lid, :now)"
            ),
            {"id": pid, "sid": legacy_scope_id, "lid": legacy_learner_id, "now": now},
        )
        return pid

    # workspaces: backfill from owner_scope_id
    try:
        rows = conn.execute(
            sa.text(
                "SELECT DISTINCT owner_scope_id FROM workspaces "
                "WHERE owner_scope_id IS NOT NULL"
            )
        ).fetchall()
        for (scope_id,) in rows:
            pid = _ensure_principal(legacy_scope_id=scope_id)
            if pid:
                conn.execute(
                    sa.text(
                        "UPDATE workspaces SET owner_principal_id = :pid "
                        "WHERE owner_scope_id = :sid"
                    ),
                    {"pid": pid, "sid": scope_id},
                )
    except Exception:
        pass

    # notebook_items: backfill from session_id
    try:
        rows = conn.execute(
            sa.text("SELECT DISTINCT session_id FROM notebook_items WHERE session_id IS NOT NULL")
        ).fetchall()
        for (sid,) in rows:
            pid = _ensure_principal(legacy_scope_id=sid)
            if pid:
                conn.execute(
                    sa.text(
                        "UPDATE notebook_items SET owner_principal_id = :pid "
                        "WHERE session_id = :sid"
                    ),
                    {"pid": pid, "sid": sid},
                )
    except Exception:
        pass

    # research_conversations: each conversation gets its own legacy principal (no scope column)
    try:
        rows = conn.execute(
            sa.text("SELECT id FROM research_conversations WHERE owner_principal_id IS NULL")
        ).fetchall()
        for (conv_id,) in rows:
            pid = str(uuid.uuid4())
            conn.execute(
                sa.text(
                    "INSERT INTO principals (id, user_id, origin, legacy_scope_id, "
                    "legacy_learner_id, created_at) VALUES "
                    "(:id, NULL, ''guest'', :sid, NULL, :now)"
                ),
                {"id": pid, "sid": f"conv:{conv_id}", "now": now},
            )
            conn.execute(
                sa.text(
                    "UPDATE research_conversations SET owner_principal_id = :pid WHERE id = :cid"
                ),
                {"pid": pid, "cid": conv_id},
            )
    except Exception:
        pass

    # quiz_attempts and confusion_marks: backfill from profile_id
    for table in ("quiz_attempts", "confusion_marks"):
        try:
            rows = conn.execute(
                sa.text(f"SELECT DISTINCT profile_id FROM {table} WHERE profile_id IS NOT NULL")
            ).fetchall()
            for (profile_id,) in rows:
                pid = _ensure_principal(legacy_learner_id=profile_id)
                if pid:
                    conn.execute(
                        sa.text(
                            f"UPDATE {table} SET owner_principal_id = :pid WHERE profile_id = :lid"
                        ),
                        {"pid": pid, "lid": profile_id},
                    )
        except Exception:
            pass

    # practice_launches, practice_outcomes: backfill from local_profile_id
    for table in ("practice_launches", "practice_outcomes"):
        try:
            rows = conn.execute(
                sa.text(
                    f"SELECT DISTINCT local_profile_id FROM {table} "
                    f"WHERE local_profile_id IS NOT NULL"
                )
            ).fetchall()
            for (profile_id,) in rows:
                pid = _ensure_principal(legacy_scope_id=profile_id)
                if pid:
                    conn.execute(
                        sa.text(
                            f"UPDATE {table} SET owner_principal_id = :pid "
                            f"WHERE local_profile_id = :pid_val"
                        ),
                        {"pid": pid, "pid_val": profile_id},
                    )
        except Exception:
            pass

    # context_transfers: backfill from source_scope_id
    try:
        rows = conn.execute(
            sa.text(
                "SELECT DISTINCT source_scope_id FROM context_transfers "
                "WHERE source_scope_id IS NOT NULL"
            )
        ).fetchall()
        for (scope_id,) in rows:
            pid = _ensure_principal(legacy_scope_id=scope_id)
            if pid:
                conn.execute(
                    sa.text(
                        "UPDATE context_transfers SET owner_principal_id = :pid "
                        "WHERE source_scope_id = :sid"
                    ),
                    {"pid": pid, "sid": scope_id},
                )
    except Exception:
        pass


def downgrade() -> None:
    # Remove owner_principal_id from business tables
    _tables_to_migrate = [
        "context_transfers",
        "practice_outcomes",
        "practice_launches",
        "confusion_marks",
        "quiz_attempts",
        "research_conversations",
        "notebook_items",
        "workspaces",
    ]
    for table in _tables_to_migrate:
        try:
            op.drop_index(f"ix_{table}_owner_principal_id", table_name=table)
        except Exception:
            pass
        try:
            op.drop_column(table, "owner_principal_id")
        except Exception:
            pass

    op.drop_index("ix_auth_events_principal_id", table_name="auth_events")
    op.drop_index("ix_auth_events_user_id", table_name="auth_events")
    op.drop_table("auth_events")
    op.drop_index("ix_auth_one_time_tokens_user_purpose", table_name="auth_one_time_tokens")
    op.drop_table("auth_one_time_tokens")
    op.drop_index("ix_auth_sessions_principal_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("password_credentials")
    op.drop_index("ix_principals_legacy_learner_id", table_name="principals")
    op.drop_index("ix_principals_legacy_scope_id", table_name="principals")
    op.drop_index("ix_principals_user_id", table_name="principals")
    op.drop_table("principals")
    op.drop_table("users")
