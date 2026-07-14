# Code-Navi Agent Kernel

Code-Navi Agent Kernel 是一个小型、平台无关的单 Agent 运行时内核。它的第一个宿主目标是 Code-Navi CLI，但 kernel core 有意不包含 CLI、UI、真实 provider SDK、教学业务逻辑或其他平台相关行为。

本项目按阶段推进。每个 S 阶段先冻结一组很窄的 contract，再进入下一层实现。

### 当前状态

截至 2026-07-14：

- S1 Scope：已完成
- S2 Core abstractions：部分完成，已足够作为 S3 gate
- S3 Execution loop：core v1 已完成
- S4 Tools and permissions：已完成
- S5 Context and persistence：已完成
- S6 Observability and replay：已完成
- S7：尚未开始

验证命令：

```bash
python -m pytest -q
```

当前结果：

```text
78 passed
```

### 阶段总览

#### S1 Scope

目标：定义什么属于 kernel，什么必须留在 kernel 外部。

已完成产物：

- `docs/INVARIANTS.md`
- `docs/NON_GOALS.md`

关键决定：

- Kernel core 保持平台无关。
- Kernel core 拥有 v1 单 Agent execution loop。
- Kernel-native types 是稳定边界。
- Core 不导入 provider SDK。
- Core 拥有 Event 语义，但不拥有存储后端。
- Core 不包含业务逻辑、prompt 内容、RAG、UI 或多 Agent 编排。

完成度：已完成。

#### S2 Core Abstractions

目标：定义 loop 和未来 adapter 使用的最小 kernel-native type system。

已完成产物：

- `docs/S2_ABSTRACTIONS_DECISIONS.md`
- `kernel/core/types.py`
- `kernel/core/__init__.py`

当前 contract 包括：

- `Message`
- `ContentBlock`
- `ToolCall`
- `ToolResult`
- `Event`
- `AgentState`
- `RunStatus`
- `RunResult`
- `ProviderResult`
- `ProviderStreamEvent`
- `KernelConfig`
- `ToolPermission`
- `ToolDispatcher`
- `MockProvider`
- `RetryableProviderError`
- `FatalProviderError`

完成度：部分完成。

说明：

- S2 type gate 已足够支撑 S3。
- 仍需补充更完整的 round-trip 和 provider conformance tests。

#### S3 Execution Loop

目标：实现 plan-act-observe loop，统一管理 run lifecycle、terminal status、budget、retry、interrupt、tool dispatch 顺序和 resume 行为。

已完成产物：

- `docs/S3_LOOP_DECISIONS.md`
- `kernel/core/loop.py`
- `tests/kernel/core/test_loop_lifecycle.py`
- `tests/kernel/core/test_loop_budget.py`
- `tests/kernel/core/test_loop_tools.py`
- `tests/kernel/core/test_loop_interrupt.py`
- `tests/kernel/core/test_loop_resume.py`
- `tests/kernel/core/test_loop_retry.py`
- `tests/kernel/core/test_run_result.py`

已实现行为：

- terminal statuses: `completed`, `budget_exhausted`, `interrupted`, `fatal_error`
- `RunResult.reason` 镜像最终 `run_finished` Event 的 reason
- provider retry with bounded exponential backoff
- 注入式 sleeper，方便快速确定性测试
- step budget 和 tool-call budget
- cooperative interrupt checks
- 单一 tool dispatch call site
- tool result messages 写回模型上下文
- 从 `prior_events` resume
- terminal logs read-only
- unsafe resume with in-flight tool calls fails fast
- 除一次批准的 `context_compressed` 外不新增 Event type

完成度：core v1 已完成。

#### S4 Tools and Permissions

目标：实现显式 tool registry 和 permission enforcement layer。

已完成产物：

- `docs/S4_TOOLS_DESIGN.md`
- `docs/S4_TOOLS_DECISIONS.md`
- `kernel/core/registry.py`
- `kernel/tools/bash.py`
- `tests/kernel/core/test_registry.py`
- `tests/kernel/core/test_permissions.py`
- `tests/tools/test_bash.py`

已实现行为：

- 显式 `ToolRegistry` 与每 run `RunToolDispatcher`
- Draft 2020-12 JSON Schema 注册时与调用时校验
- 7 个可组合权限 flag 的 deny-by-default enforcement
- READ 默认允许，其他权限显式 grant
- DESTRUCTIVE 按具体工具名二次授权
- WRITE workspace root 边界检查
- 结构化 ToolResult 拒绝，保持 S2/S3 Event contract 不变
- 真实 unrestricted Bash 工具与文件 canary 测试

完成度：core v1 已完成。

#### S5 Context and Persistence

目标：定义 context-window policy 和 durable replay/resume 行为。

已完成产物：

- `docs/S5_CONTEXT_DECISIONS.md`
- `kernel/core/context.py`
- `kernel/adapters/jsonl_session.py`
- context pinning、load-bearing 与 session round-trip 测试

已实现行为：

- `ContextView`、`FullHistory` 与 `TailWithSummary`
- pinned Message 逐字保留与 `context_budget_exceeded` fatal path
- loop-only `context_compressed` Event emission
- rolling compression 去重与 resume 复用
- append-only JSONL prefix/suffix 保存和严格加载校验
- Event-only persistence；不持久化 AgentState 或真实 PermissionGrant

完成度：core policy 与 JSONL adapter v1 已完成。

#### S6 Observability and Replay

目标：让 run 可检查、可 replay、可 debug。

已完成产物：

- `docs/S6_OBSERVABILITY_DECISIONS.md`
- `docs/S6_DETERMINISM_AUDIT.md`
- `kernel/providers/replay.py`
- `kernel/trace/__main__.py`
- replay identity、divergence 与 trace CLI 测试

已实现行为：

- 完整 kernel-native provider request/response Events
- `ReplayProvider` 与字段级 `ReplayDivergence`
- 确定性 Event ID 与原始 run ID 重放
- 人类可读、verbose 与结构化 diff trace CLI
- 旧 S5 日志可 trace、明确不可 replay

完成度：S6 v1 已完成。

#### S7 Provider Adapters

目标：连接真实 LLM providers 和 agent frameworks，同时不污染 core contracts。

计划 adapter targets：

- OpenAI
- Anthropic
- Gemini
- Qwen
- DeepSeek
- Kimi
- GLM
- Baichuan
- MiniMax
- StepFun
- Ollama
- vLLM

完成度：尚未开始。

### 仓库结构

```text
docs/
  INVARIANTS.md
  NON_GOALS.md
  S2_ABSTRACTIONS_DECISIONS.md
  S3_LOOP_DECISIONS.md

kernel/
  core/
    types.py
    loop.py
    registry.py
  tools/
    bash.py

tests/
  kernel/
    core/
      test_loop_*.py
      test_run_result.py
      test_registry.py
      test_permissions.py
  tools/
    test_bash.py
```

### License

目前尚未选择 license。

公开前建议先明确 license。若不确定：

- MIT：简单、宽松。
- Apache-2.0：宽松，并包含明确 patent grant。
- 如果复用权利尚不清楚，先保持 private。

## README

Code-Navi Agent Kernel is a small, platform-agnostic runtime for single-agent execution. Its first host target is the Code-Navi CLI, while the kernel core intentionally stays free of CLI, UI, provider SDKs, teaching-domain logic, and platform-specific behavior.

The project is built in staged design phases. Each phase freezes a narrow contract before the next layer is added.

### Current Status

As of 2026-07-14:

- S1 Scope: complete
- S2 Core abstractions: partially complete, enough to gate S3
- S3 Execution loop: core v1 complete
- S4 Tools and permissions: complete
- S5 Context and persistence: complete
- S6 observability and replay: complete
- S7: not started

Validation:

```bash
python -m pytest -q
```

Current result:

```text
78 passed
```

### Phase Overview

#### S1 Scope

Goal: define what belongs in the kernel and what must stay outside it.

Completed artifacts:

- `docs/INVARIANTS.md`
- `docs/NON_GOALS.md`

Key decisions:

- Kernel core is platform-agnostic.
- Kernel core owns the v1 single-agent execution loop.
- Kernel-native types are the stable boundary.
- Core imports no provider SDKs.
- Core owns Event semantics but not storage backends.
- Core contains no business logic, prompt content, RAG, UI, or multi-agent orchestration.

Completion: complete.

#### S2 Core Abstractions

Goal: define the minimal kernel-native type system used by the loop and future adapters.

Completed artifacts:

- `docs/S2_ABSTRACTIONS_DECISIONS.md`
- `kernel/core/types.py`
- `kernel/core/__init__.py`

Current contracts include:

- `Message`
- `ContentBlock`
- `ToolCall`
- `ToolResult`
- `Event`
- `AgentState`
- `RunStatus`
- `RunResult`
- `ProviderResult`
- `ProviderStreamEvent`
- `KernelConfig`
- `ToolPermission`
- `ToolDispatcher`
- `MockProvider`
- `RetryableProviderError`
- `FatalProviderError`

Completion: partially complete.

Notes:

- The S2 type gate is sufficient for S3.
- More round-trip and provider conformance tests should be added.

#### S3 Execution Loop

Goal: implement the plan-act-observe loop that owns run lifecycle, terminal status, budgets, retries, interrupts, tool dispatch sequencing, and resume behavior.

Completed artifacts:

- `docs/S3_LOOP_DECISIONS.md`
- `kernel/core/loop.py`
- `tests/kernel/core/test_loop_lifecycle.py`
- `tests/kernel/core/test_loop_budget.py`
- `tests/kernel/core/test_loop_tools.py`
- `tests/kernel/core/test_loop_interrupt.py`
- `tests/kernel/core/test_loop_resume.py`
- `tests/kernel/core/test_loop_retry.py`
- `tests/kernel/core/test_run_result.py`

Implemented behavior:

- terminal statuses: `completed`, `budget_exhausted`, `interrupted`, `fatal_error`
- `RunResult.reason` mirrors the final `run_finished` Event reason
- provider retry with bounded exponential backoff
- injected sleeper for fast deterministic tests
- step and tool-call budgets
- cooperative interrupt checks
- single tool dispatch call site
- tool result messages written back to model context
- resume from `prior_events`
- terminal logs are read-only
- unsafe resume with in-flight tool calls fails fast
- no Event type beyond the one approved `context_compressed` addition

Completion: core v1 complete.

#### S4 Tools and Permissions

Goal: build the explicit tool registry and permission enforcement layer.

Completed artifacts:

- `docs/S4_TOOLS_DESIGN.md`
- `docs/S4_TOOLS_DECISIONS.md`
- `kernel/core/registry.py`
- `kernel/tools/bash.py`
- `tests/kernel/core/test_registry.py`
- `tests/kernel/core/test_permissions.py`
- `tests/tools/test_bash.py`

Implemented behavior:

- explicit `ToolRegistry` and per-run `RunToolDispatcher`
- Draft 2020-12 JSON Schema registration and call validation
- deny-by-default enforcement for seven composable permission flags
- ambient READ with explicit grants for all other permissions
- per-tool secondary authorization for DESTRUCTIVE calls
- WRITE workspace-root containment
- structured ToolResult denials without changing the S2/S3 Event contract
- real unrestricted Bash tool and filesystem canary tests

Completion: core v1 complete.

#### S5 Context and Persistence

Goal: define context-window policy and durable replay/resume behavior.

Completed artifacts:

- `docs/S5_CONTEXT_DECISIONS.md`
- `kernel/core/context.py`
- `kernel/adapters/jsonl_session.py`
- context pinning, load-bearing, and session round-trip tests

Implemented behavior:

- `ContextView`, `FullHistory`, and `TailWithSummary`
- verbatim pinned Messages and the `context_budget_exceeded` fatal path
- loop-only `context_compressed` Event emission
- rolling compression de-duplication and reuse on resume
- append-only JSONL prefix/suffix saves with strict load validation
- Event-only persistence without AgentState or real PermissionGrant storage

Completion: core policy and JSONL adapter v1 complete.

#### S6 Observability and Replay

Goal: make runs inspectable, replayable, and debuggable.

Completed artifacts:

- `docs/S6_OBSERVABILITY_DECISIONS.md`
- `docs/S6_DETERMINISM_AUDIT.md`
- `kernel/providers/replay.py`
- `kernel/trace/__main__.py`
- replay identity, divergence, and trace CLI tests

Implemented behavior:

- complete kernel-native provider request/response Events
- `ReplayProvider` with field-level `ReplayDivergence`
- deterministic Event IDs and original run ID replay
- human-readable, verbose, and structural-diff trace CLI
- old S5 logs remain traceable and are explicitly not replayable

Completion: S6 v1 complete.

#### S7 Provider Adapters

Goal: connect the kernel to real LLM providers and agent frameworks without polluting core contracts.

Planned adapter targets include:

- OpenAI
- Anthropic
- Gemini
- Qwen
- DeepSeek
- Kimi
- GLM
- Baichuan
- MiniMax
- StepFun
- Ollama
- vLLM

Completion: not started.

### Repository Layout

```text
docs/
  INVARIANTS.md
  NON_GOALS.md
  S2_ABSTRACTIONS_DECISIONS.md
  S3_LOOP_DECISIONS.md

kernel/
  core/
    types.py
    loop.py
    registry.py
  tools/
    bash.py

tests/
  kernel/
    core/
      test_loop_*.py
      test_run_result.py
      test_registry.py
      test_permissions.py
  tools/
    test_bash.py
```

### License

No license has been selected yet.

Before making the repository public, choose a license intentionally. If unsure:

- MIT is simple and permissive.
- Apache-2.0 is permissive and includes an explicit patent grant.
- Keep it private until reuse rights are clear.
