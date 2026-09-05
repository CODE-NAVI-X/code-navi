"""Offline handoff tests from research clarification to academic search."""

from __future__ import annotations

import json
import os
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

os.environ["LEARNING_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import engine  # noqa: E402
from code_navi.learning.models import Base  # noqa: E402
from code_navi.research.academic import (  # noqa: E402
    AcademicSearchTool,
    AcademicSourceResult,
    PaperMetadata,
)
from code_navi.research.conversation_agent import (  # noqa: E402
    ConversationDecisionOutcome,
)
from code_navi.research.conversation_schemas import (  # noqa: E402
    ResearchConversationDecision,
    ResearchProfilePatch,
)
from code_navi.research.research_artifact_llm import ArtifactLlmOutcome  # noqa: E402
from code_navi.research.router import (  # noqa: E402
    _conversation_search_service,
    _conversation_service,
)
from code_navi.research.skill_runtime import load_academic_search_skill  # noqa: E402
from code_navi.server import app  # noqa: E402
from research_llm_fakes import ContextAwareArtifactGenerator  # noqa: E402


class ReadyDecisionGenerator:
    def generate(self, **_kwargs: object) -> ConversationDecisionOutcome:
        decision = ResearchConversationDecision(
            reply="科研画像已准备好，可以先检查检索计划。",
            intent="prepare_search",
            profile_patch=ResearchProfilePatch(
                topic="生成式 AI 辅助编程学习",
                research_questions=["不同提示策略如何影响学习效果？"],
                context="本科编程课程",
                methods=["对照实验"],
                data_requirements="公开数据与课程记录",
            ),
            candidate_questions=["不同提示策略如何影响学习效果？"],
            recommended_action="prepare_search",
        )
        return ConversationDecisionOutcome.generated(
            decision,
            run_id="run-search-ready",
            event_count=2,
        )


class FakeSource:
    def __init__(self) -> None:
        self.calls = 0

    def search(self, query: str) -> AcademicSourceResult:
        self.calls += 1
        return AcademicSourceResult.success(
            "arxiv",
            [
                PaperMetadata(
                    title="Generative AI in Programming Education",
                    authors=["Ada Example"],
                    year=2025,
                    source_name="arXiv",
                    url="https://arxiv.org/abs/2501.00001",
                    identifier="arXiv:2501.00001",
                    abstract_excerpt=f"Evidence for {query}",
                    accessed_at=datetime(2026, 8, 3, tzinfo=UTC),
                )
            ],
        )


class MissingPaperScopeGenerator(ContextAwareArtifactGenerator):
    """Simulate a model omitting the deterministic information-scope field."""

    def generate(
        self,
        *,
        kind: str,
        context: dict[str, object],
        conversation_id: str,
    ) -> ArtifactLlmOutcome:
        outcome = super().generate(
            kind=kind, context=context, conversation_id=conversation_id
        )
        if kind == "paper_analysis" and outcome.text:
            payload = json.loads(outcome.text)
            payload.pop("information_scope", None)
            return ArtifactLlmOutcome.generated(json.dumps(payload, ensure_ascii=False))
        return outcome


@pytest.fixture(autouse=True)
def isolated_services() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    original_generator = _conversation_service.decision_generator
    original_tool = _conversation_search_service.search_tool
    original_artifact = _conversation_search_service.artifact_generator
    _conversation_service.decision_generator = ReadyDecisionGenerator()
    yield
    _conversation_service.decision_generator = original_generator
    _conversation_search_service.search_tool = original_tool
    _conversation_search_service.artifact_generator = original_artifact
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def test_search_plan_uses_profile_fields_without_calling_a_source(
    client: TestClient,
) -> None:
    source = FakeSource()
    _conversation_search_service.search_tool = AcademicSearchTool({"arxiv": source})
    created = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究编程学习中的生成式 AI"},
    ).json()

    response = client.get(
        f"/api/v1/research/conversations/{created['conversation_id']}/search-plan"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "research-search-plan.v1"
    assert body["user_confirmation_required"] is True
    assert "生成式 AI 辅助编程学习" in body["query"]
    assert "本科编程课程" in body["query"]
    assert source.calls == 0


def test_one_complete_rules_request_can_prepare_search_without_network_call(
    client: TestClient,
) -> None:
    source = FakeSource()
    _conversation_search_service.search_tool = AcademicSearchTool({"arxiv": source})
    _conversation_service.decision_generator = type(
        "UnavailableGenerator",
        (),
        {"generate": lambda self, **kwargs: ConversationDecisionOutcome.unavailable()},
    )()
    created = client.post(
        "/api/v1/research/conversations",
        json={
            "initial_message": (
                "我想研究 GCN 在 Cora 节点分类中的表现，候选问题是 GCN 是否优于 GraphSAGE；"
                "采用对照实验，使用 Cora 数据集，指标 Accuracy；只有 RTX 4060 笔记本，"
                "计划两周完成开题报告。"
            )
        },
    ).json()

    response = client.get(
        f"/api/v1/research/conversations/{created['conversation_id']}/search-plan"
    )

    assert response.status_code == 200
    assert response.json()["user_confirmation_required"] is True
    assert source.calls == 0


def test_explicit_conversation_search_dispatches_registered_tool(
    client: TestClient,
) -> None:
    source = FakeSource()
    _conversation_search_service.search_tool = AcademicSearchTool({"arxiv": source})
    created = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究编程学习中的生成式 AI"},
    ).json()

    response = client.post(
        f"/api/v1/research/conversations/{created['conversation_id']}/evidence-bundles",
        json={"sources": ["arxiv"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "academic-evidence.v1"
    assert body["conversation_id"] == created["conversation_id"]
    assert body["papers"][0]["title"] == "Generative AI in Programming Education"
    assert body["tool_audit"]["required_permissions"] == ["NETWORK", "READ"]
    assert source.calls == 1


def test_repeated_search_uses_persistent_cache_and_restores_bundle(
    client: TestClient,
) -> None:
    source = FakeSource()
    _conversation_search_service.search_tool = AcademicSearchTool({"arxiv": source})
    created = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究编程学习中的生成式 AI"},
    ).json()
    url = f"/api/v1/research/conversations/{created['conversation_id']}/evidence-bundles"

    first = client.post(url, json={"query": "AI programming education", "sources": ["arxiv"]})
    second = client.post(url, json={"query": " AI  programming education ", "sources": ["arxiv"]})
    restored = client.get(url)

    assert first.status_code == 200
    assert first.json()["cache_hit"] is False
    assert second.status_code == 200
    assert second.json()["cache_hit"] is True
    assert second.json()["bundle_id"] == first.json()["bundle_id"]
    first_paper = first.json()["papers"][0]
    assert first_paper["paper_id"]
    assert first_paper["arxiv_id"] == "2501.00001"
    assert first_paper["information_scope"] == "metadata_and_abstract_only"
    assert first_paper["metadata_evidence"][0]["classification"] == "fact"
    assert first_paper["relevance"]["classification"] == "inference"
    assert first_paper["verification"]["classification"] == "to_verify"
    assert source.calls == 1
    assert restored.status_code == 200
    assert len(restored.json()) == 1
    assert restored.json()[0]["bundle_id"] == first.json()["bundle_id"]
    assert restored.json()[0]["papers"][0]["paper_id"] == first_paper["paper_id"]
    assert restored.json()[0]["papers"][0]["arxiv_id"] == first_paper["arxiv_id"]


def test_selected_paper_analysis_persists_for_conversation_restore(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from code_navi.research import conversation_search_service
    from code_navi.research.paper_reading import PaperTextEvidence

    monkeypatch.setattr(
        conversation_search_service,
        "read_public_paper_pdf",
        lambda **_: PaperTextEvidence(
            source_url="https://arxiv.org/pdf/2501.00001.pdf",
            page_count=4,
            pages_read=4,
            text_excerpt="A bounded paper excerpt.",
        ),
    )
    _conversation_search_service.search_tool = AcademicSearchTool({"arxiv": FakeSource()})
    _conversation_search_service.artifact_generator = ContextAwareArtifactGenerator()
    conversation_id = client.post(
        "/api/v1/research/conversations", json={"initial_message": "我想研究编程学习中的生成式 AI"}
    ).json()["conversation_id"]
    bundle = client.post(
        f"/api/v1/research/conversations/{conversation_id}/evidence-bundles",
        json={"sources": ["arxiv"]},
    ).json()

    analysis = client.post(
        f"/api/v1/research/conversations/{conversation_id}/paper-analysis",
        json={"paper_url": bundle["papers"][0]["url"]},
    )
    restored = client.get(f"/api/v1/research/conversations/{conversation_id}")

    assert analysis.status_code == 200
    assert restored.status_code == 200
    assert restored.json()["selected_paper"]["bundle_id"] == bundle["bundle_id"]
    assert restored.json()["selected_paper"]["url"] == bundle["papers"][0]["url"]
    assert restored.json()["paper_analysis"]["generation_mode"] == "llm"


def test_uploaded_pdf_is_forwarded_to_paper_analysis(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from code_navi.research import conversation_search_service
    from code_navi.research.paper_reading import PaperTextEvidence

    monkeypatch.setattr(
        conversation_search_service,
        "read_uploaded_pdf_bytes",
        lambda *_args, **_kwargs: PaperTextEvidence(
            source_url="local-upload://test-digest",
            page_count=2,
            pages_read=2,
            text_excerpt="Uploaded paper body.",
        ),
    )
    _conversation_search_service.search_tool = AcademicSearchTool({"arxiv": FakeSource()})
    _conversation_search_service.artifact_generator = ContextAwareArtifactGenerator()
    conversation_id = client.post(
        "/api/v1/research/conversations", json={"initial_message": "我想研究编程学习中的生成式 AI"}
    ).json()["conversation_id"]
    bundle = client.post(
        f"/api/v1/research/conversations/{conversation_id}/evidence-bundles",
        json={"sources": ["arxiv"]},
    ).json()

    response = client.post(
        f"/api/v1/research/conversations/{conversation_id}/paper-analysis/upload",
        params={"paper_url": bundle["papers"][0]["url"]},
        content=b"%PDF-1.7\nplaceholder",
        headers={"Content-Type": "application/pdf", "X-Filename": "paper.pdf"},
    )

    assert response.status_code == 200
    assert response.json()["paper_reading"]["source_url"] == "local-upload://test-digest"
    assert response.json()["information_scope"] == "full_text_user_triggered"


def test_uploaded_pdf_analysis_accepts_model_omitting_derived_scope(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from code_navi.research import conversation_search_service
    from code_navi.research.paper_reading import PaperTextEvidence

    monkeypatch.setattr(
        conversation_search_service,
        "read_uploaded_pdf_bytes",
        lambda *_args, **_kwargs: PaperTextEvidence(
            source_url="local-upload://missing-scope",
            page_count=1,
            pages_read=1,
            text_excerpt="Uploaded paper body.",
        ),
    )
    _conversation_search_service.search_tool = AcademicSearchTool({"arxiv": FakeSource()})
    _conversation_search_service.artifact_generator = MissingPaperScopeGenerator()
    conversation_id = client.post(
        "/api/v1/research/conversations", json={"initial_message": "我想研究图神经网络"}
    ).json()["conversation_id"]
    bundle = client.post(
        f"/api/v1/research/conversations/{conversation_id}/evidence-bundles",
        json={"sources": ["arxiv"]},
    ).json()

    response = client.post(
        f"/api/v1/research/conversations/{conversation_id}/paper-analysis/upload",
        params={"paper_url": bundle["papers"][0]["url"]},
        content=b"%PDF-1.7\nplaceholder",
        headers={"Content-Type": "application/pdf", "X-Filename": "paper.pdf"},
    )

    assert response.status_code == 200
    assert response.json()["information_scope"] == "full_text_user_triggered"


def test_selected_evidence_is_saved_as_a_traceable_learning_research_note(
    client: TestClient,
) -> None:
    source = FakeSource()
    _conversation_search_service.search_tool = AcademicSearchTool({"arxiv": source})
    created = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究编程学习中的生成式 AI"},
    ).json()
    conversation_id = created["conversation_id"]
    bundle = client.post(
        f"/api/v1/research/conversations/{conversation_id}/evidence-bundles",
        json={"sources": ["arxiv"]},
    ).json()
    paper = bundle["papers"][0]
    save_url = (
        f"/api/v1/research/conversations/{conversation_id}/evidence-bundles/"
        f"{bundle['bundle_id']}/notebook-notes"
    )

    first = client.post(
        save_url,
        json={
            "learning_session_id": "sess-research-notebook",
            "selected_paper_urls": [paper["url"]],
        },
    )
    repeated = client.post(
        save_url,
        json={
            "learning_session_id": "sess-research-notebook",
            "selected_paper_urls": [paper["url"]],
        },
    )
    notebook = client.get(
        "/api/v1/learning/notebook",
        params={"session_id": "sess-research-notebook"},
    )

    assert first.status_code == 200
    assert repeated.status_code == 200
    assert repeated.json()["notebook_item_id"] == first.json()["notebook_item_id"]
    assert first.json()["conversation_id"] == conversation_id
    assert first.json()["bundle_id"] == bundle["bundle_id"]
    assert first.json()["evidence_refs"][0] == {
        "bundle_id": bundle["bundle_id"],
        "paper_url": paper["url"],
        "title": paper["title"],
        "source_name": "arXiv",
        "year": 2025,
        "evidence_level": "abstract",
        "evidence_summary": paper["abstract_excerpt"],
    }
    assert notebook.status_code == 200
    assert len(notebook.json()) == 1
    note = notebook.json()[0]
    assert note["kind"] == "research_note"
    assert note["research_note"]["conversation_id"] == conversation_id
    assert note["research_note"]["bundle_id"] == bundle["bundle_id"]
    assert note["source_url"] == paper["url"]


def test_research_note_rejects_evidence_outside_the_selected_bundle(
    client: TestClient,
) -> None:
    _conversation_search_service.search_tool = AcademicSearchTool({"arxiv": FakeSource()})
    created = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究编程学习中的生成式 AI"},
    ).json()
    conversation_id = created["conversation_id"]
    bundle = client.post(
        f"/api/v1/research/conversations/{conversation_id}/evidence-bundles",
        json={"sources": ["arxiv"]},
    ).json()

    response = client.post(
        f"/api/v1/research/conversations/{conversation_id}/evidence-bundles/"
        f"{bundle['bundle_id']}/notebook-notes",
        json={
            "learning_session_id": "sess-research-notebook",
            "selected_paper_urls": ["https://example.invalid/not-in-bundle"],
        },
    )

    assert response.status_code == 404
    assert client.get(
        "/api/v1/learning/notebook",
        params={"session_id": "sess-research-notebook"},
    ).json() == []


def test_sparse_conversation_cannot_start_network_search(client: TestClient) -> None:
    _conversation_service.decision_generator = type(
        "UnavailableGenerator",
        (),
        {"generate": lambda self, **kwargs: ConversationDecisionOutcome.unavailable()},
    )()
    created = client.post("/api/v1/research/conversations", json={}).json()

    response = client.post(
        f"/api/v1/research/conversations/{created['conversation_id']}/evidence-bundles",
        json={"sources": ["arxiv"]},
    )

    assert response.status_code == 409


def test_user_confirmed_query_searches_without_ready_profile(client: TestClient) -> None:
    """画像未就绪时，用户已确认的检索词仍直接驱动正式检索（设计文档 §检索）。"""
    source = FakeSource()
    _conversation_search_service.search_tool = AcademicSearchTool({"arxiv": source})
    _conversation_service.decision_generator = type(
        "UnavailableGenerator",
        (),
        {"generate": lambda self, **kwargs: ConversationDecisionOutcome.unavailable()},
    )()
    created = client.post("/api/v1/research/conversations", json={}).json()

    response = client.post(
        f"/api/v1/research/conversations/{created['conversation_id']}/evidence-bundles",
        json={"query": "GCN oversmoothing node classification", "sources": ["arxiv"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["papers"][0]["title"] == "Generative AI in Programming Education"
    assert source.calls == 1


def test_academic_search_skill_contract_is_packaged() -> None:
    skill = load_academic_search_skill()

    assert "explicit user confirmation" in skill
    assert "metadata_and_abstract_only" in skill
    assert "Do not fall back to a browser or unrestricted web search" in skill
