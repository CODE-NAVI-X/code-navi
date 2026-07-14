# P0 内核集成指南

## 目的与边界

本指南约束助学、助教、助研三组如何接入现有单 Agent 运行时。P0 的接入点是 `kernel.runtime`，不是 `kernel.core`。三组可以定义领域 Agent、准备请求、选择经批准的工具，并消费结果；不得修改 `kernel/core`，不得直接调用 `kernel.core.run()` 或自行复制执行循环。

当前三组目录如下：

- 助学组：`domains/student/`，维护面向学生的 Agent 定义。
- 助教组：`domains/teacher/`，维护面向教师的 Agent 定义。
- 助研组：`domains/research/`，维护面向科研辅导的 Agent 定义。

领域代码只放业务名称、系统提示、输出约定和获准的工具名称。平台接入、界面、真实模型 SDK、工具实现、权限确认和业务编排不属于 `kernel/core`，也不应借修改内核实现。

## 三组统一调用方式

三组都按同一接口导入并调用：

```python
from kernel.runtime import AgentRuntime, AgentSpec, RuntimeRequest

runtime = AgentRuntime(
    provider,
    dispatcher_factory=None,
    context_policy=None,
    context_budget_tokens=None,
    session_dir=None,
    default_config=None,
)
result = runtime.run(agent, request, config=None, interrupt_check=None)
```

`AgentSpec` 是领域拥有的声明，至少应明确名称、用途、系统提示和输出格式；仅在确有需要时声明工具名称。`RuntimeRequest` 是一次运行的输入，包含 `user_input`，可选 `session_id`、`run_id` 与 JSON 可序列化的 `metadata`。三组分别使用已有的 `student_tutor_agent`、`teacher_assistant_agent`、`research_coach_agent`，或在各自目录中以相同形式新增领域 Agent。

建议按下列顺序接入：

1. 在本组 `domains/<组名>/agents.py` 定义或调整 `AgentSpec`，使系统提示只描述本组职责与可验证的输出要求。
2. 在本组的宿主或应用层构造一个 `Provider` 实现和 `AgentRuntime`；无工具 Agent 不需要 `dispatcher_factory`。
3. 用 `RuntimeRequest` 发起一次 `runtime.run(...)`，读取 `RuntimeResult.output_text`、`events`、`run_result` 和可选的 `event_log_path`。
4. 需要工具时，先显式注册、按 Agent 的 `tool_names` 精确筛选，再在每次运行中生成新的授权和 dispatcher。

### 可复制的最小 MockProvider 示例

以下示例不依赖真实模型服务，适合三组先验证自己的 `AgentSpec` 和运行接入。它使用当前可用的 `MockProvider`、`ProviderResult`、`Message` 与 `ContentBlock`。

```python
from kernel.core import ContentBlock, Message, ProviderResult
from kernel.providers import MockProvider
from kernel.runtime import AgentRuntime, AgentSpec, RuntimeRequest

agent = AgentSpec(
    name="student_p0_demo",
    description="验证助学 Agent 的最小运行接入。",
    system_prompt="你是助学辅导员。以清晰步骤回答，不编造事实。",
    output_format="markdown",
)
provider = MockProvider(
    [
        ProviderResult(
            Message(
                "assistant",
                (ContentBlock("text", {"text": "请先写出已知条件，再完成下一步。"}),),
            )
        )
    ]
)

runtime = AgentRuntime(provider, session_dir="var/sessions")
result = runtime.run(
    agent,
    RuntimeRequest(
        user_input="如何开始分析一道算法题？",
        session_id="student-demo",
        run_id="run-001",
    ),
)
print(result.output_text)
print(result.event_log_path)
```

助教组和助研组仅替换 `agent` 的领域定义以及 `user_input`；运行时调用保持不变。上例的静态响应仅用于接线验证，不能代表模型能力或完整业务效果。

## 有工具时的明确注册与按需绑定

工具不是由目录扫描、装饰器或模型自发现得到的。工具实现由宿主显式登记到 `ToolRegistry`。`dispatcher_factory` 的签名为 `(run_id, tool_names) -> ToolDispatcher`；运行时会要求 `provider_tools()` 返回的名称和顺序与 `AgentSpec.tool_names` 完全一致。

下面的示例以只读检索工具说明正确的工厂形式。`TOOL_DEFINITIONS` 是宿主可审核的工具白名单，工厂只登记本次 Agent 声明的名称，并在每次调用时创建新的 `PermissionGrant` 和 `ToolExecutionContext` 后使用 `ToolRegistry.bind(...)`。因此授权不会跨运行复用。

```python
from collections.abc import Mapping

from kernel.core import (
    PermissionGrant,
    ToolExecutionContext,
    ToolPermission,
    ToolRegistry,
    ToolSpec,
)
from kernel.runtime import AgentRuntime, AgentSpec, RuntimeRequest


def lookup_reference(args: Mapping[str, object], context: ToolExecutionContext) -> dict:
    query = str(args["query"])
    return {"query": query, "items": []}


TOOL_DEFINITIONS = {
    "lookup_reference": (
        ToolSpec(
            name="lookup_reference",
            description="在已批准的资料索引中查找关键词。",
            args_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
            required_permissions=frozenset({ToolPermission.READ}),
        ),
        lookup_reference,
    )
}


def dispatcher_factory(run_id: str, tool_names: tuple[str, ...]):
    registry = ToolRegistry()
    for name in tool_names:
        try:
            spec, handler = TOOL_DEFINITIONS[name]
        except KeyError as exc:
            raise ValueError(f"未批准的工具：{name}") from exc
        registry.register(spec, handler)
    registry.freeze()

    # 每次 factory 调用均创建本 run 专属授权和执行上下文。
    grant = PermissionGrant(
        run_scope=run_id,
        allowed_permissions=frozenset({ToolPermission.READ}),
    )
    context = ToolExecutionContext(run_scope=run_id)
    return registry.bind(grant, context)


agent = AgentSpec(
    name="research_reference_helper",
    description="辅助梳理已有资料。",
    system_prompt="你是助研辅导员；仅依据工具返回内容概括，并标明证据缺口。",
    tool_names=("lookup_reference",),
    output_format="markdown",
)
runtime = AgentRuntime(provider, dispatcher_factory=dispatcher_factory)
result = runtime.run(agent, RuntimeRequest("请查找强化学习的入门资料。"))
```

工具规则如下：

- 每一个工具必须先通过 `ToolRegistry.register(spec, handler)` 显式注册；参数模式必须是 JSON Schema 对象。
- `AgentSpec.tool_names` 是该 Agent 的精确工具清单，不得把整个注册表无差别暴露给模型，也不得改变其声明顺序。
- `agent.tool_names` 非空而没有 `dispatcher_factory` 会被拒绝；空工具 Agent 可以不提供工厂。
- 工厂必须在每个 `run_id` 上重新创建 `PermissionGrant`、`ToolExecutionContext` 和绑定后的 dispatcher。不得把授权、绑定 dispatcher 或破坏性工具许可缓存到下一次运行。
- 注册和绑定本身不扩大权限。读取权限可用；写入、破坏性操作及工作区范围必须按 `ToolSpec` 与本 run 的 `PermissionGrant` 明确配置。遇到不确定的操作，先按更高风险处理并让宿主决定是否授权。

## Event、JSONL 与追踪

运行结果中的 `events` 是本次执行的可审计事实。设置 `session_dir` 后，`AgentRuntime.run()` 会将这一次运行的 Event 写为 JSONL：

- 指定 `session_id`：`<session_dir>/<session_id>/<run_id>.jsonl`
- 未指定 `session_id`：`<session_dir>/<run_id>.jsonl`

一个 JSONL 文件只对应一个 `run_id`。`session_id` 仅用于目录归类；它不表示跨运行的对话恢复，也不会恢复旧运行中的工具授权。不要把多个运行追加为同一文件或把该文件当作多轮会话数据库。

可用以下命令查看一次运行的轨迹：

```bash
python -m kernel.trace <path>
```

需要查看完整载荷时可加 `--verbose`；需要比较两次运行时可使用 `python -m kernel.trace --diff <左侧路径> <右侧路径>`。Event 和 JSONL 适用于追踪、审计与调试；业务方应保留必要的输入标识，且不要将密钥或未获授权的敏感内容写入请求元数据。

## P0 明确不包含

P0 只提供可由三组复用的单 Agent 运行接入和最小领域声明，不等同于完整产品。下列事项不作为 P0 已完成能力：

- 完整助学、助教或助研业务流程，以及课程、作业、科研数据的生产接入；
- Web 界面、账户体系、课堂协作界面或消息平台接入；
- 已验证可用的真实模型在线服务；
- 多 Agent 编排、自动课堂协同或跨运行的对话恢复；
- 在 `kernel/core` 中加入教学策略、提示词、RAG、工具业务逻辑或确认界面。

若后续需求需要这些能力，应在领域层或应用层提出独立设计与验收标准，并继续通过 `AgentRuntime` 接入内核。
