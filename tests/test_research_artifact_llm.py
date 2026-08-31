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
            '"core_judgment":"画像已能支撑方向判断，实验设置仍需确认。",'
            '"items":[{"area":"方法难点","content":"建议先固定即时与延迟反馈的比较条件。",'
            '"classification":"inference","basis":"已确认研究问题和对比实验方法。",'
            '"source_scope":"profile_and_plan_only",'
            '"relevance":"决定对比实验是否可比。",'
            '"suggested_action":"先写下一组固定的比较条件。"}],'
            '"next_action":"先固定比较条件，再生成研究计划。",'
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
                    "core_judgment": "证据范围足以支持方向判断，但方法细节仍需核验。",
                    "next_action": "围绕已保存摘要先固定一条核验清单。",
                    "items": [
                        {
                            "area": "方法难点",
                            "content": "建议核验摘要中描述的方法边界。",
                            "classification": "inference",
                            "basis": "所选论文摘要",
                            "source_scope": "metadata_and_abstract_only",
                            "relevance": "决定复现任务的模型模块边界。",
                            "suggested_action": "先记录待核验的方法条件。",
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
                    "core_judgment": "选中论文与当前研究问题对口，摘要外细节待核验。",
                    "next_action": "核对摘要范围后再生成复现方案。",
                    "items": [
                        {
                            "area": "方法难点",
                            "content": "选中论文摘要中的方法需要进一步核验。",
                            "classification": "inference",
                            "basis": "选中论文摘要",
                            "source_scope": "metadata_and_abstract_only",
                            "relevance": "决定复现方案的可行性边界。",
                            "suggested_action": "把方法细节列入正文核验清单。",
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


def test_topic_difficulty_analysis_v2_area_code_and_capability_note() -> None:
    profile = _profile()
    context_provenance = {
        "learning_mastery_snapshot": {
            "strong": ["注意力机制", "提示词工程"],
            "weak": ["对比学习", "图神经网络"],
        }
    }
    generator = FakeArtifactGenerator(
        ArtifactLlmOutcome.generated(
            json.dumps(
                {
                    "title": "方向难点分析 v2",
                    "information_scope": "profile_and_plan_only",
                    "core_judgment": "画像完整，需重点攻关对比学习与实验设计。",
                    "next_action": "补齐实验对比方案。",
                    "items": [
                        {
                            "area": "核心方法难点",
                            "content": "1) 步骤一：设计对比学习目标；2) 步骤二：实施表征对比。",
                            "classification": "inference",
                            "basis": "模型与算法设计",
                            "source_scope": "profile_and_plan_only",
                            "relevance": "影响核心创新性。",
                            "suggested_action": "先复查对比学习损失函数定义。",
                        },
                        {
                            "area": "数据与实操难点",
                            "content": "1) 数据预处理；2) 标注清洗。",
                            "classification": "to_verify",
                            "basis": "数据处理步骤",
                            "source_scope": "profile_and_plan_only",
                            "relevance": "影响数据质量。",
                            "suggested_action": "核验样本标注一致性。",
                        },
                        {
                            "area": "研究动机探讨",
                            "content": "探索大语言模型在少样本下的泛化能力。",
                            "classification": "inference",
                            "basis": "动机背景",
                            "source_scope": "profile_and_plan_only",
                            "relevance": "立项必要性。",
                            "suggested_action": "撰写引言。",
                        },
                        {
                            "area": "未知探索分类",
                            "content": "一些通用的建议文本。",
                            "classification": "to_verify",
                            "basis": "杂项说明",
                            "source_scope": "profile_and_plan_only",
                            "relevance": "辅助参考。",
                            "suggested_action": "保留为一般参考建议。",
                        },
                    ],
                    "provenance_note": "模型生成分析。",
                },
                ensure_ascii=False,
            )
        )
    )

    analysis = build_topic_difficulty_analysis(
        profile,
        plan=build_conversation_research_plan(profile, ready_for_plan=True),
        evidence_bundles=[],
        generator=generator,
        conversation_id="conv-test",
        context_provenance=context_provenance,
    )

    assert analysis.generation_mode == "llm"
    assert len(analysis.items) == 4
    # Check area_code normalization
    assert analysis.items[0].area_code == "method_difficulty"
    # Check capability_note derivation from mastery (matched weak '对比学习')
    assert analysis.items[0].capability_note is not None
    assert "超出当前掌握范围" in analysis.items[0].capability_note
    assert "对比学习" in analysis.items[0].capability_note
    # Reducer never mutates classification
    assert analysis.items[0].classification == "inference"

    assert analysis.items[1].area_code == "data_practice_difficulty"
    assert analysis.items[1].classification == "to_verify"

    assert analysis.items[2].area_code == "research_motivation"

    # Unknown area falls back to area_code=None without losing item
    assert analysis.items[3].area_code is None
    assert analysis.items[3].content == "一些通用的建议文本。"


def test_topic_difficulty_analysis_v2_downgrades_unsaved_evidence_refs() -> None:
    profile = _profile()
    paper = AcademicPaperResult(
        title="Valid Paper",
        authors=["Alice"],
        year=2024,
        source_name="arxiv",
        url="https://arxiv.org/abs/2401.00001",
        paper_id="2401.00001",
        abstract_excerpt="Valid abstract excerpt.",
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
    bundle = ConversationEvidenceBundle(
        bundle_id="b-valid",
        conversation_id="conv-test",
        round_index=1,
        query="test query",
        requested_sources=["arxiv"],
        selected_tags=[],
        allowed_sources=["arxiv"],
        queried_sources=["arxiv"],
        source_statuses=[],
        searched_at=datetime(2026, 8, 7, tzinfo=UTC),
        papers=[paper],
        source_links=[paper.url],
        failure_reasons=[],
        provenance_note="saved.",
    )

    generator = FakeArtifactGenerator(
        ArtifactLlmOutcome.generated(
            json.dumps(
                {
                    "title": "方向难点分析未保存引用降级",
                    "information_scope": "metadata_and_abstract_only",
                    "core_judgment": "需核验引用来源。",
                    "next_action": "清理未保存引用。",
                    "items": [
                        {
                            "area": "方法难点",
                            "content": "引用了未保存的外部论文。",
                            "classification": "inference",
                            "basis": "外部文献",
                            "source_scope": "metadata_and_abstract_only",
                            "relevance": "引用风险。",
                            "suggested_action": "核实文献。",
                            "evidence_refs": [
                                {
                                    "bundle_id": "unsaved-bundle",
                                    "paper_url": "https://arxiv.org/abs/9999.99999",
                                    "title": "Unsaved Fake Paper",
                                    "source_name": "arxiv",
                                    "year": 2025,
                                    "evidence_level": "abstract",
                                    "evidence_summary": "unsaved summary",
                                }
                            ],
                        }
                    ],
                    "provenance_note": "原始提示",
                },
                ensure_ascii=False,
            )
        )
    )

    analysis = build_topic_difficulty_analysis(
        profile,
        plan=build_conversation_research_plan(profile, ready_for_plan=True),
        evidence_bundles=[bundle],
        generator=generator,
        conversation_id="conv-test",
    )

    # Classification remains untouched
    assert analysis.items[0].classification == "inference"
    # Unsaved reference was stripped and downgraded
    assert len(analysis.items[0].evidence_refs) == 0
    assert analysis.items[0].source_scope == "profile_and_plan_only"
    # Provenance note indicates the downgrade
    assert "降级为建议并移除无效证据引用" in analysis.provenance_note


def test_experiment_design_v2_metric_specs_and_dataset_refs() -> None:
    profile = _profile()
    hypothesis_entry = {
        "content": "假设验证差异。",
        "classification": "inference",
        "basis": "画像。",
    }
    var_entry = {
        "content": "学习率与 batch size。",
        "classification": "inference",
        "basis": "实验设定。",
    }
    baseline_entry = {
        "content": "基准方法 A。",
        "classification": "inference",
        "basis": "文献。",
    }
    step_entry = {
        "content": "步骤一：数据准备；步骤二：模型训练。",
        "classification": "inference",
        "basis": "流程。",
    }
    res_entry = {
        "content": "单卡 A100。",
        "classification": "to_verify",
        "basis": "计算需求。",
    }
    risk_entry = {
        "content": "过拟合风险。",
        "classification": "inference",
        "basis": "小样本。",
    }
    advisor_entry = {
        "content": "确认评价指标。",
        "classification": "to_verify",
        "basis": "导师把关。",
    }
    generator = FakeArtifactGenerator(
        ArtifactLlmOutcome.generated(
            json.dumps(
                {
                    "task_type": "classification",
                    "hypothesis": hypothesis_entry,
                    "variables": [var_entry],
                    "metric_specs": [
                        {
                            "name": "ACC",
                            "definition": "模型预测准确率达到 92%",
                            "formula": None,
                            "higher_is_better": True,
                            "applies_to_task_type": ["classification"],
                            "source": "model_suggested",
                            "to_verify": True,
                        },
                        {
                            "name": "CustomLatencyScore",
                            "definition": "端到端耗时评分约 25ms 且准确率 95%",
                            "formula": "T_score = 1000 / Latency",
                            "higher_is_better": True,
                            "applies_to_task_type": ["classification"],
                            "source": "model_suggested",
                            "to_verify": False,
                        },
                    ],
                    "dataset_refs": [
                        {
                            "name": "公开基准数据集",
                            "url": "https://huggingface.co/datasets/example",
                            "license_note": "CC-BY-4.0",
                            "to_verify": False,
                        },
                        {
                            "name": "内部未公开数据集",
                            "url": None,
                            "license_note": "待申请",
                            "to_verify": False,
                        },
                    ],
                    "baselines": [baseline_entry],
                    "steps": [step_entry],
                    "resources": [res_entry],
                    "risks": [risk_entry],
                    "advisor_confirmation_items": [advisor_entry],
                    "provenance_note": "模型生成方案。",
                },
                ensure_ascii=False,
            )
        )
    )

    design = build_experiment_design(
        profile,
        plan=build_conversation_research_plan(profile, ready_for_plan=True),
        generator=generator,
        conversation_id="conv-test",
        task_type_override="classification",
    )

    assert design is not None
    assert design.task_type == "classification"

    # Metric 1: 'ACC' matches standard catalog -> source=standard_catalog, definition backfilled
    acc_metric = next(m for m in design.metric_specs if m.name == "ACC")
    assert acc_metric.source == "standard_catalog"
    assert acc_metric.to_verify is False
    assert "Accuracy = (TP + TN)" in (acc_metric.formula or "")
    assert acc_metric.definition == "预测正确的样本数占总样本数的比例。"

    # Metric 2: 'CustomLatencyScore' not in catalog -> model_suggested, stripped numeric assertion
    custom_metric = next(m for m in design.metric_specs if m.name == "CustomLatencyScore")
    assert custom_metric.source == "model_suggested"
    assert custom_metric.to_verify is True
    # '约 25ms 且准确率 95%' numeric assertions should be stripped
    assert "95%" not in custom_metric.definition
    assert "25" not in custom_metric.definition

    # Dataset 1: Has public https URL -> to_verify=False
    public_dataset = next(d for d in design.dataset_refs if d.name == "公开基准数据集")
    assert public_dataset.to_verify is False
    assert public_dataset.url == "https://huggingface.co/datasets/example"

    # Dataset 2: No public URL -> to_verify forced to True
    internal_dataset = next(d for d in design.dataset_refs if d.name == "内部未公开数据集")
    assert internal_dataset.to_verify is True

    # Legacy fields projected correctly
    assert len(design.metrics) == 2
    assert any("ACC：" in m.content for m in design.metrics)
    assert len(design.data_sources) == 2
    assert any(
        "https://huggingface.co/datasets/example" in ds.content for ds in design.data_sources
    )
    assert any(
        ds.classification == "to_verify"
        for ds in design.data_sources
        if ds.content == "内部未公开数据集"
    )
