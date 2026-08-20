# Workspace–Task–Capability 产品模型

| 状态 | 日期 |
| --- | --- |
| 已采纳 | 2026-08-19 |

## 1. 背景

Code Navi 已允许用户独立进入 Learning、Practice 或 Research，但长期上下文分别依赖学习会话、科研对话、匿名练习标识和浏览器临时状态。用户围绕课程、项目或研究目标持续工作时，缺少一个能够跨模块恢复活动与产物来源的产品层。

新的编排层需要保存长期上下文，又不能把三个业务模块改造成固定流水线，也不能扩大现有工具权限和跨模块数据传递范围。

## 2. 决策

### 2.1 产品实体与职责

Workspace 与 Task 是一等产品实体。Workspace 组织长期上下文，Task 聚焦一个目标及其成功标准。Learning、Practice、Research 是可独立使用的业务 Capability，继续维护各自的数据、接口和权限边界。

Activity 是编排层中的跨模块索引。它记录一次已经持久化、用户可识别的模块结果及其安全摘要，不接管模块产物的事实来源，也不替代 Runtime Event 或请求日志。Activity 由服务端从模块结果幂等派生，前端不能自行声明模块执行成功。

### 2.2 归属关系

1. 每个 Task 只属于一个 Workspace。
2. 每个 Activity 只属于一个 Workspace，并且可以不关联 Task。
3. Activity 关联 Task 时，两者必须属于同一 Workspace。
4. Capability-first 活动关联其他 Workspace 中的 Task 时，系统原子更新 Activity 的 Workspace 与 Task 引用；模块原始产物不移动、不复制。
5. Workspace 可以没有 Task，Task 也可以只使用一种 Capability。

### 2.3 三种入口

产品同时支持 Task-first、Workspace-first 和 Capability-first。Task-first 在没有显式 Workspace 时使用个人工作区；Capability-first 允许用户先完成活动，再整理到现有或新建 Task。任何入口都不能成为使用其他入口的前置条件。

### 2.4 生命周期与完成

Task 只保存目标、成功标准和生命周期状态，不保存 `learning / practice / research` 形式的当前阶段。Task 是否完成由用户目标和成功标准决定，不根据访问过的模块数量或模块覆盖率计算。

### 2.5 建议、权限与上下文

编排建议始终可以跳过，不自动改变 Task 状态，不自动调用模型、网络或代码执行。模块切换不继承工具权限、完整会话或长期记忆。

需要携带具体内容的跨模块传递继续使用用户可查看和确认的 `context-transfer.v1`。Workspace、Task 和 Activity 引用只提供组织关系，不替代内容传递确认。

### 2.6 本地所有权

在尚无登录系统的本地产品中，浏览器生成的稳定 `local_profile_id` 只用于取得个人工作区和隔离本机数据。它不代表身份认证、授权或跨设备账号。

## 3. 直接后果

1. 根页面将承载创建目标、继续最近 Task、进入 Workspace 和直接使用 Capability 的入口，不再固定跳转到 Learning。
2. 学生公共布局将逐步承载统一工作上下文和轻量 AppShell；各模块仍负责自己的内部流程。
3. `FlowPayload` 只保留为同一浏览器中的即时恢复缓存，不再承担持久工作上下文。
4. 统一时间线只保存模块产物引用和允许跨模块展示的摘要。原始练习代码、完整科研对话、隐藏测试内容和工具权限不进入 Activity。

## 4. 保持可修改的内容

本决策不固定数据库字段名、HTTP 路径、Activity 动作枚举、历史数据导入策略或保留期限。这些内容在最小纵向切片跑通后，根据实际接口和查询需求写入架构文档。
