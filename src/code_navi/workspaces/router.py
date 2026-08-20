"""FastAPI routes for local persistent Workspaces and Tasks."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from code_navi.db import get_db

from .schemas import (
    ActivityListResponse,
    CreateTaskRequest,
    CreateWorkspaceRequest,
    TaskListResponse,
    TaskResponse,
    WorkspaceListResponse,
    WorkspaceResponse,
)
from .service import (
    TaskNotFoundError,
    WorkspaceNotFoundError,
    WorkspaceService,
)

router = APIRouter(prefix="/api/v1", tags=["Workspace"])

_service = WorkspaceService()
_db_dependency = Depends(get_db)


def _not_found(error: LookupError) -> HTTPException:
    return HTTPException(status_code=404, detail="Workspace or Task not found.")


@router.post("/workspaces/personal", response_model=WorkspaceResponse)
def get_or_create_personal_workspace(
    local_profile_id: str = Query(..., min_length=1, max_length=64),
    db: Session = _db_dependency,
) -> WorkspaceResponse:
    """Idempotently return the current browser profile's personal Workspace."""
    try:
        workspace = _service.get_or_create_personal_workspace(local_profile_id, db)
        db.commit()
        db.refresh(workspace)
        return _service.workspace_response(workspace)
    except Exception:
        db.rollback()
        raise


@router.get("/workspaces", response_model=WorkspaceListResponse)
def list_workspaces(
    local_profile_id: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0, le=10_000),
    db: Session = _db_dependency,
) -> WorkspaceListResponse:
    return WorkspaceListResponse(
        items=_service.list_workspaces(local_profile_id, db, limit=limit, offset=offset)
    )


@router.post("/workspaces", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    request: CreateWorkspaceRequest,
    db: Session = _db_dependency,
) -> WorkspaceResponse:
    return _service.create_workspace(request, db)


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(
    workspace_id: str,
    local_profile_id: str = Query(..., min_length=1, max_length=64),
    db: Session = _db_dependency,
) -> WorkspaceResponse:
    try:
        workspace = _service.get_workspace(workspace_id, local_profile_id, db)
        return _service.workspace_response(workspace)
    except WorkspaceNotFoundError as error:
        raise _not_found(error) from error


@router.get("/workspaces/{workspace_id}/tasks", response_model=TaskListResponse)
def list_workspace_tasks(
    workspace_id: str,
    local_profile_id: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0, le=10_000),
    db: Session = _db_dependency,
) -> TaskListResponse:
    try:
        return TaskListResponse(
            items=_service.list_workspace_tasks(
                workspace_id,
                local_profile_id,
                db,
                limit=limit,
                offset=offset,
            )
        )
    except WorkspaceNotFoundError as error:
        raise _not_found(error) from error


@router.get("/workspaces/{workspace_id}/activities", response_model=ActivityListResponse)
def list_workspace_activities(
    workspace_id: str,
    local_profile_id: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0, le=10_000),
    db: Session = _db_dependency,
) -> ActivityListResponse:
    try:
        return ActivityListResponse(
            items=_service.list_workspace_activities(
                workspace_id,
                local_profile_id,
                db,
                limit=limit,
                offset=offset,
            )
        )
    except WorkspaceNotFoundError as error:
        raise _not_found(error) from error


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    request: CreateTaskRequest,
    db: Session = _db_dependency,
) -> TaskResponse:
    try:
        return _service.create_task(request, db)
    except WorkspaceNotFoundError as error:
        raise _not_found(error) from error


@router.get("/tasks/recent", response_model=TaskListResponse)
def list_recent_tasks(
    local_profile_id: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(8, ge=1, le=50),
    db: Session = _db_dependency,
) -> TaskListResponse:
    return TaskListResponse(items=_service.list_recent_tasks(local_profile_id, db, limit=limit))


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: str,
    local_profile_id: str = Query(..., min_length=1, max_length=64),
    db: Session = _db_dependency,
) -> TaskResponse:
    try:
        return _service.task_response(_service.get_task(task_id, local_profile_id, db))
    except TaskNotFoundError as error:
        raise _not_found(error) from error


@router.get("/tasks/{task_id}/activities", response_model=ActivityListResponse)
def list_task_activities(
    task_id: str,
    local_profile_id: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0, le=10_000),
    db: Session = _db_dependency,
) -> ActivityListResponse:
    try:
        return ActivityListResponse(
            items=_service.list_task_activities(
                task_id,
                local_profile_id,
                db,
                limit=limit,
                offset=offset,
            )
        )
    except TaskNotFoundError as error:
        raise _not_found(error) from error


__all__ = ["router"]
