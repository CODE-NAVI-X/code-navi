# S3 Loop Decisions

Status: FROZEN for S3 v1 as of 2026-07-08.

Amend only by explicit user decision. Record amendments in the changelog at the bottom.

This document is a decision ledger, not a tutorial, README, or implementation guide. It records only already-decided kernel loop constraints.

## 1. Scope

D1. `kernel/core/loop.py` is the S3 transition layer.
    It owns the v1 single-agent run lifecycle: provider calls, Event emission, tool dispatch sequencing, budgets, cooperative interrupts, retry policy, terminal status, and resume from Event history.

D2. `kernel/core/types.py` is the S2 to S3 contract layer.
    It defines kernel-native boundary types, including `RunResult`, `RunStatus`, `Event`, `Message`, `ToolCall`, `ToolResult`, `KernelConfig`, `ToolDispatcher`, provider errors, and `MockProvider`.

D3. The loop must not contain host behavior, confirmation UI, real provider adapter logic, tool registry logic, schema validation logic, permission checks, prompt policy, teaching policy, RAG, or business logic.

## 2. Terminal Statuses and Reasons

D4. S3 v1 terminal statuses are:

- `completed`
- `budget_exhausted`
- `interrupted`
- `fatal_error`

D5. `RunResult.reason` mirrors the final `run_finished.payload["reason"]`.
    The Event remains the source of truth. `RunResult.reason` is a convenience field for callers.

D6. The current S3 v1 reason list is:

- `completed`
- `interrupted`
- `budget_exhausted`
- `tool_budget_exhausted`
- `retry_exhausted`
- `fatal_provider_error`
- `fatal_tool_error`
- `kernel_error`
- `unsafe_resume_inflight_tool`
- `context_budget_exceeded`

D7. Every S3 v1 `run_finished` Event carries both `status` and `reason`.

## 3. Event Types and Payload Contracts

D8. S3 v1 uses only the S2 frozen Event set as amended by S5 and S6.
    S5 adds `context_compressed`; S6 adds exactly `provider_called` and `provider_returned`. No provider failure Event or other provider/context/summary Event variant is allowed.

D9. `budget_updated` payload is:

```python
{
    "used_steps": int,
    "max_steps": int,
    "used_tool_calls": int,
    "max_tool_calls": int,
}
```

D10. `budget_updated` does not contain token fields in S3 v1.

D11. `error` payload is:

```python
{
    "source": "provider" | "tool" | "kernel",
    "classification": "retryable" | "fatal",
    "message": str,
    "attempt": int | None,
}
```

D12. Ordinary tool failure represented as `ToolResult(error=...)` is not an `error` Event.

## 4. Provider Call Semantics

D13. The user-approved S6 amendment records every provider attempt as `provider_called` and every successful response as `provider_returned`.

`provider_called` contains `attempt`, complete kernel-native `messages`, and complete kernel-native `tools`. It never contains provider SDK objects, handlers, PermissionGrant instances, subprocess runners, secrets held outside the provider request, or host UI state.

`provider_returned` contains `attempt`, `request_event_id`, `request_seq`, and the complete `ProviderResult.to_json()` response.

D14. Provider success is represented by:

```text
budget_updated
message_added
```

D15. Provider failure is represented by:

```text
error(source="provider", ...)
```

D16. Provider success sequence is:

```text
provider_called
-> provider.complete(...) returns ProviderResult
-> provider_returned
-> used_steps += 1
-> budget_updated
-> message_added(provider_result.message)
-> scan message.content for tool_use
```

Provider failure sequence is exactly:

```text
provider_called
-> error(source="provider", classification="retryable" | "fatal", attempt=N)
```

There is no provider failure Event type.

D17. Provider exceptions do not emit `budget_updated` or `message_added`.

## 5. Budget Semantics

D18. `used_steps` counts only successfully completed `provider.complete(...)` calls.

D19. Provider exceptions do not increment `used_steps`.

D20. Tool calls do not increment `used_steps`.

D21. Step budget is checked at iteration top after interrupt check and before `provider.complete(...)`.

D22. If `used_steps >= max_steps`, the loop emits:

```python
run_finished(status="budget_exhausted", reason="budget_exhausted")
```

D23. `used_tool_calls` counts attempted tool dispatches.

D24. Tool budget is checked immediately before each tool dispatch, after interrupt check and before `tool_called`.

D25. If `used_tool_calls >= max_tool_calls`, the loop emits:

```python
run_finished(status="budget_exhausted", reason="tool_budget_exhausted")
```

It does not emit `tool_called` and does not dispatch the tool.

## 6. Tool Dispatch Semantics

D26. S3 v1 has exactly one tool execution boundary:

```python
tool_dispatcher.dispatch(call: ToolCall) -> ToolResult
```

D27. `loop.py` must not import concrete tool implementations or know whether tools come from functions, MCP, HTTP, sandboxing, or services.

D28. `tool_dispatcher` owns registry lookup, schema validation, permission checks, execution, and ordinary tool exception conversion to `ToolResult`.

D29. `tool_dispatcher` must not emit Events in S3 v1. Only the loop emits Events.

D30. Tool dispatch sequence is:

```text
interrupt_check
-> tool budget check
-> tool_called
-> used_tool_calls += 1
-> budget_updated
-> tool_dispatcher.dispatch(call)
-> tool_returned
-> message_added(tool_result)
```

D31. If `tool_dispatcher.dispatch(call)` raises, the attempted call already counts. The loop emits:

```python
error(source="tool", classification="fatal", attempt=None)
run_finished(status="fatal_error", reason="fatal_tool_error")
```

## 7. Tool Use / Tool Result Content Blocks

D32. Provider tool use is represented only as:

```python
ContentBlock(
    type="tool_use",
    data={"tool_call": ToolCall.to_json()},
)
```

D33. `ProviderResult` does not have a separate `tool_calls` field.

D34. The loop scans only `ProviderResult.message.content` for `type == "tool_use"`.

D35. Tool result context is represented only as:

```python
ContentBlock(
    type="tool_result",
    data={"tool_result": ToolResult.to_json()},
)
```

D36. `ToolCall.to_json()` and `ToolResult.to_json()` return JSON-compatible dicts, not JSON strings and not native objects.

## 8. Retry Semantics

D37. Provider adapters and `MockProvider` express provider failure classification through:

- `RetryableProviderError`
- `FatalProviderError`

D38. Unknown provider exceptions are fatal in S3 v1 and are not retried.

D39. `RetryableProviderError` emits:

```python
error(source="provider", classification="retryable", attempt=N)
```

D40. `FatalProviderError` emits:

```python
error(source="provider", classification="fatal", attempt=N)
```

D41. Retry backoff is injected through:

```python
sleeper: Callable[[float], None] = time.sleep
```

D42. `sleeper` only waits. It does not decide retry count or backoff policy.

D43. The last `RetryableProviderError` after retry exhaustion remains `classification="retryable"`.
    The loop then emits:

```python
run_finished(status="fatal_error", reason="retry_exhausted")
```

D44. Fatal provider errors and unknown provider exceptions do not sleep.

## 9. Interrupt Semantics

D45. Interrupts are cooperative and are injected through:

```python
interrupt_check: Callable[[], bool] | None = None
```

D46. `interrupt_check` receives no `AgentState`.

D47. The loop checks interrupts only:

- at iteration top, before budget check and before `provider.complete(...)`
- before each `tool_dispatcher.dispatch(call)`

D48. Interrupt terminal sequence is:

```text
interrupted
run_finished(status="interrupted", reason="interrupted")
```

D49. S3 v1 does not force-kill an in-flight provider call or tool dispatch.

## 10. Resume Semantics

D50. Resume input is:

```python
prior_events: Sequence[Event] = ()
```

D51. Resume starts from `AgentState.fold(prior_events)`, reuses the recovered `run_id`, and continues Event sequence from `last_seq + 1`.

D52. Resume uses recovered messages and budget counters.

D53. Resume does not re-emit `run_started` or initial `message_added` Events.

D54. Resume must not automatically re-dispatch in-flight tool calls.

D55. Completed, interrupted, and fatal terminal logs are read-only. `run(...)` returns the recovered `RunResult` without calling provider, dispatching tools, or appending Events. The user-approved S6 run-ID integrity check is the sole exception: if a caller supplies a run ID that conflicts with prior Events, the kernel appends its fatal mismatch path under the recorded run ID and performs no provider or tool call.

D56. If `prior_events` contains `interrupted` but not `run_finished(status="interrupted")`, S3 v1 treats it as an incomplete or abnormal log and returns `fatal_error` with `reason="kernel_error"`.

D57. To continue after interruption, the host must start a new run or pass a safe Event prefix before the `interrupted` Event.

## 11. Test Layout

D58. S3 lifecycle tests live under:

```text
tests/kernel/core/test_loop_*.py
```

D59. The initial S3 test split is:

- `tests/kernel/core/test_loop_lifecycle.py`
- `tests/kernel/core/test_loop_budget.py`
- `tests/kernel/core/test_loop_tools.py`
- `tests/kernel/core/test_loop_interrupt.py`
- `tests/kernel/core/test_loop_resume.py`
- `tests/kernel/core/test_loop_retry.py`
- `tests/kernel/core/test_run_result.py`

D60. Any lifecycle behavior recorded in this document must have at least one corresponding test under `tests/kernel/core/test_loop_*.py` or `tests/kernel/core/test_run_result.py`.

## 12. Explicit Non-goals for S3 v1

D61. No new Event types beyond S5 `context_compressed` and the two S6-approved `provider_called` and `provider_returned` additions.

D62. No async, batch, or streamed tool results.

D63. No provider-native schemas in `kernel/core`.

D64. No concrete tool implementations in `loop.py`.

D65. No confirmation UI, host prompts, or blocking on user input in core.

D66. No automatic continuation from interrupted terminal logs.

D67. No token budget enforcement in S3 v1, even though `KernelConfig.max_total_tokens` remains part of the S2 type contract.

## Changelog

### 2026-07-08 — Initial S3 loop decision ledger

Created the S3 v1 decision ledger for loop scope, terminal statuses, Event payloads, provider semantics, budgets, tool dispatch, retry, interrupt, resume, tests, and non-goals.

### 2026-07-08 — Unsafe resume with in-flight tool call tightened

S3 v1 now treats any `prior_events` prefix containing `tool_called` without a matching `tool_returned` as unsafe to resume.

The loop must not redispatch the tool call, must not continue to the next provider step, and must not run interrupt or budget checks before this invariant is handled.

Required behavior:

- emit `error(source="kernel", classification="fatal", attempt=None)`
- emit `run_finished(status="fatal_error", reason="unsafe_resume_inflight_tool")`
- return `RunResult(status="fatal_error", reason="unsafe_resume_inflight_tool")`

Rationale: the tool may already have produced side effects, but the event log does not contain a corresponding result. Redispatch risks duplicate side effects; continuing provider execution risks advancing without the required tool result.

### 2026-07-14 — S5 context view integration

The user approved a one-time D8/D61 amendment adding only `context_compressed`. A context policy returns `ContextView(messages, compression)` without mutating Event history; loop remains the sole Event emitter and appends the compression audit Event before the provider call. If pinned content cannot fit the supplied context budget, loop emits a fatal kernel error and finishes with `reason="context_budget_exceeded"`.

### 2026-07-14 — S6 provider I/O and replay amendment

The user approved adding only `provider_called` and `provider_returned`. `attempt` remains payload data. Success ordering is `provider_called -> provider_returned -> budget_updated -> message_added`; failure ordering is `provider_called -> error(source="provider", ...)`. Successful provider calls reset retry attempt state so each new provider step begins at attempt 1.

Replay may supply the recorded `run_id`. When `prior_events` exist they remain the fact source; a conflicting caller-supplied `run_id` follows the kernel fatal path. Event IDs may be derived deterministically from `(run_id, seq)`, while timestamps remain record-only metadata and never affect decisions.
