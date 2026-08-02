from __future__ import annotations

from code_navi.online_compiler.ai_evaluation import KernelAiEvaluator
from code_navi.online_compiler.evaluation import classify_execution
from code_navi.online_compiler.piston import ExecutionResult, RuntimeInfo
from kernel.core import ContentBlock, Message, ProviderResult
from kernel.providers import MockProvider
from kernel.runtime import AgentRuntime


def test_ai_evaluator_runs_through_agent_runtime_with_mock_provider() -> None:
    provider = MockProvider(
        [
            ProviderResult(
                Message(
                    "assistant",
                    (
                        ContentBlock(
                            "text",
                            {
                                "text": (
                                    '{"explanation":"除数为零导致异常。",'
                                    '"suggestions":["除法前检查除数"],'
                                    '"quality":{"readability":75,'
                                    '"structure":70,"robustness":35}}'
                                )
                            },
                        ),
                    ),
                )
            )
        ]
    )
    evaluator = KernelAiEvaluator(AgentRuntime(provider))
    result = ExecutionResult(
        outcome="runtime_error",
        stdout="",
        stderr="ZeroDivisionError: division by zero",
        exit_code=1,
        signal=None,
        status="RE",
        wall_time_ms=9,
        cpu_time_ms=7,
        memory_bytes=2_048,
        runtime=RuntimeInfo("python", "3.12.0"),
    )

    feedback = evaluator.evaluate(
        "print(1 / 0)",
        result,
        classify_execution(result),
        "fd5f93a4-36c9-4f8d-9a73-71af013a4368",
    )

    assert feedback.quality.overall == 60
    call = provider.calls[0]
    assert call["messages"][0]["metadata"]["agent_name"] == "code_result_explainer"
    assert call["messages"][1]["metadata"] == {
        "rule_category": "runtime_error",
        "language": "python",
    }
    assert call["tools"] == []
