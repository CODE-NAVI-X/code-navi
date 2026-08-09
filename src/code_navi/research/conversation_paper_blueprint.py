"""Rule-governed paper blueprints built only from already saved evidence."""

from __future__ import annotations

from .conversation_schemas import (
    ConversationEvidenceBundle,
    ConversationResearchPlan,
    ExperimentEvidenceBundle,
    PaperBlueprint,
    PaperBlueprintEntry,
    PaperBlueprintReference,
    PaperBlueprintSection,
    ResearchProfile,
)


def build_paper_blueprint(
    profile: ResearchProfile,
    *,
    conversation_id: str,
    plan: ConversationResearchPlan | None,
    academic_evidence: list[ConversationEvidenceBundle],
    experiment_evidence: list[ExperimentEvidenceBundle],
) -> PaperBlueprint:
    """Produce an offline outline without elevating unverified claims to facts."""
    topic = profile.topic or "待确认研究主题"
    question = next(
        iter(profile.research_questions or profile.candidate_questions), "待确认研究问题"
    )
    profile_refs = _profile_references(profile)
    paper_refs = _academic_references(academic_evidence)
    experiment_refs = _experiment_fact_references(experiment_evidence)
    plan_refs = _plan_references(plan)
    verify = _entry("to_verify")
    infer = _entry("inference")
    has_results = bool(experiment_refs)
    readiness = (
        verify("尚未达到投稿就绪状态。", "本蓝图只组织已保存事实、建议与待验证项。")
        if not has_results
        else verify(
            "已有用户提交的实验记录，但仍需核验设计、数据许可、统计处理与投稿规范。",
            "实验结果仅是用户提交事实，系统未执行或复核实验。",
        )
    )
    sections = [
        PaperBlueprintSection(
            section="引言",
            writing_goal=infer(
                f"说明“{question}”的重要性、场景与可验证边界。", "已确认研究主题和问题。"
            ),
            evidence_references=profile_refs,
            missing_evidence=[
                verify("补充问题背景与研究缺口的可引用来源。", "当前没有系统综述或全文证据。")
            ],
            forbidden_claims=["不得把研究动机写成已被文献验证的普遍结论。"],
        ),
        PaperBlueprintSection(
            section="相关工作",
            writing_goal=infer(
                "整理已保存受限来源的元数据或摘要，并标明仅有摘要的边界。",
                "用户主动保存的学术检索证据。",
            ),
            evidence_references=paper_refs,
            missing_evidence=[]
            if paper_refs
            else [verify("需要用户主动检索并保存相关学术来源。", "当前没有已保存的受限检索来源。")],
            forbidden_claims=["不得根据标题或摘要断言论文的完整方法、实验设置或结论。"],
            citation_placeholders=paper_refs,
        ),
        PaperBlueprintSection(
            section="方法",
            writing_goal=infer(
                "把已确认研究问题、候选方法和约束改写为可复核的方法描述。",
                "科研画像与规则研究计划。",
            ),
            evidence_references=[*profile_refs, *plan_refs],
            missing_evidence=[
                verify(
                    "确认变量定义、分组方式、数据许可和分析计划。",
                    "当前规则计划中的条件均未独立验证。",
                )
            ],
            forbidden_claims=[
                "不得声明数据、样本、GPU、许可或随机化已具备，除非用户已明确提交事实。"
            ],
        ),
        PaperBlueprintSection(
            section="实验",
            writing_goal=(
                infer(
                    "报告用户已提交的实验设置、指标、结果与失败记录，并分开描述待验证项。",
                    "已保存实验结果证据包。",
                )
                if has_results
                else verify(
                    "等待用户提交实际实验设置、结果、失败记录与局限。", "没有已保存的实验结果证据。"
                )
            ),
            evidence_references=experiment_refs,
            missing_evidence=(
                [
                    verify(
                        "补充可复核的实验设置、随机种子/不可得原因和失败记录。",
                        "仅能引用用户已提交事实。",
                    )
                ]
                if not has_results
                else [
                    verify(
                        "核验统计方法、随机种子、对照公平性与结果表格来源。",
                        "系统没有运行代码或读取原始实验数据。",
                    )
                ]
            ),
            forbidden_claims=["不得补造显著性、样本规模、基线结果、图表或因果结论。"],
        ),
        PaperBlueprintSection(
            section="讨论",
            writing_goal=infer(
                "解释结果可能的含义，同时显式保留替代解释与局限。", "用户提交实验事实与规则风险项。"
            ),
            evidence_references=experiment_refs,
            missing_evidence=[
                verify("确认替代解释、外部效度和失败实验的影响。", "当前没有独立复核或全文精读。")
            ],
            forbidden_claims=["不得将用户提交的描述直接提升为可泛化的因果结论。"],
        ),
        PaperBlueprintSection(
            section="结论",
            writing_goal=infer(
                "概括研究问题、已提交结果范围和下一步验证任务。", "研究画像、计划和实验结果证据。"
            ),
            evidence_references=[*profile_refs, *experiment_refs],
            missing_evidence=[
                verify(
                    "投稿前核对全部主张与来源、伦理和格式要求。",
                    "投稿就绪度始终需要用户与导师审阅。",
                )
            ],
            forbidden_claims=["不得宣称论文已投稿、已录用或研究结论已被独立验证。"],
        ),
    ]
    return PaperBlueprint(
        conversation_id=conversation_id,
        candidate_titles=[infer(f"{topic}：围绕“{question}”的初步研究", "研究主题与核心问题。")],
        target_submission_direction=verify(
            "目标投稿方向待用户与导师结合格式、受众和证据完整度确认。",
            "当前没有用户确认的目标期刊或会议。",
        ),
        abstract_requirements=[
            infer("说明待回答的研究问题。", "已确认科研画像。"),
            infer("说明已计划或已执行的方法范围。", "规则研究计划和用户提交记录。"),
            (
                infer("仅概述已保存的用户提交结果。", "实验结果证据包。")
                if has_results
                else verify("提交实际结果后再撰写摘要结果句。", "没有实验结果事实。")
            ),
            verify("在摘要中写明关键局限、数据/伦理边界和待验证项。", "当前证据范围有限。"),
        ],
        sections=sections,
        submission_readiness=readiness,
        gaps=[item for section in sections for item in section.missing_evidence][:12],
        provenance_note="论文蓝图由已保存的科研画像、规则研究计划、用户主动保存的受限来源元数据/摘要和用户提交实验文本离线组织；不是论文全文、实验复核或投稿资格判断，不联网、不读文件、不运行代码。",
    )


def _entry(classification: str):
    return lambda content, basis: PaperBlueprintEntry(
        content=content, classification=classification, basis=basis
    )


def _profile_references(profile: ResearchProfile) -> list[PaperBlueprintReference]:
    values = [
        profile.topic,
        *profile.research_questions,
        *profile.candidate_questions,
        profile.context,
    ]
    return [
        PaperBlueprintReference(
            source_type="research_profile",
            label=value,
            classification="fact",
            information_scope="user_confirmed_profile",
        )
        for value in values
        if value
    ][:8]


def _plan_references(plan: ConversationResearchPlan | None) -> list[PaperBlueprintReference]:
    if plan is None:
        return []
    entries = [
        plan.research_goal,
        *plan.candidate_methods_or_baselines,
        *plan.suggested_datasets_or_metrics,
    ]
    return [
        PaperBlueprintReference(
            source_type="research_plan",
            label=entry.content,
            classification=entry.classification,
            information_scope="rules_plan_suggestion",
        )
        for entry in entries
    ][:10]


def _academic_references(
    bundles: list[ConversationEvidenceBundle],
) -> list[PaperBlueprintReference]:
    result: list[PaperBlueprintReference] = []
    for bundle in bundles:
        for paper in bundle.papers:
            result.append(
                PaperBlueprintReference(
                    source_type="academic_evidence",
                    bundle_id=bundle.bundle_id,
                    label=paper.title,
                    classification="fact",
                    source_url=paper.url,
                    information_scope="metadata_and_abstract_only",
                )
            )
    return result[:24]


def _experiment_fact_references(
    bundles: list[ExperimentEvidenceBundle],
) -> list[PaperBlueprintReference]:
    result: list[PaperBlueprintReference] = []
    for bundle in bundles:
        for item in [bundle.experiment_name, bundle.goal, *bundle.items]:
            if item.classification == "fact":
                result.append(
                    PaperBlueprintReference(
                        source_type="experiment_evidence",
                        bundle_id=bundle.bundle_id,
                        label=item.content,
                        classification="fact",
                        information_scope="user_submitted_text_unverified",
                    )
                )
    return result[:24]
