"""Explicit, source-restricted academic metadata search for research sessions."""

from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

SourceStatus = Literal[
    "success",
    "no_results",
    "network_error",
    "timeout",
    "unavailable",
    "disabled",
    "not_allowed",
    "dependency_missing",
]
PaperKind = Literal["original_paper", "review", "downstream_application"]

ARXIV_SOURCE = "arxiv"
ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_SOURCE_URL = "https://arxiv.org"
OPENALEX_SOURCE = "openalex"
OPENALEX_API_URL = "https://api.openalex.org/works"
OPENALEX_SOURCE_URL = "https://openalex.org"
CROSSREF_SOURCE = "crossref"
CROSSREF_API_URL = "https://api.crossref.org/works"
CROSSREF_SOURCE_URL = "https://www.crossref.org"
SOURCE_URLS = {
    ARXIV_SOURCE: ARXIV_SOURCE_URL,
    OPENALEX_SOURCE: OPENALEX_SOURCE_URL,
    CROSSREF_SOURCE: CROSSREF_SOURCE_URL,
}


@dataclass(frozen=True)
class PaperMetadata:
    """Only metadata and abstract text returned by an allowed source."""

    title: str
    authors: list[str]
    year: int | None
    source_name: str
    url: str
    identifier: str | None
    abstract_excerpt: str | None
    accessed_at: datetime


@dataclass(frozen=True)
class AcademicSourceResult:
    """A source result that never fabricates papers when a request fails."""

    source: str
    status: SourceStatus
    papers: list[PaperMetadata]
    reason: str | None = None
    queried: bool = False

    @classmethod
    def success(cls, source: str, papers: list[PaperMetadata]) -> AcademicSourceResult:
        return cls(source, "success" if papers else "no_results", papers, queried=True)

    @classmethod
    def failure(
        cls, source: str, status: SourceStatus, reason: str, *, queried: bool = False
    ) -> AcademicSourceResult:
        return cls(source, status, [], reason, queried)


class AcademicSourceClient(Protocol):
    def search(self, query: str) -> AcademicSourceResult: ...


class ArxivMetadataClient:
    """Small stdlib-only arXiv Atom API client; no paper PDF download is performed."""

    def __init__(self, timeout_seconds: float = 8.0, max_results: int = 5) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results

    def search(self, query: str) -> AcademicSourceResult:
        if os.getenv("CODE_NAVI_ACADEMIC_ARXIV_ENABLED", "true").lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }:
            return AcademicSourceResult.failure(
                ARXIV_SOURCE, "disabled", "arXiv source is disabled"
            )
        parameters = urlencode(
            {"search_query": f"all:{query}", "start": 0, "max_results": self.max_results}
        )
        try:
            with urlopen(f"{ARXIV_API_URL}?{parameters}", timeout=self.timeout_seconds) as response:
                payload = response.read()
        except TimeoutError:
            return AcademicSourceResult.failure(
                ARXIV_SOURCE, "timeout", "arXiv request timed out", queried=True
            )
        except URLError as error:
            return AcademicSourceResult.failure(
                ARXIV_SOURCE, "network_error", f"arXiv unavailable: {error.reason}", queried=True
            )
        except OSError as error:
            return AcademicSourceResult.failure(
                ARXIV_SOURCE, "network_error", f"arXiv unavailable: {error}", queried=True
            )
        try:
            feed = ElementTree.fromstring(payload)
        except ElementTree.ParseError:
            return AcademicSourceResult.failure(
                ARXIV_SOURCE, "unavailable", "arXiv returned invalid XML", queried=True
            )
        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        accessed_at = datetime.now(UTC)
        papers: list[PaperMetadata] = []
        for entry in feed.findall("atom:entry", namespace):
            identifier = _text(entry, "atom:id", namespace)
            title = _compact(_text(entry, "atom:title", namespace))
            if not title or not identifier:
                continue
            published = _text(entry, "atom:published", namespace)
            year = int(published[:4]) if published and published[:4].isdigit() else None
            papers.append(
                PaperMetadata(
                    title=title,
                    authors=[
                        name
                        for author in entry.findall("atom:author", namespace)
                        if (name := _text(author, "atom:name", namespace))
                    ],
                    year=year,
                    source_name="arXiv",
                    url=identifier,
                    identifier=_arxiv_identifier(identifier),
                    abstract_excerpt=_compact(_text(entry, "atom:summary", namespace))[:800]
                    or None,
                    accessed_at=accessed_at,
                )
            )
        return AcademicSourceResult.success(ARXIV_SOURCE, papers)


class OpenAlexMetadataClient:
    """OpenAlex works search restricted to public metadata and reconstructed abstracts."""

    def __init__(self, timeout_seconds: float = 6.0, max_results: int = 5) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results

    def search(self, query: str) -> AcademicSourceResult:
        if not _source_enabled("OPENALEX", default=True):
            return AcademicSourceResult.failure(
                OPENALEX_SOURCE, "disabled", "OpenAlex source is disabled"
            )
        parameters = urlencode({"search": query, "per-page": self.max_results})
        try:
            payload = _request_json(
                f"{OPENALEX_API_URL}?{parameters}",
                timeout_seconds=self.timeout_seconds,
                attempts=2,
            )
        except TimeoutError:
            return AcademicSourceResult.failure(
                OPENALEX_SOURCE, "timeout", "OpenAlex request timed out", queried=True
            )
        except (HTTPError, URLError, OSError, ValueError) as error:
            return AcademicSourceResult.failure(
                OPENALEX_SOURCE,
                "network_error",
                f"OpenAlex unavailable: {_safe_error(error)}",
                queried=True,
            )
        papers = []
        accessed_at = datetime.now(UTC)
        for item in payload.get("results", []):
            if not isinstance(item, dict):
                continue
            title = _compact(str(item.get("display_name") or item.get("title") or ""))
            url = str(item.get("id") or "")
            if not title or not url:
                continue
            authorships = item.get("authorships") or []
            authors = [
                str(author.get("author", {}).get("display_name"))
                for author in authorships
                if isinstance(author, dict)
                and isinstance(author.get("author"), dict)
                and author["author"].get("display_name")
            ]
            papers.append(
                PaperMetadata(
                    title=title,
                    authors=authors,
                    year=item.get("publication_year")
                    if isinstance(item.get("publication_year"), int)
                    else None,
                    source_name="OpenAlex",
                    url=url,
                    identifier=str(item.get("doi") or url),
                    abstract_excerpt=_openalex_abstract(item.get("abstract_inverted_index")),
                    accessed_at=accessed_at,
                )
            )
        return AcademicSourceResult.success(OPENALEX_SOURCE, papers)


class CrossrefMetadataClient:
    """Crossref works search restricted to DOI metadata and provider abstracts."""

    def __init__(self, timeout_seconds: float = 6.0, max_results: int = 5) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results

    def search(self, query: str) -> AcademicSourceResult:
        if not _source_enabled("CROSSREF", default=True):
            return AcademicSourceResult.failure(
                CROSSREF_SOURCE, "disabled", "Crossref source is disabled"
            )
        parameters = urlencode({"query.bibliographic": query, "rows": self.max_results})
        try:
            payload = _request_json(
                f"{CROSSREF_API_URL}?{parameters}",
                timeout_seconds=self.timeout_seconds,
                attempts=2,
            )
        except TimeoutError:
            return AcademicSourceResult.failure(
                CROSSREF_SOURCE, "timeout", "Crossref request timed out", queried=True
            )
        except (HTTPError, URLError, OSError, ValueError) as error:
            return AcademicSourceResult.failure(
                CROSSREF_SOURCE,
                "network_error",
                f"Crossref unavailable: {_safe_error(error)}",
                queried=True,
            )
        message = payload.get("message")
        items = message.get("items", []) if isinstance(message, dict) else []
        papers = []
        accessed_at = datetime.now(UTC)
        for item in items:
            if not isinstance(item, dict):
                continue
            titles = item.get("title") or []
            title = _compact(str(titles[0])) if titles else ""
            doi = str(item.get("DOI") or "")
            url = str(item.get("URL") or (f"https://doi.org/{doi}" if doi else ""))
            if not title or not url:
                continue
            authors = [
                " ".join(
                    value
                    for value in (str(author.get("given") or ""), str(author.get("family") or ""))
                    if value
                )
                for author in item.get("author") or []
                if isinstance(author, dict)
            ]
            papers.append(
                PaperMetadata(
                    title=title,
                    authors=[author for author in authors if author],
                    year=_crossref_year(item),
                    source_name="Crossref",
                    url=url,
                    identifier=f"doi:{doi}" if doi else None,
                    abstract_excerpt=_strip_markup(item.get("abstract")),
                    accessed_at=accessed_at,
                )
            )
        return AcademicSourceResult.success(CROSSREF_SOURCE, papers)


class AcademicSearchTool:
    """Source allow-list boundary used by the registered academic_search Tool."""

    def __init__(self, source_clients: dict[str, AcademicSourceClient] | None = None) -> None:
        self.source_clients = (
            {
                OPENALEX_SOURCE: OpenAlexMetadataClient(),
                CROSSREF_SOURCE: CrossrefMetadataClient(),
                ARXIV_SOURCE: ArxivMetadataClient(),
            }
            if source_clients is None
            else source_clients
        )

    def search(self, session_id: str, query: str, sources: list[str]) -> dict[str, object]:
        searched_at = datetime.now(UTC)
        source_statuses: list[dict[str, object]] = []
        candidate_papers: list[PaperMetadata] = []
        failure_reasons: list[str] = []
        actual_sources: list[str] = []
        pending: list[tuple[str, AcademicSourceClient]] = []
        results: dict[str, AcademicSourceResult] = {}
        durations: dict[str, int] = {}
        for source in dict.fromkeys(sources):
            client = self.source_clients.get(source)
            if client is None:
                reason = f"source is not allowed: {source}"
                source_statuses.append(_status(source, "not_allowed", searched_at, reason))
                failure_reasons.append(reason)
                continue
            pending.append((source, client))
        with ThreadPoolExecutor(max_workers=max(1, len(pending))) as executor:
            started = time.perf_counter()
            future_sources = {
                executor.submit(client.search, query): source for source, client in pending
            }
            for future in as_completed(future_sources):
                source = future_sources[future]
                durations[source] = max(0, round((time.perf_counter() - started) * 1000))
                try:
                    results[source] = future.result()
                except ImportError as error:
                    results[source] = AcademicSourceResult.failure(
                        source, "dependency_missing", str(error)
                    )
                except TimeoutError:
                    results[source] = AcademicSourceResult.failure(
                        source, "timeout", f"{source} request timed out", queried=True
                    )
                except Exception:
                    results[source] = AcademicSourceResult.failure(
                        source, "unavailable", f"{source} source failed safely", queried=True
                    )
        for source in dict.fromkeys(sources):
            result = results.get(source)
            if result is None:
                continue
            source_statuses.append(
                _status(
                    result.source,
                    result.status,
                    searched_at,
                    result.reason,
                    duration_ms=durations.get(source, 0),
                )
            )
            if result.queried:
                actual_sources.append(result.source)
            if result.reason:
                failure_reasons.append(result.reason)
            candidate_papers.extend(result.papers)
        papers = [
            _paper_payload(paper, query, doi=doi, arxiv_id=arxiv_id)
            for paper, doi, arxiv_id in _deduplicate_and_rank(candidate_papers, query)
        ]
        return {
            "session_id": session_id,
            "query": query,
            "allowed_sources": list(self.source_clients),
            "queried_sources": actual_sources,
            "source_statuses": source_statuses,
            "searched_at": searched_at.isoformat(),
            "papers": papers,
            "source_links": [item["source_url"] for item in source_statuses],
            "failure_reasons": failure_reasons,
            "provenance_note": (
                "结果仅来自用户显式选择且代码允许的学术来源；未执行全网搜索、正文下载或论文精读。"
            ),
        }


def _status(
    source: str,
    status: SourceStatus,
    searched_at: datetime,
    reason: str | None,
    *,
    duration_ms: int = 0,
) -> dict[str, object]:
    return {
        "source": source,
        "status": status,
        "source_url": SOURCE_URLS.get(source),
        "accessed_at": searched_at.isoformat(),
        "reason": reason,
        "duration_ms": duration_ms,
    }


def _paper_payload(
    paper: PaperMetadata,
    query: str,
    *,
    doi: str | None,
    arxiv_id: str | None,
) -> dict[str, object]:
    metadata_fact = {
        "content": "标题、作者、年份、链接和摘要片段直接来自该来源返回的元数据。",
        "classification": "fact",
        "source_url": paper.url,
        "basis": paper.source_name,
    }
    return {
        "title": paper.title,
        "authors": paper.authors,
        "year": paper.year,
        "source_name": paper.source_name,
        "url": paper.url,
        "identifier": paper.identifier,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "abstract_excerpt": paper.abstract_excerpt,
        "accessed_at": paper.accessed_at.isoformat(),
        "information_scope": "metadata_and_abstract_only",
        "metadata_evidence": [metadata_fact],
        "supporting_snippets": [
            {
                "content": paper.abstract_excerpt or "该来源未提供摘要。",
                "classification": "fact",
                "source_url": paper.url,
                "basis": "来源返回的摘要片段" if paper.abstract_excerpt else "来源元数据",
            }
        ],
        "relevance": {
            "content": f"该条目的标题或摘要与检索词“{query}”可能相关，需人工核验。",
            "classification": "inference",
            "source_url": paper.url,
            "basis": "关键词与元数据/摘要的匹配",
        },
        "paper_kind": {
            "content": _paper_kind(paper),
            "classification": "inference",
            "source_url": paper.url,
            "basis": "标题和摘要中的论文类型线索；未读取全文，需人工核验。",
        },
        "verification": {
            "content": "需要阅读全文并核验实验设置、数据集与结论；本检索未下载正文。",
            "classification": "to_verify",
            "source_url": paper.url,
            "basis": "当前信息范围仅为元数据和摘要",
        },
        "full_text_available": False,
    }


def _deduplicate_and_rank(
    papers: list[PaperMetadata], query: str
) -> list[tuple[PaperMetadata, str | None, str | None]]:
    groups: list[list[PaperMetadata]] = []
    for paper in papers:
        group = next((item for item in groups if _same_paper(item[0], paper)), None)
        if group is None:
            groups.append([paper])
        else:
            group.append(paper)
    merged = [
        (
            max(group, key=_paper_quality),
            next((doi for paper in group if (doi := _normalized_doi(paper))), None),
            next((arxiv for paper in group if (arxiv := _normalized_arxiv_id(paper))), None),
        )
        for group in groups
    ]
    return sorted(merged, key=lambda item: _ranking_key(item[0], query))


def _same_paper(left: PaperMetadata, right: PaperMetadata) -> bool:
    left_doi = _normalized_doi(left)
    right_doi = _normalized_doi(right)
    if left_doi and right_doi and left_doi == right_doi:
        return True
    if _normalized_title(left.title) == _normalized_title(right.title):
        return True
    left_arxiv = _normalized_arxiv_id(left)
    right_arxiv = _normalized_arxiv_id(right)
    if left_arxiv and right_arxiv and left_arxiv == right_arxiv:
        return True
    return (
        left.source_name != right.source_name
        and _title_overlap(left.title, right.title) >= 0.85
        and bool(set(_author_tokens(left)) & set(_author_tokens(right)))
    )


def _paper_quality(paper: PaperMetadata) -> tuple[int, int, int, int, str]:
    return (
        int(bool(paper.abstract_excerpt)),
        int(bool(_normalized_doi(paper))),
        len(paper.authors),
        int(paper.year is not None),
        paper.url.casefold(),
    )


def _ranking_key(paper: PaperMetadata, query: str) -> tuple[int, int, int, int, int, str, str]:
    query_tokens = _tokens(query)
    title_tokens = _tokens(paper.title)
    author_tokens = set(_author_tokens(paper))
    kind_score = {"original_paper": 3, "review": 2, "downstream_application": 1}[
        _paper_kind(paper)
    ]
    title_matches = len(query_tokens & title_tokens)
    author_matches = len(query_tokens & author_tokens)
    keyword_coverage = len(query_tokens & _tokens(f"{paper.title} {paper.abstract_excerpt or ''}"))
    year_score = int(paper.year is not None and 1800 <= paper.year <= 2100)
    return (
        -kind_score,
        -title_matches,
        -author_matches,
        -keyword_coverage,
        -year_score,
        _normalized_title(paper.title),
        paper.url.casefold(),
    )


def _paper_kind(paper: PaperMetadata) -> PaperKind:
    text = f"{paper.title} {paper.abstract_excerpt or ''}".casefold()
    if any(marker in text for marker in ("survey", "review", "综述", "overview")):
        return "review"
    if any(marker in text for marker in ("application", "applying", "applied", "应用")):
        return "downstream_application"
    return "original_paper"


def _normalized_doi(paper: PaperMetadata) -> str | None:
    for value in (paper.identifier, paper.url):
        if not value:
            continue
        match = re.search(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", value.casefold())
        if match:
            return match.group(0).rstrip(".,;)")
    return None


def _normalized_arxiv_id(paper: PaperMetadata) -> str | None:
    for value in (paper.identifier, paper.url):
        if not value:
            continue
        match = re.search(r"(?:arxiv[:./]|abs/)(\d{4}\.\d{4,5})(?:v\d+)?", value.casefold())
        if match:
            return match.group(1)
    return None


def _normalized_title(title: str) -> str:
    return " ".join(sorted(_tokens(title)))


def _title_overlap(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _author_tokens(paper: PaperMetadata) -> list[str]:
    return [token for author in paper.authors for token in _tokens(author)]


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))


def _text(element: ElementTree.Element, path: str, namespace: dict[str, str]) -> str | None:
    child = element.find(path, namespace)
    return child.text if child is not None else None


def _compact(value: str | None) -> str:
    return " ".join((value or "").split())


def _arxiv_identifier(url: str) -> str | None:
    marker = "/abs/"
    return f"arXiv:{url.split(marker, 1)[1]}" if marker in url else None


def _source_enabled(name: str, *, default: bool) -> bool:
    value = os.getenv(f"CODE_NAVI_ACADEMIC_{name}_ENABLED", str(default))
    return value.lower() in {"1", "true", "yes", "on"}


def _request_json(
    url: str,
    *,
    timeout_seconds: float,
    attempts: int,
) -> dict[str, object]:
    """Read JSON with a bounded retry policy; urllib honors HTTP(S)_PROXY."""
    last_error: Exception | None = None
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "Code-Navi/0.1"})
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read())
            if not isinstance(payload, dict):
                raise ValueError("source returned a non-object JSON payload")
            return payload
        except HTTPError as error:
            last_error = error
            if error.code not in {429, 500, 502, 503, 504} or attempt + 1 >= attempts:
                raise
        except (TimeoutError, URLError, OSError) as error:
            last_error = error
            if attempt + 1 >= attempts:
                raise
        time.sleep(0.2 * (attempt + 1))
    raise RuntimeError("source retry policy ended without a result") from last_error


def _openalex_abstract(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    positioned: list[tuple[int, str]] = []
    for word, positions in value.items():
        if isinstance(word, str) and isinstance(positions, list):
            positioned.extend(
                (position, word) for position in positions if isinstance(position, int)
            )
    text = " ".join(word for _, word in sorted(positioned))
    return text[:800] or None


def _crossref_year(item: dict[str, object]) -> int | None:
    for field in ("published-print", "published-online", "issued", "created"):
        value = item.get(field)
        if not isinstance(value, dict):
            continue
        parts = value.get("date-parts")
        if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
            year = parts[0][0]
            if isinstance(year, int):
                return year
    return None


def _strip_markup(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return _compact(re.sub(r"<[^>]+>", " ", value))[:800] or None


def _safe_error(error: Exception) -> str:
    if isinstance(error, HTTPError):
        return f"HTTP {error.code}"
    if isinstance(error, URLError):
        return str(error.reason)
    return error.__class__.__name__
