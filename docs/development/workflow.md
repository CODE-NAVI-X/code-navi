# 日常开发与贡献流程

## 1. 本地环境

后端要求 Python 3.11 或更高版本，依赖以 `pyproject.toml` 为准：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,server]"
code-navi --help
```

前端要求 Node `20.19` 或更高版本，依赖以 `frontend/package.json` 和 `package-lock.json` 为准：

```powershell
cd frontend
npm ci
```

不得提交虚拟环境、`node_modules`、构建产物、缓存、IDE 临时文件、真实密钥、个人信息、未脱敏业务数据或个人机器绝对路径。

## 2. 当前入口与代码位置

| 任务 | 先定位 |
| --- | --- |
| CLI 问答 | `src/code_navi/cli.py`、`application.py`、`context.py` |
| 学习 API | `src/code_navi/learning/`、`frontend/lib/api/learning.ts`、学习页面 |
| 跨模块上下文 | `src/code_navi/context_transfer/`、`frontend/lib/api/context-transfers.ts`、来源页面和目标确认页面 |
| Python 练习与判题 | `src/code_navi/online_compiler/`、`frontend/lib/api/compiler.ts`、练习页面、`tests/online_compiler/` |
| 科研对话与检索 | `src/code_navi/research/conversation_agent.py`、`conversation_service.py`、`conversation_search_service.py`、`academic.py`、科研页面 |
| Provider | `src/code_navi/providers.py` 与 `src/kernel/adapters/` |
| Kernel | `src/kernel/` 与 `tests/kernel/` |
| 数据库 | `src/code_navi/db.py`、模块 ORM、`migrations/` |
| 本地 Web/API | `src/code_navi/server.py`、`frontend/`、`scripts/dev.py`、`dev-start.cmd`、`dev-stop.cmd` |

开始修改前确认仓库根目录、分支和工作树状态，找到真实入口及最接近的测试，并从同一工作树运行最小闭环。不要按尚不存在的目标目录重新组织实现。

## 3. 实施顺序

### 普通功能

1. 确认所属产品模块和当前范围。
2. 从现有入口贯通到实际结果，先完成最窄纵向切片。
3. 运行闭环，检查返回值、持久化、Event 和失败状态中实际受影响的部分。
4. 根据运行结果修正接口，再补直接相关测试。
5. 只在重复职责已经出现时抽取公共能力。
6. 更新受影响的命令、配置、接口和状态文档。

首个闭环前不冻结契约，不预建完整异常矩阵、兼容层或迁移体系。

### 缺陷修复

1. 从真实入口或最近的公开接口复现故障。
2. 定位故障层级，不用跨层调用绕开根因。
3. 增加修改前失败、修改后通过的回归测试。
4. 完成最小修复并重跑复现场景与受影响测试。

不得通过删除断言、放宽预期、吞异常或跳过测试隐藏故障。

### 前端与 Kernel

前端任务遵循 [前端架构](../architecture/frontend.md)，以现有 API 和页面为入口。Kernel 只有在公开 Runtime 无法支持已验证需求时才修改，并遵循 [Kernel 维护](../architecture/kernel.md)。

## 4. 数据库变更

业务模块共用 `code_navi.db.Base` 和 `CODE_NAVI_DATABASE_URL`。新增或修改 ORM schema 时：

1. 修改对应模型；
2. 新增 Alembic revision，不改写已经发布的 revision；
3. 验证空数据库 `alembic upgrade head`；
4. 验证受影响的旧 schema 升级和数据保留；
5. 更新 `tests/test_migrations.py` 和直接相关模块测试。

本地开发启动前运行：

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
```

对于早于 Alembic 的既有 PoC 数据库，先确认其确实已有基线表，再执行仓库脚本提示的 `alembic stamp 0001` 和后续升级；不得对未知数据库直接 stamp。

## 5. 本地运行

默认 Provider 为离线 Mock。跨平台启动前先迁移数据库；启动器会检查依赖，并启动 FastAPI `:8000` 与 Next `:3000`：

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
python scripts/dev.py
```

Windows 也可使用：

```powershell
.\dev-start.cmd
```

在线 Provider 必须显式配置名称、模型和对应凭据。本机可运行 `code-navi configure-provider --provider deepseek`，配置写入已忽略的 `.code-navi/provider.env`；网页写入接口默认禁用。凭据不写入源码、日志、Event 或前端状态。具体边界见 [高风险能力](high-risk-capabilities.md)。

## 6. 代码与依赖规则

1. 公开接口使用明确名称、类型标注和必要的简短 docstring。
2. 输入校验、业务规则、外部调用和展示保持分层；不复制已有实现形成平行路径。
3. 不绕过公开边界，不伪造成功，不把 Provider 文本当作工具或测试事实。
4. Python 行宽为 100，并使用 Ruff；前端使用项目现有 ESLint 和 TypeScript 配置。
5. 新依赖需说明用途、现有方案为何不足、兼容范围和安全影响；删除依赖同步清理导入、配置与文档。
6. 实验、配置和消融使用完整、稳定且与论文及结果文件一致的名称，禁止 `A1`、`B2` 等“单字母 + 数字”编号。

## 7. 提交与合并

分支名使用 `<type>/<short-topic>`；提交使用 Conventional Commits：`<type>(<scope>): <description>`。一次提交只解决一个可解释、可审查和可回退的问题，不混入无关格式化、目录迁移或生成文件。

PR 至少说明问题与范围、关键实现、实际验证和受影响的接口或配置。合并前确认：

1. 目标行为已有相称测试或可重复验证；
2. [testing.md](testing.md) 中必要质量门通过；
3. 代码、迁移、前后端类型和受影响文档一致；
4. 没有未说明的 Kernel 契约变化、权限扩大、外部副作用或敏感数据；
5. 完成状态与根 [AGENTS.md](../../AGENTS.md) 的定义一致。
