"""ORM models for the classroom module: classes and class_members."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..auth.models import User
from ..db import Base


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid4())


class Classroom(Base):
    """Classroom entity."""

    __tablename__ = "classes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    invite_code: Mapped[str] = mapped_column(
        String(12), nullable=False, unique=True, index=True
    )
    owner_user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_now, onupdate=_now
    )

    members: Mapped[list[ClassroomMember]] = relationship(
        "ClassroomMember",
        back_populates="classroom",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    owner: Mapped[User] = relationship("User", foreign_keys=[owner_user_id])


class ClassroomMember(Base):
    """Membership of a user in a class."""

    __tablename__ = "class_members"
    __table_args__ = (
        UniqueConstraint("class_id", "user_id", name="uq_class_members_class_user"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    class_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("classes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_in_class: Mapped[str] = mapped_column(
        String(16), nullable=False, default="student", server_default="student"
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)

    classroom: Mapped[Classroom] = relationship("Classroom", back_populates="members")
    user: Mapped[User] = relationship("User", foreign_keys=[user_id])
