"""Business logic for classroom management."""

from __future__ import annotations

import secrets
from uuid import uuid4

from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth.models import User
from .models import Classroom, ClassroomMember
from .schemas import ClassroomMemberOut, ClassroomOut

INVITE_CODE_CHARACTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class ClassroomError(Exception):
    """Domain error for classroom operations."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def generate_invite_code() -> str:
    """Generate an unambiguous 8-character uppercase alphanumeric code."""
    return "".join(secrets.choice(INVITE_CODE_CHARACTERS) for _ in range(8))


def create_classroom(user_id: str, name: str, db: Session) -> Classroom:
    """Create a classroom with owner as teacher and retry on invite code collision."""
    trimmed_name = name.strip()
    if not trimmed_name:
        raise ClassroomError("class.validation_failed", "班级名称不能为空", 422)

    for attempt in range(5):
        code = generate_invite_code()
        classroom = Classroom(
            id=str(uuid4()),
            name=trimmed_name,
            invite_code=code,
            owner_user_id=user_id,
        )
        member = ClassroomMember(
            id=str(uuid4()),
            class_id=classroom.id,
            user_id=user_id,
            role_in_class="teacher",
        )
        db.add(classroom)
        db.add(member)
        try:
            db.flush()
            db.commit()
            db.refresh(classroom)
            return classroom
        except IntegrityError as exc:
            db.rollback()
            if attempt == 4:
                raise ClassroomError("class.server_error", "生成邀请码失败，请重试", 500) from exc

    raise ClassroomError("class.server_error", "生成邀请码失败，请重试", 500)


def list_classrooms(user_id: str, db: Session) -> list[ClassroomOut]:
    """Return all classrooms where the user is an owner or member."""
    memberships = (
        db.query(ClassroomMember)
        .filter(ClassroomMember.user_id == user_id)
        .all()
    )
    member_roles = {m.class_id: m.role_in_class for m in memberships}

    owned_classes = (
        db.query(Classroom)
        .filter(Classroom.owner_user_id == user_id)
        .all()
    )
    owned_ids = {c.id for c in owned_classes}

    all_class_ids = list(set(member_roles.keys()) | owned_ids)
    if not all_class_ids:
        return []

    classes = (
        db.query(Classroom)
        .filter(Classroom.id.in_(all_class_ids))
        .order_by(Classroom.created_at.desc())
        .all()
    )

    count_rows = (
        db.query(ClassroomMember.class_id, func.count(ClassroomMember.id))
        .filter(ClassroomMember.class_id.in_(all_class_ids))
        .group_by(ClassroomMember.class_id)
        .all()
    )
    count_map = {row[0]: row[1] for row in count_rows}

    items: list[ClassroomOut] = []
    for c in classes:
        is_owner = (c.owner_user_id == user_id)
        role_in_class = "teacher" if is_owner else member_roles.get(c.id, "student")
        items.append(
            ClassroomOut(
                id=c.id,
                name=c.name,
                inviteCode=c.invite_code if is_owner else None,
                roleInClass=role_in_class,
                isOwner=is_owner,
                memberCount=count_map.get(c.id, 0),
                createdAt=c.created_at,
            )
        )
    return items


def get_classroom(classroom_id: str, requester_user_id: str, db: Session) -> ClassroomOut:
    """Return a single classroom if requester is owner or member, else 404."""
    classroom = db.query(Classroom).filter(Classroom.id == classroom_id).first()
    if not classroom:
        raise ClassroomError("class.not_found", "班级不存在", 404)

    is_owner = (classroom.owner_user_id == requester_user_id)
    membership = (
        db.query(ClassroomMember)
        .filter(
            ClassroomMember.class_id == classroom_id,
            ClassroomMember.user_id == requester_user_id,
        )
        .first()
    )

    if not is_owner and not membership:
        # Anti-probing: unauthorized returns 404
        raise ClassroomError("class.not_found", "班级不存在", 404)

    if is_owner:
        role_in_class = "teacher"
    else:
        role_in_class = membership.role_in_class if membership else "student"
    member_count = (
        db.query(func.count(ClassroomMember.id))
        .filter(ClassroomMember.class_id == classroom_id)
        .scalar()
        or 0
    )

    return ClassroomOut(
        id=classroom.id,
        name=classroom.name,
        inviteCode=classroom.invite_code if is_owner else None,
        roleInClass=role_in_class,
        isOwner=is_owner,
        memberCount=member_count,
        createdAt=classroom.created_at,
    )


def join_classroom(user_id: str, invite_code: str, db: Session) -> ClassroomOut:
    """Join a classroom by invite code."""
    clean_code = invite_code.strip().upper()
    classroom = db.query(Classroom).filter(Classroom.invite_code == clean_code).first()
    if not classroom:
        raise ClassroomError("class.invalid_invite_code", "班级不存在或邀请码无效", 404)

    existing = (
        db.query(ClassroomMember)
        .filter(
            ClassroomMember.class_id == classroom.id,
            ClassroomMember.user_id == user_id,
        )
        .first()
    )
    if existing:
        raise ClassroomError("class.already_member", "您已是该班级成员", 409)

    member = ClassroomMember(
        id=str(uuid4()),
        class_id=classroom.id,
        user_id=user_id,
        role_in_class="student",
    )
    db.add(member)
    db.commit()

    member_count = (
        db.query(func.count(ClassroomMember.id))
        .filter(ClassroomMember.class_id == classroom.id)
        .scalar()
        or 0
    )
    is_owner = (classroom.owner_user_id == user_id)

    return ClassroomOut(
        id=classroom.id,
        name=classroom.name,
        inviteCode=classroom.invite_code if is_owner else None,
        roleInClass="student",
        isOwner=is_owner,
        memberCount=member_count,
        createdAt=classroom.created_at,
    )


def list_members(
    classroom_id: str, requester_user_id: str, db: Session
) -> list[ClassroomMemberOut]:
    """List all members in a classroom. Exposes email and note only to owner."""
    classroom = db.query(Classroom).filter(Classroom.id == classroom_id).first()
    if not classroom:
        raise ClassroomError("class.not_found", "班级不存在", 404)

    is_owner = classroom.owner_user_id == requester_user_id
    is_member = (
        db.query(ClassroomMember.id)
        .filter(
            ClassroomMember.class_id == classroom_id,
            ClassroomMember.user_id == requester_user_id,
        )
        .first()
        is not None
    )
    if not is_owner and not is_member:
        raise ClassroomError("class.not_found", "班级不存在", 404)

    rows = (
        db.query(ClassroomMember, User.display_name, User.email_display)
        .join(User, ClassroomMember.user_id == User.id)
        .filter(ClassroomMember.class_id == classroom_id)
        .order_by(
            case((ClassroomMember.role_in_class == "teacher", 0), else_=1),
            ClassroomMember.joined_at.asc(),
        )
        .all()
    )

    return [
        ClassroomMemberOut(
            userId=m.user_id,
            displayName=display_name,
            email=email_display if is_owner else None,
            note=m.note if is_owner else None,
            roleInClass=m.role_in_class,
            joinedAt=m.joined_at,
        )
        for m, display_name, email_display in rows
    ]


def remove_member(
    classroom_id: str,
    member_user_id: str,
    requester_user_id: str,
    db: Session,
) -> None:
    """Remove a student member from a classroom. Owner only."""
    classroom = db.query(Classroom).filter(Classroom.id == classroom_id).first()
    if not classroom:
        raise ClassroomError("class.not_found", "班级不存在", 404)

    if classroom.owner_user_id != requester_user_id:
        raise ClassroomError("class.not_found", "班级不存在", 404)

    if member_user_id == classroom.owner_user_id:
        raise ClassroomError("class.forbidden", "不能移除班级所有者", 400)

    membership = (
        db.query(ClassroomMember)
        .filter(
            ClassroomMember.class_id == classroom_id,
            ClassroomMember.user_id == member_user_id,
        )
        .first()
    )
    if not membership:
        raise ClassroomError("class.invalid_member", "该成员不在班级中", 404)

    db.delete(membership)
    db.commit()


def update_member_note(
    classroom_id: str,
    member_user_id: str,
    note: str | None,
    requester_user_id: str,
    db: Session,
) -> ClassroomMemberOut:
    """Update private note on a student member. Owner only."""
    classroom = db.query(Classroom).filter(Classroom.id == classroom_id).first()
    if not classroom:
        raise ClassroomError("class.not_found", "班级不存在", 404)

    if classroom.owner_user_id != requester_user_id:
        raise ClassroomError("class.not_found", "班级不存在", 404)

    membership = (
        db.query(ClassroomMember)
        .filter(
            ClassroomMember.class_id == classroom_id,
            ClassroomMember.user_id == member_user_id,
        )
        .first()
    )
    if not membership:
        raise ClassroomError("class.invalid_member", "该成员不在班级中", 404)

    user = db.query(User).filter(User.id == member_user_id).first()
    display_name = user.display_name if user else "未知用户"
    email = user.email_display if user else None

    cleaned_note = note.strip() if note else None
    membership.note = cleaned_note
    db.commit()
    db.refresh(membership)

    return ClassroomMemberOut(
        userId=membership.user_id,
        displayName=display_name,
        email=email,
        note=membership.note,
        roleInClass=membership.role_in_class,
        joinedAt=membership.joined_at,
    )
