---
name: topic-difficulty-analysis
description: 从已确认画像、规则计划与有限证据中识别研究设计难点，而不把推测当作实验或论文事实。
---

# 研究方向难点分析

## 版本与用途

- 版本：`0.2.0`
- 用途：输出 `topic-difficulty-analysis.v1`，帮助学生检查研究问题、方法、数据、复现、资源和时间风险。

## 输入与输出

- 输入：已确认的 `ResearchProfile`、`research-plan.v1` 和可选 EvidenceBundle。
- 输出：带 `area`、`content`、`classification`、`basis`、`source_scope` 的难点及下一步建议。

## 规则层与模型层边界

- 规则层控制会话、确认、可用上下文、事实标签和规则降级。
- 用户确认后可选模型只能生成经 JSON 校验的表达；不得改写画像、声称数据/资源/结论存在，或决定联网、写入、安装和执行。

## 权限、来源与副作用

- 不联网；只读取已保存画像、规则计划和 EvidenceBundle 元数据/摘要。
- 不写用户项目、不安装依赖、不执行代码或命令。

## 失败与规则降级

无 Provider/密钥、模型超时、网络错误、非法 JSON、字段缺失或事实边界不合格时，使用规则结果。摘要未覆盖的内容必须标记 `to_verify`。

## 测试样例

- `tests/test_research_artifact_llm.py`：模型成功与 JSON/超时降级。
- `tests/test_research_mindmap.py`：无摘要及事实标签回归。

## 外部参考与许可证

仅借鉴结构化科研风险梳理思路；不复制外部 Agent、论文或数据处理代码。无新增第三方运行时依赖。
