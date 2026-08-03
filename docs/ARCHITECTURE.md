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

## 当前科研澄清请求路径

1. Web 宿主通过 `/api/v1/research/conversations` 接收自由文本，并在应用数据库创建或恢复 `research_conversations` 记录。
2. `ResearchConversationService` 只把当前动态画像、最近 12 条消息和本轮输入装配为受限上下文；用户内容被标记为待分析数据。
3. 显式配置在线 Provider 时，`RuntimeConversationDecisionGenerator` 通过公开 `AgentRuntime` 运行无工具权限的 `research_conversation_agent`。
4. 模型只能返回 `ResearchConversationDecision`；Pydantic 校验后，应用层 reducer 才能修改画像。失败或无 Provider 时使用不伪造事实的确定性降级规则。
5. 本地开发密钥可由 CLI 隐藏输入，或由仅接受回环地址请求的 Web 配置入口一次性提交；服务端校验后原子写入 Git 已忽略的 `.code-navi/provider.env` 并立即激活。响应永不返回密钥，浏览器不持久化密钥。部署环境继续使用宿主环境变量或外部密钥管理，并不得直接暴露本地配置入口。
6. `research_conversation_agent` 直接加载随包交付的 `research-clarification` Skill。模型负责自适应澄清，应用层强制执行不重复建议题和显式检索交接；`academic-search` 只能在 `next_skill` 明确后由后续用户动作触发。
7. 应用层把画像、消息以及 Kernel `run_id` 等必要关联写回 SQLite；GET 恢复不会重新运行 Agent。
8. 澄清 Agent 不具备网络工具。论文检索仍是用户显式触发、独立授权的后续能力。

## 当前受限学术检索请求路径

1. `GET /api/v1/research/conversations/{id}/search-plan` 只从已校验的科研画像生成查询词和来源清单，不读取原始整句聊天文本，也不联网。
2. 用户在页面检查查询词并勾选 OpenAlex、Crossref、arXiv；只有显式 POST EvidenceBundle 才授予本次 `READ + NETWORK` Tool 调用。
3. `AcademicSearchTool` 对 allow-list 来源并行请求；来源各自处理超时、网络错误和禁用状态，单源失败不丢弃其他来源结果。
4. 应用层去重论文并保存包含来源状态、耗时、访问时间和事实边界的 `research_evidence_bundles` 记录。
5. 相同会话、规范化查询词和相同来源组合在 TTL 内复用持久化缓存；GET 恢复证据只读 SQLite，不联网。

旧 `/api/v1/research/sessions` 五字段流程暂时作为学生端兼容层保留，不是新能力的依赖。前端迁移、旧数据处理和接口弃用应分阶段完成。

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
| `src/code_navi/paths.py` | 跨平台解析项目数据目录与绝对 SQLite URL |
| `src/code_navi/cli.py` | 命令、交互焦点、展示与退出码 |
| `src/code_navi/research/conversation_*.py` | 对话式科研澄清声明、契约与应用层持久化编排 |
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
