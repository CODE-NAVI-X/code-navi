"""Contracts for offline, evidence-bounded reproduction project evaluation."""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

os.environ["LEARNING_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import Base, SessionLocal, engine  # noqa: E402
from code_navi.research.conversation_schemas import ResearchProfile  # noqa: E402
from code_navi.research.models import (  # noqa: E402
    ResearchConversationModel,
    ResearchReproductionEvaluationModel,
    ResearchReproductionImprovementTaskModel,
)
from code_navi.research.reproduction_evaluation import (  # noqa: E402
    evaluate_reproduction_project_v2,
)
from code_navi.server import app  # noqa: E402

_CRITERION_TITLES = [
    "研究问题与假设可复述性",
    "方法可执行性（步骤完整、变量可操作）",
    "数据可得性（公开链接与许可）",
    "指标与统计方法正确性（对照标准目录）",
    "计算资源与时间可行性",
    "结果核验路径（baseline 与预期区间）",
]


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
            constraints=["只使用公开数据", "两周内完成"],
            expected_output="复现报告",
        ).model_dump(mode="json")
        db.commit()
    return conversation_id


def test_new_reproduction_evaluation_is_v2_with_six_criteria_and_12_point_total(
    client: TestClient,
) -> None:
    conversation_id = _conversation(client)

    response = client.post(
        f"/api/v1/research/conversations/{conversation_id}/reproduction-evaluations",
        json={"user_confirmed": True},
    )

    assert response.status_code == 201
    result = response.json()
    assert result["schema_version"] == "reproduction-project-evaluation.v2"
    assert "total_score" in result
    assert 0 <= result["total_score"] <= 12
    assert len(result["criteria"]) == 6

    for index, criterion in enumerate(result["criteria"], start=1):
        assert criterion["criterion_no"] == index
        assert criterion["title"] == _CRITERION_TITLES[index - 1]
        assert criterion["score"] in (0, 1, 2)
        assert len(criterion["basis"]) <= 500
        assert isinstance(criterion["evidence_refs"], list)

    assert result["total_score"] == sum(item["score"] for item in result["criteria"])
    assert "不表示复现成功" in result["boundary_note"]


def test_evaluation_v2_persists_and_links_tasks_by_criterion(
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
    assert result["schema_version"] == "reproduction-project-evaluation.v2"
    assert result["total_score"] <= 12
    assert restored.status_code == 200
    assert len(restored.json()) == 1
    assert restored.json()[0]["schema_version"] == "reproduction-project-evaluation.v2"
    assert restored.json()[0]["evaluation_id"] == result["evaluation_id"]

    if result["improvement_tasks"]:
        task = result["improvement_tasks"][0]
        task_id = task["task_id"]
        # task basis 引用 criterion_no
        assert any(str(i) in task["basis"] for i in range(1, 7))

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
            t for t in refreshed["improvement_tasks"] if t["task_id"] == task_id
        )["status"] == "completed"


def test_v1_historical_evaluation_restores_as_is_without_conversion(
    client: TestClient,
) -> None:
    conversation_id = _conversation(client)
    created_at = datetime.now(UTC)
    eval_id = "eval-v1-history"
    v1_data = {
        "schema_version": "reproduction-project-evaluation.v1",
        "evaluation_id": eval_id,
        "conversation_id": conversation_id,
        "pipeline_id": None,
        "pipeline_contract_status": "unavailable",
        "selected_paper_count": 1,
        "experiment_record_count": 0,
        "score_summary": {
            "earned_score": 48,
            "scored_maximum": 80,
            "total_maximum": 100,
            "scored_dimension_count": 4,
            "unscored_dimension_count": 1,
            "display": "48/80（当前有 1 个维度因证据不足未评分；完整结构上限为 100）",
        },
        "dimensions": [
            {
                "dimension": "research_definition",
                "label": "问题与目标定义",
                "status": "checklist_complete",
                "score": 16,
                "maximum_score": 20,
                "issues": [],
                "evidence": [],
                "fact_boundary": "事实边界说明",
                "to_verify": [],
                "next_suggestions": [],
            },
            {
                "dimension": "source_traceability",
                "label": "论文与来源可追溯性",
                "status": "needs_revision",
                "score": 12,
                "maximum_score": 20,
                "issues": ["元数据缺口"],
                "evidence": [],
                "fact_boundary": "事实边界说明",
                "to_verify": [],
                "next_suggestions": ["补齐元数据"],
            },
            {
                "dimension": "reproduction_plan",
                "label": "复现路径与可执行性",
                "status": "not_evaluable",
                "score": None,
                "maximum_score": 20,
                "issues": ["无 Pipeline"],
                "evidence": [],
                "fact_boundary": "事实边界说明",
                "to_verify": [],
                "next_suggestions": [],
            },
            {
                "dimension": "execution_evidence",
                "label": "执行记录与结果证据",
                "status": "needs_revision",
                "score": 8,
                "maximum_score": 20,
                "issues": ["缺少基线"],
                "evidence": [],
                "fact_boundary": "事实边界说明",
                "to_verify": [],
                "next_suggestions": ["补充基线"],
            },
            {
                "dimension": "reflection_and_compliance",
                "label": "局限、伦理与迭代记录",
                "status": "needs_revision",
                "score": 12,
                "maximum_score": 20,
                "issues": ["缺少伦理"],
                "evidence": [],
                "fact_boundary": "事实边界说明",
                "to_verify": [],
                "next_suggestions": ["补充伦理"],
            },
        ],
        "created_at": created_at.isoformat(),
        "boundary_note": "v1 历史边界说明",
    }
    with SessionLocal() as db:
        db.add(
            ResearchReproductionEvaluationModel(
                id=eval_id,
                conversation_id=conversation_id,
                evaluation_data=v1_data,
                created_at=created_at,
            )
        )
        db.add(
            ResearchReproductionImprovementTaskModel(
                id="task-v1",
                evaluation_id=eval_id,
                conversation_id=conversation_id,
                task_data={
                    "schema_version": "reproduction-improvement-task.v1",
                    "task_id": "task-v1",
                    "evaluation_id": eval_id,
                    "conversation_id": conversation_id,
                    "dimension": "source_traceability",
                    "title": "改进“论文与来源可追溯性”",
                    "description": "补齐元数据",
                    "status": "pending",
                    "classification": "to_verify",
                    "basis": "来自当前评估维度的显式证据缺口",
                    "created_at": created_at.isoformat(),
                    "updated_at": created_at.isoformat(),
                },
                created_at=created_at,
                updated_at=created_at,
            )
        )
        db.commit()

    url = f"/api/v1/research/conversations/{conversation_id}/reproduction-evaluations"
    list_resp = client.get(url)
    assert list_resp.status_code == 200
    list_body = list_resp.json()
    assert len(list_body) == 1
    item = list_body[0]
    assert item["schema_version"] == "reproduction-project-evaluation.v1"
    # 绝对禁止 100 -> 12 换算，原样返回 100 分制
    assert item["score_summary"]["earned_score"] == 48
    assert item["score_summary"]["total_maximum"] == 100
    assert "dimensions" in item

    get_resp = client.get(f"/api/v1/research/reproduction-evaluations/{eval_id}")
    assert get_resp.status_code == 200
    get_body = get_resp.json()
    assert get_body["schema_version"] == "reproduction-project-evaluation.v1"
    assert get_body["score_summary"]["earned_score"] == 48
    assert get_body["score_summary"]["total_maximum"] == 100


def test_evaluate_reproduction_project_v2_criteria_and_bounds() -> None:
    profile = ResearchProfile(
        topic="图神经网络复现",
        research_questions=["能否复现 Cora 节点分类基线？"],
        constraints=["两周", "单卡 GPU"],
    )
    criteria, total_score, tasks = evaluate_reproduction_project_v2(
        profile,
        [],
        [],
        None,
        conversation_id="conv-test",
        evaluation_id="eval-test",
    )
    assert len(criteria) == 6
    assert total_score == sum(c.score for c in criteria)
    assert total_score <= 12
    assert criteria[0].title == "研究问题与假设可复述性"
    assert criteria[1].title == "方法可执行性（步骤完整、变量可操作）"
    assert criteria[2].title == "数据可得性（公开链接与许可）"
    assert criteria[3].title == "指标与统计方法正确性（对照标准目录）"
    assert criteria[4].title == "计算资源与时间可行性"
    assert criteria[5].title == "结果核验路径（baseline 与预期区间）"
    for c in criteria:
        assert c.score in (0, 1, 2)
        assert len(c.basis) <= 500


def test_schema_validation_locks_criteria_order_and_sum() -> None:
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionEvaluationCriterion,
        ReproductionEvaluationScoreSummaryV2,
        ReproductionProjectEvaluationV2,
    )

    valid_criteria = [
        ReproductionEvaluationCriterion(
            criterion_no=i,
            title=_CRITERION_TITLES[i - 1],  # type: ignore
            score=1,
            basis=f"依据 {i}",
        )
        for i in range(1, 7)
    ]
    eval_obj = ReproductionProjectEvaluationV2(
        evaluation_id="eval-1",
        conversation_id="conv-1",
        pipeline_contract_status="available",
        selected_paper_count=1,
        experiment_record_count=0,
        total_score=6,
        score_summary=ReproductionEvaluationScoreSummaryV2(
            earned_score=6,
            scored_maximum=12,
            total_maximum=12,
            scored_criterion_count=6,
            unscored_criterion_count=0,
            display="6/12",
        ),
        criteria=valid_criteria,
        created_at=datetime.now(UTC),
        boundary_note="边界",
    )
    assert eval_obj.total_score == 6

    # 1. 验证求和不一致时抛出 ValueError
    with pytest.raises(ValueError, match="total_score"):
        ReproductionProjectEvaluationV2(
            evaluation_id="eval-1",
            conversation_id="conv-1",
            pipeline_contract_status="available",
            selected_paper_count=1,
            experiment_record_count=0,
            total_score=10,  # 错误求和
            score_summary=ReproductionEvaluationScoreSummaryV2(
                earned_score=10,
                scored_maximum=12,
                total_maximum=12,
                scored_criterion_count=6,
                unscored_criterion_count=0,
                display="10/12",
            ),
            criteria=valid_criteria,
            created_at=datetime.now(UTC),
            boundary_note="边界",
        )

    # 2. 验证 criterion_no 顺序错误时抛出 ValueError
    shuffled_criteria = list(reversed(valid_criteria))
    with pytest.raises(ValueError, match="criteria must have criterion_no 1 through 6"):
        ReproductionProjectEvaluationV2(
            evaluation_id="eval-1",
            conversation_id="conv-1",
            pipeline_contract_status="available",
            selected_paper_count=1,
            experiment_record_count=0,
            total_score=6,
            score_summary=ReproductionEvaluationScoreSummaryV2(
                earned_score=6,
                scored_maximum=12,
                total_maximum=12,
                scored_criterion_count=6,
                unscored_criterion_count=0,
                display="6/12",
            ),
            criteria=shuffled_criteria,
            created_at=datetime.now(UTC),
            boundary_note="边界",
        )


def test_no_experiment_record_keeps_result_criterion_zero_and_boundary_explicit() -> None:
    profile = ResearchProfile(
        topic="对比学习复现",
        research_questions=["SimCLR 基准能否在 CIFAR-10 上复现？"],
    )
    criteria, total_score, tasks = evaluate_reproduction_project_v2(
        profile,
        [],
        [],
        None,
        conversation_id="conv-1",
        evaluation_id="eval-1",
    )
    crit6 = next(c for c in criteria if c.criterion_no == 6)
    assert crit6.score == 0
    assert "尚未保存对照基线" in crit6.basis
    assert any(t.dimension == "execution_evidence" for t in tasks)


def test_failure_only_experiment_records_score_one_and_never_claims_verified_result() -> None:
    from code_navi.research.conversation_schemas import (
        ExperimentEvidenceBundle,
        ExperimentEvidenceItem,
    )

    profile = ResearchProfile(
        topic="大模型微调复现",
        research_questions=["LoRA 是否有效降低显存？"],
    )
    failure_bundle = ExperimentEvidenceBundle(
        bundle_id="b-fail",
        conversation_id="conv-1",
        experiment_name=ExperimentEvidenceItem(
            category="metric_or_result",
            content="第一次微调尝试",
            classification="fact",
            basis="用户输入",
            source_scope="user_submitted_text",
        ),
        goal=ExperimentEvidenceItem(
            category="metric_or_result",
            content="复现 7B 模型微调",
            classification="fact",
            basis="用户输入",
            source_scope="user_submitted_text",
        ),
        items=[
            ExperimentEvidenceItem(
                category="failure_or_limitation",
                content="由于显存不足（OOM Error）导致训练中断失败",
                classification="fact",
                basis="终端报错",
                source_scope="user_submitted_text",
            )
        ],
        submitted_at=datetime.now(UTC),
        provenance_note="用户提交",
    )
    criteria, total_score, tasks = evaluate_reproduction_project_v2(
        profile,
        [],
        [failure_bundle],
        None,
        conversation_id="conv-1",
        evaluation_id="eval-1",
    )
    crit6 = next(c for c in criteria if c.criterion_no == 6)
    # 纯失败记录不能冒充有效核验证据，保守得 1 分
    assert crit6.score == 1
    assert "核验路径尚未完整建立" in crit6.basis
    assert "闭环" not in crit6.basis


def test_data_availability_never_treats_paper_url_as_dataset_link() -> None:
    from code_navi.research.conversation_schemas import (
        CitationCandidate,
        ReferenceEntryDraft,
        SelectedCitation,
    )

    profile = ResearchProfile(topic="NLP 复现", research_questions=["Q1"])
    citation = SelectedCitation(
        selected_citation_id="cit-1",
        session_id="conv-1",
        citation=CitationCandidate(
            citation_id="cand-1",
            conversation_id="conv-1",
            evidence_bundle_id="bundle-1",
            paper_title="Transformer 论文",
            url="https://arxiv.org/abs/1706.03762",
            authors=["Vaswani"],
            year=2017,
            abstract_scope="metadata_and_abstract",
            metadata_completeness="complete",
            classification="to_verify",
            created_at=datetime.now(UTC),
        ),
        target_document="paper_draft",
        target_section="相关工作",
        paragraph_anchor="p1",
        citation_placeholder="(Vaswani et al., 2017)",
        reference_entry=ReferenceEntryDraft(
            reference_id="ref-1",
            selected_citation_id="cit-1",
            display_text="Vaswani et al. (2017)",
            citation_key="vaswani2017",
            metadata_fields={"title": "Transformer 论文"},
            classification="to_verify",
        ),
        created_at=datetime.now(UTC),
    )
    criteria, total_score, tasks = evaluate_reproduction_project_v2(
        profile,
        [citation],
        [],
        None,
        conversation_id="conv-1",
        evaluation_id="eval-1",
    )
    crit3 = next(c for c in criteria if c.criterion_no == 3)
    # 仅有论文链接不能冒充数据集公开下载/许可，得 1 分
    assert crit3.score == 1
    assert "非数据集直接下载" in crit3.evidence_refs[0].basis
    assert "尚未在 Pipeline 中提供经核验的数据集" in crit3.basis


def test_abstract_scope_never_becomes_full_text_fact() -> None:
    from code_navi.research.conversation_schemas import (
        CitationCandidate,
        ReferenceEntryDraft,
        SelectedCitation,
    )

    profile = ResearchProfile(topic="NLP 复现", research_questions=["Q1"])
    citation = SelectedCitation(
        selected_citation_id="cit-1",
        session_id="conv-1",
        citation=CitationCandidate(
            citation_id="cand-1",
            conversation_id="conv-1",
            evidence_bundle_id="bundle-1",
            paper_title="Transformer 论文",
            url="https://arxiv.org/abs/1706.03762",
            authors=["Vaswani"],
            year=2017,
            abstract_scope="metadata_and_abstract",
            metadata_completeness="complete",
            classification="to_verify",
            created_at=datetime.now(UTC),
        ),
        target_document="paper_draft",
        target_section="相关工作",
        paragraph_anchor="p1",
        citation_placeholder="(Vaswani et al., 2017)",
        reference_entry=ReferenceEntryDraft(
            reference_id="ref-1",
            selected_citation_id="cit-1",
            display_text="Vaswani et al. (2017)",
            citation_key="vaswani2017",
            metadata_fields={"title": "Transformer 论文"},
            classification="to_verify",
        ),
        created_at=datetime.now(UTC),
    )
    criteria, total_score, tasks = evaluate_reproduction_project_v2(
        profile,
        [citation],
        [],
        None,
        conversation_id="conv-1",
        evaluation_id="eval-1",
    )
    for c in criteria:
        for ref in c.evidence_refs:
            if ref.source_type == "selected_citation":
                assert "摘要" in ref.information_scope
                assert "不包含论文全文" in ref.information_scope
                assert ref.classification != "fact"


def test_criterion4_standard_catalog_hit_and_miss() -> None:
    """验证使用上游真实 metrics_catalog / MetricSpec 进行准则 4 评估。"""
    from code_navi.research.conversation_schemas import MetricSpec
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
        ReproductionPipelineEvidenceEntry,
    )

    profile = ResearchProfile(topic="CV 复现", research_questions=["Q1"])

    # 1. 命中标准指标文本条目（Accuracy） -> 得 2 分
    view_hit_entry = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        metric_entries=[
            ReproductionPipelineEvidenceEntry(
                content="Accuracy",
                classification="to_verify",
                basis="指标",
                source_scope="pipeline",
            )
        ],
    )
    c_hit, _, _ = evaluate_reproduction_project_v2(
        profile, [], [], view_hit_entry, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit4_hit = next(c for c in c_hit if c.criterion_no == 4)
    assert crit4_hit.score == 2
    assert "命中标准指标目录" in crit4_hit.basis

    # 2. 命中上游结构化 MetricSpec -> 得 2 分
    view_hit_spec = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        metric_specs=[
            MetricSpec(
                name="F1",
                definition="Precision 与 Recall 的调和平均数",
                higher_is_better=True,
                applies_to_task_type=["classification"],
                source="standard_catalog",
                to_verify=False,
            )
        ],
    )
    c_hit_spec, _, _ = evaluate_reproduction_project_v2(
        profile, [], [], view_hit_spec, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit4_spec = next(c for c in c_hit_spec if c.criterion_no == 4)
    assert crit4_spec.score == 2
    assert "命中标准指标目录" in crit4_spec.basis

    # 3. 未命中标准指标 -> 得 1 分（to_verify）
    view_miss = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        metric_entries=[
            ReproductionPipelineEvidenceEntry(
                content="CustomDomainScoreX",
                classification="to_verify",
                basis="自研指标",
                source_scope="pipeline",
            )
        ],
    )
    c_miss, _, _ = evaluate_reproduction_project_v2(
        profile, [], [], view_miss, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit4_miss = next(c for c in c_miss if c.criterion_no == 4)
    assert crit4_miss.score == 1
    assert "未完全匹配标准指标目录" in crit4_miss.basis

    # 4. 无指标条目 -> 得 0 分
    view_empty = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        metric_entries=[],
    )
    c_empty, _, _ = evaluate_reproduction_project_v2(
        profile, [], [], view_empty, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit4_empty = next(c for c in c_empty if c.criterion_no == 4)
    assert crit4_empty.score == 0
    assert "尚未保存评估指标" in crit4_empty.basis


def test_pipeline_adapter_view_can_score_plan_without_redefining_a_model() -> None:
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
        ReproductionPipelineEvidenceEntry,
    )

    profile = ResearchProfile(
        topic="GNN 复现",
        research_questions=["复现 GCN 准确率"],
        constraints=["GPU 24G 显存", "两周内完成"],
    )
    view = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target GNN Paper",
        step_entries=[
            ReproductionPipelineEvidenceEntry(
                content="步骤1：数据预处理与特征归一化",
                classification="to_verify",
                basis="步骤1",
                source_scope="pipeline",
            ),
            ReproductionPipelineEvidenceEntry(
                content="步骤2：模型训练与评估，调节超参数学习率 lr=0.01 与 batch=32",
                classification="to_verify",
                basis="步骤2",
                source_scope="pipeline",
            ),
        ],
        dataset_entries=[
            ReproductionPipelineEvidenceEntry(
                content="Cora 数据集 https://github.com/cora，遵循 MIT 开源许可",
                classification="to_verify",
                basis="数据集",
                source_scope="pipeline",
            )
        ],
        metric_entries=[
            ReproductionPipelineEvidenceEntry(
                content="Micro-F1",
                classification="to_verify",
                basis="指标",
                source_scope="pipeline",
            )
        ],
        resource_entries=[
            ReproductionPipelineEvidenceEntry(
                content="GPU RTX 3090, 24GB 显存，全量训练预计耗时 3天",
                classification="to_verify",
                basis="资源",
                source_scope="pipeline",
            )
        ],
        baseline_entries=[
            ReproductionPipelineEvidenceEntry(
                content="GCN 原论文基准准确率 [80.0% ~ 83.0%]",
                classification="to_verify",
                basis="基线",
                source_scope="pipeline",
            )
        ],
        objective_entries=[
            ReproductionPipelineEvidenceEntry(
                content="复现节点分类准确率预期达到 81.5% ± 0.5%",
                classification="to_verify",
                basis="目标",
                source_scope="pipeline",
            )
        ],
    )
    criteria, total_score, tasks = evaluate_reproduction_project_v2(
        profile,
        [],
        [],
        view,
        conversation_id="conv-1",
        evaluation_id="eval-1",
    )
    assert len(criteria) == 6
    assert total_score >= 6
    # 验证步骤充足且包含可操作变量时 criterion 2 得 2 分
    crit2 = next(c for c in criteria if c.criterion_no == 2)
    assert crit2.score == 2
    # 验证数据集同时具备公开 URL 与明确许可时 criterion 3 得 2 分
    crit3 = next(c for c in criteria if c.criterion_no == 3)
    assert crit3.score == 2


# =========================================================================
# 反例测试（Negative / Boundary Counterexample Tests）
# =========================================================================


def test_criterion3_counterexamples_url_without_license_scores_one() -> None:
    """反例：有公开 URL 但无明确许可说明 -> 严格最多 1 分。"""
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
        ReproductionPipelineEvidenceEntry,
    )

    profile = ResearchProfile(topic="NLP 复现", research_questions=["Q1"])
    view = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        dataset_entries=[
            ReproductionPipelineEvidenceEntry(
                content="数据集下载自 https://github.com/example/data",
                classification="to_verify",
                basis="数据",
                source_scope="pipeline",
            )
        ],
    )
    criteria, _score, _tasks = evaluate_reproduction_project_v2(
        profile, [], [], view, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit3 = next(c for c in criteria if c.criterion_no == 3)
    assert crit3.score == 1
    assert "缺少明确的数据使用/开源许可协议说明" in crit3.basis


def test_criterion3_counterexamples_license_without_url_scores_one() -> None:
    """反例：有开源许可说明但无公开可核验 URL -> 严格最多 1 分。"""
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
        ReproductionPipelineEvidenceEntry,
    )

    profile = ResearchProfile(topic="NLP 复现", research_questions=["Q1"])
    view = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        dataset_entries=[
            ReproductionPipelineEvidenceEntry(
                content="数据集遵循 CC-BY 4.0 许可协议，本地提供",
                classification="to_verify",
                basis="数据",
                source_scope="pipeline",
            )
        ],
    )
    criteria, _score, _tasks = evaluate_reproduction_project_v2(
        profile, [], [], view, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit3 = next(c for c in criteria if c.criterion_no == 3)
    assert crit3.score == 1
    assert "缺少可直接核验的数据集公开获取 URL" in crit3.basis


def test_criterion3_counterexamples_vague_words_scores_one() -> None:
    """反例：仅写了“公开数据集”泛泛文字而无具体 URL 和具体协议 -> 严格最多 1 分。"""
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
        ReproductionPipelineEvidenceEntry,
    )

    profile = ResearchProfile(topic="NLP 复现", research_questions=["Q1"])
    view = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        dataset_entries=[
            ReproductionPipelineEvidenceEntry(
                content="使用开源公开数据集进行测试",
                classification="to_verify",
                basis="数据",
                source_scope="pipeline",
            )
        ],
    )
    criteria, _score, _tasks = evaluate_reproduction_project_v2(
        profile, [], [], view, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit3 = next(c for c in criteria if c.criterion_no == 3)
    assert crit3.score == 1


def test_criterion3_both_url_and_license_scores_two() -> None:
    """正例：同时具备可核验 URL 与明确许可协议 -> 满分 2 分。"""
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
        ReproductionPipelineEvidenceEntry,
    )

    profile = ResearchProfile(topic="NLP 复现", research_questions=["Q1"])
    view = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        dataset_entries=[
            ReproductionPipelineEvidenceEntry(
                content="数据集位于 https://huggingface.co/datasets/glue，遵循 Apache 2.0 协议",
                classification="to_verify",
                basis="数据",
                source_scope="pipeline",
            )
        ],
    )
    criteria, _score, _tasks = evaluate_reproduction_project_v2(
        profile, [], [], view, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit3 = next(c for c in criteria if c.criterion_no == 3)
    assert crit3.score == 2


def test_criterion3_structured_dataset_ref_with_url_and_license_scores_two() -> None:
    """正例：使用上游结构化 DatasetRef 且同时包含 URL 与许可 -> 满分 2 分。"""
    from code_navi.research.conversation_schemas import DatasetRef
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
    )

    profile = ResearchProfile(topic="NLP 复现", research_questions=["Q1"])
    view = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        dataset_refs=[
            DatasetRef(
                name="GLUE Benchmark",
                url="https://huggingface.co/datasets/glue",
                license_note="Apache 2.0",
                to_verify=False,
            )
        ],
    )
    criteria, _score, _tasks = evaluate_reproduction_project_v2(
        profile, [], [], view, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit3 = next(c for c in criteria if c.criterion_no == 3)
    assert crit3.score == 2


def test_criterion3_structured_dataset_ref_missing_license_scores_one() -> None:
    """反例：使用上游结构化 DatasetRef 但缺少许可 -> 严格最多 1 分。"""
    from code_navi.research.conversation_schemas import DatasetRef
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
    )

    profile = ResearchProfile(topic="NLP 复现", research_questions=["Q1"])
    view = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        dataset_refs=[
            DatasetRef(
                name="GLUE Benchmark",
                url="https://huggingface.co/datasets/glue",
                license_note=None,
                to_verify=True,
            )
        ],
    )
    criteria, _score, _tasks = evaluate_reproduction_project_v2(
        profile, [], [], view, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit3 = next(c for c in criteria if c.criterion_no == 3)
    assert crit3.score == 1
    assert "缺少明确的数据使用/开源许可协议说明" in crit3.basis


def test_criterion6_counterexamples_missing_any_of_three_scores_at_most_one() -> None:
    """反例：基线、预期数值区间、非失败实验三项缺任何一项均最多 1 分。"""
    from code_navi.research.conversation_schemas import (
        ExperimentEvidenceBundle,
        ExperimentEvidenceItem,
    )
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
        ReproductionPipelineEvidenceEntry,
    )

    profile = ResearchProfile(topic="NLP 复现", research_questions=["Q1"])
    valid_bundle = ExperimentEvidenceBundle(
        bundle_id="b-valid",
        conversation_id="conv-1",
        experiment_name=ExperimentEvidenceItem(
            category="metric_or_result",
            content="第一次实验",
            classification="fact",
            basis="运行日志",
            source_scope="user_submitted_text",
        ),
        goal=ExperimentEvidenceItem(
            category="metric_or_result",
            content="测试测试集准确率",
            classification="fact",
            basis="运行日志",
            source_scope="user_submitted_text",
        ),
        items=[
            ExperimentEvidenceItem(
                category="metric_or_result",
                content="测试集准确率为 0.82",
                classification="fact",
                basis="终端输出",
                source_scope="user_submitted_text",
            )
        ],
        submitted_at=datetime.now(UTC),
        provenance_note="用户提交",
    )

    # 1. 缺实验记录（有基线和区间）-> 1 分
    view_with_baseline_and_range = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        baseline_entries=[
            ReproductionPipelineEvidenceEntry(
                content="BERT 原论文基线准确率 0.81 [0.80 ~ 0.83]",
                classification="to_verify",
                basis="基线",
                source_scope="pipeline",
            )
        ],
    )
    c_no_exp, _, _ = evaluate_reproduction_project_v2(
        profile,
        [],
        [],
        view_with_baseline_and_range,
        conversation_id="conv-1",
        evaluation_id="eval-1",
    )
    assert next(c for c in c_no_exp if c.criterion_no == 6).score == 1

    # 2. 缺预期数值区间（有基线和实验，但基线无明确数值区间）-> 1 分
    view_no_range = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        baseline_entries=[
            ReproductionPipelineEvidenceEntry(
                content="以原论文方法作为基线参考",
                classification="to_verify",
                basis="基线",
                source_scope="pipeline",
            )
        ],
    )
    c_no_range, _, _ = evaluate_reproduction_project_v2(
        profile,
        [],
        [valid_bundle],
        view_no_range,
        conversation_id="conv-1",
        evaluation_id="eval-1",
    )
    assert next(c for c in c_no_range if c.criterion_no == 6).score == 1

    # 3. 缺基线（仅有实验）-> 1 分
    c_no_base, _, _ = evaluate_reproduction_project_v2(
        profile,
        [],
        [valid_bundle],
        None,
        conversation_id="conv-1",
        evaluation_id="eval-1",
    )
    assert next(c for c in c_no_base if c.criterion_no == 6).score == 1

    # 4. 三项齐全 -> 满分 2 分
    c_full, _, _ = evaluate_reproduction_project_v2(
        profile,
        [],
        [valid_bundle],
        view_with_baseline_and_range,
        conversation_id="conv-1",
        evaluation_id="eval-1",
    )
    assert next(c for c in c_full if c.criterion_no == 6).score == 2


def test_criterion6_wording_strictly_forbids_bihuan_wancheng_chenggong() -> None:
    """文案审查：准则 6 的依据与改进建议中绝对不得出现“闭环”、“完成”、“成功”。"""
    from code_navi.research.conversation_schemas import (
        ExperimentEvidenceBundle,
        ExperimentEvidenceItem,
    )
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
        ReproductionPipelineEvidenceEntry,
    )

    profile = ResearchProfile(topic="NLP 复现", research_questions=["Q1"])
    valid_bundle = ExperimentEvidenceBundle(
        bundle_id="b-valid",
        conversation_id="conv-1",
        experiment_name=ExperimentEvidenceItem(
            category="metric_or_result",
            content="实验1",
            classification="fact",
            basis="日志",
            source_scope="user_submitted_text",
        ),
        goal=ExperimentEvidenceItem(
            category="metric_or_result",
            content="目标",
            classification="fact",
            basis="日志",
            source_scope="user_submitted_text",
        ),
        items=[
            ExperimentEvidenceItem(
                category="metric_or_result",
                content="准确率 0.85",
                classification="fact",
                basis="输出",
                source_scope="user_submitted_text",
            )
        ],
        submitted_at=datetime.now(UTC),
        provenance_note="用户提交",
    )
    view = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        baseline_entries=[
            ReproductionPipelineEvidenceEntry(
                content="基线区间 [0.80, 0.85]",
                classification="to_verify",
                basis="基线",
                source_scope="pipeline",
            )
        ],
    )
    criteria, _, tasks = evaluate_reproduction_project_v2(
        profile, [], [valid_bundle], view, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit6 = next(c for c in criteria if c.criterion_no == 6)
    assert "闭环" not in crit6.basis
    assert "完成" not in crit6.basis
    assert "成功" not in crit6.basis
    for t in tasks:
        if t.dimension == "execution_evidence":
            assert "闭环" not in t.description
            assert "闭环" not in t.basis


def test_criterion2_counterexamples_steps_without_actionable_variables_scores_one() -> None:
    """反例：多步骤但无具体操作变量/参数说明 -> 严格最多 1 分。"""
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
        ReproductionPipelineEvidenceEntry,
    )

    profile = ResearchProfile(topic="CV 复现", research_questions=["Q1"])
    view = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        step_entries=[
            ReproductionPipelineEvidenceEntry(
                content="第一阶段：数据下载与解压",
                classification="to_verify",
                basis="步骤1",
                source_scope="pipeline",
            ),
            ReproductionPipelineEvidenceEntry(
                content="第二阶段：模型执行与测试",
                classification="to_verify",
                basis="步骤2",
                source_scope="pipeline",
            ),
        ],
    )
    criteria, _, _ = evaluate_reproduction_project_v2(
        profile, [], [], view, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit2 = next(c for c in criteria if c.criterion_no == 2)
    assert crit2.score == 1
    assert "缺少具体可操作的变量" in crit2.basis


def test_criterion2_steps_with_actionable_variables_scores_two() -> None:
    """正例：多步骤且包含学习率/batch/超参数等可操作变量 -> 满分 2 分。"""
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
        ReproductionPipelineEvidenceEntry,
    )

    profile = ResearchProfile(topic="CV 复现", research_questions=["Q1"])
    view = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        step_entries=[
            ReproductionPipelineEvidenceEntry(
                content="步骤1：数据清洗与按 8:2 划分数据集",
                classification="to_verify",
                basis="步骤1",
                source_scope="pipeline",
            ),
            ReproductionPipelineEvidenceEntry(
                content="步骤2：模型微调，设定学习率 lr=1e-4, batch_size=16, 优化器 AdamW",
                classification="to_verify",
                basis="步骤2",
                source_scope="pipeline",
            ),
        ],
    )
    criteria, _, _ = evaluate_reproduction_project_v2(
        profile, [], [], view, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit2 = next(c for c in criteria if c.criterion_no == 2)
    assert crit2.score == 2


def test_criterion5_counterexamples_profile_lacks_time_or_hardware_scores_one() -> None:
    """反例：画像仅有时间无硬件，或仅有硬件无时间 -> 严格最多 1 分。"""
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
        ReproductionPipelineEvidenceEntry,
    )

    view = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        resource_entries=[
            ReproductionPipelineEvidenceEntry(
                content="GPU RTX 3090, 24GB 显存，全量运行预计耗时 3天",
                classification="to_verify",
                basis="资源",
                source_scope="pipeline",
            )
        ],
    )

    # 1. 仅有时间约束（无硬件约束）-> 1 分
    profile_time_only = ResearchProfile(
        topic="CV 复现",
        research_questions=["Q1"],
        constraints=["两周内完成实验"],
    )
    c_time, _, _ = evaluate_reproduction_project_v2(
        profile_time_only, [], [], view, conversation_id="conv-1", evaluation_id="eval-1"
    )
    assert next(c for c in c_time if c.criterion_no == 5).score == 1

    # 2. 仅有硬件约束（无时间约束）-> 1 分
    profile_gpu_only = ResearchProfile(
        topic="CV 复现",
        research_questions=["Q1"],
        constraints=["单卡 GPU 16GB"],
    )
    c_gpu, _, _ = evaluate_reproduction_project_v2(
        profile_gpu_only, [], [], view, conversation_id="conv-1", evaluation_id="eval-1"
    )
    assert next(c for c in c_gpu if c.criterion_no == 5).score == 1

    # 3. 同时具备时间与硬件约束且可用资源满足需求 -> 满分 2 分
    profile_matched = ResearchProfile(
        topic="CV 复现",
        research_questions=["Q1"],
        constraints=["单卡 GPU 24GB 显存", "两周内完成"],
    )
    c_matched, _, _ = evaluate_reproduction_project_v2(
        profile_matched, [], [], view, conversation_id="conv-1", evaluation_id="eval-1"
    )
    assert next(c for c in c_matched if c.criterion_no == 5).score == 2


def test_criterion5_user_has_time_pipeline_lacks_duration_scores_one() -> None:
    """反例：用户有两周时间预算，但方案只有显存需求而没有预计耗时 -> 严格最多 1 分。"""
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
        ReproductionPipelineEvidenceEntry,
    )

    profile_2weeks = ResearchProfile(
        topic="CV 复现",
        research_questions=["Q1"],
        constraints=["单卡 GPU 24GB 显存", "两周内完成"],
    )
    # 方案仅有显存需求，缺少耗时说明
    view_vram_only = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        resource_entries=[
            ReproductionPipelineEvidenceEntry(
                content="计算设备：GPU RTX 3090, 24GB 显存",
                classification="to_verify",
                basis="资源",
                source_scope="pipeline",
            )
        ],
    )
    criteria, _, _ = evaluate_reproduction_project_v2(
        profile_2weeks, [], [], view_vram_only, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit5 = next(c for c in criteria if c.criterion_no == 5)
    assert crit5.score == 1
    assert "尚未记录方案运行的预计耗时" in crit5.basis


def test_criterion5_resource_shortfall_8gb_user_vs_24gb_or_80gb_pipeline_scores_one() -> None:
    """反例：用户仅有 8GB 显存，而 Pipeline 方案需求为 24GB 或 80GB -> 严格最多 1 分。"""
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
        ReproductionPipelineEvidenceEntry,
    )

    profile_8gb = ResearchProfile(
        topic="LLM 复现",
        research_questions=["Q1"],
        constraints=["可用设备：单卡 RTX 2080 8GB 显存", "时间：两周内完成"],
    )

    # 1. 方案需求 24GB 显存 (8GB < 24GB) -> 1 分
    view_24gb = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        resource_entries=[
            ReproductionPipelineEvidenceEntry(
                content="计算资源需求：单卡 RTX 3090 24GB 显存",
                classification="to_verify",
                basis="资源",
                source_scope="pipeline",
            )
        ],
    )
    c_24, _, _ = evaluate_reproduction_project_v2(
        profile_8gb, [], [], view_24gb, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit5_24 = next(c for c in c_24 if c.criterion_no == 5)
    assert crit5_24.score == 1
    assert "超出科研画像记录的用户可用显存（8GB）" in crit5_24.basis

    # 2. 方案需求 80GB 显存 (8GB < 80GB) -> 1 分
    view_80gb = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        resource_entries=[
            ReproductionPipelineEvidenceEntry(
                content="计算资源需求：NVIDIA A100 80GB 显存集群",
                classification="to_verify",
                basis="资源",
                source_scope="pipeline",
            )
        ],
    )
    c_80, _, _ = evaluate_reproduction_project_v2(
        profile_8gb, [], [], view_80gb, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit5_80 = next(c for c in c_80 if c.criterion_no == 5)
    assert crit5_80.score == 1
    assert "超出科研画像记录的用户可用显存（8GB）" in crit5_80.basis


def test_criterion5_time_budget_shortfall_scores_one() -> None:
    """反例：方案预计耗时超出画像记录的时间预算 -> 严格最多 1 分。"""
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
        ReproductionPipelineEvidenceEntry,
    )

    profile_3days = ResearchProfile(
        topic="NLP 复现",
        research_questions=["Q1"],
        constraints=["GPU 24GB 显存", "时间预算：3天"],
    )
    view_7days = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        resource_entries=[
            ReproductionPipelineEvidenceEntry(
                content="单卡 24GB 显存，全量训练预计耗时 7天",
                classification="to_verify",
                basis="资源",
                source_scope="pipeline",
            )
        ],
    )
    c, _, _ = evaluate_reproduction_project_v2(
        profile_3days, [], [], view_7days, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit5 = next(c for c in c if c.criterion_no == 5)
    assert crit5.score == 1
    assert "超出科研画像中的可用时间预算" in crit5.basis


def test_criterion3_cross_entry_url_and_license_split_scores_one() -> None:
    """反例：URL 与许可分散在不同数据集条目中（跨条目拼凑）-> 严格最多 1 分。"""
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
        ReproductionPipelineEvidenceEntry,
    )

    profile = ResearchProfile(topic="CV 复现", research_questions=["Q1"])
    # 条目 1 仅有 URL，条目 2 仅有许可
    view = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        dataset_entries=[
            ReproductionPipelineEvidenceEntry(
                content="数据下载自 https://huggingface.co/datasets/imagenet",
                classification="to_verify",
                basis="数据1",
                source_scope="pipeline",
            ),
            ReproductionPipelineEvidenceEntry(
                content="数据集遵循 CC-BY-4.0 许可协议",
                classification="to_verify",
                basis="数据2",
                source_scope="pipeline",
            ),
        ],
    )
    criteria, _, _ = evaluate_reproduction_project_v2(
        profile, [], [], view, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit3 = next(c for c in criteria if c.criterion_no == 3)
    assert crit3.score == 1
    assert "未在同一数据集条目中同时提供" in crit3.basis


def test_criterion3_fake_url_word_only_scores_one() -> None:
    """反例：仅出现 'URL' 或 '链接' 字样但无真实合规 URL -> 严格最多 1 分。"""
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
        ReproductionPipelineEvidenceEntry,
    )

    profile = ResearchProfile(topic="CV 复现", research_questions=["Q1"])
    view = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        dataset_entries=[
            ReproductionPipelineEvidenceEntry(
                content="数据集已开源，提供可访问的 URL 链接，遵循 MIT 协议",
                classification="to_verify",
                basis="数据",
                source_scope="pipeline",
            )
        ],
    )
    criteria, _, _ = evaluate_reproduction_project_v2(
        profile, [], [], view, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit3 = next(c for c in criteria if c.criterion_no == 3)
    assert crit3.score == 1
    assert "缺少可直接核验的数据集公开获取 URL" in crit3.basis


def test_criterion5_vague_keywords_not_quantifiable_scores_one() -> None:
    """反例：仅有泛泛关键词（如'GPU设备'、'有充足时间'）无量化显存/规格/周期 -> 严格最多 1 分。"""
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
        ReproductionPipelineEvidenceEntry,
    )

    profile_vague = ResearchProfile(
        topic="NLP 复现",
        research_questions=["Q1"],
        constraints=["需要 GPU 设备进行计算", "项目有充足时间预算"],
    )
    view_vague = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        resource_entries=[
            ReproductionPipelineEvidenceEntry(
                content="使用高性能 GPU 设备",
                classification="to_verify",
                basis="资源",
                source_scope="pipeline",
            )
        ],
    )
    criteria, _, _ = evaluate_reproduction_project_v2(
        profile_vague, [], [], view_vague, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit5 = next(c for c in criteria if c.criterion_no == 5)
    assert crit5.score == 1
    assert "缺少可量化对照的显存规格" in crit5.basis


def test_criterion6_single_number_not_range_scores_one() -> None:
    """反例：基线仅有单个数字（如 81.5% 或 0.82）或'目标/阈值'文字而无区间 -> 严格最多 1 分。"""
    from code_navi.research.conversation_schemas import (
        ExperimentEvidenceBundle,
        ExperimentEvidenceItem,
    )
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
        ReproductionPipelineEvidenceEntry,
    )

    profile = ResearchProfile(topic="NLP 复现", research_questions=["Q1"])
    valid_bundle = ExperimentEvidenceBundle(
        bundle_id="b-valid",
        conversation_id="conv-1",
        experiment_name=ExperimentEvidenceItem(
            category="metric_or_result",
            content="实验1",
            classification="fact",
            basis="日志",
            source_scope="user_submitted_text",
        ),
        goal=ExperimentEvidenceItem(
            category="metric_or_result",
            content="测试",
            classification="fact",
            basis="日志",
            source_scope="user_submitted_text",
        ),
        items=[
            ExperimentEvidenceItem(
                category="metric_or_result",
                content="准确率 Micro-F1: 0.835",
                classification="fact",
                basis="输出",
                source_scope="user_submitted_text",
            )
        ],
        submitted_at=datetime.now(UTC),
        provenance_note="用户提交",
    )

    # 1. 仅有单个数值 "81.5%"，无两个边界或波动区间
    view_single_num = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        baseline_entries=[
            ReproductionPipelineEvidenceEntry(
                content="原论文基线准确率为 81.5%",
                classification="to_verify",
                basis="基线",
                source_scope="pipeline",
            )
        ],
    )
    c1, _, _ = evaluate_reproduction_project_v2(
        profile,
        [],
        [valid_bundle],
        view_single_num,
        conversation_id="conv-1",
        evaluation_id="eval-1",
    )
    assert next(c for c in c1 if c.criterion_no == 6).score == 1

    # 2. 仅有"设定目标阈值为 0.85"，无上下界或波动区间
    view_threshold = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        baseline_entries=[
            ReproductionPipelineEvidenceEntry(
                content="基线模型目标阈值设定为 0.85",
                classification="to_verify",
                basis="基线",
                source_scope="pipeline",
            )
        ],
    )
    c2, _, _ = evaluate_reproduction_project_v2(
        profile,
        [],
        [valid_bundle],
        view_threshold,
        conversation_id="conv-1",
        evaluation_id="eval-1",
    )
    assert next(c for c in c2 if c.criterion_no == 6).score == 1


def test_criterion6_non_numerical_or_non_result_evidence_scores_one() -> None:
    """反例：实验记录无数值结果（仅为 setup 描述或无数字）-> 严格最多 1 分。"""
    from code_navi.research.conversation_schemas import (
        ExperimentEvidenceBundle,
        ExperimentEvidenceItem,
    )
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
        ReproductionPipelineEvidenceEntry,
    )

    profile = ResearchProfile(topic="NLP 复现", research_questions=["Q1"])
    view = ReproductionPipelineEvaluationView(
        pipeline_id="pipe-1",
        target_paper_title="Target",
        baseline_entries=[
            ReproductionPipelineEvidenceEntry(
                content="基线区间 [0.80, 0.85]",
                classification="to_verify",
                basis="基线",
                source_scope="pipeline",
            )
        ],
    )

    # 实验证据仅有 setup 描述，无任何数值结果
    setup_only_bundle = ExperimentEvidenceBundle(
        bundle_id="b-setup",
        conversation_id="conv-1",
        experiment_name=ExperimentEvidenceItem(
            category="setup",
            content="环境配置实验",
            classification="fact",
            basis="配置",
            source_scope="user_submitted_text",
        ),
        goal=ExperimentEvidenceItem(
            category="setup",
            content="安装依赖包",
            classification="fact",
            basis="配置",
            source_scope="user_submitted_text",
        ),
        items=[
            ExperimentEvidenceItem(
                category="setup",
                content="成功安装 PyTorch 与 CUDA 环境",
                classification="fact",
                basis="配置",
                source_scope="user_submitted_text",
            )
        ],
        submitted_at=datetime.now(UTC),
        provenance_note="用户提交",
    )
    criteria, _, _ = evaluate_reproduction_project_v2(
        profile, [], [setup_only_bundle], view, conversation_id="conv-1", evaluation_id="eval-1"
    )
    crit6 = next(c for c in criteria if c.criterion_no == 6)
    assert crit6.score == 1
    assert "非失败的数值实验结果证据" in crit6.basis


def test_criterion6_various_strict_numerical_ranges_score_two() -> None:
    """正例：多种合规严格区间格式（均值±波动、~、到、括号区间）配合数值实验证据均得 2 分。"""
    from code_navi.research.conversation_schemas import (
        ExperimentEvidenceBundle,
        ExperimentEvidenceItem,
    )
    from code_navi.research.reproduction_evaluation_schemas import (
        ReproductionPipelineEvaluationView,
        ReproductionPipelineEvidenceEntry,
    )

    profile = ResearchProfile(topic="NLP 复现", research_questions=["Q1"])
    valid_bundle = ExperimentEvidenceBundle(
        bundle_id="b-valid",
        conversation_id="conv-1",
        experiment_name=ExperimentEvidenceItem(
            category="metric_or_result",
            content="实验1",
            classification="fact",
            basis="日志",
            source_scope="user_submitted_text",
        ),
        goal=ExperimentEvidenceItem(
            category="metric_or_result",
            content="评估",
            classification="fact",
            basis="日志",
            source_scope="user_submitted_text",
        ),
        items=[
            ExperimentEvidenceItem(
                category="metric_or_result",
                content="实测 Accuracy: 82.3%",
                classification="fact",
                basis="输出",
                source_scope="user_submitted_text",
            )
        ],
        submitted_at=datetime.now(UTC),
        provenance_note="用户提交",
    )

    valid_ranges = [
        "原论文基准区间 [0.80, 0.85]",
        "原论文基线准确率 81.5% ± 0.5%",
        "基线预期 80.0% ~ 85.0%",
        "基准指标 0.80 到 0.85",
        "预期波动 0.815+-0.005",
    ]

    for range_text in valid_ranges:
        view = ReproductionPipelineEvaluationView(
            pipeline_id="pipe-1",
            target_paper_title="Target",
            baseline_entries=[
                ReproductionPipelineEvidenceEntry(
                    content=range_text,
                    classification="to_verify",
                    basis="基线",
                    source_scope="pipeline",
                )
            ],
        )
        criteria, _, _ = evaluate_reproduction_project_v2(
            profile,
            [],
            [valid_bundle],
            view,
            conversation_id="conv-1",
            evaluation_id="eval-1",
        )
        res_crit = next(c for c in criteria if c.criterion_no == 6)
        assert res_crit.score == 2, f"Failed for {range_text}"
