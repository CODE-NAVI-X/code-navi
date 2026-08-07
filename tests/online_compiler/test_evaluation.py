from __future__ import annotations

import pytest

from code_navi.online_compiler.evaluation import (
    QualityRubric,
    classify_execution,
    parse_ai_feedback,
)
from code_navi.online_compiler.piston import ExecutionResult, RuntimeInfo


def execution(outcome: str, *, stderr: str = "") -> ExecutionResult:
    return ExecutionResult(
        outcome=outcome,
        stdout="",
        stderr=stderr,
        exit_code=0 if outcome == "success" else 1,
        signal=None,
        status=None,
        wall_time_ms=12,
        cpu_time_ms=8,
        memory_bytes=1_024,
        runtime=RuntimeInfo("python", "3.12.0"),
    )


def test_python_syntax_error_is_not_misclassified_as_runtime_error() -> None:
    result = execution(
        "runtime_error",
        stderr=(
            '  File "/piston/jobs/abc/main.py", line 3\n'
            "    print(\n"
            "         ^\n"
            'SyntaxError: "(" was never closed\n'
        ),
    )

    assessment = classify_execution(result)

    assert assessment.category == "syntax_error"
    assert assessment.error_type == "SyntaxError"
    assert assessment.line == 3
    assert "never closed" in assessment.summary


def test_runtime_error_extracts_exception_and_last_main_line() -> None:
    result = execution(
        "runtime_error",
        stderr=(
            'Traceback (most recent call last):\n  File "/piston/jobs/a/main.py", line 4, '
            'in <module>\n    value = 1 / 0\nZeroDivisionError: division by zero\n'
        ),
    )

    assessment = classify_execution(result)

    assert assessment.category == "runtime_error"
    assert assessment.error_type == "ZeroDivisionError"
    assert assessment.line == 4


def test_timeout_is_deterministic_and_not_a_correctness_score() -> None:
    assessment = classify_execution(execution("time_limit"))

    assert assessment.category == "time_limit"
    assert assessment.severity == "warning"
    assert assessment.as_dict()["source"] == "deterministic_rule"


def test_success_explicitly_does_not_claim_answer_correctness() -> None:
    assessment = classify_execution(execution("success"))

    assert assessment.category == "success"
    assert "尚未使用题目测试用例" in assessment.summary


def test_ai_json_is_validated_and_overall_is_derived() -> None:
    feedback = parse_ai_feedback(
        '{"explanation":"命名清晰。","suggestions":["补充边界检查"],'
        '"quality":{"readability":90,"structure":80,"robustness":70}}'
    )

    assert feedback.quality == QualityRubric(90, 80, 70)
    assert feedback.quality.overall == 80
    assert feedback.as_dict()["scoreType"] == "ai_code_quality_reference"


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        '{"explanation":"","suggestions":[],"quality":{}}',
        (
            '{"explanation":"x","suggestions":["y"],'
            '"quality":{"readability":101,"structure":80,"robustness":70}}'
        ),
    ],
)
def test_invalid_ai_feedback_is_rejected(payload: str) -> None:
    with pytest.raises(ValueError):
        parse_ai_feedback(payload)
