---
name: reproduction-evaluation
description: 对已保存的论文复现项目做五维证据完整性评估，并生成由用户控制的改进任务。
---

# 论文复现项目评估

## 版本与用途

- 版本：`reproduction-project-evaluation.v1`
- 用途：在用户明确点击后，离线检查一个论文复现项目的记录与证据完整度；结果不是论文质量、复现成功或投稿结论。

## 输入与输出

- 输入：当前会话已保存的科研画像、用户明确选择的论文/来源、A 的 `ReproductionPipeline` 只读适配视图、用户主动提交的实验记录。
- 输出：五个各 20 分的维度、`earned_score`、当前 `scored_maximum`、结构总上限 100、每维问题/依据/事实边界/待核验项/下一步，以及可接受、跳过或完成的改进任务。
- 缺少足够证据的维度输出 `not_evaluable` 和空分值，不以零分或模型猜测代替。只有五个状态：`not_evaluable`、`needs_revision`、`evidence_partial`、`checklist_complete`。

## 规则层与模型层边界

- 当前完全规则化，按显式条目是否存在、能否追溯和信息范围评分。
- `checklist_complete` 只表示该维度的记录清单完整，不表示复现成功、结果正确、论文可投稿或会被接收。
- 模型不得补造 Pipeline、实验数值、数据集、基线、指标、失败记录、伦理审批或全文事实。

## 权限、来源与副作用

- 只读取应用数据库中当前会话的已保存记录；不联网、不下载或读取论文全文、不读取原始实验文件、不运行代码、不改写草稿。
- 用户点击评估后写入一个不可变评估快照及改进任务；任务状态只在用户明确接受、跳过或标记完成后改变。
- B 只定义面向评估的只读适配视图，不持有或重写 A 的 `ReproductionPipeline` 规则。

## 失败与规则降级

- 会话不存在返回 404；评估或任务不存在返回 404；非法任务状态迁移返回 409。
- A 的 Pipeline 合同不可用时，“复现路径与可执行性”保持 `not_evaluable`；没有实验记录时，“执行记录与结果证据”保持 `not_evaluable`。
- 只有元数据/摘要的来源始终保留该信息范围，摘要之外内容不会升级为 `fact`。

## 测试样例

- `tests/test_research_reproduction_evaluation.py`：空实验记录、Pipeline 缺失、摘要事实边界、评分、持久化、任务状态机和刷新恢复。
- `tests/test_migrations.py`：空数据库升级、历史迁移链和 ORM schema 一致性。
- `tests/test_research_frontend_copy.py`：用户触发、五维展示、不可评估说明和禁止性结论文案。

## 外部参考与许可证

只复用本项目现有 EvidenceBundle、实验结果证据包和 `fact / inference / to_verify` 边界；未复制第三方评分量表、代码、Prompt 或论文内容，未新增运行时依赖。
