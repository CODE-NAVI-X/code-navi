"""Pydantic schemas for the classroom module."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateClassroomRequest(BaseModel):
    """Payload to create a new classroom."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("班级名称不能为空")
        return trimmed


class JoinClassroomRequest(BaseModel):
    """Payload to join an existing classroom via invite code."""

    model_config = ConfigDict(extra="forbid")

    inviteCode: str = Field(..., min_length=1, max_length=32)

    @field_validator("inviteCode")
    @classmethod
    def validate_invite_code(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("邀请码不能为空")
        return trimmed


class ClassroomOut(BaseModel):
    """Serialized classroom view."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    inviteCode: str | None = None
    roleInClass: str
    isOwner: bool
    memberCount: int
    createdAt: datetime


class ClassroomListResponse(BaseModel):
    """List of classrooms."""

    items: list[ClassroomOut]


class ClassroomMemberOut(BaseModel):
    """Single member within a classroom."""

    model_config = ConfigDict(from_attributes=True)

    userId: str
    displayName: str
    email: str | None = None
    note: str | None = None
    roleInClass: str
    joinedAt: datetime


class ClassroomMemberListResponse(BaseModel):
    """List of classroom members."""

    items: list[ClassroomMemberOut]


class UpdateMemberNoteRequest(BaseModel):
    """Payload to update member note."""

    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=500)
