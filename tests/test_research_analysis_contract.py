"""Evidence-contract tests for model-authored analysis output (checkpoint 3).

Every generated analysis must answer three questions per item — what it
concludes, why it matters to the current research question, and what to do
next — plus a one-sentence core judgment. Outputs missing any of these are
rejected as ``invalid_output`` instead of reaching the UI as generic prose.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from code_navi.research.conversation_difficulty import (
    build_paper_analysis,
    build_topic_difficulty_analysis,
)
from code_navi.research.conversation_plan import build_llm_research_plan
from code_navi.research.conversation_schemas import ResearchProfile
from code_navi.research.research_artifact_llm import ArtifactLlmOutcome
from code_navi.research.research_generation import ResearchGenerationError
from code_navi.research.schemas import AcademicPaperResult, EvidenceStatement


def _paper_for_analysis() -> AcademicPaperResult:
    return AcademicPaperResult(
        title="Semi-Supervised Classification with Graph Convolutional Networks",
        authors=["Thomas N. Kipf", "Max Welling"],
        source_name="arXiv",
        url="https://example.org/paper",
        abstract_excerpt=(
            "We present a scalable approach for semi-supervised learning "
            "on graph-structured data."
        ),
        accessed_at=datetime(2026, 8, 30, tzinfo=UTC),
        information_scope="metadata_and_abstract_only",
        metadata_evidence=[],
        supporting_snippets=[],
        relevance=EvidenceStatement(
            content="与图节点分类复现相关。",
            classification="inference",
            basis="标题与摘要匹配",
        ),
        verification=EvidenceStatement(
            content="正文细节待核验。",
            classification="to_verify",
            basis="只有摘要",
        ),
        full_text_available=False,
    )


def _rich_paper_analysis_json() -> str:
    item = {
        "area": "方法难点",
        "content": (
            "论文将 semi-supervised 学习与 graph 结构上的谱卷积逐层传播结合，"
            "需核对该 scalable 方法定义与当前任务的匹配条件。"
        ),
        "classification": "inference",
        "basis": "摘要明确说明 graph-structured 数据上的 semi-supervised learning 方法。",
        "source_scope": "metadata_and_abstract_only",
        "relevance": "与当前图节点分类复现目标直接相关，决定模型模块设计。",
        "suggested_action": "在拿到正文前先记录待核验的传播层数与激活函数。",
    }
    return json.dumps(
        {
            "title": (
                "Semi-Supervised Classification with Graph Convolutional Networks"
            ),
            "paper_url": "https://example.org/paper",
            "information_scope": "metadata_and_abstract_only",
            "abstract_available": True,
            "core_judgment": (
                "该论文与当前节点分类复现目标直接对口，但摘要范围外细节仍待核验。"
            ),
            "items": [item],
            "summary": (
                "当前摘要已覆盖问题与方法定位；数据划分、超参数与精度仍需正文核验。"
            ),
            "next_action": "先在元数据范围核对可复现部分，再决定是否读取正文。",
            "provenance_note": "模型基于已保存元数据/摘要生成。",
        },
        ensure_ascii=False,
    )


def _old_paper_analysis_json() -> str:
    return json.dumps(
        {
            "title": (
                "Semi-Supervised Classification with Graph Convolutional Networks"
            ),
            "paper_url": "https://example.org/paper",
            "information_scope": "metadata_and_abstract_only",
            "abstract_available": True,
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


def _rich_topic_difficulty_json() -> str:
    item = {
        "area": "实验设计难点",
        "content": "对照条件与随机种子策略未在画像中确认。",
        "classification": "to_verify",
        "basis": "当前画像没有实验设置信息。",
        "source_scope": "profile_and_plan_only",
        "relevance": "直接影响两周 MVP 能否给出可信比较。",
        "suggested_action": "在检索文献后先固定一条对照实验设计。",
    }
    return json.dumps(
        {
            "title": "方向难点分析",
            "information_scope": "profile_and_plan_only",
            "core_judgment": "当前画像缺少实验设置与数据条件，是进入检索前的主要缺口。",
            "items": [item],
            "next_action": "补充数据条件后生成研究计划。",
            "provenance_note": "模型基于已确认画像生成。",
        },
        ensure_ascii=False,
    )


def _old_topic_difficulty_json() -> str:
    return json.dumps(
        {
            "title": "方向难点分析",
            "information_scope": "profile_and_plan_only",
            "items": [
                {
                    "area": "数据难点",
                    "content": "数据来源待确认。",
                    "classification": "to_verify",
                    "basis": "画像未覆盖。",
                    "source_scope": "profile_and_plan_only",
                }
            ],
            "provenance_note": "模型基于已确认画像生成。",
        },
        ensure_ascii=False,
    )


def _rich_plan_json() -> str:
    entry = {
        "content": "比较两层谱卷积与基线在 Cora 上的表现。",
        "classification": "inference",
        "basis": "已确认主题为图卷积网络复现。",
        "relevance": "直接对应研究目标中的可比性要求。",
        "suggested_action": "先在元数据范围核对基线来源。",
    }
    return json.dumps(
        {
            "research_title": entry,
            "research_goal": entry,
            "candidate_methods_or_baselines": [entry],
            "suggested_datasets_or_metrics": [entry],
            "two_week_mvp_plan": [entry],
            "risks_and_mitigations": [
                {
                    "risk": {
                        "content": "数据划分未知导致结果不可比。",
                        "classification": "to_verify",
                        "basis": "画像未覆盖数据划分。",
                        "relevance": "影响全部精度比较。",
                        "suggested_action": "阅读正文确认划分方式。",
                    },
                    "mitigation": {
                        "content": "先记录待核验项再设计实验。",
                        "classification": "inference",
                        "basis": "当前只有摘要范围。",
                        "relevance": "保证计划可执行。",
                        "suggested_action": "把划分方式列入第一周核对清单。",
                    },
                }
            ],
            "suggested_search_keywords": ["graph convolutional network"],
            "pending_items": [],
            "core_judgment": "画像已达到计划准入条件，缺数据划分信息。",
            "next_action": "检索并保存原始论文。",
            "provenance_note": "模型生成。",
        },
        ensure_ascii=False,
    )


def _old_plan_json() -> str:
    entry = {
        "content": "比较两层谱卷积与基线的表现。",
        "classification": "inference",
        "basis": "已确认主题。",
    }
    return json.dumps(
        {
            "research_title": entry,
            "research_goal": entry,
            "candidate_methods_or_baselines": [entry],
            "suggested_datasets_or_metrics": [entry],
            "two_week_mvp_plan": [entry],
            "risks_and_mitigations": [
                {"risk": entry, "mitigation": entry},
            ],
            "suggested_search_keywords": ["graph convolutional network"],
            "pending_items": [],
            "provenance_note": "模型生成。",
        },
        ensure_ascii=False,
    )


class _StaticGenerator:
    def __init__(self, text: str, run_id: str = "contract-run") -> None:
        self.text = text
        self.run_id = run_id

    def generate(self, **_: object) -> ArtifactLlmOutcome:
        return ArtifactLlmOutcome.generated(self.text, run_id=self.run_id, event_count=1)


def test_paper_analysis_output_carries_core_judgment_relevance_and_actions() -> None:
    analysis = build_paper_analysis(
        _paper_for_analysis(),
        generator=_StaticGenerator(_rich_paper_analysis_json(), "pa-run"),
        conversation_id="c-3a",
    )

    assert analysis.generation_mode == "llm"
    assert analysis.run_id == "pa-run"
    assert analysis.core_judgment
    assert analysis.next_action
    assert analysis.summary
    item = analysis.items[0]
    assert item.relevance
    assert item.suggested_action


def test_paper_analysis_rejects_items_without_relevance_or_action() -> None:
    with pytest.raises(ResearchGenerationError) as error:
        build_paper_analysis(
            _paper_for_analysis(),
            generator=_StaticGenerator(_old_paper_analysis_json()),
            conversation_id="c-3a",
        )

    assert error.value.stage == "invalid_output"


def test_paper_analysis_maps_timeout_and_invalid_json_to_typed_stages() -> None:
    class TimeoutGenerator:
        def generate(self, **_: object) -> ArtifactLlmOutcome:
            return ArtifactLlmOutcome.failed("provider request timed out")

    with pytest.raises(ResearchGenerationError) as timeout_error:
        build_paper_analysis(
            _paper_for_analysis(),
            generator=TimeoutGenerator(),
            conversation_id="c-3a",
        )
    assert timeout_error.value.stage == "timeout"

    with pytest.raises(ResearchGenerationError) as invalid_error:
        build_paper_analysis(
            _paper_for_analysis(),
            generator=_StaticGenerator("not-json"),
            conversation_id="c-3a",
        )
    assert invalid_error.value.stage == "invalid_output"


def test_topic_difficulty_output_carries_core_judgment_and_relevance() -> None:
    analysis = build_topic_difficulty_analysis(
        ResearchProfile(topic="图神经网络复现"),
        plan=None,
        evidence_bundles=[],
        generator=_StaticGenerator(_rich_topic_difficulty_json(), "topic-run"),
        conversation_id="c-3t",
    )

    assert analysis.generation_mode == "llm"
    assert analysis.core_judgment
    assert analysis.next_action
    assert analysis.items[0].relevance
    assert analysis.items[0].suggested_action


def test_topic_difficulty_rejects_output_without_relevance_or_action() -> None:
    with pytest.raises(ResearchGenerationError) as error:
        build_topic_difficulty_analysis(
            ResearchProfile(topic="图神经网络复现"),
            plan=None,
            evidence_bundles=[],
            generator=_StaticGenerator(_old_topic_difficulty_json()),
            conversation_id="c-3t",
        )

    assert error.value.stage == "invalid_output"


def test_research_plan_entries_carry_relevance_and_action() -> None:
    plan = build_llm_research_plan(
        ResearchProfile(topic="图卷积网络复现", research_questions=["如何比较方法？"]),
        generator=_StaticGenerator(_rich_plan_json(), "plan-run-3"),
        conversation_id="c-3p",
    )

    assert plan is not None
    assert plan.core_judgment
    assert plan.next_action
    goal = plan.research_goal
    assert goal.relevance
    assert goal.suggested_action
    assert plan.risks_and_mitigations[0].risk.relevance


def test_research_plan_rejects_entries_without_relevance_or_action() -> None:
    with pytest.raises(ResearchGenerationError) as error:
        build_llm_research_plan(
            ResearchProfile(topic="图卷积网络", research_questions=["如何比较方法？"]),
            generator=_StaticGenerator(_old_plan_json()),
            conversation_id="c-3p",
        )

    assert error.value.stage == "invalid_output"


def test_paper_analysis_rejects_items_unrelated_to_saved_material() -> None:
    payload = json.loads(_rich_paper_analysis_json())
    payload["items"] = [
        {
            "area": "烹饪难点",
            "content": "建议注意火候并进一步研究调味方案。",
            "classification": "to_verify",
            "basis": "通用研究经验。",
            "source_scope": "metadata_and_abstract_only",
            "relevance": "与任何研究都相关。",
            "suggested_action": "继续努力。",
        }
    ]
    text = json.dumps(payload, ensure_ascii=False)

    with pytest.raises(ResearchGenerationError) as error:
        build_paper_analysis(
            _paper_for_analysis(),
            generator=_StaticGenerator(text),
            conversation_id="c-3a",
        )

    assert error.value.stage == "invalid_output"


def test_agent_prompt_carries_negative_list_and_context_carries_full_materials() -> None:
    from code_navi.research.research_artifact_llm import research_artifact_agent

    assert "反面清单" in research_artifact_agent.system_prompt
    assert "禁止通用鼓励话术" in research_artifact_agent.system_prompt
    assert "引用不到具体内容就不要写那条" in research_artifact_agent.system_prompt

    captured: dict[str, object] = {}

    class CapturingGenerator:
        def generate(self, *, context: dict[str, object], **_: object) -> ArtifactLlmOutcome:
            captured.update(context)
            return ArtifactLlmOutcome.generated(_rich_paper_analysis_json())

    paper = _paper_for_analysis()
    build_paper_analysis(
        paper,
        generator=CapturingGenerator(),
        conversation_id="c-3a",
        research_context={"research_question": "如何比较方法？"},
    )

    context_paper = captured["paper"]
    assert context_paper["abstract_excerpt"] == paper.abstract_excerpt
    assert captured["research_context"]["research_question"] == "如何比较方法？"
    guidance = " ".join(captured["writing_guidance"])
    assert "core_judgment" in guidance
    assert "不使用空洞的鼓励话术" in guidance
