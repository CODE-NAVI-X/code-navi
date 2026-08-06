---
name: academic-search
description: 在用户明确触发后，仅从允许的学术来源检索元数据和摘要，并保存可追溯 EvidenceBundle。
---

# 受限学术检索

## 版本与用途

- 版本：`0.2.0`
- 用途：根据已确认画像和研究计划生成可审计的检索结果及 `academic-evidence.v1` EvidenceBundle；不是默认全网搜索。

## 输入与输出

- 输入：会话/计划标识、用户明确提交的检索词和已选来源。
- 输出：`research-search-plan.v1`、来源状态、`AcademicPaperResult` 元数据/摘要片段和包含访问时间、失败原因、`fact / inference / to_verify` 分类的 EvidenceBundle；证据范围固定为 `metadata_and_abstract_only`。

## 规则层与模型层边界

- 规则层构造查询、验证来源、保存证据包并区分事实边界。
- 此 Skill 不需要模型；模型不得虚构论文、摘要、来源状态或把关键词关联写成事实。

## 权限、来源与副作用

- 只能经已注册的 `academic_search` Tool，以 `READ + NETWORK` 权限运行，且必须由用户显式触发。
- 当前允许来源由宿主 allow-list 决定（OpenAlex、Crossref、arXiv）；未选或未允许来源在联网前拒绝。
- 仅写入应用的 EvidenceBundle；不下载全文、不写用户项目、不执行代码。
- Execution requires explicit user confirmation. Do not fall back to a browser or unrestricted web search.

## 失败与规则降级

网络、超时、来源禁用/不可用、依赖缺失或无结果时，返回空的安全结果和逐来源原因；保留其他来源已成功的元数据，绝不回退为浏览器或全网检索。

## 测试样例

- `tests/test_academic_evidence.py`：EvidenceBundle 字段、来源状态与事实/推断边界。
- `tests/test_conversation_search.py`、`tests/test_research_tools.py`：显式触发、allow-list 和 Tool 权限契约。

## 外部参考与许可证

仅调用公开学术来源的受限 API 适配，不引入完整 MCP 服务或抓取器。上游数据的使用遵循各来源条款；仓库未复制其代码。
