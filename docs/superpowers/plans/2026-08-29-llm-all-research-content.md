# 科研端全内容 LLM 生成实施计划

> **For agentic workers:** Execute this plan inline with test-first checkpoints; all work remains local.

**Goal:** Replace user-visible rule-generated welcome and research-plan prose with persisted, validated LLM output while retaining rule-controlled state and evidence boundaries.

**Architecture:** Reuse the existing `ResearchArtifactGenerator` boundary for a new `research_plan` artifact. The conversation service generates it only after a user-triggered turn reaches readiness, persists the validated artifact in `generated_artifacts`, and restores it on GET. A missing provider or invalid result is surfaced as a typed generation error; no rule text is returned as a visible substitute. Existing deterministic plan helpers remain internal context builders for downstream prompts.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy JSON persistence, AgentRuntime, pytest, TypeScript/Next.js.

---

### Task 1: Add the LLM research-plan contract

**Files:**
- Modify: `src/code_navi/research/conversation_schemas.py`
- Modify: `src/code_navi/research/conversation_plan.py`
- Test: `tests/test_research_generation_llm.py`

- [ ] Add `generation_mode`, `run_id`, and `event_count` fields to `ConversationResearchPlan` with safe defaults for existing internal fixtures.
- [ ] Add a `build_llm_research_plan(...)` function that sends profile plus deterministic context to the artifact generator, validates `ConversationResearchPlan`, forces `generation_mode="llm"`, and raises `ResearchGenerationError` on unavailable/invalid output.
- [ ] Test valid, unavailable, and invalid plan output with a deterministic artifact generator.

### Task 2: Persist and restore only LLM plans in conversational responses

**Files:**
- Modify: `src/code_navi/research/conversation_service.py`
- Modify: `src/code_navi/research/router.py`
- Test: `tests/test_research_generation_llm.py`

- [ ] Generate and persist a plan after a user-triggered conversation turn becomes search-ready.
- [ ] Make `_to_response` read the persisted LLM plan and return `None` when no generated plan exists; do not construct visible rule prose.
- [ ] Catch typed generation errors in conversation create/send routes and return the existing structured 503/422 contract.
- [ ] Test persistence, refresh restoration, and no-template failure behavior.

### Task 3: Route the empty-session welcome through the conversation model

**Files:**
- Modify: `src/code_navi/research/conversation_service.py`
- Modify: `src/code_navi/research/conversation_agent.py`
- Test: `tests/test_research_generation_llm.py`

- [ ] Add a model-generated welcome request using the existing decision schema and runtime audit metadata.
- [ ] Persist the model decision as `generation_mode="agent"`; when unavailable, return a structured generation error instead of the current fixed welcome text.
- [ ] Test model welcome and provider failure without network access.

### Task 4: Align visible labels and verify

**Files:**
- Modify: `frontend/components/research/ResearchPlanPanel.tsx`
- Modify: `frontend/components/research/ResearchConversation.tsx`
- Test: `tests/test_research_frontend_copy.py`

- [ ] Replace “规则研究计划” copy with a model-generated label and show the persisted run metadata.
- [ ] Keep fact-boundary warnings and explicit retry/error semantics.
- [ ] Run targeted pytest, Ruff, frontend lint, TypeScript, build, and `git diff --check`.
