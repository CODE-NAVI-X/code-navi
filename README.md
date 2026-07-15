# Code Navi

Code Navi（智教码航）是面向计算机专业人才培养的 Agent 应用仓库，覆盖助学、助教和助研三个方向。本仓库负责产品、领域 Agent、应用编排与交付；通用单 Agent 执行能力由独立的 `code-navi-kernel` 仓库提供。

## 当前状态

仓库拆分与基础接线已经完成：

- kernel 以固定提交的外部依赖接入，不在本仓库复制维护；
- 助学、助教、助研各有一个最小 `AgentSpec`；
- 提供基于 `MockProvider` 的离线示例和测试；
- 架构、开发、测试、提交和 kernel 升级规范统一存放在 `docs/`。

这不表示完整业务流程、Web 产品、在线模型服务或多 Agent 协作已经完成。后续能力以[产品路线图](docs/PRODUCT_ROADMAP.md)中的验收状态为准。

## 快速开始

前置条件：Python 3.11+，以及可读取私有 `Dlalmlurn/code-navi-kernel` 仓库的 GitHub Git 凭据。可使用 `gh auth setup-git` 配置本机凭据。

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev]"
pytest
ruff check .
python examples/run_mock.py
```

Linux/macOS 请使用 `source .venv/bin/activate` 激活虚拟环境。

## 仓库结构

```text
code-navi/
├── docs/                  # 架构、开发规范、路线图和集成约束
├── examples/              # 可运行的最小接线示例
├── src/code_navi/         # 产品包与领域 Agent
├── tests/                 # 应用仓库测试
├── pyproject.toml         # 依赖、构建和质量工具配置
└── README.md              # 项目入口
```

## 文档入口

- [文档索引](docs/README.md)
- [架构说明](docs/ARCHITECTURE.md)
- [开发规范](docs/DEVELOPMENT.md)
- [Kernel 集成规范](docs/KERNEL_INTEGRATION.md)
- [产品路线图](docs/PRODUCT_ROADMAP.md)
- [应用不变量](docs/INVARIANTS.md)
- [当前非目标](docs/NON_GOALS.md)
