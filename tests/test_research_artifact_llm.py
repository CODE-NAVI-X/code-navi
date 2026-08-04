"""Safety contracts for provider-enhanced research artefacts."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from code_navi.research.conversation_difficulty import build_topic_difficulty_analysis
from code_navi.research.conversation_plan import build_conversation_research_plan
from code_navi.research.conversation_schemas import ResearchProfile
from code_navi.research.research_artifact_llm import (
    ArtifactLlmOutcome,
    DeepSeekResearchArtifactGenerator,
)
from kernel.core import ContentBlock, Message


class FakeArtifactGenerator:
    def __init__(self, outcome: ArtifactLlmOutcome) -> None:
        self.outcome = outcome
        self.calls: list[str] = []

    def generate(self, *, kind: str, context: dict[str, object]) -> ArtifactLlmOutcome:
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
        profile, plan=plan, evidence_bundles=[], generator=generator
    )

    assert generator.calls == ["topic_difficulty_analysis"]
    assert analysis.generation_mode == "llm"
    assert analysis.items[0].classification == "inference"


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
        _profile(), plan=None, evidence_bundles=[], generator=generator
    )

    assert analysis.generation_mode == "rules_fallback"
    assert all(item.content != "模型声称得到结果" for item in analysis.items)


def test_unavailable_model_keeps_rules_difficulty_analysis() -> None:
    analysis = build_topic_difficulty_analysis(
        _profile(),
        plan=None,
        evidence_bundles=[],
        generator=FakeArtifactGenerator(ArtifactLlmOutcome.unavailable()),
    )

    assert analysis.generation_mode == "rules"


class FakeDeepSeekProvider:
    def __init__(self, text: str | Exception) -> None:
        self.text = text

    def complete(self, _messages: object) -> SimpleNamespace:
        if isinstance(self.text, Exception):
            raise self.text
        return SimpleNamespace(
            message=Message("assistant", (ContentBlock("text", {"text": self.text}),))
        )


def test_deepseek_artifact_generator_uses_existing_settings_with_mock_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-" + "a" * 32)
    monkeypatch.setattr(
        "code_navi.research.research_artifact_llm.DeepSeekGuidanceProvider",
        lambda: FakeDeepSeekProvider('{"title":"ok"}'),
    )

    outcome = DeepSeekResearchArtifactGenerator().generate(
        kind="topic_difficulty_analysis", context={"profile": {}}
    )

    assert outcome.status == "generated"
    assert outcome.text == '{"title":"ok"}'


def test_deepseek_artifact_generator_without_key_is_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    assert DeepSeekResearchArtifactGenerator().generate(
        kind="topic_difficulty_analysis", context={}
    ).status == "unavailable"


@pytest.mark.parametrize("failure", [TimeoutError("timeout"), OSError("network down")])
def test_deepseek_artifact_generator_turns_provider_failures_into_fallback_status(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-" + "a" * 32)
    monkeypatch.setattr(
        "code_navi.research.research_artifact_llm.DeepSeekGuidanceProvider",
        lambda: FakeDeepSeekProvider(failure),
    )

    assert DeepSeekResearchArtifactGenerator().generate(
        kind="topic_difficulty_analysis", context={}
    ).status == "failed"
