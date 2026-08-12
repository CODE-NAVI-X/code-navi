# 测试与质量检查

## 1. 原则

优先验证实际功能、公开接口和端到端接线，再按真实风险增加细粒度测试。缺陷修复必须有能复现原问题的回归测试；不为覆盖率或形式完整预建假设分支矩阵。

默认测试必须离线、确定、无真实账号副作用，并使用 Mock Provider 或受控替身。

禁止测试嵌套测试。辅助代码保持简单、可读，通过人工检查和实际运行确认，不扩张为独立测试工程。

## 2. 测试范围

| 改动 | 优先测试 |
| --- | --- |
| Kernel Runtime、Event、Provider 或权限 | 对应 `tests/kernel/`，显式历史改动还需证明消息顺序和 `session_id` 不会隐式恢复，再加一个应用接线测试 |
| CLI、上下文或公共 Provider 选择 | `tests/test_cli.py`、`test_context.py`、`test_providers.py`；shell 恢复还需覆盖项目隔离、业务 `conversation_id` 与 Runtime `session_id` 分离、branch 非持久化和无状态 `ask` |
| 知识点学习 | `tests/test_learning_module.py` 与相关 server/provider 测试 |
| 跨模块上下文 | `tests/test_context_transfers.py`、`tests/test_migrations.py`，验证最终数据确认、每轮澄清接收背景、来源/画像/计划恢复、重复确认与确认页构建 |
| Python 执行、判题与学习记录 | `tests/online_compiler/`；涉及真实 Piston 时再追加显式隔离环境测试 |
| 科研兼容规则、API 或措辞 | `tests/test_research_api.py`、`test_research_llm.py` |
| 动态科研对话、规则研究计划与 Provider | `tests/test_research_conversation.py`、`test_research_frontend_copy.py`、`test_research_deepseek.py`、`test_provider_configuration.py`；持久化上下文还需覆盖预算、摘要边界、跨 run 复用和失败保留 |
| 学术检索与对话检索 | `tests/test_research_tools.py`、`test_academic_evidence.py`、`test_conversation_search.py` |
| ORM 或 Alembic | `tests/test_migrations.py` 和受影响模块测试 |
| FastAPI 边界 | `tests/test_server_gateway.py` 与目标 router 测试 |
| 项目路径与启动器 | `tests/test_paths.py`、`test_portable_launch.py` |
| 前端 | `npm run lint`、`npm run build`；API 文案契约变化追加相应 Python 测试 |

## 3. 常用命令

先运行最接近改动的测试：

```powershell
.venv\Scripts\python.exe -m pytest tests/test_learning_module.py -q
.venv\Scripts\python.exe -m ruff check src/code_navi/learning tests/test_learning_module.py
```

影响较广、Kernel、依赖或合并就绪变更运行完整后端质量门：

```powershell
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m build
```

`pyproject.toml` 默认排除 `live` marker，因此完整测试不会调用真实外部 Provider。前端质量门：

```powershell
cd frontend
npm ci
npm run lint
npm run build
```

日常局部修改不要求每次运行全部质量门。纯文档修改只验证受影响的链接、路径、命令、模块名和状态。

## 4. 数据库与 API 验证

1. 迁移测试必须覆盖空数据库升级；会改变既有列或数据时，再覆盖实际旧 revision 升级。
2. `Base.metadata.create_all()` 不能代替迁移验证。
3. API 测试使用临时或内存数据库，不读取开发者本地 PoC 数据。
4. 学习笔记测试必须验证 `session_id` 隔离；科研测试必须验证 `conversation_id` 恢复、兼容 `session_id` 路径和缺失状态。
5. 前后端 schema 变化需要验证字段、错误状态和兼容项，不只检查页面文案。
6. 代码执行测试必须证明请求不能扩大服务端语言、runtime、CPU、内存、时间、输入和输出限制；隐藏测试不得泄漏内容，执行服务失败不得归因于学生代码。

## 5. 在线与高风险测试

真实 Provider 测试必须显式设置 `live` marker 所需配置，并使用无敏感信息的最小请求。外部服务失败要与应用失败区分，且不得破坏默认离线测试。

本地 Piston 启动并完成 Python runtime 安装后，使用以下命令验证真实隔离边界：

```powershell
$env:CODE_NAVI_PISTON_LIVE_TEST = "1"
.venv\Scripts\python.exe -m pytest -m live tests/online_compiler/test_piston_live.py -q
```

联网工具、代码执行和远程仓库按统一顺序验证：

1. 用 Mock 或假适配器验证请求、结果和错误分类；
2. 用隔离账号、仓库或执行环境验证权限和限制；
3. 真实资源测试显式启用，并验证失败、部分完成和实际副作用。

允许的动作、权限和用户确认由 [high-risk-capabilities.md](high-risk-capabilities.md) 定义，本文件不重复。

## 6. 失败处理

1. 在相同入口复现失败；
2. 区分实现故障、预期过时、环境缺失和外部服务不可用；
3. 修改预期时明确对应的产品行为变化；
4. 修复后重跑最小复现场景和受影响测试；
5. 必要检查无法运行时，说明具体原因和受影响结论。
