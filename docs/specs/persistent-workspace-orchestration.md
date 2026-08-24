# Persistent Workspace Orchestration

持久工作区与自由编排

| 状态 | 关联决策 | 当前计划 |
| --- | --- | --- |
| 已实现，Learning 与 Practice 本地验证完成 | [Workspace–Task–Capability 产品模型](../decisions/workspace-task-capability-model.md) | [持久工作区实施计划](../plans/persistent-workspace-orchestration-rollout.md) |

## 1. 产品目标

用户可以从目标、已有工作区或具体能力任意开始。Code Navi 持续保存其工作上下文、活动和产物来源，并允许用户自由组合 Learning、Practice 与 Research。

## 2. 核心概念

| 概念 | 用户侧含义 | 系统职责 |
| --- | --- | --- |
| Workspace | 一门课程、一个项目、一项研究或个人工作集合 | 保存长期组织边界和最近活动 |
| Task | 当前希望完成的目标 | 保存目标、成功标准与生命周期 |
| Capability | Learning、Practice 或 Research 的系统能力 | 维护原始产物与权限边界；产品页面不必一一对应 |
| Activity | 一次可在时间线中找到的工作记录 | 保存来源引用和安全摘要 |

## 3. 必须成立的用户路径

### 3.1 Task-first

用户在首页输入“理解 Q-learning 更新过程”。系统在个人工作区创建 Task，用户进入 Learning 并保存解释。返回 Task 或刷新页面后，目标和学习活动仍可恢复。Task 可以不进入 Practice 或 Research 就完成。

### 3.2 Workspace-first

用户进入“计算机网络课程”工作区，创建“比较 Reno 与 Cubic”Task，选择所需 Capability 保存结果并暂停。下次进入该 Workspace 时，可以恢复 Task 和已有活动。

### 3.3 Capability-first

用户直接进入 `/learning/practice`，页面取得个人 Workspace 的默认 launch。运行 Python 并获得权威结果后，活动保存到个人工作区且不强制创建 Task。用户之后可以将活动整理到现有 Task，或在目标 Workspace 中新建 Task 后关联。

## 4. 功能要求

| 能力 | 必须满足的行为 |
| --- | --- |
| 持久工作区 | 刷新和重新进入后仍能读取 Workspace、Task 与最近 Activity |
| 聚焦任务 | Task-first 与 Workspace-first 创建相同语义的 Task |
| 自由入口 | 没有 Task 时仍可使用任一 Capability，之后可以整理活动 |
| 统一上下文 | Capability 页面显示当前 Workspace、可选 Task 和明确返回入口 |
| 活动时间线 | Learning、Practice 与 Research 的安全摘要出现在同一 Workspace 或 Task 时间线中 |
| 知识缺口回流 | QuizAttempt、ConfusionMark 或 PracticeOutcome 可引用原始来源并进入复盘 |
| 可选建议 | 系统最多突出少量相关下一步，用户可以忽略且不影响完成状态 |

## 5. 产品不变量

1. Task 和 Activity 都必须属于 Workspace；Activity 的 Task 关联可以为空。
2. Activity 关联 Task 后，两者的 Workspace 必须一致。
3. 模块产物继续由原模块维护，Activity 只保存引用和允许展示的摘要。
4. Task 可以只使用一种 Capability，系统不生成模块覆盖率。
5. 推荐不自动跳转、执行能力或改变 Task 状态。
6. 跨模块敏感内容继续经过现有确认流程。
7. Activity 的来源失效时，时间线明确显示来源不可用，不把摘要伪装成可恢复的原始产物。
8. Activity 由服务端从已持久化的模块结果幂等创建，不记录加载、重试等请求过程，也不由前端声明成功。

## 6. 第一版：Persistent Workspace Foundation

第一版只验证 Task-first、Workspace-first 和 Learning 独立入口。

### 6.1 用户故事

1. 用户输入目标后，系统在个人工作区保存一个 Task。
2. 用户可以先进入 Workspace，再创建语义相同的 Task。
3. 用户从 Task 进入 Learning，成功保存解释后可在 Task 时间线看到该活动。
4. 用户可以不创建 Task，直接进入 Learning。

### 6.2 验收条件

1. 每个新 Task 都有 Workspace；未指定 Workspace 时幂等取得个人工作区。
2. Learning Activity 可以不关联 Task，并始终拥有 Workspace。
3. Task-first 与 Workspace-first 使用同一服务端创建规则。
4. 刷新首页、Workspace、Task 和 Learning 页面后，服务端持久状态可以恢复。
5. 现有 Learning Notebook 与 `context-transfer.v1` 行为保持有效。
6. 第一版不引入自动编排、统一 Artifact 表、身份系统或 Practice/Research 改造。

## 7. 后续能力

Practice 已按 [Learning–Practice Integration Spec](learning-practice-integration.md) 接入 Learning 路由、默认 launch、PracticeOutcome、Activity 和复盘；Research 接入后仍保留显式上下文确认。后续再根据已保存 Activity 和知识缺口增加确定性建议。各阶段保持三个系统 Capability 可独立调用，不要求在全局导航中各占一个入口。

## 8. 限制

本地 `local_profile_id` 只能隔离同一部署中的浏览器资料，不能提供账号授权或跨设备恢复。因此第一版的“持久”指服务端保存并可在同一浏览器资料中恢复，不代表多用户生产环境已经可用。
