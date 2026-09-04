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
import json
import os
import re
import time
from collections import OrderedDict
from uuid import uuid4

from sqlalchemy.orm import Session

from kernel.runtime import AgentRuntime, AgentSpec, RuntimeRequest

from ..learning.models import NotebookItemModel
from ..learning.quiz.schemas import QuizQuestion
from ..providers import ProviderSettings, create_provider
from .models import (
    CodeFillAttemptModel,
    CodeProjectModel,
    CodeUploadAnalysisModel,
    PracticeSetItemModel,
    PracticeSetModel,
)
from .prompts import (
    CODE_FILL_STATIC_GRADER_SYSTEM_PROMPT,
    CODE_FILL_SYSTEM_PROMPT,
    EXPLAIN_SYMBOL_SYSTEM_PROMPT,
    PROJECT_EXPLAIN_SYSTEM_PROMPT,
    code_fill_user_prompt,
    explain_symbol_user_prompt,
    project_explain_user_prompt,
    static_grade_user_prompt,
)
from .schemas import (
    CodeFillGradeRequest,
    CodeFillGradeResponse,
    CodeFillGradeResultItem,
    CodeProjectFile,
    CodeProjectFileResponse,
    CodeProjectResponse,
    CodeProjectUploadRequest,
    CodeUploadAnalysisResponse,
    CodeUploadAnalyzeRequest,
    CodeUploadSymbol,
    ExplainSymbolRequest,
    ExplainSymbolResponse,
    PracticeItem,
    PracticeSetGenerateRequest,
    PracticeSetResponse,
    ProjectCodeFillRequest,
    ProjectExplainRequest,
    ProjectExplainResponse,
    ProjectExplanationEntry,
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

_EXPLAIN_CACHE_MAX = 256
_CODE_FILL_BLANK_MAX_SCORE = 1
_MAX_UPLOAD_BYTES = 256 * 1024
_DEFAULT_MODEL_TIMEOUT = 60.0
_DEFAULT_MAX_TOKENS = 4096
_MAX_PROJECT_BYTES = 2 * 1024 * 1024


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
        structure_exercises = (
            self._structure_exercises_for_topic(request)
            if request.kind == "code_practice"
            else None
        )
        if structure_exercises:
            return self._generate_structure_set(
                request,
                structure_exercises,
                db,
                owner_principal_id=owner_principal_id,
            )

        knowledge_points = self._bound_knowledge_points(request)
        set_id = str(uuid4())
        code_fill_specs, code_fill_provider, code_fill_used_model = (
            self._generate_code_fill_specs(request)
            if request.kind != "concept_quiz"
            else ([], "mock", False)
        )
        code_fill_index = 0

        item_models: list[PracticeSetItemModel] = []
        for position in range(1, request.count + 1):
            item_kind = self._item_kind_for_position(request, position)
            if item_kind == "code_fill" and code_fill_index < len(code_fill_specs):
                payload, judge_secret = code_fill_specs[code_fill_index]
                code_fill_index += 1
            else:
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
            generation_mode=(
                "model"
                if code_fill_index and code_fill_used_model
                else (
                    "rules_fallback" if code_fill_index and code_fill_provider != "mock" else "mock"
                )
            ),
            provider_name=(
                _MOCK_PROVIDER_NAME
                if not code_fill_index or not code_fill_used_model
                else code_fill_provider
            ),
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
            generation_mode=(
                "model"
                if code_fill_index and code_fill_used_model
                else (
                    "rules_fallback" if code_fill_index and code_fill_provider != "mock" else "mock"
                )
            ),
            provider_name=(
                _MOCK_PROVIDER_NAME
                if not code_fill_index or not code_fill_used_model
                else code_fill_provider
            ),
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
            raise UploadNotFoundError(f"upload_id 不存在或不属于当前用户：{', '.join(missing)}")

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
        """Return topic and public exercise summaries for the static catalogue."""
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
                {key: blank[key] for key in _CODE_FILL_BLANK_PUBLIC_KEYS} for blank in blanks
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

    def _generate_code_fill_specs(
        self,
        request: PracticeSetGenerateRequest,
    ) -> tuple[list[tuple[dict, dict | None]], str, bool]:
        """Generate code-fill items from a provider, falling back to mock rules."""
        provider_name = self._provider_name()
        count = request.count
        if request.kind == "mixed":
            concept_count = (
                round(request.concept_ratio * request.count)
                if request.concept_ratio is not None
                else request.count // 2
            )
            concept_count = max(1, min(concept_count, request.count - 1))
            count = request.count - concept_count
        topic = self._bound_knowledge_points(request)[0]
        if provider_name == "mock":
            return (
                [self._mock_code_fill_dict(topic, position) for position in range(1, count + 1)],
                "mock",
                False,
            )
        try:
            result, provider_name = self._run_agent(
                agent_name="practice_code_fill_generator",
                system_prompt=CODE_FILL_SYSTEM_PROMPT,
                user_input=code_fill_user_prompt(topic, count, request.difficulty),
                session_id=f"practice-code-fill-{uuid4()}",
            )
            items = self._parse_code_fill_items(result.output_text or "", count, topic)
        except Exception:
            items = None
            provider_name = "rules"
        if items is None:
            items = [self._mock_code_fill_dict(topic, position) for position in range(1, count + 1)]
            return items, "rules", False
        return items, provider_name, True

    def _parse_code_fill_items(
        self,
        raw: str,
        count: int,
        topic: str,
    ) -> list[tuple[dict, dict | None]] | None:
        """Parse provider JSON into server-safe payload/secret tuples."""
        data = _loads_model_json(raw)
        if data is None or not isinstance(data.get("items"), list):
            return None
        parsed: list[tuple[dict, dict | None]] = []
        for raw_item in data["items"][:count]:
            if not isinstance(raw_item, dict):
                continue
            reference_code = str(raw_item.get("reference_code") or "").strip()
            if not reference_code:
                continue
            blanks: list[dict] = []
            seen_blank_ids: set[str] = set()
            for index, blank in enumerate(raw_item.get("blanks") or []):
                if not isinstance(blank, dict):
                    continue
                blank_id = str(blank.get("blank_id") or f"blank-{index + 1}")[:64]
                if blank_id in seen_blank_ids:
                    continue
                seen_blank_ids.add(blank_id)
                blanks.append(
                    {
                        "blank_id": blank_id,
                        "answer": str(blank.get("answer") or "")[:500],
                        "alternate_answers": [
                            str(value) for value in (blank.get("alternate_answers") or [])
                        ][:3],
                        "hint": str(blank.get("hint") or "")[:200],
                        "step_no": _coerce_step_no(blank.get("step_no")),
                    }
                )
            if not (2 <= len(blanks) <= 6):
                continue
            steps = [
                {
                    "step_no": _coerce_step_no(step.get("step_no")),
                    "title": str(step.get("title") or "")[:120],
                    "reason": str(step.get("reason") or "")[:400],
                    "sub_steps": [str(item) for item in (step.get("sub_steps") or [])][:4],
                }
                for step in raw_item.get("steps") or []
                if isinstance(step, dict)
            ][:5]
            if not steps:
                continue
            complexity, judge_mode = _code_fill_mode_from_reference(reference_code)
            payload = {
                "title": str(raw_item.get("title") or f"（生成）{topic}")[:200],
                "language": "python",
                "complexity": complexity,
                "judge_mode": judge_mode,
                "code_masked": str(raw_item.get("code_masked") or "")[:16000],
                "blanks": [
                    {key: blank[key] for key in _CODE_FILL_BLANK_PUBLIC_KEYS} for blank in blanks
                ],
                "steps": steps,
                "source": "generated",
                "reference_code_hash": hashlib.sha256(reference_code.encode("utf-8")).hexdigest(),
            }
            parsed.append((payload, {"blanks": blanks, "reference_code": reference_code}))
        return parsed or None

    def _mock_code_fill_dict(
        self,
        topic: str,
        position: int,
    ) -> tuple[dict, dict | None]:
        """Return one deterministic code-fill item matching the mock contract."""
        request = PracticeSetGenerateRequest(kind="code_practice", topic=topic, count=3)
        payload, secret = self._mock_item_payload(
            request=request,
            position=position,
            item_kind="code_fill",
            knowledge_points=[topic],
        )
        return payload, secret

    def _provider_settings(self) -> ProviderSettings:
        name = (os.getenv("CODE_NAVI_PRACTICE_PROVIDER") or "mock").strip().lower()
        if name == "mock":
            return ProviderSettings("mock")
        return ProviderSettings(
            name,
            os.getenv("CODE_NAVI_MODEL") or ("deepseek-chat" if name == "deepseek" else None),
            None,
            max_tokens=_DEFAULT_MAX_TOKENS,
            timeout=_DEFAULT_MODEL_TIMEOUT,
            thinking="disabled" if name == "deepseek" else None,
        )

    def _provider_name(self) -> str:
        return (os.getenv("CODE_NAVI_PRACTICE_PROVIDER") or "mock").strip().lower()

    def _run_agent(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        user_input: str,
        session_id: str,
    ):
        agent = AgentSpec(
            name=agent_name,
            description="Runs one practice P1-A generation/parsing step.",
            system_prompt=system_prompt,
            tool_names=(),
            output_format="json",
        )
        settings = self._provider_settings()
        provider = create_provider(settings)
        runtime = AgentRuntime(
            provider,
            session_dir=os.getenv("CODE_NAVI_EVENTS_DIR") or os.path.join("var", "runs"),
        )
        result = runtime.run(
            agent,
            RuntimeRequest(
                user_input,
                session_id=session_id,
                metadata={"interface": "api", "agent": agent_name},
            ),
        )
        return result, settings.name

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

    def upload_code_project(
        self,
        request: CodeProjectUploadRequest,
        db: Session,
        *,
        owner_principal_id: str | None = None,
    ) -> CodeProjectResponse:
        """Validate and archive a small project, retaining only allowed text files."""
        import posixpath

        total = 0
        files: list[dict] = []
        seen: set[str] = set()
        for item in request.files:
            path = item.path.replace("\\", "/").strip("/")
            if not path or path in seen or path.startswith("../") or "/../" in path:
                raise UploadValidationError("项目文件路径无效或重复", status_code=400)
            path = posixpath.normpath(path)
            parts = path.split("/")
            if ".." in parts or "data" in {part.lower() for part in parts}:
                raise UploadValidationError("不支持 data 目录或越界路径", status_code=400)
            lower = path.lower()
            if not (lower.endswith(".py") or lower.endswith(".md")):
                raise UploadValidationError("项目仅支持 .py 或 .md 文件", status_code=415)
            try:
                content = base64.b64decode(item.content_base64, validate=True).decode("utf-8")
            except Exception as exc:
                raise UploadValidationError(
                    "文件内容不是有效的 base64 文本", status_code=400
                ) from exc
            size = len(content.encode("utf-8"))
            total += size
            if total > _MAX_PROJECT_BYTES:
                raise UploadValidationError("项目超过 2MB 限制", status_code=413)
            if _looks_like_dataset_content(content):
                raise UploadValidationError(
                    "仅支持核心代码或文档文件，不支持数据集文件", status_code=400
                )
            if lower.endswith(".py"):
                analysis = self._analyze_python_upload(path, content, "", "tmp")
            else:
                analysis = self._analyze_markdown_upload(path, content, "", "tmp")
            files.append(
                {
                    "path": path,
                    "content": content,
                    "kind": analysis.kind,
                    "size": size,
                    "symbols": [s.model_dump(mode="json") for s in analysis.symbols],
                }
            )
            seen.add(path)
        project_id = str(uuid4())
        metrics = {
            "files": len(files),
            "bytes": total,
            "lines": sum(len(f["content"].splitlines()) for f in files),
        }
        db.add(
            CodeProjectModel(
                project_id=project_id,
                name=request.name.strip(),
                files=files,
                metrics=metrics,
                owner_principal_id=owner_principal_id,
            )
        )
        db.commit()
        return CodeProjectResponse(
            project_id=project_id,
            name=request.name.strip(),
            files=[
                CodeProjectFile(**{k: f[k] for k in ("path", "kind", "size", "symbols")})
                for f in files
            ],
            metrics=metrics,
        )

    @staticmethod
    def get_code_project(
        project_id: str, db: Session, *, owned_ids: list[str] | None = None
    ) -> CodeProjectResponse:
        query = db.query(CodeProjectModel).filter(CodeProjectModel.project_id == project_id)
        if owned_ids:
            query = query.filter(CodeProjectModel.owner_principal_id.in_(owned_ids))
        project = query.first()
        if project is None:
            raise UploadNotFoundError(f"project {project_id} not found")
        files = [
            CodeProjectFile(**{k: f[k] for k in ("path", "kind", "size", "symbols")})
            for f in (project.files or [])
        ]
        return CodeProjectResponse(
            project_id=project.project_id,
            name=project.name,
            files=files,
            metrics=project.metrics or {},
        )

    @staticmethod
    def get_code_project_file(
        project_id: str, file_path: str, db: Session, *, owned_ids: list[str] | None = None
    ) -> CodeProjectFileResponse:
        query = db.query(CodeProjectModel).filter(CodeProjectModel.project_id == project_id)
        if owned_ids:
            query = query.filter(CodeProjectModel.owner_principal_id.in_(owned_ids))
        project = query.first()
        if project is None:
            raise UploadNotFoundError(f"project {project_id} not found")
        normalized = file_path.replace("\\", "/").strip("/")
        for item in project.files or []:
            if item.get("path") == normalized:
                return CodeProjectFileResponse(
                    project_id=project_id,
                    path=normalized,
                    content=item.get("content", ""),
                    symbols=item.get("symbols", []),
                )
        raise UploadNotFoundError(f"project file {normalized} not found")

    def explain_code_project(
        self,
        project_id: str,
        request: ProjectExplainRequest,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
    ) -> ProjectExplainResponse:
        """Explain archived project structure without executing uploaded source."""
        project = self._owned_code_project(project_id, db, owned_ids=owned_ids)
        selected = self._project_files_for_scope(project, request.path)
        if request.symbol:
            selected = [
                item
                for item in selected
                if any(symbol.get("name") == request.symbol for symbol in item.get("symbols", []))
            ]
            if not selected:
                raise UploadNotFoundError(f"symbol {request.symbol} not found")

        model_response = self._project_explanation_from_model(
            project.name, selected, request.symbol
        )
        if model_response is not None:
            return ProjectExplainResponse(
                project_id=project_id, entries=model_response, source="model"
            )
        return ProjectExplainResponse(
            project_id=project_id,
            entries=self._project_rules_explanation(selected, request.symbol),
            source="rules",
        )

    def generate_project_code_fill(
        self,
        project_id: str,
        request: ProjectCodeFillRequest,
        db: Session,
        *,
        owner_principal_id: str | None = None,
        owned_ids: list[str] | None = None,
    ) -> PracticeSetResponse:
        """Archive project-derived blanks while keeping references server-side."""
        project = self._owned_code_project(project_id, db, owned_ids=owned_ids)
        files = self._project_files_for_scope(project, request.path)
        file = files[0]
        if file.get("kind") != "python":
            raise UploadValidationError("仅 Python 文件可以生成代码挖空练习", status_code=422)

        reference_code = str(file.get("content") or "")
        if request.symbol:
            reference_code = _project_symbol_excerpt(reference_code, request.symbol)
            if not reference_code:
                raise UploadNotFoundError(f"symbol {request.symbol} not found")
        payload_secret_pairs = _project_code_fill_items(
            reference_code, request.path, request.count
        )
        if not payload_secret_pairs:
            raise UploadValidationError("未找到足够的关键逻辑可供挖空", status_code=422)

        set_id = str(uuid4())
        knowledge_point = request.symbol or request.path
        items = [
            PracticeSetItemModel(
                set_id=set_id,
                item_id=f"item-{position:02d}",
                position=position,
                item_kind="code_fill",
                payload=payload,
                judge_secret=secret,
                owner_principal_id=owner_principal_id,
            )
            for position, (payload, secret) in enumerate(payload_secret_pairs, start=1)
        ]
        snapshot = {
            "request": {"topic": knowledge_point, "difficulty": request.difficulty},
            "coverage": [knowledge_point],
            "project_source": {
                "project_id": project_id,
                "path": request.path,
                "symbol": request.symbol,
            },
        }
        set_model = PracticeSetModel(
            set_id=set_id,
            kind="code_practice",
            context_snapshot=snapshot,
            generation_mode="rules_fallback",
            provider_name="rules",
            owner_principal_id=owner_principal_id,
        )
        set_model.items = items
        db.add(set_model)
        db.commit()
        return PracticeSetResponse(
            set_id=set_id,
            kind="code_practice",
            items=[
                PracticeItem(
                    item_id=item.item_id,
                    position=item.position,
                    item_kind="code_fill",
                    knowledge_points=[knowledge_point],
                    judging=_judging_channel("code_fill"),
                    payload=_public_payload("code_fill", item.payload),
                )
                for item in items
            ],
            coverage=[knowledge_point],
            generation_mode="rules_fallback",
            provider_name="rules",
            effective_topic=knowledge_point,
        )

    @staticmethod
    def _owned_code_project(
        project_id: str, db: Session, *, owned_ids: list[str] | None
    ) -> CodeProjectModel:
        query = db.query(CodeProjectModel).filter(CodeProjectModel.project_id == project_id)
        if owned_ids:
            query = query.filter(CodeProjectModel.owner_principal_id.in_(owned_ids))
        project = query.first()
        if project is None:
            raise UploadNotFoundError(f"project {project_id} not found")
        return project

    @staticmethod
    def _project_files_for_scope(project: CodeProjectModel, path: str | None) -> list[dict]:
        files = project.files or []
        if path is None:
            return files
        normalized = path.replace("\\", "/").strip("/")
        selected = [item for item in files if item.get("path") == normalized]
        if not selected:
            raise UploadNotFoundError(f"project file {normalized} not found")
        return selected

    def _project_explanation_from_model(
        self, project_name: str, files: list[dict], symbol: str | None
    ) -> list[ProjectExplanationEntry] | None:
        if self._provider_name() == "mock":
            return None
        model_files = [
            {"path": str(item.get("path")), "content": str(item.get("content") or "")[:4000]}
            for item in files[:8]
        ]
        try:
            result, _ = self._run_agent(
                agent_name="practice_project_explain",
                system_prompt=PROJECT_EXPLAIN_SYSTEM_PROMPT,
                user_input=project_explain_user_prompt(project_name, model_files),
                session_id=f"practice-project-explain-{uuid4()}",
            )
            data = _loads_model_json(result.output_text or "")
            raw_entries = data.get("entries") if data else None
            if not isinstance(raw_entries, list):
                return None
            entries = [ProjectExplanationEntry.model_validate(entry) for entry in raw_entries[:50]]
            if symbol:
                entries = [entry for entry in entries if entry.symbol == symbol]
            return entries or None
        except Exception:
            return None

    @staticmethod
    def _project_rules_explanation(
        files: list[dict], symbol: str | None
    ) -> list[ProjectExplanationEntry]:
        entries: list[ProjectExplanationEntry] = []
        for item in files:
            symbols = item.get("symbols") or []
            matching = [entry for entry in symbols if not symbol or entry.get("name") == symbol]
            if matching:
                for entry in matching:
                    name = str(entry.get("name"))
                    signature = str(entry.get("signature") or name)
                    entries.append(
                        ProjectExplanationEntry(
                            path=str(item.get("path")),
                            symbol=name,
                            fact=[
                                f"定义了 {entry.get('kind')} `{signature}`"
                                f"（第 {entry.get('line')} 行）。"
                            ],
                            inference=[f"从名称和签名看，它可能承担与 `{name}` 相关的职责。"],
                            to_verify=["确认其调用方、外部输入和实际运行结果。"],
                        )
                    )
            elif not symbol:
                entries.append(
                    ProjectExplanationEntry(
                        path=str(item.get("path")),
                        fact=[
                            f"文件类型为 {item.get('kind')}，规则解析到 {len(symbols)} 个"
                            " Python 符号。"
                        ],
                        inference=["文件在项目中的具体协作关系需要结合调用方确认。"],
                        to_verify=["确认入口文件和运行参数。"],
                    )
                )
        return entries

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

        def collect_symbols(nodes: list[ast.stmt], class_name: str | None = None) -> None:
            for node in nodes:
                if len(symbols) >= 50:
                    return
                if isinstance(node, ast.ClassDef):
                    symbols.append(
                        CodeUploadSymbol(
                            kind="class",
                            name=node.name,
                            line=node.lineno,
                            signature=_python_signature(node),
                            docstring_summary=_docstring_summary(node),
                        )
                    )
                    collect_symbols(node.body, class_name=node.name)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    is_method = class_name is not None
                    symbols.append(
                        CodeUploadSymbol(
                            kind="method" if is_method else "function",
                            name=f"{class_name}.{node.name}" if is_method else node.name,
                            line=node.lineno,
                            signature=_python_signature(node),
                            docstring_summary=_docstring_summary(node),
                        )
                    )

        collect_symbols(tree.body)

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
                "functions": sum(symbol.kind in {"function", "method"} for symbol in symbols),
                "classes": sum(symbol.kind == "class" for symbol in symbols),
                "methods": sum(symbol.kind == "method" for symbol in symbols),
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
        headings = [line.strip() for line in content.splitlines() if line.startswith("#")][:50]
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
        response = self._explain_symbol_from_model(request, excerpt)
        if response is None:
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

    def _explain_symbol_from_model(
        self,
        request: ExplainSymbolRequest,
        excerpt: str,
    ) -> ExplainSymbolResponse | None:
        """Return a model explanation when a provider is configured, else None."""
        provider_name = self._provider_name()
        if provider_name == "mock":
            return None
        try:
            result, _ = self._run_agent(
                agent_name="practice_explain_symbol",
                system_prompt=EXPLAIN_SYMBOL_SYSTEM_PROMPT,
                user_input=explain_symbol_user_prompt(
                    request.symbol.name,
                    request.symbol.kind,
                    excerpt,
                ),
                session_id=f"practice-explain-{uuid4()}",
            )
            data = _loads_model_json(result.output_text or "")
            if data is None:
                return None
            explanation = str(data.get("explanation") or "").strip()
            if not explanation:
                return None
            return ExplainSymbolResponse(
                explanation=explanation[:600],
                source="model",
                cached=False,
            )
        except Exception:
            return None

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
            item_query = item_query.filter(PracticeSetItemModel.owner_principal_id.in_(owned_ids))
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
        submitted_map = {answer.blank_id: answer.value for answer in request.blank_answers}
        results: list[CodeFillGradeResultItem] = []
        unmatched: list[tuple[str, str, dict]] = []
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
            if correct:
                total_score += _CODE_FILL_BLANK_MAX_SCORE
                total_max_score += _CODE_FILL_BLANK_MAX_SCORE
                results.append(
                    CodeFillGradeResultItem(
                        blank_id=blank_id,
                        correct=True,
                        score=_CODE_FILL_BLANK_MAX_SCORE,
                        max_score=_CODE_FILL_BLANK_MAX_SCORE,
                        comment="规则精确匹配。",
                        graded_by="rules",
                    )
                )
            else:
                unmatched.append(
                    (
                        blank_id,
                        submitted_map.get(blank_id, ""),
                        blank,
                    )
                )

        provider_name = None
        if unmatched and secret.get("reference_code"):
            model_results, provider_name = self._grade_unmatched_with_model(
                unmatched=unmatched,
                reference_code=str(secret["reference_code"]),
                request=request,
            )
            if model_results is not None:
                for result_item in model_results:
                    results.append(result_item)
                    total_score += result_item.score
                    total_max_score += result_item.max_score
            else:
                provider_name = None
        else:
            provider_name = None

        # Rules can deterministically judge an unmatched answer as incorrect;
        # only missing judge material is truly ungraded.
        for blank_id, _submitted, _blank in unmatched:
            if any(result.blank_id == blank_id for result in results):
                continue
            total_max_score += _CODE_FILL_BLANK_MAX_SCORE
            results.append(
                CodeFillGradeResultItem(
                    blank_id=blank_id,
                    correct=False,
                    score=0,
                    max_score=_CODE_FILL_BLANK_MAX_SCORE,
                    comment="规则判定未匹配参考答案。",
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
            provider_name=provider_name or "rules",
        )
        self._upsert_code_fill_attempt(
            db,
            request=request,
            response=response,
            graded_by=(
                "model" if any(result.graded_by == "model" for result in results) else "rules"
            ),
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
        graded_by: str,
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
        blank_answers = [answer.model_dump(mode="json") for answer in request.blank_answers]
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
        attempt.graded_by = graded_by
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

    def _grade_unmatched_with_model(
        self,
        *,
        unmatched: list[tuple[str, str, dict]],
        reference_code: str,
        request: CodeFillGradeRequest,
    ) -> tuple[list[CodeFillGradeResultItem] | None, str | None]:
        """Use the configured provider for static grading; fail closed to rules."""
        if self._provider_name() == "mock":
            return None, None
        try:
            result, provider_name = self._run_agent(
                agent_name="practice_code_fill_grader",
                system_prompt=CODE_FILL_STATIC_GRADER_SYSTEM_PROMPT,
                user_input=static_grade_user_prompt(
                    reference_code,
                    [
                        {
                            "blank_id": blank_id,
                            "answer": blank.get("answer"),
                            "alternate_answers": blank.get("alternate_answers"),
                        }
                        for blank_id, _, blank in unmatched
                    ],
                    [{"blank_id": blank_id, "value": value} for blank_id, value, _ in unmatched],
                ),
                session_id=f"practice-grade-{request.attempt_id}",
            )
            parsed = self._parse_model_grade_results(result.output_text or "", unmatched)
        except Exception:
            return None, None
        if parsed is None:
            return None, None
        return parsed, provider_name

    def _parse_model_grade_results(
        self,
        raw: str,
        unmatched: list[tuple[str, str, dict]],
    ) -> list[CodeFillGradeResultItem] | None:
        data = _loads_model_json(raw)
        if data is None or not isinstance(data.get("results"), list):
            return None
        known = {blank_id for blank_id, _, _ in unmatched}
        parsed: list[CodeFillGradeResultItem] = []
        for entry in data["results"]:
            if not isinstance(entry, dict):
                continue
            blank_id = str(entry.get("blank_id") or "")
            if blank_id not in known:
                continue
            try:
                score = int(entry.get("score") or 0)
            except (TypeError, ValueError):
                score = 0
            score = max(0, min(_CODE_FILL_BLANK_MAX_SCORE, score))
            parsed.append(
                CodeFillGradeResultItem(
                    blank_id=blank_id,
                    correct=score >= _CODE_FILL_BLANK_MAX_SCORE,
                    score=score,
                    max_score=_CODE_FILL_BLANK_MAX_SCORE,
                    comment=str(entry.get("comment") or "").strip()[:600] or None,
                    graded_by="model",
                )
            )
        return parsed or None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_basis(request: PracticeSetGenerateRequest) -> None:
        has_topic = bool(request.topic and request.topic.strip())
        has_context = request.context is not None
        has_uploads = bool(request.upload_ids)
        if not (has_topic or has_context or has_uploads):
            raise MissingGenerationBasis("缺少生成依据：topic、context、upload_ids 至少需要一项")
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
    def _item_kind_for_position(request: PracticeSetGenerateRequest, position: int) -> str:
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
                key: value for key, value in secret.items() if key not in _CONCEPT_SECRET_KEYS
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
                {key: blank[key] for key in _CODE_FILL_BLANK_PUBLIC_KEYS} for blank in blanks
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


def _strip_model_fence(raw: str) -> str:
    """Strip surrounding Markdown fences from a provider payload."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 3:
            cleaned = "\n".join(lines[1:-1]).strip()
    return cleaned


def _loads_model_json(raw: str) -> dict | None:
    """Parse JSON or a Python dict literal emitted by a provider."""
    cleaned = _strip_model_fence(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        try:
            data = ast.literal_eval(cleaned)
        except (SyntaxError, ValueError):
            return None
    return data if isinstance(data, dict) else None


def _coerce_step_no(value: object) -> int:
    """Return a safe 1-based step number from provider output."""
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def _code_fill_mode_from_reference(reference_code: str) -> tuple[str, str]:
    """Derive complexity/judge_mode on the server side (§1.1)."""
    lowered = reference_code.lower()
    framework_markers = (
        "fastapi",
        "flask",
        "torch",
        "transformers",
        "tensorflow",
        "sklearn",
    )
    is_heavy = (
        len(reference_code.splitlines()) > 200
        or any(marker in lowered for marker in framework_markers)
        or (reference_code.count("class ") >= 2 and reference_code.count("def ") >= 3)
    )
    return ("heavy", "explain_only") if is_heavy else ("light", "llm_static")


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


def _project_symbol_excerpt(content: str, symbol_name: str) -> str | None:
    """Return one class/function source block by its stored display name."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        name = node.name
        if name == symbol_name or symbol_name.endswith(f".{name}"):
            excerpt = ast.get_source_segment(content, node)
            if excerpt:
                return excerpt
    return None


def _project_code_fill_items(
    reference_code: str, path: str, requested_count: int
) -> list[tuple[dict, dict]]:
    """Create deterministic blanks from conditions, returns and meaningful expressions."""
    try:
        tree = ast.parse(reference_code)
    except SyntaxError:
        return []
    candidates: list[tuple[str, str, str]] = []
    for node in ast.walk(tree):
        expression: ast.AST | None = None
        hint = "补全该关键表达式。"
        if isinstance(node, ast.If):
            expression, hint = node.test, "补全决定分支走向的条件。"
        elif isinstance(node, ast.Return):
            expression, hint = node.value, "补全函数返回的核心结果。"
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            expression, hint = node.value, "补全参与主要计算或调用的表达式。"
        if expression is None or not isinstance(
            expression, (ast.Call, ast.BinOp, ast.BoolOp, ast.Compare, ast.IfExp, ast.ListComp)
        ):
            continue
        source = ast.get_source_segment(reference_code, expression)
        if source and source.strip() and source not in {item[0] for item in candidates}:
            candidates.append((source, hint, type(node).__name__))

    selected = candidates[: min(requested_count, 6)]
    if len(selected) < 2:
        return []
    code_masked = reference_code
    blanks: list[dict] = []
    for index, (answer, hint, _) in enumerate(selected, start=1):
        code_masked = code_masked.replace(answer, "______", 1)
        blanks.append(
            {
                "blank_id": f"blank-{index}",
                "answer": answer,
                "alternate_answers": [],
                "hint": hint,
                "step_no": 1,
            }
        )
    complexity, judge_mode = _code_fill_mode_from_reference(reference_code)
    payload = {
        "title": f"项目关键逻辑挖空：{path}",
        "language": "python",
        "complexity": complexity,
        "judge_mode": judge_mode,
        "code_masked": code_masked,
        "blanks": [{key: blank[key] for key in _CODE_FILL_BLANK_PUBLIC_KEYS} for blank in blanks],
        "steps": [
            {
                "step_no": 1,
                "title": "还原关键控制和计算逻辑",
                "reason": "空白来自条件、返回或关键调用，避免考查 import 和普通变量名。",
                "sub_steps": ["阅读上下文", "判断表达式作用", "填入等价逻辑"],
            }
        ],
        "source": "upload_derived",
        "reference_code_hash": hashlib.sha256(reference_code.encode("utf-8")).hexdigest(),
    }
    secret = {"blanks": blanks, "reference_code": reference_code}
    return [(payload, secret)]


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
