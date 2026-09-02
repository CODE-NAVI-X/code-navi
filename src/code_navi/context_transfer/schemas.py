"""Public API schemas for persisted cross-module context handoffs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer


class ContextSourceObject(BaseModel):
    """Stable reference to the application record that produced the context."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["notebook_item"]
    id: str = Field(min_length=1, max_length=36)


class SelectedContextContent(BaseModel):
    """One user-selected, editable content snapshot."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: Literal["summary", "detail"]
    label: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=12_000)


class CreateContextTransferRequest(BaseModel):
    """Create a Research-bound draft from a real Learning notebook record."""

    model_config = ConfigDict(extra="forbid")

    source_module: Literal["learning"]
    source_object: ContextSourceObject
    source_scope_id: str = Field(min_length=1, max_length=64)
    target_module: Literal["research"]
    selected_parts: list[Literal["summary", "detail"]] = Field(
        default_factory=lambda: ["summary"],
        min_length=1,
        max_length=2,
    )

    @field_validator("selected_parts")
    @classmethod
    def selected_parts_are_unique(
        cls, values: list[Literal["summary", "detail"]]
    ) -> list[Literal["summary", "detail"]]:
        if len(values) != len(set(values)):
            raise ValueError("selected_parts must not contain duplicates")
        return values


class UpdateContextTransferRequest(BaseModel):
    """Edit the draft snapshot without mutating its source Learning record."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    topic: str | None = Field(default=None, min_length=1, max_length=500)
    summary: str | None = Field(default=None, min_length=1, max_length=12_000)
    selected_content: list[SelectedContextContent] | None = Field(
        default=None,
        max_length=2,
    )

    @field_validator("selected_content")
    @classmethod
    def selected_content_kinds_are_unique(
        cls, values: list[SelectedContextContent] | None
    ) -> list[SelectedContextContent] | None:
        if values is None:
            return None
        kinds = [item.kind for item in values]
        if len(kinds) != len(set(kinds)):
            raise ValueError("selected_content kinds must not contain duplicates")
        return values


class LearningMasterySnapshot(BaseModel):
    """``learning_mastery_snapshot`` block of contract §3.2.

    Server-generated from the source learning portrait's rule aggregation
    (``learning_profile`` strengths/weaknesses); the client only flips the
    ``include_mastery_snapshot`` switch and never supplies the values.
    """

    model_config = ConfigDict(extra="forbid")

    strong: list[str] = Field(default_factory=list, max_length=5)
    weak: list[str] = Field(default_factory=list, max_length=5)


class ConfirmContextTransferRequest(BaseModel):
    """Final user-reviewed data used to create the target conversation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    topic: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=12_000)
    selected_content: list[SelectedContextContent] = Field(max_length=2)
    # Client-side switch only: the snapshot values themselves are always
    # rule-generated server-side (contract §3.2).  ``extra="forbid"`` rejects
    # any client attempt to smuggle snapshot values into the request.
    include_mastery_snapshot: bool = False

    @field_validator("selected_content")
    @classmethod
    def selected_content_kinds_are_unique(
        cls, values: list[SelectedContextContent]
    ) -> list[SelectedContextContent]:
        kinds = [item.kind for item in values]
        if len(kinds) != len(set(kinds)):
            raise ValueError("selected_content kinds must not contain duplicates")
        return values


class ConfirmedContextProvenance(BaseModel):
    """Immutable source and final snapshot recorded by a Research conversation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["context-provenance.v1"] = "context-provenance.v1"
    transfer_id: str
    source_module: Literal["learning"]
    source_object: ContextSourceObject
    source_scope_id: str
    target_module: Literal["research"]
    topic: str
    summary: str
    selected_content: list[SelectedContextContent]
    # §3.2 optional block; absent (None) in every provenance written before the
    # switch existed, so old snapshots keep validating and restoring unchanged.
    learning_mastery_snapshot: LearningMasterySnapshot | None = None
    confirmed_at: datetime

    @model_serializer(mode="wrap")
    def _omit_absent_mastery_snapshot(self, handler: Any) -> dict:
        """Drop the §3.2 key when no snapshot was generated.

        Provenances written with the switch off (and all pre-§3.2 rows) must
        serialize to exactly their old shape: no ``learning_mastery_snapshot``
        key at all, not a ``null`` placeholder.
        """
        data = handler(self)
        if data.get("learning_mastery_snapshot") is None:
            data.pop("learning_mastery_snapshot", None)
        return data


class ContextTransferResponse(BaseModel):
    """Restorable context draft shown on the target-module confirmation page."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["context-transfer.v1"] = "context-transfer.v1"
    id: str
    source_module: Literal["learning"]
    source_object: ContextSourceObject
    source_scope_id: str
    target_module: Literal["research"]
    topic: str
    summary: str
    selected_content: list[SelectedContextContent]
    status: Literal["draft", "confirmed"]
    confirmed_conversation_id: str | None = None
    confirmed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
