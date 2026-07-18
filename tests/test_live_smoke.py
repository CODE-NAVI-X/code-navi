import os

import pytest

pytest.importorskip("openai")

from kernel.adapters.openai import OpenAIResponsesAdapter
from kernel.core import (
    ContentBlock,
    KernelConfig,
    Message,
    PermissionGrant,
    RunStatus,
    ToolExecutionContext,
    ToolPermission,
    ToolRegistry,
    ToolSpec,
    run,
)


@pytest.mark.live
def test_openai_two_step_read_tool_smoke() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is required for the live smoke test")
    model = os.environ.get("OPENAI_LIVE_MODEL")
    if not model:
        pytest.skip("OPENAI_LIVE_MODEL must explicitly select the live test model")

    scope = "openai-live-smoke"
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            "read_smoke_value",
            "Read the deterministic value required to answer the smoke test.",
            {"type": "object", "additionalProperties": False},
            frozenset({ToolPermission.READ}),
        ),
        lambda args, context: {"value": "kernel-live-smoke"},
    )
    dispatcher = registry.bind(PermissionGrant(scope), ToolExecutionContext(scope))
    prompt = Message(
        "user",
        (
            ContentBlock(
                "text",
                {
                    "text": (
                        "Call read_smoke_value exactly once. After receiving its "
                        "result, reply with only the returned value."
                    )
                },
            ),
        ),
    )

    result = run(
        OpenAIResponsesAdapter(model, max_output_tokens=128),
        dispatcher,
        [prompt],
        KernelConfig(
            max_steps=2,
            max_tool_calls=1,
            max_total_tokens=512,
            retry_max_attempts=1,
        ),
        run_id=scope,
    )

    assert result.status is RunStatus.COMPLETED
    assert [event.type for event in result.events].count("tool_called") == 1
    assert result.output is not None
    text = "".join(block.data["text"] for block in result.output.content if block.type == "text")
    assert text.strip() == "kernel-live-smoke"
