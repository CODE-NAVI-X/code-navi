# 科研端 LLM 内容生成实施计划

日期：2026-08-28
设计：`docs/design/2026-08-28-research-llm-generation-design.md`

## Phase 0 — 基线与文档
- [x] 创建隔离 worktree `code-navi-research-llm-ui-local` / `codex/research-llm-ui-local` @ `f494c21`
- [x] 写设计与计划文档

## Phase 1 — 失败契约
- [x] `research_generation.py`：`ResearchGenerationError` + `require_generated_artifact`

## Phase 2 — 生成器 LLM 化（TDD）
- [x] `conversation_difficulty.py`（topic + paper）
- [x] `conversation_experiment.py`
- [x] `conversation_code_draft.py`（移除固定模板）
- [x] `conversation_reproduction.py`
- [x] `conversation_paper_blueprint.py`
- [x] `conversation_paper_review.py`（删除 rules_fallback）

## Phase 3 — 编排 / 持久化 / 路由 / 契约
- [x] `models.py`：`generated_artifacts` JSON 列
- [x] Alembic `0019_research_generated_artifacts`
- [x] `conversation_service.py`：生成器接线、上次成功持久化、恢复路径、失败不覆盖
- [x] `conversation_schemas.py`：`topic_difficulty_analysis` 可空
- [x] `router.py`：`_raise_generation_error` + 各端点错误映射

## Phase 4 — 测试
- [x] 新增 `tests/test_research_generation_llm.py`、`tests/research_llm_fakes.py`
- [x] 更新受影响既有测试（rules_fallback 断言、无 generator 调用、前端文案断言）

## Phase 5 — 前端
- [x] 失败态 + 重试 + 上次成功保留；移除 rules_fallback 展示
- [x] 字体/布局可读性（主要建议面板字号/行高提升、全局 16px/1.65 基线）

## Phase 6 — 验证与交付
- [x] pytest（663 通过；仅 2 个与本任务无关的预存在环境失败）/ ruff / 前端 eslint、tsc、build / git diff --check
- [x] 本地提交 + 交付报告（含无远程写入声明；真实 Provider 未运行，浏览器冒烟见报告）
