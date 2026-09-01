"""Rules-only submission-readiness checks for local paper artifacts."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime

from .conversation_schemas import (
    ConversationResearchPlan,
    PaperDraft,
    PaperExportFile,
    PaperExportPackage,
    PaperReview,
    PaperRevision,
    ResearchProfile,
    SelectedCitation,
    SubmissionProfile,
    SubmissionReadinessCheck,
    SubmissionReadinessItem,
)

_REQUIRED_HEADINGS = ("摘要", "引言", "方法", "实验", "结论")
_LOCAL_PATH_PATTERN = re.compile(r"(?i)[a-z]:\\(?:users|home|private)\\[^\s`\"']+")
_ANONYMITY_PATTERNS = (
    re.compile(r"(?i)(?:姓名|学号|机构|单位)\s*[:：]"),
    re.compile(r"(?i)github\.com/[a-z0-9_.-]+"),
    _LOCAL_PATH_PATTERN,
)


def _item(
    item_id: str,
    category: str,
    message: str,
    classification: str,
    basis: str,
    source_scope: str,
) -> SubmissionReadinessItem:
    return SubmissionReadinessItem(
        id=item_id,
        category=category,
        message=message,
        classification=classification,
        basis=basis,
        source_scope=source_scope,
    )


def build_submission_readiness(
    draft: PaperDraft,
    review: PaperReview | None,
    revision: PaperRevision | None,
    *,
    has_academic_evidence: bool,
    has_experiment_evidence: bool,
    submission_profile: SubmissionProfile | None = None,
    reproduction_evaluation: dict[str, object] | None = None,
) -> SubmissionReadinessCheck:
    """Check only saved local artifacts; no network/model call is made here."""
    blockers: list[SubmissionReadinessItem] = []
    warnings: list[SubmissionReadinessItem] = []
    manual_checks: list[SubmissionReadinessItem] = []
    text = revision.content if revision is not None else draft.content
    lowered = text.casefold()
    headings = {section.heading.casefold() for section in draft.sections}

    if revision is None:
        blockers.append(
            _item(
                "missing-revision-preview",
                "修订稿",
                "尚未生成用户确认任务对应的修订稿预览，不能视为投稿辅助包已收口。",
                "to_verify",
                "当前草稿没有已保存的修订版本。",
                "manual_confirmation",
            )
        )
    for heading in _REQUIRED_HEADINGS:
        if heading not in headings and not (heading == "实验" and "结果" in headings):
            blockers.append(
                _item(
                    f"missing-section-{heading}",
                    "章节结构",
                    f"未识别到“{heading}”章节，请由作者补充或确认章节命名。",
                    "to_verify",
                    "仅按用户提交的草稿标题进行本地识别，未解析 DOCX/PDF。",
                    "draft_text",
                )
            )
    if "关键词" not in lowered:
        warnings.append(
            _item(
                "missing-keywords",
                "元信息",
                "未找到关键词段落；请按目标 venue 的要求人工补充。",
                "to_verify",
                "草稿文本中没有“关键词”标识。",
                "draft_text",
            )
        )
    if "[待" in text:
        blockers.append(
            _item(
                "unresolved-placeholders",
                "待验证主张",
                "修订稿仍含“[待…]”占位符，相关主张或材料尚未完成核验。",
                "to_verify",
                "占位符由规则修订预览保留，避免补造实验结果或引用。",
                "revision_preview" if revision else "draft_text",
            )
        )
    if review is not None:
        for finding in review.findings:
            if finding.classification == "to_verify" and finding.severity in {"blocker", "major"}:
                blockers.append(
                    _item(
                        f"review-{finding.id}",
                        "主张与证据",
                        f"审稿检查仍标记：{finding.issue}",
                        "to_verify",
                        finding.basis,
                        "paper_review",
                    )
                )
        if any(task.status == "pending" for task in review.revision_tasks):
            warnings.append(
                _item(
                    "pending-revision-tasks",
                    "修订任务",
                    "仍有审稿任务未由用户接受或跳过；请人工确认其处理状态。",
                    "to_verify",
                    "系统不会自动批量改写初稿。",
                    "paper_review",
                )
            )
    if not has_experiment_evidence:
        blockers.append(
            _item(
                "missing-experiment-evidence",
                "实验记录",
                "没有已保存的用户实验结果证据包，结果性主张必须保持待验证。",
                "to_verify",
                "fact 只能来自用户明确提交的实验记录或已保存证据。",
                "experiment_evidence",
            )
        )
    if not has_academic_evidence:
        warnings.append(
            _item(
                "missing-academic-evidence",
                "引用与文献",
                "没有已保存的受限学术检索证据；请人工核对引用、链接与 DOI。",
                "to_verify",
                "本检查不会自动联网或补造参考文献。",
                "academic_metadata_abstract",
            )
        )
    identity_signal_found = any(pattern.search(text) for pattern in _ANONYMITY_PATTERNS)
    if (
        identity_signal_found
        and submission_profile is not None
        and submission_profile.anonymity_required is True
    ):
        blockers.append(
            _item(
                "anonymity-risk",
                "匿名投稿",
                (
                    "检测到可能的身份、机构、个人路径或 GitHub 用户名线索；"
                    "请按目标 venue 要求人工脱敏。"
                ),
                "to_verify",
                "仅为模式匹配提示，不判断目标 venue 的具体匿名规则。",
                "revision_preview" if revision else "draft_text",
            )
        )
    elif identity_signal_found and (
        submission_profile is None or submission_profile.anonymity_required is None
    ):
        manual_checks.append(
            _item(
                "identity-information-manual-check",
                "匿名投稿",
                "检测到可能的身份或机构线索；是否需要匿名处理取决于你尚未确认的目标投稿方向。",
                "to_verify",
                "只做本地模式匹配，不读取或抓取任何 venue 的投稿规则。",
                "manual_confirmation",
            )
        )
    if not any(marker in lowered for marker in ("伦理", "匿名", "知情同意", "数据许可")):
        manual_checks.append(
            _item(
                "ethics-data-confirmation",
                "伦理与数据许可",
                "请确认是否需要补充伦理审批、匿名化、知情同意或数据许可说明。",
                "to_verify",
                "当前文本未直接提供这些材料的充分证据。",
                "manual_confirmation",
            )
        )
    if not any(marker in lowered for marker in ("图", "表", "附录", "代码可用性", "材料可用性")):
        manual_checks.append(
            _item(
                "materials-availability",
                "图表与材料",
                "请确认图表、附录、代码或材料可用性声明是否需要补充。",
                "to_verify",
                "本地草稿与修订预览未显示相应声明。",
                "manual_confirmation",
            )
        )
    if submission_profile is None or submission_profile.target_venue is None:
        manual_checks.append(
            _item(
                "target-venue-pending",
                "目标投稿方向",
                "目标投稿方向（venue）待用户确认；系统不会猜测会议、期刊、格式或页数要求。",
                "to_verify",
                "尚未保存用户明确填写的目标投稿方向。",
                "submission_profile",
            )
        )
    else:
        manual_checks.append(
            _item(
                "venue-format-unchecked",
                "目标 venue 格式",
                f"已记录目标投稿方向“{submission_profile.target_venue}”，仍需作者或导师按正式规范核验格式、页数与模板。",
                "to_verify",
                "本地规则不会联网抓取 venue 官网，也没有专用模板或自动投稿能力。",
                "submission_profile",
            )
        )
    if submission_profile is None or submission_profile.anonymity_required is None:
        manual_checks.append(
            _item(
                "anonymity-requirement-pending",
                "匿名要求",
                "匿名要求待用户确认；在确认前，系统不会将身份线索判断为已满足或不需要处理。",
                "to_verify",
                "投稿准备档案没有记录匿名要求。",
                "submission_profile",
            )
        )
    if (
        submission_profile is not None
        and submission_profile.ethics_and_data_requirements is not None
        and not any(marker in lowered for marker in ("伦理", "匿名", "知情同意", "数据许可"))
    ):
        manual_checks.append(
            _item(
                "ethics-data-requirements-pending",
                "伦理与数据要求",
                "已记录的伦理或数据要求尚未在当前草稿/修订预览中找到直接说明，请作者补充并核对。",
                "to_verify",
                "只有用户提交的文本能支持事实；系统不推断伦理审批、匿名化或数据许可已完成。",
                "submission_profile",
            )
        )
    if (
        submission_profile is not None
        and submission_profile.length_or_section_requirements is not None
    ):
        manual_checks.append(
            _item(
                "length-section-requirements-manual-check",
                "篇幅与章节要求",
                "已记录用户填写的篇幅或章节要求；请按目标 venue 的正式模板人工核对。",
                "to_verify",
                "Markdown/纯文本草稿不能可靠验证排版页数或 venue 专用章节规则。",
                "submission_profile",
            )
        )
    if reproduction_evaluation is not None:
        eval_data = reproduction_evaluation
        schema_version = eval_data.get("schema_version")
        if schema_version == "reproduction-project-evaluation.v1":
            earned = eval_data.get("score_summary", {}).get("earned_score", 0)
            manual_checks.append(
                _item(
                    "historical-reproduction-evaluation",
                    "复现评估",
                    (
                        f"检测到历史口径复现评估（得分：{earned}/100），该快照属于 v1 历史口径，"
                        "不参与当前 12 分制投稿准备度门控判定；请人工核验或重新触发新版评估。"
                    ),
                    "to_verify",
                    "历史评估快照保留供只读查阅，不参与新版投稿就绪度阈值计算。",
                    "manual_confirmation",
                )
            )
        elif schema_version == "reproduction-project-evaluation.v2":
            total_score = eval_data.get("total_score", 0)
            manual_checks.append(
                _item(
                    "reproduction-evaluation-v2-record",
                    "复现评估",
                    (
                        f"最新复现评估已记录（当前记录完整度：{total_score}/12 分）；"
                        "准则得分仅代表记录完整度与条目规范性，各项实验结论与论文主张仍待作者或导师人工核验。"
                    ),
                    "to_verify",
                    "复现评估基于已保存画像与方案的规则打分，不代表论文录用或复现成功。",
                    "manual_confirmation",
                )
            )
    fact_boundary_notes = [
        _item(
            "fact-boundary",
            "事实边界",
            "本检查仅汇总已保存的草稿、审稿、修订预览与证据状态；它不代表导师结论、同行评审或投稿资格。",
            "fact",
            "没有联网、没有读取论文全文、没有调用模型，也没有写入用户项目。",
            "manual_confirmation",
        )
    ]
    recommended_next_actions = [
        _item(
            "next-manual-check",
            "下一步",
            "逐项处理 blocker 与待验证项，并请导师或目标 venue 的正式规范完成最终核验。",
            "inference",
            "这是基于当前检查清单的建议，不是录用或投稿判断。",
            "manual_confirmation",
        )
    ]
    if blockers:
        readiness_status = "not_ready"
    elif warnings:
        readiness_status = "needs_review"
    else:
        readiness_status = "checklist_complete"
    return SubmissionReadinessCheck(
        check_id=str(uuid.uuid4()),
        draft_id=draft.draft_id,
        revision_id=revision.revision_id if revision else None,
        conversation_id=draft.conversation_id,
        submission_profile=submission_profile,
        readiness_status=readiness_status,
        blockers=blockers,
        warnings=warnings,
        manual_checks=manual_checks,
        fact_boundary_notes=fact_boundary_notes,
        recommended_next_actions=recommended_next_actions,
        created_at=datetime.now(UTC),
    )


def _redact_export_text(value: str) -> str:
    value = re.sub(r"(?i)(api[_ -]?key\s*[:=]\s*)\S+", r"\1[已隐藏]", value)
    value = re.sub(r"(?i)sk-[a-z0-9_-]+", "[已隐藏]", value)
    return _LOCAL_PATH_PATTERN.sub("[已隐藏本地路径]", value)


def build_paper_export_package(
    draft: PaperDraft,
    review: PaperReview,
    revision: PaperRevision,
    readiness: SubmissionReadinessCheck,
    *,
    research_profile: ResearchProfile,
    research_plan: ConversationResearchPlan | None,
    revisions: list[PaperRevision],
    selected_citations: list[SelectedCitation],
) -> PaperExportPackage:
    """Build metadata-only browser downloads without network access or writes."""
    review_lines = "\n".join(
        "\n".join(
            (
                f"- [{item.severity}/{item.classification}] {item.section}：{item.issue}",
                f"  - 依据：{item.basis}",
                f"  - 建议：{item.recommended_action}",
            )
        )
        for item in review.findings
    )
    check_lines = "\n".join(
        f"- [{item.classification}] {item.category}：{item.message}\n  - 依据：{item.basis}"
        for group in (
            readiness.blockers,
            readiness.warnings,
            readiness.manual_checks,
            readiness.fact_boundary_notes,
            readiness.recommended_next_actions,
        )
        for item in group
    )
    profile_summary = {
        "topic": research_profile.topic,
        "research_questions": research_profile.research_questions,
        "methods": research_profile.methods,
        "data_requirements": research_profile.data_requirements,
        "constraints": research_profile.constraints,
        "expected_output": research_profile.expected_output,
    }
    plan_summary = (
        {
            "research_title": research_plan.research_title.model_dump(mode="json"),
            "research_goal": research_plan.research_goal.model_dump(mode="json"),
            "pending_items": [item.model_dump(mode="json") for item in research_plan.pending_items],
            "provenance_note": research_plan.provenance_note,
        }
        if research_plan is not None
        else {"status": "待确认：研究计划尚未就绪"}
    )
    revision_chain = [
        {
            "revision_id": item.revision_id,
            "parent_revision_id": item.parent_revision_id,
            "version": item.version,
            "review_id": item.review_id,
            "applied_task_ids": item.applied_task_ids,
            "applied_suggestion_ids": item.applied_suggestion_ids,
            "change_summary": item.change_summary,
            "created_at": item.created_at.isoformat(),
            "source_scope": item.source_scope,
        }
        for item in revisions
    ]
    citation_summaries = [
        {
            "selected_citation_id": item.selected_citation_id,
            "title": item.citation.paper_title,
            "authors": item.citation.authors,
            "year": item.citation.year,
            "source_name": item.citation.source_name,
            "url": item.citation.url,
            "target_section": item.target_section,
            "citation_placeholder": item.citation_placeholder,
            "metadata_completeness": item.citation.metadata_completeness,
            "to_verify_items": item.reference_entry.to_verify_items,
            "source_scope": item.citation.source_scope,
        }
        for item in selected_citations
    ]
    package_data = {
        "research_profile_summary": profile_summary,
        "research_plan_summary": plan_summary,
        "submission_profile": readiness.submission_profile.model_dump(mode="json")
        if readiness.submission_profile is not None
        else {"status": "待确认：尚未保存投稿准备档案"},
        "submission_readiness": readiness.model_dump(mode="json"),
        "draft_reference": {
            "draft_id": draft.draft_id,
            "title": draft.title,
            "format": draft.format,
            "version": draft.version,
            "created_at": draft.created_at.isoformat(),
            "source_scope": draft.source_scope,
            "content_included": False,
        },
        "revision_chain": revision_chain,
        "revision_task_basis": {
            "latest_revision_id": revision.revision_id,
            "applied_task_ids": revision.applied_task_ids,
            "applied_suggestion_ids": revision.applied_suggestion_ids,
            "change_summary": revision.change_summary,
        },
        "selected_citation_summaries": citation_summaries,
        "review": review.model_dump(mode="json"),
        "safety_notice": "不含初稿或修订稿全文；所有清单仍需作者或导师核对。",
    }
    citation_lines = "\n".join(
        f"- {item['title']}（{item['target_section']}）：{item['citation_placeholder']}"
        for item in citation_summaries
    ) or "- 待确认：尚未选择可引用的受限证据来源。"
    markdown = _redact_export_text(
        "# 投稿前辅助包（非最终投稿格式）\n\n"
        "仅由用户明确导出；仅含已保存的结构化摘要、档案和核对清单，"
        "不含初稿或修订稿全文。建议和待验证项不等于已验证实验结论、导师结论或投稿资格。\n\n"
        f"## 研究主题\n\n{research_profile.topic or '待确认'}\n\n"
        f"## 研究计划摘要\n\n{plan_summary}\n\n"
        f"## 投稿准备档案\n\n{package_data['submission_profile']}\n\n"
        "## 修订版本链（仅元数据）\n\n"
        + "\n".join(
            f"- v{item['version']}：{'；'.join(item['change_summary'])}" for item in revision_chain
        )
        + "\n\n## 修订任务依据\n\n"
        + "\n".join(f"- {summary}" for summary in revision.change_summary)
        + "\n\n## 已选受限证据来源摘要\n\n"
        + citation_lines
        + "\n\n## 结构化审稿意见\n\n"
        + review_lines
        + f"\n\n## 投稿前检查：{readiness.readiness_status}\n\n"
        + check_lines
        + "\n\n> 待作者或导师核对：本辅助包不代表符合任何 venue 要求，也不会自动投稿。"
    )
    check_json = _redact_export_text(json.dumps(package_data, ensure_ascii=False, indent=2))
    return PaperExportPackage(
        draft_id=draft.draft_id,
        revision_id=revision.revision_id,
        readiness_check_id=readiness.check_id,
        files=[
            PaperExportFile(
                filename="paper-assistant-package.md",
                content_type="text/markdown",
                content=markdown,
            ),
            PaperExportFile(
                filename="paper-assistant-checks.json",
                content_type="application/json",
                content=check_json,
            ),
        ],
        provenance_note=(
            "仅包含当前本地保存的研究与计划摘要、投稿档案、检查清单、修订依据和"
            "已选引用摘要；不含初稿或修订稿全文，浏览器下载仍需要用户主动点击。"
        ),
    )
