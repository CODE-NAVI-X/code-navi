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
    ConfusionMarkItem,
    MarkRequest,
    MarkResponse,
    ProfileMastery,
    ProfileResponse,
)

#: quiz_rate above which a knowledge point counts as a strength.
_STRENGTH_THRESHOLD = 0.75
#: quiz_rate below which a knowledge point counts as a weakness.
_WEAKNESS_THRESHOLD = 0.6

#: Fixed display order of confusion surfaces in the portrait (三栏).
_SOURCE_ORDER = ("ppt_page", "explain", "quiz_question")


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _kp_key(knowledge_point: str) -> str:
    """Normalized grouping key — ``UDP``/``udp`` collapse into one group."""
    return knowledge_point.strip().lower()


class _GroupIndex:
    """First-seen original spelling per normalized key (deterministic)."""

    def __init__(self) -> None:
        self._names: dict[str, str] = {}

    def add(self, knowledge_point: str) -> None:
        """Remember the first-seen original spelling for this point's key."""
        key = _kp_key(knowledge_point)
        if key not in self._names:
            self._names[key] = knowledge_point.strip()

    def name(self, key: str) -> str:
        """The display spelling for a normalized key (falls back to the key)."""
        return self._names.get(key, key)


def _by_latest(rows: list[ConfusionMarkModel]) -> dict[tuple[str, str], ConfusionMarkModel]:
    """Collapse marks on the same ``(source_type, source_ref)`` to the newest."""
    latest: dict[tuple[str, str], ConfusionMarkModel] = {}
    for row in rows:
        surface = (row.source_type, row.source_ref)
        prev = latest.get(surface)
        if prev is None or row.updated_at > prev.updated_at:
            latest[surface] = row
    return latest


class ProfileService:
    """Read the portrait and persist binary confusion marks."""

    def get_profile(self, profile_id: str, db: Session) -> ProfileResponse:
        """Aggregate the anonymous portrait for one ``profile_id``.

        The portrait is intentionally **not** session-scoped (CLAUDE.md rule 10
        applies to single-item detail reads).  It aggregates quiz attempts and
        confusion marks across every session that shared this ``profile_id`` —
        that is what makes it a portrait rather than a single-session snapshot.
        """
        # Both queries order by created_at so the "first-seen" spelling of a
        # normalized group is the earliest persisted row — deterministic, not
        # whatever order SQLite happened to scan.
        quiz_rows = (
            db.query(QuizAttemptModel)
            .filter(
                QuizAttemptModel.profile_id == profile_id,
                QuizAttemptModel.graded.is_(True),
            )
            .order_by(QuizAttemptModel.created_at.asc())
            .all()
        )
        mark_rows = (
            db.query(ConfusionMarkModel)
            .filter(
                ConfusionMarkModel.profile_id == profile_id,
                ConfusionMarkModel.status == "confused",
            )
            .order_by(ConfusionMarkModel.created_at.asc())
            .all()
        )

        # Mastery groups by the normalized key (UDP/udp → one row), displaying
        # the first-seen original spelling.
        attempt_index = _GroupIndex()
        by_point: dict[str, list[QuizAttemptModel]] = defaultdict(list)
        for row in quiz_rows:
            attempt_index.add(row.knowledge_point)
            by_point[_kp_key(row.knowledge_point)].append(row)

        mastery: list[ProfileMastery] = []
        for key, attempts in sorted(by_point.items()):
            total_score = sum(a.score for a in attempts)
            total_max = sum(a.max_score for a in attempts)
            rate = total_score / total_max if total_max > 0 else None
            sample = len(attempts)
            sufficient = sample >= MIN_MASTERY_SAMPLE
            mastery.append(
                ProfileMastery(
                    knowledge_point=attempt_index.name(key),
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

        # Confusion groups by the normalized key too; within a group, marks are
        # deduped per (source_type, source_ref) and grouped into the three
        # surfaces. Groups and items sort by newest mark first.
        mark_index = _GroupIndex()
        by_mark_point: dict[str, list[ConfusionMarkModel]] = defaultdict(list)
        for row in mark_rows:
            mark_index.add(row.knowledge_point)
            by_mark_point[_kp_key(row.knowledge_point)].append(row)

        confusion: list[ConfusionItem] = []
        for key, rows in by_mark_point.items():
            by_surface: dict[str, list[ConfusionMarkItem]] = {}
            for (source_type, _ref), latest in _by_latest(rows).items():
                by_surface.setdefault(source_type, []).append(
                    ConfusionMarkItem(
                        source_type=source_type,
                        source_ref=latest.source_ref,
                        label=latest.label or latest.source_ref,
                        marked_at=latest.updated_at.isoformat(),
                    )
                )
            ordered = {
                source_type: items
                for source_type in _SOURCE_ORDER
                if (items := by_surface.get(source_type))
            }
            for items in ordered.values():
                items.sort(key=lambda it: it.marked_at, reverse=True)
            confusion.append(
                ConfusionItem(
                    knowledge_point=mark_index.name(key),
                    mark_count=sum(len(items) for items in ordered.values()),
                    by_type=ordered,
                )
            )
        confusion.sort(
            key=lambda c: max(
                (it.marked_at for items in c.by_type.values() for it in items),
                default="",
            ),
            reverse=True,
        )

        return ProfileResponse(
            profile_id=profile_id,
            generated_at=_iso_now(),
            mastery=mastery,
            strengths=strengths,
            weaknesses=weaknesses,
            confusion=confusion,
        )

    def set_mark(self, request: MarkRequest, db: Session) -> MarkResponse:
        """Upsert the binary 不懂/懂了 toggle for one surface.

        Within a session the unique ``(session_id, source_type, source_ref)``
        pair keeps the toggle idempotent.  ``mark`` True → ``confused``; False
        → ``understood`` (removes it from the portrait's 待复习 list without
        deleting history).

        A "已懂" with a ``profile_id`` clears **every** confused mark on that
        ``(profile_id, source_type, source_ref)`` across sessions — the portrait
        surface is "this specific 不懂 content", and one 已懂 should dismiss it
        everywhere, not just in the current session.
        """
        target = "confused" if request.mark else "understood"
        label = request.label.strip() or request.source_ref

        if not request.mark and request.profile_id:
            rows = (
                db.query(ConfusionMarkModel)
                .filter(
                    ConfusionMarkModel.profile_id == request.profile_id,
                    ConfusionMarkModel.source_type == request.source_type,
                    ConfusionMarkModel.source_ref == request.source_ref,
                    ConfusionMarkModel.status == "confused",
                )
                .all()
            )
            for row in rows:
                row.status = "understood"
                row.knowledge_point = request.knowledge_point
                row.updated_at = datetime.now(UTC)
            if rows:
                db.commit()
            # No matching mark → harmless no-op, still reported as understood.
            return MarkResponse(
                session_id=request.session_id,
                source_type=request.source_type,
                source_ref=request.source_ref,
                status="understood",
            )

        existing = (
            db.query(ConfusionMarkModel)
            .filter(
                ConfusionMarkModel.session_id == request.session_id,
                ConfusionMarkModel.source_type == request.source_type,
                ConfusionMarkModel.source_ref == request.source_ref,
            )
            .first()
        )
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
                    label=label,
                    status=target,
                )
            )
        else:
            existing.status = target
            existing.knowledge_point = request.knowledge_point
            existing.profile_id = request.profile_id
            existing.label = label
            existing.updated_at = datetime.now(UTC)
        db.commit()
        return MarkResponse(
            session_id=request.session_id,
            source_type=request.source_type,
            source_ref=request.source_ref,
            status=target,
        )


def build_student_profile_prompt(profile: ProfileResponse) -> str | None:
    """Render a portrait as an injectable prompt segment for generative surfaces.

    Pure, deterministic, and fact-boundary-safe: only mastery values with a
    sufficient sample size are stated as facts; under-sampled points are listed
    as 样本不足 **without any invented percentage** (a portrait below the sample
    minimum must never be paraphrased as if it were a real score).  Returns
    ``None`` when the portrait has nothing to say (no graded attempts, no
    confusion marks) so callers can skip injection silently.
    """
    sections: list[str] = []
    if profile.strengths:
        sections.append("已掌握较好：" + "、".join(profile.strengths))
    if profile.weaknesses:
        sections.append("需要加强：" + "、".join(profile.weaknesses))
    undersampled = [
        m for m in profile.mastery if m.status == "insufficient"
    ]
    if undersampled:
        names = "、".join(m.knowledge_point for m in undersampled)
        sections.append(f"接触过但判分样本不足（{len(undersampled)} 个知识点）：{names}")
    if profile.confusion:
        reviewed = "、".join(
            f"{c.knowledge_point}（{c.mark_count} 处不懂标记）" for c in profile.confusion
        )
        sections.append("待复习（标记过不懂）：" + reviewed)

    if not sections:
        return None
    header = "学生真实学情画像（来自练习判分与「不懂」标记记录）："
    return header + "；".join(sections)
