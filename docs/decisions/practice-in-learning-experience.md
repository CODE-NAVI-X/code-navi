# Practice 集成进 Learning 的产品与系统边界

| 状态 | 日期 |
| --- | --- |
| 已采纳 | 2026-08-20 |

## 1. 背景

Learning 已具备讲解、PPT、Quiz、QuizAttempt、ConfusionMark、Notebook 和学习画像；Practice 已具备独立的代码执行、判题、规则反馈和匿名记录。两个入口在用户目标上都服务于学习，但当前导航、路由、身份键和记录体系仍然分离。

本决策统一用户侧学习体验，同时保留代码执行的安全边界，并使 Practice 结果可以进入 Workspace、复盘和学习画像。

## 2. 决策

### 2.1 产品入口与工作方式

全局产品入口收敛为：

```text
工作台 ｜ 学习 ｜ 科研
```

“用户”保留给真实账号或明确的本地个人资料能力，不用学习画像冒充用户中心。

Learning 内部提供六种可自由调用的工作方式：

```text
学习
├── 探索方向
├── 理解与讲解
├── 理解检查
├── 动手实践
├── 复盘与知识缺口
└── 笔记与学习画像
```

Research 保持独立产品入口。Learning 可以把当前问题延伸到 Research，但 Research 不成为 Learning 的必经阶段。

### 2.2 产品层与系统层使用不同层级

Practice 在产品信息架构中属于 Learning 的“动手实践”。在系统中，Practice 继续作为独立 Capability，维护代码执行、隐藏测试、判题、资源限制、原始结果和权限边界。

导航层级不写入后端 Capability 标识。Activity 和 launch 使用 `practice` 表示 Capability，使用具体 action 或 mode 区分自由运行、题目提交等行为；不使用 `learning.practice.code`。

### 2.3 Topic、Task 与工作方式

Topic 或其他 Focus 描述本次操作针对的内容；Task 描述用户目标和成功标准。两者保持独立：一个 Task 可以包含多个 Focus，没有 Task 时也可以围绕一个 Focus 学习或实践。

理解、检查、实践、复盘和笔记是工作方式，不是 Task 阶段。用户可以从任意工作方式开始，系统建议可以跳过，不自动改变 Task 状态。

### 2.4 规范路由

Learning 使用以下规范路由：

| 规范路由 | 职责 |
| --- | --- |
| `/learning` | 学习总入口与当前学习工作区 |
| `/learning/explore` | 方向探索的可分享入口 |
| `/learning/practice` | 动手实践 |
| `/learning/portrait` | 学习画像与复盘入口 |
| `/learning/notebook` | Notebook |

旧路径通过保留查询参数的 redirect 进入规范路由。`/practice` 与 `/student/practice` 指向 `/learning/practice`，`/portrait` 与 `/student/portrait` 指向 `/learning/portrait`，`/student/learning` 指向 `/learning`。兼容期使用 redirect，不继续用 rewrite 维持两个可见 URL。

### 2.5 PracticeOutcome、Activity 与 KnowledgeGap

Practice 首先持久化安全的权威结果 PracticeOutcome，再由编排层幂等派生 WorkspaceActivity。PracticeOutcome 不保存原始代码、标准输入或隐藏测试内容。

Activity 表示一次已有权威结果的用户活动，不表示结果一定正确。正常结束、错误答案、编译错误、运行错误和超时都可以形成 Activity；请求校验失败和执行服务故障不形成用户知识缺口。

KnowledgeGap 是 QuizAttempt、ConfusionMark 和 PracticeOutcome 的可追溯投影。每个信号保留来源类型和来源对象。自由运行成功不自动表示掌握，系统故障不归因于用户。

### 2.6 launch 上下文

编排层签发不透明的 `launchId`，将一次或一组 Practice 操作关联到已校验的 Workspace、可选 Task、Focus、来源 Activity 和所有者范围。外部 JSON 使用 `launchId`，Python 内部使用 `launch_id`。

`launchId` 只提供编排上下文，不传递工具权限，不替代每次运行的结果 ID 或幂等键。服务端在签发和使用时校验 Workspace、Task、来源 Activity 与所有者范围。

用户直接进入 `/learning/practice` 时，页面自动取得个人 Workspace 对应的默认 launch。旧客户端不传 `launchId` 时仍可执行现有 Practice API，但不承诺创建 WorkspaceActivity。

### 2.7 本地身份键汇合

现有标识按职责保留，不进行破坏性重键：

| 标识 | 当前职责 | 汇合方式 |
| --- | --- | --- |
| 学习 `session_id` | Notebook 与学习产物会话范围 | 继续作为内容范围，不承担所有权 |
| `profile_id / learner_id` | 学习画像与匿名 Practice 记录 | 保持同一个 UUID 值，作为学习行为聚合键 |
| `local_profile_id` | Workspace、Task、Activity 的本地所有者范围 | 作为本地编排所有者键 |
| `user_id` | 未来账号 | 账号阶段成为所有权主体，现有键继续保留来源和迁移关系 |

本地阶段由服务端 launch 同时绑定 `local_profile_id` 与 `profile_id / learner_id`。浏览器提交这些标识只提供本地恢复和隔离，不构成身份授权。

## 3. 直接后果

1. Practice 页面迁入 Learning 路由和导航，`online_compiler` 不迁入 `learning/`。
2. Practice 接入 Workspace 前先建立可迁移、可引用的 PracticeOutcome 持久化。
3. Activity 从服务端权威结果派生，前端不能提交执行成功、题目通过或 Activity 状态。
4. 复盘统一展示跨来源信号，同时保留各来源的事实含义。
5. 规范路由、launch 与身份汇合按 [Learning–Practice Integration Spec](../specs/learning-practice-integration.md) 验收。

## 4. 保持可修改的内容

本决策不固定 PracticeOutcome 表名、launch 存储形式、过期时间、KnowledgeGap 是否物化、Activity action 枚举或账号迁移表结构。这些内容在最小纵向闭环运行后写入当前架构文档。
