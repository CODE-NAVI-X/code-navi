# 论文分析真模型对比操作说明（GCN/Cora 场景）

> 状态：仅操作说明，本文档编写当日**未调用任何真实 Provider、未消耗任何额度**。
> 目的：让用户在已配置 DeepSeek 等 Provider 的本机，对"改造前（`88f9886`）"与"改造后（当前 HEAD）"各跑一次 GCN/Cora 论文分析，把输出留存在 `var/` 下人工对比提示词改造的实际效果。

## 背景

2026-08-30 检查点 3 对论文分析的模型上下文和输出契约做了强化（`core_judgment`、每条 `relevance`/`suggested_action`、`summary`、反面清单系统提示词、接地校验）。这些改动的**结构与边界已由 Fake Provider 测试验证**，但提示词的实际输出质量未经真模型验证，需要本对比来确认。

## 前置条件

1. 本机已配置可用 Provider：`GET /api/v1/research/provider/status` 返回 `configured: true`（网页配置或环境变量均可）。
2. 两个 worktree 都存在：
   - 改造前：`C:\Users\陈盛漳\Desktop\code-navi-workspace\code-navi-research-completion-local`（HEAD `88f9886`，运行现场 3011/8011，**不要在该现场直接改数据库**，对比用临时库）。
   - 改造后：`C:\Users\陈盛漳\Desktop\code-navi-workspace\code-navi-research-feedback-on-current`（检查点 3 之后的 HEAD，用 3023/8023 实例）。

## 操作步骤（每个基线各跑一遍）

1. 用临时数据库启动该基线的后端（端口分开设，避免互相覆盖）：

   ```powershell
   # 改造前（88f9886）
   cd C:\Users\陈盛漳\Desktop\code-navi-workspace\code-navi-research-completion-local
   $env:PYTHONPATH = 'src'
   $env:CODE_NAVI_DATABASE_URL = 'sqlite:///C:/Users/陈盛漳/Desktop/code-navi-workspace/code-navi-research-completion-local/var/compare-before.db'
   E:\Anaconda\python.exe -m alembic upgrade head
   E:\Anaconda\python.exe -m uvicorn code_navi.server:app --host 127.0.0.1 --port 8012

   # 改造后（当前 HEAD）
   cd C:\Users\陈盛漳\Desktop\code-navi-workspace\code-navi-research-feedback-on-current
   $env:PYTHONPATH = 'src'
   $env:CODE_NAVI_DATABASE_URL = 'sqlite:///C:/Users/陈盛漳/Desktop/code-navi-workspace/code-navi-research-feedback-on-current/var/compare-after.db'
   E:\Anaconda\python.exe -m alembic upgrade head
   E:\Anaconda\python.exe -m uvicorn code_navi.server:app --host 127.0.0.1 --port 8024
   ```

2. 各自浏览器登录（真实注册/登录），创建会话，在"方向与文献"用关键词 `Semi-Supervised Classification with Graph Convolutional Networks`（作者 Thomas N. Kipf、Max Welling）显式检索并保存论文，选择进入论文深度分析，点击生成分析。**两次使用相同的检索词和相同论文。**
3. 把两次返回的论文分析 JSON 分别另存为：
   - `code-navi-research-completion-local\var\paper-analysis-before.json`
   - `code-navi-research-feedback-on-current\var\paper-analysis-after.json`
   （浏览器开发者工具复制响应，或用 `Invoke-RestMethod ... | ConvertTo-Json -Depth 10 | Out-File` 均可。）
4. 对比清单（人工判断）：
   - 改造后是否有置顶 `core_judgment`、结尾 `summary` 和唯一 `next_action`；
   - 每条分析是否填写 `relevance` 与 `suggested_action`，且引用了摘要/正文中的具体内容（方法名、数据集名、具体结论）；
   - 是否消除了"建议""注意""需要进一步研究"类空话和通用鼓励话术；
   - `to_verify` 是否仍覆盖数据划分、超参数、Accuracy 等摘要外信息（不得因加厚而升格为事实）；
   - `generation_mode` 均应为 `llm` 且带 `run_id`（可在 `var/runs/<conversation_id>/` 核对审计事件）。

## 边界

- 对比只读取/生成分析，不下载论文全文、不执行论文代码；正文读取仅限允许的公开 arXiv 来源且由用户点击触发。
- 两次运行的数据库都是临时新建文件，不触碰 `research-smoke.db`、`viewer.db` 或任何现有运行现场。
- 输出 JSON 只留在本机 `var/` 下，不上传、不进 Git。
