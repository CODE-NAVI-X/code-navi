# Learning–Practice 集成计划

| 状态 | 关联 Spec |
| --- | --- |
| 当前 Epic | [Learning–Practice Integration](../specs/learning-practice-integration.md) |

## 1. 目标与完成条件

将 Practice 作为 Learning 的“动手实践”接入规范路由、Workspace Activity、复盘和学习画像，同时保持在线编译器的独立安全边界。完成时，带上下文与直接进入两条路径都产生可恢复的权威 PracticeOutcome，并按 Spec 派生 Activity 和知识缺口信号。

## 2. 实施顺序

| 切片 | 范围 | 状态 |
| --- | --- | --- |
| 文档与口径汇合 | Decision、Spec、产品范围、架构现状与路线一致 | 已完成 |
| PracticeOutcome 与 launch | 安全结果持久化、身份键绑定、默认 launch、Activity 派生 | 本地验证完成 |
| Learning 路由与导航 | 规范路由、兼容 redirect、学习内部工作方式、活动项 | 本地验证完成 |
| 复盘投影 | QuizAttempt、ConfusionMark、PracticeOutcome 的可追溯聚合 | 本地验证完成 |
| 兼容收敛 | 旧 URL 已 redirect；FlowPayload 和旧记录路径保留兼容 | 进行中 |

## 3. 最小纵向闭环

第一条闭环已经通过，并扩展到题目提交：

1. 用户直接进入 `/learning/practice`，页面取得个人 Workspace 的默认 launch。
2. 用户运行一段 Python；执行器返回权威结果。
3. 服务端持久化安全 PracticeOutcome，并在同一业务提交中派生无 Task Activity。
4. 刷新个人 Workspace 后仍能看到 Activity，并能定位到安全结果摘要。
5. 运行错误形成复盘信号；Piston 服务故障不形成用户知识缺口。

题目提交、Task 上下文和跨来源复盘已经接入；旧客户端无 launch 执行、独立 CompilerRecord 与内存 Submission 继续作为兼容路径。

## 4. 预计修改范围

| 领域 | 预计路径 |
| --- | --- |
| Practice 结果 | `src/code_navi/online_compiler/`、共享数据库模型与迁移 |
| 编排接线 | `src/code_navi/workspaces/`、FastAPI router |
| Learning 页面 | `frontend/app/(student)/learning/`、`frontend/components/` |
| 前端 API 与状态 | `frontend/lib/api/`、现有 flow store |
| 验证 | 相关后端 API、迁移、Workspace 与前端路由测试 |

适配职责放在现有 Practice 与 Workspace 边界附近，不为名称预建独立 `adapters/` 工程。

## 5. 接口与数据边界

1. `launchId` 是可选的加法字段；旧 execute/submit 请求保持可执行。
2. launch 绑定 `local_profile_id` 与 `profile_id / learner_id`，不把二者重键为同一个数据库字段。
3. `launchId` 不复用为 attempt ID；网络重试与主动重做使用独立幂等语义。
4. PracticeOutcome 只保存复盘和 Activity 所需的安全字段，不保存源码、stdin 或隐藏测试内容。
5. Activity 记录权威结果的存在和来源，不使用“成功”代替 verdict、category 或 score。

## 6. 最小验证

1. 运行成功、语法错误、运行错误与执行服务故障各走一次真实 API 边界。
2. 验证个人 Workspace、显式 Workspace 和 Task 的归属，以及跨所有者资源拒绝。
3. 验证同一结果的重试幂等和同一 launch 下的多次主动尝试。
4. 验证 Activity、复盘响应和数据库均不包含源码、stdin 与隐藏测试。
5. 最后运行受影响的迁移、后端测试和前端 lint/build。

## 7. 性能影响

每次 Practice 操作增加一次有界的 launch 查询，以及一次 PracticeOutcome 与 Activity 的数据库提交。launch 按主键读取；Activity 继续使用已有 Workspace、Task 时间索引。页面不因进入 Learning 而预取执行器、题目集或完整复盘历史。

## 8. 退出条件

Spec 的规范路由、直接进入、带 Task 进入、权威结果持久化、Activity、复盘来源和隐私边界均已在本地闭环验证。当前状态是本地验证完成，不表示账号授权、跨设备恢复或生产代码执行已经可用。
