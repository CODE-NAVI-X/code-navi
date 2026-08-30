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

import ast
import base64
import copy
import hashlib
import re
import time
from uuid import uuid4

from sqlalchemy.orm import Session

from ..learning.models import NotebookItemModel
from ..learning.quiz.schemas import QuizQuestion
from .models import CodeFillAttemptModel, PracticeSetItemModel, PracticeSetModel
from .schemas import (
    CodeFillGradeRequest,
    CodeFillGradeResponse,
    CodeFillGradeResultItem,
    CodeUploadAnalysisResponse,
    CodeUploadAnalyzeRequest,
    CodeUploadSymbol,
    ExplainSymbolRequest,
    ExplainSymbolResponse,
    PracticeItem,
    PracticeSetGenerateRequest,
    PracticeSetResponse,
    StructureCatalogExercise,
    StructureCatalogResponse,
    StructureCatalogTopic,
)
from .structure_catalog import (
    EXERCISES as STRUCTURE_EXERCISES,
)
from .structure_catalog import (
    TOPICS as STRUCTURE_TOPICS,
)
from .structure_catalog import (
    StructureExercise,
    exercises_for_topic,
    topic_by_id,
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


class UploadValidationError(Exception):
    """Raised when an upload is rejected by rules (→ 4xx)."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


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

        structure_exercises = self._structure_exercises_for_topic(request)
        if request.kind == "code_practice" and structure_exercises:
            return self._generate_structure_set(
                request,
                structure_exercises,
                db,
                owner_principal_id=owner_principal_id,
            )

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
        if request.kind in ("concept_quiz", "mixed"):
            self._double_write_concept_quizzes(
                db,
                set_id=set_id,
                knowledge_point=knowledge_points[0],
                item_models=item_models,
                owner_principal_id=owner_principal_id,
            )
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

    @staticmethod
    def _double_write_concept_quizzes(
        db: Session,
        *,
        set_id: str,
        knowledge_point: str,
        item_models: list[PracticeSetItemModel],
        owner_principal_id: str | None,
    ) -> None:
        """Archive concept items into the existing quiz notebook in one transaction."""
        for item in item_models:
            if item.item_kind != "concept_quiz_question":
                continue
            secret = item.judge_secret or {}
            question = {
                **item.payload,
                "answer": secret.get("answers") or [],
                "analysis": secret.get("analysis"),
            }
            db.add(
                NotebookItemModel(
                    user_id=owner_principal_id or "poc-user",
                    owner_principal_id=owner_principal_id,
                    session_id=set_id,
                    knowledge_id=knowledge_point,
                    item_type="quiz",
                    content=knowledge_point,
                    extra_data={
                        "quiz_id": item.item_id,
                        "questions": [question],
                        "generation_mode": "mock",
                        "provider_name": "mock",
                    },
                )
            )
            item.judge_secret = {"quiz_session_ref": set_id}

    def list_structure_catalog(self) -> StructureCatalogResponse:
        """Return topic and public exercise summaries for the static catalog."""
        topics = [
            StructureCatalogTopic(
                id=topic.id,
                title=topic.title,
                description=topic.description,
                count=len(exercises_for_topic(topic.id)),
            )
            for topic in STRUCTURE_TOPICS
        ]
        exercises = [
            StructureCatalogExercise(
                id=exercise.id,
                topic_id=exercise.topic_id,
                title=exercise.title,
                kind=(
                    "structure_sequence"
                    if exercise.blanks and exercise.blanks[0].step_no <= 1
                    else "framework_fill"
                ),
                objective=exercise.objective,
                instruction=exercise.instruction,
                options=[blank.hint for blank in exercise.blanks],
                starter_code=exercise.code_masked,
                hints=[blank.hint for blank in exercise.blanks],
            )
            for exercise in STRUCTURE_EXERCISES
        ]
        return StructureCatalogResponse(
            schema_version="structure-practice.v1",
            topics=topics,
            exercises=exercises,
        )

    def analyze_code_upload(
        self,
        request: CodeUploadAnalyzeRequest,
    ) -> CodeUploadAnalysisResponse:
        """Analyze a .py/.md upload with rules only; never store original text."""
        filename = request.filename.strip().lower()
        if filename.endswith(".markdown"):
            filename = filename.removesuffix(".markdown") + ".md"
        if not (filename.endswith(".py") or filename.endswith(".md")):
            raise UploadValidationError("仅支持 .py 或 .md 文件", status_code=415)
        try:
            content = base64.b64decode(request.content_base64, validate=True).decode("utf-8")
        except Exception as exc:
            raise UploadValidationError("文件内容不是有效的 base64 文本", status_code=400) from exc
        if len(content.encode("utf-8")) > 256 * 1024:
            raise UploadValidationError("文件超过 256KB 限制", status_code=413)
        if _looks_like_dataset_content(content):
            raise UploadValidationError(
                "仅支持核心代码或文档文件，不支持数据集文件",
                status_code=400,
            )
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if filename.endswith(".py"):
            return self._analyze_python_upload(filename, content, content_hash)
        return self._analyze_markdown_upload(filename, content, content_hash)

    @staticmethod
    def _analyze_python_upload(
        filename: str,
        content: str,
        content_hash: str,
    ) -> CodeUploadAnalysisResponse:
        try:
            tree = ast.parse(content)
        except SyntaxError as exc:
            raise UploadValidationError(
                f"Python 文件解析失败：{exc.msg}",
                status_code=400,
            ) from exc
        symbols: list[CodeUploadSymbol] = []
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbols.append(
                    CodeUploadSymbol(
                        kind="class" if isinstance(node, ast.ClassDef) else "function",
                        name=node.name,
                        line=node.lineno,
                        signature=_python_signature(node),
                        docstring_summary=_docstring_summary(node),
                    )
                )
                if len(symbols) >= 50:
                    break
        framework_hints = _framework_hints(content, imports)
        metrics = {
            "lines": len(content.splitlines()),
            "functions": sum(
                symbol.kind == "function" for symbol in symbols
            ),
            "classes": sum(symbol.kind == "class" for symbol in symbols),
        }
        return CodeUploadAnalysisResponse(
            upload_id=content_hash[:32],
            filename=filename,
            content_hash=content_hash,
            kind="python",
            symbols=symbols,
            imports=_dedupe(imports)[:30],
            framework_hints=framework_hints[:8],
            metrics=metrics,
            explanation_source="rules",
        )

    @staticmethod
    def _analyze_markdown_upload(
        filename: str,
        content: str,
        content_hash: str,
    ) -> CodeUploadAnalysisResponse:
        headings = [
            line.strip()
            for line in content.splitlines()
            if line.startswith("#")
        ][:50]
        code_blocks = re.findall(r"```(?:\w+)?\n(.*?)```", content, flags=re.DOTALL)
        symbols = [
            CodeUploadSymbol(
                kind="function",
                name=f"代码块 {index}",
                line=index + 1,
                signature="",
                docstring_summary=_first_line(block),
            )
            for index, block in enumerate(code_blocks[:50], start=1)
        ]
        framework_hints = _framework_hints(content, [])
        metrics = {
            "lines": len(content.splitlines()),
            "functions": len(code_blocks),
            "classes": len(headings),
        }
        return CodeUploadAnalysisResponse(
            upload_id=content_hash[:32],
            filename=filename,
            content_hash=content_hash,
            kind="markdown",
            symbols=symbols,
            imports=[],
            framework_hints=framework_hints[:8],
            metrics=metrics,
            explanation_source="rules",
        )

    def explain_symbol(
        self,
        request: ExplainSymbolRequest,
        *,
        principal_id: str | None = None,
    ) -> ExplainSymbolResponse:
        """Return a rule-based explanation for a symbol; no model call."""
        if request.upload_id is None and not (
            request.set_id and request.item_id
        ):
            raise UploadValidationError(
                "需要 upload_id 或 set_id+item_id",
                status_code=422,
            )
        cache_key = hashlib.sha256(
            f"{request.symbol.name}:{request.symbol.code_excerpt}".encode()
        ).hexdigest()
        self._touch_explain_cache(cache_key, principal_id)
        excerpt = request.symbol.code_excerpt or request.symbol.signature
        summary = _first_line(excerpt) if excerpt else ""
        explanation = (
            f"{request.symbol.kind} `{request.symbol.name}`"
            + (f"：{summary}" if summary else "：暂无可展示的签名或摘录。")
        )
        return ExplainSymbolResponse(
            explanation=explanation[:600],
            source="rules",
            cached=False,
        )

    def _touch_explain_cache(self, cache_key: str, principal_id: str | None) -> None:
        """Keep a tiny in-process LRU and simple per-principal rate limit."""
        cache = getattr(self, "_explain_cache", {})
        rate = getattr(self, "_explain_rates", {})
        now = time.monotonic()
        principal_key = principal_id or "anonymous"
        recent = [
            timestamp
            for timestamp in rate.get(principal_key, [])
            if now - timestamp < 60
        ]
        if len(recent) >= 30:
            raise UploadValidationError("请求过于频繁", status_code=429)
        recent.append(now)
        rate[principal_key] = recent
        cache[cache_key] = now
        while len(cache) > 256:
            oldest = min(cache, key=cache.get)
            cache.pop(oldest, None)
        self._explain_cache = cache
        self._explain_rates = rate

    def grade_code_fill(
        self,
        request: CodeFillGradeRequest,
        db: Session,
        *,
        owner_principal_id: str | None = None,
        owned_ids: list[str] | None = None,
    ) -> CodeFillGradeResponse:
        """Grade one code-fill item with deterministic rules only."""
        item = (
            db.query(PracticeSetItemModel)
            .filter(
                PracticeSetItemModel.set_id == request.set_id,
                PracticeSetItemModel.item_id == request.item_id,
            )
            .first()
        )
        if item is None or item.item_kind != "code_fill":
            raise PracticeSetNotFoundError("code-fill item not found")
        if item.judge_secret is None or "blanks" not in item.judge_secret:
            return self._offline_grade_response(request, item)

        blank_map = {
            blank["blank_id"]: blank
            for blank in item.judge_secret["blanks"]
        }
        results: list[CodeFillGradeResultItem] = []
        submitted_map = {
            answer.blank_id: answer.value for answer in request.blank_answers
        }
        total_score = 0
        total_max_score = 0
        graded = True
        for blank_id, secret in blank_map.items():
            submitted = _normalize_code_fill_value(submitted_map.get(blank_id, ""))
            expected = _normalize_code_fill_value(secret.get("answer", ""))
            alternates = [
                _normalize_code_fill_value(value)
                for value in secret.get("alternate_answers", [])
            ]
            correct = submitted in {expected, *alternates} if submitted else False
            max_score = 10
            score = max_score if correct else 0
            total_score += score
            total_max_score += max_score
            results.append(
                CodeFillGradeResultItem(
                    blank_id=blank_id,
                    correct=correct,
                    score=score,
                    max_score=max_score,
                    comment="规则精确匹配。" if correct else "未命中规则答案，离线模式暂不判分。",
                    graded_by="rules" if correct else "mock",
                )
            )
            if not correct:
                graded = False

        attempt = CodeFillAttemptModel(
            attempt_id=request.attempt_id,
            item_id=request.item_id,
            set_id=request.set_id,
            blank_answers=request.model_dump(mode="json")["blank_answers"],
            score=total_score,
            max_score=total_max_score,
            graded_by="rules" if graded else "mock",
            is_mock=not graded,
            graded=graded,
            comment=None if graded else "离线模式无法静态判分，请对照参考答案自查。",
            owner_principal_id=owner_principal_id,
        )
        db.add(attempt)
        db.commit()
        return CodeFillGradeResponse(
            attempt_id=request.attempt_id,
            item_id=request.item_id,
            set_id=request.set_id,
            results=results,
            total_score=total_score,
            total_max_score=total_max_score,
            graded=graded,
            is_mock=not graded,
            provider_name="rules",
        )

    def structure_evaluation_context(
        self,
        request: CodeFillGradeRequest,
        db: Session,
        *,
        owner_principal_id: str | None = None,
        owned_ids: list[str] | None = None,
    ) -> tuple[dict, dict, list[dict]]:
        """Grade and build the public context for an AI structure review."""
        grade = self.grade_code_fill(
            request,
            db,
            owner_principal_id=owner_principal_id,
            owned_ids=owned_ids,
        )
        item = (
            db.query(PracticeSetItemModel)
            .filter(
                PracticeSetItemModel.set_id == request.set_id,
                PracticeSetItemModel.item_id == request.item_id,
            )
            .first()
        )
        if item is None or item.item_kind != "code_fill":
            raise PracticeSetNotFoundError("code-fill item not found")
        exercise = _public_payload(item.item_kind, item.payload)
        answer = {
            blank.blank_id: blank.value for blank in request.blank_answers
        }
        return exercise, answer, [result.model_dump() for result in grade.results]

    def _offline_grade_response(
        self,
        request: CodeFillGradeRequest,
        item: PracticeSetItemModel,
    ) -> CodeFillGradeResponse:
        """Return the honest offline grading fallback."""
        blank_ids = [
            answer.blank_id for answer in request.blank_answers
        ] or ["blank-1"]
        results = [
            CodeFillGradeResultItem(
                blank_id=blank_id,
                correct=False,
                score=0,
                max_score=10,
                comment="离线模式无法静态判分，请对照参考答案自查。",
                graded_by="mock",
            )
            for blank_id in blank_ids
        ]
        return CodeFillGradeResponse(
            attempt_id=request.attempt_id,
            item_id=request.item_id,
            set_id=request.set_id,
            results=results,
            total_score=0,
            total_max_score=10 * len(results),
            graded=False,
            is_mock=True,
            provider_name=None,
        )

    def _generate_structure_set(
        self,
        request: PracticeSetGenerateRequest,
        exercises: list[StructureExercise],
        db: Session,
        owner_principal_id: str | None,
    ) -> PracticeSetResponse:
        """Archive a static structure/framework code-fill set."""
        set_id = str(uuid4())
        knowledge_points = self._bound_knowledge_points(request)
        selected = exercises[: request.count]
        item_models: list[PracticeSetItemModel] = []
        for position, exercise in enumerate(selected, start=1):
            payload, judge_secret = self._structure_item_payload(exercise)
            item_models.append(
                PracticeSetItemModel(
                    set_id=set_id,
                    item_id=exercise.id,
                    position=position,
                    item_kind="code_fill",
                    payload=payload,
                    judge_secret=judge_secret,
                    owner_principal_id=owner_principal_id,
                )
            )
        set_model = PracticeSetModel(
            set_id=set_id,
            kind=request.kind,
            context_snapshot={
                "request": request.model_dump(mode="json"),
                "coverage": knowledge_points,
                "audit": None,
                "effective_context": None,
                "effective_topic": request.topic,
            },
            local_profile_id=None,
            profile_id=request.profile_id,
            generation_mode="rules_fallback",
            provider_name="rules",
            owner_principal_id=owner_principal_id,
        )
        set_model.items = item_models
        db.add(set_model)
        db.commit()
        items = [
            PracticeItem(
                item_id=item.item_id,
                position=item.position,
                item_kind="code_fill",
                knowledge_points=knowledge_points,
                judging="llm_static",
                payload=_public_payload(item.item_kind, item.payload),
                grading_hint=None,
            )
            for item in item_models
        ]
        return PracticeSetResponse(
            set_id=set_id,
            kind=request.kind,
            items=items,
            coverage=knowledge_points,
            generation_mode="rules_fallback",
            provider_name="rules",
            audit=None,
            effective_context=None,
            effective_topic=request.topic,
        )

    @staticmethod
    def _structure_item_payload(
        exercise: StructureExercise,
    ) -> tuple[dict, dict]:
        blanks = [
            {
                "blank_id": blank.blank_id,
                "answer": blank.answer,
                "alternate_answers": list(blank.alternate_answers),
                "hint": blank.hint,
                "step_no": blank.step_no,
            }
            for blank in exercise.blanks
        ]
        payload = {
            "title": exercise.title,
            "language": "python",
            "complexity": "light",
            "judge_mode": "llm_static",
            "code_masked": exercise.code_masked,
            "blanks": [
                {key: blank[key] for key in _CODE_FILL_BLANK_PUBLIC_KEYS}
                for blank in blanks
            ],
            "steps": [
                {
                    "step_no": step.step_no,
                    "title": step.title,
                    "reason": step.reason,
                    "sub_steps": list(step.sub_steps),
                }
                for step in exercise.steps
            ],
            "source": "generated",
            "reference_code_hash": hashlib.sha256(
                exercise.reference_code.encode("utf-8")
            ).hexdigest(),
        }
        return payload, {"blanks": blanks, "reference_code": exercise.reference_code}

    @staticmethod
    def _structure_exercises_for_topic(
        request: PracticeSetGenerateRequest,
    ) -> list[StructureExercise] | None:
        if not request.topic:
            return None
        topic = topic_by_id(request.topic) or topic_by_id(
            request.topic.strip().lower().replace(" ", "-")
        )
        if topic is None:
            topic = next(
                (item for item in STRUCTURE_TOPICS if item.title == request.topic),
                None,
            )
        if topic is None:
            return None
        return exercises_for_topic(topic.id)

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


def _normalize_code_fill_value(value: str) -> str:
    """Normalize a student answer for deterministic rule comparison."""
    return "".join(value.split()).casefold()


def _looks_like_dataset_content(content: str) -> bool:
    """Reject obvious dataset traces by content rules."""
    lowered = content.lower()
    if "pickle" in lowered or "parquet" in lowered:
        return True
    if any(token in lowered for token in ("\x89png", "\xff\xd8\xff", "gif89a")):
        return True
    lines = content.splitlines()
    separators = [line.strip() for line in lines if line.strip()]
    consecutive = 0
    for separator in separators:
        if set(separator) <= {",", "\t", "|", ";"} and len(separator) > 2000:
            consecutive += 1
        else:
            consecutive = 0
        if consecutive >= 3:
            return True
    return False


def _python_signature(node: ast.AST) -> str:
    if isinstance(node, ast.ClassDef):
        bases = ", ".join(ast.unparse(base) for base in node.bases)
        return f"class {node.name}({bases})" if bases else f"class {node.name}"
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        args = node.args
        parts = [arg.arg for arg in args.args]
        if args.vararg:
            parts.append(f"*{args.vararg.arg}")
        if args.kwarg:
            parts.append(f"**{args.kwarg.arg}")
        return f"def {node.name}({', '.join(parts)})"
    return ""


def _docstring_summary(node: ast.AST) -> str:
    doc = ast.get_docstring(node, clean=False)
    return _first_line(doc) if doc else ""


def _framework_hints(content: str, imports: list[str]) -> list[str]:
    lowered = content.lower()
    hints = []
    for label, needle in (
        ("FastAPI", "fastapi"),
        ("Flask", "flask"),
        ("PyTorch", "torch"),
        ("Transformers", "transformers"),
        ("sklearn", "sklearn"),
        ("Pandas", "pandas"),
        ("NumPy", "numpy"),
        ("TensorFlow", "tensorflow"),
    ):
        if needle in lowered or any(needle in item.lower() for item in imports):
            hints.append(label)
    return _dedupe(hints)


def _first_line(value: str) -> str:
    return value.strip().splitlines()[0][:300] if value.strip() else ""


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


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
