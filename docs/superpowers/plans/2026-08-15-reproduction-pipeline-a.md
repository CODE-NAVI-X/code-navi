# Reproduction Pipeline A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a persisted, user-triggered, evidence-bounded `reproduction-pipeline.v1` that links a selected saved paper to existing experiment evidence.

**Architecture:** A rules-only `conversation_reproduction.py` builder converts a validated conversation profile, the selected local EvidenceBundle paper, and saved experiment evidence into a stable Pydantic contract. `ResearchConversationService` owns selection validation and persistence, while a dedicated table stores the serialised Pipeline. The existing `/research` page obtains the Pipeline only through the FastAPI API and its task state remains derived from the existing `related_plan_item` evidence links.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy, Alembic, pytest, Next.js 16, React 19, TypeScript, Tailwind CSS.

---

### Task 1: Define the Pipeline contract and pure rules generator

**Files:**
- Modify: `src/code_navi/research/conversation_schemas.py`
- Create: `src/code_navi/research/conversation_reproduction.py`
- Test: `tests/test_research_reproduction_pipeline.py`

- [ ] **Step 1: Write failing contract tests**

```python
def test_pipeline_marks_abstract_gaps_as_to_verify() -> None:
    pipeline = build_reproduction_pipeline(profile, plan, bundle, paper, [])
    assert pipeline.schema_version == "reproduction-pipeline.v1"
    assert all(item.classification == "to_verify" for item in pipeline.data_and_sample_conditions)
    assert "摘要/元数据未覆盖" in pipeline.data_and_sample_conditions[0].source_scope
```

- [ ] **Step 2: Run the test and verify the expected missing-import failure**

Run: `python -m pytest tests/test_research_reproduction_pipeline.py -q`

- [ ] **Step 3: Add the minimal schemas and pure builder**

```python
class ReproductionPipeline(BaseModel):
    schema_version: Literal["reproduction-pipeline.v1"] = "reproduction-pipeline.v1"
    pipeline_id: str
    conversation_id: str
    source_bundle_id: str
    selected_paper: ReproductionSelectedPaper
    reproduction_goal: ReproductionPipelineItem
    research_question: ReproductionPipelineItem
    known_method: ReproductionPipelineItem
    data_and_sample_conditions: list[ReproductionPipelineItem]
    candidate_baselines: list[ReproductionPipelineItem]
    metrics: list[ReproductionPipelineItem]
    experiment_steps: list[ReproductionPipelineItem]
    resources: list[ReproductionPipelineItem]
    risks: list[ReproductionPipelineItem]
    ethics: list[ReproductionPipelineItem]
    confirmation_items: list[ReproductionPipelineItem]
    tasks: list[ReproductionTask]
    two_week_mvp: list[ReproductionPipelineItem]
    created_at: datetime
    provenance_note: str
```

The builder must use only arguments passed to it; it must not import providers, search services, filesystems, or the compiler.

- [ ] **Step 4: Rerun the focused tests**

Run: `python -m pytest tests/test_research_reproduction_pipeline.py -q`

### Task 2: Persist and restore validated Pipelines

**Files:**
- Modify: `src/code_navi/research/models.py`
- Modify: `src/code_navi/research/conversation_service.py`
- Create: `migrations/versions/0013_reproduction_pipelines.py`
- Modify: `tests/test_migrations.py`
- Test: `tests/test_research_reproduction_pipeline.py`

- [ ] **Step 1: Add failing API/persistence tests**

```python
def test_pipeline_requires_a_saved_selected_paper(client: TestClient) -> None:
    response = client.post(f"/api/v1/research/conversations/{conversation_id}/reproduction-pipelines", json={})
    assert response.status_code == 422

def test_pipeline_persists_and_restores_with_experiment_task_links(client: TestClient) -> None:
    created = _create_pipeline_for_selected_saved_paper(client, conversation_id)
    restored = client.get(f"/api/v1/research/conversations/{conversation_id}/reproduction-pipelines")
    assert restored.json()[0]["pipeline_id"] == created["pipeline_id"]
```

- [ ] **Step 2: Run and confirm RED**

Run: `python -m pytest tests/test_research_reproduction_pipeline.py -q`

- [ ] **Step 3: Add model, revision, and service methods**

```python
class ResearchReproductionPipelineModel(Base):
    __tablename__ = "research_reproduction_pipelines"
    id = Column(String(36), primary_key=True)
    conversation_id = Column(String(36), nullable=False, index=True)
    pipeline_data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False)
```

`create_reproduction_pipeline()` must prove both bundle ownership and exact paper URL membership before calling the pure builder. `list_reproduction_pipelines()` and `get_reproduction_pipeline()` only deserialize stored JSON. The revision creates the table and conversation index; the migration test must still report no metadata drift.

- [ ] **Step 4: Rerun contract and migration tests**

Run: `python -m pytest tests/test_research_reproduction_pipeline.py tests/test_migrations.py -q`

### Task 3: Add the isolated FastAPI contract

**Files:**
- Modify: `src/code_navi/research/router.py`
- Modify: `tests/test_research_reproduction_pipeline.py`

- [ ] **Step 1: Add a failing no-network and source-membership test**

```python
def test_pipeline_does_not_search_and_rejects_a_paper_outside_the_saved_bundle(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "code_navi.research.conversation_search_service.ResearchConversationSearchService.search",
        lambda *_args, **_kwargs: pytest.fail("Pipeline must not search"),
    )
    response = client.post(url, json={"evidence_bundle_id": bundle_id, "paper_url": "https://other"})
    assert response.status_code == 404
```

- [ ] **Step 2: Run and confirm RED**

Run: `python -m pytest tests/test_research_reproduction_pipeline.py -q`

- [ ] **Step 3: Add routes**

```python
@router.post("/conversations/{conversation_id}/reproduction-pipelines", status_code=201)
def create_reproduction_pipeline(...): ...

@router.get("/conversations/{conversation_id}/reproduction-pipelines")
def list_reproduction_pipelines(...): ...

@router.get("/reproduction-pipelines/{pipeline_id}")
def get_reproduction_pipeline(...): ...
```

Map unknown conversation or source to safe 404 responses; do not add any evaluation route.

- [ ] **Step 4: Rerun API tests**

Run: `python -m pytest tests/test_research_reproduction_pipeline.py -q`

### Task 4: Add the frontend panel and API mirror

**Files:**
- Modify: `frontend/lib/api/research.ts`
- Create: `frontend/components/research/ReproductionPipelinePanel.tsx`
- Modify: `frontend/components/research/ResearchConversation.tsx`
- Modify: `tests/test_research_frontend_copy.py`

- [ ] **Step 1: Add a failing copy contract test**

```python
def test_reproduction_pipeline_copy_requires_a_saved_paper_and_never_claims_execution() -> None:
    source = Path("frontend/components/research/ReproductionPipelinePanel.tsx").read_text(encoding="utf-8")
    assert "请先从已保存的受限来源中选择一篇论文" in source
    assert "不会联网、下载全文、运行代码或写入学生项目" in source
    assert "已复现成功" not in source
```

- [ ] **Step 2: Run and confirm RED**

Run: `python -m pytest tests/test_research_frontend_copy.py -q`

- [ ] **Step 3: Implement the smallest panel**

The API mirror defines the exact Pipeline types and three request functions. The component loads existing saved bundles and Pipelines, allows one paper selection, sends only `evidence_bundle_id` plus `paper_url` when the user presses “生成复现方案”, and renders classifications, source scope, two-week tasks, and matching user-submitted evidence. It contains no code editor, provider invocation, execution controls, or B evaluation UI.

- [ ] **Step 4: Run frontend contract test and static checks**

Run: `python -m pytest tests/test_research_frontend_copy.py -q; npm --prefix frontend run lint; npm --prefix frontend run build`

### Task 5: Add the paper-reproduction Skill and verify the local slice

**Files:**
- Create: `src/code_navi/research/skills/paper-reproduction/SKILL.md`
- Test: `tests/test_research_skill_contract_docs.py`

- [ ] **Step 1: Add the failing Skill-document test**

```python
def test_paper_reproduction_skill_documents_explicit_selection_and_boundaries() -> None:
    source = Path("src/code_navi/research/skills/paper-reproduction/SKILL.md").read_text(encoding="utf-8")
    assert "用户主动选择" in source
    assert "to_verify" in source
    assert "不自动执行代码" in source
```

- [ ] **Step 2: Run and confirm RED**

Run: `python -m pytest tests/test_research_skill_contract_docs.py -q`

- [ ] **Step 3: Document the actual contract and boundaries**

Document the inputs, output schema, task-to-evidence matching rule, explicit trigger, no-network/no-full-text/no-execution boundary, and the B handoff rule that `reproduction-pipeline.v1` is read-only input rather than an evaluation result.

- [ ] **Step 4: Verify the complete local scope**

Run: `python -m pytest tests/test_research_reproduction_pipeline.py tests/test_research_paper_workflow.py tests/test_conversation_search.py tests/test_research_frontend_copy.py tests/test_research_skill_contract_docs.py tests/test_migrations.py -q; python -m ruff check src/code_navi/research tests/test_research_reproduction_pipeline.py tests/test_research_frontend_copy.py tests/test_research_skill_contract_docs.py; npm --prefix frontend run lint; npm --prefix frontend run build`
