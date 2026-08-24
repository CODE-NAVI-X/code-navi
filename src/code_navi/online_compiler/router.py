"""FastAPI router for the online Python compiler module."""

from __future__ import annotations

from threading import Lock
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from code_navi.db import get_db
from code_navi.workspaces.service import WorkspaceConflictError, WorkspaceNotFoundError

from .application import ApiResponse, CompilerApplication
from .config import Settings
from .learning_records import LearningRecordStore
from .piston import PistonClient
from .practice_integration import (
    PracticeIntegrationService,
    PracticeLaunchNotFoundError,
    PracticeLaunchValidationError,
)
from .provider_setup import create_ai_service

router = APIRouter(prefix="/api/v1/compiler", tags=["Compiler"])

_application: CompilerApplication | None = None
_application_lock = Lock()


def create_compiler_application(settings: Settings | None = None) -> CompilerApplication:
    """Construct the compiler application from environment-backed settings."""

    resolved = settings or Settings.from_env()
    gateway = PistonClient(
        resolved.piston_base_url,
        timeout_seconds=resolved.request_timeout_seconds,
    )
    ai_service = create_ai_service(resolved)
    return CompilerApplication(
        gateway,
        resolved,
        evaluator=ai_service.evaluator,
        tutor=ai_service.tutor,
        organizer=ai_service.organizer,
        practice_set_planner=ai_service.practice_set_planner,
        ai_status=ai_service.status,
        ai_message=ai_service.message,
        record_store=LearningRecordStore(resolved.database_path),
    )


def get_compiler_application() -> CompilerApplication:
    """Return the process-wide compiler application instance."""

    global _application
    if _application is None:
        with _application_lock:
            if _application is None:
                _application = create_compiler_application()
    return _application


_compiler_dependency = Depends(get_compiler_application)
_db_dependency = Depends(get_db)
_json_body = Body(...)
_practice_integration = PracticeIntegrationService()


def _json_response(response: ApiResponse) -> JSONResponse:
    return JSONResponse(status_code=response.status_code, content=response.body)


def _launch_error(error: Exception) -> HTTPException:
    if isinstance(error, PracticeLaunchValidationError):
        return HTTPException(status_code=400, detail=str(error))
    if isinstance(error, WorkspaceConflictError):
        return HTTPException(status_code=409, detail=str(error))
    return HTTPException(status_code=404, detail="Practice launch not found.")


@router.get("/runtime", status_code=200)
def runtime_status(
    application: CompilerApplication = _compiler_dependency,
) -> JSONResponse:
    """Report the configured Piston runtime and compiler limits."""

    return _json_response(application.runtime_status())


@router.post("/execute", status_code=200)
def execute(
    payload: Any = _json_body,
    application: CompilerApplication = _compiler_dependency,
    db: Session = _db_dependency,
) -> JSONResponse:
    """Execute one Python source submission through the compiler service."""

    try:
        launch = _practice_integration.resolve_launch_for_payload(payload, action="execute", db=db)
    except (PracticeLaunchValidationError, PracticeLaunchNotFoundError) as error:
        raise _launch_error(error) from error

    response = application.execute(payload)
    if launch is not None and response.status_code == 200:
        outcome = _practice_integration.record_execute_outcome(
            launch=launch.launch,
            response_body=response.body,
            request_payload=payload,
            db=db,
        )
        if outcome is not None:
            response.body["practiceOutcome"] = _practice_integration.outcome_response(outcome)
    return _json_response(response)


@router.post("/evaluate", status_code=200)
def evaluate(
    payload: Any = _json_body,
    application: CompilerApplication = _compiler_dependency,
) -> JSONResponse:
    """Resolve a queued AI evaluation ticket."""

    return _json_response(application.evaluate(payload))


@router.post("/submit", status_code=200)
def submit(
    payload: Any = _json_body,
    application: CompilerApplication = _compiler_dependency,
    db: Session = _db_dependency,
) -> JSONResponse:
    """Judge source against server-owned public and hidden tests."""

    try:
        launch = _practice_integration.resolve_launch_for_payload(payload, action="submit", db=db)
    except (PracticeLaunchValidationError, PracticeLaunchNotFoundError) as error:
        raise _launch_error(error) from error

    response = application.submit(payload)
    if launch is not None and response.status_code == 200:
        outcome = _practice_integration.record_submit_outcome(
            launch=launch.launch,
            response_body=response.body,
            request_payload=payload,
            db=db,
        )
        if outcome is not None:
            response.body["practiceOutcome"] = _practice_integration.outcome_response(outcome)
    return _json_response(response)


@router.post("/launches", status_code=201)
def create_launch(
    payload: Any = _json_body,
    db: Session = _db_dependency,
) -> JSONResponse:
    """Issue a server-owned Practice launch for a Workspace context."""

    try:
        launch = _practice_integration.create_launch(payload, db)
    except (
        PracticeLaunchValidationError,
        WorkspaceConflictError,
        WorkspaceNotFoundError,
    ) as error:
        raise _launch_error(error) from error
    return JSONResponse(
        status_code=201,
        content=_practice_integration.launch_response(launch),
    )


@router.get("/outcomes/{outcome_id}", status_code=200)
def get_outcome(
    outcome_id: str,
    localProfileId: str,
    db: Session = _db_dependency,
) -> JSONResponse:
    """Return an owner-scoped safe PracticeOutcome summary."""

    try:
        outcome = _practice_integration.get_outcome(
            outcome_id=outcome_id,
            local_profile_id=localProfileId,
            db=db,
        )
    except (PracticeLaunchValidationError, PracticeLaunchNotFoundError) as error:
        raise _launch_error(error) from error
    return JSONResponse(
        status_code=200,
        content=_practice_integration.outcome_detail_response(outcome),
    )


@router.post("/guidance", status_code=200)
def guidance(
    payload: Any = _json_body,
    application: CompilerApplication = _compiler_dependency,
) -> JSONResponse:
    """Provide guided follow-up for a server-owned submission context."""

    return _json_response(application.guidance(payload))


@router.post("/problem-imports/analyze", status_code=200)
def analyze_problem_import(
    payload: Any = _json_body,
    application: CompilerApplication = _compiler_dependency,
) -> JSONResponse:
    """Analyze pasted exercise text into ordered practice items."""

    return _json_response(application.analyze_problem_import(payload))


@router.post("/problem-sets/generate", status_code=200)
def generate_problem_set(
    payload: Any = _json_body,
    application: CompilerApplication = _compiler_dependency,
) -> JSONResponse:
    """Generate an ordered practice set from known and session-owned problems."""

    return _json_response(application.generate_problem_set(payload))


@router.get("/records", status_code=200)
def learning_records(
    learnerId: str | None = None,
    application: CompilerApplication = _compiler_dependency,
) -> JSONResponse:
    """Return compiler learning records for one anonymous learner."""

    return _json_response(application.learning_records(learnerId))
