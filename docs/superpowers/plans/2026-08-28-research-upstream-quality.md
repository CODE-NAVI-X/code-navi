# Research Upstream Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a complete first research request reliably reach the existing explicit-search handoff and return deterministic, deduplicated original-paper-first evidence bundles.

**Architecture:** Keep the `ResearchProfile` and its rule fallback as the only completion authority, and derive all plan/search eligibility from one readiness predicate. Normalize, merge, classify, and rank records in `AcademicSearchTool` after each allowed source returns metadata; assign bundle-scoped paper identifiers only after `ResearchConversationSearchService` persists the bundle record.

**Tech Stack:** Python 3.13, Pydantic, SQLAlchemy, FastAPI, pytest, Ruff.

---

### Task 1: Shared profile readiness and complete-first-turn extraction

**Files:**

- Modify: `src/code_navi/research/conversation_schemas.py:30-100`
- Modify: `src/code_navi/research/conversation_service.py:1305-1570`
- Modify: `src/code_navi/research/conversation_search_service.py:40-95`
- Test: `tests/test_research_conversation.py`
- Test: `tests/test_conversation_search.py`

- [ ] **Step 1: Write the failing profile-regression tests**

Add five parametrized complete Chinese research requests to `tests/test_research_conversation.py`. For each, use the rules fallback and assert that one message yields a profile with non-empty topic, question, method, data requirement, metric, resource constraint, and time scope; assert `readiness.stage == "ready_for_plan"`, `readiness.can_prepare_search is True`, and that the assistant does not repeat a topic/question prompt. Include expressions using “研究…”, “拟以…为题”, “课题聚焦…”, “计划比较…”, and “希望评估…”.

Add a direct readiness test using a profile with only topic and question. Its expected result is `can_prepare_search is False` while `stage != "ready_for_plan"`; this is the existing contradiction.

Add a `tests/test_conversation_search.py` test that creates a one-turn complete rules-fallback conversation, calls `GET /search-plan`, and asserts `200` without the fake source being called.

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_research_conversation.py tests/test_conversation_search.py -q
```

Expected: the new complete-input cases fail because the fallback only extracts methods/data after a prior dialogue turn, and the contradiction test fails because the current predicate accepts topic plus question before the profile is plan-ready.

- [ ] **Step 3: Write minimal implementation**

Add `metrics: list[str]` to `ResearchProfile` and `ResearchProfilePatch`, including list normalization and the `ProfileField` literal. In `_fallback_patch`, use bounded label/verb patterns to extract topic, question, context, method, data/dataset, metric, resource/time constraints, and expected output from one message; preserve existing explicit clear/reframe behavior and never manufacture values absent from the input.

Change `assess_readiness` so `can_prepare_search` is true exactly when its score has reached `ready_for_plan`; use `can_prepare_search` in response construction, plan construction, decision enforcement, fallback transition, and `ResearchConversationSearchService.plan`. This leaves search execution behind the existing explicit POST and preserves rule/model fallback behavior.

- [ ] **Step 4: Run test to verify GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_research_conversation.py tests/test_conversation_search.py -q
.venv\Scripts\python.exe -m ruff check src/code_navi/research/conversation_schemas.py src/code_navi/research/conversation_service.py src/code_navi/research/conversation_search_service.py tests/test_research_conversation.py tests/test_conversation_search.py
```

Expected: all selected tests pass; no Ruff diagnostics.

- [ ] **Step 5: Commit**

```powershell
git add src/code_navi/research/conversation_schemas.py src/code_navi/research/conversation_service.py src/code_navi/research/conversation_search_service.py tests/test_research_conversation.py tests/test_conversation_search.py
git commit -m "feat(research): unify search readiness"
```

### Task 2: Metadata-only original-paper ranking and deterministic deduplication

**Files:**

- Modify: `src/code_navi/research/academic.py:35-370`
- Modify: `src/code_navi/research/schemas.py:50-85`
- Test: `tests/test_academic_evidence.py`

- [ ] **Step 1: Write the failing GCN result test**

Add fixed `PaperMetadata` records from fake allowed sources: Kipf/Welling’s “Semi-Supervised Classification with Graph Convolutional Networks” as arXiv and formal DOI records, a GCN survey, and a later GCN application. Search for `GCN Cora Kipf Welling semi-supervised classification` and assert that the retained original paper is within the first three, appears once despite arXiv/formal duplication, has `paper_kind` classified as `original_paper` with `classification == "inference"`, and leaves Accuracy/data split/resources/reproduction conclusion in `verification` with `classification == "to_verify"`.

Add direct tests for DOI normalization, normalized-title fallback, and arXiv/formal title association. Use no live clients.

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_academic_evidence.py -q
```

Expected: the original/formal duplicate remains twice and no `paper_kind` or deterministic ranking contract exists.

- [ ] **Step 3: Write minimal implementation**

Add narrow private helpers in `academic.py`: normalized DOI, title token normalization, arXiv extraction, author/query matching, paper-kind inference, duplicate-key selection, and a stable ranking tuple. Merge duplicate records by DOI first, then title, then arXiv/formal title association; retain the best available metadata/abstract and deterministic URL/source tie-breakers. Add `paper_kind` as an inferred evidence statement to `AcademicPaperResult`.

Score title match, author tokens, year plausibility, query-keyword coverage, and paper kind; sort by descending score with normalized title and URL as deterministic final ties. Do not use full text, add sources, or label the inferred kind as fact.

- [ ] **Step 4: Run test to verify GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_academic_evidence.py -q
.venv\Scripts\python.exe -m ruff check src/code_navi/research/academic.py src/code_navi/research/schemas.py tests/test_academic_evidence.py
```

Expected: all academic-evidence tests pass and Ruff reports no diagnostics.

- [ ] **Step 5: Commit**

```powershell
git add src/code_navi/research/academic.py src/code_navi/research/schemas.py tests/test_academic_evidence.py
git commit -m "feat(research): rank original academic sources"
```

### Task 3: Persisted bundle and paper identity contract

**Files:**

- Modify: `src/code_navi/research/schemas.py:55-85`
- Modify: `src/code_navi/research/conversation_search_service.py:70-125`
- Test: `tests/test_conversation_search.py`

- [ ] **Step 1: Write the failing persisted-identity test**

Extend the explicit conversation-search test to save a deterministic bundle, assert every paper has a non-empty `paper_id`, then restore the bundle and assert identical `bundle_id`, `paper_id`, DOI/arXiv metadata, information scope, and `fact`/`inference`/`to_verify` classifications. Assert no source is invoked on restore.

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_conversation_search.py -q
```

Expected: saved papers have no stable bundle-scoped `paper_id`.

- [ ] **Step 3: Write minimal implementation**

Add optional `paper_id` to `AcademicPaperResult`. After `ResearchConversationSearchService.search` flushes the bundle record, assign each paper a UUIDv5 based on the persisted `bundle_id` and its normalized DOI, arXiv identifier, title, or URL. Validate and persist the resulting `ConversationEvidenceBundle`; cached and restored bundles return the persisted identifiers unchanged.

- [ ] **Step 4: Run required local verification**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_research_conversation.py tests/test_research_api.py tests/test_academic_evidence.py tests/test_conversation_search.py -q
.venv\Scripts\python.exe -m ruff check src/code_navi/research/conversation_schemas.py src/code_navi/research/conversation_service.py src/code_navi/research/conversation_search_service.py src/code_navi/research/academic.py src/code_navi/research/schemas.py tests/test_research_conversation.py tests/test_academic_evidence.py tests/test_conversation_search.py
git diff --check
```

Expected: all selected tests pass, Ruff has no diagnostics, and `git diff --check` exits zero.

- [ ] **Step 5: Commit and inspect local history**

```powershell
git add src/code_navi/research/schemas.py src/code_navi/research/conversation_search_service.py tests/test_conversation_search.py
git commit -m "feat(research): persist evidence paper identities"
git log --oneline main..HEAD
git status --short
```

### Task 4: Requirements review before reporting

**Files:**

- Verify only: changed files and the three protected main-worktree paths

- [ ] **Step 1: Recheck each requirement against the implementation**

Confirm the five one-turn prompts, GCN top-three/dedup scenario, explicit-only network dispatch, bundle/paper restoration, and all epistemic labels with the task-specific tests.

- [ ] **Step 2: Record verification boundaries accurately**

State the isolated worktree, branch, commits, commands/results, the local environment dependency installation, any unrun full suite/build/browser checks, and that no fetch, pull, push, PR operation, remote write, or protected-main-file modification occurred.
