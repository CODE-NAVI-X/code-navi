"""Optional web-material retrieval for quiz generation.

Uses the Tavily search API (the same provider the OpenMAIC frontend already
configures) to pull reference material the LLM can adapt into original
questions.  The search is *read-only* against a whitelisted vendor API and is
only invoked when the client explicitly opts into ``source_mode="web"``.

When no ``TAVILY_API_KEY`` is set — or the request fails — ``search()`` returns
an empty list and the generator degrades to pure LLM generation instead of
pretending a source exists (see the module's fact-boundary rule).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


@dataclass(frozen=True)
class WebResult:
    """One retrieved snippet; the LLM adapts, never copies it verbatim."""

    title: str
    url: str
    snippet: str


def _format_material(results: list[WebResult]) -> str:
    """Render retrieved results as a compact block the prompt can cite."""
    lines: list[str] = []
    for i, result in enumerate(results, start=1):
        lines.append(
            f"{i}. 《{result.title}》\n   来源：{result.url}\n   摘要：{result.snippet[:600]}"
        )
    return "\n\n".join(lines)


class WebSearchClient:
    """Tavily-backed search client that is inert without an API key."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout_seconds: float = 8.0,
        max_results: int = 4,
    ) -> None:
        self.api_key = (api_key or os.getenv("TAVILY_API_KEY", "")).strip()
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results

    @property
    def available(self) -> bool:
        """True when a key is configured, so callers can pre-check."""
        return bool(self.api_key)

    def search(self, query: str) -> list[WebResult]:
        """Return retrieved results, or an empty list on missing key/failure."""
        if not self.available:
            logger.info("TAVILY_API_KEY not configured; skipping web search.")
            return []
        payload = {
            "query": query,
            "max_results": self.max_results,
            "search_depth": "basic",
        }
        try:
            request = Request(
                TAVILY_SEARCH_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
            )
            with urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, OSError, ValueError) as exc:  # noqa: BLE001
            logger.warning("Tavily search failed (%s); using pure generation.", exc)
            return []

        results: list[WebResult] = []
        for item in (data.get("results") or [])[: self.max_results]:
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("content") or "").strip()
            if title or url:
                results.append(WebResult(title=title, url=url, snippet=snippet))
        return results
