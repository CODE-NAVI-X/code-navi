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
