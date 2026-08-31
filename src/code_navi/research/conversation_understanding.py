"""LLM-authored, evidence-bound comprehension checks inside paper analysis.

The understanding check is not a standalone panel; it is embedded in the paper
deep-analysis flow. Questions and assessments are model-authored from the saved
paper metadata/abstract scope only; identity, ownership, status transitions and
timestamps stay program-controlled. ``section_key`` is a deterministic,
program-derived link between mind-map nodes and paper-analysis sections — the
model never produces DOM ids, coordinates, or section keys.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from .conversation_schemas import (
    EvidenceReference,
    UnderstandingCheck,
    UnderstandingCheckStatus,
)
from .research_artifact_llm import ResearchArtifactGenerator
from .research_generation import ResearchGenerationError, require_generated_artifact
from .schemas import AcademicPaperResult

_QUESTION_PROVENANCE = (
    "理解检查问题由模型仅基于用户选中论文的元数据与来源摘要生成；"
    "不下载全文，不要求用户回答只有全文才有的信息，不替用户作答，不声称已运行实验。"
)
_ASSESS_PROVENANCE = (
    "理解评估由模型仅基于当前论文摘要/元数据范围与用户回答生成；"
    "不表示论文结论正确、不表示可复现、不表示实验成功，也不替代导师结论。"
)

_AREA_TO_SECTION: tuple[tuple[str, str], ...] = (
    ("待核验", "to_verify"),
    ("研究问题", "research_question"),
    ("问题", "research_question"),
    ("核心方法", "core_method"),
    ("方法", "core_method"),
    ("数据集", "dataset"),
    ("数据", "dataset"),
    ("贡献", "contribution"),
    ("背景", "background"),
    ("动机", "motivation"),
    ("实验设计", "experiment"),
    ("实验", "experiment"),
    ("评价指标", "metrics"),
    ("指标", "metrics"),
    ("结果", "results"),
    ("局限", "limitations"),
    ("复现", "reproduction"),
)

_SECTION_LABEL: dict[str, str] = {
    "research_question": "研究问题",
    "core_method": "核心方法",
    "dataset": "数据集与评价指标",
    "to_verify": "待核验内容",
    "contribution": "论文贡献",
    "background": "研究背景",
    "motivation": "研究动机",
    "experiment": "实验设计",
    "metrics": "评价指标",
    "results": "实验结果",
    "limitations": "局限性",
    "reproduction": "可复现部分",
    "other": "当前章节",
}

_FORBIDDEN_ESTABLISHED_FACTS = (
    "复现成功",
    "实验成功",
    "已运行",
    "已训练",
    "训练完成",
    "导师结论",
    "导师认可",
    "已读取全文",
    "已下载全文",
)


def section_key_for_area(area: str) -> str:
    """Deterministically map a paper-analysis area to a stable section key."""
    normalized = (area or "").strip()
    for needle, key in _AREA_TO_SECTION:
        if needle in normalized:
            return key
    return "other"


def section_label_for_key(section_key: str) -> str:
    """Reverse map for model context; never used as a DOM id."""
    return _SECTION_LABEL.get(section_key, "当前章节")


def _check_id(conversation_id: str, paper_url: str, section_key: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            "|".join(["understanding-check", conversation_id, paper_url, section_key]),
        )
    )


def _paper_context(
    paper: AcademicPaperResult,
    evidence_ref: EvidenceReference | None,
) -> dict[str, object]:
    return {
        "title": paper.title,
        "url": paper.url,
        "source_name": paper.source_name,
        "year": paper.year,
        "doi": paper.doi,
        "arxiv_id": paper.arxiv_id,
        "abstract_excerpt": paper.abstract_excerpt,
        "bundle_id": evidence_ref.bundle_id if evidence_ref else None,
        "evidence_level": evidence_ref.evidence_level if evidence_ref else "metadata",
    }


def _assert_no_established_facts(payload: dict[str, object]) -> None:
    joined = " ".join(
        str(payload.get(field) or "")
        for field in ("assessment", "explanation", "recommended_next_action")
    )
    if any(phrase in joined for phrase in _FORBIDDEN_ESTABLISHED_FACTS):
        raise ResearchGenerationError(
            "invalid_output",
            "understanding_assessment: model asserted an established experimental fact",
        )


def _map_status(level: str) -> UnderstandingCheckStatus:
    if level == "understood":
        return "understood"
    if level == "partially_understood":
        return "partially_understood"
    return "needs_explanation"


def _clean_list(raw: object) -> list[str]:
    return [str(item).strip() for item in raw or [] if str(item).strip()]


def _clean_optional(raw: object) -> str | None:
    value = str(raw).strip() if raw else ""
    return value or None



def build_understanding_question(
    paper: AcademicPaperResult,
    *,
    section_key: str,
    evidence_ref: EvidenceReference | None = None,
    generator: ResearchArtifactGenerator | None = None,
    conversation_id: str | None = None,
) -> UnderstandingCheck:
    """Generate one section-bound question from metadata/abstract scope only."""
    if generator is None:
        raise ResearchGenerationError(
            "provider_unavailable", "understanding_question: generator is unavailable"
        )
    if conversation_id is None:
        raise ValueError("conversation_id is required for understanding question")
    abstract = paper.abstract_excerpt
    source_scope = "metadata_and_abstract_only" if abstract else "metadata_only"
    context = {
        "paper": _paper_context(paper, evidence_ref),
        "section_key": section_key,
        "section_label": section_label_for_key(section_key),
        "source_scope": source_scope,
        "abstract_available": bool(abstract),
        "source_boundary": {
            "allowed_classifications": ["inference", "to_verify"],
            "forbidden": [
                "不得要求用户回答只有论文全文才有的信息。",
                "不得声称已读取全文或已运行实验。",
                "不得替用户作答。",
                "不得改变 paper_url、bundle_id、section_key 或 source_scope。",
                "question 必须针对当前章节并仅来自元数据/摘要范围。",
            ],
        },
        "required_json_shape": {
            "question": "string",
            "question_basis": (
                "string，须说明依据来自摘要、元数据、用户画像或当前分析"
                "结果，并标注 fact/inference/to_verify 边界"
            ),
            "source_scope": source_scope,
            "example": "string 或 null",
        },
    }
    outcome = generator.generate(
        kind="understanding_question",
        context=context,
        conversation_id=conversation_id,
    )
    try:
        raw = json.loads(require_generated_artifact(outcome, kind="understanding_question"))
    except ResearchGenerationError:
        raise
    if not isinstance(raw, dict):
        raise ResearchGenerationError(
            "invalid_output", "understanding_question: JSON root must be an object"
        )
    question = str(raw.get("question") or "").strip()
    basis = str(raw.get("question_basis") or "").strip()
    if not question or not basis:
        raise ResearchGenerationError(
            "invalid_output", "understanding_question: question or basis missing"
        )
    if str(raw.get("source_scope")) != source_scope:
        raise ResearchGenerationError(
            "invalid_output", "understanding_question: source_scope mismatch"
        )
    example = raw.get("example")
    now = datetime.now(UTC)
    return UnderstandingCheck(
        check_id=_check_id(conversation_id, paper.url, section_key),
        conversation_id=conversation_id,
        paper_url=paper.url,
        bundle_id=evidence_ref.bundle_id if evidence_ref else "",
        section_key=section_key,
        question=question,
        question_basis=basis,
        source_scope=source_scope,
        example=str(example).strip() if example else None,
        status="question_ready",
        generation_mode="llm",
        run_id=outcome.run_id,
        event_count=outcome.event_count,
        created_at=now,
        updated_at=now,
    )


def assess_understanding_answer(
    check: UnderstandingCheck,
    *,
    paper: AcademicPaperResult,
    answer: str,
    generator: ResearchArtifactGenerator | None = None,
    conversation_id: str | None = None,
) -> UnderstandingCheck:
    """Assess a user-submitted answer; program controls the resulting status."""
    if generator is None:
        raise ResearchGenerationError(
            "provider_unavailable", "understanding_assessment: generator is unavailable"
        )
    if conversation_id is None:
        raise ValueError("conversation_id is required for understanding assessment")
    context = {
        "paper": _paper_context(paper, None),
        "section_key": check.section_key,
        "section_label": section_label_for_key(check.section_key),
        "question": check.question,
        "source_scope": check.source_scope,
        "user_answer": answer,
        "source_boundary": {
            "allowed_classifications": ["inference", "to_verify"],
            "forbidden": [
                "不得声称已运行实验、复现成功或导师认可。",
                "不得把模型评价描述为实验或复现成功。",
                "不得编造数据集划分、超参数或 Accuracy。",
                "明确指出用户回答中正确与缺失的内容。",
            ],
        },
        "required_json_shape": {
            "assessment": "string",
            "correct_points": ["string"],
            "missing_points": ["string"],
            "explanation": "string 或 null",
            "example": "string 或 null",
            "recommended_next_action": "string",
            "assessment_level": "understood|partially_understood|needs_explanation",
        },
    }
    outcome = generator.generate(
        kind="understanding_assessment",
        context=context,
        conversation_id=conversation_id,
    )
    try:
        raw = json.loads(require_generated_artifact(outcome, kind="understanding_assessment"))
    except ResearchGenerationError:
        raise
    if not isinstance(raw, dict):
        raise ResearchGenerationError(
            "invalid_output", "understanding_assessment: JSON root must be an object"
        )
    _assert_no_established_facts(raw)
    assessment = str(raw.get("assessment") or "").strip()
    if not assessment:
        raise ResearchGenerationError(
            "invalid_output", "understanding_assessment: assessment missing"
        )
    level = str(raw.get("assessment_level") or "").strip()
    status = _map_status(level)
    now = datetime.now(UTC)
    return check.model_copy(
        update={
            "answer": answer,
            "assessment": assessment,
            "correct_points": _clean_list(raw.get("correct_points")),
            "missing_points": _clean_list(raw.get("missing_points")),
            "explanation": _clean_optional(raw.get("explanation")),
            "example": _clean_optional(raw.get("example")),
            "recommended_next_action": _clean_optional(
                raw.get("recommended_next_action")
            ),
            "status": status,
            "generation_mode": "llm",
            "run_id": outcome.run_id,
            "event_count": outcome.event_count,
            "updated_at": now,
        }
    )


__all__ = [
    "section_key_for_area",
    "section_label_for_key",
    "build_understanding_question",
    "assess_understanding_answer",
]
