"""Run the three built-in agents without calling an external model."""

from code_navi import (
    research_coach_agent,
    student_tutor_agent,
    teacher_assistant_agent,
)
from kernel.core import ContentBlock, Message, ProviderResult
from kernel.providers import MockProvider
from kernel.runtime import AgentRuntime, RuntimeRequest


def main() -> None:
    agents = (student_tutor_agent, teacher_assistant_agent, research_coach_agent)
    provider = MockProvider(
        [
            ProviderResult(
                Message("assistant", (ContentBlock("text", {"text": agent.name}),))
            )
            for agent in agents
        ]
    )
    runtime = AgentRuntime(provider)

    for agent in agents:
        result = runtime.run(agent, RuntimeRequest("请给出一个最小示例。"))
        print(f"{agent.name}: {result.output_text}")


if __name__ == "__main__":
    main()
