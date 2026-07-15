"""Student-facing agent specifications."""

from kernel.runtime import AgentSpec

student_tutor_agent = AgentSpec(
    name="student_tutor",
    description="Provides clear, supportive learning guidance for students.",
    system_prompt="你是一名学生学习辅导员。用清晰、循序的方式帮助理解问题。",
    tool_names=(),
    output_format="markdown",
)

__all__ = ["student_tutor_agent"]
