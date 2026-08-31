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
    _redact_local_context,
)
from code_navi.research.research_generation import ResearchGenerationError
from code_navi.research.schemas import AcademicPaperResult, EvidenceStatement
from kernel.core import ContentBlock, Message, ProviderCapabilities, ProviderResult


class FakeArtifactGenerator:
    def __init__(self, outcome: ArtifactLlmOutcome) -> None:
        self.outcome = outcome
        self.calls: list[str] = []
        self.contexts: list[dict[str, object]] = []

    def generate(
        self,
        *,
        kind: str,
        context: dict[str, object],
        conversation_id: str,
    ) -> ArtifactLlmOutcome:
        assert conversation_id
        self.calls.append(kind)
        self.contexts.append(context)
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


def test_selected_paper_reference_remains_allowed_after_context_paper_limit() -> None:
    from code_navi.research.conversation_schemas import EvidenceReference

    papers = [
        AcademicPaperResult(
            title=f"Saved paper {index}",
            authors=["Example Author"],
            year=2025,
            source_name="OpenAlex",
            url=f"https://openalex.org/W{index:08d}",
            abstract_excerpt="A saved abstract.",
            accessed_at=datetime(2026, 8, 7, tzinfo=UTC),
            information_scope="metadata_and_abstract_only",
            metadata_evidence=[],
            supporting_snippets=[],
            relevance=EvidenceStatement(
                content="可能相关。", classification="inference", basis="关键词匹配"
            ),
            verification=EvidenceStatement(
                content="需要核验。", classification="to_verify", basis="只有摘要"
            ),
            full_text_available=False,
        )
        for index in range(10)
    ]
    bundle = ConversationEvidenceBundle(
        bundle_id="bundle-selected-paper",
        conversation_id="conv-test",
        query="selected paper",
        requested_sources=["openalex"],
        allowed_sources=["openalex"],
        queried_sources=["openalex"],
        source_statuses=[],
        searched_at=datetime(2026, 8, 7, tzinfo=UTC),
        papers=papers,
        source_links=[paper.url for paper in papers],
        failure_reasons=[],
        provenance_note="仅元数据和摘要。",
    )
    selected_ref = EvidenceReference(
        bundle_id=bundle.bundle_id,
        paper_url=papers[9].url,
        title=papers[9].title,
        source_name=papers[9].source_name,
        year=papers[9].year,
        evidence_level="abstract",
        evidence_summary=papers[9].abstract_excerpt,
    )
    from code_navi.research.conversation_schemas import PaperAnalysis, ResearchAnalysisItem

    selected_analysis = PaperAnalysis(
        title=papers[9].title,
        paper_url=papers[9].url,
        information_scope="metadata_and_abstract_only",
        abstract_available=True,
        items=[
            ResearchAnalysisItem(
                area="方法",
                content="选中论文的摘要方法需要纳入难点分析。",
                classification="inference",
                basis="论文摘要",
                source_scope="metadata_and_abstract_only",
                evidence_refs=[selected_ref],
            )
        ],
        provenance_note="模型分析。",
    )
    generator = FakeArtifactGenerator(
        ArtifactLlmOutcome.generated(
            json.dumps(
                {
                    "title": "选中论文难点",
                    "information_scope": "metadata_and_abstract_only",
                    "items": [
                        {
                            "area": "方法难点",
                            "content": "选中论文摘要中的方法需要进一步核验。",
                            "classification": "inference",
                            "basis": "选中论文摘要",
                            "source_scope": "metadata_and_abstract_only",
                            "evidence_refs": [selected_ref.model_dump(mode="json")],
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
        paper_analysis=selected_analysis,
        generator=generator,
        conversation_id="conv-test",
    )

    assert analysis.items[0].evidence_refs[0].paper_url == papers[9].url


def test_model_fact_claim_is_rejected_as_invalid_output() -> None:
    generator = FakeArtifactGenerator(
        ArtifactLlmOutcome.generated(
            '{"title":"不安全","information_scope":"profile_and_plan_only",'
            '"items":[{"area":"实验结论","content":"模型声称得到结果",'
            '"classification":"fact","basis":"没有可核验来源",'
            '"source_scope":"profile_and_plan_only"}],'
            '"provenance_note":"不安全"}'
        )
    )

    with pytest.raises(ResearchGenerationError) as excinfo:
        build_topic_difficulty_analysis(
            _profile(),
            plan=None,
            evidence_bundles=[],
            generator=generator,
            conversation_id="conv-test",
        )

    assert excinfo.value.stage == "invalid_output"


def test_unavailable_provider_raises_generation_error_without_rules_advice() -> None:
    with pytest.raises(ResearchGenerationError) as excinfo:
        build_topic_difficulty_analysis(
            _profile(),
            plan=None,
            evidence_bundles=[],
            generator=FakeArtifactGenerator(ArtifactLlmOutcome.unavailable()),
            conversation_id="conv-test",
        )

    assert excinfo.value.stage == "provider_unavailable"


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


def test_deepseek_artifact_generator_uses_configured_generation_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-" + "a" * 32)
    seen: dict[str, float] = {}

    def provider_factory(**kwargs: object) -> FakeDeepSeekProvider:
        seen["timeout_seconds"] = float(kwargs["timeout_seconds"])
        seen["max_tokens"] = float(kwargs["max_tokens"])
        return FakeDeepSeekProvider('{"title":"ok"}')

    monkeypatch.setattr(
        "code_navi.research.research_artifact_llm.DeepSeekGuidanceProvider",
        provider_factory,
    )

    RuntimeResearchArtifactGenerator().generate(
        kind="topic_difficulty_analysis",
        context={},
        conversation_id="conv-test",
    )

    assert seen["timeout_seconds"] >= 60.0
    assert seen["max_tokens"] >= 4000.0


def test_context_redaction_preserves_non_secret_keyword_fields() -> None:
    context = {"suggested_search_keywords": ["GCN", "Cora"]}

    assert _redact_local_context(context) == context


def test_context_redaction_preserves_paper_structure_keys_but_masks_api_key() -> None:
    context = {
        "paper_sections": [{"key": "method", "order": 3}],
        "required_json_shape": {"chapter_key": "string|null"},
        "api_key": "secret-value",
    }

    assert _redact_local_context(context) == {
        "paper_sections": [{"key": "method", "order": 3}],
        "required_json_shape": {"chapter_key": "string|null"},
        "api_key": "[redacted]",
    }


def test_context_redaction_preserves_http_urls_for_paper_identity() -> None:
    context = {"url": "https://openalex.org/W2809418595", "identifier": "http://doi.org/10.1/abc"}

    assert _redact_local_context(context) == context


def test_artifact_runtime_input_explicitly_requires_output_shape() -> None:
    payload = json.loads(
        RuntimeResearchArtifactGenerator._runtime_input(
            "research_plan", {"required_json_shape": {"research_title": "ResearchPlanEntry"}}
        )
    )

    assert "output_instruction" in payload
    assert "不得原样复述 validated_context" in payload["output_instruction"]


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


def test_experiment_design_prompt_requests_detailed_professional_guidance() -> None:
    profile = _profile()
    generator = FakeArtifactGenerator(
        ArtifactLlmOutcome.generated(
            '{"hypothesis":{"content":"建议检验反馈差异。","classification":"inference","basis":"研究问题。"},'
            '"variables":[{"content":"反馈时机。","classification":"inference","basis":"方法。"}],'
            '"data_sources":[{"content":"数据许可待确认。","classification":"to_verify","basis":"约束。"}],'
            '"baselines":[{"content":"延迟反馈。","classification":"inference","basis":"比较。"}],'
            '"metrics":[{"content":"Accuracy。","classification":"to_verify","basis":"待确认。"}],'
            '"steps":[{"content":"完成一次试跑。","classification":"inference","basis":"时间。"}],'
            '"resources":[{"content":"环境待确认。","classification":"to_verify","basis":"约束。"}],'
            '"risks":[{"content":"样本不足。","classification":"to_verify","basis":"风险。"}],'
            '"advisor_confirmation_items":[{"content":"确认数据许可。","classification":"to_verify","basis":"导师确认。"}],'
            '"provenance_note":"模型生成建议。"}'
        )
    )

    build_experiment_design(
        profile,
        plan=build_conversation_research_plan(profile, ready_for_plan=True),
        generator=generator,
        conversation_id="conv-test",
    )

    guidance = generator.contexts[0]["writing_guidance"]
    assert isinstance(guidance, list)
    assert any("目的" in str(item) and "判定标准" in str(item) for item in guidance)
    assert any("selected_paper_analysis" in str(item) for item in guidance)
    assert any("content" in str(item) and "basis" in str(item) for item in guidance)
    assert generator.contexts[0]["required_json_shape"]["risks"] == "ResearchPlanEntry[]"
    detail_requirements = generator.contexts[0]["detail_requirements"]
    assert isinstance(detail_requirements, dict)
    assert "operational definition" in str(detail_requirements["variables"])


def test_invalid_experiment_design_output_raises_instead_of_rules_fallback() -> None:
    profile = _profile()
    with pytest.raises(ResearchGenerationError) as excinfo:
        build_experiment_design(
            profile,
            plan=build_conversation_research_plan(profile, ready_for_plan=True),
            generator=FakeArtifactGenerator(ArtifactLlmOutcome.generated("not-json")),
            conversation_id="conv-test",
        )

    assert excinfo.value.stage == "invalid_output"


def test_code_draft_uses_safe_model_preview_only_after_existing_plan() -> None:
    profile = _profile()
    plan = build_conversation_research_plan(profile, ready_for_plan=True)
    generator = FakeArtifactGenerator(
        ArtifactLlmOutcome.generated(
            json.dumps(
                {
                    "title": "反馈策略实验草案",
                    "directory_tree": ["README.md", "src/", "src/data.py"],
                    "dependencies": ["Python 3.11+（未安装）"],
                    "files": [
                        {"path": "README.md", "content": "# 仅预览；替换 TODO 前不要运行。"},
                        {
                            "path": "src/data.py",
                            "content": "def load_data():\n    # TODO: 确认许可\n    return []\n",
                        },
                    ],
                    "run_instructions": ["先人工确认 README 中的 TODO。"],
                    "assumptions": ["默认使用合成数据。"],
                    "to_verify_items": ["真实数据许可待确认。"],
                    "provenance_note": "模型基于已确认画像生成预览；不写文件、不执行。",
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
    assert any(item.path == "src/data.py" for item in draft.files)
    assert "不执行" in draft.provenance_note
    assert "TODO" in "\n".join(item.content for item in draft.files)


def test_code_draft_blocks_secret_or_execution_primitives() -> None:
    profile = _profile()
    generator = FakeArtifactGenerator(
        ArtifactLlmOutcome.generated(
            json.dumps(
                {
                    "title": "unsafe",
                    "directory_tree": ["src/data.py"],
                    "dependencies": [],
                    "files": [{"path": "src/data.py", "content": "api_key = 'secret'"}],
                    "run_instructions": ["run it"],
                    "assumptions": ["x"],
                    "to_verify_items": ["x"],
                    "provenance_note": "x",
                }
            )
        )
    )

    with pytest.raises(ResearchGenerationError) as excinfo:
        build_experiment_code_draft(
            profile,
            plan=build_conversation_research_plan(profile, ready_for_plan=True),
            generator=generator,
            conversation_id="conv-test",
        )

    assert excinfo.value.stage == "invalid_output"
