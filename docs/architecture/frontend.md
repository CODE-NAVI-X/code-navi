# Web 与前端架构边界

## 1. 当前实现

前端位于 `frontend/`，使用 Next `16.3.0`、React `19.2.4`、TypeScript、Tailwind CSS 4 和 npm 锁文件。当前页面为：

| 页面 | 当前能力 |
| --- | --- |
| `/` | 输入目标创建个人 Workspace 中的 Task、继续最近 Task、进入 Workspace；当前兼容页面仍直接展示三个 Capability 链接 |
| `/learning` | 调用学习 explain API，展示讲解与引文、读取普通笔记和可追溯研究笔记，并逐页生成、预览和导出演示文稿 |
| `/workspaces/[workspaceId]` | 恢复一个 Workspace、创建同一语义的 Task，并显示有界的安全 Activity 时间线 |
| `/tasks/[taskId]` | 恢复 Task、显示其 Learning Activity 时间线，并带上下文进入 Learning |
| `/research` | 创建或恢复动态科研对话；显示已确认的 Learning 上下文、画像、研究计划和检索计划；支持选择 Evidence 并保存到当前 Learning Notebook |
| `/research/confirm/[contextId]` | 恢复 Learning 创建的待传递上下文，允许修改、删除补充内容、保存或取消；确认后创建科研会话并跳转 `/research` |
| `/learning/practice` | Learning 内“动手实践”；调用在线编译 API，分别取得运行与提交 launch，展示规则与可选 AI 反馈，并读取匿名兼容记录 |
| `/learning/portrait` | 学习画像与复盘；按匿名 profile 展示画像，并按来源聚合 QuizAttempt、ConfusionMark 与 PracticeOutcome |

规范路由为 `/learning`、`/learning/explore`、`/learning/practice`、`/learning/portrait` 和 `/learning/notebook`。`/practice`、`/student/practice`、`/portrait`、`/student/portrait` 与 `/student/learning` 保留查询参数并 redirect 到对应规范路由；`/student/research` 继续作为 Research 兼容路径。目标行为见 [Learning–Practice Integration Spec](../specs/learning-practice-integration.md)。Web 是当前本地产品宿主；CLI 仍用于独立验证 Runtime 路径。

`/learning` 以 [Learning Entry Spec](../specs/learning-entry.md) 定义的三个入口区块组织：发起学习、继续最近学习和探索计算机方向。六大领域是稳定导航，方向使用单一稳定标识和多对多 `domainIds` 归属；当前领域和已选方向只保存在入口组件的探索上下文，不进入 Learning 快照或跨模块状态。最近学习通过有界的后端查询恢复原始 Notebook 讲解，并明确区分空记录、加载失败和来源失效。

## 2. API 边界

页面只能通过 `frontend/lib/api/` 调用 FastAPI，不得直接调用 Provider、Kernel core、数据库、代码执行器或远程仓库 SDK。

默认 API 地址为 `http://127.0.0.1:8000`，可用 `NEXT_PUBLIC_CODE_NAVI_API_URL` 配置；`NEXT_PUBLIC_API_BASE` 仅作为现有兼容项。前端类型镜像后端 Pydantic schema，后端契约变化时两侧和相应测试必须同步。

页面至少明确展示加载、成功、失败和需要用户主动触发的状态。服务器内部错误只显示安全的公开信息；网络错误不得伪装成空结果或成功。

Evidence 卡片逐条显示来源平台、标题、年份、证据级别、摘要状态、全文状态、规则相关性和原始链接。研究分析返回 Evidence 引用时，页面提供回到对应来源的链接。

演示文稿页面显示每次流式结果的规则、模型、混合或降级来源；读取归档时始终携带当前学习 `session_id`。研究页面默认展示规则难点与规则实验方案，模型个性化和代码草案预览分别由独立按钮触发。

练习页面不得在浏览器判定题目正确性或构造隐藏测试。执行状态来自 Piston 适配器，题目结果来自服务端判题，AI 只提供独立标记的解释或引导。Piston 不可用时显示执行服务失败，不回退为前端模拟成功。

## 3. 浏览器状态

1. 学习 `session_id`、科研 `conversation_id`、练习匿名 `learner_id` 和编排层 `local_profile_id` 分别保存在 `localStorage`，用于同一浏览器内恢复；旧科研 `session_id` 会被清除。`local_profile_id` 只隔离本地资料，不是身份、授权或跨设备账号。
2. 不在 `localStorage` 保存凭据、Provider 密钥、原始练习代码、完整研究数据或工具授权。
3. `frontend/lib/store/flow-store.ts` 的 `FlowPayload` 只服务 Learning → Practice 练习主题的即时交接；跳转 URL 携带知识点名称、标识和学习会话，`localStorage` 保存同一份轻量数据用于刷新回退，不表示持久 Task，也不保存源码、凭据或工具权限。服务端 launch 承担 Workspace、可选 Task、Focus 和来源 Activity 的编排关系；`FlowPayload` 只保留为短期界面恢复缓存。
4. Learning → Research 使用服务端 `context-transfer.v1`；浏览器从 URL 读取上下文 ID，并携带当前学习 `session_id` 恢复、编辑、取消或确认。确认请求直接提交页面最终数据，返回的 `conversation_id` 写入现有科研会话恢复键；Research 页面只根据恢复响应中的 `context_provenance` 显示来源主题、摘要和保留内容，不从 Learning 页面状态重建背景。
5. Workspace 上下文通过站内 URL 的 `workspace_id`、`task_id` 和相对 `return_to` 恢复；`local_profile_id` 不进入页面 URL。上下文加载失败时显示错误和返回入口，不把请求静默降级为独立 Learning。

`AppShell` 显示工作台、学习和科研三个全局入口；访问 `/learning/*` 时活动项统一显示“学习”，Practice 页面内部继续明确标示执行与判题来源。真实账号能力落地前不把学习画像显示为“用户”入口。AppShell 继续显示轻量 Workspace/Task 上下文条和明确返回入口。

`profile_id / learner_id` 是浏览器生成并复用的同一个 UUID，用于聚合学习画像和筛选 Practice 本地原型记录，不是身份或授权凭据。`local_profile_id` 继续负责 Workspace 所有者范围。规范集成由服务端 launch 绑定两者，不在浏览器中把它们重键成一个字段；账号、跨设备恢复和多用户隔离由后端身份与授权处理。

## 4. 模块交互

1. Learning 与 Research 可以从全局入口独立进入；Practice 可以从 `/learning/practice` 或带上下文 launch 直接开始。建议跳转必须可跳过。
2. Workspace、Task 和 Activity 引用只组织归属。跨模块需要传递具体内容时，只传递当前目标所需字段，标明来源和目标模块，并继续使用用户可查看、确认的传递边界。
3. 模块切换不继承工具权限、完整对话或 Runtime 会话。
4. 代码执行、联网写入和仓库操作必须由后端受控能力完成，并在界面展示目标、动作与必要确认。

## 5. 开发与验收

前端依赖和脚本以 `frontend/package.json`、`package-lock.json` 为准：

```powershell
cd frontend
npm ci
npm run lint
npm run build
```

普通页面修改先运行受影响的前端检查；API 接线变化还要验证对应后端路由。生产准入见 [生产准入](../deployment/production.md)。
