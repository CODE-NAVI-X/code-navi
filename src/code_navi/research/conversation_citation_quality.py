"""Rules-only citation completeness checks over explicit local selections."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime

from .conversation_schemas import (
    CitationCoverageItem,
    CitationQualityCheck,
    CitationQualityIssue,
    SelectedCitation,
)

CORE_PAPER_SECTIONS = ("引言", "相关工作", "方法", "实验", "讨论", "结论")


def build_citation_quality_check(
    session_id: str,
    selected_citations: list[SelectedCitation],
    *,
    check_id: str,
    checked_at: datetime,
) -> CitationQualityCheck:
    """Inspect saved choices without searching, reading full text, or changing a draft."""
    active = [item for item in selected_citations if item.status != "skipped"]
    if not active:
        return CitationQualityCheck(
            check_id=check_id,
            session_id=session_id,
            checked_at=checked_at,
            quality_status="empty",
            selected_source_count=0,
            unique_source_count=0,
            mapped_section_count=0,
            core_section_coverage_percent=0,
            empty_state_message=(
                "当前没有用户明确保留的引用来源；请先主动选择已保存 EvidenceBundle 中的来源。"
            ),
            boundary_note=_BOUNDARY_NOTE,
        )

    coverage_items = _coverage_items(active)
    uninserted = _uninserted_placeholders(active)
    duplicates = _duplicate_selections(active)
    metadata_gaps = _metadata_gaps(active)
    verification = _author_verification_items(coverage_items)
    mapped_core_sections = {
        item.target_section for item in coverage_items if item.target_section in CORE_PAPER_SECTIONS
    }
    structural_gaps = uninserted or duplicates or metadata_gaps
    return CitationQualityCheck(
        check_id=check_id,
        session_id=session_id,
        checked_at=checked_at,
        quality_status="needs_review" if structural_gaps else "review_ready",
        selected_source_count=len(active),
        unique_source_count=len({item.citation.url.casefold() for item in active}),
        mapped_section_count=len(coverage_items),
        core_section_coverage_percent=round(
            len(mapped_core_sections) * 100 / len(CORE_PAPER_SECTIONS)
        ),
        coverage_items=coverage_items,
        unmapped_core_sections=[
            section for section in CORE_PAPER_SECTIONS if section not in mapped_core_sections
        ],
        uninserted_placeholders=uninserted,
        duplicate_selections=duplicates,
        metadata_gaps=metadata_gaps,
        author_verification_items=verification,
        boundary_note=_BOUNDARY_NOTE,
    )


def _coverage_items(selected: list[SelectedCitation]) -> list[CitationCoverageItem]:
    grouped: dict[tuple[str, str], list[SelectedCitation]] = defaultdict(list)
    for item in selected:
        grouped[(item.target_document, item.target_section)].append(item)

    coverage: list[CitationCoverageItem] = []
    for (target_document, target_section), items in sorted(grouped.items()):
        gaps = _unique(
            gap for item in items for gap in _selection_metadata_gaps(item)
        )
        scopes = sorted({item.citation.abstract_scope for item in items})
        coverage.append(
            CitationCoverageItem(
                target_document=target_document,
                target_section=target_section,
                selected_citation_ids=[item.selected_citation_id for item in items],
                source_titles=[item.citation.paper_title for item in items],
                citation_placeholders=[item.citation_placeholder for item in items],
                status="needs_verification" if gaps else "mapped",
                information_scopes=scopes,
                basis=(
                    "该映射来自用户明确选择；来源是否支持本章节的具体论述仍需作者或导师核对。"
                ),
                to_verify_items=gaps,
            )
        )
    return coverage


def _uninserted_placeholders(selected: list[SelectedCitation]) -> list[CitationQualityIssue]:
    return [
        CitationQualityIssue(
            issue_code="placeholder_not_confirmed_inserted",
            message=f"“{item.citation.paper_title}”的占位尚未由用户确认已人工插入正文。",
            selected_citation_ids=[item.selected_citation_id],
            classification="to_verify",
            basis=f"当前本地选择状态为 {item.status}；系统不会自动修改论文正文。",
        )
        for item in selected
        if item.status != "inserted"
    ]


def _duplicate_selections(selected: list[SelectedCitation]) -> list[CitationQualityIssue]:
    grouped: dict[tuple[str, str, str, str], list[SelectedCitation]] = defaultdict(list)
    for item in selected:
        grouped[
            (
                item.citation.url.casefold(),
                item.target_document,
                item.target_section.casefold(),
                item.paragraph_anchor.casefold(),
            )
        ].append(item)
    return [
        CitationQualityIssue(
            issue_code="duplicate_selection",
            message=f"同一来源在“{items[0].target_section}”的同一位置被重复选择。",
            selected_citation_ids=[item.selected_citation_id for item in items],
            classification="to_verify",
            basis="保存的来源链接、目标文档、章节和段落锚点完全相同。",
        )
        for items in grouped.values()
        if len(items) > 1
    ]


def _metadata_gaps(selected: list[SelectedCitation]) -> list[CitationQualityIssue]:
    issues: list[CitationQualityIssue] = []
    for item in selected:
        gaps = _selection_metadata_gaps(item)
        if not gaps:
            continue
        issues.append(
            CitationQualityIssue(
                issue_code="metadata_gap",
                message=f"“{item.citation.paper_title}”存在待人工核对的来源信息。",
                selected_citation_ids=[item.selected_citation_id],
                classification="to_verify",
                basis="；".join(gaps),
            )
        )
    return issues


def _selection_metadata_gaps(item: SelectedCitation) -> list[str]:
    gaps = list(item.reference_entry.to_verify_items)
    if not item.citation.url.casefold().startswith(("https://", "http://")):
        gaps.append("来源链接待核对")
    if item.citation.abstract_scope == "metadata_only":
        gaps.append("当前只保存元数据，摘要范围内的论述也无法由该条目直接支持")
    return _unique(gaps)


def _author_verification_items(
    coverage_items: list[CitationCoverageItem],
) -> list[CitationQualityIssue]:
    return [
        CitationQualityIssue(
            issue_code="section_support_scope",
            message=f"请人工核对已选来源能否支持“{item.target_section}”中的具体表述。",
            selected_citation_ids=item.selected_citation_ids,
            classification="to_verify",
            basis=(
                "系统只知道用户建立了章节关联；“与章节相关”属于推断，摘要外事实不得据此写入正文。"
            ),
        )
        for item in coverage_items
    ]


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


_BOUNDARY_NOTE = (
    "本检查只读取当前会话中用户明确选择的已保存来源；不联网补全、不读取全文、"
    "不自动插入或改写论文，也不代表引用正确或论文可以投稿。"
)
