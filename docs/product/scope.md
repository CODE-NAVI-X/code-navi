# 产品范围与模块

## 1. 产品定位

Code Navi（智教码航）面向学生自主学习、代码练习和项目科研。用户可以从长期工作上下文、当前目标或具体工作方式任意开始，不要求按固定教学路径使用。

全局产品入口固定为：

1. 工作台；
2. 学习；
3. 科研。

“用户”保留给真实账号或明确的本地个人资料能力，不用学习画像冒充用户中心。

系统继续维护 Learning、Practice、Research 三个独立 Capability。Practice 在产品信息架构中进入 Learning 的“动手实践”，但代码执行、隐藏测试、判题、资源限制和原始结果仍由 Practice 维护。产品入口不等同于后端 Capability、路由目录或代码目录；具体决策见 [Practice 集成进 Learning](../decisions/practice-in-learning-experience.md)。

Workspace 与 Task 位于产品编排层。Workspace 组织长期上下文，Task 聚焦目标和成功标准；Capability 提供活动和产物。完整产品模型见 [Workspace–Task–Capability 决策](../decisions/workspace-task-capability-model.md)，用户可观察行为见 [持久工作区与自由编排 Spec](../specs/persistent-workspace-orchestration.md)。

## 2. 产品编排边界

1. 每个 Task 属于一个 Workspace；每个 Activity 属于一个 Workspace，并可以不关联 Task。
2. 用户可以通过 Task-first、Workspace-first 或 Capability-first 进入产品，任一入口都不成为其他入口的前置条件。
3. Task 完成由目标和成功标准决定，不使用模块访问数量或覆盖率计算。
4. 统一 Activity 只保存模块产物引用和安全摘要，不接管模块事实来源或权限。
5. 编排建议可以跳过，不自动执行能力或改变 Task 状态。

当前代码已实现 Persistent Workspace Foundation 及 Practice Capability-first 接线：Workspace、Task、Learning Activity、PracticeOutcome 和 Practice Activity 由服务端持久化，支持 Task-first、Workspace-first、独立 Learning 与独立 Practice；Research 和推荐尚未接入编排层。Practice 已迁入 Learning 规范路由，服务端 launch 绑定编排上下文，复盘视图按来源聚合 QuizAttempt、ConfusionMark 与 PracticeOutcome。交付状态与后续顺序见 [roadmap.md](roadmap.md)。

## 3. Capability 与产品职责

### 3.1 知识点学习

接收概念、问题或用户提供的材料和学习风格，返回结构化讲解、可选引文、学习笔记和逐页生成的演示文稿。学习入口允许用户直接发起学习、恢复最近学习或按计算机方向探索，方向选择不是前置步骤；可验收行为见 [Learning Entry Spec](../specs/learning-entry.md)。当前 explain 路径接受最多 64 个字符的概念、问题或材料片段，由仓库内 `learning` 模块调用 Kernel Runtime 和可选 Provider，不依赖外部课堂平台；入口改版状态见 [学习入口页改版计划](../plans/learning-entry-redesign.md)。

Learning 的产品工作区提供探索方向、理解与讲解、理解检查、动手实践、复盘与知识缺口、笔记与学习画像。六种工作方式可以自由调用，不构成固定步骤。Topic 或其他 Focus 描述当前内容，Task 描述用户目标；两者不互相替代。规范路由和可验收行为见 [Learning–Practice Integration Spec](../specs/learning-practice-integration.md)。

该模块必须满足：

1. 可以独立进入，不强制跳转到练习或项目模块；
2. 在线和离线结果均明确标明实际来源；
3. 每次模型运行产生可关联的 Event；
4. 笔记读取按学习 `session_id` 隔离；
5. Provider 失败不得伪装为已有知识来源或执行成功。
6. 演示文稿必须显示规则、模型或降级来源；归档读取按学习 `session_id` 隔离，图片只接受受限的内联 PNG、JPEG 或 WebP 数据。
7. 用户显式保存的科研证据可作为研究笔记进入当前 Learning Notebook；研究笔记保留对应 Research Conversation、Evidence Bundle、论文来源和信息范围。
8. 学习入口页以六大领域提供稳定导航，领域下的方向胶囊支持多选和跨领域归属；选择结果只构成探索上下文，不写入学习状态，也不阻塞直接搜索。最近学习必须来自可恢复的持久化记录。

当前不引入 OpenMAIC，也不设计其适配器、前端承载或集成测试。

### 3.2 代码测试练习

围绕明确的编程任务提供代码编写、执行、测试和错误反馈。Practice 在产品中通过 Learning 的“动手实践”进入，在系统中继续作为独立 Capability。当前本地原型只支持固定的 Python 3.12 runtime，通过独立 Piston 服务执行代码；页面支持自由运行、服务端题目提交、公开与隐藏测试、规则分类、可选 AI 解释和匿名学习记录。

该模块必须满足：

1. 执行结果、测试判定、规则解释和模型建议分层返回；运行成功只代表当前输入正常结束，题目正确性只由服务端测试结果决定；
2. 结构化区分成功、答案错误、编译错误、运行错误、超时、输出超限和执行服务错误；
3. 语言、runtime 版本、源代码与输入大小、CPU、内存、墙钟时间和输出限制由服务端配置，浏览器不能扩大；
4. 隐藏测试不返回输入、期望输出、stdout 或 stderr；
5. AI 评价可以关闭或失败，不影响执行器结果、规则分类和测试判定；
6. 学习记录只保存匿名 `learner_id`、分类、摘要、代码哈希、代码字节数、运行指标和可选 AI 反馈，不保存原始代码或标准输入。

当前 Piston 容器使用 `privileged: true`；Compose 已显式配置网络、进程、文件、输出、并发和容器资源限制，但 live 隔离检查仍须在可用的 Docker 环境取得通过结果。学习记录使用浏览器生成的 UUID 和独立 SQLite，也不提供身份授权。该能力只计为本地原型，不计为生产代码执行服务。

Practice 接入编排层后，服务器先持久化不含源码、stdin 和隐藏测试的权威 PracticeOutcome，再幂等派生 WorkspaceActivity。Activity 表示结果存在，不表示代码正确。错误答案和用户代码错误形成可追溯知识缺口信号；请求校验失败和执行服务故障不归因于用户。

### 3.3 项目/科研助手

帮助用户澄清任务、形成结构化计划、检索可核验资料并组织下一步。当前主流程以自由对话逐步形成动态研究画像，持久化消息、画像和检索结果。画像达到计划准备度后，应用只根据已校验画像离线生成 `research-plan.v1`，所有条目标明建议或待核验；难点分析和实验方案默认使用规则结果，只有用户点击确认后才调用模型个性化并返回审计 run；代码草案由服务端固定模板生成，模型只能补充建议性元数据。达到检索条件后，先展示检索计划，再由用户显式触发 OpenAlex、Crossref 和 arXiv 元数据与摘要检索。

该模块必须满足：

1. 事实、规则结论、模型措辞和待核验项可以区分；
2. 外部检索结果包含注册工具返回的来源、检索范围和失败状态；
3. 主流程可以通过 `conversation_id` 恢复对话、规则研究计划与证据；
4. 项目、课程、多 Agent 和远程仓库流程在分别跑通前不计入现有能力。
5. Evidence 条目展示来源平台、标题、年份、原始链接、摘要与全文可用状态及规则相关性；使用 Evidence 的研究分析必须返回可核验的 Evidence 引用。

原五字段 `research_sessions` 流程仅作为兼容 API 保留，不再代表当前科研页面和产品主流程。

## 4. 跨模块规则

1. 用户可以从任一工作方式或 Capability 开始；系统可以建议下一步，但建议必须可跳过。
2. 跨模块上下文只传递当前目标所需内容，并标明来源模块，以及存在时的父 Task 或父 run。
3. 用户在传递前能够查看、修改或清除上下文。
4. 模块切换不自动继承工具权限、完整对话或长期记忆。
5. 浏览器内存状态和 `localStorage` 只是当前本地原型状态，不是身份、授权或跨设备会话。
6. Workspace 与 Task 只组织上下文，不替代需要用户确认的内容传递，也不继承模块权限。

Learning 可以从真实摘要笔记创建 `context-transfer.v1` Research 待确认上下文；服务端保存来源模块、来源对象、学习会话、目标模块、主题、摘要和用户选择内容。确认页支持刷新恢复、修改、删除补充内容和取消；只有用户点击确认后，服务端才使用页面最终数据创建科研会话，并在会话中保存 `context-provenance.v1` 来源及最终快照。Research 每轮需求澄清都从会话加载该快照，将其作为已确认学习背景，避免重复询问其中已经明确的信息；一般知识内容不会自动变成用户的研究问题、方法、数据或结论。确认过程不调用模型或继承工具权限。

Learning 内进入 Practice 时，编排层签发 `launchId`，在服务端绑定 Workspace、可选 Task、Focus、来源 Activity、`local_profile_id` 和 `profile_id / learner_id`。直接进入 `/learning/practice` 时，页面分别取得自由运行与题目提交所需的个人 Workspace launch。旧客户端不传 `launchId` 时保持执行能力，但不创建 WorkspaceActivity。URL 与轻量 `FlowPayload` 只恢复可清除的练习主题，持久编排关系以服务端 launch 为准。

Research → Learning 回程只在用户从已保存 Evidence Bundle 中选择论文并确认保存后发生。前端显式提交当前 Learning `session_id`，服务端验证 Conversation、Bundle 与论文归属后写入 `research_note`；重复保存同一选择不会创建重复记录。

## 5. 当前非目标

1. 复杂教师端、班级与完整 LMS；
2. 强制的学习、练习、项目使用顺序；
3. 绕过受控执行服务和服务端限制的代码执行，或默认启用联网、项目文件写入、仓库推送和发布；
4. 把 Event JSONL 当作完整会话数据库、身份系统或长期记忆；
5. 未经独立验证的多 Agent 编排、自动评分、自动发布或自动研究结论。
6. 用固定阶段、模块覆盖率或强制推荐驱动 Task 完成。

## 6. 变更规则

1. 修改全局产品入口、系统 Capability 边界、编排实体关系、强制使用顺序或非目标时，更新本文件并检查架构影响。
2. 页面、字段和控件变化只更新受影响模块，不自动升级为跨模块契约。
3. 易变的实现状态和交付顺序只写入 [roadmap.md](roadmap.md)。
