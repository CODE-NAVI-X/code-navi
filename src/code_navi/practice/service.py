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
from collections import OrderedDict
from uuid import uuid4

from sqlalchemy.orm import Session

from ..learning.models import NotebookItemModel
from ..learning.quiz.schemas import QuizQuestion
from .models import (
    CodeFillAttemptModel,
    CodeUploadAnalysisModel,
    PracticeSetItemModel,
    PracticeSetModel,
)
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
)

_MOCK_PROVIDER_NAME = "mock"

#: Keys allowed to cross the API boundary for code-fill blanks. Everything else
#: (``answer``, ``alternate_answers``, ...) stays in ``judge_secret``.
_CODE_FILL_BLANK_PUBLIC_KEYS = ("blank_id", "hint", "step_no")

#: Keys of the concept payload that hold grading material and must be stripped.
_CONCEPT_SECRET_KEYS = ("answer", "analysis")

_CONCEPT_GRADING_HINT = "/learning/quiz/grade"

_EXPLAIN_CACHE_MAX = 256
_CODE_FILL_BLANK_MAX_SCORE = 1
_MAX_UPLOAD_BYTES = 256 * 1024


class PracticeSetNotFoundError(Exception):
    """Raised when a set does not exist or belongs to another owner."""


class MissingGenerationBasis(Exception):
    """Raised when topic/context/upload_ids are all absent (→ 422)."""


class UploadValidationError(Exception):
    """Raised when an upload is rejected by rules (→ 4xx)."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class UploadNotFoundError(Exception):
    """Raised when a referenced upload_id is absent (→ 404)."""


class ExplainOnlyJudgingError(Exception):
    """Raised when an explain-only item is sent to the grading endpoint."""


class PracticeSetService:
    """Generate (mock) and read back archived practice sets."""

    def __init__(self) -> None:
        self._explain_cache: OrderedDict[str, ExplainSymbolResponse] = OrderedDict()
        self._explain_rates: dict[str, list[float]] = {}

    # ------------------------------------------------------------------
    # Generate (mock)
    # ------------------------------------------------------------------

    def generate(
        self,
        request: PracticeSetGenerateRequest,
        db: Session,
        owner_principal_id: str | None = None,
        owned_ids: list[str] | None = None,
    ) -> PracticeSetResponse:
        self._validate_basis(request)
        self._validate_upload_ids(request, db, owned_ids=owned_ids)

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
    def _validate_upload_ids(
        request: PracticeSetGenerateRequest,
        db: Session,
        *,
        owned_ids: list[str] | None,
    ) -> None:
        """Ensure every referenced upload_id points to an archived analysis."""
        upload_ids = [upload_id for upload_id in request.upload_ids if upload_id]
        if not upload_ids:
            return
        query = db.query(CodeUploadAnalysisModel.upload_id).filter(
            CodeUploadAnalysisModel.upload_id.in_(upload_ids)
        )
        if owned_ids:
            query = query.filter(CodeUploadAnalysisModel.owner_principal_id.in_(owned_ids))
        found = {row[0] for row in query.all()}
        missing = [upload_id for upload_id in upload_ids if upload_id not in found]
        if missing:
            raise UploadNotFoundError(
                f"upload_id 不存在或不属于当前用户：{', '.join(missing)}"
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
    # P1-A contract endpoints
    # ------------------------------------------------------------------

    def analyze_code_upload(
        self,
        request: CodeUploadAnalyzeRequest,
        db: Session,
        *,
        owner_principal_id: str | None = None,
    ) -> CodeUploadAnalysisResponse:
        """Analyze a .py/.md upload and archive only the rules-derived summary."""
        filename = request.filename.strip().lower()
        if filename.endswith(".markdown"):
            filename = filename.removesuffix(".markdown") + ".md"
        if not (filename.endswith(".py") or filename.endswith(".md")):
            raise UploadValidationError("仅支持 .py 或 .md 文件", status_code=415)
        try:
            content = base64.b64decode(request.content_base64, validate=True).decode("utf-8")
        except Exception as exc:
            raise UploadValidationError("文件内容不是有效的 base64 文本", status_code=400) from exc
        if len(content.encode("utf-8")) > _MAX_UPLOAD_BYTES:
            raise UploadValidationError("文件超过 256KB 限制", status_code=413)
        if _looks_like_dataset_content(content):
            raise UploadValidationError(
                "仅支持核心代码或文档文件，不支持数据集文件",
                status_code=400,
            )

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        upload_id = str(uuid4())
        if filename.endswith(".py"):
            response = self._analyze_python_upload(filename, content, content_hash, upload_id)
        else:
            response = self._analyze_markdown_upload(filename, content, content_hash, upload_id)

        db.add(
            CodeUploadAnalysisModel(
                upload_id=response.upload_id,
                filename=response.filename,
                content_hash=response.content_hash,
                kind=response.kind,
                symbols=[symbol.model_dump(mode="json") for symbol in response.symbols],
                imports=list(response.imports),
                framework_hints=list(response.framework_hints),
                metrics=dict(response.metrics),
                owner_principal_id=owner_principal_id,
            )
        )
        db.commit()
        return response

    @staticmethod
    def _analyze_python_upload(
        filename: str,
        content: str,
        content_hash: str,
        upload_id: str,
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

        return CodeUploadAnalysisResponse(
            upload_id=upload_id,
            filename=filename,
            content_hash=content_hash,
            kind="python",
            symbols=symbols,
            imports=_dedupe(imports)[:30],
            framework_hints=_framework_hints(content, imports)[:8],
            metrics={
                "lines": len(content.splitlines()),
                "functions": sum(symbol.kind == "function" for symbol in symbols),
                "classes": sum(symbol.kind == "class" for symbol in symbols),
            },
            explanation_source="rules",
        )

    @staticmethod
    def _analyze_markdown_upload(
        filename: str,
        content: str,
        content_hash: str,
        upload_id: str,
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
        return CodeUploadAnalysisResponse(
            upload_id=upload_id,
            filename=filename,
            content_hash=content_hash,
            kind="markdown",
            symbols=symbols,
            imports=[],
            framework_hints=_framework_hints(content, [])[:8],
            metrics={
                "lines": len(content.splitlines()),
                "functions": len(code_blocks),
                "classes": len(headings),
            },
            explanation_source="rules",
        )

    def explain_symbol(
        self,
        request: ExplainSymbolRequest,
        db: Session,
        *,
        principal_id: str | None = None,
        owned_ids: list[str] | None = None,
    ) -> ExplainSymbolResponse:
        """Return a rules-based symbol explanation with an in-process LRU cache."""
        if request.upload_id is None and not (request.set_id and request.item_id):
            raise UploadValidationError(
                "需要 upload_id 或 set_id+item_id",
                status_code=422,
            )

        if request.upload_id is not None:
            upload_query = db.query(CodeUploadAnalysisModel).filter(
                CodeUploadAnalysisModel.upload_id == request.upload_id
            )
            if owned_ids:
                upload_query = upload_query.filter(
                    CodeUploadAnalysisModel.owner_principal_id.in_(owned_ids)
                )
            if upload_query.first() is None:
                raise UploadNotFoundError(f"upload_id {request.upload_id} not found")
        else:
            item_query = db.query(PracticeSetItemModel).filter(
                PracticeSetItemModel.set_id == request.set_id,
                PracticeSetItemModel.item_id == request.item_id,
            )
            if owned_ids:
                item_query = item_query.filter(
                    PracticeSetItemModel.owner_principal_id.in_(owned_ids)
                )
            if item_query.first() is None:
                raise PracticeSetNotFoundError(
                    f"Practice item {request.item_id} not found in set {request.set_id}"
                )

        cache_key = hashlib.sha256(
            f"{request.symbol.name}:{request.symbol.code_excerpt}".encode()
        ).hexdigest()
        cached = self._explain_cache.get(cache_key)
        if cached is not None:
            return cached.model_copy(update={"cached": True})

        self._enforce_explain_rate_limit(principal_id)
        excerpt = request.symbol.code_excerpt.strip()
        summary = _first_line(excerpt) if excerpt else "暂无可展示的签名或摘录。"
        explanation = f"{request.symbol.kind} `{request.symbol.name}`：{summary}"
        response = ExplainSymbolResponse(
            explanation=explanation[:600],
            source="rules",
            cached=False,
        )
        self._remember_explain_response(cache_key, response)
        return response

    def _enforce_explain_rate_limit(self, principal_id: str | None) -> None:
        principal_key = principal_id or "anonymous"
        now = time.monotonic()
        recent = [
            timestamp
            for timestamp in self._explain_rates.get(principal_key, [])
            if now - timestamp < 60
        ]
        if len(recent) >= 30:
            raise UploadValidationError("请求过于频繁", status_code=429)
        recent.append(now)
        self._explain_rates[principal_key] = recent

    def _remember_explain_response(
        self,
        cache_key: str,
        response: ExplainSymbolResponse,
    ) -> None:
        self._explain_cache[cache_key] = response
        self._explain_cache.move_to_end(cache_key)
        while len(self._explain_cache) > _EXPLAIN_CACHE_MAX:
            self._explain_cache.popitem(last=False)

    def grade_code_fill(
        self,
        request: CodeFillGradeRequest,
        db: Session,
        *,
        owner_principal_id: str | None = None,
        owned_ids: list[str] | None = None,
    ) -> CodeFillGradeResponse:
        """Grade one code-fill item deterministically and idempotently."""
        item_query = db.query(PracticeSetItemModel).filter(
            PracticeSetItemModel.set_id == request.set_id,
            PracticeSetItemModel.item_id == request.item_id,
        )
        if owned_ids:
            item_query = item_query.filter(
                PracticeSetItemModel.owner_principal_id.in_(owned_ids)
            )
        item = item_query.first()
        if item is None or item.item_kind != "code_fill":
            raise PracticeSetNotFoundError("code-fill item not found")

        judge_mode = (item.payload or {}).get("judge_mode")
        if judge_mode == "explain_only":
            raise ExplainOnlyJudgingError("该题为讲解型，不判分，请阅读讲解提示。")

        secret = item.judge_secret or {}
        blank_specs = secret.get("blanks")
        if not isinstance(blank_specs, list) or not blank_specs:
            return self._offline_grade_response(request, item)

        blank_map: dict[str, dict] = {
            str(blank["blank_id"]): blank for blank in blank_specs if isinstance(blank, dict)
        }
        submitted_map = {
            answer.blank_id: answer.value for answer in request.blank_answers
        }
        results: list[CodeFillGradeResultItem] = []
        total_score = 0
        total_max_score = 0
        for blank_id, blank in blank_map.items():
            submitted = _normalize_code_fill_value(submitted_map.get(blank_id, ""))
            expected = _normalize_code_fill_value(str(blank.get("answer", "")))
            alternates = {
                _normalize_code_fill_value(str(value))
                for value in blank.get("alternate_answers", [])
            }
            correct = bool(submitted) and submitted in {expected, *alternates}
            score = _CODE_FILL_BLANK_MAX_SCORE if correct else 0
            total_score += score
            total_max_score += _CODE_FILL_BLANK_MAX_SCORE
            results.append(
                CodeFillGradeResultItem(
                    blank_id=blank_id,
                    correct=correct,
                    score=score,
                    max_score=_CODE_FILL_BLANK_MAX_SCORE,
                    comment="规则精确匹配。" if correct else "规则判定未匹配参考答案。",
                    graded_by="rules",
                )
            )

        response = CodeFillGradeResponse(
            attempt_id=request.attempt_id,
            item_id=request.item_id,
            set_id=request.set_id,
            results=results,
            total_score=total_score,
            total_max_score=total_max_score,
            graded=True,
            is_mock=False,
            provider_name="rules",
        )
        self._upsert_code_fill_attempt(
            db,
            request=request,
            response=response,
            owner_principal_id=owner_principal_id,
            owned_ids=owned_ids,
        )
        return response

    def _upsert_code_fill_attempt(
        self,
        db: Session,
        *,
        request: CodeFillGradeRequest,
        response: CodeFillGradeResponse,
        owner_principal_id: str | None,
        owned_ids: list[str] | None,
    ) -> None:
        """Persist grading facts, updating an existing (attempt_id, item_id) row."""
        query = db.query(CodeFillAttemptModel).filter(
            CodeFillAttemptModel.attempt_id == request.attempt_id,
            CodeFillAttemptModel.item_id == request.item_id,
        )
        if owned_ids:
            query = query.filter(CodeFillAttemptModel.owner_principal_id.in_(owned_ids))
        attempt = query.first()
        blank_answers = [
            answer.model_dump(mode="json") for answer in request.blank_answers
        ]
        if attempt is None:
            attempt = CodeFillAttemptModel(
                attempt_id=request.attempt_id,
                item_id=request.item_id,
                set_id=request.set_id,
                owner_principal_id=owner_principal_id,
            )
            db.add(attempt)
        attempt.set_id = request.set_id
        attempt.blank_answers = blank_answers
        attempt.score = response.total_score
        attempt.max_score = response.total_max_score
        attempt.graded_by = "rules"
        attempt.is_mock = response.is_mock
        attempt.graded = response.graded
        attempt.comment = None
        attempt.owner_principal_id = owner_principal_id
        db.commit()

    def _offline_grade_response(
        self,
        request: CodeFillGradeRequest,
        item: PracticeSetItemModel,
    ) -> CodeFillGradeResponse:
        """Return the honest offline fallback when no judge secret is archived."""
        blank_ids = [answer.blank_id for answer in request.blank_answers] or ["blank-1"]
        results = [
            CodeFillGradeResultItem(
                blank_id=blank_id,
                correct=False,
                score=0,
                max_score=_CODE_FILL_BLANK_MAX_SCORE,
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
            total_max_score=_CODE_FILL_BLANK_MAX_SCORE * len(results),
            graded=False,
            is_mock=True,
            provider_name=None,
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
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    consecutive = 0
    for line in lines:
        if set(line) <= {",", "\t", "|", ";"} and len(line) > 2000:
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
    hints: list[str] = []
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


__all__ = [
    "CodeFillAttemptModel",
    "ExplainOnlyJudgingError",
    "MissingGenerationBasis",
    "PracticeSetNotFoundError",
    "PracticeSetService",
    "UploadNotFoundError",
    "UploadValidationError",
]
