"""TDD for evidence-bound paper understanding checks (Fake Provider only)."""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

os.environ["LEARNING_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import engine  # noqa: E402
from code_navi.learning.models import Base  # noqa: E402
from code_navi.research.conversation_agent import (  # noqa: E402
    ConversationDecisionOutcome,
    ResearchConversationDecision,
)
from code_navi.research.conversation_schemas import (  # noqa: E402
    ConversationEvidenceBundle,
    ResearchProfilePatch,
)
from code_navi.research.conversation_understanding import (  # noqa: E402
    section_key_for_area,
)
from code_navi.research.models import ResearchEvidenceBundleModel  # noqa: E402
from code_navi.research.research_artifact_llm import ArtifactLlmOutcome  # noqa: E402
from code_navi.research.router import _conversation_service  # noqa: E402
from code_navi.research.schemas import AcademicPaperResult, EvidenceStatement  # noqa: E402
from code_navi.server import app  # noqa: E402
from research_llm_fakes import ContextAwareArtifactGenerator  # noqa: E402

NOW = datetime(2026, 8, 28, tzinfo=UTC)
GCN_URL = "https://arxiv.org/abs/1609.02907"


class ReadyDecisionGenerator:
    def generate(self, **_: object) -> ConversationDecisionOutcome:
        return ConversationDecisionOutcome.generated(
            ResearchConversationDecision(
                reply="研究画像已整理。",
                intent="clarify",
                profile_patch=ResearchProfilePatch(topic="图卷积网络节点分类复现"),
                candidate_questions=["GCN 在 Cora 上如何工作？"],
                recommended_action="review_profile",
            ),
            run_id="test-ready",
            event_count=1,
        )


class StaticArtifactGenerator:
    def __init__(self, outcome: ArtifactLlmOutcome) -> None:
        self.outcome = outcome

    def generate(self, **_: object) -> ArtifactLlmOutcome:
        return self.outcome


@pytest.fixture(autouse=True)
def fresh_tables() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def restore_generators() -> Generator[None, None, None]:
    decision = _conversation_service.decision_generator
    artifact = _conversation_service.artifact_generator
    yield
    _conversation_service.decision_generator = decision
    _conversation_service.artifact_generator = artifact


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def _gcn_paper(*, abstract: bool = True) -> AcademicPaperResult:
    return AcademicPaperResult(
        title="Semi-Supervised Classification with Graph Convolutional Networks",
        authors=["Thomas N. Kipf", "Max Welling"],
        year=2017,
        source_name="arXiv",
        url=GCN_URL,
        identifier="arXiv:1609.02907",
        arxiv_id="1609.02907",
        doi="10.48550/arXiv.1609.02907",
        abstract_excerpt=(
            "We introduce a scalable approach for semi-supervised classification on"
            " graph-structured data via localized first-order approximations."
        )
        if abstract
        else None,
        accessed_at=NOW,
        information_scope="metadata_and_abstract_only",
        metadata_evidence=[
            EvidenceStatement(
                content="标题与作者来自 arXiv 元数据。",
                classification="fact",
                source_url=GCN_URL,
                basis="arXiv 元数据",
            )
        ],
        supporting_snippets=[],
        relevance=EvidenceStatement(
            content="与图卷积节点分类相关。",
            classification="inference",
            source_url=GCN_URL,
            basis="标题与摘要匹配",
        ),
        verification=EvidenceStatement(
            content="需阅读全文核验实验设置与 Accuracy。",
            classification="to_verify",
            source_url=GCN_URL,
            basis="当前只有摘要",
        ),
        full_text_available=False,
    )


def _save_bundle(conversation_id: str, paper: AcademicPaperResult) -> str:
    bundle = ConversationEvidenceBundle(
        bundle_id="bundle-gcn",
        conversation_id=conversation_id,
        query="graph convolutional networks",
        requested_sources=["arxiv"],
        allowed_sources=["arxiv"],
        queried_sources=["arxiv"],
        source_statuses=[],
        searched_at=NOW,
        papers=[paper],
        source_links=[paper.url],
        failure_reasons=[],
        provenance_note="仅元数据与摘要。",
    )
    with Session(engine) as db:
        db.add(
            ResearchEvidenceBundleModel(
                conversation_id=conversation_id,
                bundle_data=bundle.model_dump(mode="json"),
            )
        )
        db.commit()
    return bundle.bundle_id


def _ready_conversation(client: TestClient) -> str:
    _conversation_service.decision_generator = ReadyDecisionGenerator()
    response = client.post(
        "/api/v1/research/conversations", json={"initial_message": "我研究 GCN"}
    )
    assert response.status_code == 201
    return response.json()["conversation_id"]


def _question_payload(bundle_id: str, section_key: str = "research_question") -> dict:
    return {"paper_url": GCN_URL, "bundle_id": bundle_id, "section_key": section_key}


def _assess_payload(check_id: str, bundle_id: str, answer: str) -> dict:
    return {
        "check_id": check_id,
        "paper_url": GCN_URL,
        "bundle_id": bundle_id,
        "section_key": "research_question",
        "answer": answer,
    }



def test_section_key_mapping_is_deterministic() -> None:
    assert section_key_for_area("研究问题") == "research_question"
    assert section_key_for_area("核心方法") == "core_method"
    assert section_key_for_area("数据集与预处理") == "dataset"
    assert section_key_for_area("待核验内容") == "to_verify"
    assert section_key_for_area("未知章节") == "other"


def test_understanding_question_uses_abstract_scope_and_persists(client: TestClient) -> None:
    _conversation_service.artifact_generator = ContextAwareArtifactGenerator()
    conv = _ready_conversation(client)
    bundle_id = _save_bundle(conv, _gcn_paper(abstract=True))

    res = client.post(
        f"/api/v1/research/conversations/{conv}/understanding-checks/question",
        json=_question_payload(bundle_id),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "question_ready"
    assert body["source_scope"] == "metadata_and_abstract_only"
    assert body["generation_mode"] == "llm"
    assert "GCN" in body["question"] or "Cora" in body["question"]
    assert body["paper_url"] == GCN_URL
    assert body["bundle_id"] == bundle_id

    restored = client.get(
        f"/api/v1/research/conversations/{conv}/understanding-checks",
        params={"paper_url": GCN_URL},
    )
    assert restored.status_code == 200
    checks = restored.json()
    assert len(checks) == 1
    assert checks[0]["question"] == body["question"]


def test_metadata_only_paper_question_uses_metadata_scope(client: TestClient) -> None:
    _conversation_service.artifact_generator = ContextAwareArtifactGenerator()
    conv = _ready_conversation(client)
    bundle_id = _save_bundle(conv, _gcn_paper(abstract=False))

    res = client.post(
        f"/api/v1/research/conversations/{conv}/understanding-checks/question",
        json=_question_payload(bundle_id),
    )
    assert res.status_code == 200, res.text
    assert res.json()["source_scope"] == "metadata_only"


def test_assess_understood_answer_persists_and_restores(client: TestClient) -> None:
    _conversation_service.artifact_generator = ContextAwareArtifactGenerator()
    conv = _ready_conversation(client)
    bundle_id = _save_bundle(conv, _gcn_paper())
    question = client.post(
        f"/api/v1/research/conversations/{conv}/understanding-checks/question",
        json=_question_payload(bundle_id),
    ).json()
    assess = client.post(
        f"/api/v1/research/conversations/{conv}/understanding-checks/assess",
        json=_assess_payload(
            question["check_id"], bundle_id, "GCN 用半监督节点分类在 Cora 上传播标签。"
        ),
    )
    assert assess.status_code == 200, assess.text
    body = assess.json()
    assert body["status"] == "understood"
    assert body["answer"] == "GCN 用半监督节点分类在 Cora 上传播标签。"
    assert body["correct_points"]
    assert body["assessment"]
    restored = client.get(
        f"/api/v1/research/conversations/{conv}/understanding-checks",
        params={"paper_url": GCN_URL},
    ).json()
    assert restored[0]["status"] == "understood"
    assert restored[0]["assessment"] == body["assessment"]


def test_assess_failure_preserves_answer_and_last_success(client: TestClient) -> None:
    _conversation_service.artifact_generator = ContextAwareArtifactGenerator()
    conv = _ready_conversation(client)
    bundle_id = _save_bundle(conv, _gcn_paper())
    question = client.post(
        f"/api/v1/research/conversations/{conv}/understanding-checks/question",
        json=_question_payload(bundle_id),
    ).json()
    good = client.post(
        f"/api/v1/research/conversations/{conv}/understanding-checks/assess",
        json=_assess_payload(question["check_id"], bundle_id, "半监督节点分类"),
    ).json()
    assert good["status"] == "understood"
    _conversation_service.artifact_generator = StaticArtifactGenerator(
        ArtifactLlmOutcome.unavailable()
    )
    failed = client.post(
        f"/api/v1/research/conversations/{conv}/understanding-checks/assess",
        json=_assess_payload(question["check_id"], bundle_id, "我又改了答案但模型失败"),
    )
    assert failed.status_code == 503
    restored = client.get(
        f"/api/v1/research/conversations/{conv}/understanding-checks",
        params={"paper_url": GCN_URL},
    ).json()[0]
    assert restored["status"] == "generation_failed"
    assert restored["answer"] == "我又改了答案但模型失败"
    assert restored["assessment"] == good["assessment"]
    assert restored["correct_points"] == good["correct_points"]


def test_assess_without_question_returns_409(client: TestClient) -> None:
    _conversation_service.artifact_generator = ContextAwareArtifactGenerator()
    conv = _ready_conversation(client)
    bundle_id = _save_bundle(conv, _gcn_paper())
    res = client.post(
        f"/api/v1/research/conversations/{conv}/understanding-checks/assess",
        json=_assess_payload("missing-check", bundle_id, "anything"),
    )
    assert res.status_code == 409


def test_assess_rejects_mismatched_check_id_without_overwriting_answer(
    client: TestClient,
) -> None:
    _conversation_service.artifact_generator = ContextAwareArtifactGenerator()
    conv = _ready_conversation(client)
    bundle_id = _save_bundle(conv, _gcn_paper())
    question = client.post(
        f"/api/v1/research/conversations/{conv}/understanding-checks/question",
        json=_question_payload(bundle_id),
    ).json()
    first = client.post(
        f"/api/v1/research/conversations/{conv}/understanding-checks/assess",
        json=_assess_payload(question["check_id"], bundle_id, "半监督节点分类"),
    )
    assert first.status_code == 200, first.text

    mismatched = client.post(
        f"/api/v1/research/conversations/{conv}/understanding-checks/assess",
        json=_assess_payload("different-check-id", bundle_id, "不应写入的答案"),
    )
    assert mismatched.status_code == 409
    restored = client.get(
        f"/api/v1/research/conversations/{conv}/understanding-checks",
        params={"paper_url": GCN_URL},
    ).json()[0]
    assert restored["check_id"] == question["check_id"]
    assert restored["answer"] == "半监督节点分类"
    assert restored["status"] == "understood"


def test_question_rejects_unknown_section_key(client: TestClient) -> None:
    _conversation_service.artifact_generator = ContextAwareArtifactGenerator()
    conv = _ready_conversation(client)
    bundle_id = _save_bundle(conv, _gcn_paper())
    res = client.post(
        f"/api/v1/research/conversations/{conv}/understanding-checks/question",
        json=_question_payload(bundle_id, "invented_section"),
    )
    assert res.status_code == 422


def test_paper_not_in_saved_bundle_returns_404(client: TestClient) -> None:
    _conversation_service.artifact_generator = ContextAwareArtifactGenerator()
    conv = _ready_conversation(client)
    _save_bundle(conv, _gcn_paper())
    res = client.post(
        f"/api/v1/research/conversations/{conv}/understanding-checks/question",
        json={
            "paper_url": "https://other.test/paper",
            "bundle_id": "bundle-gcn",
            "section_key": "research_question",
        },
    )
    assert res.status_code == 404


def test_question_prompt_carries_section_and_source_boundary(client: TestClient) -> None:
    gen = ContextAwareArtifactGenerator()
    _conversation_service.artifact_generator = gen
    conv = _ready_conversation(client)
    bundle_id = _save_bundle(conv, _gcn_paper())
    client.post(
        f"/api/v1/research/conversations/{conv}/understanding-checks/question",
        json=_question_payload(bundle_id, "core_method"),
    )
    ctx = gen.contexts[0]
    assert ctx["section_key"] == "core_method"
    assert ctx["source_scope"] == "metadata_and_abstract_only"
    assert "source_boundary" in ctx
    assert "required_json_shape" in ctx
    assert ctx["paper"]["url"] == GCN_URL


def _register_login(email: str) -> tuple[TestClient, dict[str, str]]:
    test_client = TestClient(app)
    test_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "displayName": "Test"},
    )
    res = test_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert res.status_code == 200, res.text
    return test_client, {"X-CSRF-Token": res.json()["csrfToken"]}


def test_understanding_check_cross_user_isolation() -> None:
    """Bob cannot access Alice's understanding checks through the real auth path."""
    _conversation_service.artifact_generator = ContextAwareArtifactGenerator()
    client_a, headers_a = _register_login("alice_und@example.com")
    _conversation_service.decision_generator = ReadyDecisionGenerator()
    create = client_a.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我研究 GCN"},
        headers=headers_a,
    )
    assert create.status_code == 201, create.text
    conv = create.json()["conversation_id"]
    _save_bundle(conv, _gcn_paper())

    alice_res = client_a.post(
        f"/api/v1/research/conversations/{conv}/understanding-checks/question",
        json=_question_payload("bundle-gcn"),
        headers=headers_a,
    )
    assert alice_res.status_code == 200, alice_res.text

    client_b, headers_b = _register_login("bob_und@example.com")
    bob_res = client_b.post(
        f"/api/v1/research/conversations/{conv}/understanding-checks/question",
        json=_question_payload("bundle-gcn"),
        headers=headers_b,
    )
    assert bob_res.status_code == 404

    bob_list = client_b.get(
        f"/api/v1/research/conversations/{conv}/understanding-checks",
        params={"paper_url": GCN_URL},
        headers=headers_b,
    )
    assert bob_list.status_code == 404
