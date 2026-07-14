# S2 ABSTRACTIONS DECISIONS

Status: FROZEN for S2 v1 as of 2026-07-08.

Amend only by explicit user decision. Record amendments in the changelog at the bottom.

D1. S2 code path is `kernel/core/...`; bare `core/...` is forbidden.
    Rationale: The project is extracting a portable Agent Kernel, so the path must make the platform-agnostic kernel boundary explicit and avoid mixing kernel abstractions with host, service, CLI, or domain-specific code.
    Check: Core abstractions live under `kernel/core/...`; tests refer to kernel core through that boundary.

D2. Initial provider migration targets are OpenAI, Anthropic, Gemini, Qwen, DeepSeek, Kimi, GLM, Baichuan, MiniMax, StepFun, Ollama, and vLLM.
    Rationale: The provider interface must cover mainstream hosted APIs, major domestic vendors, and local/open-compatible runtimes without importing provider-native schemas into kernel core.
    Check: `kernel/core/...` exposes provider-neutral request, response, tool, streaming, and error abstractions only; provider-specific names appear only in adapter packages and tests for those adapters.

D3. Tool permission vocabulary is frozen as seven composable permission flags: READ, WRITE, DESTRUCTIVE, EXECUTE, NETWORK, SENSITIVE, and PUBLISH.
    Rationale: Tool permissions are not mutually exclusive tiers; a tool may require multiple independent risk labels.
    Check: Core uses `ToolPermission` or `ToolPermissionFlag`, never `ToolPermissionTier`; tool specs declare `required_permissions: set[ToolPermission]`, and the kernel validates that all required permissions are allowed before executing a tool call.

Permission semantics:

- READ: Read data without changing durable state.
- WRITE: Create or modify durable state, but not in an obviously irreversible or externally visible way.
- DESTRUCTIVE: Delete, overwrite, revoke, reset, purge, or perform actions that are hard to undo.
- EXECUTE: Run code, commands, scripts, notebooks, tests, shell operations, or dynamic procedures.
- NETWORK: Access external networks, APIs, URLs, remote services, or provider-side resources.
- SENSITIVE: Access or process secrets, credentials, private user data, student records, grades, unpublished research, personal identity data, or protected institutional data.
- PUBLISH: Expose information or actions outside the local/private run context, including sending messages, emails, posts, notifications, PR comments, course announcements, or teacher/student-visible feedback.

Boundary notes:

- PUBLISH is not the same as NETWORK. External search is NETWORK; sending DingTalk messages, email, course notices, or formal student feedback is PUBLISH.
- SENSITIVE is not the same as READ. Reading public course material is READ; reading grades, student profiles, API keys, or unpublished experiment results is READ plus SENSITIVE.

Kernel core defines permission semantics only. Host layers decide how to ask for confirmation, display risk, or map permissions to UI policies.

D4. Event v1 set is frozen as run_started, message_added, tool_called, tool_returned, budget_updated, context_compressed, provider_called, provider_returned, interrupted, error, and run_finished.
    Rationale: `run_started` records the runtime beginning, the S5 addition `context_compressed` audits a derived provider-visible view, and the user-approved S6 additions `provider_called` and `provider_returned` record complete kernel-native provider I/O for deterministic replay.
    Check: Event type names are stable public kernel vocabulary; every event has the common envelope and JSON round-trips without provider-native objects.

S5 adds exactly one Event type, `context_compressed`, as a derived-view audit fact. It records the original `message_added` Event range and summary, never replaces source Events, and `AgentState.fold()` ignores it except for advancing the common Event sequence.

Event v1 deliberately excludes any other finer tracing events, including provider failure variants, state_updated, step_started, step_finished, context_compacted, permission_checked, and confirmation_requested. The S6 amendment permits exactly `provider_called` and `provider_returned`; `attempt` is payload data, never part of an Event type name.

Every Event must use this common envelope:

- `event_id`
- `run_id`
- `seq`
- `timestamp`
- `type`
- `payload`

`seq` is monotonic within a run and restores event order during replay. `payload` must be JSON-serializable and must not contain provider-native objects, exception objects, SDK responses, file handles, or other unserializable values.

Provider-specific details must stay inside normalized payload fields or adapter-private logs, not event type names.

D5. Message content block v1 is frozen as text, tool_use, tool_result, image_ref, and artifact_ref.
    Rationale: Message content must represent portable kernel-native content without embedding binary data or provider-native objects; references keep large or external data outside the core type system.
    Check: `kernel/core` serialization rejects unknown block types, rejects non-JSON-serializable content, and does not allow `raw_ref` as a standard Message content block.

Content block semantics:

- text: Plain UTF-8 text content.
- tool_use: A model-requested tool call represented by kernel-native ToolCall.
- tool_result: A tool execution result represented by kernel-native ToolResult.
- image_ref: A JSON-serializable reference or metadata object for an image. It must not embed binary data, bytes objects, PIL objects, SDK-native image objects, or large base64 payloads.
- artifact_ref: A JSON-serializable reference to an external artifact, such as a local file, object storage item, generated report, rendered chart, notebook output, dataset snapshot, or code patch.

Example `image_ref`:

```json
{
  "type": "image_ref",
  "uri": "file://artifacts/input/circle_gap_001.png",
  "mime_type": "image/png",
  "width": 512,
  "height": 512,
  "alt": "two circles with a small gap"
}
```

Example `artifact_ref`:

```json
{
  "type": "artifact_ref",
  "uri": "s3://bucket/courseware/week3-slides.pdf",
  "mime_type": "application/pdf",
  "name": "week3-slides.pdf",
  "kind": "courseware"
}
```

Message content blocks are closed in v1. Unknown block types are rejected by `kernel/core` serialization. Provider adapters may keep provider-native raw payloads outside Message, but must not store them inside Message content.

D6. KernelConfig v1 is frozen as run-level control budgets: max_steps, max_tool_calls, max_total_tokens, timeout_seconds, retry_max_attempts, retry_backoff_seconds, and allow_parallel_tool_calls.
    Rationale: KernelConfig should control one portable run without owning provider-specific decoding, pricing, tokenizer, or context-window policy details too early.
    Check: KernelConfig has only these v1 fields; provider-specific decoding parameters such as temperature, top_p, max_output_tokens, stop, and response_format do not live in KernelConfig v1.

Fields and defaults:

- `max_steps: int = 20`
- `max_tool_calls: int = 20`
- `max_total_tokens: int | None = None`
- `timeout_seconds: float | None = None`
- `retry_max_attempts: int = 2`
- `retry_backoff_seconds: float = 1.0`
- `allow_parallel_tool_calls: bool = False`

Field semantics:

- max_steps: Maximum number of kernel loop iterations in one run.
- max_tool_calls: Maximum number of tool calls allowed in one run.
- max_total_tokens: Maximum total provider token usage allowed in one run. None means token budget is not enforced by kernel v1. Provider adapters must normalize usage when available.
- timeout_seconds: Maximum wall-clock time for one run. None means no kernel-level timeout.
- retry_max_attempts: Maximum retry attempts for retryable provider/tool failures. 0 means no retry.
- retry_backoff_seconds: Base backoff seconds between retry attempts.
- allow_parallel_tool_calls: Whether the kernel may execute multiple tool calls from the same model step concurrently. Default is False in v1.

Excluded from KernelConfig v1:

- max_input_tokens
- max_output_tokens
- max_context_tokens
- max_cost_usd
- max_provider_calls
- max_concurrent_tools
- provider-specific decoding parameters such as temperature, top_p, stop, response_format, and provider-native options

Provider-specific decoding parameters belong to ProviderRequest, ProviderOptions, adapter configuration, or higher-level policy objects, not KernelConfig v1.

D7. S2 tests use deterministic hand-written generators and golden fixtures first; Hypothesis is not required in S2 v1.
    Rationale: During abstraction freeze, deterministic fixtures make type boundaries, serialization formats, and provider conformance behavior easier to inspect and stabilize.
    Check: Round-trip and conformance tests use seeded or hand-written deterministic data only; no unseeded randomness is allowed.

Round-trip tests must cover all kernel-native types:

- Message
- ToolCall
- ToolResult
- Event
- AgentState
- KernelConfig
- ProviderResult
- ProviderStreamEvent

Every round-trip test must verify:

```python
from_json(to_json(x)) == x
```

and preferably:

```python
from_json(json.loads(json.dumps(to_json(x)))) == x
```

Suggested S2 test structure:

- `tests/kernel/core/fixtures.py`
- `tests/kernel/core/test_message_roundtrip.py`
- `tests/kernel/core/test_toolcall_roundtrip.py`
- `tests/kernel/core/test_toolresult_roundtrip.py`
- `tests/kernel/core/test_event_roundtrip.py`
- `tests/kernel/core/test_agent_state_roundtrip.py`
- `tests/kernel/core/test_kernel_config_roundtrip.py`
- `tests/kernel/core/test_provider_conformance.py`

Fixture helpers should include representative Message content blocks, all Event v1 types, MockProvider, and a streaming-capable MockProvider.

Hypothesis may be introduced after S2 v1 types are frozen and golden fixtures pass, but it must not replace deterministic conformance fixtures.

Suggested initial module split:

- `kernel/core/messages.py`
- `kernel/core/tools.py`
- `kernel/core/events.py`
- `kernel/core/state.py`
- `kernel/core/config.py`
- `kernel/core/providers.py`
- `kernel/core/results.py`
- `kernel/core/serialization.py`

Suggested initial test split:

- `tests/kernel/core/test_message_roundtrip.py`
- `tests/kernel/core/test_toolcall_roundtrip.py`
- `tests/kernel/core/test_event_roundtrip.py`
- `tests/kernel/core/test_provider_conformance.py`

Changelog:
- 2026-07-08 initial S2 path decision.
- 2026-07-08 added initial provider migration targets.
- 2026-07-08 froze tool permission flags and semantics.
- 2026-07-08 froze Event v1 minimal event set and envelope.
- 2026-07-08 froze Message v1 content blocks.
- 2026-07-08 froze KernelConfig v1 fields and defaults.
- 2026-07-08 froze S2 deterministic test strategy.
- 2026-07-14 user-approved S6 amendment added only `provider_called` and `provider_returned` for complete kernel-native provider I/O.
- 2026-07-14 user-approved one-time D4 amendment adding only `context_compressed` for S5.
- 2026-07-14 user-approved S7 gate repair created `kernel/core/provider.py`,
  added kernel-native `ProviderTool` and `ProviderCapabilities`, and moved
  `MockProvider` to `kernel/providers/mock.py` before real adapter work.
