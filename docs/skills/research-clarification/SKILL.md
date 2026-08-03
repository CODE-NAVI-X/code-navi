# 对话式科研需求澄清 Skill

- 名称：`research_clarification`
- 版本：`0.9.0`
- 状态：运行时需求确认 Skill、对话式后端核心、学生端界面及到受限学术检索 Skill 的显式交接已实现
- 用途：通过自然、多轮、可恢复的对话，把模糊想法逐步整理为可讨论、可检索的科研画像；不再要求用户依次填写五个固定字段。

## 设计边界

科研澄清是 `code_navi` 应用层工作流。在线决策只能通过 Kernel 公开的 `AgentRuntime` 运行 `research_conversation_agent`，不得直接绕过 Runtime 调用平台 SDK。该 Agent 不注册工具，因此澄清对话不会自动联网、检索论文、写文件或执行代码。学术检索必须由用户明确触发，并由单独的受限检索能力执行。

运行时使用的精简 Skill 契约位于 `src/code_navi/research/skills/research-clarification/SKILL.md`，随 Python 包一起交付并由 `research_conversation_agent` 直接加载；本文档保留 API、持久化和验收等工程说明。关键状态转移仍由应用层校验，避免模型忽略 Skill 指令后重复提问或越权检索。

模型可以在一轮中提取多个明确事实、提出候选问题、修正已有画像并决定最值得追问的一项；模型不能把推测写成用户事实。推测存入 `assumptions`，未知项存入 `uncertainties`。所有模型结果必须通过 Pydantic 严格校验，额外字段、错误类型、空内容和非法枚举都会触发安全降级。

## 主接口

创建对话并可选处理第一条消息：

```http
POST /api/v1/research/conversations
Content-Type: application/json

{"initial_message":"我想研究演化博弈法，数据来源不太清楚"}
```

继续自由对话：

```http
POST /api/v1/research/conversations/{conversation_id}/messages
Content-Type: application/json

{"message":"更具体一点，我想研究平台参与者之间的策略演化"}
```

恢复对话（不会再次调用模型或外部服务）：

```http
GET /api/v1/research/conversations/{conversation_id}
```

三类接口统一返回：

- `schema_version`：当前为 `research-conversation.v1`，用于前后端显式协商响应契约；
- `active_skill` / `next_skill`：当前运行的 `research-clarification`，以及用户确认后待交接的 `academic-search`；
- `conversation_id`：可恢复会话的标识；
- `profile`：动态科研画像，包括主题、动机、候选研究问题、场景、方法、数据需求、证据偏好、时间范围、约束、预期产出、假设与不确定项；
- `readiness`：可解释的 0–100 分成熟度、当前阶段、是否具备准备检索的条件及原因；
- `stage` / `ready_for_plan`：`exploring`、`focusing` 或 `ready_for_plan`，只是对当前画像的建议，不是固定问卷的必填门禁；
- `reply`、`next_question`、`suggested_answers`：自然回复、最多一个主要追问和可选回答；
- `candidate_questions`：可供用户比较、修改的候选科研问题；
- `recommended_action`：继续对话、检查画像或准备检索；
- `messages`：完整可恢复消息与每轮审计元数据；
- `generation_mode`：`agent`、`rules` 或 `rules_fallback`；
- `last_run_id`：在线 Agent 成功运行时对应的 Kernel 审计标识。

请求体禁止额外字段。空白消息、超过 4000 字的消息或类型错误返回 FastAPI/Pydantic 的 HTTP 422；不存在的 `conversation_id` 返回 HTTP 404。

## 学生端交互契约

- `/research` 使用 `/conversations` 主接口，不再调用旧五字段 `/sessions`；
- 浏览器只保存 `conversation_id`，刷新通过 GET 恢复服务端画像与完整消息，不保存密钥或模型响应副本；
- 消息区区分会话恢复与“正在理解并整理研究画像”状态，并在失败时保留草稿、显示具体原因和本轮重试入口；
- 助手回复支持不执行 HTML 的安全 Markdown 子集；建议答案和候选研究问题可直接作为下一轮自然语言发送；
- “本轮处理过程”只展示生成模式、意图、Kernel Event 数量和 Run ID，不展示或伪造模型内部思维链；
- 桌面端在侧栏显示科研画像、成熟度、缺口原因和候选问题，移动端使用可折叠面板；
- 页面明确说明不会自动联网；交接后展示查询计划和来源，只有用户再次确认才执行受限检索。

## 对话与状态规则

1. 用户可以一次说明多个维度，服务应一次性更新，不强迫重复回答。
2. 用户可以在后续消息中更正之前的主题、场景或约束。
3. `ResearchProfilePatch` 是唯一允许修改画像的数据结构；模型原始文本不能直接写数据库。
4. `clear_fields` 用于明确撤销旧字段。列表内容会去空白、去重并限制数量。
5. “不知道”“不清楚”等表达只记录为不确定项，绝不作为研究事实；同一句中已经明确的信息仍须保留。例如“我想研究演化博弈法，数据来源不太清楚”应保留主题，同时记录数据不确定性。
6. `readiness` 由画像信息量计算并给出缺口原因，不依赖固定字段顺序。具备主题以及研究问题或候选问题时，才可建议准备探索性检索。
7. 页面恢复只读数据库，不产生新的 Agent run，避免刷新页面造成费用、重复回复或状态漂移。
8. 用户选择上一轮建议后不得重复同一问题；若模型忽略该约束，应用层必须推进到新的澄清维度。
9. 用户明确选择“准备探索性检索”且画像满足最低检索条件时，当前 Skill 必须结束提问，返回 `recommended_action=prepare_search`、`next_skill=academic-search`、空 `next_question`，但不得自动联网。

## Provider、超时与降级

显式选择 OpenAI 或 DeepSeek 且提供对应服务端密钥时，服务才尝试在线运行。本地开发可通过 `code-navi configure-provider --provider deepseek` 隐藏输入，或通过仅限回环地址的 `PUT /api/v1/research/provider/configuration` 表单配置；两者都写入项目内 Git 已忽略的 `.code-navi/provider.env`。Web 表单不把 Key 写入 localStorage，保存后清空；服务响应、SQLite、消息、Event metadata、测试和日志不得包含 Key。状态接口只返回 Provider、模型、模式和配置来源；连接测试必须由用户显式触发。部署环境使用宿主环境变量或外部密钥管理，不得把本地入口当作生产管理端。

在线运行默认等待不超过 10 秒。Provider 不可用、超时、网络异常、Runtime 异常、空响应或结构校验失败时，本轮使用确定性规则生成；用户消息和已识别画像仍会保存，对话不会返回 500。降级模式不会伪造论文、方法、数据集或搜索结果，也不会自动触发学术检索。

当前 Kernel Provider 契约没有暴露底层请求取消句柄，因此超时后守护线程可能继续等待上游网络自行结束；其迟到结果会被丢弃且不会写入会话。并发限流、真正可取消调用和进程级任务队列属于后续宿主层工作。

## 持久化与审计

动态对话写入应用数据库的 `research_conversations` 表，包含 `profile_data`、`messages_data`、创建时间和更新时间。每条助手消息保存生成模式、意图、下一问、建议答案、候选问题、推荐动作，以及在线成功时的 `run_id` 和事件数量。受限检索结果单独写入 `research_evidence_bundles`，不会混入科研画像。不会保存 Provider 原始异常、API Key 或论文全文。

## 兼容接口

旧的 `/api/v1/research/sessions` 五字段接口继续作为 API 兼容层保留，但学生端已经迁移到 `/conversations`。新旧 EvidenceBundle 接口并存；旧接口的弃用和历史数据清理需要单独设计，不在本阶段直接删除。

## 离线验收

```bash
python -m pytest tests/test_research_conversation.py -q -p no:cacheprovider
ruff check . --no-cache
pytest -p no:cacheprovider
python -m build
```

测试必须覆盖：自由对话创建与恢复、单轮多维提取、后续纠正、非固定成熟度、无 Key 降级、模型非法输出降级、已知信息与“不清楚”共存、404，以及经 `AgentRuntime` + `MockProvider` 完成的可审计离线运行。真实 Provider 与外部网络测试只能显式标记并单独运行。
