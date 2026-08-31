"""Contracts for offline, evidence-bounded reproduction project evaluation."""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

os.environ["LEARNING_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import Base, SessionLocal, engine  # noqa: E402
from code_navi.research.conversation_schemas import (  # noqa: E402
    CitationCandidate,
    ExperimentEvidenceBundle,
    ExperimentEvidenceItem,
    ReferenceEntryDraft,
    ReproductionPipeline,
    ReproductionPipelineItem,
    ReproductionSelectedPaper,
    ResearchProfile,
    SelectedCitation,
)
from code_navi.research.models import (  # noqa: E402
    ResearchConversationModel,
    ResearchReproductionPipelineModel,
)
from code_navi.research.reproduction_evaluation import (  # noqa: E402
    evaluate_reproduction_project,
)
from code_navi.research.reproduction_evaluation_schemas import (  # noqa: E402
    ReproductionPipelineEvaluationView,
    ReproductionPipelineEvidenceEntry,
)
from code_navi.server import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_tables() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def _conversation(client: TestClient) -> str:
    response = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": None},
    )
    assert response.status_code == 201
    conversation_id = response.json()["conversation_id"]
    with SessionLocal() as db:
        model = db.get(ResearchConversationModel, conversation_id)
        assert model is not None
        model.profile_data = ResearchProfile(
            topic="图神经网络论文复现",
            research_questions=["目标方法能否复现实验表中的主要趋势？"],
            context="课程复现项目",
            constraints=["只使用公开数据"],
            expected_output="复现报告",
        ).model_dump(mode="json")
        db.commit()
    return conversation_id


def _dimension(result: dict[str, object], name: str) -> dict[str, object]:
    return next(item for item in result["dimensions"] if item["dimension"] == name)


def test_no_experiment_record_keeps_execution_dimension_unscored(
    client: TestClient,
) -> None:
    conversation_id = _conversation(client)

    response = client.post(
        f"/api/v1/research/conversations/{conversation_id}/reproduction-evaluations",
        json={"user_confirmed": True},
    )

    assert response.status_code == 201
    result = response.json()
    execution = _dimension(result, "execution_evidence")
    plan = _dimension(result, "reproduction_plan")
    assert execution["status"] == "not_evaluable"
    assert execution["score"] is None
    assert plan["status"] == "not_evaluable"
    assert result["pipeline_contract_status"] == "unavailable"
    assert result["score_summary"]["scored_maximum"] < 100
    assert "不表示复现成功" in result["boundary_note"]


def test_partial_experiment_evidence_scores_below_complete_case(
    client: TestClient,
) -> None:
    """中间案例：只有一条失败记录时，执行证据应低于完整记录案例且仍非成功。"""
    conversation_id = _conversation(client)

    saved = client.post(
        f"/api/v1/research/conversations/{conversation_id}/experiment-evidence-bundles",
        json={
            "experiment_name": "部分记录",
            "goal": "先核对训练能否启动",
            "items": [
                {
                    "category": "failure_or_limitation",
                    "content": "第一次训练因显存不足中断，未产生指标。",
                    "classification": "fact",
                }
            ],
        },
    )
    assert saved.status_code == 201

    response = client.post(
        f"/api/v1/research/conversations/{conversation_id}/reproduction-evaluations",
        json={"user_confirmed": True},
    )
    assert response.status_code == 201
    result = response.json()
    execution = _dimension(result, "execution_evidence")
    assert execution["status"] != "not_evaluable"
    summary = result["score_summary"]
    assert summary["scored_maximum"] < 100
    assert "不表示复现成功" in result["boundary_note"]


def test_evaluation_persists_records_and_user_controlled_tasks(
    client: TestClient,
) -> None:
    conversation_id = _conversation(client)
    evidence = client.post(
        f"/api/v1/research/conversations/{conversation_id}/experiment-evidence-bundles",
        json={
            "experiment_name": "基础复现实验",
            "goal": "复现公开结果趋势",
            "items": [
                {
                    "category": "metric_or_result",
                    "classification": "fact",
                    "content": "用户报告：验证集准确率为 0.81。",
                },
                {
                    "category": "failure_or_limitation",
                    "classification": "fact",
                    "content": "用户报告：第二次运行发生显存不足。",
                },
            ],
        },
    )
    assert evidence.status_code == 201

    created = client.post(
        f"/api/v1/research/conversations/{conversation_id}/reproduction-evaluations",
        json={"user_confirmed": True},
    )
    restored = client.get(
        f"/api/v1/research/conversations/{conversation_id}/reproduction-evaluations"
    )

    assert created.status_code == 201
    result = created.json()
    execution = _dimension(result, "execution_evidence")
    assert execution["status"] == "needs_revision"
    assert execution["score"] == 8
    assert execution["evidence"][0]["information_scope"].startswith("用户主动提交")
    assert result["improvement_tasks"]
    assert restored.status_code == 200
    assert restored.json()[0]["evaluation_id"] == result["evaluation_id"]

    task_id = result["improvement_tasks"][0]["task_id"]
    accepted = client.patch(
        f"/api/v1/research/reproduction-improvement-tasks/{task_id}",
        json={"status": "accepted"},
    )
    completed = client.patch(
        f"/api/v1/research/reproduction-improvement-tasks/{task_id}",
        json={"status": "completed"},
    )
    invalid = client.patch(
        f"/api/v1/research/reproduction-improvement-tasks/{task_id}",
        json={"status": "accepted"},
    )

    assert accepted.status_code == 200
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert invalid.status_code == 409
    refreshed = client.get(
        f"/api/v1/research/conversations/{conversation_id}/reproduction-evaluations"
    ).json()[0]
    assert next(
        task for task in refreshed["improvement_tasks"] if task["task_id"] == task_id
    )["status"] == "completed"


def test_complete_user_report_still_requires_human_judgment() -> None:
    categories = (
        "setup",
        "baseline_or_control",
        "metric_or_result",
        "random_seed_or_reason",
        "failure_or_limitation",
    )
    bundle = ExperimentEvidenceBundle(
        bundle_id="experiment-complete",
        conversation_id="conversation-1",
        experiment_name=ExperimentEvidenceItem(
            category="setup",
            content="用户报告的完整实验",
            classification="fact",
            basis="用户主动提交。",
        ),
        goal=ExperimentEvidenceItem(
            category="setup",
            content="核对主要趋势",
            classification="fact",
            basis="用户主动提交。",
        ),
        items=[
            ExperimentEvidenceItem(
                category=category,
                content=f"用户报告的 {category} 记录",
                classification="fact",
                basis="用户主动提交，系统未复核。",
            )
            for category in categories
        ],
        submitted_at=datetime.now(UTC),
        provenance_note="用户主动提交，系统未复核。",
    )

    dimensions, _ = evaluate_reproduction_project(
        ResearchProfile(topic="复现", research_questions=["能否复现？"]),
        [],
        [bundle],
        None,
    )
    execution = next(item for item in dimensions if item.dimension == "execution_evidence")

    assert execution.score == 20
    assert execution.status == "checklist_complete"
    assert "系统未读取原始数据、运行代码或独立复核结果" in execution.fact_boundary


def test_abstract_scope_never_becomes_full_text_fact() -> None:
    now = datetime.now(UTC)
    citation = SelectedCitation(
        selected_citation_id="selected-1",
        session_id="conversation-1",
        citation=CitationCandidate(
            citation_id="citation-1",
            conversation_id="conversation-1",
            evidence_bundle_id="bundle-1",
            paper_title="A Reproduction Study",
            authors=["Researcher"],
            year=2026,
            source_name="arXiv",
            url="https://arxiv.org/abs/2601.00001",
            arxiv_id="2601.00001",
            abstract_scope="metadata_and_abstract",
            metadata_completeness="complete",
            classification="inference",
            created_at=now,
        ),
        target_document="paper_blueprint",
        target_section="方法",
        paragraph_anchor="方法-1",
        citation_placeholder="[A Reproduction Study]",
        reference_entry=ReferenceEntryDraft(
            reference_id="reference-1",
            selected_citation_id="selected-1",
            display_text="Researcher. A Reproduction Study. 2026.",
            citation_key="researcher-2026",
            metadata_fields={"year": 2026},
            classification="inference",
        ),
        created_at=now,
    )
    dimensions, _ = evaluate_reproduction_project(
        ResearchProfile(topic="复现", research_questions=["能否复现？"]),
        [citation],
        [],
        None,
    )
    source = next(item for item in dimensions if item.dimension == "source_traceability")

    assert source.evidence[0].classification == "inference"
    assert "不包含论文全文" in source.evidence[0].information_scope
    assert "摘要之外" in source.fact_boundary


def test_pipeline_adapter_view_can_score_plan_without_redefining_a_model() -> None:
    entry = ReproductionPipelineEvidenceEntry(
        content="已保存条目",
        classification="to_verify",
        basis="来自 A Pipeline 的只读适配器。",
        source_scope="pipeline_saved_entry",
    )
    pipeline = ReproductionPipelineEvaluationView(
        pipeline_id="pipeline-1",
        target_paper_title="Target Paper",
        dataset_entries=[entry],
        baseline_entries=[entry],
        metric_entries=[entry],
        step_entries=[entry],
        resource_entries=[entry],
    )

    dimensions, summary = evaluate_reproduction_project(
        ResearchProfile(topic="复现", research_questions=["能否复现？"]),
        [],
        [
            ExperimentEvidenceBundle(
                bundle_id="experiment-1",
                conversation_id="conversation-1",
                experiment_name=ExperimentEvidenceItem(
                    category="setup",
                    content="实验",
                    classification="fact",
                    basis="用户提交。",
                ),
                goal=ExperimentEvidenceItem(
                    category="setup",
                    content="目标",
                    classification="fact",
                    basis="用户提交。",
                ),
                items=[
                    ExperimentEvidenceItem(
                        category="metric_or_result",
                        content="结果",
                        classification="fact",
                        basis="用户提交。",
                    )
                ],
                submitted_at=datetime.now(UTC),
                provenance_note="用户提交，系统未复核。",
            )
        ],
        pipeline,
    )
    plan = next(item for item in dimensions if item.dimension == "reproduction_plan")

    assert plan.score == 0
    assert plan.status == "needs_revision"
    assert all(item.classification == "to_verify" for item in plan.evidence)
    assert summary.total_maximum == 100


def test_default_service_reads_latest_persisted_a_pipeline(client: TestClient) -> None:
    conversation_id = _conversation(client)
    created_at = datetime.now(UTC)
    entry = ReproductionPipelineItem(
        content="待人工核对的复现条件",
        classification="to_verify",
        basis="来自用户主动生成并保存的 A Pipeline。",
        source_scope="摘要/元数据未覆盖",
    )
    pipeline = ReproductionPipeline(
        pipeline_id="pipeline-from-a",
        conversation_id=conversation_id,
        source_bundle_id="bundle-from-a",
        selected_paper=ReproductionSelectedPaper(
            url="https://example.test/paper",
            title="A Persisted Reproduction Study",
            source_name="OpenAlex",
            year=2026,
            abstract_scope="metadata_and_abstract",
            abstract_excerpt="A bounded abstract excerpt.",
        ),
        reproduction_goal=entry,
        research_question=entry,
        known_method=entry,
        data_and_sample_conditions=[entry],
        candidate_baselines=[entry],
        metrics=[entry],
        experiment_steps=[entry],
        resources=[entry],
        risks=[entry],
        ethics=[entry],
        confirmation_items=[entry],
        tasks=[],
        two_week_mvp=[entry],
        created_at=created_at,
        provenance_note="规则生成的只读 Pipeline；不表示已执行或复现成功。",
    )
    with SessionLocal() as db:
        db.add(
            ResearchReproductionPipelineModel(
                id=pipeline.pipeline_id,
                conversation_id=conversation_id,
                pipeline_data=pipeline.model_dump(mode="json"),
                created_at=created_at,
            )
        )
        db.commit()

    response = client.post(
        f"/api/v1/research/conversations/{conversation_id}/reproduction-evaluations",
        json={"user_confirmed": True},
    )

    assert response.status_code == 201
    result = response.json()
    plan = _dimension(result, "reproduction_plan")
    assert result["pipeline_contract_status"] == "available"
    assert result["pipeline_id"] == "pipeline-from-a"
    assert plan["status"] == "needs_revision"
    assert plan["score"] == 0
    assert all(item["classification"] == "to_verify" for item in plan["evidence"])
