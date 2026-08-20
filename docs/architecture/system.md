# 公共架构、接口与系统边界

## 1. 当前结构

```text
Next Web ─→ FastAPI routers ─→ learning / research services
        │                             ├─→ AgentRuntime ─→ Provider ─→ Event JSONL
        │                             ├─→ ToolRegistry ─→ academic sources
        │                             └─→ SQLAlchemy ─→ business database
        └───────────────────→ online compiler service ─→ Piston
                                             ├─→ compiler records SQLite
                                             └─→ optional AgentRuntime guidance

CLI ─→ QuestionService ─→ AgentRuntime ─→ Provider ─→ Event JSONL
```

`src/code_navi/` 负责产品入口、业务规则、Provider 选择和持久化接线；`src/kernel/` 提供平台无关的 Runtime、Event、Provider 与工具权限契约。依赖只能向下：前端调用 HTTP API，应用调用 Kernel 公开接口，Kernel 不导入产品或界面代码。

## 2. 实际目录职责

| 路径 | 当前职责 |
| --- | --- |
| `src/code_navi/cli.py`、`application.py`、`context.py`、`assistant.py`、`cli_conversation.py` | CLI 入口、上下文装配、学习问答和 shell 主对话持久化 |
| `src/code_navi/server.py` | FastAPI 装配、CORS、统一异常边界和 `/health` |
| `src/code_navi/learning/` | 知识讲解 API、Runtime 编排和学习笔记 |
| `src/code_navi/context_transfer/` | 跨模块上下文的来源校验、可编辑快照、会话范围读取、取消和确认消费 |
| `src/code_navi/workspaces/` | 本地 Workspace、Task 与来源派生 Activity 的归属校验、持久化和 API |
| `src/code_navi/online_compiler/` | Python/Piston 接线、服务端判题、规则反馈、可选 AI 指导和匿名学习记录 |
| `src/code_navi/research/` | 动态科研对话、Provider 状态、兼容澄清流程、检索计划和学术证据 |
| `src/code_navi/providers.py` | Mock、OpenAI 与 DeepSeek Provider 的统一选择 |
| `src/code_navi/conversations.py` | Host 之间共享的显式状态加载与上下文装配最小协议；不定义统一存储模型 |
| `src/code_navi/db.py` | 所有业务模块共享的 SQLAlchemy Base、engine 和 session |
| `src/code_navi/domains/` | 旧领域接口兼容；新业务优先进入实际模块 |
| `src/kernel/` | Runtime、Event、Provider 契约、工具注册与运行级授权 |
| `frontend/` | Next Web 宿主和浏览器侧临时状态 |
| `migrations/` | Alembic schema 演进 |
| `tests/` | Kernel、CLI、API、迁移、Provider、科研工具与前端契约验证 |

不要按尚不存在的 `modules/`、`workflows/`、`skills/`、`hosts/` 或 `adapters/` 目录实现功能。只有真实职责冲突已经出现时才迁移目录，并把迁移与无关功能分开。

## 3. 宿主与业务接口

学习与科研请求响应模型以各模块 Pydantic schema 为准；在线编译器当前在应用层手工校验 JSON，并由 `frontend/lib/api/compiler.ts` 镜像公开字段。前端不能绕过模块 API 直接调用 Provider、Piston 或数据库。

| 入口 | 输入 | 输出与副作用 |
| --- | --- | --- |
| `code-navi ask` | 问题、项目上下文、Provider 配置 | 无状态的 `RuntimeResult` 和 Event JSONL；不修改项目文件 |
| `code-navi shell [--resume conversation-id]` | 问题、项目上下文、显式 CLI 对话标识、Provider 配置 | 项目作用域内的主对话状态、`RuntimeResult` 和 Event JSONL；branch 只在当前进程存在 |
| `POST /api/v1/workspaces/personal` | 本地 `local_profile_id` | 幂等取得该浏览器资料的个人 Workspace；它不是身份或授权 |
| `GET`、`POST /api/v1/workspaces...` | 本地 `local_profile_id`、Workspace 数据和资源 ID | 按浏览器资料范围列出、创建或读取 Workspace；跨资料资源统一返回 404 |
| `POST /api/v1/tasks`、`GET /api/v1/tasks...` | 本地 `local_profile_id`、目标、可选 Workspace 和 Task ID | Task-first 自动取得个人 Workspace；Workspace-first 使用同一服务端创建规则 |
| `GET /api/v1/workspaces/{id}/activities`、`GET /api/v1/tasks/{id}/activities` | 资源 ID 与本地 `local_profile_id` | 稳定倒序的有界安全 Activity 时间线；不返回原模块完整产物 |
| `POST /api/v1/learning/explain` | `ExplainRequest`、可选本地 Workspace/Task 上下文 | `ExplainResponse`、Runtime Event，并写入 `notebook_items`；带本地资料时由服务端在同一事务派生 Learning Activity |
| `GET /api/v1/learning/notebook?session_id=...` | 学习 `session_id` | 该学习会话的 `NotebookItem` 列表 |
| `POST /api/v1/context-transfers` | Learning 笔记 ID、学习 `session_id`、目标模块和选择内容 | 从真实笔记派生并持久化 `context-transfer.v1` 待确认上下文 |
| `GET`、`PATCH`、`DELETE /api/v1/context-transfers/{id}` | 上下文 ID 和来源学习 `session_id` | 在来源会话范围内恢复、编辑或清除传递快照；不修改原笔记 |
| `POST /api/v1/context-transfers/{id}/confirm` | 上下文 ID、来源学习 `session_id` 和用户最终确认的主题、摘要、保留内容 | 原子保存最终快照、创建科研会话并写入 `context-provenance.v1`；重复确认返回同一会话 |
| `POST /api/v1/learning/presentations/generate` | 知识点、学习 `session_id`、风格 | SSE 逐页返回演示文稿、生成来源并归档 |
| `GET /api/v1/learning/presentations/{presentation_id}?session_id=...` | 演示文稿 id 与学习 `session_id` | 只返回该学习会话内的已归档演示文稿 |
| `GET /api/v1/compiler/runtime` | 无 | Piston runtime 状态和服务端执行限制；不执行用户代码 |
| `POST /api/v1/compiler/execute` | Python 源码、标准输入、可选匿名 `learnerId` 和 AI 开关 | Piston 执行结果、规则分类、可选评价票据和最小学习记录 |
| `POST /api/v1/compiler/submit` | 服务端题目标识、版本、Python 源码和匿名 `learnerId` | 公开与隐藏测试的服务端判定；隐藏测试不返回内容或执行输出 |
| `POST /api/v1/compiler/evaluate`、`POST /api/v1/compiler/guidance` | 一次性票据或服务端提交上下文、匿名 `learnerId` | 可选 AgentRuntime 评价或引导；不修改执行和判题事实 |
| `GET /api/v1/compiler/records?learnerId=...` | 浏览器生成的匿名 UUID | 对应 UUID 的最近练习摘要；不是授权查询 |
| `POST /api/v1/research/conversations` | `CreateResearchConversationRequest` | 新的 `ResearchConversationResponse` |
| `POST /api/v1/research/conversations/{conversation_id}/messages` | 自由文本 | 更新画像、消息与下一步；达到准备度时附带规则生成的 `research_plan` |
| `GET /api/v1/research/conversations/{conversation_id}` | `conversation_id` | 已持久化的动态对话，并按当前画像恢复相同规则研究计划 |
| `POST /api/v1/research/conversations/{conversation_id}/topic-difficulty-analysis` | `user_confirmed: true` | 显式触发的难点个性化结果及 Runtime run 标识 |
| `POST /api/v1/research/conversations/{conversation_id}/experiment-design` | `user_confirmed: true` | 显式触发的实验方案个性化结果及 Runtime run 标识 |
| `POST /api/v1/research/conversations/{conversation_id}/experiment-code-draft` | 明确确认仅预览 | 服务端固定代码模板；模型只可补充建议性元数据 |
| `GET /api/v1/research/conversations/{conversation_id}/search-plan` | `conversation_id` | 不联网的 `ResearchSearchPlan` |
| `POST /api/v1/research/conversations/{conversation_id}/evidence-bundles` | 用户确认、查询和允许来源 | OpenAlex、Crossref、arXiv 元数据与摘要组成的 `ConversationEvidenceBundle` |
| `GET /api/v1/research/conversations/{conversation_id}/evidence-bundles` | `conversation_id` | 已保存的 evidence bundle 列表，不触发联网 |
| `POST /api/v1/research/conversations/{conversation_id}/citation-quality-checks` | `conversation_id` | 用户显式触发、仅基于当前会话已选择证据的引用完整性快照；不联网、不读全文、不改写正文 |
| `GET /api/v1/research/conversations/{conversation_id}/citation-quality-checks` | `conversation_id` | 恢复该会话已保存的引用完整性检查历史，不重新执行检查 |
| `GET /api/v1/research/conversations/{conversation_id}/reference-draft-package` | `conversation_id` | 确定性整理可复制文本与集中人工核验清单；每条追溯到用户选择和原始链接，不联网或修改原稿 |
| `POST /api/v1/research/conversations/{conversation_id}/reproduction-evaluations` | `user_confirmed: true` | 基于已保存画像、选择、可用 Pipeline 只读视图和实验记录生成并保存五维证据完整性评估；不联网、不执行代码、不改稿 |
| `GET /api/v1/research/conversations/{conversation_id}/reproduction-evaluations` | `conversation_id` | 恢复评估历史和当前改进任务状态，不重新运行评估 |
| `PATCH /api/v1/research/reproduction-improvement-tasks/{task_id}` | 用户明确的 `accepted / skipped / completed` | 仅更新允许的任务状态；不执行任务或推断已完成 |
| `POST /api/v1/research/conversations/{conversation_id}/evidence-bundles/{bundle_id}/notebook-notes` | Learning `session_id` 与用户选择的论文 URL | 校验 Conversation、Bundle 与论文归属，幂等写入可追溯的 `research_note` |
| `GET /api/v1/research/provider/status` | 无 | 不含密钥的 `ProviderStatusResponse` |
| `PUT /api/v1/research/provider/configuration`、`POST /api/v1/research/provider/test` | 本机显式配置或测试 | 默认禁用且仅允许 loopback 的 Provider 状态或测试结果 |
| `/api/v1/research/sessions...` | 原五字段 session 请求 | 兼容 `ResearchSessionResponse` 和 legacy evidence bundle |
| `GET /health` | 无 | FastAPI 进程存活状态，不检查数据库或外部依赖 |

请求 schema 不合法返回 422；科研对话或兼容会话不存在返回 404；画像尚未达到检索条件时返回 409；未处理异常返回不暴露内部细节的 500 和 `error_id`。调用方不得把这些状态映射为成功或空结果。

动态研究画像维护主题、动机、问题、上下文、方法、数据需求、证据偏好、时间范围、限制、预期产出、假设和不确定性，并以 `research-conversation.v1` 返回。画像达到计划准备度后，纯规则生成器派生 `research-plan.v1`；它不调用模型或网络，只使用已校验画像，结构化条目只允许 `inference` 或 `to_verify`。检索计划和证据分别使用 `research-search-plan.v1`、`academic-evidence.v1`。原五字段规则只属于兼容流程；这些业务状态都不进入 Kernel 契约。

Evidence 引用使用 Bundle ID、论文 URL、标题、来源平台、年份、证据级别和可用摘要片段。论文分析固定关联用户选中的 Evidence；模型生成的方向分析只有引用当前 Conversation 已保存的 Evidence 时，才可声明使用了元数据或摘要范围。

由跨模块确认创建的科研会话额外返回 `context_provenance`，完整保存服务端来源引用、确认时间和用户最终确认内容。科研对话服务在每轮消息处理时从会话记录加载该快照：Runtime 请求通过 `confirmed_learning_context` 接收完整背景，离线规则也识别其存在并只追问画像中尚未明确的研究选择。来源快照不随后续对话修改，普通科研会话的该字段为 `null`。

科研对话历史由业务数据库的 `messages_data` 恢复并显式转换为 Kernel `Message`。当完整 system、结构化画像、confirmed context、当前用户输入和历史超过 Research 上下文预算时，应用只压缩摘要边界后尚未覆盖的旧消息；`context_summary_data` 保存可复用摘要、覆盖边界、来源消息数、更新时间、生成方式和审计 run id。压缩失败继续使用原始消息并保留上一份有效摘要。

Research 与 CLI 共同依赖 `ConversationStateStore` 的“业务 ID + Host scope”显式加载契约，并通过泛型 `ContextAssembler` 注入各自上下文策略。Research 使用可持久化摘要和画像/confirmed context 预算；CLI 首期保留完整最近主对话轮次。共享协议不统一两者的 ORM schema、业务字段或恢复权限。

## 4. Runtime、Provider 与工具接口

### Runtime

标准 Agent 调用为：

```text
AgentSpec + RuntimeRequest
          ↓ AgentRuntime.run(...)
RuntimeResult + Event JSONL
```

`RuntimeRequest.conversation_history` 由业务 Host 显式提供。Runtime 按 system → conversation history → current user 组装消息；system 与当前 user 固定 pinned，历史可由上下文策略处理。`session_id` 仍只组织 Event 文件，不触发历史读取或恢复。

动态科研对话、显式触发的研究产物个性化、Provider 连接测试，以及可选的练习评价与引导使用该接口，均不授予工具权限。模型不可用或结构无效时，科研回退到规则，练习保留执行器与规则结果并把 AI 标记为禁用或不可用。对话 reducer 完成画像校验后，`research-plan.v1` 由应用规则派生，不产生新的 Agent run，也不访问 Provider 或网络。兼容五字段流程仍通过统一 Provider 契约调用 `complete()`；超时由供应商 SDK 传输层配置。

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

Piston 是应用层外部执行器，不注册为 Kernel Tool。学生代码状态以规范化的 Piston 响应为准，题目正确性以服务端测试比较为准；AgentRuntime 文本只作为独立建议。

## 5. 会话与持久化接口

| 标识 | 作用 | 不代表什么 |
| --- | --- | --- |
| Runtime `session_id` | 组织同一来源的 Event JSONL | 业务状态、身份或自动恢复的对话 |
| CLI `conversation_id` | 通过显式 `shell --resume` 恢复当前项目的主对话消息 | Runtime Event 分组、`run_id`、跨项目恢复或 branch 状态 |
| 学习 `session_id` | 隔离 `notebook_items` 并关联学习 run | 用户账号或跨设备会话 |
| 本地 `local_profile_id` | 隔离同一部署中浏览器资料的 Workspace、Task 和 Activity | 身份认证、授权或跨设备账号 |
| Workspace / Task / Activity ID | 组织长期上下文、目标和模块产物安全索引 | 模块原始产物、完整会话、工具权限或内容传递确认 |
| 上下文 `id` + 来源 `session_id` | 恢复待确认快照，并在显式确认后绑定一个科研会话 | 身份授权、未经确认的 Research 写入或工具权限 |
| 练习 `learner_id` | 筛选独立 SQLite 中的匿名练习摘要 | 身份、授权或防止他人读取已知 UUID |
| 科研 `conversation_id` | 恢复动态画像、消息和 evidence bundle | Kernel 权限、身份或长期记忆 |
| 兼容科研 `session_id` | 恢复原五字段澄清状态与 turns | 当前科研页面主流程 |

浏览器将学习 `session_id`、科研 `conversation_id` 和练习 `learner_id` 存入 `localStorage`，只提供同一浏览器内恢复，不提供身份绑定或授权。

研究笔记仍由学习 `session_id` 隔离；其 `extra_data` 保存 `research-notebook-note.v1`，包括来源 Conversation、Bundle、选中 Evidence 和下一步建议。当前字符串 `item_type` 与 JSON 扩展列可直接承载该类型，不新增数据库列。

业务模块共用 `code_navi.db.Base`、`get_db()` 和 `CODE_NAVI_DATABASE_URL`；`LEARNING_DATABASE_URL` 仅兼容旧配置。默认数据库为 `.code-navi/learning_poc.db`。`workspaces`、`workspace_tasks` 和 `workspace_activities` 共同组成编排层：Task 必须归属 Workspace，Activity 可没有 Task，但只保存来源引用和安全摘要；个人 Workspace 由数据库唯一约束幂等取得。`cli_conversations` 按规范化项目根目录隔离 shell 主对话；Research 与 CLI 分别保留 `research_conversations` 和 `cli_conversations`，不共用全局 Agent 会话表。Runtime Event 单独写入 JSONL，不作为业务数据库。

练习记录当前例外地使用 `COMPILER_DATABASE_PATH` 指向独立 SQLite，并由模块自行创建 `learning_records` 表；它不进入共享 SQLAlchemy Base 或 Alembic。记录保存匿名 UUID、规则与 AI 摘要、代码哈希、代码大小和运行指标，不保存原始代码与标准输入。该路径属于本地原型，生产化前必须统一迁移、所有权和删除规则。

schema 变更必须新增 Alembic revision，并验证空库和受影响旧库升级。`0003` 创建动态科研对话和证据表，`0004` 创建待传递上下文，`0005` 增加确认状态、科研会话关联和来源快照；`research_context_summary_v1` 增加 Research 跨 run 摘要，`cli_conversations_v1` 增加项目作用域内的 CLI shell 主对话，`persistent_workspace_foundation_v1` 创建 Workspace、Task 与 Activity 编排表及时间线索引。启动时的 `Base.metadata.create_all()` 只创建缺失表，不能替代迁移。

## 6. 架构变更条件

以下变化需要 ADR 或等价的简短书面决策：

1. 改变主要分层、依赖方向或公开 Runtime、Provider、工具、API 或持久化契约；
2. 引入难以替换的基础依赖、身份系统、正式数据库或生产部署方案；
3. 扩大工具权限或真实外部副作用；
4. 多个独立组件即将并行依赖同一稳定接口。

小型、可逆且不改变外部行为的实现细节留在 PR 中。Kernel 内部维护见 [kernel.md](kernel.md)，前端专属状态见 [frontend.md](frontend.md)，高风险能力见 [高风险能力](../development/high-risk-capabilities.md)。
