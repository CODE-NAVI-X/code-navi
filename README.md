# 05—作品代码：Code Navi

这是 Code Navi 的可复现源码包，来源于 `CODE-NAVI-X/code-navi` 的
`a0c1f502b49ef91fe635842a80adc0331c8f5cf8` 提交。

本包只保留运行、测试和复现所需内容：Python 后端、Next.js 前端、数据库迁移、
依赖清单、启动脚本和自动化测试。它不包含会议纪要、产品方案、开发计划、演示讲稿、
历史数据库、模型缓存、密钥或个人环境文件。

## 运行范围

- 后端：FastAPI，默认监听 `http://127.0.0.1:8000`
- 前端：Next.js，默认监听 `http://127.0.0.1:3000`
- 默认 Provider：`mock`，可离线启动；不需要模型权重或 ServiceID
- 可选的在线模型配置只从本机环境变量读取，绝不提交密钥

## 前置条件

- Windows PowerShell
- Python 3.11 或更高版本
- Node.js 20.19 或更高版本

## 最小复现步骤

在本目录运行：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev,server]"
Push-Location frontend
npm ci
Pop-Location
$env:CODE_NAVI_PROVIDER = "mock"
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe scripts\dev.py
```

另开一个 PowerShell 窗口验证后端：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

预期返回 `status: ok`。随后在浏览器打开 `http://127.0.0.1:3000`。

## 自动化验证

运行测试时使用独立数据库，避免写入日常开发数据：

```powershell
New-Item -ItemType Directory -Force .quality-tmp | Out-Null
$env:CODE_NAVI_DATABASE_URL = "sqlite:///./.quality-tmp/repro.db"
$env:CODE_NAVI_PROVIDER = "mock"
.venv\Scripts\python.exe -m pytest tests\test_dev_launcher_ports.py tests\test_research_cnn_flow.py -q
Push-Location frontend
npm run test
npm run build
Pop-Location
```

## 可选：动手实践代码执行

科研、学习和界面演示不依赖 Docker。若需要运行“动手实践”中的 Python 执行功能，
安装并启动 Docker Desktop 后运行 `dev-start.cmd`；该脚本会启动本地 Piston 容器。

## 边界说明

本包不随附模型权重。`mock` 模式用于离线复现系统流程；如需接入在线 Provider，
请参考 `.env.example`，仅在本机设置对应环境变量。科研辅助输出保留
`fact`、`inference` 和 `to_verify` 的证据边界，不把系统建议表述为实验事实或复现成功。
