# 动手实践与科研引导接口设计 v2

状态：设计契约 v2（已对照代码自评审修订，编码前评审用）。苏育按 §1 实现动手实践，陈盛漳按 §2 实现科研引导，夏俊杰按 §3 实现学习端上下文协议，梓柯按 §4 实现画像统一读口；总案与迁移切片见 [板块合并与全局导航顶端设计](../plans/module-consolidation-and-navigation-redesign.md)。所有端点入参、出参、错误码以本文为准；PR 必须随附与本文一致的接口文档变更。文末附评审变更记录。

## 0. 总则

1. **鉴权与所有权**：沿用 `src/code_navi/auth/dependencies.py`——读接口用 `get_optional_principal` + `get_owned_principal_ids`，新表一律带可空 `owner_principal_id`（兼容期），登录态下按 owner 过滤，跨 owner 资源统一 404。**兼容期裁决（2026-08，S1 起生效）**：本契约的写接口暂不采用 `require_user`，与现有 `POST /learning/quiz/generate` 一致使用 `get_optional_principal`（匿名态 `owner_principal_id` 落 NULL）；兼容期结束后写接口统一切换 `require_user`。`profile_id`（UUID v4，== practice `learner_id`）仍作为画像聚合键传入。
2. **错误码**：400 业务校验失败（JSON body，应用层手工校验时使用）；401 未认证；403 角色或所有权不符；404 资源不存在（跨 owner 也 404）；409 前置条件未满足（未确认、未达准备度、Provider 禁用且无规则回退）；413 上传超限；422 schema 不合法（Pydantic 边界）；500 只返回安全信息 + `error_id`。调用方不得把 4xx/5xx 映射为空结果或成功。
3. **审计与事件**：每次模型运行产生可关联 Event；响应中的 `generation_mode`（`mock | model | rules_fallback`）与 `provider_name` 为必填事实字段，前端必须原样展示来源。
4. **降级诚信**：模型不可用时回退规则并明确标注；判分字段 `graded_by: rules | mock | model`、`is_mock: bool`、`graded: bool` 缺一不可，离线不可判时 `graded=false` 并提示对照参考答案自查，禁止伪称模型结论。
5. **幂等**：判分/提交类接口使用客户端铸造的 UUID v4 `attempt_id`，服务端按 `(attempt_id, item_id)` 幂等 upsert。
6. **答案保密**：判题依据（挖空答案、参考代码、隐藏测试）只在服务端归档中保存，任何读取接口剥离答案字段，判分时服务端加载——与现有 `/learning/quiz/grade` 同构。
7. **持久化**：新表进入共享 SQLAlchemy Base 并新增 Alembic revision（当前 head 为 `0021`，顺延编号，如 `0022_practice_sets_v1`）；迁移需验证空库与旧库升级。兼容练习记录的独立 SQLite 不动。

## 1. 动手实践 `/api/v1/practice`

Router 前缀 `/api/v1/practice`，tags `["Practice"]`；建议新目录 `src/code_navi/practice/`（若暂时挂入 `online_compiler` 也可，但 schema 文件独立）。

### 1.1 数据模型

```python
PracticeSetKind = Literal["concept_quiz", "code_practice", "mixed"]
PracticeItemKind = Literal["concept_quiz_question", "code_fill", "coding_problem"]
JudgeChannel = Literal["rules_llm", "server_tests", "llm_static", "explain_only"]
```

PracticeItem envelope（统一出参单元）：

```text
{
  "item_id": str,                       # 集内稳定 id
  "position": int,                      # 1-based
  "item_kind": PracticeItemKind,
  "knowledge_points": [str],            # ≤4，强绑定知识点名
  "judging": JudgeChannel,              # concept_quiz_question→rules_llm
                                        # coding_problem→server_tests
                                        # code_fill→llm_static | explain_only
  "payload": object                     # 按 item_kind 取下列三种之一
}
```

- `concept_quiz_question` → 现有 `QuizQuestion`（`learning/quiz/schemas.py:67`），**不新增字段**。
- `coding_problem` → 现有 `PracticeSetProblem.as_dict()`（`online_compiler/problem_sets.py:44`）。
- `code_fill` → 新 `CodeFillSpec`：

```text
CodeFillSpec {
  "title": str ≤200,
  "language": "python",                        # 首期固定
  "complexity": "light" | "heavy",             # 决定 judge_mode
  "judge_mode": "llm_static" | "explain_only",
  "code_masked": str ≤16000,                   # 挖空处为 ______（6 下划线）
  "blanks": [{
      "blank_id": str ≤64,
      "answer": str ≤500,                      # 仅服务端归档，出参剥离
      "alternate_answers": [str] ≤3,           # 等价写法
      "hint": str ≤200,
      "step_no": int ≥1                        # 所属步骤
  }] 2..6,
  "steps": [{
      "step_no": int ≥1,
      "title": str ≤120,
      "reason": str ≤400,                      # 排序/架构设计原因（评审要求）
      "sub_steps": [str] ≤4
  }] 1..5,
  "source": "generated" | "upload_derived",
  "reference_code_hash": str                   # SHA-256，可出示（完整性核对用）
}
```

复杂度判定规则（生成时由服务端定，前端不得改）：代码 >200 行、或涉及多文件/框架工程结构 → `heavy` → `explain_only`（仅解析与讲解，不做在线执行或挖空判分）；否则 `light` → `llm_static`。

存储（新表，均含 `owner_principal_id`、`created_at`）：

| 表 | 关键列 | 说明 |
| --- | --- | --- |
| `practice_sets` | `set_id` PK、`kind`、`context_snapshot` JSON、`local_profile_id`、`profile_id`、`generation_mode`、`provider_name` | 归档生成上下文，刷新恢复用 |
| `practice_set_items` | `item_id`、`set_id` FK、`position`、`item_kind`、`payload` JSON、`judge_secret` JSON | `judge_secret` 存答案/参考代码，任何出参路径剥离 |
| `code_fill_attempts` | `attempt_id`、`item_id`、`set_id`、`blank_answers` JSON、`score`、`max_score`、`graded_by`、`is_mock`、`graded`、`comment` | 判分事实；UNIQUE(attempt_id, item_id) |
| `practice_code_uploads` | `upload_id` PK、`filename`、`content_hash`、`kind`、`symbols` JSON、`imports` JSON、`framework_hints` JSON、`metrics` JSON | §1.5 解析结果归档；不落原文，只存摘要与哈希 |

### 1.2 `POST /api/v1/practice/sets/generate` — 统一生成网关

请求：

```text
{
  "kind": PracticeSetKind = "code_practice",
  "count": int 3..8 = 5,                      # 评审要求 3~8 题
  "difficulty": "easy"|"medium"|"hard" = "medium",
  "topic": str ≤512 | null,                   # 自由主题（无 context 时驱动生成；
                                              # concept_quiz 映射为 quiz 的 knowledge_point）
  "context": PracticeContextV1 | null,        # §3.1，理解→动手实践 payload
  "profile_id": uuid_v4 | null,               # 注入真实画像（复用 quiz 注入逻辑）
  "upload_ids": [str] ≤3,                     # 来自 §1.5 的解析结果引用
  "concept_ratio": float 0..1 | null          # kind=mixed 时概念题占比
}
```

校验：`topic`、`context`、`upload_ids` 三者至少一项非空，否则 422（`detail` 指明缺少生成依据）；`kind` 含概念题时取 `context.knowledge_points[0].name` ?? `topic` 作为 quiz `knowledge_point`，两者皆缺 → 422。

处理顺序：

1. 校验 → 组 prompt。概念题复用 `QUIZ_SYSTEM_PROMPT` 扩展"学习上下文"块；code_fill 用新 `CODE_FILL_SYSTEM_PROMPT`，约束（写入 prompt 与 reducer 双重校验）：
   - 先产出**完整可运行** Python 代码并通过 2 个自测样例，再裁剪 2~6 处**核心逻辑**为挖空；禁止挖空琐碎变量名、import 或纯格式行；
   - 按架构层次产出 1~5 个 Step 及子步骤，每个 Step 附排序/架构原因；
   - 输出必须强绑定 `context.knowledge_points`（或 `topic`）；
   - `upload_ids` 存在时以解析出的类/函数结构为骨架出题。
2. audit 一轮（沿用 quiz audit 模式），`verdict=adjust` 时最多重试一次。
3. 归档 `practice_sets` + `practice_set_items`（`judge_secret` 与 `blanks[].answer` 隔离存放）。**混合归档规则**：`kind` 含概念题时，概念题同步写入既有 quiz 归档，`session_id = set_id`，envelope 的 `item_id` 即 quiz 归档题 id，`judge_secret` 只存 `{"quiz_session_ref": set_id}` 不复制答案——两条写必须在同一 DB 事务内，判题继续走 `POST /api/v1/learning/quiz/grade`，接口签名零改动。
4. 响应：

```text
{
  "set_id": str,
  "kind": PracticeSetKind,
  "items": [PracticeItem],                    # blanks[].answer / judge_secret 已剥离；
                                              # concept 题判题提示：grading_hint = "/learning/quiz/grade"
  "coverage": [str],
  "generation_mode": "mock"|"model"|"rules_fallback",
  "provider_name": str,
  "audit": QuizAuditReport | null,
  "effective_context": PracticeContextV1 | null,   # 回显模型实际看到的结构化上下文
  "effective_topic": str | null                    # topic 驱动时回显主题（两者互斥回显）
}
```

错误：422 schema 或缺少生成依据；404 引用的 `upload_id` 不存在或非本人；409 Provider 禁用且规则回退也不可用（同现状 quiz 语义）；413 不会出现（上下文超限归入 422）。

### 1.3 `GET /api/v1/practice/sets/{set_id}` — 恢复归档

按 owner 校验返回 1.2 响应结构（重建 `effective_context`/`effective_topic`），供刷新恢复。404：不存在或非本人。出参永不含 `judge_secret` 与 `blanks[].answer`。

### 1.4 `POST /api/v1/practice/code-fill/grade` — 挖空静态判题

请求：

```text
{
  "set_id": str,
  "item_id": str,
  "attempt_id": uuid_v4,                      # 幂等键
  "blank_answers": [{"blank_id": str, "value": str ≤500}] ≤6,
  "profile_id": uuid_v4 | null
}
```

处理：

1. 服务端从归档加载 `judge_secret`。
2. **规则预判**：规范化（去空白、大小写折叠）后与 `answer`/`alternate_answers` 精确匹配，命中即满分；未命中同样是规则判分事实，`correct=false`、`score=0`、`graded=true`、`graded_by=rules`、`is_mock=false`。
3. 在线 Provider 可用时，未命中的空白拼接回完整代码，交 LLM 做**静态**正确性/等价性评审（prompt 约束：只做静态分析，禁止声称执行过代码；按空白逐项给分并给中文评语），相应结果 `graded_by=model`。
4. 逐项 `score`、总分汇总；按 `(attempt_id, item_id)` 幂等 upsert 到 `code_fill_attempts`；`profile_id` 存在时进入画像聚合。
5. 离线降级：按第 2 步规则结果返回；只有 `judge_secret` 缺失或答案结构不完整、无法判分时，才 `graded=false`、`score=0`、`is_mock=true`、`comment="离线模式无法静态判分，请对照参考答案自查"`（`hint` 不足以公开答案，不出示）。不得把已经按规则判错的题标记为未判分。

响应：

```text
{
  "attempt_id": str, "item_id": str, "set_id": str,
  "results": [{"blank_id": str, "correct": bool, "score": int,
               "max_score": int, "comment": str | null, "graded_by": "rules"|"model"|"mock"}],
  "total_score": int, "total_max_score": int,
  "graded": bool, "is_mock": bool, "provider_name": str | null
}
```

`judge_mode=explain_only` 的 item 调用本端点返回 409（附 explanation 提示：该题为讲解型，不判分）。响应只携带判题事实字段，不携带生成期字段（`generation_mode` 属于 §1.2/1.3 出参）。

### 1.5 `POST /api/v1/practice/code-uploads/analyze` — .py/.md 上传解析

请求（JSON）：`{"filename": str, "content_base64": str}`；或 multipart。约束：

- 仅接受 `.py`、`.md` 后缀（`.markdown` 归一为 `.md`）；其余 415；
- 解码后 ≤256KB，否则 413；
- 内容特征拒绝：检测到内联数据集痕迹（连续分隔符行 >2000、`pickle`/`parquet`/二进制魔数）→ 400，message 指示"仅支持核心代码或文档文件"。

处理：AST 解析（`ast` 模块）提取类/函数/签名/docstring 摘要；`.md` 提取标题结构与代码块清单；导入依赖清单；框架提示（flask/fastapi/torch/transformers 等关键词）。解析结果归档到 `practice_code_uploads`（原文只留 `content_hash`，不落原文），返回 `upload_id` 供 §1.2 引用与前端左栏结构树；§1.2 生成前校验 `upload_id` 存在且属于当前 owner。

响应：

```text
{
  "upload_id": str, "filename": str, "content_hash": str,
  "kind": "python"|"markdown",
  "symbols": [{"kind": "class"|"function", "name": str, "line": int,
               "signature": str ≤300, "docstring_summary": str ≤300}] ≤50,
  "imports": [str] ≤30,
  "framework_hints": [str] ≤8,
  "metrics": {"lines": int, "functions": int, "classes": int},
  "explanation_source": "rules"
}
```

解析是纯规则行为，不调用模型，`explanation_source` 恒为 `rules`。

### 1.6 `POST /api/v1/practice/code-fill/explain-symbol` — 悬停浮窗解析

请求：`{"upload_id" | "set_id"+"item_id", "symbol": {"name": str ≤128, "kind": "class"|"function", "code_excerpt": str ≤4000}}`。

处理：以 `sha256(name + excerpt)` 为缓存键（进程内 LRU ≤256 条）；命中直接返回同一解析并置 `cached=true`。未命中时调 LLM 生成 ≤600 字中文功能解析（约束：仅基于摘录，不得断言摘录外行为）；Provider 禁用 → 规则模板（签名 + docstring/摘录摘要）并标注。

响应：`{"explanation": str ≤600, "source": "model"|"rules", "cached": bool}`。限频：同 principal 30 次/分钟，超出 429。

### 1.7 与现有执行/判题边界

- `coding_problem` 类 item 仍走 `POST /api/v1/compiler/submit`（服务端隐藏测试），本模块不复制判题逻辑；
- `code_fill` **不做容器执行**（评审要求），Piston 不参与本模块；
- AI 解析/评语是独立建议，永不改写判分事实（沿用 evaluate/guidance 原则）。

## 2. 科研引导 `/api/v1/research/conversations/{conversation_id}/...`

全部端点挂现有 research router，沿用会话 404、准备度 409 语义。破坏性字段变更一律 additive：新增字段 + 旧字段投影保留，前端迁移完成后下线旧字段。两处例外：§2.5 论文蓝图（唯一非 additive 变更，豁免理由见该节）；§2.6 复现评估（已落库，改用 payload `schema_version` 版本化共存）。

**架构哲学与边界注记**：
1. **\"全 LLM + 结构化失败\"仅适用 v1 存量端点**：存量科研会话、计划、难点、实验设计、代码草案、论文蓝图等采用全 LLM 生成，失败时返回显式结构化错误，不以伪造的规则正文替代模型输出。
2. **P0-B 新增引导端点保持纯规则**：§2.1 `stage-briefing` 与 §2.2 `study-recommendations` 等端点保持确定性规则运算，绝不调用模型。
3. **事实与证据红线**：模型只许产出 `inference` 与 `to_verify` 标签，不得自造 `fact` 事实分类；`evidence_linked` 仅代表存在实验记录证据，绝不表示复现成功。

### 2.1 `GET .../stage-briefing` — 科研首屏阶段总结（规则）

六步闭环第 5→6 步的衔接接口。无 body；`?include_evidence_trends=true` 可选。

处理（纯规则，不调模型、不联网）：

1. 读取该会话 `context_provenance` 最终快照（无则 `has_learning_context=false`，HTTP 200 空态，不 404）；
2. 读取快照中的 `learning_mastery_snapshot`（§3.2，可选）；
3. 汇总已保存 evidence bundle 数、reproduction pipeline 状态，作为"论文复现路径"入口；
4. `include_evidence_trends=true` 时按已存 Evidence 的年份/来源聚合关键词 Top3 作为方向提示，每条附 `evidence_refs`（只允许引用本会话已保存证据）。

响应：

```text
{
  "conversation_id": str,
  "has_learning_context": bool,
  "stage_summary": {
      "topic": str | null,
      "digest": str ≤1000 | null,             # 学习背景摘要（快照原文截取）
      "knowledge_points": [{"name": str, "mastery": float|null}] ≤8 | null
  },
  "reproduction_entry": {"bundle_count": int, "pipeline_status": str|null},
  "evidence_trends": [{"keyword": str, "paper_count": int,
                       "evidence_refs": [EvidenceReference]}] ≤3,
  "generated_by": "rules", "generated_at": iso8601
}
```

实现注记（PR-A，2026-08，实现即冻结的规则裁定）：

1. `reproduction_entry.pipeline_status` 取该会话最新一条复现 pipeline 的任务状态投影：任一 task `evidence_linked` → `evidence_linked`，否则 `not_started`；无 pipeline 为 `null`。
2. `evidence_trends` 关键词规则：对会话内已存 evidence bundle 的论文（按 URL 去重）标题做小写分词（`[a-z0-9]+`、长度 ≥3、去停用词），按命中论文数取 Top3（并列按字典序）；`paper_count` 为命中的去重论文数；每条最多 5 条 `evidence_refs`（按 bundle 时间与论文存储顺序取前 5）。
3. `knowledge_points[].mastery` 恒为 `null`：§3.2 快照只存 strong/weak 列表、无数值，规则产物不得编造掌握度数值。
4. `stage_summary.digest` 为快照 `summary` 原文归一空白后截断（≤1000 字符）。

### 2.2 `POST .../study-recommendations` — 为科研而学（规则，显式触发）

请求：`{"user_confirmed": true}`；false 或缺省 → 409。

处理：从画像 `methods`、`data_requirements`、`plan.suggested_datasets_or_metrics` 规则提取知识点关键词（去重 ≤6 条）；对照 `learning_mastery_snapshot` 标注 `mastered | weak | unknown`；生成跳转 payload。

响应：

```text
{
  "recommendations": [{
      "knowledge_point": str ≤128,
      "reason": str ≤300,
      "mastery_status": "mastered"|"weak"|"unknown",
      "action": {"type": "learning_explain"|"practice_set",
                 "payload": object}          # 分别可直接投给 explain 或 §1.2
  }] ≤6,
  "provenance_note": str                     # 说明规则来源与未调用模型
}
```

实现注记（PR-A，2026-08，实现即冻结的规则裁定）：

1. 知识点提取：`methods`、`data_requirements`、`plan.suggested_datasets_or_metrics` 条目按中英文常见分隔符（`,` `，` `、` `;` `；` `。` `/` `|` 与换行）切分为短语，归一空白、丢弃长度 >128 字符的长句；大小写不敏感去重后按 methods → data_requirements → plan 顺序取前 6 条。plan 复用现有 `build_conversation_research_plan`（仅 `ready_for_plan` 时产出）；未就绪时仅从画像 `methods`/`data_requirements` 提取。
2. `mastery_status` 对照：快照 `strong` 命中 → `mastered`、`weak` 命中 → `weak`、快照缺失或未命中 → `unknown`（大小写不敏感精确匹配）。
3. `action` 规则：`mastered` → `practice_set`，payload `{"kind": "code_practice", "topic": <关键词>, "count": 5}`（可直接投 §1.2 生成网关）；`weak`/`unknown` → `learning_explain`，payload `{"knowledge_point": <关键词>}`（可直接投 `POST /api/v1/learning/explain`）。
4. 错误码次序：会话不存在（含跨 owner）一律 404；会话存在且 `user_confirmed` 非 true 才 409。

### 2.3 `POST .../topic-difficulty-analysis` v2 — 温故知新重构

**现状更正（v2 评审）**：现状分区为 研究问题/方法难点/数据与实验难点/复现风险/资源需求（+关联计划项），`ResearchAnalysisItem.area` 是自由字符串（≤200）；"对象与场景"是科研画像面板对 `profile.context` 的前端标签（`ResearchProfilePanel.tsx:92`），并非现有分析分区。

变更（additive）：

1. `ResearchAnalysisItem` 新增 `area_code: Literal["research_goal","research_motivation","method_difficulty","data_practice_difficulty"]`（研究目标/研究动机/方法难点/数据实操难点四区），由 reducer 从模型/规则产出的 `area` 文本归一映射；**旧 `area` 字段保留**（显示名），历史自由分区值不迁移。画像字段 `context` 保留但不再驱动分析产出、不再在画像面板展示（§4.3）。
2. Token 深度：`method_difficulty` 与 `data_practice_difficulty` 区条目的 `content` 上限 1000→2000 字符，prompt 要求分步骤陈述（1) 2) 3)）。
3. 能力边界：快照存在时，`method_difficulty` 条目追加可选 `capability_note: str ≤200`（规则生成，标注该难点超出/贴合当前掌握范围）。
4. prompt 重构（陈盛漳）：system prompt 以研究目标与动机为主轴，不再设问对象与场景；模型输出经 reducer 校验，无法归入四区的条目降级为普通建议文本（不带 `area_code`），不丢弃信息。

### 2.4 `POST .../experiment-design` v2 — 实验方案严谨化

1. 顶层新增 `task_type: Literal["classification","regression","clustering","retrieval","generation","other"]`，规则从画像方法/问题推断，允许用户在请求中显式指定 `task_type_override`。
2. 新增服务端常量 **标准指标目录**（`src/code_navi/research/metrics_catalog.py`，纯规则数据）：

| task_type | 标准指标 |
| --- | --- |
| classification | ACC、Precision、Recall、F1、AUC |
| regression | RMSE、MAE、R² |
| clustering | Silhouette、ARI、NMI |
| retrieval | MRR、NDCG、Recall@K |
| generation | BLEU、ROUGE、（人工评估说明） |

3. `metrics` 条目升级为 `MetricSpec`：

```text
{"name": str ≤64, "definition": str ≤300, "formula": str ≤300 | null,
 "higher_is_better": bool, "applies_to_task_type": [task_type] ≥1,
 "source": "standard_catalog"|"model_suggested", "to_verify": bool}
```

   校验规则（reducer 强制）：`name` 命中目录 → `source=standard_catalog`、`to_verify=false` 并回填目录中的 definition/formula；未命中 → `source=model_suggested`、`to_verify=true`（禁止编造指标语义）。模型输出中自造的"准确率 92%"式数值断言一律剥离。
4. `data_sources` 条目升级为 `DatasetRef`：`{"name": str, "url": str|null, "license_note": str ≤200|null, "to_verify": bool}`；模型建议的数据源必须给公开可访问 URL，无 URL → `to_verify=true` 且不展示为可用数据源。
5. 兼容：旧 `metrics`/`data_sources`（`ResearchPlanEntry`）由新结构投影生成（name+definition 截断），标注 deprecated。

### 2.5 `POST .../paper-blueprint` v2 — 五段标准学术结构

**现状更正（v2 评审）**：`PaperBlueprintSection.section` 现为六段中文枚举 `["引言","相关工作","方法","实验","讨论","结论"]`（`conversation_schemas.py:733`），按需生成、不落库。v2 枚举改为固定五段，顺序即输出顺序：

1. `摘要`（abstract）
2. `介绍`（introduction）
3. `文献综述`（related_work）
4. `方法`（method）
5. `实验`（experiments）

沿用中文枚举值与现有代码风格一致；原"引言"内容并入"介绍"；"摘要"段为新增（写作目标：从画像+计划规则提炼 ≤200 字结构化摘要骨架）；原"讨论"段的可信边界/风险内容并入"实验"段 `missing_evidence`，原"结论"段并入"方法"段 `writing_goal` 的收束要点——**讨论/结论不再作为独立段**（评审要求聚焦五段）。每段 `writing_goal`、`evidence_references`、`missing_evidence`、`forbidden_claims` 语义不变；prompt 中亦不得设问"对象与场景"。

**这是本设计中唯一一处非 additive 变更**，豁免理由（三项同时成立，缺一不可）：① 蓝图不落库，无历史数据迁移；② 唯一消费方是 `/research` 前端，与后端在 S3 同一切片内切换；③ 契约测试随 PR 同步更新。豁免不适用于其他任何端点。前端蓝图面板置于内容最下方（布局要求，见总案 D4）。

### 2.6 `POST .../reproduction-evaluations` v2 — 六条评分依据

**现状更正（v2 评审）**：现状为五维 `Literal["research_definition","source_traceability","reproduction_plan","execution_evidence","reflection_and_compliance"]`，每维 0..20、总分 100，且评估快照**已落库**（`research_reproduction_evaluations.evaluation_data` JSON，`schema_version=reproduction-project-evaluation.v1`）。v2 不改表结构，`evaluation_data` 内以 `schema_version: "reproduction-project-evaluation.v2"` 版本化共存：

1. **新评估**（本端点产生）使用 v2 结构：固定 6 条 criterion，每条：

```text
{"criterion_no": 1..6, "title": str, "score": 0|1|2,
 "basis": str ≤500,                        # 确切评分依据，禁止一句话带过
 "evidence_refs": [EvidenceReference] | null,
 "improvement_task_id": str | null}
```

六条固定为：① 研究问题与假设可复述性；② 方法可执行性（步骤完整、变量可操作）；③ 数据可得性（公开链接与许可）；④ 指标与统计方法正确性（对照 §2.4 目录）；⑤ 计算资源与时间可行性；⑥ 结果核验路径（baseline 与预期区间）。总分 12，`total_score` 字段随响应返回。前端逐条结构化展示，不得合并为纯文本。
2. **历史 v1 评估只读保留**：读取端点（`GET .../reproduction-evaluations/{id}` 与列表）按 payload 内 `schema_version` 分发渲染；v1 快照原样返回，**不做 100→12 的数值换算**（评分模型不同，换算即编造）。列表响应新增 `schema_version` 字段供前端选择渲染器。
3. **改进任务联动**：`ReproductionImprovementTask` 仍按维度生成；v2 评估的 task `title`/`classification` 沿用现有字段，`basis` 引用 criterion_no，不新增表。
4. `submission-readiness` 等下游消费者按 v2 总分口径重算阈值（12 分制），v1 历史值不参与新阈值计算，读侧遇到 v1 标注"历史口径"。

### 2.7 Prompt 总约束（陈盛漳编码时遵循）

1. 五段结构写入 paper-blueprint system prompt；指标目录以白名单注入 experiment-design prompt；
2. 模型输出统一过 reducer：越界字段丢弃（温故知新条目例外——无法归入四区的降级为无 `area_code` 的普通建议文本，见 §2.3）；未命中目录指标降级 `to_verify`；引用了未保存 Evidence 的方向分析降级为"建议"并去掉证据声明；
3. 所有产物 `provenance_note` 必须写明 规则/模型/降级 来源与边界（沿用现有边界语义）。

### 2.8 `POST .../messages/retry-last` — 对话回复重试（检查点 2）

请求：无 body。

处理：当上一轮模型生成由于网络、Provider 异常或输出解析校验失败中断时，保持用户输入的消息文本与会话上下文不变，仅重发并重试该轮模型回复。若最新一条消息非 assistant 失败记录，返回 HTTP 409。

响应：返回更新后的 `ResearchConversationResponse`。

### 2.9 `PUT .../reproduction-conditions` — 复现条件收集与 409 门控（检查点 4）

请求：
```text
{
  "hardware_environment": str ≤500,     # GPU/CPU/内存配置
  "time_budget": str ≤200,               # 预期耗时/可用周期
  "reproduction_goal": str ≤500          # 精度验证/性能复现/全量重跑
}
```

处理：将用户提供的客观运行先决条件作为用户事实（`fact`）记录在 `generated_artifacts.reproduction_conditions` 中。下游 `POST .../reproduction-pipelines` 在生成复现规划前必须校验此条件集合已完整填报，若缺失直接返回 HTTP 409 `reproduction_conditions_missing` 阻止未约束的方案生成。

响应：返回包含已持久化条件的 `ResearchConversationResponse`。

### 2.10 `POST/GET .../reading-reports` — 论文精读与阅读报告（检查点 5）

`POST .../reading-reports` 请求：
```text
{
  "paper_url": str,
  "title": str ≤200,
  "content": str ≤8000
}
```

处理：允许学生对已存入文献库的论文提交个人阅读笔记与报告摘要。报告作为用户第一手事实证据归档入会话，不被模型二次加工或改写，可作为后续复现规划与导图生成的事实输入。`GET .../reading-reports` 原样按存储顺序返回报告列表。

## 3. 学习端上下文协议（夏俊杰）

### 3.1 `practice-context.v1` — 理解/检查 → 动手实践

学习端在跳转动手实践时构造（替代现状 `FlowPayload` 的纯主题交接）：

```text
{
  "source_session_id": str ≤64,              # 学习 session_id
  "knowledge_points": [{
      "name": str ≤128,
      "source_ref": str ≤256,                # notebook_item_id / explain 引用
      "mastery": float 0..1 | null           # 画像有真实值才填，否则 null
  }] 1..8,
  "objective": str ≤512,                     # 用户目标原文
  "notes_summary": str ≤2000 | null          # 用户勾选的笔记摘要
}
```

传递边界：跳转前用户可查看、修改、清除（scope.md 跨模块规则）；URL 仅带轻量指针，正文经 `POST /api/v1/practice/sets/generate` 的 `context` 字段提交；浏览器侧仍保留一份可清除的刷新回退缓存（现 flow-store 机制不变，内容升级为本结构）。

### 3.2 `learning_mastery_snapshot` — 确认上下文可选项

`POST /api/v1/context-transfers/{id}/confirm` 请求体新增可选字段：

```text
"include_mastery_snapshot": bool = false        # 客户端只传开关，不传数值
```

确认后 `context-provenance.v1` 快照 JSON 内由服务端写入：

```text
"learning_mastery_snapshot": {
    "strong": [str] ≤5, "weak": [str] ≤5
}
```

快照内容按来源 `profile_id` 的真实画像**规则生成**（不接受客户端自填数值），供 §2.1/§2.2/§2.3 读取。一般知识内容不会自动变成研究问题/方法/数据/结论——快照只作为能力边界提示。开关关闭或画像样本不足时快照缺省，读取方按空态处理。

### 3.3 笔记 → 科研引导入口

`/learning/notebook` 页 DownstreamGoCard 保持现有跳转；新增动作"带总结进入科研引导"：跳转 `/research` 后由页面调用 `GET .../stage-briefing` 渲染首屏简报卡片。不需要新的后端端点。

## 4. 画像统一读口与共用投影（梓柯实现，夏俊杰接线）

### 4.1 `GET /api/v1/portraits/overview` — 两套画像一次读齐

总案 D1/D3 的统一读口。**只读聚合投影，不建第二套事实表**：learning 块委托 `learning_profile` 服务（`GET /api/v1/profile` 同一聚合逻辑），research 块委托 research 会话服务，bridges 块只投影既有信号。纯规则，不调模型、不联网。

请求（query）：`profile_id: uuid_v4`（必填）、`local_profile_id: uuid_v4 | null`（Practice 复盘投影需要）、`conversation_limit: int 1..10 = 5`。

响应：

```text
{
  "profile_id": str,
  "learning": {
      "mastery": {"graded_attempts": int, "strong_points": [str] ≤5, "weak_points": [str] ≤5,
                  "insufficient_sample": bool},
      "review_queue": {"active_confusion_marks": int, "top_surfaces": [str] ≤3},
      "knowledge_gaps": [{"knowledge_point": str, "source_type": str, "summary": str}] ≤8
  },
  "research": {
      "conversations": [{
          "conversation_id": str, "topic": str | null, "updated_at": iso8601,
          "readiness": str | null,             # 现有会话准备度语义
          "evidence_bundle_count": int,
          "reproduction_pipeline_status": str | null
      }] ≤conversation_limit
  },
  "bridges": {
      "learning_to_research": {"latest_transfer_id": str | null,
                                "confirmed": bool, "has_mastery_snapshot": bool},
      "research_to_learning": {"pending_study_recommendations": int ≥0}   # 最近一次会话的未消化条数
  },
  "generated_by": "rules", "generated_at": iso8601
}
```

错误：401/403 按 §0.1；`profile_id` 非法 422；**任何空态返回 200 + 空数组/空对象**（新用户零数据不报错）。鉴权：`get_optional_principal` + `get_owned_principal_ids`，登录态下 research 会话按 owner 过滤（`research_conversations.owner_principal_id`），匿名态沿用现状仅按会话可达性。前端画像中枢（`/learning/portrait` 复盘页 + 科研画像组件）一次调用渲染，替代现状前端自行拼 `/api/v1/profile` + 会话列表两次请求。

### 4.2 `GET /api/v1/learning/knowledge-gaps` — 新增 code_fill 缺口来源

变更（additive）：`source_type` 新增枚举值 `code_fill_attempt`。聚合规则与 quiz 一致：仅 `graded=true` 的 `code_fill_attempts` 参与；缺口知识点取该 item 归档的 `knowledge_points`（§1.1 envelope 字段），摘要取判分 `comment` 截断。三源只读投影原则不变，不复制判分事实。

### 4.3 科研画像面板 v2（组件级，无新端点）

`ResearchProfilePanel` 按总案 D3/评审意见调整展示字段：砍掉"对象与场景"（`profile.context` 不再展示），保留 研究主题/研究动机/方法路径/数据需求/预期产出；数据仍来自现有会话读取接口，仅前端变更，随 S3 一并交付。

## 5. 实现顺序

1. S1：迁移 + schema + 网关骨架（mock 模式闭环）+ 契约测试；
2. S2/S3 并行：动手实践（§1.2/1.4–1.6、code_fill prompt）与科研 v2（§2.3–2.6）；
3. S4：上下文协议（§3）接线 + 画像统一读口（§4，梓柯）；
4. S5：前端导航与 UI（总案 D4）。
每片完成标准：`tests/` 契约测试通过 + 手动端到端闭环（mock 与真实 Provider 各一轮）+ 受影响文档同步。

### 5.1 P1-A 实现状态

- §1.2：mock 生成行为保持冻结；`upload_ids` 已接入 `practice_code_uploads` 存在性/owner 校验；mixed/concept 概念题双写 quiz 归档完成；真实 code_fill 生成通过 `CODE_NAVI_PRACTICE_PROVIDER` 显式启用，失败时 `generation_mode=rules_fallback`。
- §1.4：规则判分、跨 owner 404、`explain_only` 409、`(attempt_id, item_id)` 幂等 upsert 与 LLM 静态评审已实现；`profile_id` 进入画像聚合仍待接线。
- §1.5：`.py/.md` 解析、415/413/数据集 400 与结果持久化已实现。
- §1.6：`symbol.code_excerpt` schema 已补齐；进程内 LRU≤256 缓存、模型路径、规则回退与同 principal 限频已实现。

### 5.2 P0-B 实现状态（PR-A，2026-08）

- §2.1 `stage-briefing` 与 §2.2 `study-recommendations` 已实现（`src/code_navi/research/conversation_guidance.py`，独立模块避免与存量 `conversation_service.py` 大改冲突）；纯规则、不调模型、不联网；空态 200、显式触发 409、跨 owner 404 均有契约测试（`tests/test_research_guidance.py`）。
- 规则裁定见 §2.1/§2.2 实现注记；`learning_mastery_snapshot`（§3.2）未落地前快照缺省走空态，读取侧已按原始 JSON 键预留，P1-B 落地后无需改动本端点。
- §2.3–2.6 待 PR-B/PR-C（陈盛漳），不受本 PR 影响。

## 6. 评审变更记录（v2 自评审，2026-01）

| # | 变更 | 依据（代码证据） |
| --- | --- | --- |
| C1 | §1.2 请求新增 `topic`，并规定 `topic`/`context`/`upload_ids` 至少一项否则 422 | `learning/quiz/schemas.py:125` `knowledge_point` 必填；practice 页现状靠自由 prompt 组卷 |
| C2 | §1.2 新增混合归档规则：概念题双写 quiz 归档（`session_id=set_id`、`item_id`=quiz 题 id、`judge_secret` 存引用不存答案）、同一事务、判题接口零改动 | `/learning/quiz/grade` 按 session 读归档；避免第三条判题通道与答案双份存储 |
| C3 | §1.4 出参删除 `generation_mode`，`provider_name` 可空 | 判题响应只保留判题事实字段，生成期字段属于 §1.2/1.3 |
| C4 | §2.5 蓝图现状更正为六段中文枚举；v2 沿用中文枚举值（摘要/介绍/文献综述/方法/实验）；讨论/结论内容去向明确；非 additive 豁免三条件 | `conversation_schemas.py:733`；蓝图按需生成不落库（`router.py:681` 无持久化模型） |
| C5 | §2.6 复现评估改为 payload `schema_version=v2` 共存：v1 历史只读、不做 100→12 数值换算；下游阈值按 12 分制重算且 v1 不参与 | `reproduction_evaluation_schemas.py:12`（五维×20=100）；`models.py:149` `evaluation_data` JSON 已落库 |
| C6 | 新增 §4 画像统一读口契约（v1 总案 D1/D3 引用了"接口文档 §2"但 v1 文档并无该契约） | 总案与接口文档引用对齐，PR 交付标准需要可对照的入参/出参 |
| C7 | §4.2 knowledge-gaps 新增 `code_fill_attempt` 来源（从总案下沉到契约文档） | 画像归因需要明确入表与聚合规则 |
| C8 | §4.3 明确科研画像面板砍"对象与场景"是**前端组件级变更**（`profile.context` 字段保留，仅不展示） | `ResearchProfilePanel.tsx:92` 该词是字段标签而非分析分区 |
