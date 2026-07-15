"""Teacher-facing agent specifications."""

from kernel.runtime import AgentSpec

teacher_assistant_agent = AgentSpec(
    name="teacher_assistant",
    description="Helps teachers prepare reviewable instructional materials.",
    system_prompt="你是一名教师助理。输出可供教师复核的教学材料草案，不替教师发布结论。",
    tool_names=(),
    output_format="markdown",
)

__all__ = ["teacher_assistant_agent"]
