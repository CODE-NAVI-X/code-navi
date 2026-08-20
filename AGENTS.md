# Code Navi 执行入口

## 本文件职责

1. 确定指令优先级与冲突处理方式。
2. 根据任务类型，决定具体加载哪份专题文档。
3. 规定所有任务共同遵守的执行原则，例如先跑最小闭环、按风险验证和何时询问用户。
4. 统一“原型完成”“本地验证完成”“合并就绪”和“生产可用”等状态的含义。

## 1. 指令优先级与冲突处理

本文件适用于当前目录及其子目录。约束优先级为：用户当前明确指令 → 距目标文件最近的 `AGENTS.md` → 本文件 → 其他项目文档。

1. 当前指令与项目文档冲突时，停止冲突部分，说明冲突条款和实际影响，并请求用户裁决；不受冲突影响的部分可以继续。
2. 文档要求明显超过任务风险、产生重复工作或阻碍最小闭环时，指出具体条款并按用户决定处理，不机械执行。
3. 会改变产品含义、实验含义、稳定接口、真实外部资源或不可逆结果的歧义必须询问用户。
4. 能通过代码、现有上下文或低成本试运行确认的问题直接验证，不提出不必要的问题。

## 2. 文档导航

专题文档按职责组织：

| 领域 | 文档职责 |
| --- | --- |
| 产品 | [docs/product/scope.md](docs/product/scope.md) 定义稳定范围、模块和非目标；[docs/product/roadmap.md](docs/product/roadmap.md) 记录易变的状态、优先级和里程碑 |
| 产品设计 | `docs/decisions/` 记录已采纳的重要选择；`docs/specs/` 定义可验收行为；`docs/plans/` 记录实施顺序与当前切片 |
| 架构 | [docs/architecture/system.md](docs/architecture/system.md) 定义公共系统边界与跨组件接口；[docs/architecture/kernel.md](docs/architecture/kernel.md) 只管 Kernel 内部；[docs/architecture/frontend.md](docs/architecture/frontend.md) 只管 Web 与前端 |
| 开发 | [docs/development/workflow.md](docs/development/workflow.md) 负责日常实现与贡献；[docs/development/testing.md](docs/development/testing.md) 负责测试；[docs/development/high-risk-capabilities.md](docs/development/high-risk-capabilities.md) 负责高风险能力 |
| 部署 | [docs/deployment/local.md](docs/deployment/local.md) 负责当前 CLI、本地 Web/API、CLI Compose 和受限 Web 容器运行；[docs/deployment/production.md](docs/deployment/production.md) 负责公网服务、正式发布和生产准入 |

### USE WHEN：按任务路由（优先）

后续 Agent 应优先使用下表判断“何时读取哪些文档”；上方“文档职责”表仅用于了解文档内容，不代替任务路由。

按任务加载下列最小组合：

| 任务 | 必须读取 | 仅在对应条件出现时追加 |
| --- | --- | --- |
| 普通模块、Workflow 或 Skill 功能 | `docs/product/scope.md`、`docs/development/workflow.md` | 改变系统边界时加 `docs/architecture/system.md`；新增或修改测试时加 `docs/development/testing.md` |
| 产品范围、模块行为或非目标 | `docs/product/scope.md` | 涉及优先级、状态或阶段验收时加 `docs/product/roadmap.md` |
| Learning、Practice 与 Research 跨模块上下文 | `docs/product/scope.md`、`docs/architecture/system.md`、`docs/architecture/frontend.md` | 改持久化时加 `docs/development/workflow.md`、`docs/development/testing.md` |
| 缺陷诊断与修复 | `docs/development/workflow.md`、`docs/development/testing.md` | 改变产品行为时加 `docs/product/scope.md`；触及架构边界时加 `docs/architecture/system.md` |
| Kernel 修改或同步 | `docs/architecture/system.md`、`docs/architecture/kernel.md`、`docs/development/workflow.md`、`docs/development/testing.md` | 改变产品可见行为时加 `docs/product/scope.md` |
| Web 页面或前端交互 | `docs/product/scope.md`、`docs/architecture/frontend.md`、`docs/development/workflow.md` | 改 API 契约时加 `docs/architecture/system.md`；测试任务加 `docs/development/testing.md`；上线任务加 `docs/deployment/production.md` |
| FastAPI router、API 契约或前后端接线 | `docs/architecture/system.md`、`docs/development/workflow.md` | 改产品行为时加 `docs/product/scope.md`；改前端客户端时加 `docs/architecture/frontend.md`；测试任务加 `docs/development/testing.md`；上线任务加 `docs/deployment/production.md` |
| 纯测试、测试失败或合并检查 | `docs/development/testing.md` | 需要修改实现时加 `docs/development/workflow.md`；Kernel 测试加 `docs/architecture/system.md`、`docs/architecture/kernel.md` |
| 数据模型、SQLAlchemy、Alembic 或迁移 | `docs/architecture/system.md`、`docs/development/workflow.md`、`docs/development/testing.md` | 涉及生产数据库时加 `docs/deployment/production.md` |
| 代码执行、在线 Provider、真实联网写入或远程仓库操作 | `docs/architecture/system.md`、`docs/development/high-risk-capabilities.md`、`docs/development/testing.md` | 修改普通实现时加 `docs/development/workflow.md`；部署真实能力时加 `docs/deployment/production.md` |
| 当前 CLI/Docker、本地或受限环境 Web/API 启停、Provider 配置、数据库或 Event | `docs/deployment/local.md` | 改镜像或应用实现时加 `docs/development/workflow.md`；公网服务或正式发布时加 `docs/deployment/production.md` |
| 生产发布、Web/API 上线、受限服务或生产回滚 | `docs/deployment/production.md` | 同时读取被部署组件对应的架构和开发文档 |
| 仅修改文档 | 目标文档 | 只有修改内容涉及其他领域事实时，才读取该领域文档；不因文档任务加载完整开发或测试手册 |

先加载“必须读取”，确认任务实际触及追加条件后再加载对应文件。文件位于某目录中，不表示必须先读该目录的其他文档；表中未命中的文档不读取。跨领域任务按实际影响合并最小组合，不遍历全部文档。

若目标功能已经有相互链接的 Decision、Spec 或 Plan，行为判断优先读取 Spec，稳定原则或跨组件关系变化时追加 Decision，实施与状态任务追加 Plan。三类文档按当前任务选读，不要求成套遍历。目录职责和当前入口见 [docs/README.md](docs/README.md)。

## 3. 通用执行流程

1. 在实际仓库和工作树中定位入口、公开接口、相关测试和运行命令，不为上传另建项目副本。
2. 先用真实接口路径跑通最小、可观察、可纠错的端到端闭环；允许使用 Mock、临时数据、受限沙箱或可推翻原型。
3. 根据运行结果纠错，再增加分层、抽象、兼容和完整验证。
4. 早期接口保持可修改；只有闭环已跑通，或多个组件必须并行依赖时才固定契约。
5. 只修改受影响内容并进行风险相称的验证；完成任务要求后立即交付。

首次闭环前，不建立完整异常矩阵、验证矩阵、兼容层、迁移体系、证据包或校验清单。SHA-256 只用于外部下载、发布产物、跨环境传输或并发修改调查；Git 提交号可用于明确代码来源。

缺陷修复先复现实际故障，再增加回归测试。高风险能力先用 Mock、dry-run 或隔离资源试运行，接触真实外部资源前展示目标和动作并按风险取得确认。文档修改只核对受影响的代码、命令、路径和状态，不运行无关的完整测试。

## 4. 仓库级底线

1. 模型文本不得冒充执行结果、测试通过、外部写入或人工决定。
2. 密钥、完整凭据、个人信息和未脱敏业务数据不得进入仓库、日志、Event、测试数据或模型上下文。
3. 产品和系统不变量以任务命中的 `docs/product/`、`docs/architecture/` 文档为准；测试方法和质量门以 [docs/development/testing.md](docs/development/testing.md) 为准。
4. 正式文档只保留结论、依据、方法、结果和具体限制，不写内部推理、执行流水账或无关的写作说明。限制必须指出来源及其影响的具体结论。

## 5. 状态与完成

1. **原型完成**：最小闭环已运行，范围和具体限制已说明。
2. **本地验证完成**：相关实现和验证在指定本地环境通过。
3. **合并就绪**：实现、相关测试、受影响文档和配置一致，必要质量门通过。
4. **生产可用**：目标环境中的部署、权限、安全和验收均已实际完成。

本地原型可以作为原型任务的完整交付，但不得描述为合并就绪或生产可用。创建 PR、补齐无关文档和增加无收益验证不是所有任务的通用完成条件。
