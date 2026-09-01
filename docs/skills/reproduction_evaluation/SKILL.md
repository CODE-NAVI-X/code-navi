# 论文复现项目评估 Skill

## 版本

`reproduction-project-evaluation.v2`

## 输入与输出

输入只来自当前会话已保存的科研画像、用户明确选择的论文来源、A 的 `ReproductionPipeline` 只读适配视图和用户提交的实验记录。新评估输出六条固定准则，每条 0/1/2 分，`total_score` 满分 12，并提供依据、证据引用和用户可接受、跳过或完成的改进任务；v1 快照只读保留为“历史口径”，不做 100→12 换算。

## 规则层与模型层边界

当前评分完全由确定性规则生成。模型不得补造 Pipeline、论文全文事实、数据集、基线、指标、实验结果、失败记录或伦理审批。`checklist_complete` 只表示记录清单完整，不表示复现成功、论文质量、可投稿或会被接收。

## 权限、来源与副作用

只有用户点击后才创建评估快照；刷新只恢复已保存结果。服务不联网、不读论文全文或原始实验文件、不运行代码、不修改论文。改进任务只在用户明确操作后改变状态。B 的适配视图不持有或重写 A 的 Pipeline 业务规则。

## 失败与规则降级

会话、评估或任务不存在时返回 404，非法任务状态迁移返回 409。A 的 Pipeline 不可用时，复现路径维度为 `not_evaluable`；没有实验记录时，执行与结果维度为 `not_evaluable`。元数据/摘要来源始终保留其有限信息范围，摘要外内容不会标为 `fact`。

## 测试样例

后端契约、事实边界、持久化、任务状态机与刷新恢复见 `tests/test_research_reproduction_evaluation.py`；前端显式触发与禁止性文案见 `tests/test_research_frontend_copy.py`；数据库升级见 `tests/test_migrations.py`。

## 外部参考与许可证

仅沿用仓库内 EvidenceBundle 和 `fact / inference / to_verify` 规则；未复制第三方量表、代码、Prompt 或论文内容，未新增依赖。
