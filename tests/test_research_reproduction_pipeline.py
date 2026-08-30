import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

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
from code_navi.research.research_artifact_llm import ArtifactLlmOutcome
from code_navi.research.research_generation import ResearchGenerationError
from code_navi.research.schemas import (
    AcademicPaperResult,
    AcademicSourceStatus,
    EvidenceStatement,
)

NOW = datetime(2026, 8, 15, tzinfo=UTC)


class FakeArtifactGenerator:
    def __init__(self, outcome: ArtifactLlmOutcome) -> None:
        self.outcome = outcome
        self.calls: list[str] = []

    def generate(
        self,
        *,
        kind: str,
        context: dict[str, object],
        conversation_id: str,
    ) -> ArtifactLlmOutcome:
        self.calls.append(kind)
        return self.outcome


def _item(content: str, classification: str = "to_verify") -> dict[str, str]:
    return {
        "content": content,
        "classification": classification,
        "basis": "模型基于已保存上下文生成。",
        "source_scope": "profile_and_plan_only",
    }


def _task(task_id: str) -> dict[str, object]:
    return {
        "task_id": task_id,
        "title": f"任务 {task_id}",
        "description": "学习脚手架任务，不含可执行代码。",
        "classification": "inference",
        "basis": "模型生成的任务建议。",
        "source_scope": "profile_and_plan_only",
        "status": "not_started",
        "evidence_links": [],
    }


def _llm_pipeline_payload(
    paper: AcademicPaperResult, *, task_ids: list[str]
) -> ArtifactLlmOutcome:
    payload = {
        "schema_version": "reproduction-pipeline.v1",
        "pipeline_id": "pipeline-model",
        "conversation_id": "conversation-1",
        "source_bundle_id": "bundle-1",
        "selected_paper": {
            "url": paper.url,
            "title": paper.title,
            "source_name": paper.source_name,
            "year": paper.year,
            "identifier": paper.identifier,
            "abstract_scope": "metadata_and_abstract",
            "abstract_excerpt": paper.abstract_excerpt,
        },
        "reproduction_goal": _item("定义可确认的复现目标。", "inference"),
        "research_question": _item("研究问题。", "inference"),
        "known_method": _item("方法细节待核验。"),
        "data_and_sample_conditions": [_item("数据集与样本范围待核验。")],
        "candidate_baselines": [_item("候选基线待确认。", "inference")],
        "metrics": [_item("主指标与阈值待确认。")],
        "experiment_steps": [_item("先记录输入与对照。", "inference")],
        "resources": [_item("设备与时间待确认。")],
        "risks": [_item("摘要不足以证明可复现性。")],
        "ethics": [_item("数据治理与伦理待确认。")],
        "confirmation_items": [_item("确认边界后再人工实验。")],
        "tasks": [_task(task_id) for task_id in task_ids],
        "two_week_mvp": [_item("两周 MVP 范围待确认。", "inference")],
        "created_at": NOW.isoformat(),
        "provenance_note": "模型生成；边界由规则校验。",
    }
    return ArtifactLlmOutcome.generated(json.dumps(payload, ensure_ascii=False))


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


def test_pipeline_is_model_written_and_keeps_identity_and_boundary() -> None:
    paper = _paper()
    generator = FakeArtifactGenerator(
        _llm_pipeline_payload(paper, task_ids=["confirm-python-environment"])
    )

    pipeline = build_reproduction_pipeline(
        ResearchProfile(topic="Prompt learning", research_questions=["Which prompt helps?"]),
        _plan(),
        _bundle(paper),
        paper,
        [],
        generator=generator,
        conversation_id="conversation-1",
    )

    assert generator.calls == ["reproduction_pipeline"]
    assert pipeline.schema_version == "reproduction-pipeline.v1"
    assert pipeline.generation_mode == "llm"
    assert pipeline.selected_paper.abstract_scope == "metadata_and_abstract"
    assert pipeline.selected_paper.identifier == paper.identifier
    assert pipeline.known_method.classification != "fact"
    assert all(
        item.classification != "fact" for item in pipeline.data_and_sample_conditions
    )
    assert all(task.status == "not_started" for task in pipeline.tasks)


def test_pipeline_restamps_metadata_only_scope_from_the_selected_paper() -> None:
    paper = _paper().model_copy(update={"abstract_excerpt": None})
    generator = FakeArtifactGenerator(
        _llm_pipeline_payload(paper, task_ids=["confirm-python-environment"])
    )

    pipeline = build_reproduction_pipeline(
        ResearchProfile(topic="Prompt learning"),
        _plan(),
        _bundle(paper),
        paper,
        [],
        generator=generator,
        conversation_id="conversation-1",
    )

    assert pipeline.selected_paper.abstract_scope == "metadata_only"
    assert pipeline.selected_paper.abstract_excerpt is None


def test_model_cannot_introduce_fact_or_unknown_scope() -> None:
    paper = _paper()
    payload = json.loads(_llm_pipeline_payload(paper, task_ids=["confirm-python-environment"]).text)
    payload["known_method"]["classification"] = "fact"
    generator = FakeArtifactGenerator(
        ArtifactLlmOutcome.generated(json.dumps(payload, ensure_ascii=False))
    )

    with pytest.raises(ResearchGenerationError) as excinfo:
        build_reproduction_pipeline(
            ResearchProfile(topic="Prompt learning"),
            _plan(),
            _bundle(paper),
            paper,
            [],
            generator=generator,
            conversation_id="conversation-1",
        )

    assert excinfo.value.stage == "invalid_output"


def test_unavailable_provider_raises_instead_of_a_scaffold() -> None:
    paper = _paper()

    with pytest.raises(ResearchGenerationError) as excinfo:
        build_reproduction_pipeline(
            ResearchProfile(topic="Prompt learning"),
            _plan(),
            _bundle(paper),
            paper,
            [],
            generator=FakeArtifactGenerator(ArtifactLlmOutcome.unavailable()),
            conversation_id="conversation-1",
        )

    assert excinfo.value.stage == "provider_unavailable"


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

    generator = FakeArtifactGenerator(
        _llm_pipeline_payload(paper, task_ids=["compare-python-baseline"])
    )

    pipeline = build_reproduction_pipeline(
        ResearchProfile(topic="Prompt learning"),
        _plan(),
        _bundle(paper),
        paper,
        [experiment],
        generator=generator,
        conversation_id="conversation-1",
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
