# Docker 部署

## 一键启动

服务器安装 Docker Engine 与 Docker Compose 后，在项目根目录执行：

```bash
docker compose up --build
```

Compose 会构建 `code-navi:local`、只读挂载当前项目、拉起 CLI 容器，并把 Event JSONL 保存到 `code_navi_runs` volume。默认使用离线 Mock Provider，不需要密钥或其他私有仓库凭据。

部分新版 Compose 会把 `up` 的前台输入用于 Compose 菜单，而不转发给服务。此时保持 `up` 运行，并在另一个终端连接交互 Shell：

```bash
docker compose attach code-navi
```

也可以在已启动的容器中执行一次性问题：

```bash
docker compose exec code-navi code-navi ask "这个项目的目标是什么？" \
  --project /workspace --events-dir /data/runs
```

停止服务：

```bash
docker compose down
```

同时删除 Event volume：

```bash
docker compose down --volumes
```

删除 volume 会永久删除容器内保存的 Event 日志。

## 在线 Provider

在线运行前在服务器环境中设置变量，不要把密钥写入镜像或提交到仓库：

```bash
export CODE_NAVI_PROVIDER=openai
export CODE_NAVI_MODEL=<model-name>
export OPENAI_API_KEY=<api-key>
docker compose up --build
```

## 容器边界

- 基础镜像为 `python:3.11-slim`，构建阶段和运行阶段分离。
- 最终镜像不包含 Git、编译工具、测试、文档或构建缓存。
- 进程使用固定非 root UID/GID `10001`。
- 项目挂载到 `/workspace` 且只读。
- Event 只写入 `/data/runs`，由 Docker volume 持久化。
- 根文件系统只读，`/tmp` 使用临时文件系统。
- 容器不开放端口；当前交付物是 CLI，不是 HTTP 服务。

## 常用检查

查看容器状态和日志：

```bash
docker compose ps
docker compose logs code-navi
```

清理并重新构建：

```bash
docker compose build --no-cache
docker compose up
```
