"""Contract tests for the deterministic research-mindmap Skill."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from code_navi.research.conversation_code_draft import build_experiment_code_draft
from code_navi.research.conversation_difficulty import (
    build_paper_analysis,
    build_topic_difficulty_analysis,
)
from code_navi.research.conversation_experiment import build_experiment_design
from code_navi.research.conversation_mindmap import (
    build_generated_research_mindmap,
    build_research_mindmap,
)
from code_navi.research.conversation_plan import build_conversation_research_plan
from code_navi.research.conversation_schemas import (
    ConversationEvidenceBundle,
    EvidenceReference,
    ResearchProfile,
)
from code_navi.research.research_artifact_llm import ArtifactLlmOutcome
from code_navi.research.schemas import AcademicPaperResult, EvidenceStatement


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


def _paper_analysis_payload(*, url: str, abstract: bool) -> str:
    return json.dumps(
        {
            "title": "模型难点分析",
            "paper_url": url,
            "abstract_available": abstract,
            "items": [
                {
                    "area": "方法难点",
                    "content": "方法定义与对照条件需核验。",
                    "classification": "to_verify",
                    "basis": "仅元数据和摘要范围。",
                    "source_scope": "metadata_and_abstract_only",
                }
            ],
            "provenance_note": "模型基于已保存元数据/摘要生成。",
        },
        ensure_ascii=False,
    )


def test_generated_mindmap_keeps_program_owned_node_identity_and_evidence_boundary() -> None:
    profile = ResearchProfile(
        topic="GCN 在 Cora 节点分类中的复现",
        research_questions=["两层 GCN 是否可在 Cora 上完成节点分类？"],
        methods=["两层 GCN 与 MLP 对照"],
        data_requirements="Cora 数据集",
        constraints=["个人电脑、两周"],
    )
    plan = build_conversation_research_plan(profile, ready_for_plan=True)
    generator = FakeArtifactGenerator(
        ArtifactLlmOutcome.generated(
            json.dumps(
                {
                    "node_details": [
                        {"id": "topic", "detail": "围绕已确认的 GCN 复现范围组织问题。"},
                        {"id": "core-question", "detail": "比较 GCN 与 MLP 的可观察差异。"},
                    ],
                    "recommended_next_action": "先由用户保存一篇原始论文，再核对摘要范围。",
                },
                ensure_ascii=False,
            ),
            run_id="mindmap-run",
            event_count=3,
        )
    )

    mindmap = build_generated_research_mindmap(
        profile,
        plan=plan,
        evidence_bundles=[],
        generator=generator,
        conversation_id="conversation-mindmap",
    )

    topic = next(node for node in mindmap.nodes if node.id == "topic")
    next_step = next(node for node in mindmap.nodes if node.id == "next-step")
    assert generator.calls == ["research_mindmap"]
    assert mindmap.generation_mode == "llm"
    assert mindmap.run_id == "mindmap-run"
    assert topic.detail == "围绕已确认的 GCN 复现范围组织问题。"
    assert topic.status == "confirmed"
    assert next_step.detail == "先由用户保存一篇原始论文，再核对摘要范围。"
    assert next_step.section_key is None
    assert all(node.section_key != "model-controlled" for node in mindmap.nodes)
    assert "不下载论文全文" in mindmap.provenance_note


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
    generator = FakeArtifactGenerator(
        ArtifactLlmOutcome.generated(
            json.dumps(
                {
                    "title": "RAG 评测难点",
                    "information_scope": "profile_and_plan_only",
                    "items": [
                        {
                            "area": "方法难点",
                            "content": "建议预先固定检索与回答的对照条件。",
                            "classification": "inference",
                            "basis": "已确认研究问题和方法。",
                            "source_scope": "profile_and_plan_only",
                        },
                        {
                            "area": "数据难点",
                            "content": "检索日志的许可和字段待确认。",
                            "classification": "to_verify",
                            "basis": "当前画像未验证数据条件。",
                            "source_scope": "profile_and_plan_only",
                        },
                    ],
                    "provenance_note": "模型基于已确认画像生成。",
                },
                ensure_ascii=False,
            )
        )
    )

    analysis = build_topic_difficulty_analysis(
        profile, plan=None, evidence_bundles=[], generator=generator, conversation_id="c1"
    )

    assert analysis.schema_version == "topic-difficulty-analysis.v1"
    assert analysis.information_scope == "profile_and_plan_only"
    assert analysis.generation_mode == "llm"
    assert any(item.classification == "inference" for item in analysis.items)
    assert any(item.classification == "to_verify" for item in analysis.items)
    assert all(item.classification != "fact" for item in analysis.items)


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

    generator = FakeArtifactGenerator(
        ArtifactLlmOutcome.generated(
            _paper_analysis_payload(url=paper.url, abstract=False)
        )
    )

    analysis = build_paper_analysis(paper, generator=generator, conversation_id="c1")

    assert analysis.schema_version == "paper-analysis.v1"
    assert analysis.abstract_available is False
    assert analysis.generation_mode == "llm"
    assert all(item.classification == "to_verify" for item in analysis.items)
    assert "不下载全文" in analysis.provenance_note


def test_paper_analysis_keeps_the_selected_evidence_reference() -> None:
    paper = AcademicPaperResult(
        title="Traceable paper",
        authors=["Example Author"],
        year=2025,
        source_name="arXiv",
        url="https://arxiv.org/abs/2501.00001",
        abstract_excerpt="A source-provided abstract.",
        accessed_at=datetime(2026, 8, 3, tzinfo=UTC),
        information_scope="metadata_and_abstract_only",
        metadata_evidence=[],
        supporting_snippets=[],
        relevance=EvidenceStatement(
            content="可能相关。", classification="inference", basis="关键词匹配"
        ),
        verification=EvidenceStatement(
            content="需要阅读全文。", classification="to_verify", basis="只有摘要"
        ),
        full_text_available=False,
    )
    reference = EvidenceReference(
        bundle_id="bundle-traceable",
        paper_url=paper.url,
        title=paper.title,
        source_name=paper.source_name,
        year=paper.year,
        evidence_level="abstract",
        evidence_summary=paper.abstract_excerpt,
    )

    generator = FakeArtifactGenerator(
        ArtifactLlmOutcome.generated(_paper_analysis_payload(url=paper.url, abstract=True))
    )

    analysis = build_paper_analysis(
        paper, evidence_ref=reference, generator=generator, conversation_id="c1"
    )

    assert all(item.evidence_refs == [reference] for item in analysis.items)


def test_experiment_design_keeps_unknown_resources_to_verify() -> None:
    profile = ResearchProfile(
        topic="RAG 回答可信度评测",
        research_questions=["检索质量如何影响回答可信度？"],
        methods=["离线对照评测"],
        constraints=["两周内完成"],
    )
    plan = build_conversation_research_plan(profile, ready_for_plan=True)
    entry = {"content": "x", "classification": "inference", "basis": "b"}
    generator = FakeArtifactGenerator(
        ArtifactLlmOutcome.generated(
            json.dumps(
                {
                    "hypothesis": {
                        "content": "检索质量差异可观察。",
                        "classification": "inference",
                        "basis": "已确认研究问题。",
                    },
                    "variables": [entry],
                    "data_sources": [entry],
                    "baselines": [entry],
                    "metrics": [entry],
                    "steps": [entry],
                    "resources": [
                        {
                            "content": "样本量与许可待确认。",
                            "classification": "to_verify",
                            "basis": "当前约束。",
                        }
                    ],
                    "risks": [entry],
                    "advisor_confirmation_items": [entry],
                    "provenance_note": "模型基于已确认画像生成。",
                },
                ensure_ascii=False,
            )
        )
    )

    design = build_experiment_design(
        profile, plan=plan, generator=generator, conversation_id="c1"
    )

    assert design is not None
    assert design.schema_version == "experiment-design.v1"
    assert design.generation_mode == "llm"
    assert design.hypothesis.classification == "inference"
    assert any(item.classification == "to_verify" for item in design.resources)
    assert "不执行" in design.provenance_note


def test_experiment_code_draft_is_a_non_executable_synthetic_preview() -> None:
    profile = ResearchProfile(topic="RAG 回答可信度评测")
    plan = build_conversation_research_plan(profile, ready_for_plan=True)
    generator = FakeArtifactGenerator(
        ArtifactLlmOutcome.generated(
            json.dumps(
                {
                    "title": "RAG 评测草案",
                    "directory_tree": ["README.md", "src/", "src/data.py", "data/"],
                    "dependencies": ["Python 3.11+（未安装）"],
                    "files": [
                        {
                            "path": "src/data.py",
                            "content": "def load_data():\n    # TODO: 确认许可\n    return []\n",
                        }
                    ],
                    "run_instructions": ["先人工确认 TODO。"],
                    "assumptions": ["默认合成数据。"],
                    "to_verify_items": ["真实数据许可待确认。"],
                    "provenance_note": "模型生成预览；不执行代码。",
                },
                ensure_ascii=False,
            )
        )
    )

    draft = build_experiment_code_draft(
        profile, plan=plan, generator=generator, conversation_id="c1"
    )

    assert draft.schema_version == "experiment-code-draft.v1"
    assert draft.generation_mode == "llm"
    assert "data/" in draft.directory_tree
    assert "TODO" in "\n".join(item.content for item in draft.files)
    assert "不执行" in draft.provenance_note
