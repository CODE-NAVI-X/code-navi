"""Explicit, source-restricted academic metadata search for research sessions."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen
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

ARXIV_SOURCE = "arxiv"
ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_SOURCE_URL = "https://arxiv.org"


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


class AcademicSearchTool:
    """Source allow-list boundary used by the registered academic_search Tool."""

    def __init__(self, source_clients: dict[str, AcademicSourceClient] | None = None) -> None:
        self.source_clients = (
            {ARXIV_SOURCE: ArxivMetadataClient()} if source_clients is None else source_clients
        )

    def search(self, session_id: str, query: str, sources: list[str]) -> dict[str, object]:
        searched_at = datetime.now(UTC)
        source_statuses: list[dict[str, object]] = []
        papers: list[dict[str, object]] = []
        failure_reasons: list[str] = []
        actual_sources: list[str] = []
        for source in sources:
            client = self.source_clients.get(source)
            if client is None:
                reason = f"source is not allowed: {source}"
                source_statuses.append(_status(source, "not_allowed", searched_at, reason))
                failure_reasons.append(reason)
                continue
            try:
                result = client.search(query)
            except ImportError as error:
                result = AcademicSourceResult.failure(
                    source,
                    "dependency_missing",
                    str(error),
                )
            except TimeoutError:
                result = AcademicSourceResult.failure(
                    source,
                    "timeout",
                    f"{source} request timed out",
                    queried=True,
                )
            except Exception:
                result = AcademicSourceResult.failure(
                    source,
                    "unavailable",
                    f"{source} source failed safely",
                    queried=True,
                )
            source_statuses.append(
                _status(result.source, result.status, searched_at, result.reason)
            )
            if result.queried:
                actual_sources.append(result.source)
            if result.reason:
                failure_reasons.append(result.reason)
            for paper in result.papers:
                papers.append(_paper_payload(paper, query))
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
    source: str, status: SourceStatus, searched_at: datetime, reason: str | None
) -> dict[str, object]:
    return {
        "source": source,
        "status": status,
        "source_url": ARXIV_SOURCE_URL if source == ARXIV_SOURCE else None,
        "accessed_at": searched_at.isoformat(),
        "reason": reason,
    }


def _paper_payload(paper: PaperMetadata, query: str) -> dict[str, object]:
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
        "verification": {
            "content": "需要阅读全文并核验实验设置、数据集与结论；本检索未下载正文。",
            "classification": "to_verify",
            "source_url": paper.url,
            "basis": "当前信息范围仅为元数据和摘要",
        },
        "full_text_available": False,
    }


def _text(element: ElementTree.Element, path: str, namespace: dict[str, str]) -> str | None:
    child = element.find(path, namespace)
    return child.text if child is not None else None


def _compact(value: str | None) -> str:
    return " ".join((value or "").split())


def _arxiv_identifier(url: str) -> str | None:
    marker = "/abs/"
    return f"arXiv:{url.split(marker, 1)[1]}" if marker in url else None
