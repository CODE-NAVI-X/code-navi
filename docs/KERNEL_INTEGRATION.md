# Kernel 集成规范

## 依赖来源

本仓库依赖私有仓库 `Dlalmlurn/code-navi-kernel`，当前固定到提交：

```text
77e7c9e1898f94c42d1fbfcd7bb393a6ce1cb481
```

固定完整 SHA 是为了保证安装与 CI 可复现。在 kernel 发布稳定版本标签后，可通过独立 PR 改为固定版本范围。

## 允许的接入面

领域 Agent 使用 `kernel.runtime.AgentSpec`。应用执行使用 `AgentRuntime` 和 `RuntimeRequest`；测试优先使用 `MockProvider`。本仓库不得直接调用 `kernel.core.run()`、复制执行循环或依赖未公开的实现细节。

```python
from code_navi import student_tutor_agent
from kernel.core import ContentBlock, Message, ProviderResult
from kernel.providers import MockProvider
from kernel.runtime import AgentRuntime, RuntimeRequest

provider = MockProvider(
    [ProviderResult(Message("assistant", (ContentBlock("text", {"text": "下一步"}),)))]
)
result = AgentRuntime(provider).run(
    student_tutor_agent,
    RuntimeRequest("如何开始分析这道题？"),
)
```

## 工具与权限

- 工具由应用宿主显式注册，并按 `AgentSpec.tool_names` 精确暴露。
- 每次 run 创建独立的授权和 dispatcher，不跨 run 复用权限。
- 写入、执行、网络、发布和破坏性操作必须在应用层提供明确确认与失败处理。
- 领域提示不得暗示 Agent 拥有未注册或未授权的工具。

## Event 与持久化

Event 是一次运行的审计事实。应用可以展示、持久化或关联 Event，但不能改写其语义。`session_id` 只用于应用归类时，不应被误当作自动恢复了跨运行对话或权限。

## 升级流程

1. 在独立分支中修改 `pyproject.toml` 的 kernel SHA。
2. 阅读目标区间的 kernel 提交与契约变更。
3. 重新安装依赖并执行 `ruff check .`、`pytest`、`python -m build`。
4. 至少运行一次三个内置 Agent 的 MockProvider 集成测试。
5. 若公开类型、Event、权限或 Provider 行为变化，同步更新本文件、架构文档和相关测试。
6. PR 中记录旧 SHA、新 SHA、兼容性结论和回滚 SHA。

如果升级要求本仓库复制 kernel 代码、导入私有模块或改变应用不变量，应暂停升级并先在 kernel 仓库解决契约问题。
