from kernel.core import PermissionGrant, ToolCall, ToolExecutionContext, ToolRegistry
from code_navi.research_tools import register_research_tools

def test_research_clarification_tool_returns_a_bounded_brief() -> None:
    registry = ToolRegistry(); register_research_tools(registry)
    dispatcher = registry.bind(PermissionGrant("research"), ToolExecutionContext("research"))
    result = dispatcher.dispatch(ToolCall("1", "research_clarification", {"topic": "RAG 幻觉"}))
    assert result.result["ok"] is True
    assert result.result["value"]["research_brief"]["topic"] == "RAG 幻觉"
