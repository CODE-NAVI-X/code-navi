"""Bounded research-direction and metadata-only paper difficulty analysis."""

from __future__ import annotations

from .conversation_schemas import (
    ConversationEvidenceBundle,
    ConversationResearchPlan,
    PaperAnalysis,
    ResearchAnalysisItem,
    ResearchProfile,
    TopicDifficultyAnalysis,
)
from .research_artifact_llm import ResearchArtifactGenerator
from .schemas import AcademicPaperResult


def build_topic_difficulty_analysis(
    profile: ResearchProfile,
    *,
    plan: ConversationResearchPlan | None,
    evidence_bundles: list[ConversationEvidenceBundle],
    generator: ResearchArtifactGenerator | None = None,
) -> TopicDifficultyAnalysis:
    """List research-design gaps without asserting external facts or paper results."""
    scope = (
        "metadata_and_abstract_only"
        if any(bundle.papers for bundle in evidence_bundles)
        else "profile_and_plan_only"
    )
    question = next(iter(profile.research_questions or profile.candidate_questions), None)
    items = [
        _item(
            "研究问题",
            question or "核心问题仍待收窄；需要定义比较对象、输入和可观察输出。",
            "fact" if question else "to_verify",
            f"科研画像中的研究问题：{question}" if question else "当前画像未确认研究问题。",
            "profile_and_plan_only",
        ),
        _item(
            "方法难点",
            "建议把候选方法与至少一个可比较基线分开定义，避免把相关性直接解释为因果。",
            "inference",
            "基于当前研究计划的候选方法/基线要求。",
            "profile_and_plan_only",
        ),
        _item(
            "数据与实验难点",
            profile.data_requirements
            and f"需核验“{profile.data_requirements}”的可得性、代表性与许可范围。"
            or "样本、数据来源或材料范围尚待确认，不能预设其可用。",
            "inference" if profile.data_requirements else "to_verify",
            f"用户已说明的数据条件：{profile.data_requirements}"
            if profile.data_requirements
            else "当前科研画像没有数据条件。",
            "profile_and_plan_only",
        ),
        _item(
            "复现风险",
            "需要预先记录数据版本、对照条件、指标和失败案例；这些要求是研究设计建议，不是已有实验结论。",
            "inference",
            "参考当前两周 MVP 与风险条目。",
            "profile_and_plan_only",
        ),
        _item(
            "资源需求",
            "时间、设备、样本量和伦理/授权条件需要由用户或导师确认，不能从主题推断。",
            "to_verify",
            "当前画像中的约束：" + ("；".join(profile.constraints) or "尚未明确"),
            "profile_and_plan_only",
        ),
    ]
    if plan is not None:
        items.append(
            _item(
                "关联计划项",
                "可先执行研究计划的第一个两周 MVP 步骤，并将未满足条件记录为风险。",
                "inference",
                plan.two_week_mvp_plan[0].basis,
                "profile_and_plan_only",
            )
        )
    rules = TopicDifficultyAnalysis(
        title=f"{profile.topic or '研究方向'}的难点分析",
        information_scope=scope,
        items=items,
        provenance_note="本分析只根据科研画像、规则研究计划和已保存证据的可用范围生成；不读取论文全文，不把方向建议写成论文结论。",
    )
    return _enhance_topic_analysis(
        rules,
        generator=generator,
        context={
            "profile": profile.model_dump(mode="json"),
            "research_plan": plan.model_dump(mode="json") if plan else None,
            "evidence_scope": scope,
            "saved_papers": _paper_context(evidence_bundles),
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
                    }
                ],
                "provenance_note": "string",
            },
        },
    )


def build_paper_analysis(
    paper: AcademicPaperResult, *, generator: ResearchArtifactGenerator | None = None
) -> PaperAnalysis:
    """Analyze only an explicitly selected saved paper's metadata and abstract."""
    abstract = paper.abstract_excerpt
    items = [
        _item(
            "研究对象",
            f"论文题录：{paper.title}"
            + (f"；摘要片段：{abstract}" if abstract else "；该来源未提供摘要。"),
            "fact",
            paper.source_name,
            "metadata_and_abstract_only",
        ),
        _item(
            "关键概念与方法难点",
            "需从摘要中进一步确认方法定义、对照条件与适用边界；未阅读全文时不能补写实验细节。",
            "to_verify",
            "当前信息范围仅为元数据和摘要。",
            "metadata_and_abstract_only",
        ),
        _item(
            "数据与实验难点",
            "数据集、样本量、指标和实验设置需要阅读全文或查阅附录核验。",
            "to_verify",
            "当前信息范围仅为元数据和摘要。",
            "metadata_and_abstract_only",
        ),
        _item(
            "复现与资源风险",
            "代码、数据许可、计算资源与复现步骤未由当前元数据/摘要证明可用。",
            "to_verify",
            "未下载正文、代码或数据。",
            "metadata_and_abstract_only",
        ),
    ]
    rules = PaperAnalysis(
        title=paper.title,
        paper_url=paper.url,
        abstract_available=bool(abstract),
        items=items,
        provenance_note="仅基于用户选中的已保存论文元数据和来源摘要；不下载全文、不生成论文精读卡，也不把待核验项当作事实。",
    )
    if generator is None:
        return rules
    outcome = generator.generate(
        kind="paper_analysis",
        context={
            "paper": paper.model_dump(mode="json"),
            "information_scope": "metadata_and_abstract_only",
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
    if outcome.status == "unavailable":
        return rules
    if outcome.status != "generated" or outcome.text is None:
        return rules.model_copy(update={"generation_mode": "rules_fallback"})
    try:
        enhanced = PaperAnalysis.model_validate_json(outcome.text)
        _assert_model_analysis_boundary(enhanced.items)
        if enhanced.paper_url != paper.url or enhanced.abstract_available != bool(abstract):
            raise ValueError("model changed selected paper identity or source scope")
        return enhanced.model_copy(update={"generation_mode": "llm"})
    except ValueError:
        return rules.model_copy(update={"generation_mode": "rules_fallback"})


def _enhance_topic_analysis(
    rules: TopicDifficultyAnalysis,
    *,
    generator: ResearchArtifactGenerator | None,
    context: dict[str, object],
) -> TopicDifficultyAnalysis:
    if generator is None:
        return rules
    outcome = generator.generate(kind="topic_difficulty_analysis", context=context)
    if outcome.status == "unavailable":
        return rules
    if outcome.status != "generated" or outcome.text is None:
        return rules.model_copy(update={"generation_mode": "rules_fallback"})
    try:
        enhanced = TopicDifficultyAnalysis.model_validate_json(outcome.text)
        _assert_model_analysis_boundary(enhanced.items)
        if enhanced.information_scope != rules.information_scope:
            raise ValueError("model changed information scope")
        return enhanced.model_copy(update={"generation_mode": "llm"})
    except ValueError:
        return rules.model_copy(update={"generation_mode": "rules_fallback"})


def _assert_model_analysis_boundary(items: list[ResearchAnalysisItem]) -> None:
    if any(item.classification == "fact" for item in items):
        raise ValueError("model cannot introduce fact-classified analysis")


def _paper_context(bundles: list[ConversationEvidenceBundle]) -> list[dict[str, object]]:
    return [
        {
            "title": paper.title,
            "url": paper.url,
            "source": paper.source_name,
            "abstract_excerpt": paper.abstract_excerpt,
        }
        for bundle in bundles
        for paper in bundle.papers
    ][:8]


def _item(
    area: str, content: str, classification: str, basis: str, source_scope: str
) -> ResearchAnalysisItem:
    return ResearchAnalysisItem(
        area=_bounded(area, 200),
        content=_bounded(content, 1000),
        classification=classification,
        basis=_bounded(basis, 1000),
        source_scope=source_scope,
    )


def _bounded(value: str, limit: int) -> str:
    """Keep user-provided profile text inside the public response contract."""
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 1]}…"
