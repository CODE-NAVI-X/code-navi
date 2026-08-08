"""Rules-only submission-readiness checks for local paper artifacts."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime

from .conversation_schemas import (
    PaperDraft,
    PaperExportFile,
    PaperExportPackage,
    PaperReview,
    PaperRevision,
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
    if any(pattern.search(text) for pattern in _ANONYMITY_PATTERNS):
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
    manual_checks.append(
        _item(
            "venue-format-unchecked",
            "目标 venue 格式",
            "尚未针对指定 venue 的格式、页数、匿名与模板规则核验。",
            "to_verify",
            "当前项目没有 venue 专用模板或自动投稿能力。",
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
) -> PaperExportPackage:
    """Build two browser-downloadable text files without ZIP, network access, or writes."""
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
    markdown = _redact_export_text(
        "# 本地论文辅助包（非最终投稿格式）\n\n"
        "仅由用户明确导出；不包含会话历史、数据库、论文全文缓存或项目文件。"
        "建议和待验证项不等于已验证实验结论、导师结论或投稿资格。\n\n"
        f"## 初稿：{draft.title}\n\n{draft.content}\n\n"
        f"## 修订稿预览（v{revision.version}）\n\n{revision.content}\n\n"
        "## 已接受任务对应的修改说明\n\n"
        + "\n".join(f"- {summary}" for summary in revision.change_summary)
        + "\n\n## 结构化审稿意见\n\n"
        + review_lines
        + f"\n\n## 投稿前检查：{readiness.readiness_status}\n\n"
        + check_lines
    )
    check_json = _redact_export_text(
        json.dumps(
            {
                "review": review.model_dump(mode="json"),
                "submission_readiness": readiness.model_dump(mode="json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
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
            "仅包含当前本地保存的初稿、修订预览、审稿意见与投稿前检查；"
            "浏览器下载仍需要用户主动点击。"
        ),
    )
