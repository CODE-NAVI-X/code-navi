"""Immutable contracts for server-owned programming language packages."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

_STABLE_ID = re.compile(r"^[a-z][a-z0-9-]*$")


class ExecutionMode(StrEnum):
    """Supported server-owned execution backends."""

    PISTON = "piston"
    SQL = "sql"


class LanguageStatus(StrEnum):
    """Product capability state for one language package."""

    ENABLED = "enabled"
    UNAVAILABLE = "unavailable"
    PLANNED = "planned"


def _non_empty(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def _string_tuple(value: Iterable[str], field: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise ValueError(f"{field} must be an iterable of strings")
    try:
        entries = tuple(value)
    except TypeError as exc:
        raise ValueError(f"{field} must be an iterable of strings") from exc
    if any(not isinstance(entry, str) or not entry.strip() for entry in entries):
        raise ValueError(f"{field} must contain non-empty strings")
    normalized = tuple(entry.strip().casefold() for entry in entries)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field} must be unique")
    return normalized


@dataclass(frozen=True, slots=True)
class RuntimeRequirement:
    """An exact server-owned Piston package and runtime requirement."""

    package: str
    runtime_id: str
    version: str

    def __post_init__(self) -> None:
        _non_empty(self.package, "package")
        _non_empty(self.runtime_id, "runtime_id")
        _non_empty(self.version, "version")


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    """A discovered Piston runtime identity used for exact capability checks."""

    runtime_id: str
    version: str
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _non_empty(self.runtime_id, "runtime_id")
        _non_empty(self.version, "version")
        object.__setattr__(self, "aliases", _string_tuple(self.aliases, "aliases"))


@dataclass(frozen=True, slots=True)
class LanguagePackage:
    """Immutable metadata for one selectable programming language."""

    id: str
    display_name: str
    aliases: tuple[str, ...]
    mode: ExecutionMode
    status: LanguageStatus
    runtime: RuntimeRequirement | None
    source_file: str
    file_extension: str
    editor_language: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or _STABLE_ID.fullmatch(self.id) is None:
            raise ValueError("id must be a lowercase stable identifier")
        _non_empty(self.display_name, "display_name")
        if not isinstance(self.mode, ExecutionMode):
            raise ValueError("mode must be an ExecutionMode")
        if not isinstance(self.status, LanguageStatus):
            raise ValueError("status must be a LanguageStatus")
        aliases = _string_tuple(self.aliases, "aliases")
        if self.id in aliases:
            raise ValueError("aliases cannot repeat the stable language id")
        object.__setattr__(self, "aliases", aliases)
        if self.runtime is not None and not isinstance(self.runtime, RuntimeRequirement):
            raise ValueError("runtime must be a RuntimeRequirement or None")
        if self.mode is ExecutionMode.PISTON:
            if self.status is not LanguageStatus.PLANNED and not isinstance(
                self.runtime, RuntimeRequirement
            ):
                raise ValueError("Piston languages require runtime metadata")
        elif self.runtime is not None:
            raise ValueError("SQL languages cannot declare a Piston runtime")
        _non_empty(self.source_file, "source_file")
        if "/" in self.source_file or "\\" in self.source_file:
            raise ValueError("source_file must be a server-owned file name")
        if (
            not isinstance(self.file_extension, str)
            or not self.file_extension.startswith(".")
            or len(self.file_extension) == 1
        ):
            raise ValueError("file_extension must start with a dot")
        if not self.source_file.endswith(self.file_extension):
            raise ValueError("source_file must use file_extension")
        _non_empty(self.editor_language, "editor_language")
