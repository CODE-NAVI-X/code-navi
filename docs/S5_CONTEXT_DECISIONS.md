# S5 Context and Persistence Decisions

Status: FROZEN for S5 v1 as of 2026-07-14.

Amend only by explicit user decision. Record amendments in the changelog.

## 1. Truth and Views

D1. The append-only Event log is source truth; context policy computes a provider-visible view and never rewrites or removes source Events.

D2. `AgentState.fold()` derives state from Events and ignores `context_compressed` as a derived-view audit fact except for common sequence progression.

## 2. Pinning and Budgets

D3. `Message.pinned: bool = False` is an explicit host decision; core performs no importance heuristics.

D4. Every pinned Message appears once and byte-for-byte JSON-equivalent in every viable view. If pinned content exceeds the budget, loop terminates with `fatal_error` and `reason="context_budget_exceeded"`.

## 3. Context Policy

D5. The policy interface is `ContextPolicy.view(events, budget_tokens) -> ContextView`; `ContextView` contains `messages` and optional `compression`.

D6. S5 ships exactly `FullHistory` and `TailWithSummary`. `FullHistory` is the no-op default; `TailWithSummary` preserves pins and a recent verbatim tail while replacing older unpinned Messages with a rolling summary.

D7. Core defines only `TokenCounter` and `Summarizer` protocols. Exact tokenization, summary prompts, provider-backed implementations, and provider SDKs remain outside core.

D8. Policy computes a compression plan but emits no Event. Loop is the only Event emitter.

## 4. Compression Audit

D9. S5 adds exactly one Event type, `context_compressed`. The later user-approved S6 amendment adds only `provider_called` and `provider_returned`; no other provider/context/summary Event type is allowed.

D10. Its payload contains `start_seq`, `end_seq`, exact `source_event_ids`, `summary`, and optional `previous_event_id`. Sources must be earlier, unpinned `message_added` Events.

D11. An existing compression with the same exact source Event IDs is reused after retry or resume and does not produce an equivalent duplicate Event.

## 5. Persistence and Resume

D12. `kernel/adapters/jsonl_session.py` is the JSONL file adapter. Core owns Event semantics but performs no filesystem persistence.

D13. JSONL stores Events only: never `AgentState`, snapshots as truth, or a real `PermissionGrant`.

D14. `save_session()` accepts only an existing complete prefix and appends its missing suffix. It rejects overwrite, truncation, and forks.

D15. `load_session()` requires UTF-8 newline-terminated JSONL, the exact Event envelope, one run ID, unique IDs, contiguous sequence from zero, Event JSON round-trip, valid compression references, and successful `AgentState.fold()`.

D16. Resume passes loaded Events as `prior_events`. The host must construct a fresh per-run dispatcher and `PermissionGrant`; Event history never restores authority.

## 6. Required Tests

D17. Tests cover pinned budgets, a step-40 load-bearing constraint, `context_compressed` and pinned Message round-trips, fold ignoring compression, append-only JSONL, corruption/fork rejection, save-load-resume equivalence, compression de-duplication, and fresh permission grants.

Changelog: 2026-07-14 initial S5 freeze after explicit user approval; 2026-07-14 S6 amendment acknowledged the two approved provider I/O Events without changing context semantics.
