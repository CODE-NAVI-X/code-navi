# S6 Observability and Replay Decisions

Status: FROZEN for S6 v1 as of 2026-07-14.

Amend only by explicit user decision. Record amendments in the changelog.

## 1. Governing Invariants

I3: "Kernel-native, JSON-round-trippable types are the stable boundary."

I7: "Every durable runtime fact is an append-only Event, and kernel core owns event log, replay semantics, and persistence schema while remaining storage-agnostic."

The S5 JSONL adapter remains `kernel/adapters/jsonl_session.py`. Trace and replay consume its Event-only format; persistence does not move into core.

## 2. Provider I/O Events

D1. S6 adds exactly `provider_called` and `provider_returned`. `attempt` is payload data and never part of an Event type name.

D2. `provider_called` records `attempt`, complete kernel-native `messages`, and complete kernel-native `tools` immediately before every provider call.

D3. `provider_returned` records `attempt`, `request_event_id`, `request_seq`, and complete `ProviderResult.to_json()` immediately after success.

D4. Provider success ordering is `provider_called -> provider_returned -> budget_updated -> message_added`.

D5. Provider failure ordering is `provider_called -> error(source="provider", classification="retryable" | "fatal", attempt=N)`. There is no provider failure Event.

D6. Provider Events contain no provider SDK objects, handlers, real PermissionGrant objects, subprocess runners, host UI state, or secrets held outside the normalized request/response boundary.

D7. `AgentState.fold()` ignores both provider Events except for common sequence progression.

## 3. Deterministic Replay

D8. `ReplayProvider(recorded_log)` serves only recorded provider outcomes and never calls a live provider.

D9. Each actual request is structurally compared with the recorded request without broad canonicalization. Exhausted, extra, and mismatched calls raise `ReplayDivergence`; callers close replay verification with `assert_consumed()`, which raises the same divergence for unconsumed records.

D10. `ReplayDivergence` is a `FatalProviderError` and reports source Event index, Event sequence, JSON Pointer path, expected value, and actual value.

D11. Logs without complete provider I/O remain traceable but are explicitly not replayable.

## 4. Determinism

D12. Production runs generate a random run ID by default. Replay supplies the original run ID. Event IDs are deterministic from `(run_id, seq)`.

D13. When prior Events exist their run ID is fact. A conflicting caller run ID follows the kernel fatal path.

D14. Timestamps are record-only metadata and are never inputs to kernel decisions. Record/replay identity excludes only timestamps.

D15. Each new provider step starts at retry attempt 1. A successful provider call resets retry state before the next step.

## 5. Trace CLI and Scope

D16. Trace lives under `kernel/trace`; JSONL remains under `kernel/adapters`.

D17. S6 supports default rendering, verbose payload rendering, and structural run diffing. It does not include a TUI, dashboard, OpenTelemetry, metrics pipeline, real provider adapter, or general evaluation framework.

Changelog: 2026-07-14 initial S6 freeze after explicit user approval.
