# Web 容器化部署（NAS / 局域网 → 公网）

本页是 `compose.web.yaml` + `Caddyfile` 的使用说明。它们把当前 **FastAPI 后端**与 **Next.js 前端**打包成三个容器：`backend`、`frontend`、`caddy`。

> 注意：仓库根的 `Dockerfile` / `compose.yaml` 仍是**仅 CLI** 容器（`code-navi shell`），与本页的 Web 底座无关。

## 目标架构

```
浏览器 ──► Caddy (:25000 / 80 / 443) ──► frontend (Next.js, :3000)   页面
                              │             └── /api/*、/docs 等 ─► backend (FastAPI, :8000)
                              └── 持久化卷 code_navi_data: /data
                                 ├── code-navi.db   （SQLite）
                                 ├── provider.env   （Provider 凭据）
                                 └── runs/          （Kernel 事件日志）
```

浏览器始终只访问 **Caddy 一个入口**，`/api/*` 由 Caddy 反向代理到后端（同源），因此前端 bundle 里**没有后端地址、没有 CORS**。同一份镜像既能在局域网跑，也能切到公网域名——无需重新构建。

## 数据卷

`code_navi_data` 命名卷挂到后端 `/data`，三个写点全部落在这里：

| 路径 | 内容 | 由谁写 |
| --- | --- | --- |
| `/data/code-navi.db` | SQLite 业务库 | `CODE_NAVI_DATABASE_URL` |
| `/data/provider.env` | Provider 凭据 | `CODE_NAVI_DATA_DIR` → `.code-navi/provider.env` |
| `/data/runs/` | Kernel 事件 JSONL | `CODE_NAVI_EVENTS_DIR` |

重建镜像、`docker compose up` 升级都不会丢数据。**凭据不进镜像**：本地已有的 `.code-navi/provider.env` 首次部署时拷进卷一次：

```bash
docker compose -f compose.web.yaml up -d --build
docker compose -f compose.web.yaml cp .code-navi/provider.env backend:/data/provider.env
docker compose -f compose.web.yaml restart backend
```

不拷也行——后端用离线 Mock Provider 跑，不联网。

## 局域网先跑起来

```bash
docker compose -f compose.web.yaml up -d --build
```

- 前端：`http://<NAS-IP>:25000`
- API 文档：`http://<NAS-IP>:25000/docs`

无需防火墙额外放行 8000/3000（它们只在容器内网 `web` 网络中，不暴露到宿主机）。只需放行宿主机的 **25000**。

## 一键切公网（DDNS + Caddy 自动 HTTPS）

前置：NAS 上起一个 DDNS 域名解析到本机公网 IP；路由器把 **80** 与 **443** 转发到 NAS。

1. `compose.web.yaml` 取消注释 `80:80` / `443:443`。
2. `Caddyfile` 把 `:80` 站点块替换为你的域名站点块（文件内有注释好的示例）。
3. 重启 Caddy：`docker compose -f compose.web.yaml up -d caddy`。

Caddy 会向 Let's Encrypt 自动申请并续期证书，全程 HTTPS。**前端 bundle 不用改、不用重新构建**——因为 API 是同源的 `/api/*`。

## 生产注意（公网前必读）

当前 Web 后端**没有任何鉴权**：学习固定 `poc-user`，科研凭 `conversation_id` 可读。公网裸奔意味着任何人可调用 API、可能触发在线 Provider 产生费用。`docs/deployment/production.md` 把鉴权列为 Web/API 生产阻塞项。公网暴露前至少要先补上认证/授权，或先用 VPN/防火墙限定访问面。
