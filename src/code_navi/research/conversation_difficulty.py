"""LLM-authored research-direction and metadata-only paper difficulty analysis."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

from .conversation_schemas import (
    ConversationEvidenceBundle,
    ConversationResearchPlan,
    EvidenceReference,
    PaperAnalysis,
    PaperReadingEvidence,
    ResearchAnalysisItem,
    ResearchProfile,
    TopicDifficultyAnalysis,
)
from .conversation_understanding import section_key_for_area
from .research_artifact_llm import ResearchArtifactGenerator
from .research_generation import (
    ResearchGenerationError,
    require_contract_fields,
    require_generated_artifact,
)
from .schemas import AcademicPaperResult

_TOPIC_PROVENANCE = (
    "本分析由模型仅根据已校验科研画像、规则研究计划和已保存证据的可用范围生成；"
    "不读取论文全文，不把方向建议写成论文结论。无法确认的内容标记为 to_verify。"
)
_PAPER_PROVENANCE = (
    "本分析由模型基于用户选中的已保存论文、系统按允许来源读取的正文片段和科研目标生成；"
    "规则程序只校验来源边界，不把待核验项当作事实。"
)
_PAPER_METADATA_PROVENANCE = (
    "本分析由模型仅基于用户选中的已保存论文元数据和来源摘要生成；"
    "不下载全文，也不把待核验项当作事实。"
)

_LATIN_TOKEN = re.compile(r"[a-z][a-z0-9_-]{2,}")
_CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")


def _lexical_tokens(text: str) -> set[str]:
    """Deterministic tokens for cheap grounding checks (latin words + CJK bigrams)."""
    lowered = (text or "").lower()
    tokens = set(_LATIN_TOKEN.findall(lowered))
    cjk = _CJK_CHAR.findall(lowered)
    tokens.update(
        f"{first}{second}" for first, second in zip(cjk, cjk[1:], strict=False)
    )
    return tokens


def _assert_paper_grounded(
    items: Iterable[ResearchAnalysisItem],
    *,
    paper: AcademicPaperResult,
    paper_reading: object | None,
) -> None:
    """Reject analysis items with no lexical tie to the saved paper material.

    An item is grounded when it cites an EvidenceReference or shares at least
    one token with the paper title, abstract excerpt or the bounded reading
    text.  Fully generic prose that could describe any paper is an
    ``invalid_output`` failure, matching the negative list in the agent prompt.
    """
    materials = " ".join(
        part
        for part in (
            paper.title,
            paper.abstract_excerpt or "",
            getattr(paper_reading, "text_excerpt", "") or "",
            " ".join(
                section.text
                for section in (getattr(paper_reading, "sections", None) or [])
            ),
        )
        if part
    )
    material_tokens = _lexical_tokens(materials)
    ungrounded: list[str] = []
    for item in items:
        if item.evidence_refs:
            continue
        item_tokens = _lexical_tokens(
            " ".join((item.area, item.content, item.basis))
        )
        if not item_tokens & material_tokens:
            ungrounded.append(item.area)
    if ungrounded:
        raise ResearchGenerationError(
            "invalid_output",
            "paper_analysis: items not grounded in the saved paper material: "
            + ", ".join(ungrounded),
        )


def build_topic_difficulty_analysis(
    profile: ResearchProfile,
    *,
    plan: ConversationResearchPlan | None,
    evidence_bundles: list[ConversationEvidenceBundle],
    paper_analysis: PaperAnalysis | None = None,
    generator: ResearchArtifactGenerator | None = None,
    conversation_id: str | None = None,
) -> TopicDifficultyAnalysis:
    """List research-design gaps without asserting external facts or paper results."""
    scope = (
        "full_text_user_triggered"
        if paper_analysis is not None and paper_analysis.paper_reading is not None
        else "metadata_and_abstract_only"
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
        "selected_paper_analysis": (
            paper_analysis.model_dump(mode="json") if paper_analysis else None
        ),
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
            "core_judgment": "string",
            "next_action": "string",
            "items": [
                {
                    "area": "string",
                    "content": "string",
                    "classification": "inference|to_verify",
                    "basis": "string",
                    "source_scope": "profile_and_plan_only|metadata_and_abstract_only",
                    "relevance": "string",
                    "suggested_action": "string",
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
        if paper_analysis is not None:
            for item in paper_analysis.items:
                for reference in item.evidence_refs:
                    allowed_refs[(reference.bundle_id, reference.paper_url)] = reference
        _assert_model_analysis_boundary(enhanced.items, allowed_refs=allowed_refs)
        require_contract_fields(
            {
                "core_judgment": enhanced.core_judgment,
                "next_action": enhanced.next_action,
            },
            kind="topic_difficulty_analysis",
        )
        for topic_item in enhanced.items:
            require_contract_fields(
                {
                    "relevance": topic_item.relevance,
                    "suggested_action": topic_item.suggested_action,
                },
                kind="topic_difficulty_analysis item",
            )
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
    paper_reading: PaperReadingEvidence | None = None,
    research_context: dict[str, object] | None = None,
    generator: ResearchArtifactGenerator | None = None,
    conversation_id: str | None = None,
) -> PaperAnalysis:
    """Analyze a selected paper against the user's research goal and bounded paper text."""
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
            "information_scope": (
                "full_text_user_triggered" if paper_reading else "metadata_and_abstract_only"
            ),
            "paper_reading": paper_reading.model_dump(mode="json") if paper_reading else None,
            "paper_sections": (
                [section.model_dump(mode="json") for section in paper_reading.sections]
                if paper_reading
                else []
            ),
            "research_context": research_context or {},
            "writing_guidance": [
                "优先回答这篇论文如何帮助当前研究目标或复现任务，不要写成泛泛的领域综述。",
                "输出顶部给出 core_judgment：一句话说明该论文对当前研究问题的"
                "价值与主要缺口，不超过两句。",
                "每条分析项必须填写 relevance（与当前研究问题的关系）和"
                "suggested_action（一个可执行下一步）。",
                "结尾给出 summary：概括已覆盖的章节或范围与仍未核验的部分，不使用空洞的鼓励话术。",
                "给出唯一的 next_action；不要一次罗列多个并列建议。",
                "只提出与论文方法、数据、实验或复现限制直接相关的 3 至 6 条建议，"
                "避免重复同义内容。",
                "每条建议都要说明正文或摘要中的依据；正文未覆盖的细节保持 to_verify。",
                "输出内容应短而具体，直接给出使用者下一步要核对或执行的动作。",
                "如果 paper_sections 非空，必须按实际识别到的论文章节组织分析；"
                "每个分析项必须只对应一个章节，"
                "并填写匹配的 chapter_key 与 chapter_order。未识别或正文未覆盖的章节不要臆造，"
                "标记为 to_verify。",
                "章节分析应围绕引言/相关工作/方法/实验/讨论/结论中的实际文本，"
                "说明该章节对当前研究目标或复现的具体意义。",
                "必须返回 information_scope；有 paper_reading 时原样返回 full_text_user_triggered，"
                "没有 paper_reading 时返回 metadata_and_abstract_only。",
            ],
            "source_boundary": {
                "allowed_classifications": ["inference", "to_verify"],
                "forbidden": [
                    "不得新增 fact 分类的分析项。",
                    "不得改变 paper_url、abstract_available 或信息范围。",
                    "不得根据标题或摘要断言论文完整方法、实验设置或结论。",
                    "论文正文只可引用 paper_reading.text_excerpt 中实际出现的内容。",
                    "chapter_key 只能使用 paper_sections 中存在的 key，"
                    "chapter_order 必须与该章节一致。",
                ],
            },
            "required_json_shape": {
                "title": "string",
                "paper_url": "string",
                "information_scope": "metadata_and_abstract_only|full_text_user_triggered",
                "abstract_available": "boolean",
                "core_judgment": "string",
                "items": [
                    {
                        "area": "string",
                        "content": "string",
                        "classification": "inference|to_verify",
                        "basis": "string",
                        "source_scope": "metadata_and_abstract_only|full_text_user_triggered",
                        "chapter_key": "string|null",
                        "chapter_order": "integer|null",
                        "relevance": "string",
                        "suggested_action": "string",
                    }
                ],
                "summary": "string",
                "next_action": "string",
                "provenance_note": "string",
            },
        },
    )
    try:
        expected_scope = (
            "full_text_user_triggered" if paper_reading else "metadata_and_abstract_only"
        )
        generated_text = require_generated_artifact(outcome, kind="paper_analysis")
        # The scope is derived from the user action and is not model-authored.
        # Keep accepting older/provider outputs that omitted this field, while
        # still rejecting an explicitly contradictory scope below.
        generated_payload = json.loads(generated_text)
        if isinstance(generated_payload, dict) and "information_scope" not in generated_payload:
            generated_payload["information_scope"] = expected_scope
        enhanced = PaperAnalysis.model_validate(generated_payload)
        _assert_model_analysis_boundary(enhanced.items)
        if (
            enhanced.paper_url != paper.url
            or enhanced.abstract_available != bool(abstract)
            or enhanced.information_scope != expected_scope
        ):
            raise ValueError("model changed selected paper identity or source scope")
        enhanced = enhanced.model_copy(
            update={"items": _normalize_paper_chapter_metadata(enhanced.items, paper_reading)}
        )
        enhanced = enhanced.model_copy(
            update={
                "items": [
                    item.model_copy(update={"section_key": section_key_for_area(item.area)})
                    for item in enhanced.items
                ]
            }
        )
        if evidence_ref is not None:
            enhanced = enhanced.model_copy(
                update={
                    "items": [
                        item.model_copy(update={"evidence_refs": [evidence_ref]})
                        for item in enhanced.items
                    ]
                }
            )
        _assert_paper_grounded(
            enhanced.items, paper=paper, paper_reading=paper_reading
        )
        require_contract_fields(
            {
                "core_judgment": enhanced.core_judgment,
                "summary": enhanced.summary,
                "next_action": enhanced.next_action,
            },
            kind="paper_analysis",
        )
        for analysis_item in enhanced.items:
            require_contract_fields(
                {
                    "relevance": analysis_item.relevance,
                    "suggested_action": analysis_item.suggested_action,
                },
                kind="paper_analysis item",
            )
        return enhanced.model_copy(
            update={
                "generation_mode": "llm",
                "run_id": outcome.run_id,
                "event_count": outcome.event_count,
                "provenance_note": (
                    _PAPER_PROVENANCE if paper_reading else _PAPER_METADATA_PROVENANCE
                ),
                "paper_reading": paper_reading,
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


def _normalize_paper_chapter_metadata(
    items: Iterable[ResearchAnalysisItem],
    paper_reading: PaperReadingEvidence | None,
) -> list[ResearchAnalysisItem]:
    """Validate model chapter references against extracted, bounded sections."""
    sections = {
        section.key: section
        for section in (paper_reading.sections if paper_reading else [])
    }
    if not sections:
        return list(items)
    normalized: list[ResearchAnalysisItem] = []
    for item in items:
        if item.chapter_key is None:
            continue
        section = sections.get(item.chapter_key)
        if section is None or item.chapter_order != section.order:
            continue
        normalized.append(item)
    if not normalized:
        raise ValueError("model did not cite a valid paper chapter")
    return sorted(
        normalized,
        key=lambda item: (
            item.chapter_order if item.chapter_order is not None else 99,
            item.area.casefold(),
            item.content.casefold(),
        ),
    )


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
