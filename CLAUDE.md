# CLAUDE.md — Code Navi（智教码航）

本文件是 Claude Code 在本仓库工作时的项目级约束。执行入口（指令优先级、按任务加载文档、通用执行流程、仓库底线、完成状态定义）以根目录 [AGENTS.md](AGENTS.md) 为准；本文件只补充 AGENTS.md 未覆盖的项目事实与开发约束，冲突时遵循 AGENTS.md 声明的优先级。

## 项目定位

Code Navi（智教码航）面向学生自主学习、代码练习和项目科研，让用户直接进入当前任务所需模块，不强制固定学习顺序。顶层模块固定为：

1. 知识点学习；
2. 代码测试练习；
3. 项目/科研助手。

模块是业务边界，不等同于页面、路由或代码目录。当前仓库已具备 Kernel 与 CLI、知识点学习、科研对话与受限检索的本地闭环；代码练习仍是占位能力。复杂教师端、班级管理、完整 LMS 与 OpenMAIC 集成是当前非目标。

## 技术栈（以仓库实际代码为准）

| 层 | 当前实现 | 说明 |
| --- | --- | --- |
| 后端 | Python 3.11+、FastAPI | 依赖以 `pyproject.toml` 为准；SSE 流式返回 |
| 前端 | Next.js 16、React 19、TypeScript、Tailwind CSS 4 | 位于 `frontend/`，与后端解耦 |
| 业务持久化 | SQLAlchemy + SQLite（`.code-navi/learning_poc.db`）、Alembic | 模块共用 `code_navi.db.Base`；schema 变更必须新增 revision |
| Kernel | `src/kernel/` 自研 Agent Runtime | 统一工具注册、上下文与权限；Provider 适配器隔离厂商 SDK |
| Provider | Mock（默认）、OpenAI、DeepSeek | 在线 Provider 必须显式配置凭据 |
| Event | JSONL 事件日志 | 运行与审计唯一事实源，不作为业务数据库 |

注意：外部《技术栈选型》文档规划的是 PostgreSQL + pgvector、Redis、MinIO、Vue 3 与 OpenMAIC 方向；这些是演进目标或参考，**不是当前仓库事实**。编写代码与文档时以实际实现为准，不得把规划描述为已实现。

## 关键入口与目录

| 任务 | 先定位 |
| --- | --- |
| CLI 问答 | `src/code_navi/cli.py`、`application.py`、`context.py` |
| 学习 API | `src/code_navi/learning/`、`frontend/lib/api/learning.ts`、学习页面 |
| 科研对话与检索 | `src/code_navi/research/`（`conversation_agent.py`、`conversation_service.py`、`academic.py` 等）、科研页面 |
| Provider | `src/code_navi/providers.py`、`src/kernel/adapters/` |
| 数据库 | `src/code_navi/db.py`、`migrations/` |
| 本地 Web/API | `src/code_navi/server.py`、`scripts/dev.py`、`dev-start.cmd` |

## 开发约束

1. **先跑最小闭环**：在实际工作树定位入口、公开接口和最近测试，先跑通最小、可观察、可纠错的端到端闭环，再补分层与测试。首个闭环前不冻结契约、不预建完整异常矩阵。
2. **只修改受影响内容**：任务完成后立即交付；不为此建全新目录结构，不机械补齐无关文档或验证。
3. **数据库变更**：新增或修改 ORM schema 时新增 Alembic revision（不改写已发布 revision），验证空库 `alembic upgrade head`、旧库升级和数据保留，更新 `tests/test_migrations.py`。
4. **提交与合并**：分支名 `<type>/<short-topic>`；提交使用 Conventional Commits `<type>(<scope>): <description>`。一次提交只解决一个可解释、可审查、可回退的问题。PR 需说明问题与范围、关键实现、实际验证、受影响接口。
5. **代码规则**：公开接口明确命名、类型标注和必要 docstring；分层清晰，不复制已有实现形成平行路径；不绕过公开边界。Python 行宽 100 并用 Ruff；前端使用现有 ESLint/TS 配置。
6. **事实边界**：不伪造成功；Provider 文本不得冒充执行结果或工具事实；外部操作状态以 `ToolResult` 或执行器结果为准；不得通过删除断言、放宽预期、吞异常或跳过测试隐藏故障。
7. **敏感数据**：密钥、完整凭据、个人信息和未脱敏业务数据不得进入仓库、日志、Event、测试数据或模型上下文。
8. **知识库约束**（来自外部设计，已部分落地到科研检索）：静态知识负责正确性，动态检索只做补充；动态结果必须带来源、时间戳和可信度；优先白名单数据源，学术检索需用户确认后触发（当前 OpenAlex、Crossref、arXiv）。
9. **高风险能力**：代码执行、在线 Provider、真实联网写入或远程仓库操作属高风险能力，先用 Mock、dry-run 或隔离资源试运行，接触真实外部资源前展示目标和动作并取得确认。详见 `docs/development/high-risk-capabilities.md`。
10. **会话隔离**：按 session 隔离的数据（notebook 及其子资源，如 presentation 回读）的所有读取接口，必须用请求方 `session_id` 限定查询范围，与既有接口（如 notebook list）保持一致；不得按 id 全表扫描取数。新增或改动此类接口时，同步补一条跨 session 读取返回 404 的测试。

## 本地运行

```powershell
# 后端环境
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev,server]"

# 前端依赖
cd frontend
npm ci

# 启动前迁移数据库（必须）
cd ..
.venv\Scripts\python.exe -m alembic upgrade head

# 启动 FastAPI :8000 与 Next :3000
python scripts/dev.py
# 或 Windows： .\dev-start.cmd
```

默认 Provider 为离线 Mock。在线 Provider 用 `code-navi configure-provider --provider deepseek` 显式配置，凭据写入已忽略的 `.code-navi/provider.env`。

## Context Management Rule
1. After completing any major sub-task or code phase, automatically run `/compact` to summarize the remaining context.
2. Do not retain full implementation logs after git commits; condense progress into a status checklist.

## 文档导航

按任务需要读取（最小组合规则见 AGENTS.md）：

| 领域 | 文档 |
| --- | --- |
| 产品范围与路线 | `docs/product/scope.md`、`docs/product/roadmap.md` |
| 架构 | `docs/architecture/system.md`、`docs/architecture/kernel.md`、`docs/architecture/frontend.md` |
| 开发与测试 | `docs/development/workflow.md`、`docs/development/testing.md`、`docs/development/high-risk-capabilities.md` |
| 部署 | `docs/deployment/local.md`、`docs/deployment/production.md` |
