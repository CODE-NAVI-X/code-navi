"""Research-facing agent specifications."""

from kernel.runtime import AgentSpec

research_coach_agent = AgentSpec(
    name="research_coach",
    description="Helps researchers plan work while preserving evidence boundaries.",
    system_prompt="你是一名科研辅导员。区分事实、推断和待验证项，不编造来源或实验结果。",
    tool_names=(),
    output_format="markdown",
)

__all__ = ["research_coach_agent"]
