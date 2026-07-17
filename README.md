# Code Navi

Code Navi（智教码航）是面向计算机专业学习与项目实践的通用代码学习助手。用户围绕当前项目直接提问，应用负责装配受控项目上下文并通过独立的 `code-navi-kernel` 完成一次可审计运行。后续代码测试、信息检索、项目流程和仓库接入能力将在同一应用边界内按需注册。

## 当前状态

当前仓库已经提供：

- 通用且默认无工具权限的 `code_learning_agent`；
- `code-navi ask` 单次项目上下文问答；
- 交互 Shell 中的 `?` 快问、`/branch` 问题分支、`/back` 和 `/context`；
- README、可选 `.code-navi/task.json`、显式文件片段和上一条回答的受限上下文装配；
- 默认离线 Mock Provider、显式启用的 OpenAI Provider 和 Event JSONL；
- 原助学、助教、助研 `AgentSpec` 的兼容导出。

这不表示真实模型、持久化多轮会话、代码执行、Web 产品、多 Agent、信息检索或远程仓库接入已经完成。后续能力以[产品路线图](docs/PRODUCT_ROADMAP.md)中的验收状态为准。

## 快速开始

前置条件：Python 3.11+，以及可读取私有 `Dlalmlurn/code-navi-kernel` 仓库的 GitHub Git 凭据。可使用 `gh auth setup-git` 配置本机凭据。

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev]"
pytest
ruff check .

# 离线验证上下文与运行链路
code-navi ask "这个项目的目标是什么？"

# 进入交互 Shell
code-navi
```

Linux/macOS 请使用 `source .venv/bin/activate` 激活虚拟环境。

在线回答是可选能力，必须显式安装、选择 Provider 并配置密钥和模型：

```bash
python -m pip install -e ".[online]"
$env:OPENAI_API_KEY = "..."
code-navi ask "解释当前项目结构" --provider openai --model <model-name>
```

不要把密钥写入源码、`.code-navi/task.json`、命令历史或 Event metadata。Linux/macOS 使用对应 shell 的环境变量语法。

## 项目上下文

CLI 从当前目录向上查找项目根目录，默认携带 README 摘要。项目可以在本地选择提供 `.code-navi/task.json`；该目录默认不进入 Git：

```json
{
  "title": "图像分类课程项目",
  "goal": "完成可复现的CNN基线",
  "current_milestone": "调试训练流程",
  "active_files": ["src/train.py"]
}
```

文件片段必须位于项目根目录内，并受行数与总上下文预算限制：

```bash
code-navi ask "解释这里的数据处理" --attach src/train.py:40-80
```

完整交互方式见 [CLI 使用说明](docs/CLI.md)。

## 仓库结构

```text
code-navi/
├── docs/                  # 架构、CLI、开发规范和路线图
├── examples/              # 可运行的最小接线示例
├── src/code_navi/         # 通用助手、上下文、应用用例和 CLI
├── tests/                 # 离线单元与集成测试
├── pyproject.toml         # 依赖、命令入口和质量工具配置
└── README.md              # 项目入口
```

## 文档入口

- [文档索引](docs/README.md)
- [CLI 使用说明](docs/CLI.md)
- [架构说明](docs/ARCHITECTURE.md)
- [开发规范](docs/DEVELOPMENT.md)
- [Kernel 集成规范](docs/KERNEL_INTEGRATION.md)
- [产品路线图](docs/PRODUCT_ROADMAP.md)
- [应用不变量](docs/INVARIANTS.md)
- [当前非目标](docs/NON_GOALS.md)
