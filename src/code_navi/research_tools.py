"""Small, local-first research tools for the Code-Navi research coach."""

from collections.abc import Mapping
from typing import Any

from code_navi.research.academic import AcademicSearchTool
from kernel.core import ToolExecutionContext, ToolPermission, ToolRegistry, ToolSpec

RESEARCH_CLARIFICATION_TOOL = "research_clarification"
ACADEMIC_SEARCH_TOOL = "academic_search"


def research_clarification_spec() -> ToolSpec:
    return ToolSpec(
        RESEARCH_CLARIFICATION_TOOL,
        "Create a bounded research brief from a topic and optional goal or context.",
        {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "minLength": 2, "maxLength": 200},
                "objective": {"type": "string", "maxLength": 300},
                "research_object": {"type": "string", "maxLength": 300},
            },
            "required": ["topic"],
            "additionalProperties": False,
        },
        frozenset({ToolPermission.READ}),
    )


def research_clarification_handler(
    args: Mapping[str, Any], _context: ToolExecutionContext
) -> dict[str, Any]:
    topic = str(args["topic"]).strip()
    objective = str(args.get("objective") or "待澄清")
    research_object = str(args.get("research_object") or "未限定")
    missing = [
        name
        for name, value in (
            ("objective", args.get("objective")),
            ("research_object", args.get("research_object")),
        )
        if not value
    ]
    return {
        "research_brief": {
            "topic": topic,
            "objective": objective,
            "research_object": research_object,
        },
        "missing_fields": missing,
        "next_step": "补充缺失字段后再生成研究计划。",
    }


def academic_search_spec() -> ToolSpec:
    return ToolSpec(
        ACADEMIC_SEARCH_TOOL,
        "Search explicitly selected, allow-listed academic metadata sources only.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 2, "maxLength": 300},
                "sources": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 1,
                    "items": {"type": "string", "enum": ["arxiv"]},
                },
            },
            "required": ["query", "sources"],
            "additionalProperties": False,
        },
        frozenset({ToolPermission.READ, ToolPermission.NETWORK}),
    )


def academic_search_handler(
    args: Mapping[str, Any], context: ToolExecutionContext, search_tool: AcademicSearchTool
) -> dict[str, object]:
    return search_tool.search(context.run_scope, str(args["query"]), list(args["sources"]))


def register_research_tools(
    registry: ToolRegistry,
    academic_search: AcademicSearchTool | None = None,
) -> None:
    registry.register(research_clarification_spec(), research_clarification_handler)
    search_tool = academic_search or AcademicSearchTool()
    registry.register(
        academic_search_spec(),
        lambda args, context: academic_search_handler(args, context, search_tool),
    )
