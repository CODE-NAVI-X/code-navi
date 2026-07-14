"""Research-facing agent specifications."""

from kernel.runtime import AgentSpec


research_coach_agent = AgentSpec(
    name="research_coach",
    description="Supports rigorous research planning and interpretation.",
    system_prompt="你是一名科研辅导员。基于已有证据提供建议，不得编造结果。",
    tool_names=(),
    output_format="markdown",
)

__all__ = ["research_coach_agent"]
