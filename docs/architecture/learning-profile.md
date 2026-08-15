# 学情画像（Learning Profile）实施方案（评审修订版）

> 本文档是「学情画像」功能的**实施方案**，供 Claude Code 直接按此实现。
> 它整合了对原始方案的批判性评审结论、两处事实修正、身份键设计、数据模型、
> 接口、落库时机与分期里程碑。实现落地后，应把本文档中的接口与身份键事实
> 折叠进 `docs/architecture/system.md` 与 `docs/product/scope.md`，本文档随之归档或删除。

## 0. 已定决策（用户已裁决，直接执行）

1. **统一 profile 键 = 复用练习侧 `learner_id`**：值即前端 localStorage 键
   `code-navi-compiler-learner-id` 中的 UUID v4（由 `getLearnerId()` 生成，
   见 `frontend/app/(student)/practice/page.tsx:1222`）。
   - 练习侧已有该值，直接作为画像键。
   - 学习侧的新写入（quiz 判分）**额外携带**该 UUID 作为 `profile_id`（可空列）。
   - 不再新建第三个 localStorage 键。
2. **画像端点 = `GET /api/v1/profile`**，独立模块 `src/code_navi/learning_profile/`，
   独立路由前缀（避免与既有 `/api/v1/learning` 前缀冲突）。

---

## 1. 目标与非目标

**目标**：为单个匿名学生（本浏览器）提供一份由**真实持久化分数**聚合出的学情画像：
知识点掌握度、强弱项排序、练习统计（提交数/通过率/错误类型分布）、按周时间线、
规则生成的建议文案（LLM 仅作润色）。

**非目标**（不实现）：教师端/班级聚合、真实账号/跨浏览器、完整 LMS、自适应推荐、
自动组卷闭环、对历史数据回填伪造掌握度。

---

## 2. 现状事实核对（实现前必读，含两处必须修正的初稿错误）

数据源盘点（已逐文件核实）：

1. **学习摘要/笔记** → `NotebookItemModel`（`src/code_navi/learning/models.py`）：
   `user_id` 硬编码 `"poc-user"`，有 `session_id`/`knowledge_id`/`item_type`/`created_at`，
   详情在 JSON `extra_data`。
2. **quiz 试卷** → 以 `item_type="quiz"` 归档在 `NotebookItemModel.extra_data`，
   含 `quiz_id`、每题 `points/answer/analysis/type/comment_prompt`（`quiz/services.py:_archive`）。
   **判分结果不持久化**（`grade_quiz` 无状态，判完即弃）。
3. **练习记录** → 独立 SQLite `LearningRecordStore`（`online_compiler/learning_records.py`），
   按匿名 `learner_id` 存 `category/error_type/ai_status/reference_score/created_at`。
4. **科研会话** → `research_conversations`（未关联学生身份；仅 context-transfer 确认时
   经 `confirmed_conversation_id` 关联学习 session）。
5. **三个互不关联的匿名键**：学习 `session_id`（`sess-{hex}`）、练习 `learner_id`（UUID v4）、
   科研 `conversation_id`（UUID）——见 `docs/architecture/system.md` 第 5 节身份键表。

### 必须修正的初稿错误 A：单选题不在判分落库范围

`grade_quiz`（`quiz/services.py:539`）**只判 `fill_blank` / `short_answer`**；
`single` 由前端 `QuizView.isCorrect()` 客户端判分（`QuizView.tsx:191`）。
若只从 `grade_quiz` 落库，单选题永远不会进入画像，掌握度分母失真。

**修正**：让 `grade` 端点把 `single` 也收进来，由**服务端确定性地**与归档 `answer`
精确比对判分（复用 exact-match 逻辑，`graded_by="rules"`，`is_mock=False`），
三种题型统一落库。单选题从此不再信任客户端判分结果（服务端权威）。

### 必须修正的初稿错误 B：练习正确性信号与落库位置

- 自由运行 `POST /compiler/execute` 会写 `LearningRecordStore.add()`
  （`application.py:210`），但其 `reference_score = feedback.quality.overall` 是
  **AI 代码表达质量分（0–100，可读性/结构/健壮性均值）**，`evaluation.py:58` 明确
  「参考分只评价代码表达质量，不代表题目正确性」。**不得作为掌握度。**
- 真正的题目正确性来自 `POST /compiler/submit` → `judge_submission`（`judging.py`），
  返回 `verdict/score/passed/total/passed_points/total_points`——但 `submit` 当前
  **只放进内存 `PendingSubmission`（TTL 900s）供 guidance，从不持久化**（`application.py:290`）。
- `ProblemVersion`（submit 所用对象）不含 `knowledge_tags`；`knowledge_tags` 在
  `ProblemDefinition`（`problems/catalog.py:45` 的 `DEFAULT_PROBLEM_DEFINITIONS`），
  submit 路径当前未串入。

**修正**：新增 `practice_attempts` 表，在 `submit` 内**同步持久化**判题结果，
并在提交时从 `DEFAULT_PROBLEM_DEFINITIONS` 解析 `knowledge_tags` 快照写入。
自由运行 `execute` 的 learning_records **保持不动**（其 `error_type` 仅作错误类型分布辅助信号）。
**不要再往非 Alembic 的独立 sqlite 加 schema**（`system.md` 已声明该路径生产化前须统一）。

---

## 3. 身份键方案（统一 profile 键，零破坏性迁移）

统一 profile 键 = `learner_id` 的 UUID v4 值。原则：**叠加聚合键，不重键历史数据。**

| 键 | 作用 | 本次是否改动 |
| --- | --- | --- |
| 学习 `session_id` | 隔离 `notebook_items` 与 quiz 归档读取 | 不改，照旧 |
| 练习 `learner_id` | 练习作用域 + **画像聚合键** | 不改语义，升级为 profile 键 |
| 科研 `conversation_id` | 恢复科研会话 | 不改，本次不参与画像 |
| 未来 `user_id` | 真实账号（auth 阶段） | 本次仅在新表预置可空列 |

- 学习侧新写入：`GradeRequest` 增加可空 `profile_id`，前端传 `getLearnerId()` 的 UUID 值。
  前端学习页需读取 `code-navi-compiler-learner-id`（无则经 `getLearnerId()` 铸一个新 UUID）。
- 练习侧新写入：`submit` 已带 `learnerId`，即 profile 键本身，无需新增字段。
- 画像服务 join 键：`quiz_attempts.profile_id == practice_attempts.learner_id == profile_id 参数`。
- **不回填、不重键**现有 `notebook_items`/`learning_records`。画像只反映上线后产生的新作答，
  这是诚实行为，绝不靠回填伪造历史掌握度。

**将来用户系统对接**（auth 阶段再做，本次仅预留）：
- 新表已含可空 `user_id`；auth 落地后新写入填 `user_id`，画像查询键从 `profile_id`
  切换为 `user_id`，无需改表。
- 匿名身份「认领/合并」时再建映射表 `anonymous_profile_users(profile_id PK, user_id)`。
- 历史数据归属回填、删除权/导出权（GDPR 类）留到 auth 阶段。

---

## 4. 数据模型（DDL 草案）

Alembic 事实：当前单一 head = `research_submission_profile_v1`（`0010_submission_profiles.py`）；
`0005` 之后 revision id 已用描述性 `*_v1` slug（文件名数字前缀已乱序，勿依赖）。
**新 revision：`down_revision = "research_submission_profile_v1"`，revision id 用 `learning_profile_v1`**，
不改写任何已发布 revision。

### 4.1 `quiz_attempts`（Alembic，共享 `code_navi.db.Base`）

```sql
CREATE TABLE quiz_attempts (
  id              TEXT PRIMARY KEY,           -- uuid
  attempt_id      TEXT NOT NULL,              -- 客户端幂等键 (UUID v4)
  quiz_id         TEXT NOT NULL,
  session_id      TEXT NOT NULL,              -- 学习作用域键 (既有约定)
  knowledge_point TEXT NOT NULL,              -- 自由文本知识点 (== notebook.knowledge_id)
  profile_id      TEXT NULL,                  -- 统一 profile 键 (= learner_id 值)
  user_id         TEXT NULL,                  -- 未来真实账号 (本次可空)
  question_id     TEXT NOT NULL,
  question_type   TEXT NOT NULL,              -- single|fill_blank|short_answer
  points          INTEGER NOT NULL,
  score           INTEGER NOT NULL,
  max_score       INTEGER NOT NULL,
  correct         BOOLEAN NOT NULL,
  graded          BOOLEAN NOT NULL,           -- false: 不进掌握度分母
  graded_by       TEXT NOT NULL,              -- mock|rules|model
  is_mock         BOOLEAN NOT NULL,
  comment         TEXT NULL,
  created_at      DATETIME NOT NULL
);
CREATE UNIQUE INDEX ux_quiz_attempts_idem ON quiz_attempts (attempt_id, question_id);
CREATE INDEX ix_quiz_attempts_profile ON quiz_attempts (profile_id, knowledge_point, created_at);
CREATE INDEX ix_quiz_attempts_session ON quiz_attempts (session_id, created_at);
```

### 4.2 `practice_attempts`（Alembic，共享 Base）

```sql
CREATE TABLE practice_attempts (
  id               TEXT PRIMARY KEY,
  attempt_id       TEXT NOT NULL,             -- 幂等键
  problem_id       TEXT NOT NULL,
  problem_version  INTEGER NOT NULL,
  learner_id       TEXT NOT NULL,             -- == profile 键 (UUID v4)
  user_id          TEXT NULL,                 -- 未来真实账号
  knowledge_tags   TEXT NOT NULL,             -- JSON 数组快照 (提交时从 catalog 解析)
  verdict          TEXT NOT NULL,
  score            REAL NOT NULL,             -- 0..100
  passed           INTEGER NOT NULL,
  total            INTEGER NOT NULL,
  passed_points    INTEGER NOT NULL,
  total_points     INTEGER NOT NULL,
  created_at       DATETIME NOT NULL
);
CREATE UNIQUE INDEX ux_practice_attempts_idem ON practice_attempts (attempt_id);
CREATE INDEX ix_practice_attempts_learner ON practice_attempts (learner_id, created_at);
```

要点：
- `profile_id`（quiz 侧）与 `learner_id`（practice 侧）**存同一个 UUID v4 值**；画像服务
  统一按该值 join，`practice_attempts` 不再重复加 `profile_id` 列。
- `knowledge_tags` 存提交时刻快照（JSON），避免依赖内存 catalog 后续变更。
- 隐藏测试内容**不落库**（只落 verdict/score/passed/total，符合 `scope.md` 2.2.4）。

---

## 5. 接口设计

### 5.1 扩展 `POST /api/v1/learning/quiz/grade`（加法式，向后兼容）

```jsonc
// 请求：新增 attempt_id、profile_id；student_answers 现含 single
{
  "session_id": "sess-...",
  "quiz_id": "quiz-...",
  "attempt_id": "uuid-v4",          // 新增：幂等键
  "profile_id": "uuid-v4",          // 新增：统一 profile 键 (可空)
  "student_answers": [
    { "question_id": "q1", "answer": ["B"] },   // single 由服务端确定性判分
    { "question_id": "q2", "answer": ["3"] }
  ]
}
// 响应：新增 attempt_id；其余字段不变
{ "session_id":"...", "attempt_id":"...", "results":[...],
  "total_score":10, "total_max_score":20, "generation_mode":"...", "provider_name":"..." }
```

判分规则（服务端权威）：
- `single` / `fill_blank`（离线）：与归档 `answer` 精确比对，`graded_by="rules"`（single）
  或 `graded_by="mock" + is_mock=True`（离线填空），绝不伪造 LLM 结论。
- `short_answer`：在线走 LLM（`graded_by="model"`）；离线 `graded=False` 提示自评，
  **不计入掌握度分母**。

### 5.2 扩展 `POST /api/v1/compiler/submit`（加法式）

```jsonc
// 请求：不变（learnerId 即 profile 键）
{ "problemId":"palindrome", "problemVersion":1, "source":"...", "learnerId":"uuid" }
// 响应：新增 attemptId；其余字段不变
{ "submissionId":"...", "attemptId":"uuid", "verdict":"accepted", "score":100, ... }
```

服务端在 `submit` 内：`judge_submission` → 解析 `knowledge_tags`（`DEFAULT_PROBLEM_DEFINITIONS`）
→ 写 `practice_attempts` → 提交。

### 5.3 新增 `GET /api/v1/profile`

独立模块 `src/code_navi/learning_profile/`（router 前缀 `/api/v1/profile`）。

```jsonc
// GET /api/v1/profile?profile_id=<uuid-v4>
{
  "profile_id": "uuid",
  "generated_at": "ISO8601",
  "mastery": [
    { "knowledge_point": "...", "quiz_rate": 0.8, "practice_rate": null,
      "mastery": null, "sample_size": 3, "status": "insufficient" } // 样本不足→mastery=null
  ],
  "strengths":  ["..."],                // 规则排序
  "weaknesses": ["..."],
  "practice_stats": { "submissions": 12, "pass_rate": 0.66,
                      "error_types": { "wrong_answer": 4, "runtime_error": 2 } },
  "timeline": [ { "week": "2026-W31", "quiz_attempts": 2, "practice_attempts": 3 } ],
  "suggestions": ["..."]                // 规则模板；LLM 仅润色，离线回退模板
}
```

**鉴权边界**：无身份鉴权，语义与 `GET /api/v1/compiler/records` 一致——
「只返回该 key 的数据，不是授权查询」。服务端仅按 `profile_id` 过滤；
未知 key 返回空画像（200 + `sample_size=0`），**不返回 404**（避免泄漏 key 是否存在）。
`profile_id` 校验为 UUID v4（复用 `_validate_learner_id` 语义）。

掌握度公式（规则先算，无 LLM 参与计算）：
- quiz 得分率 = `Σscore / Σmax_score`（仅 `graded=true`）。
- 练习 = `passed_points / total_points`。
- 加权系数写死并注释；样本 < 阈值（默认 3）时 `mastery=null + "样本不足"`，
  页面显示「暂无足够数据」，**禁止显示 0% 或伪百分比**。

---

## 6. 落库时机与幂等

**同步落库、服务端权威**：在 `grade_quiz` / `submit` 内部、判分完成后、返回响应前，
同事务写入并提交。**绝不「前端成功后单独写」**——只有服务端持有评分依据，前端不得回传分数。

- quiz：`load_quiz` 取归档 → 服务端判分 → `db.add_all(quiz_attempts 行)` → `commit` → 返回 `attempt_id`。
  单一事务保证「判分即落库」。
- practice：`judge_submission` 返回后写 `practice_attempts` 并返回 `attemptId`。

**幂等**：客户端铸 `attempt_id`（UUID v4）+ `UNIQUE(attempt_id[, question_id])`。
网络重试命中唯一约束时返回已存记录而非重复插入。多次主动重做（重考）是合法事件，
用**新 `attempt_id`** 区分，二者不矛盾。

---

## 7. 分期里程碑与验收

### M1：最小可观察闭环（quiz 单信号）
- 扩展 `grade`：服务端判 single + 落 `quiz_attempts`；迁移 `learning_profile_v1`。
- 新增 `/api/v1/profile`，仅聚合 quiz 掌握度（无练习、无 LLM 建议）。
- 最小 `/student/portrait` 页：掌握度条 + 「样本不足」空态。
- **验收**：离线 Mock 走完「组卷→作答→判分→画像」；画像数值与归档判分逐题一致（断言验证，
  禁止伪造）；`graded=false` 不计分母；空画像不报假分；`tests/test_migrations.py` 空库升级 + 旧库升级通过。

### M2：练习信号 + 跨信号聚合
- `submit` 落 `practice_attempts`（解析 knowledge_tags）；画像加入 practice_stats、练习通过率。
- quiz 知识点（自由文本）与练习标签（短标签）**分开展示**（合并留到有映射表后）。
- **验收**：judge 通过/失败都在画像反映；隐藏测试内容不落库。

### M3：建议文案 + 时间线 + 跳转
- 规则模板先算强弱项/建议 → LLM 可选润色 → Mock 回退模板；按周时间线；
  画像→测验（学习模块内，带 `knowledge_point+session_id`）/画像→练习（复用 `navigateToPractice`）。
- **验收**：断网/无 Provider 时建议仍来自规则模板且不含伪分数；
  `npm run lint` + `npx tsc --noEmit` + `npm run build` 全过；无 effect 内 setState。

### 留到用户系统阶段
真实 `user_id` 生成与认证、`profile_id→user_id` 映射表、历史回填、跨设备、删除/导出权、
教师端/班级聚合（非目标）。

---

## 8. 风险清单

| # | 风险 | 缓解 |
| --- | --- | --- |
| 1 | `reference_score`（AI 表达质量）误当正确性 | 只取 `practice_attempts` 的 judge 结果；单测断言 `reference_score` 不进掌握度 |
| 2 | 单选客户端判分致 quiz_attempts 缺 single | M1 改服务端确定性判分 |
| 3 | quiz 自由文本 vs 练习短标签词汇不一致 | MVP 分开展示；无映射表前禁止合并编造 |
| 4 | 重键 session/learner_id 破坏历史 | 叠加 `profile_id`，旧键不动，不回填 |
| 5 | 画像端点被误当授权查询/越权 | 对齐 `/records` 语义：无鉴权、只按请求 key 过滤，文档注明 |
| 6 | 迁移编号混乱、改错 head | `down_revision="research_submission_profile_v1"` + 描述性 slug + 双库升级验证 |
| 7 | 独立 sqlite 继续膨胀 | 不新增该 sqlite schema；新判题信号进共享 Alembic 库 |
| 8 | 网络重试重复落库 | `attempt_id` + `UNIQUE` 约束 |
| 9 | effect 内 setState 触发质量门 | `key` 重挂载 + 事件处理器重置 |
| 10 | LLM 建议越权编造分数/事实 | LLM 只润色规则已算好的 bullet；断言建议不含分数变化 |
| 11 | 「自动评分/自适应推荐」越界（scope.md 非目标） | 只做展示性掌握度 + 规则建议，不做自动推荐闭环 |
| 12 | 画像→练习跳转绕过 context-transfer | 复用 `navigateToPractice`；若携带薄弱点进练习则走 `context_transfer` 确认流 |

---

## 9. 铁律落实

### 9.1 尽量参考 OpenMAIC（已逐文件核对）
- **直接移植**：`QuestionResult{questionId, correct, earned, status}` 形状、
  `arraysEqual/toArray`（`lib/quiz/grading.ts`）、`correct/total/pct` 聚合模型
  （`lib/classroom/complete-summary.ts`）→ 作为掌握度公式。
- **参考但不照搬**：`persistence.ts` 的 localStorage 三键生命周期（已决定服务端化）；
  quiz-player 单选题客户端判分（改服务端化）；quiz-generator（本仓库已有服务端组卷）。
- **必须自建**：服务端权威 attempt 持久化、画像聚合服务、统一 profile 键、未来 user 映射。
- **冲突取舍（不移植）**：OpenMAIC `app/api/quiz-grade/route.ts` 从客户端接收 `points` +
  `commentPrompt`，且解析失败回退 `score = round(points*0.5)`——这是「判分标准客户端提交 +
  伪造分数」双重反模式，违反本仓库铁律 3，**不移植**。保持本仓库 `grade_quiz` 的
  服务端加载 rubric + 诚实 mock（`graded=false`）。

### 9.2 用户系统预留
见第 3 节：加可空 `user_id` 列 + 统一 `profile_id` 聚合键，旧键保留，
映射表/回填/删除权留到 auth 阶段。`NotebookItemModel.user_id="poc-user"` 是未来真实账号列占位，
新表沿用同列名即对齐。

### 9.3 开发约束对照（要点）
- 事实边界：画像数值只来自真实持久化分数；`graded=false`/样本不足 → `mastery=null`；
  不用 `reference_score` 当正确性；LLM 仅润色。
- 服务端权威：评分依据从归档 quiz 服务端加载，请求只带 id+提交；single 也改服务端判分；
  归档缺失/跨会话 404（既有 `load_quiz` 行为保持）。
- 会话隔离：画像按请求方 `profile_id` 过滤，与 `/records` 同语义（匿名、非授权）。
- 数据库变更：新 Alembic revision，不改写已发布 revision；验证空库升级、旧库升级、数据保留；
  练习判题信号进共享 Alembic 库，不动独立 sqlite。
- 最小闭环：M1 只做 quiz 单信号 + 画像端点，先跑通再补分层/LLM/时间线。
- 只改受影响内容：新增 `learning_profile` 模块（职责真实新增），不建平行目录。
- 前端质量门：lint / tsc --noEmit / build；`key` 重挂载而非 effect setState。
- 打包资源：本特性无新增运行时资源文件（prompt 在源码内），不触发 package-data；加资源再加 wheel 断言。
- 文档归属：实现后接口/身份键进 `system.md`，产品边界进 `scope.md`。
- 跨模块上下文：画像→练习复用 `navigateToPractice`；升级为「薄弱点带入组题」走 `context_transfer` 确认流。

---

## 10. 实施文件改动清单（供参考，按 M1→M3）

后端：
- 新增 `src/code_navi/learning_profile/`（`__init__.py`、`models.py`、`schemas.py`、
  `service.py`、`router.py`），并在 `src/code_navi/server.py` 注册路由。
- 改 `src/code_navi/learning/quiz/schemas.py`（GradeRequest 增 `attempt_id`/`profile_id`；
  GradeResponse 增 `attempt_id`；StudentAnswerItem 允许 single）。
- 改 `src/code_navi/learning/quiz/services.py`（`grade_quiz` 服务端判 single + 落 `quiz_attempts`）。
- 改 `src/code_navi/online_compiler/application.py`（`submit` 落 `practice_attempts` +
  解析 knowledge_tags）。
- 新增 `migrations/versions/<slug>_learning_profile_v1.py`（`down_revision="research_submission_profile_v1"`）。

前端：
- `frontend/lib/api/quiz.ts`、`frontend/lib/api/learning.ts`：`gradeQuizAnswers` 增 `profile_id`/attempt_id。
- 新增 `frontend/lib/api/profile.ts` + `frontend/app/(student)/portrait/page.tsx`。
- 学习页判分调用处（`QuizView.tsx` 经 learning.ts）读取并传 `profile_id`（复用 `getLearnerId()`）。

测试：
- `tests/test_migrations.py`（空库/旧库升级）、`tests/test_learning_module.py`（quiz 判分落库）、
  `tests/online_compiler/`（submit 落库）、新增 `tests/test_learning_profile.py`（画像聚合、
  样本不足、graded=false 不计、无伪分数）。
