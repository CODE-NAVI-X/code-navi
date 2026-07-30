# 规则控流程的科研澄清 Skill

- 名称：`research_clarification`
- 版本：`0.3.0`
- 用途：通过可恢复的规则会话收集科研需求，并在五个字段完整后生成结构化研究简报和规则研究计划。可选模型仅用于生成更贴合上下文的澄清文案。

## 输入与输出

创建接口为 `POST /api/v1/research/sessions`，可选输入：

```json
{"initial_description": "教育场景中的人工智能"}
```

该描述会原样记录为第一个字段“研究领域”的自由输入，不对其做模型推断。后续接口 `POST /api/v1/research/sessions/{session_id}/turns` 必须且只能提供 `answer`（自由输入）或 `selected_option`（三个规则推荐项之一）。

输出固定包含：`session_id`、五字段 `state`、按固定顺序的 `missing_fields`、下一题及三个选项、`turns`、`reply` 和 `generation_mode`。`generation_mode` 只能是 `llm`、`rules`、`rules_fallback`；模型输出的 `reply`、`next_question`、恰好三个 `options` 与可选 `suggested_value` 都会被严格校验。只有全部字段存在时才提供 `research_brief`、`research_plan` 并将 `completed` 设为 `true`。

`research_plan` 固定包含研究题目、研究目标、候选方法/基线、可选数据集或指标、两周 MVP、风险与规避、检索关键词和来源说明。每个计划条目带有 `classification`：`inference` 表示仅由用户简报推导出的建议，`to_verify` 表示缺少可靠来源、必须后续核验的事项；本版本不会产生或宣称 `fact` 类型的论文/实验事实。

五字段：`research_domain`、`core_question`、`data_and_method`、`constraints`、`expected_deliverable`。

## 权限、信息源与持久化

- 所需 Kernel 权限：无。本 Skill 作为应用层 Workflow API，不会自动调用 AgentRuntime 或 ToolRegistry。
- 可访问的信息源：规则层仅访问本次 API 请求和本应用 SQLite 会话记录。可选文案生成复用应用已有 OpenAI Provider 配置，只在 `CODE_NAVI_PROVIDER=openai`、模型名和服务器环境变量 `OPENAI_API_KEY` 都已配置时向该 Provider 发送当前规则状态与本轮输入；不保存 Key，也不访问论文库、MCP 或文件系统。学生端仅在浏览器本地保存 `session_id`。
- 写操作：仅写入应用层 SQLite 的 `research_sessions` 表，以保存会话状态、用户回合历史，以及最后一轮已校验的展示文案或降级状态；不保存 Key、原始 Provider 异常或论文内容，不写入 Kernel Event，也不写入用户项目。

## 失败与降级

- 不存在的 `session_id` 返回 HTTP 404；
- 同时提供或同时缺少 `answer` 与 `selected_option` 返回 HTTP 422；
- 无 Key、未选择 OpenAI Provider、超过 8 秒的调用、网络/Provider 失败、无文本响应或 JSON/字段校验失败时，均返回固定规则问题和三个选项，不中断或丢失会话。页面明确显示规则生成或规则降级。
- 8 秒限制保证本 API 响应不再等待上游调用；由于现有 Provider 契约没有暴露可取消请求句柄，超时后的底层网络请求可能由守护线程自行结束，其结果会被丢弃且绝不会写入会话。高并发限流与 Provider 级取消属于后续 Provider/宿主层工作，不在本 Skill 中绕过 Kernel 实现。
- 模型不能决定字段名、字段顺序、缺失判定或完成条件；这些均由 `rules.py` 控制。模型输出含多余字段、非字符串内容、空值、不是三项/重复选项，或在非推荐请求中提供 `suggested_value` 时一律降级。
- 用户表达“不知道/帮我推荐”时，只有校验通过的 `suggested_value` 可以作为当前字段的 `llm_suggested` 回合写入；无有效建议时该字段保持待填写，不能把“不知道”保存为研究数据。
- 数据集、指标、基线或文献来源无法由规则可靠确认时，计划返回 `to_verify`，不会伪造具体名称、实验设置或结论。

## 测试样例

```bash
python -m pytest tests/test_research_api.py tests/test_research_llm.py -q
```

测试覆盖创建会话、固定三个选项、自由输入、初始描述、会话恢复、五字段完成简报和规则研究计划、无 Key 规则流程、Provider 结构化输出、失败降级、推荐值写入、输入校验和 404。前端可使用 `npm --prefix frontend run lint` 和 `npm --prefix frontend run build` 验证类型与页面构建。

## 外部参考与许可证

本实现仅借鉴 POIROT 的“任务状态与上下文治理”思想，以及 Anthropic Skills 的清晰契约与测试组织思想：将业务会话状态保存在应用层、使用可观察的结构化回合记录。未复制 POIROT、Anthropic Skills、LangGraph 或其他第三方代码、脚本、资源与许可证内容；本 Skill 不引入外部运行时或依赖。
