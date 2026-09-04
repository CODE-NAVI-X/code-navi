"""API router for the unified practice gateway (contract §1).

Prefix ``/api/v1/practice``, tags ``["Practice"]``.  During the compat period
both endpoints use ``get_optional_principal`` (the same pattern as
``POST /learning/quiz/generate``): ``owner_principal_id`` stays nullable and
authenticated reads are owner-filtered — see the §0.1 ruling in the contract.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.dependencies import (
    CurrentPrincipal,
    get_optional_principal,
    get_owned_principal_ids,
)
from ..db import get_db
from ..online_compiler.ai_evaluation import AiEvaluationError
from ..online_compiler.config import Settings
from ..online_compiler.provider_setup import create_ai_service
from .schemas import (
    CodeFillGradeRequest,
    CodeFillGradeResponse,
    CodeProjectFileResponse,
    CodeProjectResponse,
    CodeProjectUploadRequest,
    CodeUploadAnalysisResponse,
    CodeUploadAnalyzeRequest,
    ExplainSymbolRequest,
    ExplainSymbolResponse,
    PracticeSetGenerateRequest,
    PracticeSetResponse,
    StructureCatalogResponse,
)
from .service import (
    ExplainOnlyJudgingError,
    MissingGenerationBasis,
    PracticeSetNotFoundError,
    PracticeSetService,
    UploadNotFoundError,
    UploadValidationError,
)
from .structure_practice import (
    StructureExerciseNotFoundError,
    StructureExerciseValidationError,
    StructurePracticeService,
)

router = APIRouter(prefix="/api/v1/practice", tags=["Practice"])

_practice_service = PracticeSetService()
_structure_practice = StructurePracticeService()
_db_dependency = Depends(get_db)
_opt_principal_dep = Depends(get_optional_principal)


@router.post("/sets/generate", response_model=PracticeSetResponse, status_code=200)
async def generate_practice_set(
    request: PracticeSetGenerateRequest,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> PracticeSetResponse:
    """Generate one practice set (S1: mock mode only, no provider call)."""
    principal_id = principal.principal_id if principal else None
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _practice_service.generate(
            request,
            db,
            owner_principal_id=principal_id,
            owned_ids=owned_ids,
        )
    except MissingGenerationBasis as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UploadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/sets/{set_id}", response_model=PracticeSetResponse, status_code=200)
async def get_practice_set(
    set_id: str,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> PracticeSetResponse:
    """Restore an archived set (answers stripped); 404 when missing/cross-owner."""
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _practice_service.get_set(db, set_id, owned_ids=owned_ids)
    except PracticeSetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/structure-exercises", status_code=200)
async def list_structure_exercises() -> dict:
    """Return the frontend-compatible structure exercise catalogue."""
    return _structure_practice.list_exercises()


@router.post("/structure-exercises/{exercise_id}/submit", status_code=200)
async def submit_structure_exercise(exercise_id: str, payload: dict) -> dict:
    """Grade a structure exercise using deterministic rules."""
    if "answer" not in payload:
        raise HTTPException(status_code=400, detail="answer is required")
    level = payload.get("level")
    if level is not None and not isinstance(level, int):
        raise HTTPException(status_code=400, detail="level must be an integer")
    try:
        return _structure_practice.submit(exercise_id, payload["answer"], level=level)
    except StructureExerciseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StructureExerciseValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/structure-exercises/{exercise_id}/evaluate", status_code=200)
async def evaluate_structure_exercise(exercise_id: str, payload: dict) -> dict:
    """Return AI feedback for a legacy structure exercise."""
    if "answer" not in payload:
        raise HTTPException(status_code=400, detail="answer is required")
    level = payload.get("level")
    if level is not None and not isinstance(level, int):
        raise HTTPException(status_code=400, detail="level must be an integer")
    try:
        context = _structure_practice.exercise_public_context(exercise_id)
        rule_result = _structure_practice.submit(exercise_id, payload["answer"], level=level)
    except StructureExerciseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StructureExerciseValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    ai_service = create_ai_service(Settings.from_env())
    evaluator = ai_service.evaluator
    if evaluator is None:
        return {"ai": {"status": "disabled", "message": ai_service.message}}
    try:
        feedback = evaluator.evaluate_structure_answer(
            context,
            payload["answer"],
            _legacy_rule_results(rule_result["feedback"]),
            None,
        )
    except AiEvaluationError:
        return {
            "ai": {
                "status": "unavailable",
                "message": "AI 反馈暂时不可用；规则结论不受影响。",
            }
        }
    return {"ai": feedback.as_dict()}


@router.post("/structure-exercises/{exercise_id}/chat", status_code=200)
async def chat_structure_exercise(exercise_id: str, payload: dict) -> dict:
    """Answer one follow-up question for a legacy structure exercise."""
    question = payload.get("question")
    history = payload.get("history") or []
    if not isinstance(question, str) or not question.strip():
        raise HTTPException(status_code=400, detail="question is required")
    if not isinstance(history, list):
        raise HTTPException(status_code=400, detail="history must be a list")
    try:
        context = _structure_practice.exercise_public_context(exercise_id)
    except StructureExerciseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    ai_service = create_ai_service(Settings.from_env())
    tutor = ai_service.tutor
    if tutor is None:
        return {
            "ai": {
                "reply": ai_service.message,
                "strategy": "explanation",
                "blocked": False,
            }
        }
    try:
        reply = tutor.chat(question, context, history, None)
    except AiEvaluationError:
        return {
            "ai": {
                "reply": "AI 引导暂时不可用。",
                "strategy": "explanation",
                "blocked": False,
            }
        }
    return {"ai": reply}


@router.get(
    "/structure-catalog",
    response_model=StructureCatalogResponse,
    status_code=200,
)
async def list_structure_catalog() -> StructureCatalogResponse:
    """Return read-only topics and public exercise summaries for static practice."""
    return _practice_service.list_structure_catalog()


@router.post(
    "/code-fill/grade",
    response_model=CodeFillGradeResponse,
    status_code=200,
)
async def grade_code_fill(
    request: CodeFillGradeRequest,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> CodeFillGradeResponse:
    """Grade one code-fill item with deterministic rules; no code execution."""
    principal_id = principal.principal_id if principal else None
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _practice_service.grade_code_fill(
            request,
            db,
            owner_principal_id=principal_id,
            owned_ids=owned_ids,
        )
    except PracticeSetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExplainOnlyJudgingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/code-uploads/analyze",
    response_model=CodeUploadAnalysisResponse,
    status_code=200,
)
async def analyze_code_upload(
    request: CodeUploadAnalyzeRequest,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> CodeUploadAnalysisResponse:
    """Analyze a .py/.md upload with rules only; original text is never stored."""
    principal_id = principal.principal_id if principal else None
    try:
        return _practice_service.analyze_code_upload(
            request,
            db,
            owner_principal_id=principal_id,
        )
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/projects", response_model=CodeProjectResponse, status_code=200)
async def upload_code_project(
    request: CodeProjectUploadRequest,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> CodeProjectResponse:
    """Upload a bounded .py/.md project and return its navigation tree."""
    try:
        return _practice_service.upload_code_project(
            request, db, owner_principal_id=principal.principal_id if principal else None
        )
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/projects/{project_id}", response_model=CodeProjectResponse, status_code=200)
async def get_code_project(
    project_id: str,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> CodeProjectResponse:
    try:
        return _practice_service.get_code_project(
            project_id, db, owned_ids=get_owned_principal_ids(principal, db) if principal else None
        )
    except UploadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/files/{file_path:path}", response_model=CodeProjectFileResponse)
async def get_code_project_file(
    project_id: str,
    file_path: str,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> CodeProjectFileResponse:
    try:
        return _practice_service.get_code_project_file(
            project_id, file_path, db,
            owned_ids=get_owned_principal_ids(principal, db) if principal else None,
        )
    except UploadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/code-fill/explain-symbol",
    response_model=ExplainSymbolResponse,
    status_code=200,
)
async def explain_symbol(
    request: ExplainSymbolRequest,
    principal: CurrentPrincipal | None = _opt_principal_dep,
    db: Session = _db_dependency,
) -> ExplainSymbolResponse:
    """Return a cached, rules-based symbol explanation."""
    principal_id = principal.principal_id if principal else None
    owned_ids = get_owned_principal_ids(principal, db) if principal else None
    try:
        return _practice_service.explain_symbol(
            request,
            db,
            principal_id=principal_id,
            owned_ids=owned_ids,
        )
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except UploadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PracticeSetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _legacy_rule_results(feedback: list[dict]) -> list[dict]:
    """Convert the legacy structure feedback shape to AI rule results."""
    results = []
    for index, item in enumerate(feedback):
        passed = item.get("status") == "passed"
        results.append(
            {
                "blank_id": item.get("token") or f"step-{index + 1}",
                "correct": passed,
                "score": 10 if passed else 0,
                "max_score": 10,
                "graded_by": "rules",
            }
        )
    return results
