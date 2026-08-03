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
- 对话式科研澄清后端核心：用户可自由表达、修正方向并恢复完整对话；服务维护动态科研画像和可解释成熟度，在线决策统一经 `AgentRuntime`，失败时安全降级；
- 对话主流程的规则研究计划：科研画像达到计划准备度后，离线生成并恢复带“建议/待确认”边界的结构化计划；
- 旧规则五字段科研 API 作为兼容层保留，不再驱动学生端主流程；
- 对话式学生端科研页面：展示完整消息、动态科研画像、候选问题、可解释成熟度与可折叠处理摘要；支持自由输入、建议选项、会话恢复、移动端布局和明确的请求失败重试。
- 显式、受限的学术检索：从科研画像生成可复核查询，只检索用户勾选的 OpenAlex、Crossref、arXiv，持久化可追溯 EvidenceBundle，并允许部分来源失败。

新的 `/api/v1/research/conversations` 已成为学生端主流程。它没有固定问题顺序：模型可以在一轮中提取多个用户明确表达的信息、给出候选科研问题并修正已有画像，但只能提交经过 Pydantic 校验的结构化决策，不能把猜测写成事实，也不能自动搜索。无 Key、调用超时、网络失败或输出不合法时，对话会使用确定性规则继续，不返回 500。旧的 `/api/v1/research/sessions` 五字段流程只作为 API 兼容层保留，不再由科研页面调用；弃用和数据清理另行安排。

科研澄清和学术检索是两个独立 Skill。准备检索计划不会联网；只有用户在页面确认查询词和来源后，系统才通过具有 `READ + NETWORK` 权限的 `academic_search` Tool 并行访问允许来源。结果只包含元数据和来源提供的摘要，按会话写入 SQLite；相同会话、规范化查询词和相同来源组合在默认一小时内复用缓存。不会默认全网搜索、下载正文或声称已阅读全文。

## 快速开始

前置条件：Python 3.11+、Node.js 20.9+ 与 npm。仓库可以放在任意磁盘和目录，不要求固定盘符。

Windows PowerShell：

```powershell
python -m venv .venv
\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,server]"
Set-Location frontend
npm ci
Set-Location ..
python scripts/dev.py
```

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,server]"
cd frontend
npm ci
cd ..
python scripts/dev.py
```

Windows 也可以双击 `dev-start.cmd`；脚本始终以自身所在目录作为项目目录，不依赖终端当前路径。启动后访问 `http://127.0.0.1:3000/research`。`Ctrl+C` 可停止跨平台启动器中的两个服务，Windows 双窗口启动方式可使用 `dev-stop.cmd`。

提交前质量检查：

```bash
ruff check .
pytest --basetemp .quality-tmp
python -m build
cd frontend
npm run lint
npx tsc --noEmit
npm run build
```

SQLite、会话和本地 Provider 配置默认写入当前项目的 `.code-navi/`。代码会在运行时把它解析为当前电脑上的绝对路径；也可以设置 `CODE_NAVI_DATA_DIR` 指向独立数据目录，或设置 `CODE_NAVI_PROJECT_ROOT` 指定项目根目录。前端访问其他地址的后端时，在 `frontend/.env.local` 配置 `NEXT_PUBLIC_CODE_NAVI_API_URL`；后端跨域来源用 `CODE_NAVI_CORS_ORIGINS` 配置。

CLI 可单独使用：

```bash
# 离线验证上下文与运行链路
code-navi ask "这个项目的目标是什么？"

# 进入交互 Shell
code-navi
```

## 对话式科研澄清 API（新主流程）

启动服务后，可直接用一句自然语言创建会话；没有模型或 API Key 时会自动使用离线规则：

```bash
uvicorn code_navi.server:app --reload

curl -X POST http://127.0.0.1:8000/api/v1/research/conversations \
  -H "Content-Type: application/json" \
  -d '{"initial_message":"我想研究演化博弈法，数据来源不太清楚"}'
```

后续向 `/api/v1/research/conversations/{conversation_id}/messages` 提交 `{"message":"..."}`，或用 GET 请求同一 `conversation_id` 恢复对话。响应包含动态 `profile`、可解释 `readiness`、候选问题、下一问、建议答案、完整消息以及 Kernel `last_run_id`。当画像处于 `ready_for_plan` 时，响应还会包含 `research_plan`：题目/问题、目标、候选方法或基线、数据或指标、两周 MVP、风险与规避、检索关键词和待确认项。它只读取用户已确认的画像，所有内容明确标为建议或待验证，不访问模型、网络或论文，也不会把推断写成论文事实。具体契约、降级边界和验收方法见 [科研澄清 Skill](docs/skills/research-clarification/SKILL.md)。

学生端启动后访问 `/research`。页面只在浏览器 `localStorage` 保存 `conversation_id`，刷新时通过 GET 恢复服务端消息和最近一次 EvidenceBundle；模型回复使用不执行 HTML 的安全 Markdown 子集展示。“本轮处理过程”只展示生成方式、意图、事件数量和 Run ID 等审计摘要，不暴露或伪造内部思维链。页面不会在刷新或澄清对话时自动联网。

科研页面由 `research-clarification` Skill 驱动而不是固定问卷。用户选择建议答案后必须推进到新的澄清维度；画像具备最低检索条件且用户明确选择“准备探索性检索”时，对话停止追问并返回 `next_skill=academic-search`。随后页面展示由画像生成的查询词和来源选项，仍需用户再次点击执行。

## 兼容科研澄清 API（旧五字段流程）

启动服务后可创建会话；无模型或 API Key 也可使用：

```bash
uvicorn code_navi.server:app --reload

curl -X POST http://127.0.0.1:8000/api/v1/research/sessions \
  -H "Content-Type: application/json" \
  -d '{"initial_description":"教育场景中的人工智能"}'
```

客户端可在每轮提交 `selected_option` 或 `answer` 之一，并使用同一个 `session_id` 恢复会话。响应中的 `generation_mode` 为 `llm`、`rules` 或 `rules_fallback`，并配有 `reply`；下一题仍由规则确定字段，模型只可更换已校验的文案和固定三个选项。用户输入“我不知道，有什么推荐吗”时，只有模型返回通过校验的 `suggested_value` 才会填入当前字段；无模型或无有效建议时该字段保持待填写，绝不会把“不知道”写入研究数据。五个字段齐全后，响应中的 `research_brief` 和 `research_plan` 才会出现；`research_plan` 不访问外部资料，每个条目都带有 `inference` 或 `to_verify` 标记。学生端页面读取 `NEXT_PUBLIC_CODE_NAVI_API_URL`（或 `NEXT_PUBLIC_API_BASE`）连接后端，并仅在浏览器 `localStorage` 保存科研会话 ID，不保存密钥。具体契约见 [科研澄清 Skill](docs/skills/research-clarification/SKILL.md)。

### DeepSeek 对话决策（可选）

新对话流程使用 DeepSeek 生成经过严格 JSON 校验的画像 patch、自然回复、候选问题和下一问；画像写入、成熟度、会话恢复与搜索权限仍由应用规则控制。使用其 OpenAI-compatible `chat/completions` 接口前，在**运行服务的环境**中设置：

本地演示如需在 `/research` 页面配置模型，必须先在运行服务的本机环境显式设置 `CODE_NAVI_ALLOW_BROWSER_PROVIDER_CONFIG=true`；默认关闭。随后可在页面顶部打开“科研模型连接”，点击“输入 API Key”，填写 Provider、Key、模型和 Base URL 后选择“保存并测试连接”。保存和测试接口都只接受来自本机回环地址的请求；Key 只随本机请求发送一次，服务端原子写入当前项目 Git 已忽略的 `.code-navi/provider.env`，随后立即在当前进程生效。响应不会回显 Key，页面不会写入 `localStorage`，保存成功后密码框立即清空。

不希望 Key 经过浏览器时，仍可使用隐藏输入命令：

```powershell
Set-Location <你的-code-navi-目录>
.\.venv\Scripts\code-navi.exe configure-provider --provider deepseek
```

DeepSeek 默认模型为 `deepseek-v4-flash`。网页配置调用 `PUT /api/v1/research/provider/configuration`，保存后会立即激活并自动测试；也可以分别调用 `GET /api/v1/research/provider/status` 和 `POST /api/v1/research/provider/test`。所有响应都不返回 Key。CLI 修改配置后，已运行服务仍建议重启。

网页和 CLI 都会拒绝明显截断、包含空白的 Key 或非 HTTPS Base URL。页面区分“已配置（待验证）”“连接正常”“密钥被拒绝”“模型不可用”“网络超时”和“响应结构无效”，不能仅凭配置文件存在就宣称模型可用。

部署环境仍可直接使用环境变量：

```bash
export CODE_NAVI_PROVIDER=deepseek
export DEEPSEEK_API_KEY=<api-key>
export DEEPSEEK_BASE_URL=https://api.deepseek.com     # 可省略
export DEEPSEEK_MODEL=deepseek-v4-flash               # 可省略
uvicorn code_navi.server:app --reload
```

Windows PowerShell 可用 `$env:CODE_NAVI_PROVIDER = "deepseek"` 等对应语法。未显式选择 Provider 时科研对话保持基础规则模式，通用 CLI 仍保持离线 Mock。Key 只能持久化在服务端环境或项目内 Git 已忽略的 `.code-navi/provider.env`，不能写入仓库、SQLite、localStorage、日志或 Event metadata。网页配置默认关闭，且即使显式开启也只用于单机开发；公开部署应保持 `CODE_NAVI_ALLOW_BROWSER_PROVIDER_CONFIG=false`，并使用服务端环境变量或带身份认证、TLS 和专用密钥管理的管理端。无 Key、10 秒超时、网络/Provider 失败或结构化输出不合法时，页面明确显示基础规则或规则接管，科研会话不会中断。DeepSeek 不会自动触发学术检索。

### 显式受限学术检索

新对话主流程先用只读接口生成检索计划（不会联网）：

```bash
curl http://127.0.0.1:8000/api/v1/research/conversations/<conversation_id>/search-plan
```

用户确认查询词与来源后才执行检索：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/research/conversations/<conversation_id>/evidence-bundles \
  -H "Content-Type: application/json" \
  -d '{"sources":["openalex","crossref","arxiv"]}'
```

已保存结果可通过 GET 同一路径恢复，不会访问外部来源。旧会话兼容接口仍可调用：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/research/sessions/<session_id>/evidence-bundles \
  -H "Content-Type: application/json" \
  -d '{"query":"教育场景 人工智能","sources":["arxiv"]}'
```

检索通过需要 `READ + NETWORK` 的 `academic_search` Tool 执行。EvidenceBundle 仅含允许来源的元数据和摘要；`fact` 只表示来源直接支持的内容，关键词关联是 `inference`，实验设置和结论是 `to_verify`。任一来源不可用时会保留其他来源结果，并返回每个来源的状态、耗时和安全失败原因。可用 `CODE_NAVI_ACADEMIC_<SOURCE>_ENABLED=false` 分别禁用来源，用 `CODE_NAVI_ACADEMIC_CACHE_TTL_SECONDS` 调整缓存，并通过标准 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量配置代理。详见 [学术检索 Skill](docs/skills/academic-search/SKILL.md) 和 [.env.example](.env.example)。

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
