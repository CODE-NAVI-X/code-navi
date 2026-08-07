"""Rules-first local paper-draft review and revision-preview helpers."""

from __future__ import annotations

import difflib
import json
import re
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from .conversation_schemas import (
    ConversationEvidenceBundle,
    ExperimentEvidenceBundle,
    PaperBlueprint,
    PaperDraft,
    PaperReview,
    PaperRevision,
    PaperSection,
    ResearchProfile,
    ReviewFinding,
    RevisionTask,
)
from .research_artifact_llm import ResearchArtifactGenerator

_EXPECTED_SECTIONS = ("摘要", "引言", "方法", "实验", "结果", "讨论", "局限", "结论")
_CLAIM_PATTERN = re.compile(r"显著(?:提升|改善|差异)|证明(?:了)?(?:.*?)(?:有效|优于)")


class _ReviewExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    finding_id: str
    why_it_matters: str = Field(min_length=1, max_length=2000)
    recommended_action: str = Field(min_length=1, max_length=2000)


class _ReviewExplanationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explanations: list[_ReviewExplanation] = Field(max_length=40)


def parse_paper_sections(content: str, *, format: str) -> list[PaperSection]:
    """Parse only user-pasted headings; plain text safely remains one section."""
    if format == "markdown":
        matches = list(re.finditer(r"^(#{1,6})\s+(.+?)\s*$", content, re.MULTILINE))
        if matches:
            sections: list[PaperSection] = []
            for order, match in enumerate(matches, start=1):
                end = matches[order].start() if order < len(matches) else len(content)
                body = content[match.end() : end].strip()
                sections.append(
                    PaperSection(
                        section_id=f"section-{order}",
                        heading=match.group(2).strip(),
                        content=body or "[该章节尚未填写内容]",
                        order=order,
                    )
                )
            return sections
    return [
        PaperSection(
            section_id="section-1",
            heading="未分节原稿",
            content=content,
            order=1,
        )
    ]


def build_rules_paper_review(
    draft: PaperDraft,
    *,
    profile: ResearchProfile,
    blueprint: PaperBlueprint,
    academic_evidence: list[ConversationEvidenceBundle],
    experiment_evidence: list[ExperimentEvidenceBundle],
    generator: ResearchArtifactGenerator | None = None,
    conversation_id: str | None = None,
) -> PaperReview:
    """Review only saved inputs; model wording can never change rule classifications."""
    headings = " ".join(section.heading for section in draft.sections)
    findings: list[ReviewFinding] = []
    requirements = (
        ("摘要", ("摘要",)),
        ("引言", ("引言",)),
        ("方法", ("方法",)),
        ("实验或结果", ("实验", "结果")),
        ("讨论或局限", ("讨论", "局限")),
        ("结论", ("结论",)),
    )
    for label, alternatives in requirements:
        if not any(item in headings for item in alternatives):
            findings.append(
                _finding(
                    f"missing-{label}",
                    "major",
                    label,
                    f"初稿缺少“{label}”章节或可识别标题。",
                    "章节缺失会让研究问题、证据和限制难以被审阅。",
                    f"补充“{label}”小节，并仅引用已保存的研究计划、文献元数据或实验记录。",
                    "to_verify",
                    "基于用户粘贴原稿中可解析的章节标题。",
                    "draft_text",
                )
            )
    if not experiment_evidence:
        findings.append(
            _finding(
                "missing-experiment-evidence",
                "major",
                "实验/结果",
                "尚未保存用户提交的实验结果证据包。",
                "结果章节不能用模型推测或未核验文字替代真实实验记录。",
                "先录入实际设置、指标、结果、失败案例和限制，再修订结果与讨论。",
                "to_verify",
                "当前会话没有 ExperimentEvidenceBundle。",
                "experiment_evidence",
                "实验章节的事实依据",
            )
        )
    for index, match in enumerate(_CLAIM_PATTERN.finditer(draft.content), start=1):
        claim = match.group(0)
        findings.append(
            _finding(
                f"unsupported-claim-{index}",
                "major",
                "实验/结果",
                f"“{claim}”缺少已保存实验事实的直接支持。",
                "未经证据支撑的效果或证明性表述会越过当前事实边界。",
                "改为“[待补充实验结果]”，或补充对应的指标、对照、样本与用户提交结果。",
                "to_verify",
                "该主张出现在用户原稿；当前规则不会把原稿主张视为实验事实。",
                "draft_text",
                "实验章节的禁止主张",
            )
        )
    if not any(token in draft.content for token in ("伦理", "匿名", "许可", "知情同意")):
        findings.append(
            _finding(
                "missing-ethics-boundary",
                "major",
                "方法/实验",
                "初稿未说明匿名化、数据许可或伦理待确认项。",
                "涉及学习记录或参与者时，这些条件不能从研究主题中推断。",
                "补充数据来源、匿名化、许可/伦理状态；未知内容使用“待确认”。",
                "to_verify",
                "用户原稿和保存实验记录中没有可直接支持的伦理说明。",
                "draft_text",
            )
        )
    if not academic_evidence:
        findings.append(
            _finding(
                "missing-citation-evidence",
                "minor",
                "引言/相关工作",
                "尚未保存受限学术检索的文献元数据或摘要证据。",
                "相关工作不能由模型补造引用或论文结论。",
                "在用户主动检索后，只引用 EvidenceBundle 中保存的链接与摘要范围。",
                "to_verify",
                "当前会话没有保存的 ConversationEvidenceBundle。",
                "academic_metadata_abstract",
            )
        )
    if not findings:
        findings.append(
            _finding(
                "review-boundary-reminder",
                "suggestion",
                "全文",
                "已识别基本章节；仍需逐项核对事实、引用与投稿规范。",
                "本地规则审稿不会替代导师、同行评审或期刊格式检查。",
                "逐项核对论文蓝图中的缺口和禁止主张。",
                "inference",
                "根据已保存蓝图与初稿结构生成的审阅建议。",
                "research_plan",
            )
        )
    now = datetime.now(UTC)
    rules = PaperReview(
        review_id=str(uuid.uuid4()),
        draft_id=draft.draft_id,
        conversation_id=draft.conversation_id,
        findings=findings,
        revision_tasks=[
            RevisionTask(
                task_id=str(uuid.uuid4()),
                finding_id=item.id,
                finding=item,
                created_at=now,
                updated_at=now,
            )
            for item in findings
        ],
        provenance_note=(
            "规则审稿只对照用户原稿、已保存研究画像/计划、受限检索元数据摘要和用户提交实验记录；"
            "所有意见均为建议，不是导师、同行评审或投稿结论。"
        ),
        created_at=now,
    )
    return _enhance_review(
        rules,
        generator=generator,
        conversation_id=conversation_id,
        profile=profile,
        blueprint=blueprint,
    )


def build_revision_preview(
    review: PaperReview, draft: PaperDraft, *, version: int
) -> PaperRevision:
    accepted = [task for task in review.revision_tasks if task.status == "accepted"]
    if not accepted:
        raise ValueError("请先明确接受至少一项修订任务；系统不会自动批量改稿。")
    additions = "\n\n## 人工确认的修订建议（未自动覆盖原稿）\n" + "\n".join(
        f"- [{task.finding.section}] {task.finding.recommended_action}"
        f"（依据：{task.finding.basis}；边界：{task.finding.classification}）"
        for task in accepted
    )
    content = draft.content.rstrip() + additions + "\n"
    diff = "\n".join(
        difflib.unified_diff(
            draft.content.splitlines(),
            content.splitlines(),
            fromfile=f"draft-v{draft.version}",
            tofile=f"revision-v{version}",
            lineterm="",
        )
    )
    return PaperRevision(
        revision_id=str(uuid.uuid4()),
        parent_draft_id=draft.draft_id,
        review_id=review.review_id,
        version=version,
        content=content,
        applied_task_ids=[task.task_id for task in accepted],
        change_summary=[f"{task.finding.section}：{task.finding.issue}" for task in accepted],
        diff_preview=diff or "[未产生文本差异]",
        created_at=datetime.now(UTC),
    )


def _finding(
    finding_id: str,
    severity: str,
    section: str,
    issue: str,
    why: str,
    action: str,
    classification: str,
    basis: str,
    source_scope: str,
    related: str | None = None,
) -> ReviewFinding:
    return ReviewFinding(
        id=finding_id,
        severity=severity,
        section=section,
        issue=issue,
        why_it_matters=why,
        recommended_action=action,
        classification=classification,
        basis=basis,
        source_scope=source_scope,
        related_blueprint_item=related,
        can_auto_suggest=True,
    )


def _enhance_review(
    rules: PaperReview,
    *,
    generator: ResearchArtifactGenerator | None,
    conversation_id: str | None,
    profile: ResearchProfile,
    blueprint: PaperBlueprint,
) -> PaperReview:
    if generator is None:
        return rules
    if conversation_id is None:
        raise ValueError("conversation_id is required for model paper review")
    outcome = generator.generate(
        kind="paper_review",
        conversation_id=conversation_id,
        context={
            "profile": profile.model_dump(mode="json"),
            "blueprint": blueprint.model_dump(mode="json"),
            "rule_findings": [item.model_dump(mode="json") for item in rules.findings],
            "required_json_shape": {
                "explanations": [
                    {
                        "finding_id": "existing id",
                        "why_it_matters": "string",
                        "recommended_action": "string",
                    }
                ]
            },
        },
    )
    if outcome.status == "unavailable":
        return rules
    if outcome.status != "generated" or outcome.text is None:
        return rules.model_copy(update={"generation_mode": "rules_fallback"})
    try:
        payload = _ReviewExplanationPayload.model_validate_json(outcome.text)
        by_id = {item.finding_id: item for item in payload.explanations}
        if not by_id or not set(by_id).issubset({item.id for item in rules.findings}):
            raise ValueError("model referenced an unknown finding")
        findings = [
            item.model_copy(
                update={
                    "why_it_matters": by_id[item.id].why_it_matters,
                    "recommended_action": by_id[item.id].recommended_action,
                }
            )
            if item.id in by_id
            else item
            for item in rules.findings
        ]
        tasks = [
            task.model_copy(
                update={"finding": next(item for item in findings if item.id == task.finding_id)}
            )
            for task in rules.revision_tasks
        ]
        return rules.model_copy(
            update={
                "findings": findings,
                "revision_tasks": tasks,
                "generation_mode": "llm",
                "run_id": outcome.run_id,
                "event_count": outcome.event_count,
            }
        )
    except (ValueError, json.JSONDecodeError):
        return rules.model_copy(update={"generation_mode": "rules_fallback"})
