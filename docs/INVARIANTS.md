# INVARIANTS (FROZEN)

Amend only by explicit user decision. Record amendments in the changelog at the bottom.

First host: code-navi CLI.

I1. Kernel core must stay platform-agnostic and must not know CLI, DingTalk, Lark, Telegram, or other transport details.
    Rationale: Host and service channels must not leak into runtime semantics.
    Check: grep core imports and type fields for platform names and transport SDKs.
I2. Kernel core owns the v1 single-agent execution loop.
    Rationale: A run needs one portable definition for progression, pause, resume, tool invocation, interruption, and terminal states.
    Check: review run-loop code for state progression outside kernel core.
I3. Kernel-native, JSON-round-trippable types are the stable boundary.
    Rationale: Message, ToolCall, Event, RunResult, AgentState, ProviderResult, and ProviderStreamEvent must not be polluted by provider or platform schemas.
    Check: review core types for provider-native fields and verify from_json(json.loads(json.dumps(to_json(x)))) == x.
I4. Every tool call must pass explicit registration, schema validation, and permission checks before execution.
    Rationale: Auditability and safety depend on rejecting unknown, malformed, or unauthorized calls.
    Check: tool execution path contains registry lookup, argument validation, and permission enforcement before handler invocation.
I5. Kernel core defines permission semantics but not confirmation UI.
    Rationale: READ, WRITE, DESTRUCTIVE, EXECUTE, NETWORK, SENSITIVE, and PUBLISH are runtime rules, while user interaction belongs to hosts.
    Check: permission types exist in core, while prompts, buttons, dialogs, and CLI confirmation rendering do not.
I6. Kernel core owns context-window policy.
    Rationale: Provider-visible context, budgets, pinned fields, compression triggers, truncation triggers, and related events are required for stable runs.
    Check: context assembly and compression/truncation event emission are in core; prompt text, summarizer choice, and business summaries are not.
I7. Every durable runtime fact is an append-only Event, and kernel core owns event log, replay semantics, and persistence schema while remaining storage-agnostic.
    Rationale: Debugging and recovery need immutable source facts, but files, databases, retention, encryption, and sync are deployment choices.
    Check: core derives state and context views from Events without rewriting them; JSONL appears only in adapters or CLI defaults.
I8. Kernel core owns the provider interface but imports no provider SDKs.
    Rationale: OpenAI, Anthropic, Gemini, Qwen, DeepSeek, Ollama, vLLM, and future providers must be replaceable adapters.
    Check: grep core imports for provider SDK packages and native request/response schemas.
I9. Kernel extensions must be explicitly registered.
    Rationale: Tools, providers, context sources, and storage backends must be reproducible and auditable.
    Check: no core code scans directories, imports packages dynamically, or auto-loads plugins.
I10. Kernel core contains no business logic, prompt content, RAG implementation, eval harness, or multi-agent orchestration.
    Rationale: These belong above or beside the kernel; v1 may keep run_id and parent_run_id without becoming an orchestrator.
    Check: review core modules for domain names, prompt templates, retrievers, benchmark runners, or agent scheduling logic.

Changelog: 2026-07-08 initial freeze; 2026-07-14 user-approved I3/I7 JSON round-trip and append-only Event clarification.
