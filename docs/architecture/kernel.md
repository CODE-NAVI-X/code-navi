# Kernel 内部结构与维护

应用侧 Runtime、Provider、工具和 Event 接口统一见 [system.md](system.md)。本文件只说明 `src/kernel/` 的来源、内部归属和修改流程。

## 1. 来源

Kernel 初始内容来自 `Dlalmlurn/code-navi-kernel` 提交 `77e7c9e1898f94c42d1fbfcd7bb393a6ce1cb481`，已于 2026-07-18 并入当前仓库。安装、测试和运行不得依赖旧私有仓库或外部 Kernel 包。

## 2. 内部目录

| 路径 | 职责 |
| --- | --- |
| `src/kernel/core/` | 执行循环、基础类型、Provider 协议、工具注册和权限判断 |
| `src/kernel/runtime/` | `AgentSpec`、`AgentRuntime`、Runtime 请求结果和 Event 保存 |
| `src/kernel/adapters/` | JSONL、OpenAI Responses 与 Chat Completions 适配 |
| `src/kernel/providers/` | Mock 与 Replay Provider |
| `src/kernel/tools/` | 通用工具实现；存在不表示产品已经注册或授权 |
| `src/kernel/trace/` | Event trace 命令与展示 |

`core/` 不导入供应商 SDK、`code_navi`、前端、CLI 或业务配置。产品提示、Workflow、数据库模型和页面状态留在应用层。

`RuntimeRequest` 可携带显式 `conversation_history`；Kernel 不按 `session_id` 读取业务历史。Runtime 只负责将 system、Host 提供的历史和当前 user 交给执行循环，业务会话恢复、摘要边界与持久化压缩仍属于 Host。

## 3. 修改与验证

只有公开接口已经复现出能力缺口时才修改 Kernel：

1. 用现有 Runtime 或工具接口复现缺口；
2. 将 Kernel 契约变更与产品功能、前端和目录迁移分开；
3. 更新对应 `tests/kernel/` 测试和至少一个应用接线测试；
4. 先运行受影响测试与 Ruff，合并前运行完整 `pytest` 和 `python -m build`；
5. 公开语义变化时更新 [system.md](system.md) 并说明迁移影响。

## 4. 旧仓库同步

同步旧仓库时，以来源提交为基点比较目标差异，只移植经过评审的部分。不得覆盖当前实现，也不自动带入旧打包配置、重复 README 或旧领域兼容代码。
