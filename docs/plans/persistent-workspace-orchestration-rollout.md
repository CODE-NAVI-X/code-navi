# Persistent Workspace Orchestration 实施计划

| 状态 | 关联 Spec |
| --- | --- |
| 当前 Epic | [持久工作区与自由编排](../specs/persistent-workspace-orchestration.md) |

## 1. 交付策略

每次只接入一个真实 Capability，先跑通可恢复的端到端闭环，再确定下一阶段需要稳定的 API 和数据字段。Persistent Workspace Foundation 与 Practice Capability-first 已完成本地验证；当前后续项是 Research 接入、确定性建议与兼容收敛。

| 阶段 | 范围 | 状态 |
| --- | --- | --- |
| 文档基线 | 产品模型、Spec、计划与产品范围对齐 | 已完成 |
| Persistent Workspace Foundation | Workspace、Task、Learning Activity 与基础页面 | 本地验证完成 |
| Practice Capability-first | Learning 内动手实践、默认 launch、权威结果与 Activity | 本地验证完成 |
| Research 可选接入 | Research 来源引用、显式上下文确认与时间线 | 待实现 |
| 知识缺口与可选建议 | 三来源复盘投影已完成；确定性下一步建议待实现 | 进行中 |
| 交互收敛 | 统一返回语义、导航状态与兼容状态清理 | 待实现 |

## 2. 已完成纵向切片

### 2.1 后端持久化与服务

新增 Workspace、Task 和 Workspace Activity 的最小模型及 Alembic revision。服务端负责幂等取得个人工作区、校验 Workspace 归属，并在 Learning 成功保存产物后幂等创建 Activity。模型字段和路由形状在实现前通过现有 FastAPI 与 SQLAlchemy 约定确认，不在本计划中冻结。

实现路径：

```text
src/code_navi/workspaces/
src/code_navi/learning/
src/code_navi/server.py
migrations/versions/
tests/
```

### 2.2 Web 最小入口

根页面提供输入目标、继续最近 Task、进入 Workspace 和直接使用 Capability 的入口。新增 Workspace 页面与 Task 概览页，并在公共学生布局中加入轻量工作上下文。Learning 同时支持带上下文进入和无 Task 独立进入。

实现路径：

```text
frontend/app/page.tsx
frontend/app/(student)/layout.tsx
frontend/app/(student)/workspaces/
frontend/app/(student)/tasks/
frontend/app/(student)/learning/page.tsx
frontend/lib/api/
```

### 2.3 最小验证

1. 后端验证 Task-first、Workspace-first、个人工作区幂等性和 Activity 归属规则。
2. 迁移验证覆盖空库与当前 schema 升级。
3. 前端运行相关 lint 与 build。
4. 手动走通 Task-first、Workspace-first 和直接 Learning，并刷新恢复。

### 2.4 退出条件

第一版只有在 Spec 第 6.2 节全部成立后完成。Practice、Research、推荐引擎和历史数据导入不作为该切片的退出条件。

## 3. 后续切片

### 3.1 Practice Capability-first（已完成）

Practice 按 [Learning–Practice 集成计划](learning-practice-integration-rollout.md) 先持久化安全的权威 PracticeOutcome，再派生 Activity。正常结束、错误答案和用户代码错误都可以形成 Activity；请求校验失败和执行服务故障不形成用户知识缺口。用户可以将无 Task Activity 整理到现有或新 Task；整理只更新索引归属，不复制源代码、输入或隐藏测试。

### 3.2 Research 可选接入

Research Conversation 和用户保存的 Evidence 产生来源 Activity。Task 引用不替代 `context-transfer.v1`，也不继承联网、模型或代码执行权限。

### 3.3 知识缺口与可选建议（复盘投影已完成）

当前已将 QuizAttempt、ConfusionMark 与 PracticeOutcome 投影为保留来源的知识缺口。后续根据已保存事实运行确定性推荐；推荐只提供少量下一步，不自动调用 Capability，Task 完成仍由目标和成功标准决定。

### 3.4 交互与兼容收敛

统一 Learning 与 Research 产品入口的上下文条和返回语义；Practice 作为 Learning 内部工作方式继续显示其独立执行来源。规范路由稳定后，将 `FlowPayload` 收敛为即时恢复缓存，并在实现事实变化后更新 `architecture/system.md` 与 `architecture/frontend.md`。

## 4. 已知边界风险

| 风险 | 当前处理 |
| --- | --- |
| 本地 profile 被误当作身份授权 | API 和页面明确其为本地隔离标识，生产身份另行设计 |
| Activity 与 Task 跨 Workspace 不一致 | 关联操作在服务端事务中同时校验并更新 Activity 归属 |
| 时间线取代模块事实来源 | Activity 只保存引用与安全摘要，详情仍由模块 API 返回 |
| 时间线增长影响读取 | 实现首期按 Workspace、Task 和时间建立索引并使用有界分页 |
