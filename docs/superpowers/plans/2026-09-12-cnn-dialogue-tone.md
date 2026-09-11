# CNN Dialogue Tone and Direction Follow-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the public CNN research dialogue warmer and more conversational, add a clarification step for the broad explainability option, and keep all existing research-safety gates unchanged.

**Architecture:** Keep the deterministic CNN state machine and persisted answer schema. Change only user-facing copy and add one explicit `direction_focus` question after the broad option D; the collected focus is stored as part of the direction answer so query/provenance interfaces remain compatible.

**Tech Stack:** Python, pytest, existing Code Navi research orchestrator and SQLite test fixtures.

---

### Task 1: Lock the desired dialogue behavior with tests

**Files:**
- Modify: `tests/test_research_cnn_flow.py`

- [ ] Add tests that require a small number of natural emoticons, explanatory copy, and no implementation labels.
- [ ] Add a test that choosing the broad explainability option asks a focus question before the dataset question.
- [ ] Run the focused tests and confirm they fail against the current implementation.

### Task 2: Implement the minimal dialogue changes

**Files:**
- Modify: `src/code_navi/research/cnn_flow.py`
- Modify: `src/code_navi/research/conversation_orchestrator.py`

- [ ] Update the public CNN copy with warm wording and restrained kaomoji.
- [ ] Add a deterministic focus clarification branch for option D, preserving the existing answer and query fields.
- [ ] Keep paper filtering, provenance, evidence bundles, confirmation gates, stage transitions, and redline logic unchanged.

### Task 3: Verify and hand off

**Files:**
- No additional source files.

- [ ] Run focused CNN tests, full Python tests, TypeScript check, frontend build, Ruff, and `git diff --check`.
- [ ] Restart the local backend from this worktree and open a fresh browser conversation; report login or environment blockers honestly.
- [ ] Create one local commit only; do not push or create a PR.
