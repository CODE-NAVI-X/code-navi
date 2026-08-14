"""Deterministic reference-draft packaging over explicit local selections."""

from __future__ import annotations

from .conversation_schemas import (
    ReferenceDraftItem,
    ReferenceDraftPackage,
    ReferenceDraftVerificationItem,
    SelectedCitation,
)

_FORMAT_NOTICE = "非正式格式化参考文献，提交前须由作者或导师按目标格式核对。"
_BOUNDARY_NOTE = (
    "草案只整理当前会话中用户明确保留的已保存元数据；不联网补全、不校验 APA、IEEE、"
    "GB/T 或期刊格式，不读取全文，也不自动写入论文正文。"
)


def build_reference_draft_package(
    session_id: str,
    selected_citations: list[SelectedCitation],
) -> ReferenceDraftPackage:
    """Build stable, copyable text without exposing notes or mutating a paper draft."""
    active = sorted(
        (item for item in selected_citations if item.status != "skipped"),
        key=lambda item: (item.created_at, item.selected_citation_id),
    )
    if not active:
        return ReferenceDraftPackage(
            session_id=session_id,
            empty_state_message=(
                "当前没有用户明确保留的引用来源；请先主动选择已保存 EvidenceBundle 中的来源。"
            ),
            boundary_note=_BOUNDARY_NOTE,
        )

    entries = [_draft_item(item) for item in active]
    verification_items = [
        ReferenceDraftVerificationItem(
            selected_citation_id=item.selected_citation_id,
            source_url=item.citation.url,
            missing_fields=list(item.reference_entry.to_verify_items),
            basis="缺失项直接来自已保存元数据；系统没有联网猜测或补全。",
        )
        for item in active
        if item.reference_entry.to_verify_items
    ]
    copy_text = "\n".join(
        f"[{index}] {item.display_text}" for index, item in enumerate(entries, start=1)
    )
    return ReferenceDraftPackage(
        session_id=session_id,
        entries=entries,
        copy_text=copy_text,
        verification_items=verification_items,
        boundary_note=_BOUNDARY_NOTE,
    )


def _draft_item(selected: SelectedCitation) -> ReferenceDraftItem:
    reference = selected.reference_entry
    return ReferenceDraftItem(
        selected_citation_id=selected.selected_citation_id,
        source_url=selected.citation.url,
        citation_placeholder=selected.citation_placeholder,
        display_text=reference.display_text,
        classification=reference.classification,
        to_verify_items=list(reference.to_verify_items),
        format_notice=_FORMAT_NOTICE,
    )
