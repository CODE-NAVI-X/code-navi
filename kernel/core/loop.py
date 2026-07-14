"""S3 plan-act-observe execution loop."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from .context import ContextBudgetExceeded, ContextPolicy, FullHistory
from .types import (
    AgentState,
    Event,
    FatalProviderError,
    KernelConfig,
    Message,
    MockProvider,
    ProviderResult,
    RetryableProviderError,
    RunResult,
    RunStatus,
    ToolCall,
    ToolDispatcher,
    make_tool_result_block,
)


class Provider(Protocol):
    def complete(self, messages: Sequence[Message], tools: Sequence[dict[str, Any]] | None = None) -> ProviderResult:
        ...


def _event(run_id: str, seq: int, event_type: str, payload: dict[str, Any]) -> Event:
    event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{run_id}:{seq}"))
    return Event(event_id, run_id, seq, datetime.now(UTC).isoformat(), event_type, payload)


def _error_payload(
    source: str,
    classification: str,
    exc: BaseException,
    attempt: int | None,
) -> dict[str, Any]:
    return {
        "source": source,
        "classification": classification,
        "message": str(exc),
        "attempt": attempt,
    }


def _tool_calls_from(message: Message) -> tuple[ToolCall, ...]:
    return tuple(
        ToolCall.from_json(block.data["tool_call"])
        for block in message.content
        if block.type == "tool_use"
    )


def _last_message(state: AgentState) -> Message | None:
    return state.messages[-1] if state.messages else None


def _final_reason(events: Sequence[Event]) -> str | None:
    return next(
        (event.payload.get("reason") for event in reversed(events) if event.type == "run_finished"),
        None,
    )


def _inflight_tool_ids(events: Sequence[Event]) -> set[str]:
    called = {
        event.payload["tool_call"]["id"] for event in events if event.type == "tool_called"
    }
    returned = {
        event.payload["tool_result"]["tool_call_id"] for event in events if event.type == "tool_returned"
    }
    return called - returned


def run(
    provider: Provider | MockProvider,
    tool_dispatcher: ToolDispatcher,
    initial_messages: Sequence[Message],
    config: KernelConfig | None = None,
    *,
    prior_events: Sequence[Event] = (),
    run_id: str | None = None,
    context_policy: ContextPolicy | None = None,
    context_budget_tokens: int | None = None,
    interrupt_check: Callable[[], bool] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> RunResult:
    """Run provider calls until one terminal condition is reached."""
    config = config or KernelConfig()
    context_policy = context_policy or FullHistory()
    context_budget = context_budget_tokens
    if context_budget is None:
        context_budget = getattr(provider, "max_context", None) or (2**63 - 1)
    if run_id is not None and (
        not isinstance(run_id, str) or not run_id
    ):
        raise ValueError("run_id must be a non-empty string when supplied")
    events: list[Event] = list(prior_events)
    recovered = AgentState.fold(events)
    recovered_run_id = recovered.run_id
    effective_run_id = recovered_run_id or run_id or str(uuid.uuid4())
    seq = recovered.last_seq + 1
    used_steps = recovered.steps_used
    used_tool_calls = recovered.tool_calls_used

    def emit(event_type: str, payload: dict[str, Any]) -> None:
        nonlocal seq
        events.append(_event(effective_run_id, seq, event_type, payload))
        seq += 1

    def emit_budget() -> None:
        emit(
            "budget_updated",
            {
                "used_steps": used_steps,
                "max_steps": config.max_steps,
                "used_tool_calls": used_tool_calls,
                "max_tool_calls": config.max_tool_calls,
            },
        )

    def finish(status: RunStatus, reason: str, error: str | None = None, output: Message | None = None) -> RunResult:
        payload: dict[str, Any] = {"status": status.value, "reason": reason}
        emit("run_finished", payload)
        state = AgentState.fold(events)
        return RunResult(status, state, tuple(events), reason, output, error)

    def maybe_interrupt() -> RunResult | None:
        if interrupt_check is not None and interrupt_check():
            emit("interrupted", {})
            return finish(RunStatus.INTERRUPTED, "interrupted")
        return None

    if (
        recovered_run_id is not None
        and run_id is not None
        and run_id != recovered_run_id
    ):
        exc = RuntimeError(
            f"run_id mismatch: prior Events use {recovered_run_id!r}, "
            f"caller supplied {run_id!r}"
        )
        emit("error", _error_payload("kernel", "fatal", exc, None))
        return finish(RunStatus.FATAL_ERROR, "kernel_error", str(exc))

    if recovered.status in {
        RunStatus.COMPLETED,
        RunStatus.INTERRUPTED,
        RunStatus.FATAL_ERROR,
    }:
        return RunResult(
            recovered.status,
            recovered,
            tuple(events),
            _final_reason(events),
            _last_message(recovered),
        )

    if recovered.interrupted:
        exc = RuntimeError("cannot resume from an interrupted event prefix")
        emit("error", _error_payload("kernel", "fatal", exc, None))
        return finish(RunStatus.FATAL_ERROR, "kernel_error", str(exc))
    if _inflight_tool_ids(events):
        exc = RuntimeError("unsafe resume: in-flight tool call")
        emit("error", _error_payload("kernel", "fatal", exc, None))
        return finish(RunStatus.FATAL_ERROR, "unsafe_resume_inflight_tool", str(exc))

    if events:
        messages = tuple(recovered.messages)
    else:
        emit("run_started", {})
        messages = tuple(initial_messages)
        for message in messages:
            emit("message_added", {"message": message.to_json()})

    attempt = 1
    while True:
        interrupted = maybe_interrupt()
        if interrupted is not None:
            return interrupted
        if used_steps >= config.max_steps:
            return finish(RunStatus.BUDGET_EXHAUSTED, RunStatus.BUDGET_EXHAUSTED.value)
        try:
            context_view = context_policy.view(tuple(events), context_budget)
            if context_view.compression is not None:
                emit("context_compressed", context_view.compression.to_payload())
            provider_tools: tuple[dict[str, Any], ...] = ()
            emit(
                "provider_called",
                {
                    "attempt": attempt,
                    "messages": [
                        message.to_json() for message in context_view.messages
                    ],
                    "tools": list(provider_tools),
                },
            )
            request_event = events[-1]
            result = provider.complete(context_view.messages, tools=provider_tools)
            emit(
                "provider_returned",
                {
                    "attempt": attempt,
                    "request_event_id": request_event.event_id,
                    "request_seq": request_event.seq,
                    "response": result.to_json(),
                },
            )
            used_steps += 1
            emit_budget()
            emit("message_added", {"message": result.message.to_json()})
            attempt = 1
            messages += (result.message,)
            tool_calls = _tool_calls_from(result.message)
            if not tool_calls:
                return finish(RunStatus.COMPLETED, "completed", output=result.message)
            for call in tool_calls:
                interrupted = maybe_interrupt()
                if interrupted is not None:
                    return interrupted
                if used_tool_calls >= config.max_tool_calls:
                    return finish(RunStatus.BUDGET_EXHAUSTED, "tool_budget_exhausted")
                emit("tool_called", {"tool_call": call.to_json()})
                used_tool_calls += 1
                emit_budget()
                try:
                    tool_result = tool_dispatcher.dispatch(call)
                except Exception as exc:
                    emit("error", _error_payload("tool", "fatal", exc, None))
                    return finish(RunStatus.FATAL_ERROR, "fatal_tool_error", str(exc))
                emit("tool_returned", {"tool_result": tool_result.to_json()})
                tool_message = Message("tool", (make_tool_result_block(tool_result),))
                emit("message_added", {"message": tool_message.to_json()})
                messages += (tool_message,)
        except ContextBudgetExceeded as exc:
            emit("error", _error_payload("kernel", "fatal", exc, None))
            return finish(
                RunStatus.FATAL_ERROR, "context_budget_exceeded", str(exc)
            )
        except RetryableProviderError as exc:
            emit("error", _error_payload("provider", "retryable", exc, attempt))
            if attempt > config.retry_max_attempts:
                return finish(RunStatus.FATAL_ERROR, "retry_exhausted", str(exc))
            sleeper(config.retry_backoff_seconds * (2 ** (attempt - 1)))
            attempt += 1
        except FatalProviderError as exc:
            emit("error", _error_payload("provider", "fatal", exc, attempt))
            return finish(RunStatus.FATAL_ERROR, "fatal_provider_error", str(exc))
        except Exception as exc:
            emit("error", _error_payload("provider", "fatal", exc, attempt))
            return finish(RunStatus.FATAL_ERROR, "fatal_provider_error", str(exc))
