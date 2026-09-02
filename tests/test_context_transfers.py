"""End-to-end API tests for Learning-to-Research context drafts."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import Base, SessionLocal, engine  # noqa: E402
from code_navi.research.conversation_agent import ConversationDecisionOutcome  # noqa: E402
from code_navi.research.router import _conversation_service  # noqa: E402
from code_navi.server import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_tables(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "mock")
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def _create_learning_record(client: TestClient, session_id: str = "sess-transfer") -> dict:
    explained = client.post(
        "/api/v1/learning/explain",
        json={"knowledge_point": "检索增强生成", "session_id": session_id},
    )
    assert explained.status_code == 200
    notebook = client.get("/api/v1/learning/notebook", params={"session_id": session_id})
    assert notebook.status_code == 200
    return notebook.json()[0]


class CapturingUnavailableDecisionGenerator:
    """Capture the restored Learning context while exercising offline clarification."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate(self, **kwargs: object) -> ConversationDecisionOutcome:
        self.calls.append(kwargs)
        return ConversationDecisionOutcome.unavailable()


def test_real_learning_record_creates_restorable_context(client: TestClient) -> None:
    record = _create_learning_record(client)

    created = client.post(
        "/api/v1/context-transfers",
        json={
            "source_module": "learning",
            "source_object": {"type": "notebook_item", "id": record["id"]},
            "source_scope_id": "sess-transfer",
            "target_module": "research",
            "selected_parts": ["summary"],
        },
    )

    assert created.status_code == 201
    body = created.json()
    assert body["schema_version"] == "context-transfer.v1"
    assert body["source_object"] == {"type": "notebook_item", "id": record["id"]}
    assert body["topic"] == "检索增强生成"
    assert body["summary"] == record["content"]
    assert body["selected_content"] == [
        {"kind": "summary", "label": "学习摘要", "content": record["content"]}
    ]

    restored = client.get(
        f"/api/v1/context-transfers/{body['id']}",
        params={"source_scope_id": "sess-transfer"},
    )
    assert restored.status_code == 200
    assert restored.json() == body


def test_workspace_learning_record_keeps_context_transfer_session_and_research_boundaries(
    client: TestClient,
) -> None:
    task = client.post(
        "/api/v1/tasks",
        json={"local_profile_id": "profile-transfer", "goal": "研究 RAG 证据覆盖"},
    ).json()
    explained = client.post(
        "/api/v1/learning/explain",
        json={
            "knowledge_point": "检索增强生成",
            "session_id": "sess-workspace-transfer",
            "local_profile_id": "profile-transfer",
            "workspace_id": task["workspace_id"],
            "task_id": task["id"],
        },
    )
    assert explained.status_code == 200
    other_session = client.post(
        "/api/v1/learning/explain",
        json={"knowledge_point": "不属于当前传递的记录", "session_id": "sess-transfer-other"},
    )
    assert other_session.status_code == 200

    source_items = client.get(
        "/api/v1/learning/notebook", params={"session_id": "sess-workspace-transfer"}
    )
    other_items = client.get(
        "/api/v1/learning/notebook", params={"session_id": "sess-transfer-other"}
    )
    assert source_items.status_code == 200
    assert other_items.status_code == 200
    assert [item["id"] for item in source_items.json()] == [explained.json()["notebook_item_id"]]
    assert [item["id"] for item in other_items.json()] == [other_session.json()["notebook_item_id"]]

    created = client.post(
        "/api/v1/context-transfers",
        json={
            "source_module": "learning",
            "source_object": {"type": "notebook_item", "id": explained.json()["notebook_item_id"]},
            "source_scope_id": "sess-workspace-transfer",
            "target_module": "research",
            "selected_parts": ["summary"],
        },
    )
    assert created.status_code == 201
    confirmed = client.post(
        f"/api/v1/context-transfers/{created.json()['id']}/confirm",
        params={"source_scope_id": "sess-workspace-transfer"},
        json={
            "topic": "RAG 证据覆盖研究",
            "summary": "比较检索策略的证据覆盖。",
            "selected_content": [],
        },
    )
    assert confirmed.status_code == 200
    conversation = confirmed.json()
    assert conversation["generation_mode"] == "rules"
    assert conversation["context_provenance"]["source_scope_id"] == "sess-workspace-transfer"
    assert "workspace_id" not in conversation["context_provenance"]
    assert "task_id" not in conversation["context_provenance"]

    restored = client.get(f"/api/v1/research/conversations/{conversation['conversation_id']}")
    assert restored.status_code == 200
    assert restored.json()["context_provenance"] == conversation["context_provenance"]


def test_context_source_must_belong_to_learning_session(client: TestClient) -> None:
    record = _create_learning_record(client, "sess-owner")

    response = client.post(
        "/api/v1/context-transfers",
        json={
            "source_module": "learning",
            "source_object": {"type": "notebook_item", "id": record["id"]},
            "source_scope_id": "sess-other",
            "target_module": "research",
            "selected_parts": ["summary"],
        },
    )

    assert response.status_code == 404


def test_context_can_be_edited_and_cleared_without_changing_source(
    client: TestClient,
) -> None:
    record = _create_learning_record(client)
    created = client.post(
        "/api/v1/context-transfers",
        json={
            "source_module": "learning",
            "source_object": {"type": "notebook_item", "id": record["id"]},
            "source_scope_id": "sess-transfer",
            "target_module": "research",
            "selected_parts": ["summary"],
        },
    ).json()

    updated = client.patch(
        f"/api/v1/context-transfers/{created['id']}",
        params={"source_scope_id": "sess-transfer"},
        json={
            "topic": "RAG 可信度研究",
            "summary": "聚焦证据覆盖与引用准确率。",
            "selected_content": [
                {
                    "kind": "summary",
                    "label": "研究入口",
                    "content": "比较不同检索策略的证据覆盖率。",
                }
            ],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["topic"] == "RAG 可信度研究"

    notebook = client.get(
        "/api/v1/learning/notebook", params={"session_id": "sess-transfer"}
    ).json()
    assert notebook[0]["content"] == record["content"]

    deleted = client.delete(
        f"/api/v1/context-transfers/{created['id']}",
        params={"source_scope_id": "sess-transfer"},
    )
    assert deleted.status_code == 204
    missing = client.get(
        f"/api/v1/context-transfers/{created['id']}",
        params={"source_scope_id": "sess-transfer"},
    )
    assert missing.status_code == 404


def test_client_cannot_override_canonical_source_fields(client: TestClient) -> None:
    record = _create_learning_record(client)

    response = client.post(
        "/api/v1/context-transfers",
        json={
            "source_module": "learning",
            "source_object": {"type": "notebook_item", "id": record["id"]},
            "source_scope_id": "sess-transfer",
            "target_module": "research",
            "selected_parts": ["summary"],
            "topic": "浏览器伪造主题",
        },
    )

    assert response.status_code == 422


def test_final_confirmation_creates_one_research_conversation_with_provenance(
    client: TestClient,
) -> None:
    record = _create_learning_record(client)
    created = client.post(
        "/api/v1/context-transfers",
        json={
            "source_module": "learning",
            "source_object": {"type": "notebook_item", "id": record["id"]},
            "source_scope_id": "sess-transfer",
            "target_module": "research",
            "selected_parts": ["summary"],
        },
    ).json()
    final_data = {
        "topic": "RAG 证据覆盖研究",
        "summary": "比较不同检索策略对证据覆盖率的影响。",
        "selected_content": [],
    }

    confirmed = client.post(
        f"/api/v1/context-transfers/{created['id']}/confirm",
        params={"source_scope_id": "sess-transfer"},
        json=final_data,
    )

    assert confirmed.status_code == 200
    conversation = confirmed.json()
    assert conversation["profile"]["topic"] == final_data["topic"]
    assert conversation["generation_mode"] == "rules"
    assert conversation["context_provenance"] == {
        "schema_version": "context-provenance.v1",
        "transfer_id": created["id"],
        "source_module": "learning",
        "source_object": {"type": "notebook_item", "id": record["id"]},
        "source_scope_id": "sess-transfer",
        "target_module": "research",
        **final_data,
        "confirmed_at": conversation["context_provenance"]["confirmed_at"],
    }

    restored_transfer = client.get(
        f"/api/v1/context-transfers/{created['id']}",
        params={"source_scope_id": "sess-transfer"},
    ).json()
    assert restored_transfer["status"] == "confirmed"
    assert restored_transfer["confirmed_conversation_id"] == conversation["conversation_id"]
    restored_conversation = client.get(
        f"/api/v1/research/conversations/{conversation['conversation_id']}"
    )
    assert restored_conversation.status_code == 200
    assert restored_conversation.json()["context_provenance"] == conversation[
        "context_provenance"
    ]

    repeated = client.post(
        f"/api/v1/context-transfers/{created['id']}/confirm",
        params={"source_scope_id": "sess-transfer"},
        json={
            "topic": "不应覆盖已确认主题",
            "summary": "不应覆盖已确认摘要",
            "selected_content": [],
        },
    )
    assert repeated.status_code == 200
    assert repeated.json()["conversation_id"] == conversation["conversation_id"]
    assert repeated.json()["context_provenance"] == conversation["context_provenance"]

    blocked_update = client.patch(
        f"/api/v1/context-transfers/{created['id']}",
        params={"source_scope_id": "sess-transfer"},
        json={"topic": "确认后禁止修改"},
    )
    assert blocked_update.status_code == 409
    blocked_delete = client.delete(
        f"/api/v1/context-transfers/{created['id']}",
        params={"source_scope_id": "sess-transfer"},
    )
    assert blocked_delete.status_code == 409


def test_confirmation_requires_the_source_learning_session(client: TestClient) -> None:
    record = _create_learning_record(client, "sess-owner")
    created = client.post(
        "/api/v1/context-transfers",
        json={
            "source_module": "learning",
            "source_object": {"type": "notebook_item", "id": record["id"]},
            "source_scope_id": "sess-owner",
            "target_module": "research",
            "selected_parts": ["summary"],
        },
    ).json()

    response = client.post(
        f"/api/v1/context-transfers/{created['id']}/confirm",
        params={"source_scope_id": "sess-other"},
        json={
            "topic": "越权主题",
            "summary": "越权摘要",
            "selected_content": [],
        },
    )

    assert response.status_code == 404


def test_research_uses_and_restores_confirmed_learning_context(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _create_learning_record(client)
    transfer = client.post(
        "/api/v1/context-transfers",
        json={
            "source_module": "learning",
            "source_object": {"type": "notebook_item", "id": record["id"]},
            "source_scope_id": "sess-transfer",
            "target_module": "research",
            "selected_parts": ["summary"],
        },
    ).json()
    final_context = {
        "topic": "RAG 证据覆盖研究",
        "summary": "已掌握检索、生成与引用之间的基本关系。",
        "selected_content": [
            {
                "kind": "summary",
                "label": "已确认学习重点",
                "content": "检索质量会影响回答所依据的证据范围。",
            }
        ],
    }
    conversation = client.post(
        f"/api/v1/context-transfers/{transfer['id']}/confirm",
        params={"source_scope_id": "sess-transfer"},
        json=final_context,
    ).json()
    assert conversation["profile"]["topic"] == final_context["topic"]
    assert "研究主题" not in conversation["next_question"]

    generator = CapturingUnavailableDecisionGenerator()
    monkeypatch.setattr(_conversation_service, "decision_generator", generator)
    for message in (
        "我想比较不同检索策略如何影响回答的证据覆盖率",
        "面向高校课程知识库",
        "我只能使用公开数据集和现有检索日志",
    ):
        current = client.post(
            f"/api/v1/research/conversations/{conversation['conversation_id']}/messages",
            json={"message": message},
        )
        assert current.status_code == 200
        conversation = current.json()

    assert conversation["ready_for_plan"] is True
    assert conversation["research_plan"] is None
    assert len(generator.calls) == 3
    for call in generator.calls:
        confirmed_context = call["confirmed_context"]
        assert confirmed_context.topic == final_context["topic"]
        assert confirmed_context.summary == final_context["summary"]
        assert confirmed_context.selected_content[0].content == final_context[
            "selected_content"
        ][0]["content"]

    restored = client.get(
        f"/api/v1/research/conversations/{conversation['conversation_id']}"
    )
    assert restored.status_code == 200
    restored_body = restored.json()
    assert restored_body["context_provenance"] == conversation["context_provenance"]
    assert restored_body["profile"] == conversation["profile"]
    assert restored_body["research_plan"] is None
    assert restored_body["messages"] == conversation["messages"]


# ---------------------------------------------------------------------------
# §3.2 include_mastery_snapshot — server-side rule-generated mastery snapshot
# ---------------------------------------------------------------------------


def _seed_portrait(
    session_id: str,
    profile_id: str,
    strong_point: str,
    weak_point: str,
) -> None:
    """Persist real quiz attempts so the rule portrait has sufficient samples."""
    import uuid

    from code_navi.learning_profile.models import QuizAttemptModel

    with SessionLocal() as db:
        rows = [
            QuizAttemptModel(
                attempt_id=str(uuid.uuid4()),
                quiz_id="quiz-seed",
                session_id=session_id,
                knowledge_point=strong_point,
                profile_id=profile_id,
                user_id="poc-user",
                question_id=f"q-strong-{index}",
                question_type="single",
                points=10,
                score=10,
                max_score=10,
                correct=True,
                graded=True,
                graded_by="rules",
                is_mock=True,
            )
            for index in range(3)
        ]
        rows += [
            QuizAttemptModel(
                attempt_id=str(uuid.uuid4()),
                quiz_id="quiz-seed",
                session_id=session_id,
                knowledge_point=weak_point,
                profile_id=profile_id,
                user_id="poc-user",
                question_id=f"q-weak-{index}",
                question_type="single",
                points=10,
                score=2,
                max_score=10,
                correct=False,
                graded=True,
                graded_by="rules",
                is_mock=True,
            )
            for index in range(3)
        ]
        db.add_all(rows)
        db.commit()


def _create_transfer(client: TestClient, session_id: str = "sess-transfer") -> dict:
    record = _create_learning_record(client, session_id)
    created = client.post(
        "/api/v1/context-transfers",
        json={
            "source_module": "learning",
            "source_object": {"type": "notebook_item", "id": record["id"]},
            "source_scope_id": session_id,
            "target_module": "research",
            "selected_parts": ["summary"],
        },
    )
    assert created.status_code in (200, 201)
    return created.json()


def _confirm(
    client: TestClient,
    transfer: dict,
    session_id: str,
    extra: dict | None = None,
):
    return client.post(
        f"/api/v1/context-transfers/{transfer['id']}/confirm",
        params={"source_scope_id": session_id},
        json={
            "topic": "RAG 证据覆盖研究",
            "summary": "比较不同检索策略对证据覆盖率的影响。",
            "selected_content": [],
            **(extra or {}),
        },
    )


def test_snapshot_switch_off_keeps_provenance_unchanged(client: TestClient) -> None:
    transfer = _create_transfer(client)
    confirmed = _confirm(client, transfer, "sess-transfer")

    assert confirmed.status_code == 200
    assert "learning_mastery_snapshot" not in confirmed.json()["context_provenance"]


def test_snapshot_generated_from_real_portrait_when_switched_on(
    client: TestClient,
) -> None:
    _seed_portrait(
        "sess-transfer",
        "0d3f7b3e-1111-4aaa-8bbb-2c2d3e4f5a6b",
        "检索增强生成",
        "循环不变式",
    )
    transfer = _create_transfer(client)
    confirmed = _confirm(
        client, transfer, "sess-transfer", {"include_mastery_snapshot": True}
    )

    assert confirmed.status_code == 200
    snapshot = confirmed.json()["context_provenance"]["learning_mastery_snapshot"]
    assert snapshot == {"strong": ["检索增强生成"], "weak": ["循环不变式"]}

    restored = client.get(
        f"/api/v1/research/conversations/{confirmed.json()['conversation_id']}"
    )
    assert restored.status_code == 200
    assert restored.json()["context_provenance"]["learning_mastery_snapshot"] == snapshot


def test_snapshot_defaults_to_empty_state_without_portrait(client: TestClient) -> None:
    transfer = _create_transfer(client)
    confirmed = _confirm(
        client, transfer, "sess-transfer", {"include_mastery_snapshot": True}
    )

    assert confirmed.status_code == 200
    assert "learning_mastery_snapshot" not in confirmed.json()["context_provenance"]


def test_client_cannot_supply_snapshot_values(client: TestClient) -> None:
    transfer = _create_transfer(client)
    response = _confirm(
        client,
        transfer,
        "sess-transfer",
        {
            "include_mastery_snapshot": True,
            "learning_mastery_snapshot": {"strong": ["伪造知识点"], "weak": []},
        },
    )

    assert response.status_code == 422


def test_stage_briefing_reads_the_written_snapshot(client: TestClient) -> None:
    _seed_portrait(
        "sess-transfer",
        "0d3f7b3e-2222-4aaa-8bbb-2c2d3e4f5a6b",
        "检索增强生成",
        "循环不变式",
    )
    transfer = _create_transfer(client)
    confirmed = _confirm(
        client, transfer, "sess-transfer", {"include_mastery_snapshot": True}
    ).json()

    briefing = client.get(
        f"/api/v1/research/conversations/{confirmed['conversation_id']}/stage-briefing"
    )

    assert briefing.status_code == 200
    names = [
        point["name"]
        for point in briefing.json()["stage_summary"]["knowledge_points"] or []
    ]
    assert "检索增强生成" in names
    assert "循环不变式" in names
