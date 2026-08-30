from datetime import UTC, datetime
from pathlib import Path

from code_navi.research.conversation_reproduction import build_reproduction_pipeline
from code_navi.research.conversation_schemas import (
    ConversationEvidenceBundle,
    ConversationResearchPlan,
    ExperimentEvidenceBundle,
    ExperimentEvidenceItem,
    ResearchPlanEntry,
    ResearchPlanRisk,
    ResearchProfile,
)
from code_navi.research.schemas import (
    AcademicPaperResult,
    AcademicSourceStatus,
    EvidenceStatement,
)

NOW = datetime(2026, 8, 15, tzinfo=UTC)


def _entry(content: str) -> ResearchPlanEntry:
    return ResearchPlanEntry(content=content, classification="inference", basis="已保存规则计划")


def _paper() -> AcademicPaperResult:
    return AcademicPaperResult(
        title="A Reproducible Learning Study",
        authors=["Ada Lovelace"],
        year=2025,
        source_name="OpenAlex",
        url="https://example.test/paper",
        identifier="doi:10.1000/example",
        abstract_excerpt="We compare two learning prompts in a classroom setting.",
        accessed_at=NOW,
        information_scope="metadata_and_abstract_only",
        metadata_evidence=[
            EvidenceStatement(
                content="A Reproducible Learning Study",
                classification="fact",
                source_url="https://example.test/paper",
                basis="OpenAlex metadata",
            )
        ],
        supporting_snippets=[],
        relevance=EvidenceStatement(
            content="Topic overlap",
            classification="inference",
            source_url="https://example.test/paper",
            basis="Title and abstract",
        ),
        verification=EvidenceStatement(
            content="Read the full text before relying on details.",
            classification="to_verify",
            source_url="https://example.test/paper",
            basis="Full text unavailable",
        ),
        full_text_available=False,
    )


def _bundle(paper: AcademicPaperResult) -> ConversationEvidenceBundle:
    return ConversationEvidenceBundle(
        bundle_id="bundle-1",
        conversation_id="conversation-1",
        query="learning prompts",
        requested_sources=["openalex"],
        allowed_sources=["openalex"],
        queried_sources=["openalex"],
        source_statuses=[
            AcademicSourceStatus(
                source="openalex",
                status="success",
                source_url="https://api.openalex.org",
                accessed_at=NOW,
            )
        ],
        searched_at=NOW,
        papers=[paper],
        source_links=[paper.url],
        failure_reasons=[],
        provenance_note="Saved metadata and abstract evidence.",
    )


def _plan() -> ConversationResearchPlan:
    return ConversationResearchPlan(
        research_title=_entry("Prompt learning study"),
        research_goal=_entry("Compare prompt strategies"),
        candidate_methods_or_baselines=[_entry("Use a simple comparison baseline")],
        suggested_datasets_or_metrics=[_entry("Record a learning outcome")],
        two_week_mvp_plan=[_entry("Plan the first week"), _entry("Review the second week")],
        risks_and_mitigations=[
            ResearchPlanRisk(risk=_entry("Scope may be too broad"), mitigation=_entry("Narrow it"))
        ],
        suggested_search_keywords=["learning prompts"],
        provenance_note="Rules plan.",
    )


def test_pipeline_marks_abstract_gaps_as_to_verify() -> None:
    paper = _paper()

    pipeline = build_reproduction_pipeline(
        ResearchProfile(topic="Prompt learning", research_questions=["Which prompt helps?"]),
        _plan(),
        _bundle(paper),
        paper,
        [],
    )

    assert pipeline.schema_version == "reproduction-pipeline.v1"
    assert pipeline.selected_paper.abstract_scope == "metadata_and_abstract"
    assert pipeline.known_method.classification == "fact"
    assert all(item.classification == "to_verify" for item in pipeline.data_and_sample_conditions)
    assert "摘要/元数据未覆盖" in pipeline.data_and_sample_conditions[0].source_scope
    assert all(task.status == "not_started" for task in pipeline.tasks)


def test_pipeline_keeps_metadata_only_method_and_scope_to_verify() -> None:
    paper = _paper().model_copy(update={"abstract_excerpt": None})

    pipeline = build_reproduction_pipeline(
        ResearchProfile(topic="Prompt learning"), _plan(), _bundle(paper), paper, []
    )

    assert pipeline.selected_paper.abstract_scope == "metadata_only"
    assert pipeline.known_method.classification == "to_verify"
    assert "摘要/元数据未覆盖" in pipeline.known_method.source_scope


def test_pipeline_links_user_experiment_evidence_only_by_task_id() -> None:
    paper = _paper()
    experiment = ExperimentEvidenceBundle(
        bundle_id="experiment-1",
        conversation_id="conversation-1",
        experiment_name=ExperimentEvidenceItem(
            category="setup",
            content="A user-described baseline run",
            classification="fact",
            basis="Submitted by user",
            related_plan_item="compare-python-baseline",
        ),
        goal=ExperimentEvidenceItem(
            category="pending_item",
            content="Check the baseline",
            classification="fact",
            basis="Submitted by user",
        ),
        items=[
            ExperimentEvidenceItem(
                category="baseline_or_control",
                content="A user-described baseline run",
                classification="fact",
                basis="Submitted by user",
                related_plan_item="compare-python-baseline",
            )
        ],
        submitted_at=NOW,
        provenance_note="Unverified user text.",
    )

    pipeline = build_reproduction_pipeline(
        ResearchProfile(topic="Prompt learning"), _plan(), _bundle(paper), paper, [experiment]
    )
    task = next(task for task in pipeline.tasks if task.task_id == "compare-python-baseline")

    assert task.status == "evidence_linked"
    assert task.evidence_links[0].experiment_bundle_id == "experiment-1"
    assert task.evidence_links[0].source_scope == "user_submitted_text_unverified"


def test_reproduction_panel_preserves_the_selected_evidence_bundle_and_contract_sections() -> None:
    source = Path("frontend/components/research/ReproductionPipelinePanel.tsx").read_text(
        encoding="utf-8"
    )

    assert "selectionKey" in source
    assert "paper.paper_id" in source
    assert "item.selectionKey === selected" in source
    assert "value={paper.selectionKey}" in source
    for label in (
        "研究问题",
        "候选基线",
        "实验步骤",
        "资源",
        "伦理",
        "待确认项",
        "两周 MVP",
    ):
        assert label in source


def test_reproduction_panel_refreshes_saved_evidence_and_experiment_links() -> None:
    source = Path("frontend/components/research/ReproductionPipelinePanel.tsx").read_text(
        encoding="utf-8"
    )

    assert "evidenceVersion" in source
    assert "listExperimentEvidenceBundles" in source
    assert "linkedTaskIds" in source
    assert "已关联用户实验记录" in source
