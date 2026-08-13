"""Built-in language package declarations for the foundation stage."""

from __future__ import annotations

from .models import ExecutionMode, LanguagePackage, LanguageStatus, RuntimeRequirement
from .registry import LanguageRegistry

BUILTIN_LANGUAGE_PACKAGES = (
    LanguagePackage(
        id="python",
        display_name="Python",
        aliases=("py", "py3", "python3", "python3.12"),
        mode=ExecutionMode.PISTON,
        status=LanguageStatus.ENABLED,
        runtime=RuntimeRequirement("python", "python", "3.12.0"),
        source_file="main.py",
        file_extension=".py",
        editor_language="python",
    ),
    LanguagePackage(
        id="c",
        display_name="C",
        aliases=(),
        mode=ExecutionMode.PISTON,
        status=LanguageStatus.UNAVAILABLE,
        runtime=RuntimeRequirement("gcc", "c", "10.2.0"),
        source_file="main.c",
        file_extension=".c",
        editor_language="c",
    ),
    LanguagePackage(
        id="cpp",
        display_name="C++",
        aliases=("c++",),
        mode=ExecutionMode.PISTON,
        status=LanguageStatus.UNAVAILABLE,
        runtime=RuntimeRequirement("gcc", "c++", "10.2.0"),
        source_file="main.cpp",
        file_extension=".cpp",
        editor_language="cpp",
    ),
    LanguagePackage(
        id="java",
        display_name="Java",
        aliases=(),
        mode=ExecutionMode.PISTON,
        status=LanguageStatus.UNAVAILABLE,
        runtime=RuntimeRequirement("java", "java", "15.0.2"),
        source_file="Main.java",
        file_extension=".java",
        editor_language="java",
    ),
    LanguagePackage(
        id="javascript",
        display_name="JavaScript",
        aliases=("js",),
        mode=ExecutionMode.PISTON,
        status=LanguageStatus.UNAVAILABLE,
        runtime=RuntimeRequirement("node", "javascript", "20.11.1"),
        source_file="main.js",
        file_extension=".js",
        editor_language="javascript",
    ),
    LanguagePackage(
        id="go",
        display_name="Go",
        aliases=(),
        mode=ExecutionMode.PISTON,
        status=LanguageStatus.PLANNED,
        runtime=None,
        source_file="main.go",
        file_extension=".go",
        editor_language="go",
    ),
    LanguagePackage(
        id="rust",
        display_name="Rust",
        aliases=(),
        mode=ExecutionMode.PISTON,
        status=LanguageStatus.PLANNED,
        runtime=None,
        source_file="main.rs",
        file_extension=".rs",
        editor_language="rust",
    ),
    LanguagePackage(
        id="sql",
        display_name="SQL",
        aliases=("sqlite",),
        mode=ExecutionMode.SQL,
        status=LanguageStatus.PLANNED,
        runtime=None,
        source_file="main.sql",
        file_extension=".sql",
        editor_language="sql",
    ),
)

DEFAULT_LANGUAGE_REGISTRY = LanguageRegistry(BUILTIN_LANGUAGE_PACKAGES)
