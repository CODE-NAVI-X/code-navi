"""Domain-owned agent specifications."""

from .research import research_coach_agent
from .student import student_tutor_agent
from .teacher import teacher_assistant_agent

__all__ = [
    "research_coach_agent",
    "student_tutor_agent",
    "teacher_assistant_agent",
]
