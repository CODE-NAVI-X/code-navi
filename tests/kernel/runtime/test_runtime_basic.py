import pytest

from kernel.core import (
    ContentBlock,
    KernelConfig,
    Message,
    PermissionGrant,
    ProviderResult,
    RunStatus,
    ToolCall,
    ToolExecutionContext,
    ToolPermission,
    ToolRegistry,
    ToolSpec,
)
from kernel.providers import MockProvider
from kernel.runtime import AgentRuntime, AgentSpec, RuntimeRequest


def text_message(text: str) -> Message:
    return Message("assistant", (ContentBlock("text", {"text": text}),))


def test_runtime_runs_one_agent_and_exposes_host_friendly_result() -> None:
    provider = MockProvider([ProviderResult(text_message("All done."))])
    runtime = AgentRuntime(provider)
    agent = AgentSpec("helper", "Helps with tasks.", "Follow the instructions.")

    result = runtime.run(
        agent,
        RuntimeRequest("Please help.", session_id="s-1", run_id="r-1", metadata={"source": "ui"}),
    )

    assert result.agent_name == "helper"
    assert result.run_id == "r-1"
    assert result.session_id == "s-1"
    assert result.run_result.status is RunStatus.COMPLETED
    assert result.events == result.run_result.events
    assert result.final_messages == result.run_result.state.messages
    assert result.output_text == "All done."
    assert result.event_log_path is None
    sent = provider.calls[0]["messages"]
    assert sent[0]["role"] == "system" and sent[0]["pinned"] is True
    assert sent[0]["metadata"] == {"agent_name": "helper", "output_format": "markdown", "session_id": "s-1"}
    assert sent[1]["role"] == "user" and sent[1]["pinned"] is True
    assert sent[1]["metadata"] == {"source": "ui"}


def test_runtime_config_priority_is_explicit_then_agent_then_runtime() -> None:
    agent_default = AgentSpec(
        "helper", "Helps.", "Help.", default_config=KernelConfig(max_steps=0)
    )
    runtime = AgentRuntime(
        MockProvider([ProviderResult(text_message("explicit wins"))]),
        default_config=KernelConfig(max_steps=0),
    )

    explicit = runtime.run(agent_default, RuntimeRequest("go", run_id="explicit"), config=KernelConfig(max_steps=1))
    assert explicit.run_result.status is RunStatus.COMPLETED

    agent_wins = AgentRuntime(MockProvider([]), default_config=KernelConfig(max_steps=1)).run(
        agent_default, RuntimeRequest("go", run_id="agent")
    )
    assert agent_wins.run_result.status is RunStatus.BUDGET_EXHAUSTED

    runtime_wins = AgentRuntime(MockProvider([]), default_config=KernelConfig(max_steps=0)).run(
        AgentSpec("plain", "Plain.", "Help."), RuntimeRequest("go", run_id="runtime")
    )
    assert runtime_wins.run_result.status is RunStatus.BUDGET_EXHAUSTED


def _registry_for(run_id: str, names: tuple[str, ...], calls: list[object]):
    registry = ToolRegistry()
    for name in names:
        registry.register(
            ToolSpec(
                name,
                f"{name} from the local test registry.",
                {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"], "additionalProperties": False},
                frozenset({ToolPermission.READ}),
            ),
            lambda args, context, tool_name=name: calls.append((tool_name, dict(args), context.run_scope)) or args["value"].upper(),
        )
    registry.freeze()
    return registry.bind(PermissionGrant(run_id), ToolExecutionContext(run_id))


def test_runtime_tool_loop_uses_requested_tools_factory_and_dispatcher() -> None:
    factory_calls: list[tuple[str, tuple[str, ...]]] = []
    handler_calls: list[object] = []

    def factory(run_id: str, names: tuple[str, ...]):
        factory_calls.append((run_id, names))
        return _registry_for(run_id, names, handler_calls)

    tool_call = ToolCall("call-1", "lookup", {"value": "answer"})
    provider = MockProvider([
        ProviderResult(Message("assistant", (ContentBlock("tool_use", {"tool_call": tool_call.to_json()}),))),
        ProviderResult(text_message("The lookup completed.")),
    ])
    result = AgentRuntime(provider, dispatcher_factory=factory).run(
        AgentSpec("tool_agent", "Uses local tools.", "Use lookup.", tool_names=("lookup",)),
        RuntimeRequest("Find it.", run_id="tools-run"),
    )

    assert factory_calls == [("tools-run", ("lookup",))]
    assert handler_calls == [("lookup", {"value": "answer"}, "tools-run")]
    assert result.output_text == "The lookup completed."
    assert [event.type for event in result.events if event.type in {"tool_called", "tool_returned"}] == ["tool_called", "tool_returned"]
    assert provider.calls[0]["tools"][0]["name"] == "lookup"


def test_runtime_rejects_declared_tools_without_factory() -> None:
    runtime = AgentRuntime(MockProvider([]))
    with pytest.raises(ValueError, match="dispatcher_factory"):
        runtime.run(AgentSpec("tool_agent", "Uses tools.", "Use tools.", ("lookup",)), RuntimeRequest("go"))


@pytest.mark.parametrize("declared, returned", [(('lookup',), ('lookup', 'extra')), (('first', 'second'), ('second', 'first'))])
def test_runtime_rejects_factory_tool_sets_that_do_not_match_spec(declared: tuple[str, ...], returned: tuple[str, ...]) -> None:
    def factory(run_id: str, names: tuple[str, ...]):
        return _registry_for(run_id, returned, [])

    runtime = AgentRuntime(MockProvider([]), dispatcher_factory=factory)
    with pytest.raises(ValueError, match="names and order"):
        runtime.run(AgentSpec("tool_agent", "Uses tools.", "Use tools.", declared), RuntimeRequest("go", run_id="bad-tools"))
