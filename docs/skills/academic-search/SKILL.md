# 受限学术检索与 EvidenceBundle Skill

- 名称：`academic_search`
- 版本：`0.2.0`
- 用途：在已完成的科研会话后，由用户明确请求检索允许的学术来源，并返回可追溯、仅含元数据/摘要的 EvidenceBundle。

## 输入与输出

新对话主流程先读取不联网的计划，再显式执行：

```http
GET /api/v1/research/conversations/{conversation_id}/search-plan
POST /api/v1/research/conversations/{conversation_id}/evidence-bundles
GET /api/v1/research/conversations/{conversation_id}/evidence-bundles
```

POST 请求示例：

```json
{"query": "教育场景 人工智能", "sources": ["openalex", "crossref", "arxiv"]}
```

只有 POST 会触发联网；创建、恢复科研会话、生成计划和 GET 恢复 EvidenceBundle 都不会访问外部来源。`query` 可省略，此时使用从科研画像的主题、候选问题、场景和方法确定性组合的主查询，不直接把整句聊天文本当查询。允许来源为 `openalex`、`crossref` 和 `arxiv`。

返回 `EvidenceBundle`：关联会话、检索词、允许/实际查询来源、来源状态与访问时间、论文元数据、来源链接、摘要支持片段、失败原因及 Tool 审计信息。每条论文结果均标记 `information_scope=metadata_and_abstract_only`，并包含：

- `fact`：来源直接返回的标题、作者、年份、链接或摘要片段；
- `inference`：基于检索词与元数据/摘要的关联提示；
- `to_verify`：需要阅读全文或人工核验的项目。

## 权限、来源与写操作

- Tool：`academic_search`，固定需要 `READ + NETWORK`，通过既有 `ToolRegistry`、`PermissionGrant` 和 `ToolExecutionContext` 分发。
- 来源：仅 OpenAlex Works API、Crossref Works API 与 arXiv Atom API；没有浏览器或全网搜索后备。
- 并发：所选来源并行请求。OpenAlex、Crossref 使用最多两次有界尝试和 6 秒单次超时；arXiv 使用 8 秒超时，避免在经常不可达的网络上重复拉长等待。
- 代理：标准库 `urllib` 自动读取服务进程的 `HTTP_PROXY` / `HTTPS_PROXY`；代理地址不写入数据库或响应。
- 写操作：EvidenceBundle 按会话写入应用 SQLite，只保存检索词、来源状态、论文元数据/摘要和 Tool 审计，不保存 Key、论文全文或用户项目文件。
- 缓存：同一会话中，规范化查询词及来源组合完全相同时，默认 3600 秒内复用已保存结果；`CODE_NAVI_ACADEMIC_CACHE_TTL_SECONDS=0` 可禁用。

## 失败与降级

单一来源网络失败、超时、无结果、被禁用或返回非法数据时，EvidenceBundle 仍保留其他来源的成功论文。响应始终列出每个所选来源的状态、耗时和安全失败原因，绝不伪造论文；只有全部来源均无结果时 `papers` 才为空。当前不下载正文、不做 LLM 精读、不生成论文证据卡。

## 测试样例

```bash
python -m pytest tests/test_academic_evidence.py tests/test_conversation_search.py -q
```

覆盖来源 allow-list、`READ + NETWORK` 拒绝、显式 API 触发、画像生成查询、三源聚合、部分失败、网络/超时/无结果/来源不可用降级、持久化恢复、缓存命中、未就绪会话拒绝和事实边界。真实网络不属于默认离线测试。

## 外部参考与许可证

仅借鉴 Anthropic Skills 的独立契约组织，以及 World Monitor 的来源状态、时间与可追溯展示思想。未复制第三方代码或资源；arXiv 名称/API 的使用应遵守其服务条款与限流要求。
