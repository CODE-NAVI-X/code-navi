"""Privacy-minimized SQLite persistence for personal compiler learning records."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .evaluation import AiFeedback, RuleAssessment
from .piston import ExecutionResult


@dataclass(frozen=True, slots=True)
class LearningRecord:
    """One personal execution summary without raw source or standard input."""

    record_id: str
    learner_id: str
    created_at: str
    category: str
    title: str
    summary: str
    error_type: str | None
    line: int | None
    ai_status: str
    ai_explanation: str | None
    suggestions: tuple[str, ...]
    reference_score: int | None
    source_hash: str
    source_bytes: int
    wall_time_ms: int | None

    def as_dict(self) -> dict[str, Any]:
        """Serialize a record for the learner history API."""

        return {
            "id": self.record_id,
            "createdAt": self.created_at,
            "category": self.category,
            "title": self.title,
            "summary": self.summary,
            "errorType": self.error_type,
            "line": self.line,
            "aiStatus": self.ai_status,
            "aiExplanation": self.ai_explanation,
            "suggestions": list(self.suggestions),
            "referenceScore": self.reference_score,
            "sourceHash": self.source_hash,
            "sourceBytes": self.source_bytes,
            "wallTimeMs": self.wall_time_ms,
        }


class LearningRecordStore:
    """Store and query records using short-lived SQLite connections."""

    def __init__(self, database_path: str | Path) -> None:
        self._path = Path(database_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def add(
        self,
        learner_id: str,
        source: str,
        result: ExecutionResult,
        assessment: RuleAssessment,
        *,
        ai_status: str,
        feedback: AiFeedback | None,
    ) -> LearningRecord:
        """Persist one normalized record and return it."""

        encoded_source = source.encode("utf-8")
        record = LearningRecord(
            record_id=str(uuid4()),
            learner_id=learner_id,
            created_at=datetime.now(UTC).isoformat(),
            category=assessment.category,
            title=assessment.title,
            summary=assessment.summary,
            error_type=assessment.error_type,
            line=assessment.line,
            ai_status=ai_status,
            ai_explanation=None if feedback is None else feedback.explanation,
            suggestions=() if feedback is None else feedback.suggestions,
            reference_score=None if feedback is None else feedback.quality.overall,
            source_hash=hashlib.sha256(encoded_source).hexdigest(),
            source_bytes=len(encoded_source),
            wall_time_ms=result.wall_time_ms,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO learning_records (
                    record_id, learner_id, created_at, category, title, summary,
                    error_type, error_line, ai_status, ai_explanation, suggestions_json,
                    reference_score, source_hash, source_bytes, wall_time_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    record.learner_id,
                    record.created_at,
                    record.category,
                    record.title,
                    record.summary,
                    record.error_type,
                    record.line,
                    record.ai_status,
                    record.ai_explanation,
                    json.dumps(record.suggestions, ensure_ascii=False),
                    record.reference_score,
                    record.source_hash,
                    record.source_bytes,
                    record.wall_time_ms,
                ),
            )
        return record

    def list_for(self, learner_id: str, *, limit: int = 20) -> tuple[LearningRecord, ...]:
        """Return newest records for one anonymous learner identifier."""

        safe_limit = max(1, min(limit, 50))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT record_id, learner_id, created_at, category, title, summary,
                       error_type, error_line, ai_status, ai_explanation,
                       suggestions_json, reference_score, source_hash, source_bytes,
                       wall_time_ms
                FROM learning_records
                WHERE learner_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (learner_id, safe_limit),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def update_feedback(
        self,
        record_id: str,
        learner_id: str,
        *,
        ai_status: str,
        feedback: AiFeedback | None,
    ) -> LearningRecord | None:
        """Update AI fields on an existing learner-owned record."""

        explanation = None if feedback is None else feedback.explanation
        suggestions = () if feedback is None else feedback.suggestions
        reference_score = None if feedback is None else feedback.quality.overall
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE learning_records
                SET ai_status = ?, ai_explanation = ?, suggestions_json = ?,
                    reference_score = ?
                WHERE record_id = ? AND learner_id = ?
                """,
                (
                    ai_status,
                    explanation,
                    json.dumps(suggestions, ensure_ascii=False),
                    reference_score,
                    record_id,
                    learner_id,
                ),
            )
            if cursor.rowcount != 1:
                return None
            row = connection.execute(
                """
                SELECT record_id, learner_id, created_at, category, title, summary,
                       error_type, error_line, ai_status, ai_explanation,
                       suggestions_json, reference_score, source_hash, source_bytes,
                       wall_time_ms
                FROM learning_records
                WHERE record_id = ? AND learner_id = ?
                """,
                (record_id, learner_id),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS learning_records (
                    record_id TEXT PRIMARY KEY,
                    learner_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    error_type TEXT,
                    error_line INTEGER,
                    ai_status TEXT NOT NULL,
                    ai_explanation TEXT,
                    suggestions_json TEXT NOT NULL,
                    reference_score INTEGER,
                    source_hash TEXT NOT NULL,
                    source_bytes INTEGER NOT NULL,
                    wall_time_ms INTEGER
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS learning_records_learner_created
                ON learning_records (learner_id, created_at DESC)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _from_row(row: sqlite3.Row) -> LearningRecord:
        suggestions = json.loads(row["suggestions_json"])
        return LearningRecord(
            record_id=row["record_id"],
            learner_id=row["learner_id"],
            created_at=row["created_at"],
            category=row["category"],
            title=row["title"],
            summary=row["summary"],
            error_type=row["error_type"],
            line=row["error_line"],
            ai_status=row["ai_status"],
            ai_explanation=row["ai_explanation"],
            suggestions=tuple(suggestions),
            reference_score=row["reference_score"],
            source_hash=row["source_hash"],
            source_bytes=row["source_bytes"],
            wall_time_ms=row["wall_time_ms"],
        )
