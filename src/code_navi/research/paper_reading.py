"""Explicit, bounded reading of a public arXiv PDF for grounded advice."""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    from pypdf import PdfReader
except ModuleNotFoundError:  # pragma: no cover - exercised by deployment diagnostics
    PdfReader = None  # type: ignore[assignment,misc]

MAX_PDF_BYTES = 8 * 1024 * 1024
MAX_PAGES = 40
MAX_TEXT_CHARS = 48_000
MAX_PAGE_CHARS = 4_000


class PaperTextUnavailableError(ValueError):
    """The user did not provide a supported, public paper PDF."""


@dataclass(frozen=True, slots=True)
class PaperSection:
    """A bounded section extracted from user-triggered paper text."""

    key: str
    title: str
    order: int
    text: str


@dataclass(frozen=True, slots=True)
class PaperTextEvidence:
    source_url: str
    page_count: int
    pages_read: int
    text_excerpt: str
    sections: tuple[PaperSection, ...] = ()


_SECTION_DEFINITIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("introduction", "引言", ("introduction", "background", "引言", "绪论", "研究背景")),
    (
        "related_work",
        "相关工作",
        ("related work", "related works", "literature review", "相关工作", "文献综述"),
    ),
    ("method", "方法", ("method", "methodology", "approach", "方法", "模型")),
    ("experiments", "实验", ("experiment", "experiments", "evaluation", "实验", "评估")),
    ("discussion", "讨论", ("discussion", "讨论")),
    ("conclusion", "结论", ("conclusion", "conclusions", "结论")),
)


def read_public_paper_pdf(
    *,
    pdf_url: str | None = None,
    arxiv_id: str | None = None,
    timeout_seconds: float = 15.0,
    max_bytes: int = MAX_PDF_BYTES,
) -> PaperTextEvidence:
    """Read a bounded public arXiv PDF after an explicit user action.

    This deliberately accepts only arXiv PDF hosts. It never reads a local path,
    follows a DOI to an unknown host, or executes anything from the document.
    """
    source_url = _resolve_arxiv_pdf_url(pdf_url=pdf_url, arxiv_id=arxiv_id)
    if PdfReader is None:
        raise PaperTextUnavailableError("当前环境缺少 PDF 解析依赖，请安装 pypdf 后重试。")
    if timeout_seconds <= 0 or max_bytes <= 0:
        raise ValueError("timeout_seconds and max_bytes must be positive")
    request = Request(source_url, headers={"User-Agent": "Code-Navi/1.0"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read(max_bytes + 1)
    except Exception as error:  # urllib errors vary by platform and provider
        raise PaperTextUnavailableError(f"无法读取公开 PDF：{error}") from error
    if len(payload) > max_bytes:
        raise PaperTextUnavailableError("论文 PDF 超过 8 MB 上限，请提供较小的公开版本。")
    if not payload.startswith(b"%PDF"):
        raise PaperTextUnavailableError("公开链接未返回有效 PDF 文件。")
    return _parse_pdf_bytes(payload, source_url=source_url)


def read_uploaded_pdf_bytes(
    payload: bytes,
    *,
    filename: str | None = None,
    max_bytes: int = MAX_PDF_BYTES,
) -> PaperTextEvidence:
    """Parse a PDF uploaded by the user without persisting the original file."""
    if PdfReader is None:
        raise PaperTextUnavailableError("当前环境缺少 PDF 解析依赖，请安装 pypdf 后重试。")
    if not isinstance(payload, bytes) or not payload:
        raise PaperTextUnavailableError("请上传非空 PDF 文件。")
    if max_bytes <= 0 or len(payload) > max_bytes:
        raise PaperTextUnavailableError("上传的 PDF 超过 8 MB 上限。")
    if not payload.startswith(b"%PDF"):
        raise PaperTextUnavailableError("上传文件不是有效 PDF。")
    digest = hashlib.sha256(payload).hexdigest()[:24]
    _ = filename  # The filename is intentionally not persisted or echoed to the model.
    return _parse_pdf_bytes(payload, source_url=f"local-upload://{digest}")


def _parse_pdf_bytes(payload: bytes, *, source_url: str) -> PaperTextEvidence:
    try:
        reader = PdfReader(io.BytesIO(payload))
        pages = list(reader.pages)
        chunks: list[str] = []
        for page in pages[:MAX_PAGES]:
            text = _clean_text(page.extract_text() or "")
            if text:
                chunks.append(text[:MAX_PAGE_CHARS])
        excerpt = "\n\n".join(chunks)[:MAX_TEXT_CHARS]
    except Exception as error:
        raise PaperTextUnavailableError(f"PDF 正文无法解析：{error}") from error
    if not excerpt:
        raise PaperTextUnavailableError("PDF 未提取到可用正文，请提供可复制文本的公开版本。")
    return PaperTextEvidence(
        source_url=source_url,
        page_count=len(pages),
        pages_read=min(len(pages), MAX_PAGES),
        text_excerpt=excerpt,
        sections=tuple(extract_paper_sections(excerpt)),
    )


def extract_paper_sections(text: str) -> list[PaperSection]:
    """Extract common paper chapters without inferring missing content."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    found: dict[str, list[str]] = {}
    titles: dict[str, str] = {}
    current_key: str | None = None
    for line in lines:
        heading = _match_section_heading(line)
        if heading is not None:
            current_key, title, _order = heading
            found.setdefault(current_key, [])
            titles[current_key] = title
            continue
        if current_key is not None:
            found[current_key].append(line)
    sections: list[PaperSection] = []
    for order, (key, title, _aliases) in enumerate(_SECTION_DEFINITIONS, start=1):
        if key in found:
            sections.append(
                PaperSection(
                    key=key,
                    title=titles.get(key, title),
                    order=order,
                    text="\n".join(found[key])[:8_000],
                )
            )
    return sections


def _match_section_heading(line: str) -> tuple[str, str, int] | None:
    normalized = re.sub(r"^\s*(?:\d+(?:\.\d+)*|[IVX]+)[.)]?\s*", "", line, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip(" .:：-—")
    if not normalized or len(normalized) > 100:
        return None
    lowered = normalized.casefold()
    for order, (key, title, aliases) in enumerate(_SECTION_DEFINITIONS, start=1):
        if any(
            lowered == alias.casefold()
            or lowered.startswith(f"{alias.casefold()}:")
            or lowered.startswith(f"{alias.casefold()} ")
            for alias in aliases
        ):
            return key, title, order
    return None


def _resolve_arxiv_pdf_url(*, pdf_url: str | None, arxiv_id: str | None) -> str:
    candidate = (pdf_url or "").strip()
    if not candidate and arxiv_id:
        normalized = re.sub(r"^arxiv:", "", arxiv_id.strip(), flags=re.IGNORECASE)
        normalized = re.sub(r"v\d+$", "", normalized)
        if re.fullmatch(r"[0-9]{4}\.[0-9]{4,5}", normalized):
            candidate = f"https://arxiv.org/pdf/{normalized}.pdf"
    parsed = urlparse(candidate)
    host = parsed.hostname.casefold() if parsed.hostname else ""
    if parsed.scheme != "https" or host not in {"arxiv.org", "export.arxiv.org"}:
        raise PaperTextUnavailableError("请选择 arXiv 的公开 PDF 链接；当前仅支持 arXiv。")
    if not parsed.path.startswith("/pdf/"):
        raise PaperTextUnavailableError("请选择 arXiv 的公开 PDF 链接；当前仅支持 arXiv。")
    return candidate


def _clean_text(value: str) -> str:
    lines = [" ".join(line.replace("\u00ad", "").split()) for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


__all__ = [
    "PaperTextEvidence",
    "PaperSection",
    "PaperTextUnavailableError",
    "extract_paper_sections",
    "read_public_paper_pdf",
    "read_uploaded_pdf_bytes",
]
