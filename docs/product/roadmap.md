# 产品状态与交付路线

## 1. 当前实现基线

执行任务时以实际代码、测试和运行结果为准。当前仓库的能力边界如下：

| 能力 | 当前状态 | 实际范围 |
| --- | --- | --- |
| Kernel 与 CLI | 本地可运行 | `code-navi ask`、`code-navi shell` 经 `AgentRuntime` 使用 Mock、OpenAI 或 DeepSeek Provider，并保存 Event JSONL |
| 知识点学习 | 本地闭环已实现 | FastAPI 与 Next 页面可提交知识点；模型调用经 Runtime；结果写入按学习会话隔离的 SQLite 笔记 |
| 科研助手 | 本地闭环已实现 | 动态研究对话、画像/会话恢复、规则研究计划、用户主动的 OpenAlex/Crossref/arXiv 元数据与摘要检索和 EvidenceBundle、用户主动选择的引用占位、引用完整性检查与参考文献雏形、难点分析、实验方案、用户确认后的代码草案、实验结果证据包、用户主动的五维复现项目评估与改进任务、论文蓝图、结构化审稿、人工确认修订任务、逐段候选改写与可回退版本管理、用户配置的投稿准备档案与本地规则检查、用户主动受控导出与可追溯思维导图；也可加载用户确认的学习背景；模型不可用时回退到规则。复现评估已提供 A Pipeline 的只读适配边界，主线尚未存在该合同时对应维度保持不可评估 |
| 代码测试练习 | 本地原型已实现 | Python 3.12 代码通过本机 Piston 执行；支持自由运行、服务端题目判定、规则反馈、可选 AI 指导和匿名学习记录 |
| 跨模块上下文 | Learning → Research 与 Learning → Practice 已接通 | Research 继续使用用户确认的可恢复上下文；Practice 由服务端 launch 绑定 Workspace、可选 Task、Focus 与本地画像键，`FlowPayload` 只作轻量主题恢复 |
| Web/API 宿主 | 本地与受限容器可用 | Next 前端、FastAPI、本地启动脚本，以及由 Caddy 统一入口的 Web Compose 已存在；`/health` 仅检查后端进程存活 |
| 业务持久化 | 本地可用 | 学习笔记、兼容科研会话、动态对话和证据共用 SQLAlchemy Base；Alembic 管理当前 schema |
| Docker | 两套容器基线 | `compose.yaml` 运行 CLI、Piston 和 runtime 初始化；`compose.web.yaml` 构建 FastAPI、Next standalone 与 Caddy，但尚未接入 Piston |
| 生产 Web 服务 | 部署骨架已实现 | 当前 Web Compose 使用本地标签镜像和特定 NAS 的证书挂载；应用身份授权、版本化发布、生产数据运维、监控和已验证回滚尚未完成 |
| 代码执行 | 本地 Piston 原型 | 已显式配置网络、进程、文件、输出、并发与容器资源限制并提供 live 隔离检查；privileged 容器、应用授权和真实隔离结果仍阻塞生产化 |
| 远程仓库写入 | 未实现 | 不得描述为可用能力 |
| 持久工作区编排 | Learning 与 Practice 本地验证完成 | Workspace、Task、Learning Activity、PracticeOutcome、Practice Activity、基础页面和刷新恢复已接通；Research、推荐与统一 Artifact 尚未接入 |
| 学习入口页改版 | 已实现，本地验证完成 | 首屏为发起学习、继续最近学习和探索计算机方向；六大领域作为稳定导航，多对多归属的方向胶囊支持多选，已选方向在搜索框下方显示并可逐项取消 |
| Practice 集成进 Learning | 已实现，本地验证完成 | 已落地 Learning 内“动手实践”、规范路由与兼容 redirect、独立 Practice Capability、PracticeOutcome、分 mode launch、Activity 和三来源知识缺口投影 |
| 身份角色字段（学生/教师） | 本地验证完成 | 注册可选身份、账户设置可切换身份、设备会话合并管理与一键/批量下线 |
| 班级管理 | 本地验证完成 | 教师建班/8位邀请码、学生加入、教师查看成员与邮箱、私有教学备注编辑、移除成员管理；学生端隐私保护 |

## 2. 当前优先事项

### 2.1 Persistent Workspace Foundation

Persistent Workspace Foundation 已完成本地 Learning 最小纵向闭环：Task-first、Workspace-first 和直接 Learning 均由服务端持久化并可刷新恢复。具体行为和后续切片见 [持久工作区与自由编排 Spec](../specs/persistent-workspace-orchestration.md) 与 [实施计划](../plans/persistent-workspace-orchestration-rollout.md)。

Foundation 当时只接入 Learning；后续 Practice Capability-first 已完成。Research、推荐引擎、统一 Artifact 表和身份系统仍按独立切片推进。

### 2.2 学习入口页改版

学习入口页的目标行为已由 [Learning Entry Spec](../specs/learning-entry.md) 统一：首屏只保留发起学习、继续最近学习和探索计算机方向三个一级区块；六大领域作为稳定导航，领域下提供可多选的方向胶囊，方向可跨领域归属，选择结果只形成探索上下文。已选方向在搜索框下方显示并可逐项取消，不再提供重复的完整方向入口。实现顺序、接口风险和退出条件见 [学习入口页改版计划](../plans/learning-entry-redesign.md)。

当前代码已移除独立方向首屏和单选方向学习快照；最近学习从持久化 Activity 定位原始 Notebook 结果，材料输入在页面与服务端以 64 字符为界处理，因此该项计为本地验证完成。

### 2.3 Practice 集成进 Learning

产品与系统边界已由 [Practice 集成进 Learning 决策](../decisions/practice-in-learning-experience.md) 确立：全局入口收敛为工作台、学习和科研；Practice 在产品中作为 Learning 的“动手实践”，在系统中继续维护独立执行、判题和安全边界。

该切片已按 [Learning–Practice Integration Spec](../specs/learning-practice-integration.md) 与 [实施计划](../plans/learning-practice-integration-rollout.md) 落地：页面使用规范路由，旧路径保留查询参数并 redirect；自由运行与题目提交分别取得对应 mode 的 launch；服务端持久化安全 PracticeOutcome、派生 Activity，并提供三来源复盘投影。独立 SQLite CompilerRecord 与内存 Submission 仍是兼容事实源，不替代共享数据库中的 PracticeOutcome。

### 2.4 收敛已有本地闭环

1. 保持所有 ORM schema 变化同步新增 Alembic revision，并验证空库和受影响旧库升级；
2. 保持学习、科研、CLI 的 Provider 配置和错误语义一致；
3. 明确 Runtime Event、学习会话、科研对话和兼容科研会话标识的职责；
4. 在现有“确认后新建科研会话”基础上，按实际需求评估加入现有科研会话，并保持每次来源与最终快照可追溯。

Research 当前本地演示覆盖的内部步骤为：**对话澄清 → 研究计划 → 用户主动受限检索 → 用户主动选择受限证据的引用占位 → 难点分析 → 实验方案 → 用户确认后代码草案 → 实验结果证据包 → 用户主动五维复现项目评估与改进任务 → 论文蓝图 → 用户粘贴初稿 → 结构化审稿 → 人工确认修订任务 → 修订预览 → 用户保存投稿准备档案 → 用户确认投稿前检查 → 用户主动受控导出 → 思维导图**。这条路径不约束 Task-first、Workspace-first 或 Capability-first 入口。其中 EvidenceBundle 只保存受限来源的元数据和摘要范围；引用占位和参考文献雏形只能基于当前会话已保存来源，缺失作者、年份、来源或标识会标为待核对，不自动联网、插入或改写文本。实验结果证据包仅保存用户主动提交文本，`fact / inference / to_verify` 不可互相替代。五维复现评估只衡量记录与证据完整度；缺少 Pipeline、来源或实验记录的维度保持不可评估，改进任务的接受、跳过和完成状态全部由用户控制。论文蓝图只列出已保存证据、缺口和禁止主张；结构化审稿、修订任务和投稿前检查都是建议，不替代导师、同行评审或投稿资格判断，修订预览也不会覆盖原稿。投稿准备档案只保存用户已知的目标方向、匿名、篇幅/章节与伦理/数据要求；检查不联网抓取 venue 官网或模板，缺失信息仍标为待核验。受控导出仅在用户点击后返回 Markdown 与 JSON 投稿前辅助包，包含研究/计划摘要、投稿准备档案、检查清单、修订依据与已选引用摘要；不包含初稿或修订稿全文，不会写入项目或自动投稿，也不宣称是最终投稿格式。思维导图只读取已保存状态，使用既有 `@xyflow/react` 与 Dagre 展示后端节点/边：默认呈现摘要卡，用户展开后进入专注工作区，节点详情按需显示；它不联网、不读论文全文、不调用模型、不写文件，支持 SVG 导出；PNG 作为后续增强，当前未实现。外部 Skill 评估只吸收一次一问、证据和可行性检查的提问策略；不接入多 Agent、MCP、外部脚本或自动执行，详见 [评估记录](../research-skill-evaluation.md)。

引用阶段现在额外提供用户主动运行的本地完整性检查：只检查当前会话已选择来源的章节映射、重复选择、未插入占位和元数据缺口，并保存检查快照供刷新后恢复；它不验证论文全文或引用事实是否正确。

参考文献草案按已保存选择稳定整理为可复制文本，每条保留 `SelectedCitation` 与原始链接，并集中展示缺失字段；所有条目均为非正式格式，不自动校验或转换为 BibTeX、GB/T、APA、IEEE 或期刊格式。

导师演示前可按 [科研论文辅助演示检查表](../research-paper-assistance-demo-checklist.md) 核对本地启动、事实边界、规则降级、会话恢复和已知限制；该清单不改变任何产品能力或权限边界。

### 2.5 收敛代码练习本地闭环

当前 Mock/假适配器测试、本机 Piston 接线和显式 live 隔离检查已经存在。下一步先取得真实隔离检查结果并统一持久化与身份边界，再扩展语言或公开部署。

完成条件：

1. 移除或隔离 Piston 的宿主级 privileged 依赖，并实际验证网络、文件系统、进程和临时工作区清理；
2. 将学习记录纳入明确的数据迁移、所有权和删除流程；
3. 在隔离环境运行固定可信示例和恶意边界样例，确认服务端限制不能被请求覆盖；
4. 保持执行器事实、规则判定和 AI 建议在 API、页面、记录和测试中一致。

### 2.6 生产化 Web/API

现有本地 Web/API 和受限 Web Compose 不等于生产可用。进入生产前补齐应用身份与授权、跨设备会话、版本化镜像、数据库备份与恢复、速率限制、监控和隔离环境回滚验证。具体准入见 [生产准入](../deployment/production.md)。

## 3. 条件推进能力

代码执行的生产隔离与新增语言、远程仓库写入、新增全文或付费资料源、多 Agent、自动评分和自动发布分别建立独立闭环，不因现有本地 Piston、Web 页面或在线 Provider 可用而自动获得权限。当前科研助手的初稿、结构化审稿、修订任务、版本预览、投稿前检查与受控导出没有生产级文件存储和隐私托管；当前引用占位也只是作者/导师核对用的元数据草案。仍**未实现**论文全文下载与精读、完整 BibTeX、格式化参考文献、DOCX/PDF 导入、期刊模板适配、引用格式自动校验、ZIP/DOCX/PDF/LaTeX 最终投稿包导出、自动投稿、自动检索、自动写入项目、自动安装依赖、自动执行代码或多 Agent/MCP；代码草案仅供用户显式操作后的本地预览、复制或下载。

## 4. 状态更新

1. 路线按实际运行结果推进，不以页面存在、接口草图或模型输出代替闭环。
2. 每次只更新受影响能力，不要求三个系统 Capability 同步达到相同成熟度。
3. 状态使用根 [AGENTS.md](../../AGENTS.md) 定义的“原型完成”“本地验证完成”“合并就绪”和“生产可用”。
4. 稳定产品边界变化时同步检查 [scope.md](scope.md)。
