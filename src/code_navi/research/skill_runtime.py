"""Load the packaged research-clarification Skill contract."""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files

RESEARCH_CLARIFICATION_SKILL_ID = "research-clarification"
RESEARCH_CLARIFICATION_SKILL_VERSION = "1.0.0"
ACADEMIC_SEARCH_SKILL_ID = "academic-search"
ACADEMIC_SEARCH_SKILL_VERSION = "1.0.0"


@lru_cache(maxsize=1)
def load_research_clarification_skill() -> str:
    """Return the canonical runtime instructions from the packaged SKILL.md."""
    resource = files("code_navi.research").joinpath(
        "skills", RESEARCH_CLARIFICATION_SKILL_ID, "SKILL.md"
    )
    text = resource.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) != 3 or "name: research-clarification" not in parts[1]:
        raise RuntimeError("invalid packaged research-clarification Skill metadata")
    body = parts[2].strip()
    if not body:
        raise RuntimeError("packaged research-clarification Skill is empty")
    return body


@lru_cache(maxsize=1)
def load_academic_search_skill() -> str:
    """Return the canonical academic-search instructions from package data."""
    resource = files("code_navi.research").joinpath(
        "skills", ACADEMIC_SEARCH_SKILL_ID, "SKILL.md"
    )
    text = resource.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) != 3 or "name: academic-search" not in parts[1]:
        raise RuntimeError("invalid packaged academic-search Skill metadata")
    body = parts[2].strip()
    if not body:
        raise RuntimeError("packaged academic-search Skill is empty")
    return body


__all__ = [
    "ACADEMIC_SEARCH_SKILL_ID",
    "ACADEMIC_SEARCH_SKILL_VERSION",
    "RESEARCH_CLARIFICATION_SKILL_ID",
    "RESEARCH_CLARIFICATION_SKILL_VERSION",
    "load_academic_search_skill",
    "load_research_clarification_skill",
]
