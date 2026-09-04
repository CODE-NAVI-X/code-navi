"""Backend tests for the static structure/framework practice catalogue (#56)."""

from __future__ import annotations

import os
from collections.abc import Generator
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import Base, engine  # noqa: E402
from code_navi.practice.structure_catalog import (  # noqa: E402
    TOPICS,
    exercises_for_topic,
)
from code_navi.practice.structure_practice import DEFAULT_EXERCISES  # noqa: E402
from code_navi.server import app  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_tables() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as tc:
        yield tc


def test_structure_catalog_lists_topics_and_public_exercises(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/practice/structure-catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "structure-practice.v1"
    assert len(payload["topics"]) == len(TOPICS)
    assert payload["exercises"]
    for exercise in payload["exercises"]:
        assert "answer" not in exercise
        assert "answer_sequence" not in exercise
        assert "required_tokens" not in exercise


def test_structure_topic_generates_code_fill_set(client: TestClient) -> None:
    topic = TOPICS[0]

    generated = client.post(
        "/api/v1/practice/sets/generate",
        json={"kind": "code_practice", "topic": topic.id, "count": 3},
    )

    assert generated.status_code == 200, generated.text
    payload = generated.json()
    assert payload["generation_mode"] == "rules_fallback"
    assert payload["provider_name"] == "rules"
    assert {item["item_kind"] for item in payload["items"]} == {"code_fill"}
    assert len(payload["items"]) == min(3, len(exercises_for_topic(topic.id)))


def test_context_code_practice_binds_every_item_to_learning_knowledge_points(
    client: TestClient,
) -> None:
    context = {
        "source_session_id": "sess-direct-structure",
        "knowledge_points": [
            {"name": "卷积", "source_ref": "notebook-conv", "mastery": 0.2},
            {"name": "池化", "source_ref": "notebook-pool", "mastery": None},
        ],
        "objective": "理解卷积与池化在图像特征提取中的作用",
        "notes_summary": "先掌握主干结构。",
    }

    generated = client.post(
        "/api/v1/practice/sets/generate",
        json={"kind": "code_practice", "context": context, "count": 5},
    )

    assert generated.status_code == 200, generated.text
    payload = generated.json()
    assert payload["effective_context"] == context
    assert payload["coverage"] == ["卷积", "池化"]
    assert payload["items"]
    assert {item["item_kind"] for item in payload["items"]} == {
        "code_fill",
        "coding_problem",
    }
    assert all(item["knowledge_points"] == ["卷积", "池化"] for item in payload["items"])


def test_structure_topic_set_can_grade_with_code_fill_grade(
    client: TestClient,
) -> None:
    topic = TOPICS[0]
    generated = client.post(
        "/api/v1/practice/sets/generate",
        json={"kind": "code_practice", "topic": topic.id, "count": 3},
    ).json()
    item = generated["items"][0]
    blank_ids = [blank["blank_id"] for blank in item["payload"]["blanks"]]

    response = client.post(
        "/api/v1/practice/code-fill/grade",
        json={
            "set_id": generated["set_id"],
            "item_id": item["item_id"],
            "attempt_id": str(uuid4()),
            "blank_answers": [
                {"blank_id": blank_id, "value": "wrong"} for blank_id in blank_ids
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["graded"] is True


def test_legacy_structure_exercise_api_returns_list_and_grade(
    client: TestClient,
) -> None:
    listed = client.get("/api/v1/practice/structure-exercises")
    assert listed.status_code == 200
    exercise_id = listed.json()["exercises"][0]["id"]
    exercise = next(item for item in DEFAULT_EXERCISES if item.id == exercise_id)

    if exercise.levels:
        answer = [list(level.answer_sequence) for level in exercise.levels]
    else:
        answer = list(exercise.answer_sequence)

    submitted = client.post(
        f"/api/v1/practice/structure-exercises/{exercise_id}/submit",
        json={"answer": answer},
    )

    assert submitted.status_code == 200
    assert submitted.json()["verdict"] == "accepted"


def test_structure_evaluate_and_chat_return_disabled_without_provider(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "code_navi.practice.router.create_ai_service",
        lambda _settings: SimpleNamespace(
            evaluator=None,
            tutor=None,
            message="AI 功能未启用",
        ),
    )
    listed = client.get("/api/v1/practice/structure-exercises").json()
    exercise_id = listed["exercises"][0]["id"]
    exercise = next(item for item in DEFAULT_EXERCISES if item.id == exercise_id)
    answer = (
        [list(level.answer_sequence) for level in exercise.levels]
        if exercise.levels
        else list(exercise.answer_sequence)
    )

    evaluated = client.post(
        f"/api/v1/practice/structure-exercises/{exercise_id}/evaluate",
        json={"answer": answer},
    )
    chatted = client.post(
        f"/api/v1/practice/structure-exercises/{exercise_id}/chat",
        json={"question": "为什么？", "history": []},
    )

    assert evaluated.status_code == 200
    assert evaluated.json()["ai"]["status"] == "disabled"
    assert chatted.status_code == 200
    assert chatted.json()["ai"]["reply"]
