# Web 与前端架构边界

## 1. 当前实现

前端位于 `frontend/`，使用 Next `16.3.0`、React `19.2.4`、TypeScript、Tailwind CSS 4 和 npm 锁文件。当前页面为：

| 页面 | 当前能力 |
| --- | --- |
| `/learning` | 调用学习 explain API，展示讲解与引文、读取普通笔记和可追溯研究笔记，并逐页生成、预览和导出演示文稿 |
| `/research` | 创建或恢复动态科研对话；显示已确认的 Learning 上下文、画像、研究计划和检索计划；支持选择 Evidence 并保存到当前 Learning Notebook |
| `/research/confirm/[contextId]` | 恢复 Learning 创建的待传递上下文，允许修改、删除补充内容、保存或取消；确认后创建科研会话并跳转 `/research` |
| `/practice` | 调用在线编译 API，运行 Python、提交服务端题目、展示规则与可选 AI 反馈，并读取匿名学习记录 |

`/student/learning`、`/student/practice` 和 `/student/research` 通过 Next rewrite 映射到上述页面。Web 是当前本地产品宿主；CLI 仍用于独立验证 Runtime 路径。

## 2. API 边界

页面只能通过 `frontend/lib/api/` 调用 FastAPI，不得直接调用 Provider、Kernel core、数据库、代码执行器或远程仓库 SDK。

默认 API 地址为 `http://127.0.0.1:8000`，可用 `NEXT_PUBLIC_CODE_NAVI_API_URL` 配置；`NEXT_PUBLIC_API_BASE` 仅作为现有兼容项。前端类型镜像后端 Pydantic schema，后端契约变化时两侧和相应测试必须同步。

页面至少明确展示加载、成功、失败和需要用户主动触发的状态。服务器内部错误只显示安全的公开信息；网络错误不得伪装成空结果或成功。

Evidence 卡片逐条显示来源平台、标题、年份、证据级别、摘要状态、全文状态、规则相关性和原始链接。研究分析返回 Evidence 引用时，页面提供回到对应来源的链接。

演示文稿页面显示每次流式结果的规则、模型、混合或降级来源；读取归档时始终携带当前学习 `session_id`。研究页面默认展示规则难点与规则实验方案，模型个性化和代码草案预览分别由独立按钮触发。

练习页面不得在浏览器判定题目正确性或构造隐藏测试。执行状态来自 Piston 适配器，题目结果来自服务端判题，AI 只提供独立标记的解释或引导。Piston 不可用时显示执行服务失败，不回退为前端模拟成功。

## 3. 浏览器状态

1. 学习 `session_id`、科研 `conversation_id` 和练习匿名 `learner_id` 分别保存在 `localStorage`，用于同一浏览器内恢复；旧科研 `session_id` 会被清除。
2. 不在 `localStorage` 保存凭据、Provider 密钥、原始练习代码、完整研究数据或工具授权。
3. `frontend/lib/store/flow-store.ts` 的 `FlowPayload` 只服务 Learning → Practice 当前任务；跳转 URL 携带知识点名称、标识和学习会话，`localStorage` 保存同一份轻量数据用于刷新回退，不保存源码、凭据或工具权限。Practice 提供“清除当前主题 / 自由练习”动作，同时清除内存和浏览器持久化任务；没有 URL 或持久化任务时显示自由练习，不虚构当前主题。
4. Learning → Research 使用服务端 `context-transfer.v1`；浏览器从 URL 读取上下文 ID，并携带当前学习 `session_id` 恢复、编辑、取消或确认。确认请求直接提交页面最终数据，返回的 `conversation_id` 写入现有科研会话恢复键；Research 页面只根据恢复响应中的 `context_provenance` 显示来源主题、摘要和保留内容，不从 Learning 页面状态重建背景。

顶层学习、练习和科研路由共用 `AppShell`，在桌面与窄屏持续显示三个独立入口和当前活动模块。各模块内部导航继续负责模块内步骤，不替代顶层模块位置感。

练习 `learner_id` 是浏览器生成的 UUID，只用于筛选本地原型记录，不是身份或授权凭据。需要身份绑定、跨设备恢复或多用户隔离时，由后端持久化和授权处理，不扩张浏览器状态承担这些职责。

## 4. 模块交互

1. 三个模块均可独立进入，建议跳转必须可跳过。
2. 跨模块只传递当前任务所需字段，并标明来源和目标模块。
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
