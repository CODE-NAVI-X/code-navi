# 公共架构、接口与系统边界

## 1. 当前结构

```text
Next Web ─→ FastAPI routers ─→ learning / research services
                                      ├─→ AgentRuntime ─→ Provider ─→ Event JSONL
                                      ├─→ ToolRegistry ─→ academic sources
                                      └─→ SQLAlchemy ─→ business database

CLI ─→ QuestionService ─→ AgentRuntime ─→ Provider ─→ Event JSONL
```

`src/code_navi/` 负责产品入口、业务规则、Provider 选择和持久化接线；`src/kernel/` 提供平台无关的 Runtime、Event、Provider 与工具权限契约。依赖只能向下：前端调用 HTTP API，应用调用 Kernel 公开接口，Kernel 不导入产品或界面代码。

## 2. 实际目录职责

| 路径 | 当前职责 |
| --- | --- |
| `src/code_navi/cli.py`、`application.py`、`context.py`、`assistant.py` | CLI 入口、上下文装配和学习问答用例 |
| `src/code_navi/server.py` | FastAPI 装配、CORS、统一异常边界和 `/health` |
| `src/code_navi/learning/` | 知识讲解 API、Runtime 编排和学习笔记 |
| `src/code_navi/research/` | 动态科研对话、Provider 状态、兼容澄清流程、检索计划和学术证据 |
| `src/code_navi/providers.py` | Mock、OpenAI 与 DeepSeek Provider 的统一选择 |
| `src/code_navi/db.py` | 所有业务模块共享的 SQLAlchemy Base、engine 和 session |
| `src/code_navi/domains/` | 旧领域接口兼容；新业务优先进入实际模块 |
| `src/kernel/` | Runtime、Event、Provider 契约、工具注册与运行级授权 |
| `frontend/` | Next Web 宿主和浏览器侧临时状态 |
| `migrations/` | Alembic schema 演进 |
| `tests/` | Kernel、CLI、API、迁移、Provider、科研工具与前端契约验证 |

不要按尚不存在的 `modules/`、`workflows/`、`skills/`、`hosts/` 或 `adapters/` 目录实现功能。只有真实职责冲突已经出现时才迁移目录，并把迁移与无关功能分开。

## 3. 宿主与业务接口

请求和响应模型以 `src/code_navi/learning/schemas.py` 以及科研目录中的 `conversation_schemas.py`、`provider_schemas.py`、`schemas.py` 为准；前端类型镜像这些模型。

| 入口 | 输入 | 输出与副作用 |
| --- | --- | --- |
| `code-navi ask`、`code-navi shell` | 问题、项目上下文、Provider 配置 | `RuntimeResult` 和 Event JSONL；不修改项目文件 |
| `POST /api/v1/learning/explain` | `ExplainRequest` | `ExplainResponse`、Runtime Event，并写入 `notebook_items` |
| `GET /api/v1/learning/notebook?session_id=...` | 学习 `session_id` | 该学习会话的 `NotebookItem` 列表 |
| `POST /api/v1/learning/presentations/generate` | 知识点、学习 `session_id`、风格 | SSE 逐页返回演示文稿、生成来源并归档 |
| `GET /api/v1/learning/presentations/{presentation_id}?session_id=...` | 演示文稿 id 与学习 `session_id` | 只返回该学习会话内的已归档演示文稿 |
| `POST /api/v1/research/conversations` | `CreateResearchConversationRequest` | 新的 `ResearchConversationResponse` |
| `POST /api/v1/research/conversations/{conversation_id}/messages` | 自由文本 | 更新画像、消息与下一步；达到准备度时附带规则生成的 `research_plan` |
| `GET /api/v1/research/conversations/{conversation_id}` | `conversation_id` | 已持久化的动态对话，并按当前画像恢复相同规则研究计划 |
| `POST /api/v1/research/conversations/{conversation_id}/topic-difficulty-analysis` | `user_confirmed: true` | 显式触发的难点个性化结果及 Runtime run 标识 |
| `POST /api/v1/research/conversations/{conversation_id}/experiment-design` | `user_confirmed: true` | 显式触发的实验方案个性化结果及 Runtime run 标识 |
| `POST /api/v1/research/conversations/{conversation_id}/experiment-code-draft` | 明确确认仅预览 | 服务端固定代码模板；模型只可补充建议性元数据 |
| `GET /api/v1/research/conversations/{conversation_id}/search-plan` | `conversation_id` | 不联网的 `ResearchSearchPlan` |
| `POST /api/v1/research/conversations/{conversation_id}/evidence-bundles` | 用户确认、查询和允许来源 | OpenAlex、Crossref、arXiv 元数据与摘要组成的 `ConversationEvidenceBundle` |
| `GET /api/v1/research/conversations/{conversation_id}/evidence-bundles` | `conversation_id` | 已保存的 evidence bundle 列表，不触发联网 |
| `GET /api/v1/research/provider/status` | 无 | 不含密钥的 `ProviderStatusResponse` |
| `PUT /api/v1/research/provider/configuration`、`POST /api/v1/research/provider/test` | 本机显式配置或测试 | 默认禁用且仅允许 loopback 的 Provider 状态或测试结果 |
| `/api/v1/research/sessions...` | 原五字段 session 请求 | 兼容 `ResearchSessionResponse` 和 legacy evidence bundle |
| `GET /health` | 无 | FastAPI 进程存活状态，不检查数据库或外部依赖 |

请求 schema 不合法返回 422；科研对话或兼容会话不存在返回 404；画像尚未达到检索条件时返回 409；未处理异常返回不暴露内部细节的 500 和 `error_id`。调用方不得把这些状态映射为成功或空结果。

动态研究画像维护主题、动机、问题、上下文、方法、数据需求、证据偏好、时间范围、限制、预期产出、假设和不确定性，并以 `research-conversation.v1` 返回。画像达到计划准备度后，纯规则生成器派生 `research-plan.v1`；它不调用模型或网络，只使用已校验画像，结构化条目只允许 `inference` 或 `to_verify`。检索计划和证据分别使用 `research-search-plan.v1`、`academic-evidence.v1`。原五字段规则只属于兼容流程；这些业务状态都不进入 Kernel 契约。

## 4. Runtime、Provider 与工具接口

### Runtime

标准 Agent 调用为：

```text
AgentSpec + RuntimeRequest
          ↓ AgentRuntime.run(...)
RuntimeResult + Event JSONL
```

动态科研对话、显式触发的研究产物个性化和 Provider 连接测试使用该接口，均不授予工具权限；模型不可用或结构无效时回退到规则。对话 reducer 完成画像校验后，`research-plan.v1` 由应用规则派生，不产生新的 Agent run，也不访问 Provider 或网络。个性化结果返回 `run_id` 与 `event_count`，对应 Event JSONL。兼容五字段流程仍通过统一 Provider 契约调用 `complete()`；超时由供应商 SDK 传输层配置，不启动后台守护线程。

### Provider

应用通过 `create_provider(ProviderSettings)` 获得 Kernel-compatible Provider；Provider 接收 `messages` 与可选工具描述并返回 `ProviderResult`。供应商 SDK、原生错误和配置不得进入业务接口。

### 工具

```text
ToolSpec → ToolRegistry.register(...)
         → bind(PermissionGrant, ToolExecutionContext)
         → RunToolDispatcher.dispatch(ToolCall)
         → ToolResult
```

grant 和 execution context 每次调用独立创建，权限不因页面、业务标识或上下文传递而继承。当前科研 evidence bundle 注册 `academic_search`，仅授予 `READ + NETWORK`，且必须在用户确认后调用。`ProviderResult` 是模型输出；外部操作状态以 `ToolResult` 或对应执行器结果为准。

## 5. 会话与持久化接口

| 标识 | 作用 | 不代表什么 |
| --- | --- | --- |
| Runtime `session_id` | 组织同一来源的 Event JSONL | 业务状态、身份或自动恢复的对话 |
| 学习 `session_id` | 隔离 `notebook_items` 并关联学习 run | 用户账号或跨设备会话 |
| 科研 `conversation_id` | 恢复动态画像、消息和 evidence bundle | Kernel 权限、身份或长期记忆 |
| 兼容科研 `session_id` | 恢复原五字段澄清状态与 turns | 当前科研页面主流程 |

浏览器将学习 `session_id` 和科研 `conversation_id` 存入 `localStorage`，只提供同一浏览器内恢复，不提供身份绑定或授权。

业务模块共用 `code_navi.db.Base`、`get_db()` 和 `CODE_NAVI_DATABASE_URL`；`LEARNING_DATABASE_URL` 仅兼容旧配置。默认数据库为 `.code-navi/learning_poc.db`。当前业务表包括 `notebook_items`、`research_sessions`、`research_conversations` 和 `research_evidence_bundles`。Runtime Event 单独写入 JSONL，不作为业务数据库。

schema 变更必须新增 Alembic revision，并验证空库和受影响旧库升级。当前 `0003` revision 创建动态科研对话和证据表；启动时的 `Base.metadata.create_all()` 只创建缺失表，不能替代迁移。

## 6. 架构变更条件

以下变化需要 ADR 或等价的简短书面决策：

1. 改变主要分层、依赖方向或公开 Runtime、Provider、工具、API 或持久化契约；
2. 引入难以替换的基础依赖、身份系统、正式数据库或生产部署方案；
3. 扩大工具权限或真实外部副作用；
4. 多个独立组件即将并行依赖同一稳定接口。

小型、可逆且不改变外部行为的实现细节留在 PR 中。Kernel 内部维护见 [kernel.md](kernel.md)，前端专属状态见 [frontend.md](frontend.md)，高风险能力见 [高风险能力](../development/high-risk-capabilities.md)。
