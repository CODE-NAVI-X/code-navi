"""Teacher-facing agent specifications."""

from kernel.runtime import AgentSpec


teacher_assistant_agent = AgentSpec(
    name="teacher_assistant",
    description="Assists teachers with clear instructional support.",
    system_prompt="你是一名教师助理。提供清晰、实用的教学支持。",
    tool_names=(),
    output_format="markdown",
)

__all__ = ["teacher_assistant_agent"]
