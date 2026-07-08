import json

import pytest

from kernel.core import AgentState, Event, RunResult, RunStatus


def finished_event(reason: str) -> Event:
    return Event(
        "e1",
        "r1",
        0,
        "2026-07-08T00:00:00Z",
        "run_finished",
        {"status": "fatal_error", "reason": reason},
    )


def test_run_result_reason_round_trips() -> None:
    event = finished_event("retry_exhausted")
    state = AgentState.fold([event])
    result = RunResult(RunStatus.FATAL_ERROR, state, (event,), "retry_exhausted")

    encoded = json.loads(json.dumps(result.to_json()))

    assert RunResult.from_json(encoded) == result
    assert encoded["reason"] == "retry_exhausted"


def test_run_result_reason_must_match_final_run_finished_event() -> None:
    event = finished_event("retry_exhausted")
    state = AgentState.fold([event])

    with pytest.raises(ValueError, match="RunResult.reason"):
        RunResult(RunStatus.FATAL_ERROR, state, (event,), "fatal_provider_error")
