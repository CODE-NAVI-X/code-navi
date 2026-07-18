# 开发规范

## 1. 环境与安装

- Python 最低版本为 3.11；开发者应使用独立虚拟环境。
- Kernel 源码位于 `src/kernel/`，安装和测试不依赖其他私有仓库或 Git 凭据。
- 依赖只在 `pyproject.toml` 声明，不提交虚拟环境、构建产物或本地密钥。

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## 2. 代码与目录

- 生产代码放在 `src/code_navi/`，测试放在 `tests/`，可运行示例放在 `examples/`。
- 新模块使用类型标注；公开接口提供简短 docstring；优先使用小而明确的函数和不可变数据。
- 行宽为 100；导入、基础错误和常见 Python 反模式由 Ruff 检查。
- 助手和能力声明只描述业务角色、输入输出和允许的工具，不持有平台 SDK 或密钥。
- 应用只通过 kernel 公开接口集成，不绕过 `AgentRuntime`；`src/kernel/` 不反向导入应用层。
- 不在日志、Event metadata、测试样例或文档中提交令牌、个人信息和未脱敏业务数据。

## 3. 测试与本地质量门

每个行为变更至少包含一个能够在修改前失败、修改后通过的测试。测试默认离线、确定且不访问真实模型；外部服务测试必须显式标记并由独立流程运行。

提交前执行：

```bash
ruff check .
pytest
python -m build
```

开发依赖已经包含构建工具。文档-only 改动至少检查链接、命令和当前状态是否一致。

测试分层：

- 单元测试：领域声明、解析、校验和纯业务规则；
- 集成测试：应用层经 `AgentRuntime` 与 MockProvider/假工具完成一次运行；
- 在线冒烟测试：真实 Provider 或外部系统，仅在明确配置凭据后手动/CI 触发。

## 4. 分支与提交

`main` 保持可安装、可测试，不直接堆叠未完成工作。分支使用 `<type>/<short-topic>`：

- `feat/`：新能力；
- `fix/`：缺陷修复；
- `docs/`：文档；
- `refactor/`：不改变外部行为的重构；
- `test/`：测试；
- `chore/`：依赖或工程维护。

提交信息遵循 Conventional Commits，例如 `feat(student): add exercise planner`、`docs: clarify kernel upgrade flow`。一次提交只解决一个可解释的问题，不混入无关格式化或生成文件。

## 5. Pull Request

PR 描述至少包含：问题与范围、实现摘要、验证命令与结果、风险/回滚方式、涉及的文档。满足以下条件才能合并：

- 测试和 Ruff 通过；
- 新行为有测试，用户可见变化有文档；
- 未破坏 [INVARIANTS.md](INVARIANTS.md)；
- 没有未说明的 kernel 升级、权限扩大或外部副作用；
- 评审者能从 PR 中区分已完成能力和后续计划。

## 6. 依赖与 Kernel 维护

- 生产依赖必须固定兼容范围；kernel 变更应保持独立提交和清晰的契约说明。
- 同步旧仓库实现或修改 kernel 契约时，按照 [KERNEL_INTEGRATION.md](KERNEL_INTEGRATION.md)执行完整回归验证。
- 新依赖应说明用途、维护状态、许可证/安全影响和不使用它的代价；能用标准库清晰实现时不新增依赖。

## 7. 完成定义

一项工作只有在代码、测试、文档、配置和验收说明彼此一致时才算完成。未实现、未验证或只在本机成立的能力必须明确标注，不能写入“已完成”列表。
