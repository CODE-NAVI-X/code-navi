"""Contract tests for pure-rule research guidance endpoints (contract §2.1/§2.2)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

os.environ["LEARNING_DATABASE_URL"] = "sqlite:///:memory:"
os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.auth.rate_limiter import get_rate_limiter  # noqa: E402
from code_navi.db import Base, SessionLocal, engine  # noqa: E402
from code_navi.research.models import (  # noqa: E402
    ResearchConversationModel,
    ResearchEvidenceBundleModel,
    ResearchReproductionPipelineModel,
)
from code_navi.server import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_tables() -> Generator[None, None, None]:
    """Keep guidance tests isolated in the shared in-memory engine."""
    get_rate_limiter().reset()
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    get_rate_limiter().reset()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def _add_conversation(**overrides: object) -> ResearchConversationModel:
    fields: dict[str, object] = {
        "id": str(uuid.uuid4()),
        "profile_data": {},
        "messages_data": [],
    }
    fields.update(overrides)
    conversation = ResearchConversationModel(**fields)  # type: ignore[arg-type]
    db = SessionLocal()
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    db.close()
    return conversation


def _add_bundle(conversation_id: str, papers: list[dict[str, object]]) -> str:
    bundle = ResearchEvidenceBundleModel(
        conversation_id=conversation_id,
        bundle_data={"papers": papers},
    )
    db = SessionLocal()
    db.add(bundle)
    db.commit()
    db.refresh(bundle)
    db.close()
    return bundle.id


def _add_pipeline(
    conversation_id: str, tasks: list[dict[str, str]], created_at: datetime
) -> None:
    db = SessionLocal()
    db.add(
        ResearchReproductionPipelineModel(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            pipeline_data={"tasks": tasks},
            created_at=created_at,
        )
    )
    db.commit()
    db.close()


def _provenance(mastery: dict[str, list[str]] | None = None) -> dict[str, object]:
    provenance: dict[str, object] = {
        "schema_version": "context-provenance.v1",
        "transfer_id": str(uuid.uuid4()),
        "source_module": "learning",
        "source_object": {"type": "notebook_item", "id": str(uuid.uuid4())},
        "source_scope_id": "scope-1",
        "target_module": "research",
        "topic": "图神经网络入门",
        "summary": "已学习图神经网络基础概念，希望迁移到科研项目中。",
        "selected_content": [
            {"kind": "summary", "label": "学习总结", "content": "图神经网络基础概念总结。"}
        ],
        "confirmed_at": datetime.now(UTC).isoformat(),
    }
    if mastery is not None:
        provenance["learning_mastery_snapshot"] = mastery
    return provenance


def test_stage_briefing_returns_404_for_missing_conversation(client: TestClient) -> None:
    response = client.get("/api/v1/research/conversations/does-not-exist/stage-briefing")
    assert response.status_code == 404


def test_stage_briefing_empty_state_is_200_without_learning_context(client: TestClient) -> None:
    conversation = _add_conversation()
    response = client.get(f"/api/v1/research/conversations/{conversation.id}/stage-briefing")
    assert response.status_code == 200
    payload = response.json()
    assert payload["conversation_id"] == conversation.id
    assert payload["has_learning_context"] is False
    assert payload["stage_summary"] == {
        "topic": None,
        "digest": None,
        "knowledge_points": None,
    }
    assert payload["reproduction_entry"] == {"bundle_count": 0, "pipeline_status": None}
    assert payload["evidence_trends"] == []
    assert payload["generated_by"] == "rules"


def test_stage_briefing_projects_confirmed_learning_context(client: TestClient) -> None:
    long_summary = " 学习背景摘要。" * 200  # 1400 chars before whitespace-normalized truncation
    conversation = _add_conversation(
        context_provenance=_provenance(mastery={"strong": ["transformer"], "weak": ["pytest"]})
        | {"summary": long_summary}
    )
    response = client.get(f"/api/v1/research/conversations/{conversation.id}/stage-briefing")
    assert response.status_code == 200
    payload = response.json()
    assert payload["has_learning_context"] is True
    assert payload["stage_summary"]["topic"] == "图神经网络入门"
    digest = payload["stage_summary"]["digest"]
    assert digest is not None and len(digest) <= 1000 and digest.endswith("…")
    points = payload["stage_summary"]["knowledge_points"]
    assert [point["name"] for point in points] == ["transformer", "pytest"]
    assert all(point["mastery"] is None for point in points)


def test_stage_briefing_evidence_trends_only_reference_saved_evidence(
    client: TestClient,
) -> None:
    conversation = _add_conversation()
    bundle_a = _add_bundle(
        conversation.id,
        [
            {
                "url": "https://example.org/a",
                "title": "Transformers for Sequence Transduction: Attention Is All You Need",
                "source_name": "arXiv",
                "year": 2017,
            },
            {
                "url": "https://example.org/b",
                "title": "BERT: Pre-training of Deep Bidirectional Transformers",
                "source_name": "arXiv",
                "year": 2019,
                "abstract_excerpt": "Transformers for language understanding.",
            },
        ],
    )
    bundle_b = _add_bundle(
        conversation.id,
        [
            {
                "url": "https://example.org/c",
                "title": "Vision Transformers for Image Recognition",
                "source_name": "arXiv",
                "year": 2021,
            }
        ],
    )
    other_conversation = _add_conversation()
    _add_bundle(
        other_conversation.id,
        [
            {
                "url": "https://example.org/x",
                "title": "Unrelated Paper Title",
                "source_name": "arXiv",
            }
        ],
    )

    response = client.get(
        f"/api/v1/research/conversations/{conversation.id}/stage-briefing",
        params={"include_evidence_trends": True},
    )
    assert response.status_code == 200
    trends = response.json()["evidence_trends"]
    assert [trend["keyword"] for trend in trends] == ["transformers", "attention", "bert"]
    assert trends[0]["paper_count"] == 3
    assert {ref["bundle_id"] for ref in trends[0]["evidence_refs"]} == {bundle_a, bundle_b}
    refs_by_url = {ref["paper_url"]: ref for ref in trends[0]["evidence_refs"]}
    assert refs_by_url["https://example.org/b"]["evidence_level"] == "abstract"
    assert refs_by_url["https://example.org/a"]["evidence_level"] == "metadata"

    plain = client.get(f"/api/v1/research/conversations/{conversation.id}/stage-briefing")
    assert plain.json()["evidence_trends"] == []


def test_stage_briefing_pipeline_status_from_latest_pipeline_tasks(
    client: TestClient,
) -> None:
    conversation = _add_conversation()
    now = datetime.now(UTC)
    _add_pipeline(conversation.id, [{"status": "not_started"}], now - timedelta(minutes=5))
    _add_pipeline(conversation.id, [{"status": "evidence_linked"}], now)
    response = client.get(f"/api/v1/research/conversations/{conversation.id}/stage-briefing")
    assert response.json()["reproduction_entry"]["pipeline_status"] == "evidence_linked"

    other = _add_conversation()
    _add_pipeline(other.id, [{"status": "not_started"}], now)
    response = client.get(f"/api/v1/research/conversations/{other.id}/stage-briefing")
    assert response.json()["reproduction_entry"]["pipeline_status"] == "not_started"


def test_study_recommendations_require_explicit_confirmation(client: TestClient) -> None:
    conversation = _add_conversation()
    missing = client.post(
        f"/api/v1/research/conversations/{conversation.id}/study-recommendations", json={}
    )
    assert missing.status_code == 409
    declined = client.post(
        f"/api/v1/research/conversations/{conversation.id}/study-recommendations",
        json={"user_confirmed": False},
    )
    assert declined.status_code == 409


def test_study_recommendations_return_404_for_missing_conversation(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/research/conversations/does-not-exist/study-recommendations",
        json={"user_confirmed": True},
    )
    assert response.status_code == 404


def _ready_profile_data() -> dict[str, object]:
    return {
        "topic": "图神经网络在分子性质预测中的应用",
        "research_questions": ["GNN 如何用于分子性质预测"],
        "context": "分子性质预测任务",
        "motivation": "课程项目延伸",
        "methods": ["PyTorch", "Graph Neural Networks"],
        "data_requirements": "需要公开的分子图数据集；标准评测脚本",
        "expected_output": "可复现的基线对比",
    }


def test_study_recommendations_extract_from_profile_and_plan(client: TestClient) -> None:
    conversation = _add_conversation(profile_data=_ready_profile_data())
    response = client.post(
        f"/api/v1/research/conversations/{conversation.id}/study-recommendations",
        json={"user_confirmed": True},
    )
    assert response.status_code == 200
    payload = response.json()
    points = [item["knowledge_point"] for item in payload["recommendations"]]
    assert len(points) <= 6
    assert "PyTorch" in points and "Graph Neural Networks" in points
    assert "标准评测脚本" in points
    assert all(item["mastery_status"] == "unknown" for item in payload["recommendations"])
    assert all(
        item["action"]
        == {
            "type": "learning_explain",
            "payload": {"knowledge_point": item["knowledge_point"]},
        }
        for item in payload["recommendations"]
    )
    assert any(item["reason"].startswith("来自研究计划") for item in payload["recommendations"])
    assert "未调用模型" in payload["provenance_note"]


def test_study_recommendations_map_mastery_and_jump_actions(client: TestClient) -> None:
    conversation = _add_conversation(
        profile_data=_ready_profile_data(),
        context_provenance=_provenance(
            mastery={"strong": ["PyTorch"], "weak": ["标准评测脚本"]}
        ),
    )
    response = client.post(
        f"/api/v1/research/conversations/{conversation.id}/study-recommendations",
        json={"user_confirmed": True},
    )
    assert response.status_code == 200
    by_point = {item["knowledge_point"]: item for item in response.json()["recommendations"]}
    assert by_point["PyTorch"]["mastery_status"] == "mastered"
    assert by_point["PyTorch"]["action"] == {
        "type": "practice_set",
        "payload": {"kind": "code_practice", "topic": "PyTorch", "count": 5},
    }
    assert by_point["标准评测脚本"]["mastery_status"] == "weak"
    assert by_point["标准评测脚本"]["action"]["type"] == "learning_explain"


def test_study_recommendations_cap_at_six_deduplicated_points(client: TestClient) -> None:
    profile = _ready_profile_data()
    profile["methods"] = ["方法一", "方法二", "方法三", "方法四", "方法五", "方法六", "方法七"]
    conversation = _add_conversation(profile_data=profile)
    response = client.post(
        f"/api/v1/research/conversations/{conversation.id}/study-recommendations",
        json={"user_confirmed": True},
    )
    points = [item["knowledge_point"] for item in response.json()["recommendations"]]
    assert len(points) == 6
    assert len(set(points)) == len(points)


def _create_user_and_login(client: TestClient, email: str) -> dict[str, str]:
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "displayName": "Guidance Test"},
    )
    res = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert res.status_code == 200, res.text
    return {"X-CSRF-Token": res.json()["csrfToken"]}


def test_guidance_endpoints_isolate_across_principals(client: TestClient) -> None:
    client_a = TestClient(app)
    client_b = TestClient(app)
    headers_a = _create_user_and_login(client_a, "alice_guidance@example.com")
    headers_b = _create_user_and_login(client_b, "bob_guidance@example.com")
    created = client_a.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究图神经网络的分子性质预测"},
        headers=headers_a,
    )
    assert created.status_code == 201, created.text
    conversation_id = created.json()["conversation_id"]

    assert (
        client_b.get(
            f"/api/v1/research/conversations/{conversation_id}/stage-briefing",
            headers=headers_b,
        ).status_code
        == 404
    )
    assert (
        client_b.post(
            f"/api/v1/research/conversations/{conversation_id}/study-recommendations",
            json={"user_confirmed": True},
            headers=headers_b,
        ).status_code
        == 404
    )
    assert (
        client_a.get(
            f"/api/v1/research/conversations/{conversation_id}/stage-briefing",
            headers=headers_a,
        ).status_code
        == 200
    )
