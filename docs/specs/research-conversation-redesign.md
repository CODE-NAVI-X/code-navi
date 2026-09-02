# 科研端对话式重建 —— 契约（R0 基线）

_状态：R0 契约骨架，作为科研端重建（#73–#77）的实现基线。来源为导师确认的《科研端对话式重建设计文档》；与旧契约 `hands-on-practice-research-guidance-interfaces.md` 冲突时，以本文件为准。_

## 1. 目标与边界

科研端重建为由科研 Agent「姜姜」主导的连续聊天体验：把学习衔接、方向探索、研究计划、文献检索、论文理解、复现准备和结果分析串成一条可恢复的对话。

**本轮不做**：拆多主页面/独立计划面板、自动执行代码或训练模型、自动下载论文全文、自动联网补造引用、论文写作/审稿/投稿/思维导图、用规则模板掩盖 DeepSeek 失败。

## 2. 四阶段状态机

顶部只保留不可点击的四阶段横向进度：`研究需求确定` → `研究计划生成` → `研究开展` → `研究结果分析`。

- 状态枚举（后端）：`research_need` / `research_plan` / `research_execution` / `research_analysis`。
- 顶部三态：已完成（高亮）/ 当前（中性）/ 未开始（弱化）；**无百分比、评分、箭头、可跳转入口**。
- 阶段推进：只由聊天自然语言确认触发。`可以` / `继续` / `就这样` 等明确答复可推进；含糊、犹豫或提出修改时，姜姜澄清或留在当前阶段，不提前点亮。
- 换方向：保留历史，回到 `research_need` 重建当前方案；仅追问旧内容不回退阶段。

## 3. 姜姜 persona 与对话规则

- 语气：活泼、亲切、专业；颜文字可用；**emoji 禁用**。
- 开场 / 阶段切换 / 完成用大字号区块；正文 ≥16px；长回复用 小标题 / 短段落 / 任务列表 / 时间安排。
- 阶段完成提示必须说清「完成的具体工作 + 依据 + 下一步」，禁用「核心判断」「当前聚焦于」等空标签。
- 可点击例外（仅两类）：进入后 5 个方向框；正式检索后候选论文卡片（一次只能一篇当前论文）。
- DeepSeek 调用时显示「姜姜正在思考……」；失败如实提示、允许重试、不推进阶段、不以模板冒充成功。

## 4. 学习端 → 科研端输入契约

时序与调用流程：
1. 学习端 producer 先取得或创建目标 research conversation（`POST /api/v1/research/conversations`）；
2. 学习端 producer 调用 `PUT /api/v1/research/conversations/{conversation_id}/orchestrator/learning-context` 写入最新学习上下文；
3. 前端再进入既有科研聊天入口；
4. 两字段均允许为空，空态请求返回 HTTP 200；
5. `learned_content` 只表示已学内容，不等同于已掌握所有相关知识；
6. `learning_progress` 只表示当前学习进度，不等同于研究结论或实验能力；
7. 两字段都不代表掌握度、研究结论或实验能力；
8. #84 负责学习页 producer 与页面跳转接线，R3 只保证科研端接收契约、空态容错与消费行为；
9. 学习输入快照消费内部语义：学习输入仅在 Provider 成功、输出通过校验且实际 Prompt 包含当前学习上下文/增量上下文时确认快照（`last_consumed_snapshot`）；历史查询、换方向、多工具意图澄清、被动工具回复或 Provider 失败均不会消费增量快照，确保后续正常科研对话能准确感知学习端输入更新。

| 字段 | 用途 | 不推断 |
| --- | --- | --- |
| `learned_content`（已学内容） | 欢迎语、动态 5 方向卡片、知识桥接 | 不等同于已掌握所有相关知识 |
| `learning_progress`（当前学习进度） | 判断先复习 / 延展 / 探索 | 不等同于研究结论或实验能力 |

方向框必须按实际输入动态生成（围绕提取的真实课题锚点组织复现基准、受限资源优化、特征鲁棒性、少样本弱监督、前沿变体迁移等），**严禁固定 CNN 清单**。无前置学习输入时返回空列表 `[]`（展示空态），不编造虚假卡片或假造学习事实。用户自定义方向跨度大时，姜姜说明前置知识缺口并给补学建议，但仍允许继续探索。


## 5. 八个 Prompt 模板

| 模板 | 输入 | 期望输出 | 禁止 |
| --- | --- | --- | --- |
| 欢迎与衔接 | 已学内容、学习进度、方向概览 | 欢迎语、能力介绍、5 方向框 | 把学习信息说成研究结论 |
| 需求澄清 | 方向选择、自由输入 | 具体研究问题与需求总结 | 模糊信息下推进阶段 |
| 画像与计划 | 多轮画像、设备、时间、目标 | 小目标与可执行总体计划 | 忽略设备限制或编造时间 |
| 检索引导 | 检索词、来源范围 | 关键词优化与确认问题 | 未确认即正式检索 |
| 论文介绍 | 已选论文、允许材料、画像 | 问题/创新/方法/难点/适配性 | 无来源公式或突兀技术片段 |
| 实验方案 | 论文、画像、总体计划 | 初步或具体方案 | 生成与用户条件矛盾的计划 |
| 结果分析 | 用户结果、指标、配置、现象 | 缺失项追问或具体分析 | 伪造实验或声称复现成功 |
| 阶段切换 | 当前已完成子任务 | 具体总结与下一步引导 | 空泛套话或装饰状态 |

共享约束：只用当前会话已确认上下文；信息缺失优先追问、不猜测；解释论文先建「研究问题 → 创新点 → 方法 → 与目标关系」桥梁；避免空标签与泛泛鼓励；允许用户提问无关内容后自然拉回当前任务。

## 6. §2 被动能力清单（保留为按需工具）

现有 §2 规则能力**全部保留，但降级为被动 / 按需**：用户主动提问时才触发，不自动进入主流程。

| 用户意图示例 | 触发工具 | 触发后行为 |
| --- | --- | --- |
| 我现在进展如何 / 总结一下 / 我们到哪了 | `stage-briefing` | 规则生成阶段总结，姜姜自然语言复述 |
| 我该先学什么 / 要补什么知识 / 学习建议 | `study-recommendations` | 规则生成清单，姜姜逐条介绍 |
| 这个方向难吗 / 难点在哪 / 有什么困难 | `topic-difficulty-analysis` | 四区 reducer 后按研究目标主轴叙述 |
| 帮我设计实验 / 实验方案怎么做 / 怎么跑 | `experiment-design` | 指标白名单校验，展示方案并说明 to_verify |
| 论文结构 / 大纲怎么写 / 五段 | `paper-blueprint` | 五段骨架，不写论文正文 |
| 评估一下我的复现 / 准备得怎么样 / 还差什么 | `reproduction-evaluations` | 六条 0/1/2，逐条依据与改进项 |

触发与编排规则：

- 关键词与意图识别由编排层确定性规则判定，模型不能自由选择工具。
- 每轮最多调用一个工具。
- 一轮同时命中多个工具意图时：不调用任何工具，先由姜姜澄清用户优先事项。
- 工具缺少输入、返回空态或前置条件不成立时：明确说明缺什么，禁止伪造不存在的工具结果。
- `study-recommendations` 仍遵守既有显式确认与 409 语义；不能绕过其 `user_confirmed` 约束。
- 工具输出只是姜姜回复的素材；回复使用自然语言说明来源、依据和不确定性，不堆叠密集徽标。
- 不修改被调用工具本身的规则算法、事实归类和输出边界。
- 保留红线：`fact / inference / to_verify`、`source_scope`、`evidence_linked ≠ 复现成功`、显式检索、模型失败显式回退。

## 7. 学习者画像与持久化

- 画像字段：相关领域熟悉度（`domain_familiarity`）、开发经验（`dev_experience`）、参与项目（`projects`）、设备与显存（`hardware`）、操作系统（`os`）、Python 环境（`python_env`）、每周可投入时间（`weekly_hours`）、年级（`grade`）、专业（`major`）；多轮对话形成；每次有效变更创建新版本。
- 持久化：对话消息、画像（版本化，当前版本与历史版本）、总体/具体计划（最新确认 = 当前，旧版留历史）、单一当前论文 + 用途（`replace` / `compare` / `cite`，仅 `replace` 更新当前论文）、阶段与子任务状态、换方向历史、学习端增量输入。

## 8. 联网、来源与引用

| 场景 | 自动联网 | 规则 |
| --- | --- | --- |
| 开场方向概览 | 可以 | 优先学术来源，标明来源与时间 |
| 正式检索 | 不可以 | 用户给检索词并确认后启动（OpenAlex / Crossref / arXiv） |
| 论文正文 | 不自动下载 | 仅公开内容或用户主动上传 PDF |
| 引用整理 | 不自动补造 | 仅据已提交/已保存/已选来源整理，被动触发 |

## 9. 验收场景

1. 从 Learning 进入 Research：姜姜引用已学内容与进度生成动态方向框。
2. 用户自定义方向：接受自由输入，跨度大提示前置知识但不阻止。
3. 用户确认需求：顶部仅完成第一阶段，进入多轮画像对话。
4. 设备不足：解释限制，提供租服务器或轻量替代。
5. 检索：先给检索词并确认，结果含真实来源与热点信息。
6. 选论文与方法：先精读式介绍再生成方案，公式规范（LaTeX）。
7. 用户结果不完整：追问缺失项，不声称成功。
8. 换方向 / 换论文：先澄清用途，旧内容留历史。
9. DeepSeek 失败：显示失败与重试，阶段不误推进。
10. 再次进入：自动恢复最近对话并吸收学习端新增内容。

## 10. R1 API 契约（编排与状态层）

所有端点挂载于既有 `/api/v1/research/conversations/{conversation_id}/orchestrator`，遵循现有鉴权、`owner_principal_id` 隔离与 404 隐藏边界。

### 10.1 `POST .../orchestrator/messages` — 会话编排消息交互

- **请求体** (`SendOrchestratorMessageRequest`)：
  ```json
  {
    "message": "string (1..8000 字符)"
  }
  ```
  *(注：schema 配置 `extra="forbid"`，禁止传递未审计字段)*
- **响应体** (`OrchestratorMessageResponse`)：
  ```json
  {
    "conversation_id": "string",
    "status": "completed | failed",
    "reply_message": {
      "id": "string",
      "sender": "assistant",
      "content": "string",
      "created_at": "iso8601",
      "passive_tool_called": "string | null"
    } | null,
    "state": {
      "current_stage": "research_need | research_plan | research_execution | research_analysis",
      "completed_stages": ["string"],
      "subtasks": {
        "need_defined": true,
        "profile_ready": false,
        "plan_generated": false,
        "paper_selected": false,
        "experiment_designed": false,
        "results_analyzed": false
      },
      "direction_history": [{"direction": "string", "timestamp": "iso8601"}],
      "last_status": "thinking | completed | failed",
      "last_error": "string | null"
    },
    "error": "string | null"
  }
  ```
- **编排顺序**：用户消息 → 确定性意图/确认词/换方向识别 → 至多一个 §2 被动工具 → 选择 Prompt 模板并组装已确认上下文 → DeepSeek 调用 → 校验、持久化回复 → 仅由规则决定的阶段与子任务更新。
- **错误与失败语义**：
  - 404：会话不存在或跨 owner；
  - 422：入参非法或携带未定义字段（所有写请求 schema 严格配置 `extra="forbid"`）；
  - 模型/Provider 调用失败、不可用、空回复或输出校验异常时：**统一返回 HTTP 200**，`status="failed"`，返回安全可读的 `error` 字段（`reply_message` 为 `null`）；此时严格不创建 assistant 成功消息、不推进阶段、不更新子任务/计划/论文/画像版本；用户可后续通过 `retry-last` 重试。

### 10.2 `POST .../orchestrator/messages/stream` — 思考生命周期 SSE 流式消息

- **响应头**：`Content-Type: text/event-stream`（客户端无需显式携带 `Accept: text/event-stream`）。
- **请求体**：同 10.1 请求体 (`SendOrchestratorMessageRequest`)。
- **流式生命周期事件顺序**：
  1. `event: thinking`：在调用模型生成前发出，并在数据库中持久化 `last_status="thinking"`：
     ```
     event: thinking
     data: {"status": "thinking", "stage": "research_need", "message": "姜姜正在思考..."}
     ```
  2. 终态事件（二选一）：
     - 成功完成时发出 `event: completed`：
       ```
       event: completed
       data: <OrchestratorMessageResponse JSON (status="completed")>
       ```
     - 失败/不可用/校验异常时发出 `event: failed`：
       ```
       event: failed
       data: <OrchestratorMessageResponse JSON (status="failed")>
       ```

### 10.3 `POST .../orchestrator/messages/retry-last` — 失败轮次重试

- **请求体**：无（无需请求体）。
- **前置条件与规则**：
  - 仅当会话上一轮处于 `last_status == "failed"` 且存在 `last_failed_user_message` 时允许重试；
  - 若上一轮非失败状态（如 `completed` 或正在 `thinking`），返回 `HTTP 409 Conflict`；
  - 复用失败轮次保存的原始用户输入与已确认上下文重新调用编排流程；
  - 重试成功前严禁推进阶段、更新子任务、修改计划或升级画像版本；
  - 重试成功后仅发生一次合法的状态更新。
- **响应体**：同 10.1 `OrchestratorMessageResponse`。

### 10.4 `GET .../orchestrator/state` — 状态机与子任务读取

- **响应体** (`OrchestratorStateResponse`)：
  ```json
  {
    "conversation_id": "string",
    "current_stage": "research_need | research_plan | research_execution | research_analysis",
    "completed_stages": ["string"],
    "subtasks": {
      "need_defined": "bool",
      "profile_ready": "bool",
      "plan_generated": "bool",
      "paper_selected": "bool",
      "experiment_designed": "bool",
      "results_analyzed": "bool"
    },
    "direction_history": [{"direction": "string", "timestamp": "iso8601"}],
    "last_status": "thinking | completed | failed",
    "last_error": "string | null"
  }
  ```

### 10.5 `GET .../orchestrator/direction-cards` — 动态方向卡片读取

- **处理**：根据已接收的 `learned_content` 与 `learning_progress` 动态生成 5 个方向卡片；无输入时诚实返回空数组 `[]`（禁止写死推荐）。
  ```json
  {
    "conversation_id": "string",
    "learned_content": "string | null",
    "learning_progress": "string | null",
    "cards": [
      {
        "id": "string",
        "title": "string",
        "description": "string",
        "prerequisite_gap": "string | null",
        "is_recommended": "bool"
      }
    ]
  }
  ```

### 10.6 论文管理与用途标记

- `GET .../orchestrator/papers` — 论文列表与历史读取
  - **响应体** (`OrchestratorPapersResponse`)：
    ```json
    {
      "conversation_id": "string",
      "current_paper": {
        "id": "string",
        "paper_url": "string",
        "title": "string",
        "purpose": "replace",
        "selected_at": "iso8601"
      } | null,
      "paper_history": [
        {
          "id": "string",
          "paper_url": "string",
          "title": "string",
          "purpose": "replace | compare | cite",
          "is_current": "bool",
          "selected_at": "iso8601"
        }
      ]
    }
    ```
- `POST .../orchestrator/papers/select` — 论文选择与用途标记
  - **请求体** (`SelectPaperRequest`，配置 `extra="forbid"`)：
    ```json
    {
      "paper_url": "string",
      "title": "string",
      "purpose": "replace | compare | cite",
      "metadata": {}
    }
    ```
  - **规则**：仅 `replace` 更新 `current_paper`；`compare` 与 `cite` 保留历史记录但不覆盖 `current_paper`。

### 10.7 `GET/PUT .../orchestrator/learner-profiles` — 学习者画像版本化

- `GET .../orchestrator/learner-profiles` 响应：
  ```json
  {
    "current_profile": {
      "version": 1,
      "domain_familiarity": "string | null",
      "dev_experience": "string | null",
      "projects": "string | null",
      "hardware": "string | null",
      "os": "string | null",
      "python_env": "string | null",
      "weekly_hours": "string | null",
      "grade": "string | null",
      "major": "string | null",
      "updated_at": "iso8601"
    } | null,
    "history": [
      {
        "version": 1,
        "profile_data": {},
        "change_summary": "string | null",
        "created_at": "iso8601"
      }
    ]
  }
  ```
- `PUT .../orchestrator/learner-profiles` 请求 (`LearnerProfileUpdateRequest`，配置 `extra="forbid"`)：传入需要更新的画像字段，若有实际有效变更则新增 version。

### 10.8 `GET/PUT .../orchestrator/learning-context` — 学习端输入接收与空态

- `PUT .../orchestrator/learning-context` 请求 (`LearningContextInput`，配置 `extra="forbid"`)：
  ```json
  {
    "learned_content": "string | null",
    "learning_progress": "string | null"
  }
  ```
- `GET .../orchestrator/learning-context` 响应 (`LearningContextState`)：
  ```json
  {
    "conversation_id": "string",
    "learned_content": "string | null",
    "learning_progress": "string | null",
    "updated_at": "iso8601 | null"
  }
  ```
- **规则**：两字段均可空；无数据或空态请求返回 HTTP 200 且不编造学习记录；两字段均可写入与读取；方向卡片读取学习上下文时能读到这两个字段。
