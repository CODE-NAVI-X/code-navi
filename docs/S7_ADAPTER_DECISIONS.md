# S7 Provider Adapter Decisions

Status: **APPROVED for the first OpenAI adapter on 2026-07-14.**

## 1. Provider Contract Gate

D1. `kernel/core/provider.py` owns the kernel-native `Provider` Protocol,
`ProviderTool`, `ProviderCapabilities`, and provider error classification types.
It imports no provider SDK.

D2. `MockProvider` lives in `kernel/providers/mock.py`. Stable JSON-round-trippable
provider result and stream types remain in `kernel/core/types.py`.

D3. `RunToolDispatcher.provider_tools()` returns only model-visible name,
description, and argument schema from its bound registry snapshot. It never
returns handlers, grants, workspace roots, destructive authorization, or
execution context.

D4. The loop records and sends the same immutable `ProviderTool` snapshot on
every provider attempt. `dispatch(call)` remains the only tool execution
boundary.

## 2. First Real Adapter

D5. OpenAI is the first S1 migration target. Its single adapter is
`kernel/adapters/openai.py` and uses the Responses API with `store=False`.

D6. The model is a required constructor argument. The adapter sets OpenAI SDK
`max_retries=0`; S3 remains the sole retry owner.

D7. OpenAI function calls preserve native response order and become ordered
`tool_use` content blocks. The loop dispatches them sequentially.

D8. OpenAI tools use the frozen ToolSpec schema without adapter rewrites and
explicitly set `strict=False`.

D9. `image_ref` and `artifact_ref` are fatal unsupported inputs in this S7
adapter. No content block is silently dropped.

D10. Connection errors, timeouts, 408, 409, 429, and 5xx map to
`RetryableProviderError`. Authentication, permission, request validation, 404,
422, and response validation errors map to `FatalProviderError`.

## 3. Verification

D11. MockProvider must pass provider conformance before OpenAI recorded mode is
registered in the same suite.

D12. Recorded OpenAI conformance covers Unicode and long content, a multi-turn
READ tool round trip, ordered multiple function calls, and simulated 429
classification.

D13. Recorded runs are persisted as strict JSONL and replayed through
`ReplayProvider`, with identity excluding only Event timestamps under S6.

D14. The live smoke test is marked `live`, excluded by default, budget-capped to
two provider steps and one READ tool, and requires both `OPENAI_API_KEY` and an
explicit `OPENAI_LIVE_MODEL`.
