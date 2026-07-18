# 架构说明

## 仓库边界

本仓库同时交付两个保持单向依赖的 Python 包：`code_navi` 拥有用户入口、项目上下文、应用用例、后续 Skill/Workflow、工具装配和交付代码；`kernel` 拥有平台无关的单 Agent 执行循环、Event、工具权限、上下文策略和 Provider 契约。

两个包同仓是为了消除私有 Git 构建依赖并简化部署，不代表边界消失。应用运行只通过公开的 `kernel.runtime` 接口；Provider 和持久化使用 kernel 的公开适配器。`kernel` 不得反向导入 `code_navi` 或承载产品业务状态。

## 分层与依赖方向

```text
入口与宿主（CLI / future GUI / service）
                 ↓
应用用例（问题、任务、Skill/Workflow 编排）
                 ↓
上下文与能力策略（ContextSlice / Tool selection / Permission）
                 ↓
通用代码学习 Agent
                 ↓
内置 kernel 公开运行时接口
                 ↓
Provider、工具与持久化适配器
```

依赖只能向下。助手声明不得导入 CLI、Web 或平台 SDK；CLI 不得直接调用 `kernel.core.run()` 绕过 `AgentRuntime`；Provider 原生对象不得成为应用数据模型。

## 当前 CLI 请求路径

1. CLI 从显式 `--project` 或当前目录发现项目根目录。
2. `ContextBuilder` 读取可选任务摘要和 README，并解析显式文件片段、`@last` 与问题分支历史。
3. `ContextSlice` 在字符、行数和项目根目录边界内冻结本轮参考数据。
4. `QuestionService` 将参考数据标记为非指令内容，并创建新的 `RuntimeRequest`。
5. `AgentRuntime` 执行通用助手并将 Event 保存到 run/session 路径。
6. CLI 分离 stdout 回答、stderr 诊断和稳定退出码。

一次快问和问题分支都不会修改项目文件。问题分支只在 CLI 当前进程内维护最近的受限问答；它不是 kernel 会话恢复。

## 工具、Skill 与 Workflow

后续能力应保持三个边界：

| 类型 | 职责 | 调用边界 |
| --- | --- | --- |
| Tool | 原子、确定、带权限的操作 | 通过 kernel ToolRegistry 注册和授权 |
| Skill | 有明确输入输出的可复用业务能力 | 由应用用例调用，可组合 Prompt 与 Tool |
| Workflow | 可暂停、恢复和人工确认的多阶段任务 | 由应用层保存业务状态，不写入 kernel core |

“能力已注册”“本轮向模型暴露”和“用户已授权执行”是三件不同的事。读取、执行、联网、写入、发布和破坏性权限不得因 Agent 建议而自动扩大。

## 目录职责

| 路径 | 职责 |
| --- | --- |
| `src/code_navi/assistant.py` | 通用代码学习 Agent 声明 |
| `src/code_navi/context.py` | 项目发现、任务摘要、文件片段和 ContextSlice |
| `src/code_navi/application.py` | 经 AgentRuntime 完成问题用例 |
| `src/code_navi/providers.py` | 离线和显式在线 Provider 装配 |
| `src/code_navi/cli.py` | 命令、交互焦点、展示与退出码 |
| `src/code_navi/domains/` | 旧领域 Agent 的兼容声明 |
| `src/kernel/` | 平台无关的执行循环、Event、权限、上下文、回放和 Provider 适配器 |
| `examples/` | 最小且可运行的接线示例，不承载生产逻辑 |
| `tests/` | 上下文安全、CLI、领域契约和集成测试 |
| `docs/` | 架构、开发规范、路线图和决策记录 |

## 变更归属判断

- 改变单 Agent 的执行、Event、权限或 Provider 通用语义：在 `src/kernel/` 中独立实现和评审，并运行 kernel 全量测试。
- 改变代码学习提示、项目上下文、Skill 输入输出或业务规则：在本仓库应用层实现。
- 改变命令、界面、身份、人工确认或部署：在本仓库宿主层实现。
- 只服务本产品的工具：由本仓库显式注册，不进入 kernel core。

若需求需要反向依赖、把业务状态写入 Event 语义或把无限制执行作为默认能力，应先记录架构决策。
