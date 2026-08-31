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
    RevisionSuggestion,
    RevisionTask,
)
from .research_artifact_llm import ResearchArtifactGenerator
from .research_generation import ResearchGenerationError, require_generated_artifact

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


class _RevisionSuggestionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    candidate_text: str = Field(min_length=1, max_length=8000)
    rationale: str = Field(min_length=1, max_length=2000)
    to_verify_items: list[str] = Field(default_factory=list, max_length=12)


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


def build_revision_suggestion(
    review: PaperReview,
    draft: PaperDraft,
    task_id: str,
    *,
    generator: ResearchArtifactGenerator | None = None,
    conversation_id: str | None = None,
) -> RevisionSuggestion:
    """Create one bounded candidate for an already accepted task, never a whole-draft rewrite."""
    task = next((item for item in review.revision_tasks if item.task_id == task_id), None)
    if task is None:
        raise LookupError(task_id)
    if task.status != "accepted":
        raise ValueError("请先明确接受该修订任务；系统不会为未接受任务生成改写。")
    section, original = _locate_revision_paragraph(draft, task.finding)
    candidate = _rules_candidate(original, task.finding)
    rules = RevisionSuggestion(
        suggestion_id=str(uuid.uuid4()),
        revision_task_id=task.task_id,
        draft_id=draft.draft_id,
        section_heading=section.heading,
        paragraph_anchor=f"{section.section_id}:paragraph-1",
        original_excerpt=original,
        candidate_text=candidate,
        rationale=task.finding.recommended_action,
        classification=task.finding.classification,
        basis=task.finding.basis,
        source_scope=task.finding.source_scope,
        to_verify_items=["候选改写仅是建议；请核对实验、引用与方法边界。"],
        created_at=datetime.now(UTC),
    )
    return _enhance_revision_suggestion(
        rules,
        generator=generator,
        conversation_id=conversation_id,
        finding=task.finding,
    )


def build_revision_from_suggestion(
    review: PaperReview,
    draft: PaperDraft,
    suggestion: RevisionSuggestion,
    *,
    version: int,
    parent_revision_id: str | None,
    base_content: str,
    candidate_text: str | None,
) -> PaperRevision:
    """Apply exactly one user-confirmed candidate to a preserved draft or revision snapshot."""
    task = next(
        (item for item in review.revision_tasks if item.task_id == suggestion.revision_task_id),
        None,
    )
    if task is None or task.status != "accepted":
        raise ValueError("修订任务尚未被接受，不能创建新版本。")
    text = candidate_text or suggestion.candidate_text
    _validate_candidate_text(text, suggestion.classification)
    if suggestion.original_excerpt not in base_content:
        raise ValueError("候选改写无法定位到父版本中的原文段落；请重新生成候选。")
    content = base_content.replace(suggestion.original_excerpt, text, 1)
    diff = "\n".join(
        difflib.unified_diff(
            base_content.splitlines(),
            content.splitlines(),
            fromfile=f"revision-parent-v{version - 1}",
            tofile=f"revision-v{version}",
            lineterm="",
        )
    )
    manual = candidate_text is not None and candidate_text != suggestion.candidate_text
    return PaperRevision(
        revision_id=str(uuid.uuid4()),
        parent_draft_id=draft.draft_id,
        parent_revision_id=parent_revision_id,
        review_id=review.review_id,
        version=version,
        content=content,
        applied_task_ids=[task.task_id],
        applied_suggestion_ids=[suggestion.suggestion_id],
        change_summary=[
            f"{task.finding.section}：{'用户手动编辑并接受' if manual else '接受候选改写'}"
        ],
        diff_preview=diff or "[未产生文本差异]",
        created_at=datetime.now(UTC),
    )


def _target_section(sections: list[PaperSection], finding_section: str) -> PaperSection:
    tokens = [token for token in re.split(r"[/、或 ]+", finding_section) if token]
    for section in sections:
        if any(token in section.heading for token in tokens):
            return section
    return sections[-1]


def _locate_revision_paragraph(
    draft: PaperDraft, finding: ReviewFinding
) -> tuple[PaperSection, str]:
    """Return a real user-pasted paragraph; placeholders are never replace anchors."""
    section = _target_section(draft.sections, finding.section)
    candidates = [section, *reversed(draft.sections)]
    for candidate_section in candidates:
        if candidate_section.content not in draft.content:
            continue
        paragraphs = [
            value.strip()
            for value in re.split(r"\n\s*\n", candidate_section.content)
            if value.strip()
        ]
        if finding.id.startswith("unsupported-claim"):
            matched = next((value for value in paragraphs if _CLAIM_PATTERN.search(value)), None)
            if matched:
                return candidate_section, matched
        if paragraphs:
            return candidate_section, paragraphs[0]
    raise ValueError("无法定位用户原稿中的真实段落；请补充初稿内容后重新生成候选。")


def _rules_candidate(original: str, finding: ReviewFinding) -> str:
    if finding.id.startswith("unsupported-claim"):
        candidate = _CLAIM_PATTERN.sub("[待补充实验结果]", original)
        return candidate if candidate != original else "[待补充实验结果]"
    return (
        original.rstrip()
        + f"\n\n【待验证修订建议】{finding.recommended_action}\n"
        + "[待导师确认方法边界]"
    )


def _validate_candidate_text(value: str, classification: str) -> None:
    lowered = value.casefold()
    if any(token in lowered for token in ("api_key=", "api_key =", "sk-")):
        raise ValueError("候选改写不得包含密钥。")
    if re.search(r"[a-z]:\\(?:users|home|private)\\", lowered):
        raise ValueError("候选改写不得包含私有本地路径。")
    if classification != "fact" and _CLAIM_PATTERN.search(value):
        raise ValueError("证据不足的候选改写不得写成效果或证明性事实。")


def _enhance_revision_suggestion(
    rules: RevisionSuggestion,
    *,
    generator: ResearchArtifactGenerator | None,
    conversation_id: str | None,
    finding: ReviewFinding,
) -> RevisionSuggestion:
    if generator is None or conversation_id is None:
        return rules
    outcome = generator.generate(
        kind="revision_suggestion",
        conversation_id=conversation_id,
        context={
            "finding": finding.model_dump(mode="json"),
            "original_excerpt": rules.original_excerpt,
            "rules_candidate": rules.candidate_text,
            "required_json_shape": {
                "candidate_text": "string",
                "rationale": "string",
                "to_verify_items": ["string"],
            },
        },
    )
    try:
        payload = _RevisionSuggestionPayload.model_validate_json(
            require_generated_artifact(outcome, kind="revision_suggestion")
        )
        _validate_candidate_text(payload.candidate_text, rules.classification)
        return rules.model_copy(
            update={
                "candidate_text": payload.candidate_text,
                "rationale": payload.rationale,
                "to_verify_items": payload.to_verify_items,
                "generation_mode": "llm",
                "run_id": outcome.run_id,
            }
        )
    except ResearchGenerationError:
        raise
    except (ValueError, json.JSONDecodeError) as error:
        raise ResearchGenerationError(
            "invalid_output", "revision_suggestion: output validation failed"
        ) from error


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
    try:
        payload = _ReviewExplanationPayload.model_validate_json(
            require_generated_artifact(outcome, kind="paper_review")
        )
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
    except ResearchGenerationError:
        raise
    except (ValueError, json.JSONDecodeError) as error:
        raise ResearchGenerationError(
            "invalid_output", "paper_review: output validation failed"
        ) from error
