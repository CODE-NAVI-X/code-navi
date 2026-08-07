# 论文生产闭环：本地已实现边界与后续接口

当前已实现 `experiment-evidence.v1`、`paper-blueprint.v1`、`paper-draft.v1`、`paper-review.v1` 与 `paper-revision.v1` 的本地闭环：用户粘贴 Markdown/纯文本 → 规则优先审稿 → 人工接受/跳过修订任务 → 不覆盖原稿的修订预览与 diff。它不上传 DOCX/PDF、不自动联网、不写入项目、不自动投稿；审稿意见始终是建议。

| 后续对象 | 预留输入/输出 | 计划路由边界 | 明确不做 |
| --- | --- | --- | --- |
| `PaperDraft` | 用户主动粘贴的 Markdown/纯文本初稿、版本和来源范围 | `POST /conversations/{id}/paper-drafts` | 已实现；不自动生成全文、不读取本地文件 |
| `PaperReview` | 结构、证据、逻辑、表达、引用的结构化审阅 | `POST /paper-drafts/{id}/reviews` | 已实现；不伪造同行评审、不代替导师 |
| `RevisionTask` | 严重度、依据、建议和处理状态 | `PATCH /paper-reviews/{id}/revision-tasks/{task_id}` | 已实现；不自动改写草稿 |
| `PaperRevision` | 用户确认的版本、diff 和修改理由 | `POST /paper-reviews/{id}/revisions` | 已实现；不自动覆盖用户文本 |
| `SubmissionReadiness` | 格式、匿名、伦理、数据声明、引用和事实缺口 | `POST /paper-drafts/{id}/submission-readiness` | 不判断录用概率或投稿资格 |
| 用户导出 | 用户主动导出的 Markdown/DOCX/LaTex 草稿包 | `POST /paper-drafts/{id}/exports` | 不自动写文件或投稿 |

未来每个接口仍须保持：实验事实仅来自 `ExperimentEvidenceBundle`，相关工作仅来自保存的受限 EvidenceBundle，所有推断/待验证项显式标注。不会引入多 Agent、MCP、自动检索、自动运行实验或自动投稿。
