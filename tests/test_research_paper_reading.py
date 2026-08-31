from __future__ import annotations

import io
import json
from datetime import UTC, datetime

import pytest


def test_extract_paper_sections_orders_recognized_chapters_and_marks_missing() -> None:
    from code_navi.research.paper_reading import extract_paper_sections

    sections = extract_paper_sections(
        """
        1 Introduction
        We study graph node classification.
        3 Method
        We define a two-layer graph convolution.
        4 Experiments
        We evaluate on Cora.
        """
    )

    assert [section.key for section in sections] == [
        "introduction",
        "method",
        "experiments",
    ]
    assert sections[0].order == 1
    assert sections[1].title == "方法"
    assert "two-layer graph convolution" in sections[1].text


def test_read_public_arxiv_pdf_extracts_bounded_page_text(monkeypatch: pytest.MonkeyPatch) -> None:
    from code_navi.research import paper_reading

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            self.close()

    class FakePage:
        def __init__(self, text: str) -> None:
            self.text = text

        def extract_text(self) -> str:
            return self.text

    class FakeReader:
        def __init__(self, *_args: object) -> None:
            pass

        pages = [FakePage("Introduction and method"), FakePage("Experiments on Cora")]

    monkeypatch.setattr(paper_reading, "PdfReader", FakeReader)
    monkeypatch.setattr(
        paper_reading,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(b"%PDF-1.7\nbody"),
    )

    result = paper_reading.read_public_paper_pdf(arxiv_id="1609.02907")

    assert result.source_url == "https://arxiv.org/pdf/1609.02907.pdf"
    assert result.page_count == 2
    assert result.pages_read == 2
    assert "Experiments on Cora" in result.text_excerpt


def test_read_public_pdf_rejects_missing_or_private_source() -> None:
    from code_navi.research.paper_reading import PaperTextUnavailableError, read_public_paper_pdf

    with pytest.raises(PaperTextUnavailableError, match="公开 PDF"):
        read_public_paper_pdf()
    with pytest.raises(PaperTextUnavailableError, match="仅支持 arXiv"):
        read_public_paper_pdf(pdf_url="https://example.com/private.pdf")


def test_read_uploaded_pdf_bytes_extracts_bounded_text(monkeypatch: pytest.MonkeyPatch) -> None:
    from code_navi.research import paper_reading

    class FakePage:
        def extract_text(self) -> str:
            return "Locally uploaded paper text"

    class FakeReader:
        def __init__(self, *_args: object) -> None:
            pass

        pages = [FakePage()]

    monkeypatch.setattr(paper_reading, "PdfReader", FakeReader)

    result = paper_reading.read_uploaded_pdf_bytes(b"%PDF-1.7\nbody", filename="paper.pdf")

    assert result.source_url.startswith("local-upload://")
    assert result.page_count == 1
    assert result.pages_read == 1
    assert result.text_excerpt == "Locally uploaded paper text"


def test_paper_analysis_passes_read_text_to_generator_and_marks_scope() -> None:
    from code_navi.research.conversation_difficulty import build_paper_analysis
    from code_navi.research.conversation_schemas import (
        EvidenceReference,
        PaperReadingEvidence,
        PaperReadingSection,
    )
    from code_navi.research.research_artifact_llm import ArtifactLlmOutcome
    from code_navi.research.schemas import AcademicPaperResult, EvidenceStatement

    paper = AcademicPaperResult(
        title="Semi-Supervised Classification with Graph Convolutional Networks",
        authors=["Thomas Kipf", "Max Welling"],
        year=2017,
        source_name="arXiv",
        url="https://arxiv.org/abs/1609.02907",
        arxiv_id="1609.02907",
        abstract_excerpt="Graph convolutional networks for semi-supervised learning.",
        accessed_at=datetime.now(UTC),
        information_scope="metadata_and_abstract_only",
        metadata_evidence=[],
        supporting_snippets=[],
        relevance=EvidenceStatement(content="相关", classification="inference", basis="查询"),
        verification=EvidenceStatement(content="待核验", classification="to_verify", basis="摘要"),
        full_text_available=False,
    )
    reading = PaperReadingEvidence(
        source_url="https://arxiv.org/pdf/1609.02907.pdf",
        page_count=8,
        pages_read=8,
        text_excerpt=(
            "Introduction\nWe study graph learning.\n4 Experiments\n"
            "The model is evaluated on Cora with a fixed train/validation/test split."
        ),
        sections=[
            PaperReadingSection(
                key="introduction", title="引言", order=1, text="We study graph learning."
            ),
            PaperReadingSection(
                key="experiments",
                title="实验",
                order=4,
                text="The model is evaluated on Cora with a fixed train/validation/test split.",
            ),
        ],
    )

    class Generator:
        def __init__(self) -> None:
            self.context: dict[str, object] | None = None

        def generate(self, *, context: dict[str, object], **_: object) -> ArtifactLlmOutcome:
            self.context = context
            return ArtifactLlmOutcome.generated(json.dumps({
                "title": "正文分析",
                "paper_url": paper.url,
                "information_scope": "full_text_user_triggered",
                "abstract_available": True,
                "core_judgment": "正文片段足以支撑实验设置的判断。",
                "items": [{
                    "area": "实验",
                    "content": "正文明确描述了 Cora 评估设置。",
                    "classification": "inference",
                    "basis": "论文正文片段",
                    "source_scope": "full_text_user_triggered",
                    "chapter_key": "experiments",
                    "chapter_order": 4,
                    "relevance": "直接决定复现的评估流程。",
                    "suggested_action": "按正文设置搭建评估脚本。",
                }],
                "summary": "正文已覆盖实验设置；其余章节仍待阅读。",
                "next_action": "继续核对方法章节后生成复现方案。",
                "provenance_note": "模型基于正文片段生成。",
            }, ensure_ascii=False))

    generator = Generator()
    result = build_paper_analysis(
        paper,
        paper_reading=reading,
        evidence_ref=EvidenceReference(
            bundle_id="bundle-1", paper_url=paper.url, title=paper.title,
            source_name="arXiv", year=2017, evidence_level="abstract",
            evidence_summary=paper.abstract_excerpt,
        ),
        research_context={
            "research_question": "GCN 与 MLP 在 Cora 上的可运行性差异",
            "constraints": ["个人电脑", "两周"],
        },
        generator=generator,
        conversation_id="conversation-1",
    )

    assert generator.context is not None
    assert "The model is evaluated on Cora" in generator.context["paper_reading"]["text_excerpt"]
    assert generator.context["research_context"]["research_question"].startswith("GCN")
    assert [section["key"] for section in generator.context["paper_sections"]] == [
        "introduction",
        "experiments",
    ]
    assert result.items[0].chapter_key == "experiments"
    assert result.items[0].chapter_order == 4
    assert result.information_scope == "full_text_user_triggered"
    assert result.paper_reading is not None


def test_paper_analysis_rejects_unknown_chapter_reference() -> None:
    from code_navi.research.conversation_difficulty import build_paper_analysis
    from code_navi.research.conversation_schemas import PaperReadingEvidence, PaperReadingSection
    from code_navi.research.research_artifact_llm import ArtifactLlmOutcome
    from code_navi.research.research_generation import ResearchGenerationError
    from code_navi.research.schemas import AcademicPaperResult, EvidenceStatement

    paper = AcademicPaperResult(
        title="Chapter-bound paper",
        authors=["Example Author"],
        year=2025,
        source_name="arXiv",
        url="https://arxiv.org/abs/2501.00001",
        arxiv_id="2501.00001",
        abstract_excerpt="An abstract.",
        accessed_at=datetime.now(UTC),
        information_scope="metadata_and_abstract_only",
        metadata_evidence=[],
        supporting_snippets=[],
        relevance=EvidenceStatement(content="相关", classification="inference", basis="查询"),
        verification=EvidenceStatement(content="待核验", classification="to_verify", basis="摘要"),
        full_text_available=False,
    )

    class Generator:
        def generate(self, **_: object) -> ArtifactLlmOutcome:
            return ArtifactLlmOutcome.generated(json.dumps({
                "title": "正文分析",
                "paper_url": paper.url,
                "information_scope": "full_text_user_triggered",
                "abstract_available": True,
                "items": [{
                    "area": "实验",
                    "content": "未知章节引用。",
                    "classification": "inference",
                    "basis": "正文片段",
                    "source_scope": "full_text_user_triggered",
                    "chapter_key": "results",
                    "chapter_order": 4,
                }],
                "provenance_note": "模型分析。",
            }))

    with pytest.raises(ResearchGenerationError, match="boundary validation failed"):
        build_paper_analysis(
            paper,
            paper_reading=PaperReadingEvidence(
                source_url="https://arxiv.org/pdf/2501.00001.pdf",
                page_count=2,
                pages_read=2,
                text_excerpt="Introduction\nText",
                sections=[
                    PaperReadingSection(
                        key="introduction", title="引言", order=1, text="Text"
                    )
                ],
            ),
            generator=Generator(),
            conversation_id="conversation-1",
        )


def test_paper_analysis_keeps_valid_chapter_items_when_model_includes_unanchored_item() -> None:
    from code_navi.research.conversation_difficulty import _normalize_paper_chapter_metadata
    from code_navi.research.conversation_schemas import (
        PaperReadingEvidence,
        PaperReadingSection,
        ResearchAnalysisItem,
    )

    reading = PaperReadingEvidence(
        source_url="https://arxiv.org/pdf/2501.00001.pdf",
        page_count=2,
        pages_read=2,
        text_excerpt="Method\nBounded text",
        sections=[
            PaperReadingSection(key="method", title="方法", order=3, text="Bounded text")
        ],
    )
    items = [
        ResearchAnalysisItem(
            area="方法",
            content="方法章节描述了可核对的实现路径。",
            classification="inference",
            basis="方法章节",
            source_scope="full_text_user_triggered",
            chapter_key="method",
            chapter_order=3,
        ),
        ResearchAnalysisItem(
            area="复现建议",
            content="未锚定章节的建议。",
            classification="to_verify",
            basis="模型输出未提供章节。",
            source_scope="full_text_user_triggered",
        ),
    ]

    result = _normalize_paper_chapter_metadata(items, reading)

    assert [item.chapter_key for item in result] == ["method"]


def test_selected_paper_without_arxiv_id_is_resolved_before_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from code_navi.research import conversation_search_service
    from code_navi.research.academic import (
        AcademicSearchTool,
        AcademicSourceResult,
        PaperMetadata,
    )
    from code_navi.research.conversation_search_service import ResearchConversationSearchService
    from code_navi.research.paper_reading import PaperTextEvidence
    from code_navi.research.schemas import AcademicPaperResult, EvidenceStatement

    class Source:
        def __init__(self, result: AcademicSourceResult) -> None:
            self.result = result
            self.calls = 0

        def search(self, _query: str) -> AcademicSourceResult:
            self.calls += 1
            return self.result

    now = datetime.now(UTC)
    title = "A Targeted Graph Paper"
    arxiv_source = Source(AcademicSourceResult.success("arxiv", [PaperMetadata(
        title=title,
        authors=["Ada Author"],
        year=2024,
        source_name="arXiv",
        url="https://arxiv.org/abs/2401.00001",
        identifier="arXiv:2401.00001",
        abstract_excerpt="A graph method.",
        accessed_at=now,
    )]))
    tool = AcademicSearchTool({"arxiv": arxiv_source})
    service = ResearchConversationSearchService(search_tool=tool)
    paper = AcademicPaperResult(
        title=title,
        authors=["Ada Author"],
        year=2024,
        source_name="OpenAlex",
        url="https://openalex.org/W1",
        arxiv_id=None,
        abstract_excerpt="A graph method.",
        accessed_at=now,
        information_scope="metadata_and_abstract_only",
        metadata_evidence=[],
        supporting_snippets=[],
        relevance=EvidenceStatement(content="相关", classification="inference", basis="查询"),
        verification=EvidenceStatement(content="待核验", classification="to_verify", basis="摘要"),
        full_text_available=False,
    )
    monkeypatch.setattr(
        conversation_search_service,
        "read_public_paper_pdf",
        lambda **_: PaperTextEvidence(
            source_url="https://arxiv.org/pdf/2401.00001.pdf",
            page_count=3,
            pages_read=3,
            text_excerpt="Paper body",
        ),
    )

    reading, resolved_id = service._resolve_paper_reading(paper, paper_pdf_url=None)

    assert resolved_id == "arXiv:2401.00001"
    assert reading is not None
    assert reading.source_url.endswith("2401.00001.pdf")
    assert arxiv_source.calls == 1
