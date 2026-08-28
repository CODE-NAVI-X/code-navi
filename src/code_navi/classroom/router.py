"""FastAPI router for classroom management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..auth.dependencies import (
    CurrentPrincipal,
    require_role,
    require_user,
    verify_csrf,
)
from ..auth.service import _log_event
from ..db import get_db
from .schemas import (
    ClassroomListResponse,
    ClassroomMemberListResponse,
    ClassroomMemberOut,
    ClassroomOut,
    CreateClassroomRequest,
    JoinClassroomRequest,
    UpdateMemberNoteRequest,
)
from .service import (
    ClassroomError,
    create_classroom,
    get_classroom,
    join_classroom,
    list_classrooms,
    list_members,
    remove_member,
    update_member_note,
)

router = APIRouter(prefix="/api/v1/classes", tags=["classes"])

_db_dep = Depends(get_db)
_require_user_dep = Depends(require_user)
_require_teacher_dep = Depends(require_role("teacher"))
_require_student_dep = Depends(require_role("student"))
_verify_csrf_dep = Depends(verify_csrf)


@router.post(
    "",
    response_model=ClassroomOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new classroom",
)
def create_class_endpoint(
    body: CreateClassroomRequest,
    request: Request,
    principal: CurrentPrincipal = _require_teacher_dep,
    _csrf: None = _verify_csrf_dep,
    db: Session = _db_dep,
) -> ClassroomOut:
    """Create a new classroom (teachers only)."""
    assert principal.user_id is not None
    try:
        classroom = create_classroom(principal.user_id, body.name, db)
    except ClassroomError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    _log_event(
        db,
        event_type="class_created",
        user_id=principal.user_id,
        principal_id=principal.principal_id,
        request=request,
        metadata={"class_id": classroom.id, "class_name": classroom.name},
    )
    db.commit()

    return ClassroomOut(
        id=classroom.id,
        name=classroom.name,
        inviteCode=classroom.invite_code,
        roleInClass="teacher",
        isOwner=True,
        memberCount=1,
        createdAt=classroom.created_at,
    )


@router.get(
    "",
    response_model=ClassroomListResponse,
    summary="List current user's classrooms",
)
def list_classes_endpoint(
    principal: CurrentPrincipal = _require_user_dep,
    db: Session = _db_dep,
) -> ClassroomListResponse:
    """Return all classrooms owned by or joined by the current user."""
    assert principal.user_id is not None
    items = list_classrooms(principal.user_id, db)
    return ClassroomListResponse(items=items)


@router.get(
    "/{class_id}",
    response_model=ClassroomOut,
    summary="Get single classroom details",
)
def get_class_endpoint(
    class_id: str,
    principal: CurrentPrincipal = _require_user_dep,
    db: Session = _db_dep,
) -> ClassroomOut:
    """Get classroom details. Non-members receive 404 to avoid probing."""
    assert principal.user_id is not None
    try:
        return get_classroom(class_id, principal.user_id, db)
    except ClassroomError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@router.post(
    "/join",
    response_model=ClassroomOut,
    status_code=status.HTTP_200_OK,
    summary="Join a classroom using an invite code",
)
def join_class_endpoint(
    body: JoinClassroomRequest,
    request: Request,
    principal: CurrentPrincipal = _require_student_dep,
    _csrf: None = _verify_csrf_dep,
    db: Session = _db_dep,
) -> ClassroomOut:
    """Join a classroom via invite code (students only)."""
    assert principal.user_id is not None
    try:
        classroom_out = join_classroom(principal.user_id, body.inviteCode, db)
    except ClassroomError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    _log_event(
        db,
        event_type="class_joined",
        user_id=principal.user_id,
        principal_id=principal.principal_id,
        request=request,
        metadata={"class_id": classroom_out.id, "class_name": classroom_out.name},
    )
    db.commit()

    return classroom_out


@router.get(
    "/{class_id}/members",
    response_model=ClassroomMemberListResponse,
    summary="List members of a classroom",
)
def list_members_endpoint(
    class_id: str,
    principal: CurrentPrincipal = _require_user_dep,
    db: Session = _db_dep,
) -> ClassroomMemberListResponse:
    """Return all members in the classroom. Non-members receive 404."""
    assert principal.user_id is not None
    try:
        items = list_members(class_id, principal.user_id, db)
        return ClassroomMemberListResponse(items=items)
    except ClassroomError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@router.delete(
    "/{class_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a student member from classroom (owner only)",
)
def delete_member_endpoint(
    class_id: str,
    user_id: str,
    request: Request,
    principal: CurrentPrincipal = _require_user_dep,
    _csrf: None = _verify_csrf_dep,
    db: Session = _db_dep,
) -> None:
    """Remove a student member from a classroom. Owner only."""
    assert principal.user_id is not None
    try:
        remove_member(class_id, user_id, principal.user_id, db)
    except ClassroomError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    _log_event(
        db,
        event_type="class_member_removed",
        user_id=principal.user_id,
        principal_id=principal.principal_id,
        request=request,
        metadata={"class_id": class_id, "removed_user_id": user_id},
    )
    db.commit()


@router.patch(
    "/{class_id}/members/{user_id}",
    response_model=ClassroomMemberOut,
    status_code=status.HTTP_200_OK,
    summary="Update private note on a student member (owner only)",
)
def update_member_note_endpoint(
    class_id: str,
    user_id: str,
    body: UpdateMemberNoteRequest,
    request: Request,
    principal: CurrentPrincipal = _require_user_dep,
    _csrf: None = _verify_csrf_dep,
    db: Session = _db_dep,
) -> ClassroomMemberOut:
    """Update private note on a student member. Owner only."""
    assert principal.user_id is not None
    try:
        member_out = update_member_note(class_id, user_id, body.note, principal.user_id, db)
    except ClassroomError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    _log_event(
        db,
        event_type="class_member_noted",
        user_id=principal.user_id,
        principal_id=principal.principal_id,
        request=request,
        metadata={"class_id": class_id, "noted_user_id": user_id},
    )
    db.commit()

    return member_out
