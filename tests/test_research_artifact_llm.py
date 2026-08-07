"""Safety contracts for provider-enhanced research artefacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from code_navi.research.conversation_code_draft import build_experiment_code_draft
from code_navi.research.conversation_difficulty import build_topic_difficulty_analysis
from code_navi.research.conversation_experiment import build_experiment_design
from code_navi.research.conversation_plan import build_conversation_research_plan
from code_navi.research.conversation_schemas import (
    ConversationEvidenceBundle,
    ResearchProfile,
)
from code_navi.research.research_artifact_llm import (
    ArtifactLlmOutcome,
    RuntimeResearchArtifactGenerator,
)
from code_navi.research.schemas import AcademicPaperResult, EvidenceStatement
from kernel.core import ContentBlock, Message, ProviderCapabilities, ProviderResult


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
        assert conversation_id
        self.calls.append(kind)
        return self.outcome


def _profile() -> ResearchProfile:
    return ResearchProfile(
        topic="学习反馈策略",
        research_questions=["即时反馈是否改善学习表现？"],
        context="本科课程",
        methods=["对比实验"],
        data_requirements="匿名课程作业记录",
        constraints=["两周内完成"],
        expected_output="课程项目报告",
    )


def test_difficulty_uses_validated_model_wording_without_changing_fact_boundary() -> None:
    profile = _profile()
    plan = build_conversation_research_plan(profile, ready_for_plan=True)
    generator = FakeArtifactGenerator(
        ArtifactLlmOutcome.generated(
            '{"title":"个性化难点","information_scope":"profile_and_plan_only",'
            '"items":[{"area":"方法难点","content":"建议先固定即时与延迟反馈的比较条件。",'
            '"classification":"inference","basis":"已确认研究问题和对比实验方法。",'
            '"source_scope":"profile_and_plan_only"}],'
            '"provenance_note":"模型根据已确认画像提出建议，仍需验证。"}'
        )
    )

    analysis = build_topic_difficulty_analysis(
        profile,
        plan=plan,
        evidence_bundles=[],
        generator=generator,
        conversation_id="conv-test",
    )

    assert generator.calls == ["topic_difficulty_analysis"]
    assert analysis.generation_mode == "llm"
    assert analysis.items[0].classification == "inference"


def test_evidence_scoped_model_difficulty_keeps_a_saved_evidence_reference() -> None:
    paper = AcademicPaperResult(
        title="Traceable feedback study",
        authors=["Example Author"],
        year=2025,
        source_name="arXiv",
        url="https://arxiv.org/abs/2501.00001",
        abstract_excerpt="A source-provided abstract about feedback.",
        accessed_at=datetime(2026, 8, 7, tzinfo=UTC),
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
    bundle = ConversationEvidenceBundle(
        bundle_id="bundle-model-trace",
        conversation_id="conv-test",
        query="feedback study",
        requested_sources=["arxiv"],
        allowed_sources=["arxiv"],
        queried_sources=["arxiv"],
        source_statuses=[],
        searched_at=datetime(2026, 8, 7, tzinfo=UTC),
        papers=[paper],
        source_links=[paper.url],
        failure_reasons=[],
        provenance_note="仅元数据和摘要。",
    )
    generator = FakeArtifactGenerator(
        ArtifactLlmOutcome.generated(
            json.dumps(
                {
                    "title": "证据关联难点",
                    "information_scope": "metadata_and_abstract_only",
                    "items": [
                        {
                            "area": "方法难点",
                            "content": "建议核验摘要中描述的方法边界。",
                            "classification": "inference",
                            "basis": "所选论文摘要",
                            "source_scope": "metadata_and_abstract_only",
                            "evidence_refs": [
                                {
                                    "bundle_id": bundle.bundle_id,
                                    "paper_url": paper.url,
                                    "title": paper.title,
                                    "source_name": paper.source_name,
                                    "year": paper.year,
                                    "evidence_level": "abstract",
                                    "evidence_summary": paper.abstract_excerpt,
                                }
                            ],
                        }
                    ],
                    "provenance_note": "建议关联到已保存摘要。",
                },
                ensure_ascii=False,
            )
        )
    )

    analysis = build_topic_difficulty_analysis(
        _profile(),
        plan=build_conversation_research_plan(_profile(), ready_for_plan=True),
        evidence_bundles=[bundle],
        generator=generator,
        conversation_id="conv-test",
    )

    assert analysis.generation_mode == "llm"
    assert analysis.items[0].evidence_refs[0].bundle_id == bundle.bundle_id


def test_invalid_model_fact_claim_falls_back_to_rules() -> None:
    generator = FakeArtifactGenerator(
        ArtifactLlmOutcome.generated(
            '{"title":"不安全","information_scope":"profile_and_plan_only",'
            '"items":[{"area":"实验结论","content":"模型声称得到结果",'
            '"classification":"fact","basis":"没有可核验来源",'
            '"source_scope":"profile_and_plan_only"}],'
            '"provenance_note":"不安全"}'
        )
    )

    analysis = build_topic_difficulty_analysis(
        _profile(),
        plan=None,
        evidence_bundles=[],
        generator=generator,
        conversation_id="conv-test",
    )

    assert analysis.generation_mode == "rules_fallback"
    assert all(item.content != "模型声称得到结果" for item in analysis.items)


def test_unavailable_model_keeps_rules_difficulty_analysis() -> None:
    analysis = build_topic_difficulty_analysis(
        _profile(),
        plan=None,
        evidence_bundles=[],
        generator=FakeArtifactGenerator(ArtifactLlmOutcome.unavailable()),
        conversation_id="conv-test",
    )

    assert analysis.generation_mode == "rules"


class FakeDeepSeekProvider:
    capabilities = ProviderCapabilities()

    def __init__(self, text: str | Exception) -> None:
        self.text = text

    def complete(self, _messages: object, tools: object = ()) -> ProviderResult:
        del tools
        if isinstance(self.text, Exception):
            raise self.text
        return ProviderResult(
            Message("assistant", (ContentBlock("text", {"text": self.text}),))
        )


def test_deepseek_artifact_generator_uses_existing_settings_with_mock_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-" + "a" * 32)
    monkeypatch.setenv("CODE_NAVI_EVENTS_DIR", str(tmp_path))
    monkeypatch.setattr(
        "code_navi.research.research_artifact_llm.DeepSeekGuidanceProvider",
        lambda **_kwargs: FakeDeepSeekProvider('{"title":"ok"}'),
    )

    outcome = RuntimeResearchArtifactGenerator().generate(
        kind="topic_difficulty_analysis",
        context={"profile": {}},
        conversation_id="conv-test",
    )

    assert outcome.status == "generated", outcome.reason
    assert outcome.text == '{"title":"ok"}'
    assert outcome.run_id
    assert outcome.event_count > 0
    assert list(tmp_path.rglob("*.jsonl"))


def test_deepseek_artifact_generator_without_key_is_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    assert RuntimeResearchArtifactGenerator().generate(
        kind="topic_difficulty_analysis",
        context={},
        conversation_id="conv-test",
    ).status == "unavailable"


@pytest.mark.parametrize("failure", [TimeoutError("timeout"), OSError("network down")])
def test_deepseek_artifact_generator_turns_provider_failures_into_fallback_status(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-" + "a" * 32)
    monkeypatch.setattr(
        "code_navi.research.research_artifact_llm.DeepSeekGuidanceProvider",
        lambda **_kwargs: FakeDeepSeekProvider(failure),
    )

    assert RuntimeResearchArtifactGenerator().generate(
        kind="topic_difficulty_analysis",
        context={},
        conversation_id="conv-test",
    ).status == "failed"


def test_experiment_design_uses_validated_model_suggestions_after_plan_exists() -> None:
    profile = _profile()
    plan = build_conversation_research_plan(profile, ready_for_plan=True)
    generator = FakeArtifactGenerator(
        ArtifactLlmOutcome.generated(
            '{"hypothesis":{"content":"建议检验即时反馈与延迟反馈的差异。",'
            '"classification":"inference","basis":"已确认研究问题。"},'
            '"variables":[{"content":"反馈时机需要预先固定。","classification":"inference","basis":"比较实验方法。"}],'
            '"data_sources":[{"content":"匿名课程作业记录的许可和字段待确认。","classification":"to_verify","basis":"数据条件尚未验证。"}],'
            '"baselines":[{"content":"以延迟反馈作为候选对照。","classification":"inference","basis":"已确认比较方向。"}],'
            '"metrics":[{"content":"主指标与阈值需导师确认。","classification":"to_verify","basis":"当前没有已验证指标。"}],'
            '"steps":[{"content":"第一周完成最小数据检查。","classification":"inference","basis":"两周约束。"}],'
            '"resources":[{"content":"样本量与伦理条件待确认。","classification":"to_verify","basis":"当前约束范围。"}],'
            '"risks":[{"content":"样本不足风险需记录。","classification":"to_verify","basis":"没有样本量事实。"}],'
            '"advisor_confirmation_items":[{"content":"确认数据许可。","classification":"to_verify","basis":"需要导师确认。"}],'
            '"provenance_note":"模型基于已确认上下文生成建议，未验证资源可用性。"}'
        )
    )

    design = build_experiment_design(
        profile,
        plan=plan,
        generator=generator,
        conversation_id="conv-test",
    )

    assert design is not None
    assert generator.calls == ["experiment_design"]
    assert design.generation_mode == "llm"
    assert all(
        item.classification in {"inference", "to_verify"}
        for item in [design.hypothesis, *design.resources]
    )


def test_failed_experiment_design_model_uses_rules_fallback() -> None:
    profile = _profile()
    design = build_experiment_design(
        profile,
        plan=build_conversation_research_plan(profile, ready_for_plan=True),
        generator=FakeArtifactGenerator(ArtifactLlmOutcome.generated("not-json")),
        conversation_id="conv-test",
    )

    assert design is not None
    assert design.generation_mode == "rules_fallback"


def test_code_draft_uses_safe_model_preview_only_after_existing_plan() -> None:
    profile = _profile()
    plan = build_conversation_research_plan(profile, ready_for_plan=True)
    generator = FakeArtifactGenerator(
        ArtifactLlmOutcome.generated(
            json.dumps(
                {
                    "title": "反馈策略实验草案",
                    "assumptions": ["默认使用合成数据。"],
                    "to_verify_items": ["真实数据许可待确认。"],
                    "provenance_note": "模型只个性化说明，代码文件来自服务端固定模板。",
                },
                ensure_ascii=False,
            )
        )
    )

    draft = build_experiment_code_draft(
        profile,
        plan=plan,
        generator=generator,
        conversation_id="conv-test",
    )

    assert draft.generation_mode == "llm"
    assert generator.calls == ["experiment_code_draft"]
    assert any(item.path == "requirements.txt" for item in draft.files)


def test_model_cannot_replace_server_owned_code_templates() -> None:
    profile = _profile()
    draft = build_experiment_code_draft(
        profile,
        plan=build_conversation_research_plan(profile, ready_for_plan=True),
        generator=FakeArtifactGenerator(
            ArtifactLlmOutcome.generated(json.dumps({
                "title": "unsafe",
                "files": [{"path": "src/data.py", "content": "api_key = 'secret'"}],
                "assumptions": ["x"],
                "to_verify_items": ["x"],
                "provenance_note": "x",
            }))
        ),
        conversation_id="conv-test",
    )

    assert draft.generation_mode == "rules_fallback"
    assert "api_key" not in "\n".join(item.content.casefold() for item in draft.files)
