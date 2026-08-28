# 板块合并与导航重构实施计划（P0–P3）

状态：实施计划（随 [板块合并与全局导航顶端设计](module-consolidation-and-navigation-redesign.md) v2 与 [动手实践与科研引导接口设计](../specs/hands-on-practice-research-guidance-interfaces.md) v2 一并生效）。本文定义阶段划分、并行轨道、进入/退出条件与 PR 门禁；接口入参/出参/错误码一律以契约文档为准，本文不重复。

## 1. 阶段总览与依赖关系

| 阶段 | 时间盒 | 并行轨道 | 出口条件 |
| --- | --- | --- | --- |
| P0 契约地基 | 第 1 周 | A 梓柯 S1 后端地基；B 陈盛漳 §2 科研 v2 后端；C 苏育 §1 前端骨架（mock 驱动） | 契约测试全绿；科研 v2 可落库；双栏 UI 可脱机演示 |
| P1 板块升级接线 | 第 2–3 周 | A 苏育 §1 后端接线与判题；B 夏俊杰 §3 上下文协议 | 动手实践端到端闭环（生成→作答→判分→画像）；笔记→科研过渡可见 |
| P2 画像统一读口 | 第 4 周前半 | 梓柯 D3（portraits/overview + knowledge-gaps 扩展） | 复盘页一次调用渲染两套画像；缺口含 code_fill 来源 |
| P3 导航与全局 UI | 第 4–5 周 | 梓柯 + 苏育 D4（侧边栏、stepper、路由收敛、字号/卡片） | 六步闭环 UI 可见；旧 URL 全部 redirect；lint/build 通过 |

**为什么 P0 不是"只有 §1/§2"**：苏育 §1 的后端（`/api/v1/practice/sets/generate`、code_fill 归档与判题）依赖梓柯 S1 的三张表与网关骨架，没有地基他只能做空转实现。因此 P0 采用**三轨并行**：

1. 梓柯先落 S1（迁移 + router 骨架 + Pydantic schema + **契约测试**），这是全局冻结点——合入后 schema 漂移即 CI 红；
2. 陈盛漳的 §2 全在现有 research router 内，无外部依赖，P0 第一天开工；
3. 苏育不等后端：以契约文档 §1.1/1.2 的响应结构为 mock 数据源先做双栏 UI、上传交互与浮窗，S1 合入后换真接口（契约测试保证形状一致，前端改动接近零）。

**为什么梓柯的 D3/D4 排在 P2/P3**：D3 的 stage-briefing/study-recommendations 挂 research router，与陈盛漳 P0 大改同文件，排后避免长期 rebase；D4 横切所有页面，必须在各板块页面稳定后最后做，否则侧边栏/stepper 要返工多次。

## 2. 轨道明细

每条轨道列任务、验收与契约边界。验收标准与总案 §5 切片一致，此处按人拆分。

### P0-A 梓柯：S1 契约地基（阻塞苏育后端）

- 任务：Alembic `0022`（`practice_sets`/`practice_set_items`/`code_fill_attempts`，含 `owner_principal_id`）；`src/code_navi/practice/` 新目录 + router 注册进 `server.py`；契约文档 §1.1 全部 Pydantic schema；`/api/v1/practice/sets/generate` mock 模式闭环（不接真模型）；契约测试（请求/响应形状、错误码 422/409/404、出参剥离 `judge_secret` 与 `blanks[].answer`）。
- 验收：空库与旧库 `alembic upgrade head` 通过；`tests/` 契约测试绿；mock 生成 → GET 恢复归档闭环。
- 契约边界：本轨**只做骨架不做业务**——不接真 Provider、不写 code_fill prompt；mock 响应的形状必须与 §1.2 出参逐字段一致（这是苏育前端 mock 的唯一依据）。

### P0-B 陈盛漳：§2 科研引导 v2（含共用端点）

- 任务：§2.1 stage-briefing 与 §2.2 study-recommendations 两个新端点（纯规则）；§2.3 温故知新四分区（`area_code` additive）+ prompt 重构；§2.4 实验方案 `metrics_catalog.py` + task_type + DatasetRef；§2.5 蓝图五段枚举（唯一非 additive，前端同 PR 切换）；§2.6 复现评估 payload `schema_version=v2` 共存；§2.7 prompt 总约束与 reducer 规则。
- 验收：指标必命中目录或标 `to_verify`；蓝图五段顺序输出且无"对象与场景"设问；v1 历史评估在新代码路径下原样可读（不做数值换算）；`provenance_note` 齐全。
- 契约边界：不新增契约外的科研端点；prompt/文案自由迭代，但 §2.3–2.6 的字段名、枚举值、错误码（409 准备度语义）不得漂移。

### P0-C 苏育：§1 前端骨架（mock 驱动，不依赖后端）

- 任务：GitHub 风格双栏（左目录树/类方法结构列表、右代码与挖空区、点击定位）；分层步骤条（Step/子步骤 + 排序原因展示）；长代码全屏/收起左栏；.py/.md 上传交互（前端校验后缀与 256KB）；悬停浮窗（P0 用 docstring/签名规则模板，浮窗真模型解析随 P1-A）。
- 验收：以契约 §1.2 mock 响应驱动全流程可演示；无网络请求时 UI 不白屏不报错。
- 契约边界：mock 数据必须从契约文档手工构造（或复用梓柯契约测试的 fixture），禁止"先跑通后对齐"。

### P1-A 苏育：§1 后端接线与判题

- 任务：`CODE_FILL_SYSTEM_PROMPT`（完整代码→自测→裁剪挖空→分层步骤）+ audit 重试；§1.4 静态判题（规则预判 + LLM 静态评审 + 离线降级）；§1.6 explain-symbol（缓存 + 限频 + 规则回退）；mixed 归档双写 quiz 归档（同事务，总案风险 5）；前端切真接口。
- 验收：3~8 题强绑定知识点；`graded_by/is_mock/graded` 事实字段齐全；离线提示自查不伪称模型结论；上传拒绝数据集痕迹；判分落 `code_fill_attempts` 进画像。
- 契约边界：判题通道归属不可变（concept→quiz grade、coding→compiler submit、code_fill→新端点）；复杂度 `heavy/explain_only` 判定在服务端，前端不得改。

### P1-B 夏俊杰：§3 学习端上下文协议

- 任务：`practice-context.v1` 前端构造与确认 UI（可查看/修改/清除）；flow-store 内容升级；`context-transfer` confirm 的 `include_mastery_snapshot` 开关；stage-briefing/study-recommendations 前端接线；笔记页"带总结进入科研引导"入口。
- 验收：跳转实践自动跳过基础引导与语法测试（总案输入约束 2）；无确认上下文时科研首屏空态不报错；快照由服务端生成，客户端无自填数值路径。
- 契约边界：URL 只带轻量指针，正文经 `context` 字段提交；快照内容不可被前端覆写。

### P2-A 梓柯：D3 画像统一读口

- 任务：`GET /api/v1/portraits/overview`（契约 §4.1，learning/research/bridges 三块委托聚合）；`knowledge-gaps` 新增 `code_fill_attempt` 来源（§4.2）；复盘页改为一次调用渲染。
- 验收：新用户零数据返回 200 空态；登录态 owner 过滤正确；复盘页请求次数从 2 降为 1。
- 前置：P0-B 已合入（research router 稳定），开工前 rebase main。

### P3-A 梓柯 + 苏育：D4 导航与全局 UI

- 任务：桌面侧边栏/移动抽屉（六入口，工作台域二级页面不进侧边栏）；`LearningFlowStepper` 六步（含科研引导步）；`/learning/explore` 收敛为理解页区块；practice 组件归位（`learning/practice` 为规范位置，旧路径留 re-export 一版）；右上快捷链接并入侧边栏；字号 `text-base/text-lg`、`app-card`、对比度 token 校准。
- 验收：旧 URL（`/practice`、`/portrait`、`/student/*`、`/learning/explore`）redirect 全部可达；`npm run lint`、`npm run build` 通过；科研首屏含 stage-briefing 简报卡片。
- 契约边界：纯前端阶段，不触碰后端端点。

## 3. PR 门禁（治理规则）

为防止"各自板块功能升级"绕开契约，所有相关 PR 遵守：

1. **契约先行**：触碰契约文档所列端点/字段/枚举/错误码的 PR，必须同时携带 `docs/specs/hands-on-practice-research-guidance-interfaces.md` 的 diff（同一 PR 内先文档后代码或同 commit）。出现契约外新端点且无文档变更的，评审直接打回。
2. **板块内自由区**（无需改契约）：payload 内部 additive 字段、prompt 文案迭代、UI 布局、内部函数重构。**红线**（必须先改文档）：端点路径与方法的增删、判题通道归属、事实源落表、错误码语义、出参剥离规则。
3. **契约测试守卫**：P0-A 引入的契约测试进入 CI 必跑集；schema 漂移即红，修红的方式要么改代码要么先提文档变更 PR。
4. **验证清单**（沿用 workflow.md §7）：每 PR 附 mock 与真实 Provider 各一轮的验证说明；涉及迁移的附空库+旧库升级验证。
5. **分支与提交**：`<type>/<short-topic>` + Conventional Commits，一次提交一个可回退问题；禁止把文档变更混入无关功能 PR。

## 4. 里程碑与 Issue 映射

| Issue | 阶段/轨道 | 负责人 | 对应契约 |
| --- | --- | --- | --- |
| S1 契约地基 | P0-A | 梓柯 | 契约 §0/§1.1/§1.2(mock)/§1.3 |
| 科研引导 v2 | P0-B | 陈盛漳 | 契约 §2 全部 |
| 实践前端骨架 | P0-C | 苏育 | 契约 §1.1/1.2 出参形状 |
| 实践后端接线 | P1-A | 苏育 | 契约 §1.2/1.4/1.5/1.6/1.7 |
| 上下文协议 | P1-B | 夏俊杰 | 契约 §3 + 总案 D1 快照 |
| 画像统一读口 | P2-A | 梓柯 | 契约 §4.1/4.2 |
| 导航与全局 UI | P3-A | 梓柯+苏育 | 总案 D4 |

## 5. 风险缓冲与降级顺序

1. 时间盒超支时按以下顺序降级，均不影响契约形状：① explain-symbol 浮窗退化为纯规则模板（docstring+签名）；② portraits/overview 的 `bridges` 块返回空对象，前端隐藏桥接卡片；③ 温故知新 `capability_note` 仅在快照存在时输出（本就是可选）；④ D4 的移动端抽屉延后，桌面侧边栏先行。
2. research router 冲突：P2-A 开工前必须 rebase；stage-briefing 若与 P0-B 同期完成可提前至 P1 末。
3. 苏育 mock 与真接口形状不一致：以契约测试 fixture 为唯一 mock 来源，发现不一致=契约或实现有一方错，先修错再继续。
4. 复现评估 v1/v2 双渲染复杂：前端渲染器按 `schema_version` 分发，v1 只读不编辑；不追求统一 UI。
