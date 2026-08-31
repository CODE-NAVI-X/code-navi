# 科研端 LLM 内容生成设计

日期：2026-08-28
基线：`code-navi-b-research-downstream-local` @ `f494c21`（main + 上游质量 + 下游质量）
分支：`codex/research-llm-ui-local`（本地，隔离 worktree，不推送远程）

## 1. 问题

科研侧多个面板由规则模板拼出"看起来通用"的建议：

- 方向/论文难点分析：回显画像中的研究问题，再拼固定句式；
- 实验方案：把研究计划的字段直接复制为方案；
- 实验代码草案：服务端固定模板，模型只能改标题；
- 复现方案 / 论文蓝图 / 审稿：证据不足时产出大量通用待办；
- LLM 失败时以 `rules_fallback` 静默降级为规则模板并照常展示。

这些内容与当前会话、画像、已保存证据脱节，且无来源与 `fact/inference/to_verify` 边界。

## 2. 目标

- 科研建议内容由 LLM 基于已校验上下文生成，并校验来源边界；
- 不再默认展示规则模板建议；删除 `rules_fallback` 规则建议展示；
- LLM 不可用/超时/非法输出 → 明确失败状态 + 可重试，不静默降级；
- 不覆盖上一次成功的 LLM 结果；刷新后上一次成功结果可恢复；
- 规则程序继续负责：状态机、权限确认、输入校验、Evidence 归属、身份关系、
  `fact/inference/to_verify` 与 `source_scope` 校验、持久化、完成状态、错误处理；
- 不执行代码、不写用户项目、不联网；Provider 走现有配置/审计链路。

## 3. 非目标

- 不实现论文精读卡；不读全文；不运行实验；不生成可执行脚本；
- 不引入外部网络搜索；不修改学习/编译等无关模块；
- 不推送远程、不开 PR、不改动主工作区受保护文件。

## 4. 总体架构

新增 `src/code_navi/research/research_generation.py`：

- `ResearchGenerationError(stage, detail)`，`stage ∈ {provider_unavailable, timeout, invalid_output, failed}`；
- `require_generated_artifact(outcome, kind)`：把 `ArtifactLlmOutcome` 归一化为
  成功 JSON 文本或抛出 `ResearchGenerationError`（unavailable→provider_unavailable，
  含 timeout→timeout，其余→failed，空文本→failed）。

每个生成器统一模式：

1. `generator is None` → `raise ResearchGenerationError("provider_unavailable", ...)`；
2. `generator.generate(kind=..., conversation_id=..., context={已校验画像/计划/所选论文元数据/实验记录/来源边界/required_json_shape})`；
3. `text = require_generated_artifact(outcome, kind)`；
4. `Model.model_validate_json(text)` + 自定义 `_validate_generated_*` 边界校验
   （不得新增 `fact`；`source_scope` 属于允许集合；证据引用必须属于已保存 bundle；
   身份字段 conversation_id / paper url / title 不得被改写），失败 →
   `raise ResearchGenerationError("invalid_output", ...)`；
5. 成功 → `model_copy(update={generation_mode:"llm", run_id, event_count, provenance_note: 固定文案})`。

规则保留的确定性职责：身份重盖（selected_paper 由服务端以真实 paper 重建）、
用户实验记录与任务的关联（`_task_links`/`evidence_linked`）、`fact` 边界、持久化。

### 涉及的生成器

| 面板 | 函数 | 改造 |
| --- | --- | --- |
| 方向难点分析 | `build_topic_difficulty_analysis` | LLM 必需；失败抛错；保留边界校验 |
| 论文难点分析 | `build_paper_analysis` | 同上；论文身份/范围由规则校验 |
| 实验方案 | `build_experiment_design` | LLM 必需；失败抛错 |
| 实验代码草案 | `build_experiment_code_draft` | 移除固定模板，LLM 生成预览（阻断密钥/执行原语） |
| 复现方案 | `build_reproduction_pipeline` | LLM 必需；规则重建论文身份、关联用户证据、校验 fact/scope/task_id |
| 论文蓝图 | `build_paper_blueprint` | LLM 必需；规则校验可引用来源集合与 fact 边界 |
| 审稿 | `build_rules_paper_review` / `_enhance_review` / 改写建议 | 失败抛错，删除 `rules_fallback` |

## 5. 编排与持久化

- `ResearchConversationModel` 新增 `generated_artifacts`（JSON，可空），持久化
  上一次成功的 `topic_difficulty_analysis` 与 `experiment_design`；新增 Alembic
  revision `0019_research_generated_artifacts`（down_revision=`auth_csrf_learning_records_v1`）。
- `generate_topic_difficulty_analysis` / `generate_experiment_design`：成功后写入
  `generated_artifacts` 并提交；失败时抛出且不改动已存结果。
- `_to_response`：恢复时返回已存的上一次成功分析（或 `None`），不再现场构建规则模板。
  `ResearchConversationResponse.topic_difficulty_analysis` 改为可空。
- 复现 Pipeline、实验/学术证据、论文草稿/审稿/修订继续按行持久化；失败在 `db.add`
  之前抛出，既有行不被覆盖。
- `router.py` 新增 `_raise_generation_error`：`provider_unavailable`/`timeout`→503
  （`Retry-After` 提示重试），`invalid_output`→502，`failed`→502；detail 不泄露密钥/堆栈。

## 6. 前端

- 移除 `rules_fallback` 的"规则降级"展示；改为明确失败提示 + 重试按钮；
- 失败时保留并标注上一次成功结果；默认不显示规则模板建议；
- 字体/布局可读性：正文 16–18px、说明≥12px、卡片标题 18–20px、面板标题 22–26px、
  页面标题 36–44px、行高正文≥1.65/标题1.7–1.8；移除重要信息的 10/11px；阅读宽度居中；
  当前阶段置顶；深浅色可读。

## 7. 测试策略（TDD，Fake Provider，无网络）

对每个生成器覆盖：

- 无 Provider（generator None / unavailable）→ `provider_unavailable`，无规则建议；
- 超时 → `timeout`；空输出/非 JSON → `failed`/`invalid_output`；
- 非法 JSON、缺字段、模型把 `to_verify` 提升为 `fact`、引用保存之外的 Evidence、
  改写身份 → `invalid_output`；
- 成功路径：prompt 含画像/计划/所选论文元数据/实验记录/来源边界；结果为 llm 且可序列化；
- 持久化：成功后恢复可见上一次成功结果；失败不覆盖；
- 路由：失败 → 503/502 + 可重试；成功 → 200。

## 8. 验证与交付

- `pytest` 定向 + 科研相关回归；`ruff check`；前端 `lint`/`tsc`/`build`；
  `git diff --check`；环境允许时浏览器冒烟（否则明确记录未跑真实 Provider）；
- 本地提交，不推送、不开 PR；交付报告含无远程写入声明。
