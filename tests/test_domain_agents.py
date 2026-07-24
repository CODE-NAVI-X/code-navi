from code_navi import (
    code_learning_agent,
    research_coach_agent,
    student_tutor_agent,
    teacher_assistant_agent,
)
from code_navi.domains.research import RESEARCH_TOOL_CONTRACTS
from kernel.core import ContentBlock, Message, ProviderResult, RunStatus
from kernel.providers import MockProvider
from kernel.runtime import AgentRuntime, AgentSpec, RuntimeRequest


def test_research_tool_contracts_document_safe_future_capabilities() -> None:
    names = {item["name"] for item in RESEARCH_TOOL_CONTRACTS}
    assert names == {
        "research_clarification",
        "research_plan",
        "academic_search",
        "paper_evidence_card",
    }
    academic_search = next(
        item for item in RESEARCH_TOOL_CONTRACTS if item["name"] == "academic_search"
    )
    assert academic_search["permissions"] == ("READ", "NETWORK")


def test_domain_agent_specs_are_valid_markdown_agents() -> None:
    for agent in (student_tutor_agent, teacher_assistant_agent, research_coach_agent):
        assert isinstance(agent, AgentSpec)
        assert agent.name and agent.description and agent.system_prompt
        assert agent.tool_names == ()
        assert agent.output_format == "markdown"


def test_general_learning_agent_is_read_only_by_default() -> None:
    assert isinstance(code_learning_agent, AgentSpec)
    assert code_learning_agent.name == "code_learning_assistant"
    assert code_learning_agent.tool_names == ()
    assert code_learning_agent.output_format == "markdown"


def test_domain_agents_run_sequentially_through_one_runtime() -> None:
    agents = (student_tutor_agent, teacher_assistant_agent, research_coach_agent)
    provider = MockProvider(
        [
            ProviderResult(Message("assistant", (ContentBlock("text", {"text": name}),)))
            for name in ("student", "teacher", "research")
        ]
    )
    runtime = AgentRuntime(provider)

    results = [
        runtime.run(agent, RuntimeRequest("hello", run_id=f"domain-{index}"))
        for index, agent in enumerate(agents, start=1)
    ]

    assert [result.agent_name for result in results] == [
        "student_tutor",
        "teacher_assistant",
        "research_coach",
    ]
    assert [result.output_text for result in results] == ["student", "teacher", "research"]
    assert all(result.run_result.status is RunStatus.COMPLETED for result in results)
