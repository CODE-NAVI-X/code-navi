from __future__ import annotations

import pytest

from code_navi.online_compiler.languages import (
    BUILTIN_LANGUAGE_PACKAGES,
    ExecutionMode,
    LanguagePackage,
    LanguageRegistry,
    LanguageStatus,
    RuntimeIdentity,
    RuntimeRequirement,
)


def test_registry_resolves_stable_ids_and_declared_product_aliases() -> None:
    registry = LanguageRegistry(BUILTIN_LANGUAGE_PACKAGES)

    assert registry.default.id == "python"
    assert registry.require("PYTHON").id == "python"
    assert registry.require(" py3 ").id == "python"
    assert registry.require("C++").id == "cpp"
    assert registry.get("unknown") is None
    with pytest.raises(KeyError, match="unknown language"):
        registry.require("node-js")


def test_registry_rejects_duplicate_ids_and_aliases() -> None:
    python = BUILTIN_LANGUAGE_PACKAGES[0]
    duplicate_alias = LanguagePackage(
        id="python-alt",
        display_name="Python Alt",
        aliases=("py",),
        mode=ExecutionMode.PISTON,
        status=LanguageStatus.UNAVAILABLE,
        runtime=RuntimeRequirement("python", "python", "3.12.0"),
        source_file="main.py",
        file_extension=".py",
        editor_language="python",
    )

    with pytest.raises(ValueError, match="duplicate language id or alias"):
        LanguageRegistry((python, python))
    with pytest.raises(ValueError, match="duplicate language id or alias"):
        LanguageRegistry((python, duplicate_alias))


def test_capabilities_require_exact_runtime_id_and_version() -> None:
    registry = LanguageRegistry(BUILTIN_LANGUAGE_PACKAGES)

    exact = registry.with_runtime_capabilities(
        (RuntimeIdentity("python", "3.12.0", ("py",)),)
    )
    missing = registry.with_runtime_capabilities(())
    wrong_version = registry.with_runtime_capabilities(
        (RuntimeIdentity("python", "3.13.0", ("python3",)),)
    )
    alias_only = registry.with_runtime_capabilities(
        (RuntimeIdentity("cpython", "3.12.0", ("python",)),)
    )

    assert exact.require("python").status is LanguageStatus.ENABLED
    assert missing.require("python").status is LanguageStatus.UNAVAILABLE
    assert wrong_version.require("python").status is LanguageStatus.UNAVAILABLE
    assert alias_only.require("python").status is LanguageStatus.UNAVAILABLE


def test_runtime_discovery_cannot_enable_declared_unavailable_or_planned_languages() -> None:
    registry = LanguageRegistry(BUILTIN_LANGUAGE_PACKAGES)
    discovered = registry.with_runtime_capabilities(
        (
            RuntimeIdentity("java", "15.0.2"),
            RuntimeIdentity("javascript", "20.11.1", ("js",)),
        )
    )

    assert discovered.require("java").status is LanguageStatus.UNAVAILABLE
    assert discovered.require("javascript").status is LanguageStatus.UNAVAILABLE
    assert discovered.require("go").status is LanguageStatus.PLANNED
    assert discovered.require("sql").status is LanguageStatus.PLANNED


def test_registry_preserves_product_order_and_exposes_an_immutable_snapshot() -> None:
    registry = LanguageRegistry(BUILTIN_LANGUAGE_PACKAGES)

    assert registry.packages == BUILTIN_LANGUAGE_PACKAGES
    assert tuple(package.id for package in registry.packages[:3]) == ("python", "c", "cpp")
