# Code Navi

Code Navi（智教码航）是面向计算机专业学习与项目实践的通用代码学习助手。用户围绕当前项目直接提问，应用负责装配受控项目上下文，并通过仓库内置的 `kernel` 完成一次可审计运行。后续代码测试、信息检索、项目流程和仓库接入能力将在同一应用边界内按需注册。

## 当前状态

当前仓库已经提供：

- 通用且默认无工具权限的 `code_learning_agent`；
- `code-navi ask` 单次项目上下文问答；
- 交互 Shell 中的 `?` 快问、`/branch` 问题分支、`/back` 和 `/context`；
- README、可选 `.code-navi/task.json`、显式文件片段和上一条回答的受限上下文装配；
- 默认离线 Mock Provider、显式启用的 OpenAI Provider 和 Event JSONL；
- 原助学、助教、助研 `AgentSpec` 的兼容导出。
- 规则驱动、可恢复的科研澄清 API：在应用层 SQLite 中收集五个固定字段，并生成研究简报和明确标注建议/待验证项的研究计划；
- 学生端科研页面：可恢复会话、选择推荐项或自由输入，并展示研究简报与规则研究计划；已配置模型时会明确展示“模型个性化建议”，失败时提示“规则降级”。

科研澄清的字段顺序、状态保存、会话恢复和完成条件始终由规则控制。若已显式配置 OpenAI 或 DeepSeek Provider 的运行环境变量，模型只会生成经过 JSON 校验的简短回复、下一问与三个推荐项；它不能改变字段或跳过流程。没有 Key、调用超时/网络失败或输出不合法时，接口不中断并自动使用固定规则问题和选项。规则研究计划仅根据用户完成的五字段生成，所有内容均标记为“推断建议”或“待验证”，不代表论文事实或已验证结论。完成计划后，用户可主动调用受限学术检索：当前仅允许 arXiv 元数据/摘要，并返回带来源状态、访问时间及事实/推断/待验证标记的 EvidenceBundle；不会默认全网搜索、下载正文或生成论文证据卡。该 API 不会自动调用现有 `research_coach_agent`。

## 快速开始

前置条件：Python 3.11+。

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev,server]"
pytest
ruff check .

# 离线验证上下文与运行链路
code-navi ask "这个项目的目标是什么？"

# 进入交互 Shell
code-navi
```

Linux/macOS 请使用 `source .venv/bin/activate` 激活虚拟环境。

## 科研澄清 API（规则控流程 + 可选模型文案）

启动服务后可创建会话；无模型或 API Key 也可使用：

```bash
uvicorn code_navi.server:app --reload

curl -X POST http://127.0.0.1:8000/api/v1/research/sessions \
  -H "Content-Type: application/json" \
  -d '{"initial_description":"教育场景中的人工智能"}'
```

客户端可在每轮提交 `selected_option` 或 `answer` 之一，并使用同一个 `session_id` 恢复会话。响应中的 `generation_mode` 为 `llm`、`rules` 或 `rules_fallback`，并配有 `reply`；下一题仍由规则确定字段，模型只可更换已校验的文案和固定三个选项。用户输入“我不知道，有什么推荐吗”时，只有模型返回通过校验的 `suggested_value` 才会填入当前字段；无模型或无有效建议时该字段保持待填写，绝不会把“不知道”写入研究数据。五个字段齐全后，响应中的 `research_brief` 和 `research_plan` 才会出现；`research_plan` 不访问外部资料，每个条目都带有 `inference` 或 `to_verify` 标记。学生端页面读取 `NEXT_PUBLIC_CODE_NAVI_API_URL`（或 `NEXT_PUBLIC_API_BASE`）连接后端，并仅在浏览器 `localStorage` 保存科研会话 ID，不保存密钥。具体契约见 [科研澄清 Skill](docs/skills/research-clarification/SKILL.md)。

### DeepSeek 个性化科研追问（可选）

DeepSeek 仅用于科研澄清的个性化回复、下一问文案和三个推荐项；五字段、字段顺序、会话恢复和完成判定仍由规则控制。使用其 OpenAI-compatible `chat/completions` 接口前，在**运行服务的环境**中设置：

```bash
export CODE_NAVI_PROVIDER=deepseek
export DEEPSEEK_API_KEY=<api-key>
export DEEPSEEK_BASE_URL=https://api.deepseek.com     # 可省略
export DEEPSEEK_MODEL=deepseek-v4-flash               # 可省略
uvicorn code_navi.server:app --reload
```

Windows PowerShell 可用 `$env:CODE_NAVI_PROVIDER = "deepseek"` 等对应语法。该设置使科研澄清使用 DeepSeek 个性化文案；未显式选择 CLI Provider 的通用 CLI 仍保持离线 Mock。既有学习模块也使用同名 `DEEPSEEK_*` 环境变量，但仅在调用其学习解释入口时生效，本 PR 未改变该既有行为。Key 只能通过运行环境传入，不能写入仓库、`.env`、数据库、浏览器或客户端请求。无 Key、8 秒超时、网络/Provider 失败、非 JSON、字段缺失或不是三个选项时，页面会显示规则生成或规则降级，科研会话不会中断。DeepSeek 不会自动触发受限学术检索；检索仍必须由用户主动点击。

### 显式受限学术检索

计划完成后，学生端页面的“查询 arXiv”按钮才会发起网络请求；也可直接调用：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/research/sessions/<session_id>/evidence-bundles \
  -H "Content-Type: application/json" \
  -d '{"query":"教育场景 人工智能","sources":["arxiv"]}'
```

该接口通过需要 `READ + NETWORK` 的 `academic_search` Tool 执行，返回的 EvidenceBundle 仅限允许来源的元数据和摘要。`fact` 只表示来源直接支持的元数据/摘要，关键词关联一律是 `inference`，实验设置和结论是 `to_verify`。可通过 `CODE_NAVI_ACADEMIC_ARXIV_ENABLED=false` 禁用 arXiv；来源不可用时返回空结果和原因。不会下载论文正文、生成论文证据卡、使用 MCP 或保存密钥。详见 [学术检索 Skill](docs/skills/academic-search/SKILL.md)。

## Docker 部署

前置条件只有 Docker Engine 与 Docker Compose。下面的命令会构建镜像、只读挂载当前项目、拉起 CLI 容器，并将 Event 日志保存到 Docker volume：

```bash
docker compose up --build
```

若 Compose 前台被自身菜单占用，可在另一个终端进入已经拉起的交互 Shell：

```bash
docker compose attach code-navi
```

默认使用离线 Mock Provider。在线运行时，在启动前通过服务器环境变量提供配置：

```bash
export CODE_NAVI_PROVIDER=openai
export CODE_NAVI_MODEL=<model-name>
export OPENAI_API_KEY=<api-key>
docker compose up --build
```

镜像构建不需要 GitHub Token，也不需要访问其他私有源码仓库。更多说明见 [Docker 部署](docs/DEPLOYMENT.md)。

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
├── src/kernel/            # 内置单 Agent 运行时、权限、Event 和 Provider 适配器
├── docs/                  # 架构、CLI、开发规范和路线图
├── examples/              # 可运行的最小接线示例
├── src/code_navi/         # 通用助手、上下文、应用用例和 CLI
├── tests/                 # 离线单元与集成测试
├── Dockerfile             # 轻量多阶段运行镜像
├── compose.yaml           # 一键构建和启动
├── pyproject.toml         # 依赖、命令入口和质量工具配置
└── README.md              # 项目入口
```

## 文档入口

- [文档索引](docs/README.md)
- [CLI 使用说明](docs/CLI.md)
- [架构说明](docs/ARCHITECTURE.md)
- [开发规范](docs/DEVELOPMENT.md)
- [Kernel 集成规范](docs/KERNEL_INTEGRATION.md)
- [Docker 部署](docs/DEPLOYMENT.md)
- [产品路线图](docs/PRODUCT_ROADMAP.md)
- [应用不变量](docs/INVARIANTS.md)
- [当前非目标](docs/NON_GOALS.md)
