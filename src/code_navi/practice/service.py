"""Mock-mode service for the unified practice gateway (S1 skeleton).

S1 ships only the contract shapes and the mock closed loop (contract §1.2 mock,
§1.3): generation never calls a model or a provider — it archives a
deterministic sample set whose response matches §1.2 field by field.  Real
providers, prompts, judging and upload parsing arrive with P1-A.

Grading material never leaves the server: blank answers and concept answers are
stored in ``judge_secret`` only, and every response is rebuilt through
``_public_payload`` which drops them even if a future writer stores them inside
``payload``.
"""

from __future__ import annotations

import copy
import hashlib
from uuid import uuid4

from sqlalchemy.orm import Session

from ..learning.quiz.schemas import QuizQuestion
from .models import CodeFillAttemptModel, PracticeSetItemModel, PracticeSetModel
from .schemas import (
    PracticeItem,
    PracticeSetGenerateRequest,
    PracticeSetResponse,
)

_MOCK_PROVIDER_NAME = "mock"

#: Keys allowed to cross the API boundary for code-fill blanks. Everything else
#: (``answer``, ``alternate_answers``, ...) stays in ``judge_secret``.
_CODE_FILL_BLANK_PUBLIC_KEYS = ("blank_id", "hint", "step_no")

#: Keys of the concept payload that hold grading material and must be stripped.
_CONCEPT_SECRET_KEYS = ("answer", "analysis")

_CONCEPT_GRADING_HINT = "/learning/quiz/grade"


class PracticeSetNotFoundError(Exception):
    """Raised when a set does not exist or belongs to another owner."""


class MissingGenerationBasis(Exception):
    """Raised when topic/context/upload_ids are all absent (→ 422)."""


class PracticeSetService:
    """Generate (mock) and read back archived practice sets."""

    # ------------------------------------------------------------------
    # Generate (mock)
    # ------------------------------------------------------------------

    def generate(
        self,
        request: PracticeSetGenerateRequest,
        db: Session,
        owner_principal_id: str | None = None,
    ) -> PracticeSetResponse:
        self._validate_basis(request)

        knowledge_points = self._bound_knowledge_points(request)
        set_id = str(uuid4())

        item_models: list[PracticeSetItemModel] = []
        for position in range(1, request.count + 1):
            item_kind = self._item_kind_for_position(request, position)
            payload, judge_secret = self._mock_item_payload(
                request=request,
                position=position,
                item_kind=item_kind,
                knowledge_points=knowledge_points,
            )
            item_models.append(
                PracticeSetItemModel(
                    set_id=set_id,
                    item_id=f"item-{position:02d}",
                    position=position,
                    item_kind=item_kind,
                    payload=payload,
                    judge_secret=judge_secret,
                    owner_principal_id=owner_principal_id,
                )
            )

        effective_context = request.context
        effective_topic = None if request.context is not None else request.topic
        coverage = knowledge_points

        snapshot = {
            "request": request.model_dump(mode="json"),
            "coverage": coverage,
            "audit": None,
            "effective_context": (
                effective_context.model_dump(mode="json") if effective_context else None
            ),
            "effective_topic": effective_topic,
        }
        set_model = PracticeSetModel(
            set_id=set_id,
            kind=request.kind,
            context_snapshot=snapshot,
            local_profile_id=None,
            profile_id=request.profile_id,
            generation_mode="mock",
            provider_name=_MOCK_PROVIDER_NAME,
            owner_principal_id=owner_principal_id,
        )
        set_model.items = item_models
        db.add(set_model)
        db.commit()

        items = [
            PracticeItem(
                item_id=item.item_id,
                position=item.position,
                item_kind=item.item_kind,
                knowledge_points=knowledge_points,
                judging=_judging_channel(item.item_kind),
                payload=item.payload,
                grading_hint=(
                    _CONCEPT_GRADING_HINT if item.item_kind == "concept_quiz_question" else None
                ),
            )
            for item in item_models
        ]
        return PracticeSetResponse(
            set_id=set_id,
            kind=request.kind,
            items=items,
            coverage=coverage,
            generation_mode="mock",
            provider_name=_MOCK_PROVIDER_NAME,
            audit=None,
            effective_context=effective_context,
            effective_topic=effective_topic,
        )

    # ------------------------------------------------------------------
    # Read back (§1.3)
    # ------------------------------------------------------------------

    def get_set(
        self,
        db: Session,
        set_id: str,
        owned_ids: list[str] | None = None,
    ) -> PracticeSetResponse:
        """Return the archived §1.2 response, filtered by owner.

        Mirrors the quiz archive semantics: an authenticated caller only sees
        sets owned by their principals; an anonymous caller (no session) is not
        owner-filtered during the compat period. Missing or cross-owner → 404.
        """
        query = db.query(PracticeSetModel).filter(PracticeSetModel.set_id == set_id)
        if owned_ids:
            query = query.filter(PracticeSetModel.owner_principal_id.in_(owned_ids))
        set_model = query.first()
        if set_model is None:
            raise PracticeSetNotFoundError(f"Practice set {set_id} not found")

        snapshot = set_model.context_snapshot or {}
        items = [
            PracticeItem(
                item_id=item.item_id,
                position=item.position,
                item_kind=item.item_kind,
                knowledge_points=_knowledge_points_from_snapshot(snapshot),
                judging=_judging_channel(item.item_kind),
                payload=_public_payload(item.item_kind, item.payload),
                grading_hint=(
                    _CONCEPT_GRADING_HINT if item.item_kind == "concept_quiz_question" else None
                ),
            )
            for item in set_model.items
        ]
        return PracticeSetResponse(
            set_id=set_model.set_id,
            kind=set_model.kind,
            items=items,
            coverage=list(snapshot.get("coverage") or []),
            generation_mode=set_model.generation_mode,
            provider_name=set_model.provider_name,
            audit=None,
            effective_context=snapshot.get("effective_context"),
            effective_topic=snapshot.get("effective_topic"),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_basis(request: PracticeSetGenerateRequest) -> None:
        has_topic = bool(request.topic and request.topic.strip())
        has_context = request.context is not None
        has_uploads = bool(request.upload_ids)
        if not (has_topic or has_context or has_uploads):
            raise MissingGenerationBasis(
                "缺少生成依据：topic、context、upload_ids 至少需要一项"
            )
        if request.kind in ("concept_quiz", "mixed"):
            knowledge_point = (
                request.context.knowledge_points[0].name
                if request.context and request.context.knowledge_points
                else request.topic
            )
            if not knowledge_point:
                raise MissingGenerationBasis(
                    "缺少概念题生成依据：需要 context.knowledge_points 或 topic"
                )

    @staticmethod
    def _bound_knowledge_points(request: PracticeSetGenerateRequest) -> list[str]:
        """Knowledge-point names every item must bind to (≤4)."""
        if request.context and request.context.knowledge_points:
            names: list[str] = []
            for point in request.context.knowledge_points:
                if point.name not in names:
                    names.append(point.name)
            return names[:4]
        return [request.topic] if request.topic else ["未指定知识点"]

    @staticmethod
    def _item_kind_for_position(
        request: PracticeSetGenerateRequest, position: int
    ) -> str:
        """Deterministic item composition for the mock (contract §1.1 kinds)."""
        if request.kind == "concept_quiz":
            return "concept_quiz_question"
        if request.kind == "code_practice":
            return "code_fill" if position % 2 == 1 else "coding_problem"

        # mixed: honour concept_ratio deterministically — first N positions are
        # concept questions, the rest code-fill, with at least one of each.
        concept_count = (
            round(request.concept_ratio * request.count)
            if request.concept_ratio is not None
            else request.count // 2
        )
        concept_count = max(1, min(concept_count, request.count - 1))
        return "concept_quiz_question" if position <= concept_count else "code_fill"

    @staticmethod
    def _mock_item_payload(
        request: PracticeSetGenerateRequest,
        position: int,
        item_kind: str,
        knowledge_points: list[str],
    ) -> tuple[dict, dict | None]:
        """Build one deterministic mock item: (public payload, judge_secret).

        Grading material (concept answers/analysis, blank answers, reference
        code) goes into ``judge_secret`` only — never into ``payload``.
        """
        topic_label = knowledge_points[0] if knowledge_points else request.topic or "练习"

        if item_kind == "concept_quiz_question":
            question = QuizQuestion(
                id=f"item-{position:02d}",
                type="single",
                question=f"（Mock）关于「{topic_label}」，下列哪一项正确描述了它的核心作用？",
                options=[
                    {"label": f"{topic_label} 的定义与核心作用", "value": "A"},
                    {"label": "与该知识点无关的干扰项", "value": "B"},
                    {"label": "只与开发环境配置相关", "value": "C"},
                    {"label": "以上都不对", "value": "D"},
                ],
                answer=["A"],
                analysis=f"（Mock 解析）A 正确：「{topic_label}」的核心作用即其定义；"
                "其余选项为干扰项。",
                points=10,
            )
            secret = question.model_dump(mode="json")
            payload = {
                key: value
                for key, value in secret.items()
                if key not in _CONCEPT_SECRET_KEYS
            }
            payload.pop("comment_prompt", None)
            return payload, {
                "answers": secret.get("answer"),
                "analysis": secret.get("analysis"),
            }

        if item_kind == "coding_problem":
            return {
                "id": f"mock-problem-{position:02d}",
                "source": "generated",
                "title": f"（Mock）{topic_label}：两数之和",
                "description": "读入一行两个整数，输出它们的和。（Mock 占位题目，"
                "字段形状与 PracticeSetProblem.as_dict() 对齐）",
                "difficulty": request.difficulty,
                "tags": knowledge_points,
                "starterCode": "def solve(a: int, b: int) -> int:\n    # TODO\n",
                "inputHint": "一行两个整数，空格分隔",
                "outputHint": "一行一个整数，即两数之和",
                "sampleTests": [{"input": "1 2", "output": "3"}],
                "judgeable": True,
                "generationReason": f"Mock 占位题目，绑定知识点「{topic_label}」",
                "limitations": ["Mock 数据，仅用于前端联调，不做真实判题"],
            }, None

        # code_fill — deterministic 2-blank sample (contract bounds: 2..6 blanks).
        reference_code = (
            "def average(nums):\n"
            "    total = 0\n"
            "    for value in nums:\n"
            "        total = total + value\n"
            "    return total / len(nums)\n"
        )
        code_masked = (
            "def average(nums):\n"
            "    total = 0\n"
            "    for value in nums:\n"
            "        total = ______\n"
            "    return total / ______\n"
        )
        blanks = [
            {
                "blank_id": "blank-1",
                "answer": "total + value",
                "alternate_answers": ["value + total"],
                "hint": "循环体内把当前元素累加到 total",
                "step_no": 1,
            },
            {
                "blank_id": "blank-2",
                "answer": "len(nums)",
                "alternate_answers": [],
                "hint": "平均值需要元素个数",
                "step_no": 1,
            },
        ]
        payload = {
            "title": f"（Mock）{topic_label}：循环求平均数",
            "language": "python",
            "complexity": "light",
            "judge_mode": "llm_static",
            "code_masked": code_masked,
            "blanks": [
                {key: blank[key] for key in _CODE_FILL_BLANK_PUBLIC_KEYS}
                for blank in blanks
            ],
            "steps": [
                {
                    "step_no": 1,
                    "title": "遍历累加再求均值",
                    "reason": "先完成累加循环，再处理除法收尾，符合自顶向下的实现顺序",
                    "sub_steps": ["初始化 total", "循环累加", "计算并返回均值"],
                }
            ],
            "source": "generated",
            "reference_code_hash": hashlib.sha256(reference_code.encode("utf-8")).hexdigest(),
        }
        return payload, {
            "blanks": blanks,
            "reference_code": reference_code,
        }


def _judging_channel(item_kind: str) -> str:
    """§1.1 mapping from item kind to its judge channel."""
    if item_kind == "concept_quiz_question":
        return "rules_llm"
    if item_kind == "coding_problem":
        return "server_tests"
    return "llm_static"


def _knowledge_points_from_snapshot(snapshot: dict) -> list[str]:
    request = snapshot.get("request") or {}
    context = request.get("context")
    if context and context.get("knowledge_points"):
        names = [point.get("name", "") for point in context["knowledge_points"]]
        names = [name for name in names if name]
        if names:
            return names[:4]
    topic = request.get("topic")
    return [topic] if topic else ["未指定知识点"]


def _public_payload(item_kind: str, payload: dict) -> dict:
    """Copy an archived payload into its response-safe shape.

    This is the single stripping point on every read path: code-fill blanks keep
    only their public keys, concept payloads lose ``answer``/``analysis`` — even
    if a future writer accidentally archived them inside ``payload``.
    """
    public = copy.deepcopy(payload)
    if item_kind == "code_fill":
        public["blanks"] = [
            {key: blank[key] for key in _CODE_FILL_BLANK_PUBLIC_KEYS if key in blank}
            for blank in public.get("blanks", [])
        ]
    elif item_kind == "concept_quiz_question":
        for key in _CONCEPT_SECRET_KEYS:
            public.pop(key, None)
    return public


__all__ = [
    "CodeFillAttemptModel",
    "MissingGenerationBasis",
    "PracticeSetNotFoundError",
    "PracticeSetService",
]
