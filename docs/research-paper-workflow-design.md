# Research 论文辅助：当前模块边界

当前已实现 `experiment-evidence.v1`、`paper-blueprint.v1`、`paper-draft.v1`、`paper-review.v1`、`paper-revision.v1`、`submission-readiness.v1` 与 `paper-export.v1` 的本地闭环：用户粘贴 Markdown/纯文本 → 规则优先审稿 → 人工接受或跳过修订任务 → 生成并确认单条候选改写 → 用户主动执行投稿前检查 → 用户主动受控导出 Markdown/JSON。

## 当前对象与接口

公开接口的统一前缀为 `/api/v1/research`；完整 API 事实以 [系统架构](architecture/system.md) 和实际 FastAPI router 为准。

| 对象 | 输入/输出 | 当前路由边界 | 行为 |
| --- | --- | --- | --- |
| `PaperDraft` | 用户主动粘贴的 Markdown/纯文本初稿、版本和来源范围 | `POST /api/v1/research/conversations/{id}/paper-drafts` | 保存用户提供的初稿 |
| `PaperReview` | 结构化审阅与可处理的 RevisionTask | `POST /api/v1/research/paper-drafts/{id}/reviews` | 用户主动生成规则优先审稿 |
| `RevisionTask` | 严重度、依据、建议和处理状态 | `PATCH /api/v1/research/paper-reviews/{id}/revision-tasks/{task_id}` | 只记录用户接受或跳过决定 |
| `RevisionSuggestion` | 单个已接受任务的候选段落 | `POST /api/v1/research/paper-reviews/{id}/revision-tasks/{task_id}/suggestions` | 用户主动生成候选，不修改原稿 |
| `PaperRevision` | 用户确认的候选文本、diff 和修改理由 | `POST /api/v1/research/revision-suggestions/{id}/apply` | 用户接受或编辑候选后创建新版本 |
| `SubmissionReadiness` | 匿名、伦理、数据、引用和事实缺口 | `POST /api/v1/research/paper-drafts/{id}/submission-readiness` | 用户主动运行本地检查 |
| 用户导出 | Markdown 与 JSON 辅助包 | `POST /api/v1/research/paper-drafts/{id}/export-package` | 用户主动生成返回内容 |

原 `POST /api/v1/research/paper-reviews/{id}/revisions` 批量修订入口已经退役并返回 409；当前流程必须先接受单条 RevisionTask，再生成并确认对应 RevisionSuggestion。

## 与持久工作区的关系

ResearchConversation 及其 Evidence、Draft、Review 和 Revision 继续是模块产物的事实来源。Research 接入持久工作区后，Activity 只索引这些已保存结果的引用和安全摘要，Workspace 或 Task 不接管原始论文产物。

## 边界与限制

实验事实只来自 `ExperimentEvidenceBundle`，相关工作只来自当前 ResearchConversation 已保存的受限 EvidenceBundle，推断与待验证项保持显式标注。当前流程不上传 DOCX/PDF，不自动生成论文全文，不读取本地文件，不引入多 Agent 或 MCP，也不自动检索、运行实验、写文件或投稿。导出只返回用户主动请求的 Markdown 与 JSON 辅助包；ZIP、DOCX、PDF 与 LaTeX 留待独立能力验证。
