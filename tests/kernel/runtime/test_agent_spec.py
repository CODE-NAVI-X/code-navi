import math

import pytest

from kernel.core import KernelConfig
from kernel.runtime import AgentSpec, RuntimeRequest


def test_agent_spec_is_stable_and_normalizes_tool_name_lists() -> None:
    spec = AgentSpec(
        name="reviewer",
        description="Reviews a submission.",
        system_prompt="Be concise and accurate.",
        tool_names=["lookup", "format"],
        default_config=KernelConfig(max_steps=3),
    )

    assert spec.name == "reviewer"
    assert spec.tool_names == ("lookup", "format")
    assert spec.default_config == KernelConfig(max_steps=3)
    assert spec.output_format == "markdown"


@pytest.mark.parametrize("field", ["name", "description", "system_prompt"])
@pytest.mark.parametrize("value", ["", "   ", None])
def test_agent_spec_rejects_missing_or_empty_required_text(field: str, value: object) -> None:
    values: dict[str, object] = {
        "name": "reviewer",
        "description": "Reviews a submission.",
        "system_prompt": "Be helpful.",
    }
    values[field] = value

    with pytest.raises(ValueError):
        AgentSpec(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("tool_names", ["lookup", ["lookup", "lookup"], [""], [None]])
def test_agent_spec_rejects_invalid_tool_names(tool_names: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        AgentSpec("reviewer", "Reviews.", "Be helpful.", tool_names=tool_names)  # type: ignore[arg-type]


@pytest.mark.parametrize("default_config", [{}, 1, "fast"])
def test_agent_spec_rejects_invalid_default_config(default_config: object) -> None:
    with pytest.raises(TypeError, match="default_config"):
        AgentSpec("reviewer", "Reviews.", "Be helpful.", default_config=default_config)  # type: ignore[arg-type]


def test_runtime_request_normalizes_metadata_and_validates_inputs() -> None:
    request = RuntimeRequest(
        "Summarize this.", session_id="session-1", run_id="run-1", metadata={"n": 1}
    )

    assert request.metadata == {"n": 1}
    assert type(request.metadata) is dict

    for kwargs in (
        {"user_input": ""},
        {"user_input": "ok", "session_id": " "},
        {"user_input": "ok", "run_id": ""},
        {"user_input": "ok", "metadata": []},
        {"user_input": "ok", "metadata": {"bad": {1, 2}}},
        {"user_input": "ok", "metadata": {"nan": math.nan}},
    ):
        with pytest.raises((TypeError, ValueError)):
            RuntimeRequest(**kwargs)  # type: ignore[arg-type]
