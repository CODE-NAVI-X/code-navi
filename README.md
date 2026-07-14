# Code-Navi Agent Kernel

Code-Navi Agent Kernel 是一个小型、平台无关的单 Agent 运行时内核。它的第一个宿主目标是 Code-Navi CLI，但 kernel core 有意不包含 CLI、UI、真实 provider SDK、教学业务逻辑或其他平台相关行为。

本项目按阶段推进。每个 S 阶段先冻结一组很窄的 contract，再进入下一层实现。

### 当前状态

截至 2026-07-14：

- S1 Scope：已完成
- S2 Core abstractions：已完成
- S3 Execution loop：core v1 已完成
- S4 Tools and permissions：已完成
- S5 Context and persistence：已完成
- S6 Observability and replay：已完成
- S7 Provider adapters：OpenAI Responses adapter 已完成 recorded conformance；live smoke 已就绪并默认跳过

验证命令：

```bash
python -m pytest -q
```

当前结果：

```text
112 passed, 1 deselected
```

其中 `live` 测试默认不运行；上面的 `1 deselected` 是需要真实 OpenAI 凭据和显式模型选择的 smoke test。

### 安装与 OpenAI 快速开始

仅安装 kernel：

```bash
python -m pip install -e .
```

启用 OpenAI adapter：

```bash
python -m pip install -e ".[openai]"
```

`OpenAIResponsesAdapter` 使用 Responses API，模型必须由调用方显式传入。adapter 固定发送 `store=False`，并以 `max_retries=0` 创建 SDK client；provider retry 仍只由 kernel loop 管理。

```python
from kernel.adapters.openai import OpenAIResponsesAdapter
from kernel.core import (
    ContentBlock,
    KernelConfig,
    Message,
    PermissionGrant,
    ToolExecutionContext,
    ToolPermission,
    ToolRegistry,
    ToolSpec,
    run,
)

scope = "read-demo"
registry = ToolRegistry()
registry.register(
    ToolSpec(
        "read_value",
        "Read a deterministic demo value.",
        {"type": "object", "additionalProperties": False},
        frozenset({ToolPermission.READ}),
    ),
    lambda args, context: {"value": "hello"},
)
dispatcher = registry.bind(
    PermissionGrant(scope), ToolExecutionContext(scope)
)
provider = OpenAIResponsesAdapter("your-model-id", max_output_tokens=128)

result = run(
    provider,
    dispatcher,
    [
        Message(
            "user",
            (
                ContentBlock(
                    "text",
                    {"text": "Call read_value, then return only its value."},
                ),
            ),
        )
    ],
    KernelConfig(max_steps=2, max_tool_calls=1),
    run_id=scope,
)
```

SDK 会读取 `OPENAI_API_KEY`。recorded conformance 不需要网络或 API key：

```bash
python -m pytest -q tests/kernel/core/test_provider_conformance.py tests/kernel/adapters/test_openai_adapter.py
```

当前结果为 `29 passed`。真实 smoke test 必须显式选择：

```powershell
$env:OPENAI_API_KEY = "..."
$env:OPENAI_LIVE_MODEL = "your-model-id"
python -m pytest -q -m live -o addopts= tests/test_live_smoke.py
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
- `kernel/core/provider.py`
- `kernel/providers/mock.py`
- `kernel/core/__init__.py`
- `tests/kernel/core/test_provider_conformance.py`

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
- `Provider`
- `ProviderTool`
- `ProviderCapabilities`
- `RetryableProviderError`
- `FatalProviderError`

稳定的 JSON round-trippable 类型留在 `types.py`；provider contract 独立在 `provider.py`，测试桩 `MockProvider` 位于 `kernel/providers/mock.py`。

完成度：已完成，并由共享 provider conformance suite 覆盖。

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
- 绑定后的 dispatcher 通过只读 `provider_tools()` 快照仅暴露模型可见的 `name`、`description` 和 `args_schema`
- provider tools 快照不包含 handler、PermissionGrant、workspace roots、destructive grant 或执行上下文

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

已完成产物：

- `docs/S7_ADAPTER_DECISIONS.md`
- `kernel/adapters/openai.py`
- `tests/kernel/core/test_provider_conformance.py`
- `tests/kernel/adapters/test_openai_adapter.py`
- `tests/test_live_smoke.py`

已实现行为：

- kernel-native `Provider` contract，不从 `kernel/core` 导入任何 provider SDK
- loop 将同一份 provider tools 快照写入 `provider_called` Event 并传给 `provider.complete(...)`
- 工具执行唯一入口仍为 `tool_dispatcher.dispatch(call)`，adapter 不并行 dispatch
- OpenAI Responses API、`store=False`、显式 model 和 SDK `max_retries=0`
- 同一响应中的多个 function calls 保序转换为多个 `tool_use` blocks
- 连接、超时、408/409/429 和 5xx 映射为 retryable，其余 SDK API 错误映射为 fatal
- `image_ref`、`artifact_ref` 和未知内容块显式抛出 fatal provider error
- recorded client 覆盖 conformance、JSONL/replay identity 和真实 SDK request/response translation
- `pytest.mark.live` 的两步 READ tool smoke test，默认测试不运行

后续 adapter targets：

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

完成度：OpenAI adapter 的 recorded conformance 已完成；live smoke 实现已完成，需凭据运行。第二个 adapter 尚未开始。

### 仓库结构

```text
docs/
  INVARIANTS.md
  NON_GOALS.md
  S2_ABSTRACTIONS_DECISIONS.md
  S3_LOOP_DECISIONS.md
  S4_TOOLS_DESIGN.md
  S4_TOOLS_DECISIONS.md
  S5_CONTEXT_DECISIONS.md
  S6_OBSERVABILITY_DECISIONS.md
  S6_DETERMINISM_AUDIT.md
  S7_ADAPTER_DECISIONS.md

kernel/
  core/
    types.py
    provider.py
    loop.py
    registry.py
    context.py
  adapters/
    jsonl_session.py
    openai.py
  providers/
    mock.py
    replay.py
  tools/
    bash.py
  trace/
    __main__.py

tests/
  adapters/
    test_openai_adapter.py
  kernel/
    core/
      test_loop_*.py
      test_provider_conformance.py
      test_run_result.py
      test_registry.py
      test_permissions.py
  tools/
    test_bash.py
  test_live_smoke.py
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
- S2 Core abstractions: complete
- S3 Execution loop: core v1 complete
- S4 Tools and permissions: complete
- S5 Context and persistence: complete
- S6 observability and replay: complete
- S7 Provider adapters: OpenAI Responses adapter complete in recorded conformance; live smoke ready and excluded by default

Validation:

```bash
python -m pytest -q
```

Current result:

```text
112 passed, 1 deselected
```

The `live` marker is excluded from default runs. The single deselected test is the OpenAI smoke test, which requires real credentials and an explicitly selected model.

### Installation and OpenAI Quick Start

Install only the kernel:

```bash
python -m pip install -e .
```

Enable the OpenAI adapter:

```bash
python -m pip install -e ".[openai]"
```

`OpenAIResponsesAdapter` uses the Responses API and requires the caller to provide a model explicitly. The adapter always sends `store=False` and creates its SDK client with `max_retries=0`; provider retries remain exclusively owned by the kernel loop.

```python
from kernel.adapters.openai import OpenAIResponsesAdapter
from kernel.core import (
    ContentBlock,
    KernelConfig,
    Message,
    PermissionGrant,
    ToolExecutionContext,
    ToolPermission,
    ToolRegistry,
    ToolSpec,
    run,
)

scope = "read-demo"
registry = ToolRegistry()
registry.register(
    ToolSpec(
        "read_value",
        "Read a deterministic demo value.",
        {"type": "object", "additionalProperties": False},
        frozenset({ToolPermission.READ}),
    ),
    lambda args, context: {"value": "hello"},
)
dispatcher = registry.bind(
    PermissionGrant(scope), ToolExecutionContext(scope)
)
provider = OpenAIResponsesAdapter("your-model-id", max_output_tokens=128)

result = run(
    provider,
    dispatcher,
    [
        Message(
            "user",
            (
                ContentBlock(
                    "text",
                    {"text": "Call read_value, then return only its value."},
                ),
            ),
        )
    ],
    KernelConfig(max_steps=2, max_tool_calls=1),
    run_id=scope,
)
```

The SDK reads `OPENAI_API_KEY`. Recorded conformance requires neither network access nor an API key:

```bash
python -m pytest -q tests/kernel/core/test_provider_conformance.py tests/kernel/adapters/test_openai_adapter.py
```

The current result is `29 passed`. The real smoke test must be selected explicitly:

```powershell
$env:OPENAI_API_KEY = "..."
$env:OPENAI_LIVE_MODEL = "your-model-id"
python -m pytest -q -m live -o addopts= tests/test_live_smoke.py
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
- `kernel/core/provider.py`
- `kernel/providers/mock.py`
- `kernel/core/__init__.py`
- `tests/kernel/core/test_provider_conformance.py`

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
- `Provider`
- `ProviderTool`
- `ProviderCapabilities`
- `RetryableProviderError`
- `FatalProviderError`

Stable JSON round-trippable types remain in `types.py`; the provider contract lives in `provider.py`, and the `MockProvider` test double lives in `kernel/providers/mock.py`.

Completion: complete, with coverage from the shared provider conformance suite.

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
- a bound dispatcher's read-only `provider_tools()` snapshot exposes only model-visible `name`, `description`, and `args_schema`
- provider tool snapshots never contain handlers, PermissionGrant data, workspace roots, destructive grants, or execution context

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

Completed artifacts:

- `docs/S7_ADAPTER_DECISIONS.md`
- `kernel/adapters/openai.py`
- `tests/kernel/core/test_provider_conformance.py`
- `tests/kernel/adapters/test_openai_adapter.py`
- `tests/test_live_smoke.py`

Implemented behavior:

- a kernel-native `Provider` contract with no provider SDK imports under `kernel/core`
- the loop records and passes the exact same provider-tools snapshot in `provider_called` and `provider.complete(...)`
- `tool_dispatcher.dispatch(call)` remains the only execution boundary; adapters never parallel-dispatch calls
- OpenAI Responses API with `store=False`, explicit model selection, and SDK `max_retries=0`
- ordered conversion of multiple function calls in one response into multiple `tool_use` blocks
- connection, timeout, 408/409/429, and 5xx failures mapped to retryable; other SDK API errors mapped to fatal
- explicit fatal errors for `image_ref`, `artifact_ref`, and unknown content blocks
- recorded-client coverage for conformance, JSONL/replay identity, and real SDK request/response translation
- an opt-in `pytest.mark.live` two-step READ-tool smoke test

Future adapter targets include:

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

Completion: OpenAI recorded conformance is complete. The live smoke implementation is complete and awaits credentials when run; adapter #2 has not started.

### Repository Layout

```text
docs/
  INVARIANTS.md
  NON_GOALS.md
  S2_ABSTRACTIONS_DECISIONS.md
  S3_LOOP_DECISIONS.md
  S4_TOOLS_DESIGN.md
  S4_TOOLS_DECISIONS.md
  S5_CONTEXT_DECISIONS.md
  S6_OBSERVABILITY_DECISIONS.md
  S6_DETERMINISM_AUDIT.md
  S7_ADAPTER_DECISIONS.md

kernel/
  core/
    types.py
    provider.py
    loop.py
    registry.py
    context.py
  adapters/
    jsonl_session.py
    openai.py
  providers/
    mock.py
    replay.py
  tools/
    bash.py
  trace/
    __main__.py

tests/
  adapters/
    test_openai_adapter.py
  kernel/
    core/
      test_loop_*.py
      test_provider_conformance.py
      test_run_result.py
      test_registry.py
      test_permissions.py
  tools/
    test_bash.py
  test_live_smoke.py
```

### License

No license has been selected yet.

Before making the repository public, choose a license intentionally. If unsure:

- MIT is simple and permissive.
- Apache-2.0 is permissive and includes an explicit patent grant.
- Keep it private until reuse rights are clear.
