# 规则驱动科研澄清 Skill

- 名称：`research_clarification`
- 版本：`0.1.0`
- 用途：通过可恢复的规则会话收集科研需求，并在五个字段完整后生成结构化研究简报。

## 输入与输出

创建接口为 `POST /api/v1/research/sessions`，可选输入：

```json
{"initial_description": "教育场景中的人工智能"}
```

该描述会原样记录为第一个字段“研究领域”的自由输入，不对其做模型推断。后续接口 `POST /api/v1/research/sessions/{session_id}/turns` 必须且只能提供 `answer`（自由输入）或 `selected_option`（三个规则推荐项之一）。

输出固定包含：`session_id`、五字段 `state`、按固定顺序的 `missing_fields`、下一题及三个选项、`turns`。只有全部字段存在时才提供 `research_brief` 并将 `completed` 设为 `true`。

五字段：`research_domain`、`core_question`、`data_and_method`、`constraints`、`expected_deliverable`。

## 权限、信息源与持久化

- 所需 Kernel 权限：无。本 Skill 作为应用层 Workflow API，不会自动调用 AgentRuntime 或 ToolRegistry。
- 可访问的信息源：仅本次 API 请求和本应用 SQLite 会话记录；不访问网络、论文库、MCP、文件系统或外部模型。
- 写操作：仅写入应用层 SQLite 的 `research_sessions` 表，以保存会话状态和用户回合历史；不写入 Kernel Event，也不写入用户项目。

## 失败与降级

- 不存在的 `session_id` 返回 HTTP 404；
- 同时提供或同时缺少 `answer` 与 `selected_option` 返回 HTTP 422；
- 本版本不调用 LLM，因此不存在模型超时或 API Key 依赖；所有问题和推荐项均由 `rules.py` 固定规则生成。

## 测试样例

```bash
python -m pytest tests/test_research_api.py -q
```

测试覆盖创建会话、固定三个选项、自由输入、初始描述、会话恢复、五字段完成简报、输入校验和 404。

## 外部参考与许可证

本实现仅借鉴 POIROT 的“任务状态与上下文治理”思想：将业务会话状态保存在应用层、使用可观察的结构化回合记录。未复制 POIROT、LangGraph 或其他第三方代码、脚本、资源与许可证内容；本 Skill 不引入外部运行时或依赖。
