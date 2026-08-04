# 本地运行与 CLI Docker

## 1. 当前可运行范围

仓库有三种本地运行入口：

| 方式 | 覆盖范围 | 当前定位 |
| --- | --- | --- |
| `python scripts/dev.py` | FastAPI、Next 与依赖检查 | 跨平台本地 Web/API 开发闭环；迁移需先单独执行 |
| Windows `dev-start.cmd` | FastAPI、Next、迁移与依赖检查 | Windows 本地开发入口 |
| Docker Compose | `code-navi` CLI、Provider、Kernel 和 Event volume | CLI 容器验证基线 |

当前 Compose 不构建或暴露 Web/API，也不提供代码执行沙箱、远程仓库写入、身份系统或生产数据库。

## 2. 本地 Web/API

先安装 Python 3.11+、Node 20.9+、后端可编辑依赖和前端依赖，命令见 [开发流程](../development/workflow.md)。从仓库根目录跨平台启动：

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
python scripts/dev.py
```

Windows 也可启动：

```powershell
.\dev-start.cmd
```

脚本执行：

1. `.venv\Scripts\python.exe -m alembic upgrade head`；
2. 启动 FastAPI `http://127.0.0.1:8000`；
3. 启动 Next `http://localhost:3000`。

检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

预期返回 `{"status":"ok"}`。API 文档位于 `http://127.0.0.1:8000/docs`。

默认数据库为 `.code-navi/learning_poc.db`，学习 Runtime Event 默认写入 `var/runs`。新配置使用 `CODE_NAVI_DATABASE_URL` 和 `CODE_NAVI_EVENTS_DIR`；`LEARNING_DATABASE_URL` 仅为数据库兼容项。前端 API 地址使用 `NEXT_PUBLIC_CODE_NAVI_API_URL`，默认指向 `http://127.0.0.1:8000`。

停止时关闭脚本打开的两个窗口。`dev-stop.cmd` 还会终止端口 8000 和 3000 上的监听进程；运行前确认这些端口没有承载其他服务。

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

## 4. CLI Docker

前置检查：

```bash
docker version
docker compose version
docker compose config
```

启动交互式 CLI：

```bash
docker compose up --build
```

在另一个终端执行一次请求：

```bash
docker compose exec code-navi code-navi ask "这个项目的目标是什么？" \
  --project /workspace --events-dir /data/runs
```

完成信号是命令返回明确状态并在 `/data/runs` 产生对应 Event；只有模型文字而没有预期 Event 不算接线通过。

当前 Compose 直接支持 Mock 和 OpenAI 环境变量。启用 OpenAI：

```powershell
$env:CODE_NAVI_PROVIDER = "openai"
$env:CODE_NAVI_MODEL = "<model-name>"
$env:OPENAI_API_KEY = "<api-key>"
docker compose up --build
```

DeepSeek 凭据尚未写入当前 Compose 环境白名单；不要仅设置宿主环境后假定容器已经获得该配置。

## 5. 容器边界

| 项目 | 当前设置 |
| --- | --- |
| 基础镜像 | `python:3.11-slim`，分阶段构建 |
| 运行用户 | 非 root UID/GID `10001` |
| 项目目录 | `/workspace`，只读 bind mount |
| Event 数据 | `/data/runs`，位于 `code_navi_runs` volume |
| 根文件系统 | 只读；`/tmp` 为 tmpfs |
| 权限 | `no-new-privileges`，丢弃全部 Linux capabilities |
| 网络端口 | 不开放端口 |
| 入口 | `code-navi shell --project /workspace --events-dir /data/runs` |

修改这些边界时同步更新 Dockerfile、Compose、运行验证和相关安全测试。

## 6. 排查与清理

```bash
docker compose ps
docker compose logs code-navi
docker compose config
```

依次检查构建、容器状态、Provider 配置、CLI 结果、Event 和只读权限错误。停止并保留 Event：

```bash
docker compose down
```

删除容器和 Event volume：

```bash
docker compose down --volumes
```

`--volumes` 会永久删除 volume 内的 Event。执行前确认数据不再需要。当前 Compose 没有版本化镜像、Web/API 产物或生产回滚命令，不能作为生产发布流程。
