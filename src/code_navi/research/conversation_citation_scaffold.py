"""Rules-only citation placeholder and reference-draft construction."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime

from .conversation_schemas import (
    CitationCandidate,
    ConversationEvidenceBundle,
    CreateSelectedCitationRequest,
    ReferenceEntryDraft,
    SelectedCitation,
)
from .schemas import AcademicPaperResult


def build_citation_candidate(
    conversation_id: str,
    bundle: ConversationEvidenceBundle,
    paper: AcademicPaperResult,
) -> CitationCandidate:
    """Copy only already-saved metadata; never query or infer missing fields."""
    doi, arxiv_id = _identifiers(paper.identifier)
    complete = bool(paper.authors and paper.year and paper.source_name and (doi or arxiv_id))
    digest = hashlib.sha256(f"{bundle.bundle_id}|{paper.url}".encode()).hexdigest()[:24]
    return CitationCandidate(
        citation_id=f"citation-{digest}",
        conversation_id=conversation_id,
        evidence_bundle_id=bundle.bundle_id,
        paper_title=paper.title,
        authors=paper.authors,
        year=paper.year,
        source_name=paper.source_name or None,
        url=paper.url,
        doi=doi,
        arxiv_id=arxiv_id,
        abstract_scope=("metadata_and_abstract" if paper.abstract_excerpt else "metadata_only"),
        metadata_completeness="complete" if complete else "partial",
        classification="fact",
        created_at=paper.accessed_at,
    )


def build_selected_citation(
    candidate: CitationCandidate,
    request: CreateSelectedCitationRequest,
    *,
    selected_citation_id: str | None = None,
    created_at: datetime,
) -> SelectedCitation:
    """Return a suggestion only. Text insertion remains a separate user action."""
    selection_id = selected_citation_id or str(uuid.uuid4())
    reference = build_reference_entry(candidate, selection_id)
    return SelectedCitation(
        selected_citation_id=selection_id,
        session_id=candidate.conversation_id,
        citation=candidate,
        target_document=request.target_document,
        target_section=request.target_section,
        paragraph_anchor=request.paragraph_anchor,
        citation_placeholder=_placeholder(candidate),
        user_note=request.user_note,
        reference_entry=reference,
        created_at=created_at,
    )


def build_reference_entry(
    candidate: CitationCandidate, selected_citation_id: str
) -> ReferenceEntryDraft:
    """Produce a readable metadata draft and list every missing core field."""
    missing = _missing_fields(candidate)
    authors = "; ".join(_display_author(author) for author in candidate.authors)
    author_text = authors or "[待核对作者]"
    year_text = str(candidate.year) if candidate.year else "[待核对年份]"
    source_text = candidate.source_name or "[待核对来源]"
    identifier = candidate.doi or candidate.arxiv_id
    suffix = f" {identifier}." if identifier else ""
    display_text = (
        f"{author_text} ({year_text}). {candidate.paper_title}. {source_text}.{suffix}"
        f" {candidate.url}"
    )
    key_stem = _citation_key_stem(candidate.authors) or "pending"
    key_year = str(candidate.year) if candidate.year else "year"
    return ReferenceEntryDraft(
        reference_id=f"reference-{selected_citation_id}",
        selected_citation_id=selected_citation_id,
        display_text=display_text,
        citation_key=f"{key_stem}{key_year}",
        metadata_fields={
            "title": candidate.paper_title,
            "authors": "; ".join(candidate.authors) or None,
            "year": candidate.year,
            "source_name": candidate.source_name,
            "url": candidate.url,
            "doi": candidate.doi,
            "arxiv_id": candidate.arxiv_id,
            "abstract_scope": candidate.abstract_scope,
        },
        classification="fact" if not missing else "to_verify",
        to_verify_items=missing,
    )


def _placeholder(candidate: CitationCandidate) -> str:
    if not candidate.authors or candidate.year is None:
        return f"[引用待核对：{candidate.paper_title}]"
    surname = _surname(candidate.authors[0])
    suffix = " et al." if len(candidate.authors) > 1 else ""
    return f"({surname}{suffix}, {candidate.year})"


def _missing_fields(candidate: CitationCandidate) -> list[str]:
    missing: list[str] = []
    if not candidate.authors:
        missing.append("作者待核对")
    if candidate.year is None:
        missing.append("年份待核对")
    if not candidate.source_name:
        missing.append("来源待核对")
    if not candidate.doi and not candidate.arxiv_id:
        missing.append("DOI 或 arXiv 标识待核对")
    return missing


def _identifiers(identifier: str | None) -> tuple[str | None, str | None]:
    if not identifier:
        return None, None
    cleaned = identifier.strip()
    if cleaned.casefold().startswith("arxiv:"):
        return None, cleaned
    if cleaned.casefold().startswith("doi:"):
        return cleaned[4:].strip() or None, None
    if cleaned.casefold().startswith("10."):
        return cleaned, None
    return None, None


def _display_author(author: str) -> str:
    parts = author.split()
    if len(parts) < 2:
        return author
    return f"{parts[-1]}, {''.join(f'{part[0]}.' for part in parts[:-1])}"


def _surname(author: str) -> str:
    return author.split()[-1] if author.split() else "待核对作者"


def _citation_key_stem(authors: list[str]) -> str:
    if not authors:
        return ""
    return re.sub(r"[^a-z0-9]", "", _surname(authors[0]).casefold())
