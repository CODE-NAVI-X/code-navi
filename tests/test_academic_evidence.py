"""Offline tests for explicit, source-restricted academic evidence search."""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import Base, engine  # noqa: E402
from code_navi.research.academic import (  # noqa: E402
    AcademicSearchTool,
    AcademicSourceResult,
    ArxivMetadataClient,
    PaperMetadata,
)
from code_navi.research.router import _evidence_service  # noqa: E402
from code_navi.research_tools import academic_search_spec, register_research_tools  # noqa: E402
from code_navi.server import app  # noqa: E402
from kernel.core import (  # noqa: E402
    PermissionGrant,
    ToolCall,
    ToolExecutionContext,
    ToolPermission,
    ToolRegistry,
)


class FakeArxivSource:
    def __init__(self, result: AcademicSourceResult) -> None:
        self.result = result
        self.calls = 0

    def search(self, query: str) -> AcademicSourceResult:
        self.calls += 1
        assert query
        return self.result


def test_academic_tool_resolves_selected_paper_to_matching_arxiv_copy() -> None:
    source = FakeArxivSource(
        AcademicSourceResult.success(
            "arxiv",
            [
                PaperMetadata(
                    title="A Study of Feedback Systems",
                    authors=["Ada Lovelace", "Grace Hopper"],
                    year=2025,
                    source_name="arXiv",
                    url="https://arxiv.org/abs/2501.00001",
                    identifier="arXiv:2501.00001",
                    abstract_excerpt="A matching abstract.",
                    accessed_at=datetime(2026, 7, 30, tzinfo=UTC),
                ),
                PaperMetadata(
                    title="Unrelated Feedback Systems",
                    authors=["Other Author"],
                    year=2020,
                    source_name="arXiv",
                    url="https://arxiv.org/abs/2001.00001",
                    identifier="arXiv:2001.00001",
                    abstract_excerpt="An unrelated paper.",
                    accessed_at=datetime(2026, 7, 30, tzinfo=UTC),
                ),
            ],
        )
    )
    tool = AcademicSearchTool({"arxiv": source})

    resolved = tool.resolve_arxiv_paper(
        title="A Study of Feedback Systems",
        authors=["Ada Lovelace", "Grace Hopper"],
        year=2025,
    )

    assert resolved is not None
    assert resolved.identifier == "arXiv:2501.00001"
    assert source.calls == 1


@pytest.fixture(autouse=True)
def fresh_tables() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def restore_evidence_service() -> Generator[None, None, None]:
    original = _evidence_service.search_tool
    yield
    _evidence_service.search_tool = original


def _paper() -> PaperMetadata:
    return PaperMetadata(
        title="A Study of Feedback Systems",
        authors=["Ada Lovelace", "Grace Hopper"],
        year=2025,
        source_name="arXiv",
        url="https://arxiv.org/abs/2501.00001",
        identifier="arXiv:2501.00001",
        abstract_excerpt="We compare feedback systems in a controlled learning study.",
        accessed_at=datetime(2026, 7, 30, tzinfo=UTC),
    )


def _completed_session(client: TestClient) -> str:
    created = client.post("/api/v1/research/sessions", json={}).json()
    body = created
    while not body["completed"]:
        body = client.post(
            f"/api/v1/research/sessions/{created['session_id']}/turns",
            json={"selected_option": body["next_question"]["options"][0]},
        ).json()
    return created["session_id"]


def test_academic_search_tool_requires_read_and_network_permissions() -> None:
    spec = academic_search_spec()

    assert spec.required_permissions == frozenset({ToolPermission.READ, ToolPermission.NETWORK})


def test_registry_denies_academic_search_without_network_permission() -> None:
    source = FakeArxivSource(AcademicSourceResult.success("arxiv", [_paper()]))
    registry = ToolRegistry()
    register_research_tools(registry, AcademicSearchTool({"arxiv": source}))
    dispatcher = registry.bind(
        PermissionGrant("research"),
        ToolExecutionContext("research"),
    )

    result = dispatcher.dispatch(
        ToolCall("1", "academic_search", {"query": "feedback systems", "sources": ["arxiv"]})
    )

    assert result.result["ok"] is False
    assert result.result["error"]["code"] == "permission_denied"
    assert source.calls == 0


def test_academic_search_returns_source_restricted_evidence_bundle() -> None:
    source = FakeArxivSource(AcademicSourceResult.success("arxiv", [_paper()]))
    tool = AcademicSearchTool({"arxiv": source})

    bundle = tool.search("session-1", "feedback systems", ["arxiv"])

    assert bundle["session_id"] == "session-1"
    assert bundle["allowed_sources"] == ["arxiv"]
    assert bundle["source_statuses"][0]["status"] == "success"
    assert bundle["papers"][0]["title"] == "A Study of Feedback Systems"
    assert bundle["papers"][0]["metadata_evidence"][0]["classification"] == "fact"
    assert bundle["papers"][0]["relevance"]["classification"] == "inference"
    assert bundle["papers"][0]["full_text_available"] is False
    assert source.calls == 1


def test_academic_search_prioritizes_and_deduplicates_original_gcn_paper() -> None:
    accessed_at = datetime(2026, 8, 28, tzinfo=UTC)
    original_title = "Semi-Supervised Classification with Graph Convolutional Networks"
    sources = {
        "arxiv": FakeArxivSource(
            AcademicSourceResult.success(
                "arxiv",
                [
                    PaperMetadata(
                        title=original_title,
                        authors=["Thomas N. Kipf", "Max Welling"],
                        year=2016,
                        source_name="arXiv",
                        url="https://arxiv.org/abs/1609.02907",
                        identifier="arXiv:1609.02907",
                        abstract_excerpt=(
                            "We present graph convolutional networks for "
                            "semi-supervised classification."
                        ),
                        accessed_at=accessed_at,
                    ),
                    PaperMetadata(
                        title="A Survey of Graph Convolutional Networks",
                        authors=["Survey Author"],
                        year=2021,
                        source_name="arXiv",
                        url="https://arxiv.org/abs/2101.00001",
                        identifier="arXiv:2101.00001",
                        abstract_excerpt="This survey reviews graph convolutional network methods.",
                        accessed_at=accessed_at,
                    ),
                ],
            )
        ),
        "crossref": FakeArxivSource(
            AcademicSourceResult.success(
                "crossref",
                [
                    PaperMetadata(
                        title=original_title,
                        authors=["Thomas N. Kipf", "Max Welling"],
                        year=2017,
                        source_name="Crossref",
                        url="https://doi.org/10.48550/arXiv.1609.02907",
                        identifier="doi:10.48550/arXiv.1609.02907",
                        abstract_excerpt=None,
                        accessed_at=accessed_at,
                    ),
                    PaperMetadata(
                        title="Applying GCNs to Cora Citation Prediction",
                        authors=["Application Author"],
                        year=2024,
                        source_name="Crossref",
                        url="https://doi.org/10.1000/gcn-cora-application",
                        identifier="doi:10.1000/gcn-cora-application",
                        abstract_excerpt="We apply GCNs to a downstream Cora prediction task.",
                        accessed_at=accessed_at,
                    ),
                ],
            )
        ),
    }

    bundle = AcademicSearchTool(sources).search(
        "session-gcn",
        "GCN Cora Kipf Welling semi-supervised classification",
        ["arxiv", "crossref"],
    )

    original_papers = [item for item in bundle["papers"] if item["title"] == original_title]
    assert len(original_papers) == 1
    assert bundle["papers"].index(original_papers[0]) < 3
    assert original_papers[0]["paper_kind"] == {
        "content": "original_paper",
        "classification": "inference",
        "source_url": original_papers[0]["url"],
        "basis": "标题和摘要中的论文类型线索；未读取全文，需人工核验。",
    }
    assert original_papers[0]["verification"]["classification"] == "to_verify"
    assert len(bundle["papers"]) == 3


@pytest.mark.parametrize(
    "status",
    ["network_error", "timeout", "unavailable", "disabled", "dependency_missing", "no_results"],
)
def test_source_failure_returns_safe_empty_bundle(status: str) -> None:
    source = FakeArxivSource(AcademicSourceResult.failure("arxiv", status, "source unavailable"))

    bundle = AcademicSearchTool({"arxiv": source}).search("session-1", "feedback", ["arxiv"])

    assert bundle["papers"] == []
    assert bundle["source_statuses"][0]["status"] == status
    assert bundle["failure_reasons"] == ["source unavailable"]
    if status == "disabled":
        assert bundle["queried_sources"] == []


def test_unallowed_source_is_never_called() -> None:
    source = FakeArxivSource(AcademicSourceResult.success("arxiv", [_paper()]))

    bundle = AcademicSearchTool({"arxiv": source}).search("session-1", "feedback", ["crossref"])

    assert bundle["papers"] == []
    assert bundle["source_statuses"][0]["status"] == "not_allowed"
    assert source.calls == 0


def test_partial_source_failure_keeps_successful_papers() -> None:
    successful = FakeArxivSource(AcademicSourceResult.success("arxiv", [_paper()]))
    unavailable = FakeArxivSource(
        AcademicSourceResult.failure(
            "openalex", "network_error", "OpenAlex unavailable", queried=True
        )
    )

    bundle = AcademicSearchTool(
        {"arxiv": successful, "openalex": unavailable}
    ).search("session-1", "feedback", ["openalex", "arxiv"])

    assert [item["status"] for item in bundle["source_statuses"]] == [
        "network_error",
        "success",
    ]
    assert bundle["papers"][0]["title"] == "A Study of Feedback Systems"
    assert bundle["queried_sources"] == ["openalex", "arxiv"]
    assert successful.calls == 1
    assert unavailable.calls == 1


def test_academic_search_spec_exposes_only_the_three_allowed_sources() -> None:
    source_schema = academic_search_spec().args_schema["properties"]["sources"]

    assert source_schema["maxItems"] == 3
    assert source_schema["items"]["enum"] == ["openalex", "crossref", "arxiv"]


def test_configured_disabled_arxiv_source_makes_no_network_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE_NAVI_ACADEMIC_ARXIV_ENABLED", "false")

    result = ArxivMetadataClient().search("feedback")

    assert result.status == "disabled"
    assert result.papers == []
    assert result.queried is False


def test_unexpected_source_error_becomes_safe_empty_bundle() -> None:
    class BrokenSource:
        def search(self, _query: str) -> AcademicSourceResult:
            raise ImportError("optional source dependency missing")

    bundle = AcademicSearchTool({"arxiv": BrokenSource()}).search(
        "session-1", "feedback", ["arxiv"]
    )

    assert bundle["papers"] == []
    assert bundle["source_statuses"][0]["status"] == "dependency_missing"
    assert bundle["failure_reasons"] == ["optional source dependency missing"]


def test_api_only_searches_after_explicit_completed_session_request(
    client: TestClient,
) -> None:
    source = FakeArxivSource(AcademicSourceResult.success("arxiv", [_paper()]))
    _evidence_service.search_tool = AcademicSearchTool({"arxiv": source})
    session_id = _completed_session(client)

    assert source.calls == 0
    response = client.post(
        f"/api/v1/research/sessions/{session_id}/evidence-bundles",
        json={"query": "feedback systems", "sources": ["arxiv"]},
    )

    assert response.status_code == 200
    assert response.json()["papers"][0]["information_scope"] == "metadata_and_abstract_only"
    assert response.json()["tool_audit"]["required_permissions"] == ["NETWORK", "READ"]
    assert source.calls == 1


def test_api_rejects_unallowed_source_without_calling_a_client(client: TestClient) -> None:
    source = FakeArxivSource(AcademicSourceResult.success("arxiv", [_paper()]))
    _evidence_service.search_tool = AcademicSearchTool({"arxiv": source})
    session_id = _completed_session(client)

    response = client.post(
        f"/api/v1/research/sessions/{session_id}/evidence-bundles",
        json={"query": "feedback systems", "sources": ["semantic_scholar"]},
    )

    assert response.status_code == 422
    assert source.calls == 0


def test_api_rejects_search_for_incomplete_session(client: TestClient) -> None:
    session_id = client.post("/api/v1/research/sessions", json={}).json()["session_id"]

    response = client.post(
        f"/api/v1/research/sessions/{session_id}/evidence-bundles",
        json={"query": "feedback systems", "sources": ["arxiv"]},
    )

    assert response.status_code == 409
