# Learning–Practice Integration

Practice 集成进 Learning

| 状态 | 关联决策 | 当前计划 |
| --- | --- | --- |
| 已实现，本地验证完成 | [Practice 集成进 Learning](../decisions/practice-in-learning-experience.md) | [Learning–Practice 集成计划](../plans/learning-practice-integration-rollout.md) |

## 1. 产品目标

用户在统一的 Learning 入口中探索方向、理解概念、检查理解、动手实践、复盘知识缺口并管理笔记与学习画像。各工作方式可以独立进入，不形成固定教学步骤。

## 2. 导航与路由

1. 全局导航提供工作台、学习和科研。真实账号能力落地前不设置会被理解为账号中心的“用户”一级入口。
2. `/learning` 是学习总入口；方向探索、动手实践、学习画像和 Notebook 使用 Decision 规定的规范子路由。
3. 旧 Practice、Portrait 和 `/student/*` 学习路径 redirect 到规范路由，并保留查询参数。
4. 用户访问动手实践时，全局活动项显示“学习”。

## 3. 学习工作区

一个 Topic 或 Task 上下文可以展示以下工作方式：

```text
[理解] [理解检查] [动手实践] [复盘] [笔记]
```

用户可以从任意入口开始，也可以只完成一次代码运行后退出。没有 Task 时，活动进入个人 Workspace 且 `task_id = null`；Topic 或其他 Focus 继续显示本次活动针对的内容。

## 4. 自由循环

1. 理解与讲解可以进入理解检查、动手实践或科研探索。
2. Quiz 错误和有效的 Practice 错误进入复盘视图，并保留原始来源。
3. 定向回顾后，用户可以重新检查理解，也可以再次实践。
4. 系统建议不自动跳转、运行代码、调用模型或改变 Task 状态。
5. 自由运行成功只表示当前输入正常结束，不表示题目正确或知识点已掌握。

## 5. Practice 结果与活动

1. 执行与判题 API 继续由 Practice Capability 提供。
2. 服务器取得权威执行或判题结果后，持久化不含源码、stdin 和隐藏测试的 PracticeOutcome。
3. WorkspaceActivity 从 PracticeOutcome 幂等派生。前端不能提交 verdict、score、通过状态或 Activity 成功状态。
4. 用户代码错误和错误答案可以形成 Activity 与知识缺口信号；请求校验失败和执行服务故障不形成用户知识缺口。
5. Activity 来源失效时显示来源不可用，不使用 Activity 摘要代替原始结果。

## 6. launch 行为

1. 从 Task、Workspace、学习主题或已有 Activity 进入 Practice 时，编排层签发 `launchId`。
2. launch 关联 `practice` Capability、具体 mode、Workspace、可选 Task、Focus、来源 Activity、所有者范围和有效期。
3. 服务器验证 Task 与 Workspace 一致，并验证来源 Activity 属于同一本地所有者范围。
4. `launchId` 可以承载同一上下文中的多次尝试；每次结果使用独立结果 ID 或幂等键。
5. 直接进入 `/learning/practice` 时，页面自动取得个人 Workspace 的默认 launch。
6. 兼容客户端省略 `launchId` 时保持执行能力，但不创建 WorkspaceActivity。

## 7. 复盘与知识缺口

复盘视图聚合以下来源：

| 来源 | 可表达的事实 |
| --- | --- |
| QuizAttempt | 服务端评分结果与题目来源 |
| ConfusionMark | 用户主动标记的不理解位置 |
| PracticeOutcome | 规则分类、执行结果或服务端判题结果 |

KnowledgeGap 保留来源引用、Focus、错误类型、时间和当前状态。Practice 的 AI 表达质量分不作为题目正确性或掌握度；执行服务故障不进入 KnowledgeGap。

## 8. 身份与本地恢复

1. `session_id` 继续隔离 Notebook。
2. `profile_id` 与 Practice `learner_id` 使用同一个 UUID，聚合跨学习会话的画像与行为信号。
3. `local_profile_id` 继续隔离 Workspace、Task 和 Activity。
4. launch 在服务端绑定本地编排所有者键与学习行为聚合键。
5. 上述浏览器标识都不是身份授权；账号阶段使用 `user_id` 建立所有权和迁移关系。

## 9. 验收条件

1. `/practice`、`/student/practice`、`/portrait`、`/student/portrait` 和 `/student/learning` 都进入对应规范路由且查询参数不丢失。
2. `/learning/practice` 的全局活动项为“学习”，同时保留自由练习入口。
3. 带 Task 的 launch 创建同 Workspace 的 Practice Activity；直接进入时创建个人 Workspace 下、无 Task 的 Activity。
4. 错误答案、编译错误和运行错误显示为已完成的 Practice 活动，并进入可追溯复盘；系统故障不进入用户知识缺口。
5. 重试不会重复创建同一 PracticeOutcome 或 Activity；同一 launch 下的主动重做形成新的结果。
6. Activity 与复盘视图不返回源码、stdin 或隐藏测试内容。
7. 旧 API 客户端不传 `launchId` 时仍能执行且不创建 Activity；Web 页面必须取得默认 launch，取得失败时明确显示未进入 Workspace 时间线。

## 10. 当前实现与限制

当前页面使用规范 Learning 子路由，旧 Practice、Portrait 与 `/student/*` 学习路径保留查询参数并 redirect。Web 为自由运行和题目提交分别取得对应 mode 的 launch；带 launch 的结果进入共享数据库 PracticeOutcome 与 Workspace Activity，复盘视图只读聚合 QuizAttempt、ConfusionMark 和 PracticeOutcome。

独立 SQLite CompilerRecord、内存 Submission 与 `FlowPayload` 仍作为兼容路径存在；它们不替代 PracticeOutcome 或服务端 launch。`local_profile_id` 与 `profile_id / learner_id` 仍是本地隔离和聚合键，不提供账号授权或跨设备恢复。
