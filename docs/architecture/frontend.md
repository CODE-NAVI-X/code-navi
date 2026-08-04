# Web 与前端架构边界

## 1. 当前实现

前端位于 `frontend/`，使用 Next `16.2.10`、React `19.2.4`、TypeScript、Tailwind CSS 4 和 npm 锁文件。当前页面为：

| 页面 | 当前能力 |
| --- | --- |
| `/learning` | 调用学习 explain API，展示讲解与引文，并读取当前学习会话笔记 |
| `/research` | 创建或恢复动态科研对话，展示画像、离线规则研究计划、Provider 状态和检索计划，并显式触发与恢复 evidence bundle |
| `/practice` | 展示接收到的原型上下文；按钮仅提示功能未上线 |

`/student/learning`、`/student/practice` 和 `/student/research` 通过 Next rewrite 映射到上述页面。Web 是当前本地产品宿主；CLI 仍用于独立验证 Runtime 路径。

## 2. API 边界

页面只能通过 `frontend/lib/api/` 调用 FastAPI，不得直接调用 Provider、Kernel core、数据库、代码执行器或远程仓库 SDK。

默认 API 地址为 `http://127.0.0.1:8000`，可用 `NEXT_PUBLIC_CODE_NAVI_API_URL` 配置；`NEXT_PUBLIC_API_BASE` 仅作为现有兼容项。前端类型镜像后端 Pydantic schema，后端契约变化时两侧和相应测试必须同步。

页面至少明确展示加载、成功、失败和需要用户主动触发的状态。服务器内部错误只显示安全的公开信息；网络错误不得伪装成空结果或成功。

## 3. 浏览器状态

1. 学习 `session_id` 和科研 `conversation_id` 分别保存在 `localStorage`，用于同一浏览器内恢复；旧科研 `session_id` 会被清除。
2. 不在 `localStorage` 保存凭据、Provider 密钥、完整研究数据或工具授权。
3. `frontend/lib/store/flow-store.ts` 的 `FlowPayload` 是进程内原型状态，刷新页面会丢失。
4. 当前跨模块接力尚未提供传递前查看、编辑和清除，不得作为稳定数据契约。

需要身份绑定、跨设备恢复或多用户隔离时，由后端持久化和授权处理，不扩张浏览器状态承担这些职责。

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
