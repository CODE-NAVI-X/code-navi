# CLAUDE.md — Code Navi（智教码航）

本文件是 Claude Code 在本仓库工作时的项目级约束。执行入口、指令优先级、按任务加载文档、通用流程和完成状态以根目录 [AGENTS.md](AGENTS.md) 为准；本文件维护 Claude Code 需要直接掌握的项目事实与开发约束。两份文件职责不同，修改公共规则时更新 `AGENTS.md`，修改本文件所列项目事实时同步核对对应专题文档。

## 项目定位

Code Navi（智教码航）面向学生自主学习、代码练习和项目科研。用户可以从 Workspace、Task 或具体 Capability 任意开始，不强制固定学习顺序。顶层业务模块固定为：

1. 知识点学习；
2. 代码测试练习；
3. 项目/科研助手。

Workspace 与 Task 属于产品编排层，不构成第四个业务模块。对应产品模型与 Spec 已采纳，持久 Workspace、Task 和 Activity 尚未进入代码。

当前仓库已具备 Kernel 与 CLI、知识点学习、科研对话与受限检索的本地闭环；学习模块还支持逐页生成、归档、预览和导出演示文稿，并可从真实学习摘要创建可恢复、可编辑的 Research 待确认上下文。用户确认后创建带来源记录的科研会话，Research 会展示并在后续澄清中加载已确认背景。代码练习已有基于本机 Piston 的 Python 原型，尚未达到生产隔离和授权要求。复杂教师端、班级管理、完整 LMS 与 OpenMAIC 集成是当前非目标。

## 技术栈与运行基线

| 层 | 当前实现 | 说明 |
| --- | --- | --- |
| 后端 | Python 3.11+、FastAPI | 依赖以 `pyproject.toml` 为准；演示文稿使用 SSE 流式返回 |
| 前端 | Next.js 16、React 19、TypeScript、Tailwind CSS 4 | 位于 `frontend/`，前端只通过 HTTP API 访问后端 |
| 业务持久化 | SQLAlchemy + SQLite、Alembic | 模块共用 `code_navi.db.Base`；schema 变更必须新增 revision |
| Kernel | `src/kernel/` 自研 Agent Runtime | 统一工具注册、上下文、权限与 Event；Provider 适配器隔离厂商 SDK |
| Provider | Mock（默认）、OpenAI、DeepSeek | 在线 Provider 必须显式配置凭据 |
| Web 容器 | FastAPI 镜像、Next standalone、Caddy | `compose.web.yaml` 是当前特定 NAS 的受限部署骨架，不代表生产可用 |
| 练习执行器 | Piston、Python 3.12 | `compose.yaml` 启动 privileged Piston；只计为本地原型 |

外部规划中的 PostgreSQL、pgvector、Redis、MinIO、Vue 3 与 OpenMAIC 不是当前仓库事实。实现和文档以实际代码、配置与专题文档为准。

## 关键入口与目录

| 任务 | 先定位 |
| --- | --- |
| CLI 问答 | `src/code_navi/cli.py`、`application.py`、`context.py` |
| 学习 API 与演示文稿 | `src/code_navi/learning/`、`frontend/lib/api/learning.ts`、学习页面 |
| Python 练习与判题 | `src/code_navi/online_compiler/`、`frontend/lib/api/compiler.ts`、练习页面、`tests/online_compiler/` |
| 科研对话与检索 | `src/code_navi/research/`、`frontend/lib/api/research.ts`、科研页面 |
| 跨模块上下文 | `src/code_navi/context_transfer/`、`frontend/lib/api/context-transfers.ts`、Research 确认页面 |
| 运行时科研 Skill | `src/code_navi/research/skills/` 是唯一 Skill 文档位置 |
| Provider | `src/code_navi/providers.py`、`src/kernel/adapters/` |
| 数据库 | `src/code_navi/db.py`、模块 ORM、`migrations/` |
| 本地 Web/API | `src/code_navi/server.py`、`scripts/dev.py`、`dev-start.cmd`、`dev-stop.cmd` |
| 容器运行 | `compose.yaml`、`compose.web.yaml`、对应 Dockerfile 与 `Caddyfile` |

## 开发约束

1. **先跑最小闭环**：在实际工作树定位入口、公开接口和最近测试，先跑通最小、可观察、可纠错的端到端闭环，再补分层与测试。首个闭环前不冻结契约、不预建完整异常矩阵。
2. **只修改受影响内容**：任务完成后立即交付；不为此新建平行目录，不机械补齐无关文档或验证。
3. **数据库变更**：新增或修改 ORM schema 时新增 Alembic revision，不改写已发布 revision；验证空库升级、受影响旧库升级和数据保留，并更新迁移与直接相关模块测试。
4. **事实边界**：Provider 文本不得冒充执行结果、工具事实或外部写入；不得通过删除断言、放宽预期、吞异常或跳过测试隐藏故障。
5. **敏感数据**：密钥、完整凭据、个人信息和未脱敏业务数据不得进入仓库、日志、Event、测试数据或模型上下文。
6. **高风险能力**：代码执行、在线 Provider、真实联网写入和远程仓库操作先用 Mock、dry-run 或隔离资源试运行；接触真实外部资源前展示目标和动作并取得相应确认。
7. **会话隔离**：按学习 `session_id` 隔离的笔记、演示文稿和来源上下文读取必须限定请求会话；科研主流程按 `conversation_id` 恢复；练习记录按匿名 `learner_id` 查询。浏览器标识不代表用户身份或授权。
8. **科研边界**：规则拥有画像、研究计划、确认和失败回退；模型个性化与外部检索只通过独立确认入口触发。代码草案是预览文本，不写入项目、不安装依赖、不执行命令。
9. **容器状态**：`compose.yaml` 是 CLI + Piston 本地基线；`compose.web.yaml` 使用本地标签、特定 NAS 域名和证书挂载，但尚未接入 Piston。Basic Auth 不替代应用级认证和资源授权。
10. **文档归属**：产品事实、架构接口、开发方法和部署状态分别进入 `docs/product/`、`docs/architecture/`、`docs/development/`、`docs/deployment/`；重要选择、可验收行为和实施状态分别进入 `docs/decisions/`、`docs/specs/`、`docs/plans/`；运行时 Skill 留在应用源码目录。
11. **模块间上下文传递**：跨 Capability 需要传递具体内容时，必须复用既有 `context-transfer` 确认流程（服务端以已归档模块产物为来源记录）。Workspace、Task 与 Activity 引用只组织归属，不能替代内容确认；`FlowPayload` 和 URL 参数只可作为即时交接与刷新回退。新增跨模块入口先检查现有 `src/code_navi/context_transfer/` 服务。
12. **服务端权威**：判分、审核等涉及信任边界的接口，评分依据（标准答案、满分、评分要点）必须由服务端从已归档数据加载；请求只携带对象 id 与用户提交内容，客户端不得重新提交评分标准。归档资源不存在或跨会话时返回 404。
13. **打包资源**：运行时读取的资源文件（如 `MML2OMML.XSL`、模板、字体）必须列入 `pyproject.toml` 的 `[tool.setuptools.package-data]`；新增此类资源需同时添加「从构建 wheel 断言资源存在」的回归测试，避免 wheel 安装后静默退化为字面文本。
14. **前端质量门**：`npm run lint`（react-hooks/set-state-in-effect）与 `npx tsc --noEmit`、`npm run build` 均为 CI 质量门；不要在 effect 内同步调用 setState。数据驱动的状态重置优先用「以变化键重挂载子组件」或事件处理器内重置，而不是 `useEffect` 里 setState。
15. **导出去重**：同一条内容（参考答案、解析、来源等）在导出/渲染结果中只出现一次；若某类型题目「参考答案」即「解析」，不得再单独输出解析段。修改导出逻辑时用断言计数验证无重复内容。

## 本地运行

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev,server]"
cd frontend
npm ci
cd ..
.venv\Scripts\python.exe -m alembic upgrade head
python scripts/dev.py
```

默认 Provider 为离线 Mock。在线 Provider 使用 `code-navi configure-provider --provider deepseek` 或显式环境配置，凭据保存在已忽略的本机配置中。

CLI Compose 与当前受限 Web Compose 的准确命令、数据路径和前置条件见 [本地运行与容器基线](docs/deployment/local.md)。公网服务、身份授权、生产数据和回滚条件见 [生产准入](docs/deployment/production.md)。

## 文档导航

按任务选择最小文档组合的规则以 [AGENTS.md](AGENTS.md) 为准：

| 领域 | 文档 |
| --- | --- |
| 产品范围与路线 | `docs/product/scope.md`、`docs/product/roadmap.md` |
| 产品设计 | `docs/decisions/`、`docs/specs/`、`docs/plans/`；入口见 `docs/README.md` |
| 架构 | `docs/architecture/system.md`、`docs/architecture/kernel.md`、`docs/architecture/frontend.md` |
| 开发与测试 | `docs/development/workflow.md`、`docs/development/testing.md`、`docs/development/high-risk-capabilities.md` |
| 部署 | `docs/deployment/local.md`、`docs/deployment/production.md` |
