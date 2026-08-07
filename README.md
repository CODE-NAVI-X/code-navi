# Code Navi

Code Navi（智教码航）面向学生自主学习、代码练习和项目科研。当前仓库已经具备 Kernel 与 CLI、知识点学习，以及科研对话、离线规则研究计划和受限检索的本地闭环；代码练习仍是占位能力。

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

科研页面位于 `/research`。它以可恢复的研究对话和规则研究计划为基础；难点分析和实验方案只有在用户点击确认后才调用模型，代码草案保持服务端固定模板并仅供预览。用户还可保存实验结果证据包，并主动生成论文蓝图；蓝图只组织已保存证据与待验证缺口，不是论文全文或投稿结论。研究思维导图仅可视化已保存的画像、规则计划与证据包，不会触发模型或联网；节点明确显示事实边界、来源链接与访问时间。

## 科研辅助本地演示闭环

当前可演示流程为：**对话澄清 → 规则研究计划 → 用户主动触发的受限学术检索 → 难点分析 → 实验方案 → 用户确认后代码草案 → 实验结果证据包 → 论文蓝图 → 研究思维导图**。

- 检索不是自动行为：只有用户主动提交查询后，才会通过受限来源（当前为 OpenAlex、Crossref、arXiv）生成 `EvidenceBundle`。标题、作者、年份和来源摘要是 `fact`；关键词关联是 `inference`；摘要未覆盖的实验、数据集和结论是 `to_verify`。
- DeepSeek 仅可改善科研追问、难点分析和实验方案的表达；会话、确认、事实边界、受限来源和降级仍由规则控制。无密钥、超时或输出不合法时保持离线规则可用。
- 代码草案必须由用户明确确认后才生成，且只在浏览器中预览、复制或下载文本；不会自动写入项目、自动安装依赖或自动执行代码。
- 实验结果证据包只保存用户主动粘贴的文本、表格文本或图表说明；`fact` 表示用户提交事实，系统不会读取原始数据、运行代码或独立复核。论文蓝图为规则生成的章节与证据清单，实验章节只引用该证据包，相关工作只引用已保存的受限来源。
- 导图基于已保存的画像、规则计划与 EvidenceBundle，用 XYFlow 和 Dagre 显示真实节点与后端边关系；当前支持真实 SVG 导出。PNG 需要额外且尚未验证稳定性的浏览器栅格化方案，保留为后续增强。
- 已完成隔离的外部 Skill 选型试用：仅将 Socratic 的“一次一问、证据/替代解释/可行性”作为本地模型追问策略参考；未接入外部 Prompt、脚本、完整框架或运行时依赖。详见[外部科研 Skill 评估](docs/research-skill-evaluation.md)和 [EvoScientist 设计笔记](docs/references/evo_scientist_experiment_notes.md)。

当前**尚未实现**论文全文下载与精读、论文初稿/评审/修订/投稿前检查、Markdown/DOCX/LaTex 导出、自动检索、自动实验、自动投稿、自动写入项目、自动安装依赖、自动执行代码，以及多 Agent/MCP；不能把建议或摘要范围外的信息表述为已验证事实。

## 文档入口

| 内容 | 文档 |
| --- | --- |
| Agent 指令与按任务加载规则 | [AGENTS.md](AGENTS.md) |
| 产品范围与当前路线 | [产品范围](docs/product/scope.md)、[产品路线](docs/product/roadmap.md) |
| 系统、Kernel 与前端架构 | [系统架构](docs/architecture/system.md)、[Kernel](docs/architecture/kernel.md)、[前端](docs/architecture/frontend.md) |
| 开发、测试与高风险能力 | [开发流程](docs/development/workflow.md)、[测试](docs/development/testing.md)、[高风险能力](docs/development/high-risk-capabilities.md) |
| 本地运行与生产准入 | [本地运行](docs/deployment/local.md)、[生产准入](docs/deployment/production.md) |
| 外部科研 Skill 试用与论文设计依据 | [Skill 评估](docs/research-skill-evaluation.md)、[EvoScientist 笔记](docs/references/evo_scientist_experiment_notes.md) |
| 后续论文初稿/评审接口边界 | [论文工作流设计](docs/research-paper-workflow-design.md) |

当前本地闭环不等于生产可用；实际能力和生产阻塞项分别以产品路线和生产准入文档为准。
