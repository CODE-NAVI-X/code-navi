# 本地运行与容器基线

## 1. 当前可运行范围

仓库有四种本地或受限环境运行入口：

| 方式 | 覆盖范围 | 当前定位 |
| --- | --- | --- |
| `python scripts/dev.py` | FastAPI、Next 与依赖检查 | 跨平台本地 Web/API 开发闭环；迁移需先执行，不启动 Piston |
| Windows `dev-start.cmd` | 迁移、Piston runtime、FastAPI 与 Next | 当前包含 Python 练习的 Windows 本地入口 |
| `compose.yaml` | `code-navi` CLI、Piston、runtime 初始化和数据卷 | CLI 与代码执行服务容器基线 |
| `compose.web.yaml` | FastAPI、Next standalone、Caddy、Piston 与持久化数据卷 | 当前 NAS 配置对应的受限 Web 容器基线 |

两套 Compose 相互独立。`compose.yaml` 不暴露 Code Navi Web/API，但会启动 privileged Piston 并把其 API 绑定到宿主 loopback；`compose.web.yaml` 构建 Web/API 镜像、由 Caddy 提供统一 HTTPS 入口，并在同一 Compose 网络内启动 privileged Piston（不发布宿主端口）供练习执行使用。两者都不提供远程仓库写入或生产数据库。

## 2. 本地 Web/API

先安装 Python 3.11+、Node 20.19+、后端可编辑依赖和前端依赖，命令见 [开发流程](../development/workflow.md)。从仓库根目录跨平台启动：

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
python scripts/dev.py
```

该入口不启动 Piston，学习与科研模块可用，练习页面的执行请求会返回执行服务不可用。

Windows 需要练习执行服务时使用：

```powershell
.\dev-start.cmd
```

`dev-start.cmd` 执行：

1. `.venv\Scripts\python.exe -m alembic upgrade head`；
2. 通过 Compose 启动 Piston；
3. 检查并安装固定 Python 3.12 runtime；
4. 启动 FastAPI `http://127.0.0.1:8000` 和 Next `http://localhost:3000`。

检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

预期返回 `{"status":"ok"}`。API 文档位于 `http://127.0.0.1:8000/docs`。

默认业务数据库为 `.code-navi/learning_poc.db`，学习 Runtime Event 默认写入 `var/runs`。练习记录默认写入 `var/learning-records.sqlite3`，可用 `COMPILER_DATABASE_PATH` 调整。新业务配置使用 `CODE_NAVI_DATABASE_URL` 和 `CODE_NAVI_EVENTS_DIR`；`LEARNING_DATABASE_URL` 仅为数据库兼容项。前端 API 地址使用 `NEXT_PUBLIC_CODE_NAVI_API_URL`，默认指向 `http://127.0.0.1:8000`。

`dev-start.cmd` 覆盖本地 Web 产品所需的数据库迁移、FastAPI、Next、Piston 和固定 Python runtime；它不启动 CLI 容器，也不启动独立的 `compose.web.yaml` Caddy 部署。停止时运行 `dev-stop.cmd`，它会关闭该启动脚本创建的前后端窗口并停止 Piston。

## 3. 本地 Provider

未设置 Provider 且没有 DeepSeek 凭据时使用 Mock，不联网。在线模式可以使用进程环境，或从仓库根目录写入本机配置：

```powershell
code-navi configure-provider --provider deepseek
```

本机配置保存在已忽略的 `.code-navi/provider.env`，服务启动时加载。DeepSeek 默认模型为 `deepseek-v4-flash`。使用进程环境时统一显式设置 `CODE_NAVI_PROVIDER`、`CODE_NAVI_MODEL` 和对应凭据：

| Provider | 必要配置 |
| --- | --- |
| OpenAI | `CODE_NAVI_PROVIDER=openai`、`CODE_NAVI_MODEL`、`OPENAI_API_KEY` |
| DeepSeek | `CODE_NAVI_PROVIDER=deepseek`、`CODE_NAVI_MODEL`、`DEEPSEEK_API_KEY` |

科研 Provider 状态接口不返回密钥；网页配置和连接测试默认禁用，只能在显式设置 `CODE_NAVI_ALLOW_BROWSER_PROVIDER_CONFIG=true` 且本机访问时使用。学习 API 的 DeepSeek 自动选择仍是兼容行为，不是新入口可依赖的统一规则。凭据不写入仓库、日志、Event 或前端变量。在线调用的内容和费用边界见 [高风险能力](../development/high-risk-capabilities.md)。

## 4. CLI 与 Piston Compose

前置检查：

```bash
docker version
docker compose version
docker compose config
```

首次启动会拉取固定 digest 的 Piston 镜像，并由 `compiler-runtime-setup` 从 Piston 包源安装 Python 3.12 runtime；这是显式联网和本机 Docker 副作用。Piston 使用 `privileged: true`，只适合作为当前本地原型。

启动交互式 CLI：

```bash
docker compose up --build
```

Compose 先通过 `cli-database-migrate` 将 `/data/code-navi.db` 升级到 Alembic head，再启动 shell。新 shell 会显示业务 `conversation_id` 和显式恢复命令；恢复已有主对话使用：

```bash
code-navi shell --project /workspace --events-dir /data/runs --resume <conversation-id>
```

`conversation_id` 只恢复同一项目作用域的主对话。`--session-id` 仍只组织 Runtime Event；临时 branch、focus 和 `last_context` 不跨进程保存。`code-navi ask` 保持无状态。

在另一个终端执行一次请求：

```bash
docker compose exec code-navi code-navi ask "这个项目的目标是什么？" \
  --project /workspace --events-dir /data/runs
```

完成信号是命令返回明确状态并在 `/data/runs` 产生对应 Event；只有模型文字而没有预期 Event 不算接线通过。

当前 Compose 直接支持 Mock、OpenAI 与 DeepSeek 凭据。通用 Agent 和练习 AI 复用同一组 Provider 与模型选择变量；练习执行与判题本身不依赖模型。启用 OpenAI Provider：

```powershell
$env:CODE_NAVI_PROVIDER = "openai"
$env:CODE_NAVI_MODEL = "<model-name>"
$env:OPENAI_API_KEY = "<api-key>"
docker compose up --build
```

练习 AI 复用 `CODE_NAVI_PROVIDER` 和 `CODE_NAVI_MODEL`；Provider 为 `mock` 或未配置模型时，只返回执行器、判题和规则结果。页面默认关闭 AI，用户明确开启后才会把本次源码与执行输出发送给已配置模型。

## 5. 受限 Web Compose

`compose.web.yaml` 构建三个服务：FastAPI 后端、Next standalone 前端和 Caddy。浏览器只访问 Caddy；`/api/*`、`/docs*`、`/openapi.json` 和 `/health` 转发到后端，其余请求转发到前端。后端容器启动时先执行 `alembic upgrade head`，再启动 Uvicorn。

当前配置针对仓库正在使用的 NAS 环境，不是可直接复制到任意主机的通用模板：

| 配置 | 当前值与影响 |
| --- | --- |
| 入口 | `https://91666.icu:25000` |
| TLS | 从宿主机 `/vol4/docker/xray/certs` 只读挂载既有证书和私钥 |
| 入口保护 | Caddy Basic Auth；用户名和 bcrypt hash 由部署环境注入 |
| 应用数据 | `code_navi_data` 命名卷挂载到后端 `/data` |
| 数据库 | `sqlite:////data/code-navi.db` |
| Provider 配置 | `/data/provider.env` |
| Runtime Event | `/data/runs` |
| 镜像标签 | `code-navi-backend:local`、`code-navi-frontend:local` |

启动前确认部署环境已经提供 `BASIC_AUTH_USER`、`BASIC_AUTH_HASH`、证书目录和对应域名解析。然后从仓库根目录执行：

```powershell
docker compose -f compose.web.yaml config
docker compose -f compose.web.yaml up -d --build
docker compose -f compose.web.yaml ps
```

首次启动会拉取固定 digest 的 Piston 镜像，并由 `compiler-runtime-setup` 一次性安装 Python 3.12 runtime；这是显式联网步骤，runtime 包持久化在 `piston_packages` 卷中。Piston 只在 Compose 网络内暴露 2000 端口，不经 Caddy 对外，浏览器无法直接访问。

如需使用本机已有的 Provider 配置，明确复制到持久化卷并重启后端：

```powershell
docker compose -f compose.web.yaml cp .code-navi/provider.env backend:/data/provider.env
docker compose -f compose.web.yaml restart backend
```

未复制 Provider 配置时，后端使用离线 Mock。Basic Auth 只保护当前 Caddy 入口，不替代应用级用户身份、资源所有权和 API 授权；公网服务条件见 [生产准入](production.md)。

## 6. 容器边界

### CLI 容器

| 项目 | 当前设置 |
| --- | --- |
| 基础镜像 | `python:3.11-slim`，分阶段构建 |
| 运行用户 | 非 root UID/GID `10001` |
| 项目目录 | `/workspace`，只读 bind mount |
| 业务数据库与 Event | `/data/code-navi.db` 与 `/data/runs`，位于 `code_navi_runs` volume |
| 根文件系统 | 只读；`/tmp` 为 tmpfs |
| 权限 | `no-new-privileges`，丢弃全部 Linux capabilities |
| 网络端口 | 不开放端口 |
| 入口 | `code-navi shell --project /workspace --events-dir /data/runs` |

同一 Compose 中的 Piston API 绑定到宿主 `127.0.0.1:2000`，runtime 包保存在 `code-navi-piston-packages` volume。Piston 容器为 privileged；Code Navi 容器本身仍保持上表的只读根文件系统、capability 丢弃和 `no-new-privileges`。

### Web 容器

| 项目 | 当前设置 |
| --- | --- |
| 后端基础镜像 | `python:3.11-slim`；非 root UID/GID `10001` |
| 前端基础镜像 | `node:22-alpine`；Next standalone 产物由 `node server.js` 启动 |
| 内部端口 | 后端 `8000`、前端 `3000`，只在 Compose 网络中暴露 |
| Piston 容器 | 固定 digest 的 `ghcr.io/engineer-man/piston`；privileged；2 CPU / 2 GB 内存 / 512 pids；仅在 Compose 网络内暴露 `2000`；runtime 包存于 `piston_packages` 卷 |
| 外部端口 | Caddy `25000` |
| 持久化 | 后端 `/data` 与 Caddy 的 data/config 命名卷 |
| API 地址 | 前端使用同源相对路径，由 Caddy 分流 |

修改任一容器边界时同步更新对应 Dockerfile、Compose、运行验证和相关安全测试。

## 7. 排查与清理

```bash
docker compose ps
docker compose logs code-navi
docker compose config
```

CLI/Piston Compose 依次检查构建、Piston 健康与 runtime、Provider 配置、CLI 结果、练习记录、Event 和只读权限错误。停止并保留数据卷：

```bash
docker compose down
```

删除容器、Event/练习记录 volume 和 Piston runtime volume：

```bash
docker compose down --volumes
```

`--volumes` 会永久删除 Event、练习记录和已安装的 Piston runtime。执行前确认数据不再需要。该 Compose 不包含 Web/API 产物，也没有版本化镜像或生产回滚命令。

Web Compose 使用独立项目名和数据卷，排查命令必须显式指定文件：

```powershell
docker compose -f compose.web.yaml ps
docker compose -f compose.web.yaml logs backend frontend caddy
docker compose -f compose.web.yaml down
```

不要在需要保留 SQLite、Provider 配置或 Event 时对 Web Compose 使用 `down --volumes`。当前 Web 镜像使用本地标签，没有版本化发布或已验证回滚流程。
