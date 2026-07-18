# Kernel 集成规范

## 来源与目录

`src/kernel/` 初始内容来自原私有仓库 `Dlalmlurn/code-navi-kernel`：

```text
77e7c9e1898f94c42d1fbfcd7bb393a6ce1cb481
```

该提交的运行时源码和 kernel 测试已在 2026-07-18 并入当前仓库。原仓库当时没有独立许可证文件；本次整合由同一项目所有者批准。旧仓库的独立打包配置、重复 README 和旧领域兼容包不属于运行时，因此没有并入。

## 代码边界

- `src/kernel/` 保持平台无关，不导入 `code_navi`、CLI、产品提示或业务配置。
- 助手声明使用 `kernel.runtime.AgentSpec`。
- 应用执行使用 `AgentRuntime` 和 `RuntimeRequest`，不直接绕过 Runtime 驱动执行循环。
- 在线模式使用 `kernel.adapters.openai.OpenAIResponsesAdapter`，模型、密钥和 Provider 选择由应用宿主校验。
- Kernel core 不导入 OpenAI SDK；SDK 只允许出现在 adapter 层。

## 工具与权限

- 工具由应用宿主显式注册，并按 `AgentSpec.tool_names` 精确暴露。
- 每次 run 创建独立授权和 dispatcher，不跨 run 复用权限。
- 写入、执行、网络、发布和破坏性操作必须在应用层提供明确确认与失败处理。
- 领域提示不得暗示 Agent 拥有未注册或未授权的工具。

## Event 与持久化

Event 是一次运行的审计事实。应用可以展示、持久化或关联 Event，但不能改写其语义。`session_id` 只用于应用归类，不表示自动恢复了跨运行对话或权限。

CLI 的问题分支由应用在当前进程内保存受限问答，并将其作为下一次 `RuntimeRequest` 的参考数据。每个问题仍是独立 run；该行为不扩展 kernel 的 session 或 resume 语义。

## 维护流程

修改 `src/kernel/` 时：

1. 将 kernel 契约变更与产品功能变更分开提交。
2. 更新相关 core、runtime、adapter 或权限测试。
3. 执行 `ruff check .`、`pytest` 和 `python -m build`。
4. 若公开类型、Event、权限或 Provider 行为变化，同步更新架构和本文件。
5. PR 中说明兼容性、Event 迁移风险和回滚方式。

若需要从旧仓库同步后续提交，应先比较目标提交与上述来源 SHA，只移植经过评审的差异，不覆盖当前仓库中已经演进的实现。
