# 学情画像当前架构

## 1. 当前职责

学情画像聚合一个匿名 profile 的真实 QuizAttempt 与 ConfusionMark；复盘投影额外聚合权威 PracticeOutcome。它提供跨学习会话的掌握度摘要、待复习位置和可追溯知识缺口，不承担账号、授权、Workspace 所有权或自动推荐。

实现位于：

```text
src/code_navi/learning_profile/
src/code_navi/learning/quiz/
src/code_navi/online_compiler/
frontend/app/(student)/portrait/
frontend/lib/api/profile.ts
migrations/versions/0013_learning_profile_v1.py
migrations/versions/0014_learning_profile_v2.py
migrations/versions/0016_practice_launch_outcomes.py
```

## 2. 当前事实来源

| 来源 | 当前持久化 | 画像用途 |
| --- | --- | --- |
| QuizAttempt | 共享 SQLAlchemy/Alembic 数据库的 `quiz_attempts` | 仅聚合 `graded=true` 的服务端评分结果 |
| ConfusionMark | 共享数据库的 `confusion_marks` | 展示用户主动标记且当前状态为 confused 的位置 |
| PracticeOutcome | 共享数据库的 `practice_outcomes` | 错误答案、编译错误与运行错误进入可追溯复盘投影 |
| Practice CompilerRecord | 独立 SQLite `learning_records` | 兼容记录，不进入画像或复盘投影 |
| Practice Submission | 进程内存中的限时上下文 | 兼容判题上下文，不是复盘事实来源 |

Quiz 评分依据由服务器从同一 `session_id` 的归档 Quiz 加载。客户端提交答案和幂等 attempt ID，不提交 score、correct 或评分标准。单选题由规则确定性评分；模型评分和离线未评分状态通过 `graded_by`、`is_mock` 与 `graded` 保留来源边界。

ConfusionMark 记录知识点、来源表面、来源引用、显示标签、状态和学习会话。画像按最新有效状态聚合，不把“懂了”操作删除成没有历史。

## 3. 标识与范围

| 标识 | 作用 |
| --- | --- |
| 学习 `session_id` | 隔离归档 Quiz、Notebook 与标记写入范围 |
| `profile_id` | 跨学习会话聚合 QuizAttempt 与 ConfusionMark |
| Practice `learner_id` | 当前与 `profile_id` 使用同一个 UUID 值 |
| `local_profile_id` | 隔离 Workspace、Task、Activity 与 PracticeOutcome；复盘查询用它约束 Practice 来源 |
| `user_id` | QuizAttempt 与 ConfusionMark 中的可空账号预留列；当前不提供账号语义 |

前端复用 `code-navi-compiler-learner-id` 中的 UUID 作为 `profile_id / learner_id`。`GET /api/v1/profile` 按该 UUID 过滤；`GET /api/v1/learning/knowledge-gaps` 同时接收 `local_profile_id` 与 `profile_id`，对 PracticeOutcome 使用两者约束。它们是匿名本地查询键，不是授权凭据。

## 4. 聚合边界

1. 掌握度只使用已持久化且 `graded=true` 的 QuizAttempt。
2. 样本量低于阈值时返回 `mastery=null` 与样本不足状态，不显示伪百分比。
3. 待复习位置只使用当前有效的 ConfusionMark，并保留 PPT、讲解和 Quiz 等来源表面。
4. Practice 的 AI `reference_score` 评价代码表达质量，不表示题目正确性，不进入掌握度。
5. 当前没有独立 KnowledgeGap 表；KnowledgeGap 是三类权威来源的只读投影，不复制事实记录。
6. Practice 复盘不读取或返回源码、stdin、隐藏测试、raw stdout 或 raw stderr；服务故障不归因于用户。

## 5. 当前接口

| 接口 | 行为 |
| --- | --- |
| `POST /api/v1/learning/quiz/grade` | 服务端评分并幂等写入 QuizAttempt |
| `POST /api/v1/learning/marks` | 写入或清除 ConfusionMark |
| `GET /api/v1/profile?profile_id=...` | 返回该匿名 profile 的当前画像 |
| `GET /api/v1/learning/knowledge-gaps?local_profile_id=...&profile_id=...` | 返回 QuizAttempt、ConfusionMark 与 PracticeOutcome 的有界可追溯投影 |

未知 profile 返回空画像。跨 `session_id` 的 Quiz 读取保持 404；画像查询的跨会话聚合不改变 Notebook 的会话隔离。

## 6. Practice 集成现状

Practice 进入 Learning 后，画像与复盘按 [Practice 集成进 Learning 决策](../decisions/practice-in-learning-experience.md) 接收权威 PracticeOutcome。KnowledgeGap 将 QuizAttempt、ConfusionMark 和 PracticeOutcome 投影为保留来源的复盘项；系统故障、前端声明和 AI 表达质量分不进入知识缺口。

QuizAttempt 与 ConfusionMark 的现有表没有 `local_profile_id`，因此这两类继续按 `profile_id` 聚合；PracticeOutcome 同时按 `local_profile_id` 与 `learner_id` 过滤。账号授权与跨设备身份合并仍由后续身份系统处理。
