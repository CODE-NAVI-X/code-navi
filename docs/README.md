# 文档导航

Code Navi 的文档按“稳定产品边界、设计决策、可验收行为、实施状态”分开维护，避免把长期原则与阶段性实现混写在同一文件中。

| 目录 | 职责 | 更新时机 |
| --- | --- | --- |
| `product/` | 产品范围、业务边界、当前优先级与实现状态 | 产品边界或交付状态变化时 |
| `architecture/` | 当前已实现的系统边界、依赖方向和公共接口 | 架构或公开契约实际变化时 |
| `decisions/` | 已采纳的重要设计选择、约束及其后果 | 需要稳定多个组件共同依赖的原则时 |
| `specs/` | 用户可观察行为、产品不变量和验收条件 | 产品行为变化时 |
| `plans/` | 实施顺序、当前切片、代码范围和退出条件 | 推进或调整交付计划时 |
| `development/` | 开发流程、测试方法和高风险能力约束 | 工程规则变化时 |
| `deployment/` | 本地运行与生产准入 | 部署方式或准入要求变化时 |
| `references/` 与带日期的历史计划 | 设计依据和当时的实施快照，不定义当前产品行为 | 需要补充来源定位或历史状态时 |

阅读一个功能时，先从对应 Spec 了解行为，再沿链接查看 Decision 和当前 Plan。架构文档只描述已经落地的系统，不用未来计划改写当前事实。

当前产品级 Epic：

1. [Practice 集成进 Learning 决策](decisions/practice-in-learning-experience.md)、[Learning–Practice Integration Spec](specs/learning-practice-integration.md) 与 [实施计划](plans/learning-practice-integration-rollout.md)
2. [Learning Entry Spec](specs/learning-entry.md) 与 [学习入口页改版计划](plans/learning-entry-redesign.md)
3. [持久工作区与自由编排 Spec](specs/persistent-workspace-orchestration.md)
4. [Workspace–Task–Capability 决策](decisions/workspace-task-capability-model.md)
5. [持久工作区实施计划](plans/persistent-workspace-orchestration-rollout.md)
6. [板块合并与全局导航顶端设计](plans/module-consolidation-and-navigation-redesign.md)、[动手实践与科研引导接口设计](specs/hands-on-practice-research-guidance-interfaces.md)（设计提案 v2：已对照代码自评审修订，未实施；两文文末附评审记录）与 [实施计划 P0–P3](plans/module-consolidation-rollout.md)（含 PR 门禁）
7. 科研端全内容 LLM 生成与质量规范：
   - 上游基础质量：[实施计划](superpowers/plans/2026-08-28-research-upstream-quality.md) 与 [设计规格](superpowers/specs/2026-08-28-research-upstream-quality-design.md)
   - 下游证据质量：[实施计划](superpowers/plans/2026-08-28-research-downstream-quality.md) 与 [设计规格](superpowers/specs/2026-08-28-research-downstream-quality-design.md)
   - 全内容生成：[实施计划](superpowers/plans/2026-08-29-llm-all-research-content.md)、[设计规格](superpowers/specs/2026-08-29-llm-all-research-content-design.md)、[设计文档](design/2026-08-28-research-llm-generation-design.md) 与 [落地计划](plans/2026-08-28-research-llm-generation.md)
   - 辅助规划：[自动论文抓取](superpowers/plans/2026-08-29-auto-paper-ingestion.md)、[分章深度解析](superpowers/plans/2026-08-29-chapter-paper-analysis.md) 与 [论文循证建议](superpowers/plans/2026-08-29-paper-grounded-advice.md)
