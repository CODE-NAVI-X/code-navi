# 受限学术检索与 EvidenceBundle Skill

- 名称：`academic_search`
- 版本：`0.1.0`
- 用途：在已完成的科研会话后，由用户明确请求检索允许的学术来源，并返回可追溯、仅含元数据/摘要的 EvidenceBundle。

## 输入与输出

接口为 `POST /api/v1/research/sessions/{session_id}/evidence-bundles`：

```json
{"query": "教育场景 人工智能", "sources": ["arxiv"]}
```

该请求是唯一会触发联网的入口；创建、恢复科研会话及生成研究计划都不会自动检索。`query` 可省略，此时使用规则研究计划的第一个建议检索关键词。当前仅支持代码允许的 `arxiv`；通过服务器环境变量 `CODE_NAVI_ACADEMIC_ARXIV_ENABLED=false` 可禁用该来源。

返回 `EvidenceBundle`：关联会话、检索词、允许/实际查询来源、来源状态与访问时间、论文元数据、来源链接、摘要支持片段、失败原因及 Tool 审计信息。每条论文结果均标记 `information_scope=metadata_and_abstract_only`，并包含：

- `fact`：来源直接返回的标题、作者、年份、链接或摘要片段；
- `inference`：基于检索词与元数据/摘要的关联提示；
- `to_verify`：需要阅读全文或人工核验的项目。

## 权限、来源与写操作

- Tool：`academic_search`，固定需要 `READ + NETWORK`，通过既有 `ToolRegistry`、`PermissionGrant` 和 `ToolExecutionContext` 分发。
- 来源：仅 arXiv Atom API（`https://export.arxiv.org/api/query`），没有默认全网搜索，也没有 Crossref/OpenAlex 或浏览器搜索后备。
- 写操作：无。EvidenceBundle 只作为本次 API 响应返回；不保存 Key、论文全文、下载缓存或用户项目文件。

## 失败与降级

网络失败、8 秒来源超时、无结果、来源禁用、XML 不可用或不允许的来源都会返回空 `papers` 和明确的 `source_statuses` / `failure_reasons`，绝不伪造论文。当前不下载正文、不做 LLM 精读、不生成论文证据卡。

## 测试样例

```bash
python -m pytest tests/test_academic_evidence.py -q
```

覆盖来源 allow-list、`READ + NETWORK` 拒绝、显式 API 触发、成功 EvidenceBundle、网络/超时/无结果/来源不可用降级、未完成会话拒绝和事实边界。

## 外部参考与许可证

仅借鉴 Anthropic Skills 的独立契约组织，以及 World Monitor 的来源状态、时间与可追溯展示思想。未复制第三方代码或资源；arXiv 名称/API 的使用应遵守其服务条款与限流要求。
