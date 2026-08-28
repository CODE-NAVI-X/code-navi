# 板块合并与全局导航顶端设计

状态：设计提案 v2（已对照代码自评审修订，未实施）。本文回答四个问题：两套画像是否合并、两条练习生成链路是否合并、科研模块需要哪些共用接口、前端入口如何重组，并给出迁移切片。动手实践与科研引导的编码级契约见 [动手实践与科研引导接口设计](../specs/hands-on-practice-research-guidance-interfaces.md)。v2 修订依据见文末"评审记录"。

## 1. 输入与固定约束

1. 全局主流程固定为六步线性闭环：理解 → 检查 → 动手实践 → 复盘 → 笔记 → 科研引导。
2. 评审意见（王晶晶）：动手实践抛弃基础语法选择题、GitHub 双栏、分层步骤、AI 生成完整可运行代码裁剪挖空、轻量代码 LLM 静态判题、上传仅限 .py/.md；科研引导按标准学术结构（摘要/介绍/综述/方法/实验）重构、聚焦研究目标与动机、实验指标标准化并标注公开数据源、蓝图置底、复现评估展示 6 条确切评分依据；全局 UI 板块化卡片、字体放大、对比度提高。
3. 团队矩阵：苏育（动手实践/前端交互）、陈盛漳（科研辅助/论文生成）、夏俊杰（学习端链路）、梓柯（架构/接口/全局 UI）。
4. 产品不变量不因合并放松：模块事实来源不互相接管、跨模块上下文用户可查看修改清除、建议可跳过、模型输出不得冒充执行结果。

## 2. 现状事实（代码证据）

| 事实 | 位置 |
| --- | --- |
| 概念题组卷：LLM 生成 single/fill_blank/short_answer，归档后 `/quiz/grade` 服务端评分，落 `quiz_attempts` 进画像 | `src/code_navi/learning/quiz/services.py`、`learning/quiz/schemas.py`；端点 `POST /api/v1/learning/quiz/generate` |
| 代码题集组卷：规则组装内置题目录 + 用户上传题 + 占位生成题，经 `/compiler/submit` 由服务端隐藏测试判定，落 PracticeOutcome | `src/code_navi/online_compiler/problem_sets.py`；端点 `POST /api/v1/compiler/problem-sets/generate` |
| 学情画像：按匿名 `profile_id` 跨会话聚合 `quiz_attempts` + `confusion_marks`；知识缺口为三源只读投影（+PracticeOutcome） | `src/code_navi/learning_profile/`；`GET /api/v1/profile`、`GET /api/v1/learning/knowledge-gaps` |
| 科研画像：`research_conversations.profile`（主题/动机/问题/方法/数据需求等 12 字段），随对话 reducer 更新，作用域是单个科研会话 | `src/code_navi/research/conversation_schemas.py:30` |
| 科研端点 51 个（`@router` 装饰计数），温故知新/实验方案/代码草案/论文蓝图/复现评估等已存在 | `src/code_navi/research/router.py` |
| 论文蓝图现状为**六段**中文枚举（引言/相关工作/方法/实验/讨论/结论），按需生成、**不落库** | `conversation_schemas.py:733`、`conversation_paper_blueprint.py:45` |
| 复现评估现状为**五维**（research_definition 等）× 每维 20 分 = 总分 100，`schema_version=reproduction-project-evaluation.v1`，**已落库**（`evaluation_data` JSON） | `reproduction_evaluation_schemas.py:12`、`models.py:149` |
| 温故知新现状分区：研究问题/方法难点/数据与实验难点/复现风险/资源需求（+关联计划项）；"对象与场景"是画像面板对 `profile.context` 的前端标签，不是分析分区 | `conversation_difficulty.py:29`、`frontend/components/research/ResearchProfilePanel.tsx:92` |
| 已有上传解析端点 `/api/v1/compiler/problem-imports/analyze`（解析**题目录入文本**为编程题），与拟新增的代码结构解析语义不同 | `online_compiler/problem_imports.py` |
| `/learning/explore` 与 `/learning` 渲染同一组件；`/learning` 页内右上快捷链接（动手实践/学习笔记）与六步 tab 栏重复，tab 栏含"探索方向"但**无科研引导步**；`/practice` redirect → `/learning/practice` | `frontend/app/(student)/learning/explore/page.tsx`、`learning/page.tsx:980-1044`、`frontend/next.config.ts` redirects |
| 组件位置颠倒：`/learning/practice/page.tsx` 只是 re-export，规范组件实际在 `(student)/practice/page.tsx`（1882 行） | `frontend/app/(student)/learning/practice/page.tsx:1`、`practice/page.tsx` |
| 工作台族路由：`/`、`/workspaces/[workspaceId]`、`/tasks/[taskId]` 存在；`/workspaces` redirect → `/` | `frontend/app/(student)/`、`next.config.ts` |
| `/research` 为单长页 10+ 面板，锚点式工作流导航 | `frontend/components/research/ResearchConversation.tsx`、`ResearchWorkflowNav.tsx` |
| 跨模块交接已有：FlowPayload（Learning→Practice 轻量主题：masteredKnowledgePoint + exerciseIds）、`context-transfer.v1`（Learning→Research 确认制，落 `research_conversations.context_provenance`） | `frontend/lib/store/flow-store.ts`、`src/code_navi/context_transfer/`、`research/models.py:36` |
| `QuizGenerateRequest.knowledge_point` 为必填（无上下文时概念组卷必须有主题输入） | `learning/quiz/schemas.py:125` |

## 3. 设计决策

### D1 学情画像与科研画像：不合并实体，统一读口

两套画像回答不同问题、基数与隔离键都不同：

- 学情画像是**个人级、跨会话聚合的掌握度事实**（数值 mastery、混淆标记），键为 `profile_id`；
- 科研画像是**单个研究项目、会话内演化的项目上下文**（主题/动机/方法），键为 `conversation_id`。

合并实体会把人级事实与项目级事实混进一张表，违反"KnowledgeGap 是只读投影，不建立第二套事实表"的既有原则，也让画像的会话隔离失去意义。**合并的正确层次是读取层，不是存储层**：

1. 新增统一画像读口 `GET /api/v1/portraits/overview`（只读聚合投影）：一次返回 learning 块（掌握度摘要 + 知识缺口）、research 块（各科研会话画像摘要 + 准备度）、bridges 块（双向信号），前端画像中枢一次调用渲染，不再自行拼两个接口。
2. 双向信号（只投影、不接管事实）：
   - Learning → Research：`context-transfer` 确认时可选携带 `learning_mastery_snapshot`（强/弱知识点 TopN，服务端规则从画像生成，非模型编造）；科研"温故知新"读该快照输出能力边界提示。
   - Research → Learning：科研画像的方法/数据需求规则提取"科研所需知识点"，经 `study-recommendations` 返回并可一键带参跳转理解/检查。

### D2 练习生成：合并生成入口，保留两套判题

"生成练习集"（practice 页，代码题）与"配套练习题"（learning 页，概念题）当前是两条独立链路。**判题与事实源不能合并**：概念题由服务端规则/LLM 评分落 `quiz_attempts`，代码题由服务端隐藏测试判定落 PracticeOutcome——这是画像归因的基础。**合并点在"生成入口"**：

1. 新网关 `POST /api/v1/practice/sets/generate`，`kind = concept_quiz | code_practice | mixed`，内部委托现有 QuizGenerator、problem-set 组装器与新增的 code_fill 生成器；无学习上下文时以 `topic`（自由主题，兼容现状 practice 页 prompt 组卷与 quiz 必填 `knowledge_point`）驱动；响应统一为 PracticeItem envelope（`item_kind` 决定该题走哪条判题通道）。
2. 新增 `code_fill` 题型：AI 先生成完整可运行代码，再裁剪核心逻辑为 2~6 个挖空，附分层步骤（Step 与子步骤）及排序/架构原因；轻量代码 LLM 静态判题、大型项目仅解析讲解不执行。
3. **判题不新增第三条通道**：mixed 集中的概念题在归档时同步写入既有 quiz 归档（`session_id = set_id`，`item_id` 即 quiz 题 id），判题继续走 `POST /learning/quiz/grade` 不改；代码题仍走 `/compiler/submit`；挖空题走新 `/practice/code-fill/grade`。三条通道各自的事实源（quiz_attempts / PracticeOutcome / code_fill_attempts）不变，画像归因不混表。
4. 动手实践页默认 `kind=code_practice`，基础语法选择题退出动手实践（保留在"检查"步的概念题中）；一次生成 3~8 题（评审要求）。
5. 旧端点 `/learning/quiz/generate` 与 `/compiler/problem-sets/generate` 保留兼容，前端迁移完成后降级为网关内部实现细节。上传解析同样双轨：`/compiler/problem-imports/analyze`（题目录入）保留，新增 `/practice/code-uploads/analyze`（自有代码结构解析），二者共享大小/类型校验工具但语义不合并。

### D3 科研模块共用接口（画像联动）

在现有 51 个科研端点之上新增 3 个共用接口（契约见接口设计文档 §2 与 §4）：

| 端点 | 用途 | 联动方向 |
| --- | --- | --- |
| `GET /api/v1/portraits/overview` | 统一画像读口 | 前端一处渲染两套画像 + 桥接信号 |
| `GET /api/v1/research/conversations/{id}/stage-briefing` | 科研首屏阶段总结：已确认学习背景摘要 + 掌握快照 + 论文复现路径入口 + 基于已存证据的方向推荐（规则生成，不联网） | 笔记 → 科研引导过渡（六步第 5→6 步） |
| `POST /api/v1/research/conversations/{id}/study-recommendations` | "为科研而学"知识点清单，带跳转 payload | Research → Learning |

另有 4 项科研 v2 schema 变更（温故知新聚焦研究目标/动机、实验方案 task_type+标准指标目录+数据源 URL、论文蓝图五段标准结构、复现评估 6 条评分依据），见接口设计文档 §2.3–§2.6。其中**论文蓝图是唯一允许的非 additive 变更**（按需生成不落库、前端同片切换，理由见接口文档 §2.5）；**复现评估已落库**，必须以 `schema_version=v2` 的 payload 版本化共存，禁止原地改写历史 v1 评估。

### D4 前端导航：左侧边栏 + 六步进度条

现状问题：入口是顶部 4 个平铺按钮，无区内导航；learning 页快捷链接与 tab 栏重复；explore 是同页复制品；六步闭环在界面上不可见。

目标信息架构（功能优先，桌面侧边栏 / 移动抽屉）：

```text
Code Navi
├── 工作台                    /                    （含 /workspaces/[id]、/tasks/[id] 详情页，工作台域内二级页面）
├── 学习闭环
│   ├── 理解与检查            /learning            （含探索方向区块与理解检查视图）
│   ├── 动手实践              /learning/practice
│   ├── 复盘                  /learning/portrait   （学情画像 + 实操复盘）
│   └── 笔记                  /learning/notebook
├── 科研引导                  /research            （含 /research/confirm/[contextId] 确认页）
├── 班级                      /classes
└── 账户                      /account
```

`/tasks/[taskId]`、`/workspaces/[workspaceId]` 不进侧边栏一级入口：它们是工作台域内的详情页，由工作台卡片进入，页内以面包屑（工作台 → 任务详情）回溯；`/research/confirm/[contextId]` 同理属于科研域确认流。侧边栏只承载六个一级入口，避免重演"顶部 4 按钮 + 页内重复链接"的混乱。

1. 每个学习子页顶部渲染 `LearningFlowStepper`（理解 → 检查 → 动手实践 → 复盘 → 笔记 → 科研引导）：当前步高亮、其余可点；它是导航辅助，不强制顺序、可跳过（符合 scope.md 跨模块规则）。现状 tab 栏缺"科研引导"步、且把"探索方向"列为平级 tab，v2 一并收敛。
2. 删除 `/learning/explore` 独立路由（redirect 到 `/learning`），探索方向保留为理解页首屏区块；`/learning/practice`、`/learning/portrait`、`/learning/notebook` 为规范路由，旧路径 redirect 保持；同时把 1882 行的规范组件从 `(student)/practice/page.tsx` 迁至 `(student)/learning/practice/page.tsx`（现状是反向 re-export，位置与路由语义颠倒），旧目录留一行 re-export 过渡一个版本。
3. `/learning` 页右上四个快捷链接并入侧边栏与 stepper，消除重复入口。
4. `/research` 页保留锚点工作流导航，但首屏顶部新增阶段简报卡片（D3 的 stage-briefing），实现"笔记 → 科研引导"的衔接。
5. UI 规范（梓柯）：全站内容区默认 `text-base` 起步、阅读区 `text-lg`；统一 `app-card` 卡片化；`globals.css` 明度/对比度 token 校准；禁止对话流黑盒输出，复盘与科研结果一律图表 + 结构化卡片渲染。

## 4. 目标接口拓扑总表

| 方法与路径 | 状态 | 模块 | 说明 |
| --- | --- | --- | --- |
| `POST /api/v1/practice/sets/generate` | 新增 | 动手实践 | 统一生成网关（concept_quiz/code_practice/mixed；`topic` 或 `context` 至少一项） |
| `GET /api/v1/practice/sets/{set_id}` | 新增 | 动手实践 | 恢复归档练习集（剥离判题依据） |
| `POST /api/v1/practice/code-fill/grade` | 新增 | 动手实践 | 挖空静态判题（规则 + LLM），落 `code_fill_attempts` |
| `POST /api/v1/practice/code-fill/explain-symbol` | 新增 | 动手实践 | 悬停符号 AI 解析（缓存、限频） |
| `POST /api/v1/practice/code-uploads/analyze` | 新增 | 动手实践 | .py/.md 上传解析（≤256KB，剥离数据集）；与既有 `/compiler/problem-imports/analyze`（题目录入）语义分离 |
| `POST /api/v1/learning/quiz/grade` | 行为扩展 | Learning | mixed 集概念题以 `session_id=set_id` 归档后走本端点判题，接口签名不变 |
| `GET /api/v1/portraits/overview` | 新增 | 画像网关 | 学情 + 科研画像统一只读投影（契约：接口文档 §4） |
| `GET /api/v1/research/conversations/{id}/stage-briefing` | 新增 | 科研引导 | 首屏阶段总结（规则） |
| `POST /api/v1/research/conversations/{id}/study-recommendations` | 新增 | 科研引导 | 为科研而学清单（规则，显式触发） |
| `POST .../topic-difficulty-analysis` | 变更 v2 | 科研引导 | 四分区聚焦研究目标/动机；移除"对象与场景"驱动 |
| `POST .../experiment-design` | 变更 v2 | 科研引导 | task_type + 标准指标目录 + 数据源 URL |
| `POST .../paper-blueprint` | 变更 v2 | 科研引导 | 五段标准学术结构（唯一非 additive 变更，见 §2.5） |
| `POST .../reproduction-evaluations` | 变更 v2 | 科研引导 | 6 条评分依据（总分 12）；payload 版本化 v2 与历史 v1 共存 |
| `GET /api/v1/learning/knowledge-gaps` | 变更 | Learning | 新增 `code_fill_attempt` 缺口来源（仅 `graded=true`） |
| `/learning/quiz/generate`、`/compiler/problem-sets/generate` | 保留兼容 | — | 迁移后成为网关内部实现 |

## 5. 迁移切片与验收

| 切片 | 负责 | 内容 | 验收 |
| --- | --- | --- | --- |
| S1 接口契约与存储 | 梓柯 | Alembic `practice_sets`/`practice_set_items`/`code_fill_attempts`（含 `owner_principal_id`）；`src/code_navi/practice/` 新 router 注册进 `server.py` + Pydantic schema + 契约测试 | 空库与旧库迁移通过；`/practice/sets/generate` mock 模式闭环 |
| S2 动手实践改造 | 苏育 | code_fill 生成 prompt（完整代码→裁剪挖空→分层步骤）；双栏 GitHub UI（左目录树/结构列表、右代码与挖空、悬停浮窗）；长代码全屏/收起；.py/.md 上传解析 | 3~8 题强绑定知识点；判题离线降级诚实标注；上传拒绝数据集 |
| S3 科研引导改造 | 陈盛漳 | §2.3–§2.6 四项 v2 schema + prompt 重构 + 标准指标目录常量表；蓝图面板置底、6 条评分结构化展示；复现评估 payload 以 `schema_version=v2` 落库、v1 历史只读保留 | 指标必命中目录或标 `to_verify`；蓝图五段顺序输出；v1 评估在新前端仍可打开 |
| S4 上下文协议 | 夏俊杰 | `practice-context.v1` payload（理解→动手实践）；`context-transfer` 确认可选携带 `learning_mastery_snapshot`；stage-briefing/study-recommendations 接线与笔记→科研入口 | 传递前用户可查看修改清除；无确认上下文时首屏显示空态不报错 |
| S5 导航与全局 UI | 梓柯 + 苏育 | 侧边栏、LearningFlowStepper、路由收敛（含 practice 组件归位）、字号/卡片/对比度规范 | 旧 URL redirect 全部可达；`npm run lint`、`npm run build` 通过 |

## 6. 风险与限制

1. LLM 静态判题的诚信边界：所有判分必须带 `graded_by`/`is_mock`/`graded` 标注，离线降级提示自查，不得伪称模型结论；code_fill 不做容器执行。
2. 兼容期双端点并存（旧组卷端点与网关），前端迁移完成前不得删除旧端点；科研 v2 变更一律 additive，**唯一非 additive 例外是论文蓝图**（不落库、前端同片切换）；复现评估因已落库，不用"字段投影"而用 payload `schema_version=v2` 共存（v1 历史只读，禁止原地改写与数值换算）。
3. 教师端业务继续全面暂缓，仅保留身份底座；本设计不触碰班级/角色功能。
4. 方向推荐只允许引用当前会话已保存 Evidence 声明"使用了元数据或摘要范围"（scope.md 既有不变量），不新增联网能力。
5. mixed 集双写（practice_set_items + quiz 归档 `session_id=set_id`）需在同一事务内完成，否则会出现"能看题不能判题"的半归档态；契约测试须覆盖双写原子性。

## 7. 评审记录（v2 自评审，2026-01）

对 v1 设计逐条对照代码后确认了主体方向（画像不并表只并读口、生成并口判题分口、三条科研共用接口、侧边栏 + 六步 stepper 均成立），修正与补强如下：

| # | 发现（代码证据） | 处置 |
| --- | --- | --- |
| F1 | 科研端点实际 51 个而非"约 38"（`router.py` 装饰器计数） | 事实表更正 |
| F2 | 论文蓝图现状为**六段**中文枚举（引言/相关工作/方法/实验/讨论/结论），v1 文档称"替换现有四段"且未提"讨论/结论"的去向 | 更正现状；v2 明确五段枚举并规定讨论/结论内容并入"实验/方法"段，作为唯一非 additive 变更并给出理由（不落库） |
| F3 | 复现评估已落库（`research_reproduction_evaluations.evaluation_data`），五维×20=100；v1 文档"旧五维响应由新结果投影保留"会把 100 分制与 12 分制混写 | 改为 payload `schema_version=v2` 共存：v1 历史只读保留、不做数值换算，前端两种版本都可渲染 |
| F4 | v1 文档称温故知新"移除对象与场景（原 context 区）"，实际"对象与场景"只是画像面板字段标签（`ResearchProfilePanel.tsx:92`），温故知新现状分区是研究问题/方法难点/数据与实验难点/复现风险/资源需求 | 更正事实表述；v2 变更同时覆盖 prompt 分区与画像面板 UI（砍"对象与场景"字段展示） |
| F5 | mixed 集中概念题的判题路径 v1 未定义：`/learning/quiz/grade` 按 `session_id` 读归档，答案若只存 `practice_set_items.judge_secret` 则无法判题，新开判题端点又会造成第三条通道 | 规定概念题归档时同步写 quiz 归档（`session_id=set_id`、`item_id`=quiz 题 id），判题接口零改动，双写同事务（风险 5） |
| F6 | 网关请求缺主题输入：`QuizGenerateRequest.knowledge_point` 必填，无 `practice-context.v1` 时 concept_quiz 无法生成；practice 页现状靠自由 prompt 组卷 | 请求体增加 `topic`（自由主题），`context`/`topic`/`upload_ids` 至少一项否则 422 |
| F7 | 前端存在 `/tasks/[id]`、`/workspaces/[id]` 路由，v1 目标 IA 未提及；且 `/learning/practice/page.tsx` 只是反向 re-export，规范组件实际在 `(student)/practice/` | IA 补充"工作台域二级页面不进侧边栏"规则；S5 增加组件归位任务 |
| F8 | 已有 `/compiler/problem-imports/analyze`（题目录入解析），与新增 `/practice/code-uploads/analyze`（自有代码结构解析）易混淆 | D2 明确双轨语义分离、共享校验工具不合并端点 |
