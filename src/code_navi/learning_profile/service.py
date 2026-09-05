"""Portrait aggregation and confusion-mark toggling.

Fact boundary: every number in the portrait is computed from persisted
``quiz_attempts`` / ``confusion_marks`` rows.  Below the minimum sample size the
portrait reports 样本不足 (``mastery=None``) rather than a fabricated
percentage.  No LLM participates in these calculations.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from code_navi.online_compiler.models import PracticeLaunchModel, PracticeOutcomeModel
from code_navi.practice.models import CodeFillAttemptModel, PracticeSetModel

from .models import ConfusionMarkModel, QuizAttemptModel
from .schemas import (
    MIN_MASTERY_SAMPLE,
    ConfusionItem,
    ConfusionMarkItem,
    KnowledgeGapItem,
    KnowledgeGapResponse,
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
_MAX_GAP_LABEL = 160
_MAX_GAP_SUMMARY = 220


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _kp_key(knowledge_point: str) -> str:
    """Normalized grouping key — ``UDP``/``udp`` collapse into one group."""
    return knowledge_point.strip().lower()


def _trim(value: str | None, *, fallback: str, max_length: int) -> str:
    text = (value or "").strip() or fallback
    return text[:max_length]


def _knowledge_points_from_practice_snapshot(snapshot: dict | None) -> list[str]:
    """Derive the §1.1 envelope ``knowledge_points`` from an archived practice set.

    Mirrors the read-time rule used by the practice gateway: the request's
    ``context.knowledge_points`` names win (≤4), otherwise the free-text
    ``topic``.  Items do not store knowledge points themselves, so the set
    snapshot is the archived source of this fact.
    """
    request = (snapshot or {}).get("request") or {}
    context = request.get("context") or {}
    points = context.get("knowledge_points") or []
    names: list[str] = []
    for point in points:
        name = (point or {}).get("name", "")
        if name and name not in names:
            names.append(name)
    if names:
        return names[:4]
    topic = request.get("topic")
    return [topic] if topic else []


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


#: Human-readable Chinese labels for the gap source kinds used in merged summaries.
_GAP_SOURCE_LABELS = {
    "quiz_attempt": "理解检查",
    "confusion_mark": "不懂标记",
    "practice_outcome": "练习",
    "code_fill_attempt": "填空判题",
}


def _merge_gap_items(items: list[KnowledgeGapItem]) -> list[KnowledgeGapItem]:
    """把同一知识点的多条缺口记录合并为一条（合并同类项）。

    输入按 ``occurred_at`` 降序排列。每个知识点保留最近一条的可追溯字段
    （source_id / label / gap_kind / source），并把合计条数与来源分布写入
    ``summary``；展示名取该组最近一次出现的原始拼写。纯规则聚合，
    不调用模型、不改变 ``generated_by: rules`` 语义。
    """
    groups: dict[str, list[KnowledgeGapItem]] = {}
    display = _GroupIndex()
    for item in items:
        key = _kp_key(item.topic)
        display.add(item.topic)
        groups.setdefault(key, []).append(item)

    merged: list[KnowledgeGapItem] = []
    for key, group in groups.items():
        newest = group[0]
        if len(group) == 1:
            merged.append(newest)
            continue
        counts = Counter(item.source_type for item in group)
        distribution = "、".join(
            f"{_GAP_SOURCE_LABELS.get(source_type, source_type)}×{count}"
            for source_type, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
        )
        summary = f"共 {len(group)} 条记录（{distribution}）；最近：{newest.summary}"
        merged.append(
            newest.model_copy(
                update={
                    "topic": display.name(key),
                    "summary": summary[:_MAX_GAP_SUMMARY],
                }
            )
        )
    return merged


class ProfileService:
    """Read the portrait and persist binary confusion marks."""

    def get_profile(
        self,
        profile_id: str,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
    ) -> ProfileResponse:
        """Aggregate the portrait for one ``profile_id`` or owned principals.

        The portrait aggregates quiz attempts and confusion marks across every
        session that shared this ``profile_id`` / owned principals.
        """
        # Both queries order by created_at so the "first-seen" spelling of a
        # normalized group is the earliest persisted row — deterministic, not
        # whatever order SQLite happened to scan.
        quiz_query = db.query(QuizAttemptModel).filter(QuizAttemptModel.graded.is_(True))
        mark_query = db.query(ConfusionMarkModel).filter(ConfusionMarkModel.status == "confused")
        if owned_ids:
            quiz_query = quiz_query.filter(QuizAttemptModel.owner_principal_id.in_(owned_ids))
            mark_query = mark_query.filter(ConfusionMarkModel.owner_principal_id.in_(owned_ids))
        else:
            quiz_query = quiz_query.filter(QuizAttemptModel.profile_id == profile_id)
            mark_query = mark_query.filter(ConfusionMarkModel.profile_id == profile_id)

        quiz_rows = quiz_query.order_by(QuizAttemptModel.created_at.asc()).all()
        mark_rows = mark_query.order_by(ConfusionMarkModel.created_at.asc()).all()

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

    def get_knowledge_gaps(
        self,
        *,
        local_profile_id: str,
        profile_id: str,
        db: Session,
        owned_ids: list[str] | None = None,
        limit: int = 50,
    ) -> KnowledgeGapResponse:
        """Project traceable review items from existing facts without writing a new table."""
        quiz_items = self._quiz_gap_items(
            profile_id=profile_id, db=db, limit=limit, owned_ids=owned_ids
        )
        confusion_items = self._confusion_gap_items(
            profile_id=profile_id, db=db, limit=limit, owned_ids=owned_ids
        )
        practice_items = self._practice_gap_items(
            local_profile_id=local_profile_id,
            learner_id=profile_id,
            db=db,
            limit=limit,
            owned_ids=owned_ids,
        )
        code_fill_items = self._code_fill_gap_items(
            profile_id=profile_id, db=db, limit=limit, owned_ids=owned_ids
        )
        ordered = sorted(
            [*quiz_items, *confusion_items, *practice_items, *code_fill_items],
            key=lambda item: item.occurred_at,
            reverse=True,
        )
        items = _merge_gap_items(ordered)[:limit]
        return KnowledgeGapResponse(
            local_profile_id=local_profile_id,
            profile_id=profile_id,
            generated_at=_iso_now(),
            items=items,
        )

    def _quiz_gap_items(
        self,
        *,
        profile_id: str,
        db: Session,
        limit: int,
        owned_ids: list[str] | None = None,
    ) -> list[KnowledgeGapItem]:
        query = db.query(QuizAttemptModel).filter(
            QuizAttemptModel.graded.is_(True),
            QuizAttemptModel.score < QuizAttemptModel.max_score,
        )
        if owned_ids:
            query = query.filter(QuizAttemptModel.owner_principal_id.in_(owned_ids))
        else:
            query = query.filter(QuizAttemptModel.profile_id == profile_id)
        rows = (
            query.order_by(QuizAttemptModel.created_at.desc(), QuizAttemptModel.id.desc())
            .limit(limit)
            .all()
        )
        items: list[KnowledgeGapItem] = []
        for row in rows:
            gap_kind = "quiz_incorrect" if not row.correct else "quiz_partial_score"
            score_text = f"{row.score}/{row.max_score}"
            label = _trim(
                row.comment,
                fallback=f"Quiz {row.quiz_id} · {row.question_id}",
                max_length=_MAX_GAP_LABEL,
            )
            items.append(
                KnowledgeGapItem(
                    source_type="quiz_attempt",
                    source_id=row.id,
                    topic=_trim(row.knowledge_point, fallback="未命名知识点", max_length=512),
                    label=label,
                    gap_kind=gap_kind,
                    occurred_at=row.created_at.isoformat(),
                    summary=f"理解检查得分 {score_text}，需要回看该题对应知识点。",
                    source={
                        "attemptId": row.attempt_id,
                        "quizId": row.quiz_id,
                        "questionId": row.question_id,
                        "questionType": row.question_type,
                        "sessionId": row.session_id,
                        "score": row.score,
                        "maxScore": row.max_score,
                        "gradedBy": row.graded_by,
                    },
                )
            )
        return items

    def _confusion_gap_items(
        self,
        *,
        profile_id: str,
        db: Session,
        limit: int,
        owned_ids: list[str] | None = None,
    ) -> list[KnowledgeGapItem]:
        query = db.query(ConfusionMarkModel).filter(
            ConfusionMarkModel.status == "confused",
        )
        if owned_ids:
            query = query.filter(ConfusionMarkModel.owner_principal_id.in_(owned_ids))
        else:
            query = query.filter(ConfusionMarkModel.profile_id == profile_id)
        rows = (
            query.order_by(ConfusionMarkModel.updated_at.desc(), ConfusionMarkModel.id.desc())
            .limit(limit)
            .all()
        )
        items: list[KnowledgeGapItem] = []
        for row in rows:
            label = _trim(row.label, fallback=row.source_ref, max_length=_MAX_GAP_LABEL)
            items.append(
                KnowledgeGapItem(
                    source_type="confusion_mark",
                    source_id=row.id,
                    topic=_trim(row.knowledge_point, fallback="未命名知识点", max_length=512),
                    label=label,
                    gap_kind="self_reported_confusion",
                    occurred_at=row.updated_at.isoformat(),
                    summary=f"用户在 {row.source_type} 上标记不懂：{label}",
                    source={
                        "sessionId": row.session_id,
                        "surfaceType": row.source_type,
                        "surfaceRef": row.source_ref,
                    },
                )
            )
        return items

    def _practice_gap_items(
        self,
        *,
        local_profile_id: str,
        learner_id: str,
        db: Session,
        limit: int,
        owned_ids: list[str] | None = None,
    ) -> list[KnowledgeGapItem]:
        query = (
            db.query(PracticeOutcomeModel, PracticeLaunchModel)
            .join(PracticeLaunchModel, PracticeOutcomeModel.launch_id == PracticeLaunchModel.id)
            .filter(
                PracticeOutcomeModel.knowledge_gap_kind.isnot(None),
            )
        )
        if owned_ids:
            query = query.filter(PracticeOutcomeModel.owner_principal_id.in_(owned_ids))
        else:
            query = query.filter(
                PracticeOutcomeModel.local_profile_id == local_profile_id,
                PracticeOutcomeModel.learner_id == learner_id,
            )
        rows = (
            query.order_by(PracticeOutcomeModel.created_at.desc(), PracticeOutcomeModel.id.desc())
            .limit(limit)
            .all()
        )
        items: list[KnowledgeGapItem] = []
        for row, launch in rows:
            topic = _trim(
                launch.focus_label or row.problem_id,
                fallback=row.category or "Practice",
                max_length=512,
            )
            label = _trim(row.summary, fallback=f"Practice {row.mode}", max_length=_MAX_GAP_LABEL)
            items.append(
                KnowledgeGapItem(
                    source_type="practice_outcome",
                    source_id=row.id,
                    topic=topic,
                    label=label,
                    gap_kind=row.knowledge_gap_kind or row.category,
                    occurred_at=row.created_at.isoformat(),
                    summary=_trim(
                        row.summary,
                        fallback="Practice 结果需要复盘。",
                        max_length=_MAX_GAP_SUMMARY,
                    ),
                    source={
                        "launchId": row.launch_id,
                        "workspaceId": row.workspace_id,
                        "taskId": row.task_id,
                        "mode": row.mode,
                        "problemId": row.problem_id,
                        "problemVersion": row.problem_version,
                        "verdict": row.verdict,
                        "category": row.category,
                        "severity": row.severity,
                        "score": row.score,
                    },
                )
            )
        return items

    def _code_fill_gap_items(
        self,
        *,
        profile_id: str,
        db: Session,
        limit: int,
        owned_ids: list[str] | None = None,
    ) -> list[KnowledgeGapItem]:
        """Project graded code-fill misses (contract §4.2, additive read projection).

        Only ``graded=true`` attempts with a partial or zero score participate —
        the same gap rule as quiz attempts.  The knowledge focus comes from the
        owning practice set's archived generation snapshot (the §1.1 envelope
        ``knowledge_points``); the summary truncates the grading ``comment``.
        Attempt rows carry no profile key, so the anonymous path scopes through
        the set's archived ``profile_id``.  Answer material never leaves the
        server: the trace fields below are scores and ids only.
        """
        query = (
            db.query(CodeFillAttemptModel, PracticeSetModel)
            .join(PracticeSetModel, CodeFillAttemptModel.set_id == PracticeSetModel.set_id)
            .filter(
                CodeFillAttemptModel.graded.is_(True),
                CodeFillAttemptModel.score.isnot(None),
                CodeFillAttemptModel.max_score.isnot(None),
                CodeFillAttemptModel.score < CodeFillAttemptModel.max_score,
            )
        )
        if owned_ids:
            query = query.filter(CodeFillAttemptModel.owner_principal_id.in_(owned_ids))
        else:
            query = query.filter(PracticeSetModel.profile_id == profile_id)
        rows = (
            query.order_by(
                CodeFillAttemptModel.created_at.desc(),
                CodeFillAttemptModel.attempt_id.desc(),
                CodeFillAttemptModel.item_id.desc(),
            )
            .limit(limit)
            .all()
        )
        items: list[KnowledgeGapItem] = []
        for attempt, practice_set in rows:
            knowledge_points = _knowledge_points_from_practice_snapshot(
                practice_set.context_snapshot
            )
            gap_kind = (
                "code_fill_incorrect" if attempt.score == 0 else "code_fill_partial_score"
            )
            items.append(
                KnowledgeGapItem(
                    source_type="code_fill_attempt",
                    source_id=f"{attempt.attempt_id}:{attempt.item_id}",
                    topic=_trim(
                        knowledge_points[0] if knowledge_points else None,
                        fallback=f"CodeFill {attempt.item_id}",
                        max_length=512,
                    ),
                    label=_trim(
                        attempt.comment,
                        fallback=f"CodeFill {attempt.item_id}",
                        max_length=_MAX_GAP_LABEL,
                    ),
                    gap_kind=gap_kind,
                    occurred_at=attempt.created_at.isoformat(),
                    summary=_trim(
                        attempt.comment,
                        fallback="挖空判分未全部通过，需要回看对应知识点。",
                        max_length=_MAX_GAP_SUMMARY,
                    ),
                    source={
                        "attemptId": attempt.attempt_id,
                        "setId": attempt.set_id,
                        "itemId": attempt.item_id,
                        "score": attempt.score,
                        "maxScore": attempt.max_score,
                        "gradedBy": attempt.graded_by,
                    },
                )
            )
        return items

    def set_mark(
        self,
        request: MarkRequest,
        db: Session,
        *,
        owner_principal_id: str | None = None,
    ) -> MarkResponse:
        """Toggle a mark on one learning surface, idempotent on (session_id, type, ref)."""
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
                    user_id=owner_principal_id or "poc-user",
                    owner_principal_id=owner_principal_id,
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
            if owner_principal_id and not existing.owner_principal_id:
                existing.owner_principal_id = owner_principal_id
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
