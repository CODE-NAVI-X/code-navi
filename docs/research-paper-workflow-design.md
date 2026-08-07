# 论文生产闭环：后续接口边界（未实现）

当前已经实现 `experiment-evidence.v1` 与 `paper-blueprint.v1`。以下对象只定义后续边界，当前没有路由、持久化实现、导出或自动化行为。

| 后续对象 | 预留输入/输出 | 计划路由边界 | 明确不做 |
| --- | --- | --- | --- |
| `PaperDraft` | 用户主动粘贴的 Markdown/纯文本初稿、版本和来源范围 | `POST /conversations/{id}/paper-drafts` | 不自动生成全文、不读取本地文件 |
| `PaperReview` | 结构、证据、逻辑、表达、引用的结构化审阅 | `POST /paper-drafts/{id}/reviews` | 不伪造同行评审、不代替导师 |
| `RevisionTask` | 严重度、依据、建议和处理状态 | `GET/POST /paper-drafts/{id}/revision-tasks` | 不自动改写草稿 |
| `PaperRevision` | 用户确认的版本、diff 和修改理由 | `POST /paper-drafts/{id}/revisions` | 不自动覆盖用户文本 |
| `SubmissionReadiness` | 格式、匿名、伦理、数据声明、引用和事实缺口 | `POST /paper-drafts/{id}/submission-readiness` | 不判断录用概率或投稿资格 |
| 用户导出 | 用户主动导出的 Markdown/DOCX/LaTex 草稿包 | `POST /paper-drafts/{id}/exports` | 不自动写文件或投稿 |

未来每个接口仍须保持：实验事实仅来自 `ExperimentEvidenceBundle`，相关工作仅来自保存的受限 EvidenceBundle，所有推断/待验证项显式标注。不会引入多 Agent、MCP、自动检索、自动运行实验或自动投稿。
