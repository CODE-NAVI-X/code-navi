"""LLM-authored research-direction and metadata-only paper difficulty analysis."""

from __future__ import annotations

from .conversation_schemas import (
    ConversationEvidenceBundle,
    ConversationResearchPlan,
    EvidenceReference,
    PaperAnalysis,
    ResearchAnalysisItem,
    ResearchProfile,
    TopicDifficultyAnalysis,
)
from .research_artifact_llm import ResearchArtifactGenerator
from .research_generation import ResearchGenerationError, require_generated_artifact
from .schemas import AcademicPaperResult

_TOPIC_PROVENANCE = (
    "本分析由模型仅根据已校验科研画像、规则研究计划和已保存证据的可用范围生成；"
    "不读取论文全文，不把方向建议写成论文结论。无法确认的内容标记为 to_verify。"
)
_PAPER_PROVENANCE = (
    "本分析由模型仅基于用户选中的已保存论文元数据和来源摘要生成；"
    "不下载全文、不生成论文精读卡，也不把待核验项当作事实。"
)


def build_topic_difficulty_analysis(
    profile: ResearchProfile,
    *,
    plan: ConversationResearchPlan | None,
    evidence_bundles: list[ConversationEvidenceBundle],
    generator: ResearchArtifactGenerator | None = None,
    conversation_id: str | None = None,
) -> TopicDifficultyAnalysis:
    """List research-design gaps without asserting external facts or paper results."""
    scope = (
        "metadata_and_abstract_only"
        if any(bundle.papers for bundle in evidence_bundles)
        else "profile_and_plan_only"
    )
    if generator is None:
        raise ResearchGenerationError(
            "provider_unavailable", "topic_difficulty_analysis: generator is unavailable"
        )
    if conversation_id is None:
        raise ValueError("conversation_id is required for model topic analysis")
    context = {
        "profile": profile.model_dump(mode="json"),
        "research_plan": plan.model_dump(mode="json") if plan else None,
        "evidence_scope": scope,
        "saved_papers": _paper_context(evidence_bundles),
        "source_boundary": {
            "allowed_classifications": ["inference", "to_verify"],
            "forbidden": [
                "不得新增 fact 分类的分析项。",
                "不得引用保存会话之外的证据。",
                "不得改变 information_scope。",
            ],
        },
        "required_json_shape": {
            "title": "string",
            "information_scope": scope,
            "items": [
                {
                    "area": "string",
                    "content": "string",
                    "classification": "inference|to_verify",
                    "basis": "string",
                    "source_scope": "profile_and_plan_only|metadata_and_abstract_only",
                    "evidence_refs": [
                        {
                            "bundle_id": "saved bundle id",
                            "paper_url": "saved paper url",
                            "title": "saved paper title",
                            "source_name": "saved source name",
                            "year": "integer or null",
                            "evidence_level": "metadata|abstract",
                            "evidence_summary": "saved abstract excerpt or null",
                        }
                    ],
                }
            ],
            "provenance_note": "string",
        },
    }
    outcome = generator.generate(
        kind="topic_difficulty_analysis",
        context=context,
        conversation_id=conversation_id,
    )
    try:
        enhanced = TopicDifficultyAnalysis.model_validate_json(
            require_generated_artifact(outcome, kind="topic_difficulty_analysis")
        )
        allowed_refs = _context_evidence_refs(context)
        _assert_model_analysis_boundary(enhanced.items, allowed_refs=allowed_refs)
        if enhanced.information_scope != scope:
            raise ValueError("model changed information scope")
        enhanced = enhanced.model_copy(
            update={
                "items": [
                    item.model_copy(
                        update={
                            "evidence_refs": [
                                allowed_refs[(reference.bundle_id, reference.paper_url)]
                                for reference in item.evidence_refs
                            ]
                        }
                    )
                    for item in enhanced.items
                ]
            }
        )
        return enhanced.model_copy(
            update={
                "generation_mode": "llm",
                "run_id": outcome.run_id,
                "event_count": outcome.event_count,
                "provenance_note": _TOPIC_PROVENANCE,
            }
        )
    except ResearchGenerationError:
        raise
    except ValueError as error:
        raise ResearchGenerationError(
            "invalid_output", "topic_difficulty_analysis: boundary validation failed"
        ) from error


def build_paper_analysis(
    paper: AcademicPaperResult,
    *,
    evidence_ref: EvidenceReference | None = None,
    generator: ResearchArtifactGenerator | None = None,
    conversation_id: str | None = None,
) -> PaperAnalysis:
    """Analyze only an explicitly selected saved paper's metadata and abstract."""
    abstract = paper.abstract_excerpt
    if generator is None:
        raise ResearchGenerationError(
            "provider_unavailable", "paper_analysis: generator is unavailable"
        )
    if conversation_id is None:
        raise ValueError("conversation_id is required for model paper analysis")
    outcome = generator.generate(
        kind="paper_analysis",
        conversation_id=conversation_id,
        context={
            "paper": paper.model_dump(mode="json"),
            "information_scope": "metadata_and_abstract_only",
            "source_boundary": {
                "allowed_classifications": ["inference", "to_verify"],
                "forbidden": [
                    "不得新增 fact 分类的分析项。",
                    "不得改变 paper_url、abstract_available 或信息范围。",
                    "不得根据标题或摘要断言论文完整方法、实验设置或结论。",
                ],
            },
            "required_json_shape": {
                "title": "string",
                "paper_url": "string",
                "abstract_available": "boolean",
                "items": [
                    {
                        "area": "string",
                        "content": "string",
                        "classification": "inference|to_verify",
                        "basis": "string",
                        "source_scope": "metadata_and_abstract_only",
                    }
                ],
                "provenance_note": "string",
            },
        },
    )
    try:
        enhanced = PaperAnalysis.model_validate_json(
            require_generated_artifact(outcome, kind="paper_analysis")
        )
        _assert_model_analysis_boundary(enhanced.items)
        if enhanced.paper_url != paper.url or enhanced.abstract_available != bool(abstract):
            raise ValueError("model changed selected paper identity or source scope")
        if evidence_ref is not None:
            enhanced = enhanced.model_copy(
                update={
                    "items": [
                        item.model_copy(update={"evidence_refs": [evidence_ref]})
                        for item in enhanced.items
                    ]
                }
            )
        return enhanced.model_copy(
            update={
                "generation_mode": "llm",
                "run_id": outcome.run_id,
                "event_count": outcome.event_count,
                "provenance_note": _PAPER_PROVENANCE,
            }
        )
    except ResearchGenerationError:
        raise
    except ValueError as error:
        raise ResearchGenerationError(
            "invalid_output", "paper_analysis: boundary validation failed"
        ) from error


def _assert_model_analysis_boundary(
    items: list[ResearchAnalysisItem],
    *,
    allowed_refs: dict[tuple[str, str], EvidenceReference] | None = None,
) -> None:
    if any(item.classification == "fact" for item in items):
        raise ValueError("model cannot introduce fact-classified analysis")
    if allowed_refs is not None:
        for item in items:
            if item.source_scope == "metadata_and_abstract_only" and not item.evidence_refs:
                raise ValueError("evidence-scoped model analysis must cite saved evidence")
            if any(
                (reference.bundle_id, reference.paper_url) not in allowed_refs
                for reference in item.evidence_refs
            ):
                raise ValueError("model cited evidence outside the saved conversation bundles")


def _paper_context(bundles: list[ConversationEvidenceBundle]) -> list[dict[str, object]]:
    return [
        {
            "title": paper.title,
            "url": paper.url,
            "source": paper.source_name,
            "abstract_excerpt": paper.abstract_excerpt,
            "evidence_ref": {
                "bundle_id": bundle.bundle_id,
                "paper_url": paper.url,
                "title": paper.title,
                "source_name": paper.source_name,
                "year": paper.year,
                "evidence_level": "abstract" if paper.abstract_excerpt else "metadata",
                "evidence_summary": paper.abstract_excerpt[:1000]
                if paper.abstract_excerpt
                else None,
            },
        }
        for bundle in bundles
        for paper in bundle.papers
    ][:8]


def _context_evidence_refs(
    context: dict[str, object],
) -> dict[tuple[str, str], EvidenceReference]:
    raw_papers = context.get("saved_papers")
    if not isinstance(raw_papers, list):
        return {}
    allowed: dict[tuple[str, str], EvidenceReference] = {}
    for paper in raw_papers:
        if not isinstance(paper, dict):
            continue
        reference = paper.get("evidence_ref")
        if not isinstance(reference, dict):
            continue
        try:
            canonical = EvidenceReference.model_validate(reference)
        except ValueError:
            continue
        allowed[(canonical.bundle_id, canonical.paper_url)] = canonical
    return allowed
