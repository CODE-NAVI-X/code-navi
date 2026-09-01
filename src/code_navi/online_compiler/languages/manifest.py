"""Machine-readable language capability manifests."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypedDict

from .models import LanguagePackage
from .registry import DEFAULT_LANGUAGE_ID

LANGUAGE_MANIFEST_SCHEMA_VERSION = "compiler-languages.v1"


class LanguageManifestEntry(TypedDict):
    """Public fields for one language capability entry."""

    id: str
    displayName: str
    aliases: list[str]
    mode: str
    status: str
    runtimeId: str | None
    runtimeVersion: str | None
    sourceFile: str
    fileExtension: str
    editorLanguage: str


class LanguageManifest(TypedDict):
    """Versioned language capability manifest structure."""

    schemaVersion: str
    defaultLanguageId: str
    languages: list[LanguageManifestEntry]


def build_language_manifest(
    packages: Iterable[LanguagePackage],
    *,
    default_language_id: str = DEFAULT_LANGUAGE_ID,
) -> LanguageManifest:
    """Build the frozen public capability fields in product order."""

    entries = tuple(packages)
    if any(not isinstance(package, LanguagePackage) for package in entries):
        raise TypeError("packages must contain LanguagePackage values")
    if not any(package.id == default_language_id for package in entries):
        raise ValueError("default_language_id must be a registered stable ID")
    return {
        "schemaVersion": LANGUAGE_MANIFEST_SCHEMA_VERSION,
        "defaultLanguageId": default_language_id,
        "languages": [_manifest_entry(package) for package in entries],
    }


def _manifest_entry(package: LanguagePackage) -> LanguageManifestEntry:
    runtime = package.runtime
    return {
        "id": package.id,
        "displayName": package.display_name,
        "aliases": list(package.aliases),
        "mode": package.mode.value,
        "status": package.status.value,
        "runtimeId": runtime.runtime_id if runtime is not None else None,
        "runtimeVersion": runtime.version if runtime is not None else None,
        "sourceFile": package.source_file,
        "fileExtension": package.file_extension,
        "editorLanguage": package.editor_language,
    }
