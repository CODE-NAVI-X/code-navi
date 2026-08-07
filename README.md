# Code Navi

Code Navi（智教码航）面向学生自主学习、代码练习和项目科研。当前仓库已经具备 Kernel 与 CLI、知识点学习、科研对话、离线规则研究计划和受限检索的本地闭环，以及基于本机 Piston 的 Python 练习原型。

## 本地开发

后端要求 Python 3.11+，前端要求 Node 20.19+。从仓库根目录运行：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev,server]"
cd frontend
npm ci
cd ..
.venv\Scripts\python.exe -m alembic upgrade head
python scripts/dev.py
```

默认使用离线 Mock Provider。启动后访问 `http://127.0.0.1:3000`，后端健康检查位于 `http://127.0.0.1:8000/health`。

Windows 使用 `dev-start.cmd` 时会额外启动 Piston 并准备固定 Python runtime；直接运行 `scripts/dev.py` 不启动代码执行服务。练习模块的隔离边界与具体限制见本地部署和高风险能力文档。

科研页面位于 `/research`。它以可恢复的研究对话和规则研究计划为基础；难点分析和实验方案只有在用户点击确认后才调用模型，代码草案保持服务端固定模板并仅供预览。研究思维导图仅可视化已保存的画像、规则计划与证据包，不会触发模型或联网；节点明确显示事实边界、来源链接与访问时间。

## 文档入口

| 内容 | 文档 |
| --- | --- |
| Agent 指令与按任务加载规则 | [AGENTS.md](AGENTS.md) |
| 产品范围与当前路线 | [产品范围](docs/product/scope.md)、[产品路线](docs/product/roadmap.md) |
| 系统、Kernel 与前端架构 | [系统架构](docs/architecture/system.md)、[Kernel](docs/architecture/kernel.md)、[前端](docs/architecture/frontend.md) |
| 开发、测试与高风险能力 | [开发流程](docs/development/workflow.md)、[测试](docs/development/testing.md)、[高风险能力](docs/development/high-risk-capabilities.md) |
| 本地运行与生产准入 | [本地运行](docs/deployment/local.md)、[生产准入](docs/deployment/production.md) |

当前本地闭环不等于生产可用；实际能力和生产阻塞项分别以产品路线和生产准入文档为准。
