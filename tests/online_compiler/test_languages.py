from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from code_navi.online_compiler.languages import (
    BUILTIN_LANGUAGE_PACKAGES,
    DEFAULT_LANGUAGE_ID,
    ExecutionMode,
    LanguagePackage,
    LanguageStatus,
    RuntimeRequirement,
    build_language_manifest,
)


def test_builtin_packages_keep_python_as_the_only_enabled_language() -> None:
    packages = {package.id: package for package in BUILTIN_LANGUAGE_PACKAGES}

    assert tuple(packages) == (
        "python",
        "c",
        "cpp",
        "java",
        "javascript",
        "go",
        "rust",
        "sql",
    )
    assert DEFAULT_LANGUAGE_ID == "python"
    assert packages["python"].status is LanguageStatus.ENABLED
    assert {
        package.id for package in packages.values() if package.status is LanguageStatus.ENABLED
    } == {"python"}
    assert packages["c"].status is LanguageStatus.UNAVAILABLE
    assert packages["cpp"].runtime == RuntimeRequirement("gcc", "c++", "10.2.0")
    assert packages["java"].status is LanguageStatus.UNAVAILABLE
    assert packages["javascript"].status is LanguageStatus.UNAVAILABLE
    assert packages["go"].status is LanguageStatus.PLANNED
    assert packages["rust"].status is LanguageStatus.PLANNED
    assert packages["sql"].status is LanguageStatus.PLANNED


def test_language_package_is_immutable_and_validates_server_owned_metadata() -> None:
    package = LanguagePackage(
        id="python",
        display_name="Python",
        aliases=("py",),
        mode=ExecutionMode.PISTON,
        status=LanguageStatus.ENABLED,
        runtime=RuntimeRequirement("python", "python", "3.12.0"),
        source_file="main.py",
        file_extension=".py",
        editor_language="python",
    )

    with pytest.raises(FrozenInstanceError):
        package.id = "javascript"  # type: ignore[misc]

    with pytest.raises(ValueError, match="lowercase stable identifier"):
        LanguagePackage(
            id="C++",
            display_name="C++",
            aliases=(),
            mode=ExecutionMode.PISTON,
            status=LanguageStatus.UNAVAILABLE,
            runtime=RuntimeRequirement("gcc", "c++", "10.2.0"),
            source_file="main.cpp",
            file_extension=".cpp",
            editor_language="cpp",
        )

    with pytest.raises(ValueError, match="file_extension"):
        LanguagePackage(
            id="python",
            display_name="Python",
            aliases=(),
            mode=ExecutionMode.PISTON,
            status=LanguageStatus.ENABLED,
            runtime=RuntimeRequirement("python", "python", "3.12.0"),
            source_file="main.py",
            file_extension="py",
            editor_language="python",
        )


def test_execution_mode_requires_consistent_runtime_metadata() -> None:
    with pytest.raises(ValueError, match="Piston languages require runtime metadata"):
        LanguagePackage(
            id="python",
            display_name="Python",
            aliases=(),
            mode=ExecutionMode.PISTON,
            status=LanguageStatus.ENABLED,
            runtime=None,
            source_file="main.py",
            file_extension=".py",
            editor_language="python",
        )

    with pytest.raises(ValueError, match="SQL languages cannot declare a Piston runtime"):
        LanguagePackage(
            id="sql",
            display_name="SQL",
            aliases=("sqlite",),
            mode=ExecutionMode.SQL,
            status=LanguageStatus.PLANNED,
            runtime=RuntimeRequirement("python", "python", "3.12.0"),
            source_file="main.sql",
            file_extension=".sql",
            editor_language="sql",
        )

    with pytest.raises(ValueError, match="runtime must be a RuntimeRequirement"):
        LanguagePackage(
            id="go",
            display_name="Go",
            aliases=(),
            mode=ExecutionMode.PISTON,
            status=LanguageStatus.PLANNED,
            runtime="latest",  # type: ignore[arg-type]
            source_file="main.go",
            file_extension=".go",
            editor_language="go",
        )


def test_manifest_contains_only_the_frozen_public_capability_fields() -> None:
    manifest = build_language_manifest(BUILTIN_LANGUAGE_PACKAGES)

    assert manifest["schemaVersion"] == "compiler-languages.v1"
    assert manifest["defaultLanguageId"] == "python"
    python = manifest["languages"][0]
    assert python == {
        "id": "python",
        "displayName": "Python",
        "aliases": ["py", "py3", "python3", "python3.12"],
        "mode": "piston",
        "status": "enabled",
        "runtimeId": "python",
        "runtimeVersion": "3.12.0",
        "sourceFile": "main.py",
        "fileExtension": ".py",
        "editorLanguage": "python",
    }
    assert "command" not in str(manifest)
    assert "limits" not in str(manifest)
