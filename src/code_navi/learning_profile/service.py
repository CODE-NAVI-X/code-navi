"""Portrait aggregation and confusion-mark toggling.

Fact boundary: every number in the portrait is computed from persisted
``quiz_attempts`` / ``confusion_marks`` rows.  Below the minimum sample size the
portrait reports 样本不足 (``mastery=None``) rather than a fabricated
percentage.  No LLM participates in these calculations.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from .models import ConfusionMarkModel, QuizAttemptModel
from .schemas import (
    MIN_MASTERY_SAMPLE,
    ConfusionItem,
    MarkRequest,
    MarkResponse,
    ProfileMastery,
    ProfileResponse,
)

#: quiz_rate above which a knowledge point counts as a strength.
_STRENGTH_THRESHOLD = 0.75
#: quiz_rate below which a knowledge point counts as a weakness.
_WEAKNESS_THRESHOLD = 0.6


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


class ProfileService:
    """Read the portrait and persist binary confusion marks."""

    def get_profile(self, profile_id: str, db: Session) -> ProfileResponse:
        """Aggregate the anonymous portrait for one ``profile_id``.

        The portrait is intentionally **not** session-scoped (CLAUDE.md rule 10
        applies to single-item detail reads).  It aggregates quiz attempts and
        confusion marks across every session that shared this ``profile_id`` —
        that is what makes it a portrait rather than a single-session snapshot.
        """
        quiz_rows = (
            db.query(QuizAttemptModel)
            .filter(
                QuizAttemptModel.profile_id == profile_id,
                QuizAttemptModel.graded.is_(True),
            )
            .all()
        )
        mark_rows = (
            db.query(ConfusionMarkModel)
            .filter(
                ConfusionMarkModel.profile_id == profile_id,
                ConfusionMarkModel.status == "confused",
            )
            .all()
        )

        by_point: dict[str, list[QuizAttemptModel]] = defaultdict(list)
        for row in quiz_rows:
            by_point[row.knowledge_point].append(row)

        mastery: list[ProfileMastery] = []
        for point, attempts in sorted(by_point.items()):
            total_score = sum(a.score for a in attempts)
            total_max = sum(a.max_score for a in attempts)
            rate = total_score / total_max if total_max > 0 else None
            sample = len(attempts)
            sufficient = sample >= MIN_MASTERY_SAMPLE
            mastery.append(
                ProfileMastery(
                    knowledge_point=point,
                    quiz_rate=rate,
                    sample_size=sample,
                    mastery=rate if sufficient else None,
                    status="sufficient" if sufficient else "insufficient",
                )
            )
        mastery.sort(key=lambda m: (m.mastery if m.mastery is not None else -1.0), reverse=True)

        strengths = [
            m.knowledge_point
            for m in mastery
            if m.mastery is not None and m.mastery >= _STRENGTH_THRESHOLD
        ]
        weaknesses = [
            m.knowledge_point
            for m in mastery
            if m.mastery is not None and m.mastery < _WEAKNESS_THRESHOLD
        ]

        by_mark_point: dict[str, list[ConfusionMarkModel]] = defaultdict(list)
        for row in mark_rows:
            by_mark_point[row.knowledge_point].append(row)
        confusion = [
            ConfusionItem(
                knowledge_point=point,
                mark_count=len(rows),
                source_types=sorted({r.source_type for r in rows}),
            )
            for point, rows in sorted(by_mark_point.items())
        ]

        return ProfileResponse(
            profile_id=profile_id,
            generated_at=_iso_now(),
            mastery=mastery,
            strengths=strengths,
            weaknesses=weaknesses,
            confusion=confusion,
        )

    def set_mark(self, request: MarkRequest, db: Session) -> MarkResponse:
        """Upsert the binary 不懂/懂了 toggle for one surface in one session.

        The unique ``(session_id, source_type, source_ref)`` pair makes the
        toggle idempotent: repeated calls converge on the same row.  ``mark``
        True → ``confused``; False → ``understood`` (removes it from the
        portrait's 待复习 list without deleting history).
        """
        existing = (
            db.query(ConfusionMarkModel)
            .filter(
                ConfusionMarkModel.session_id == request.session_id,
                ConfusionMarkModel.source_type == request.source_type,
                ConfusionMarkModel.source_ref == request.source_ref,
            )
            .first()
        )
        target = "confused" if request.mark else "understood"
        if existing is None:
            if not request.mark:
                # Nothing to clear — no mark exists for this surface yet.
                return MarkResponse(
                    session_id=request.session_id,
                    source_type=request.source_type,
                    source_ref=request.source_ref,
                    status="understood",
                )
            db.add(
                ConfusionMarkModel(
                    session_id=request.session_id,
                    profile_id=request.profile_id,
                    user_id=None,
                    knowledge_point=request.knowledge_point,
                    source_type=request.source_type,
                    source_ref=request.source_ref,
                    status=target,
                )
            )
        else:
            existing.status = target
            existing.knowledge_point = request.knowledge_point
            existing.profile_id = request.profile_id
            existing.updated_at = datetime.now(UTC)
        db.commit()
        return MarkResponse(
            session_id=request.session_id,
            source_type=request.source_type,
            source_ref=request.source_ref,
            status=target,
        )
