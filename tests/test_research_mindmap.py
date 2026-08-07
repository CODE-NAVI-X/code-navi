"""Contract tests for the deterministic research-mindmap Skill."""

from __future__ import annotations

from datetime import UTC, datetime

from code_navi.research.conversation_code_draft import build_experiment_code_draft
from code_navi.research.conversation_difficulty import (
    build_paper_analysis,
    build_topic_difficulty_analysis,
)
from code_navi.research.conversation_experiment import build_experiment_design
from code_navi.research.conversation_mindmap import build_research_mindmap
from code_navi.research.conversation_plan import build_conversation_research_plan
from code_navi.research.conversation_schemas import (
    ConversationEvidenceBundle,
    ResearchProfile,
)
from code_navi.research.schemas import AcademicPaperResult, EvidenceStatement


def test_mindmap_traces_profile_plan_risk_and_missing_information() -> None:
    profile = ResearchProfile(
        topic="RAG 回答可信度评测",
        research_questions=["检索质量如何影响回答可信度？"],
        context="高校课程知识库",
        methods=["离线对照评测"],
        data_requirements="公开课程材料与检索日志",
        constraints=["两周内完成最小验证"],
        expected_output="研究简报与可复现评测原型",
        uncertainties=["尚未确定评价指标"],
    )
    plan = build_conversation_research_plan(profile, ready_for_plan=True)

    mindmap = build_research_mindmap(profile, plan=plan, evidence_bundles=[])

    assert mindmap.schema_version == "research-mindmap.v1"
    assert mindmap.root_node_id == "topic"
    assert {node.id for node in mindmap.nodes} >= {
        "topic",
        "core-question",
        "method-data",
        "constraints",
        "expected-output",
        "research-plan",
        "risks",
        "to-verify",
    }
    assert any(node.status == "confirmed" for node in mindmap.nodes)
    assert any(node.status == "inference" for node in mindmap.nodes)
    assert any(node.status == "to_verify" for node in mindmap.nodes)
    assert all(edge.source_id != edge.target_id for edge in mindmap.edges)
    assert "不访问模型或网络" in mindmap.provenance_note


def test_mindmap_marks_saved_paper_metadata_as_evidence_instead_of_a_fact_claim() -> None:
    accessed_at = datetime(2026, 8, 3, tzinfo=UTC)
    paper = AcademicPaperResult(
        title="A traceable RAG evaluation paper",
        authors=["Example Author"],
        source_name="arXiv",
        url="https://arxiv.org/abs/1234.5678",
        abstract_excerpt="An abstract supplied by the configured source.",
        accessed_at=accessed_at,
        information_scope="metadata_and_abstract_only",
        metadata_evidence=[
            EvidenceStatement(
                content="标题来自来源元数据。",
                classification="fact",
                source_url="https://arxiv.org/abs/1234.5678",
                basis="arXiv 元数据",
            )
        ],
        supporting_snippets=[],
        relevance=EvidenceStatement(
            content="与检索质量关键词相关。",
            classification="inference",
            basis="关键词匹配",
        ),
        verification=EvidenceStatement(
            content="需要阅读全文核验实验设置。",
            classification="to_verify",
            basis="当前只有摘要",
        ),
        full_text_available=False,
    )
    bundle = ConversationEvidenceBundle(
        bundle_id="bundle-1",
        conversation_id="conversation-1",
        query="RAG evaluation",
        requested_sources=["arxiv"],
        allowed_sources=["arxiv"],
        queried_sources=["arxiv"],
        source_statuses=[],
        searched_at=accessed_at,
        papers=[paper],
        source_links=[paper.url],
        failure_reasons=[],
        provenance_note="仅元数据和摘要。",
    )

    mindmap = build_research_mindmap(
        ResearchProfile(topic="RAG 评测"), plan=None, evidence_bundles=[bundle]
    )

    evidence_node = next(node for node in mindmap.nodes if node.id == "evidence-1")
    assert evidence_node.status == "evidence"
    assert evidence_node.sources[0].url == paper.url
    assert evidence_node.sources[0].accessed_at == accessed_at


def test_topic_difficulty_analysis_marks_unverified_feasibility_as_to_verify() -> None:
    profile = ResearchProfile(
        topic="RAG 回答可信度评测",
        research_questions=["检索质量如何影响回答可信度？"],
        context="高校课程知识库",
    )

    analysis = build_topic_difficulty_analysis(profile, plan=None, evidence_bundles=[])

    assert analysis.schema_version == "topic-difficulty-analysis.v1"
    assert analysis.information_scope == "profile_and_plan_only"
    assert any(item.classification == "inference" for item in analysis.items)
    assert any(item.classification == "to_verify" for item in analysis.items)
    assert all("论文结论" not in item.content for item in analysis.items)


def test_paper_analysis_without_an_abstract_returns_only_verification_gaps() -> None:
    paper = AcademicPaperResult(
        title="Metadata-only paper",
        authors=["Example Author"],
        source_name="Crossref",
        url="https://doi.org/10.0000/example",
        accessed_at=datetime(2026, 8, 3, tzinfo=UTC),
        information_scope="metadata_and_abstract_only",
        metadata_evidence=[],
        supporting_snippets=[],
        relevance=EvidenceStatement(
            content="可能相关。", classification="inference", basis="关键词匹配"
        ),
        verification=EvidenceStatement(
            content="需要阅读全文。", classification="to_verify", basis="只有元数据"
        ),
        full_text_available=False,
    )

    analysis = build_paper_analysis(paper)

    assert analysis.schema_version == "paper-analysis.v1"
    assert analysis.abstract_available is False
    assert all(item.classification == "to_verify" for item in analysis.items[1:])
    assert "不下载全文" in analysis.provenance_note


def test_experiment_design_is_rules_only_and_keeps_unknown_resources_to_verify() -> None:
    profile = ResearchProfile(
        topic="RAG 回答可信度评测",
        research_questions=["检索质量如何影响回答可信度？"],
        methods=["离线对照评测"],
        constraints=["两周内完成"],
    )
    plan = build_conversation_research_plan(profile, ready_for_plan=True)

    design = build_experiment_design(profile, plan=plan)

    assert design.schema_version == "experiment-design.v1"
    assert design.hypothesis.classification == "inference"
    assert any(item.classification == "to_verify" for item in design.resources)
    assert "不执行代码" in design.provenance_note


def test_experiment_code_draft_is_a_non_executable_synthetic_preview() -> None:
    draft = build_experiment_code_draft(
        ResearchProfile(topic="RAG 回答可信度评测"),
        plan=build_conversation_research_plan(
            ResearchProfile(topic="RAG 回答可信度评测"), ready_for_plan=True
        ),
    )

    assert draft.schema_version == "experiment-code-draft.v1"
    assert "data/" in draft.directory_tree
    assert "TODO" in "\n".join(item.content for item in draft.files)
    assert "不执行" in draft.provenance_note
