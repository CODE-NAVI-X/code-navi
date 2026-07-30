"""Offline integration tests for the persisted research-clarification API."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

os.environ["LEARNING_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.learning.database import engine  # noqa: E402
from code_navi.learning.models import Base  # noqa: E402
from code_navi.server import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_tables() -> Generator[None, None, None]:
    """Keep every API test isolated while reusing the PoC SQLite engine."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def create_session(client: TestClient) -> dict:
    response = client.post("/api/v1/research/sessions", json={})
    assert response.status_code == 201
    return response.json()


def submit_turn(client: TestClient, session_id: str, payload: dict) -> dict:
    response = client.post(f"/api/v1/research/sessions/{session_id}/turns", json=payload)
    assert response.status_code == 200
    return response.json()


def test_create_session_returns_first_missing_field_and_three_options(client: TestClient) -> None:
    body = create_session(client)

    assert body["completed"] is False
    assert body["missing_fields"] == [
        "research_domain",
        "core_question",
        "data_and_method",
        "constraints",
        "expected_deliverable",
    ]
    assert body["next_question"]["field"] == "research_domain"
    assert len(body["next_question"]["options"]) == 3


def test_free_input_is_recorded_and_session_can_be_restored(client: TestClient) -> None:
    created = create_session(client)
    session_id = created["session_id"]

    progressed = submit_turn(client, session_id, {"answer": "计算机视觉"})
    restored = client.get(f"/api/v1/research/sessions/{session_id}")

    assert progressed["state"]["research_domain"] == "计算机视觉"
    assert progressed["next_question"]["field"] == "core_question"
    assert restored.status_code == 200
    assert restored.json()["state"]["research_domain"] == "计算机视觉"
    assert restored.json()["turns"][0]["input_mode"] == "free_text"


def test_initial_description_is_recorded_as_first_free_text_response(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/research/sessions",
        json={"initial_description": "面向教育场景的人工智能研究"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["state"]["research_domain"] == "面向教育场景的人工智能研究"
    assert body["next_question"]["field"] == "core_question"
    assert body["turns"][0]["input_mode"] == "initial_description"


def test_recommended_options_advance_all_fields_and_return_research_brief(
    client: TestClient,
) -> None:
    created = create_session(client)
    session_id = created["session_id"]
    body = created

    while not body["completed"]:
        body = submit_turn(
            client,
            session_id,
            {"selected_option": body["next_question"]["options"][0]},
        )

    assert body["research_brief"]["research_domain"]
    assert body["research_brief"]["core_question"]
    assert body["research_brief"]["data_and_method"]
    assert body["research_brief"]["constraints"]
    assert body["research_brief"]["expected_deliverable"]
    assert body["next_question"] is None


def test_missing_session_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/research/sessions/missing-session")

    assert response.status_code == 404


def test_turn_requires_exactly_one_response_kind(client: TestClient) -> None:
    session_id = create_session(client)["session_id"]

    response = client.post(
        f"/api/v1/research/sessions/{session_id}/turns",
        json={"answer": "自由输入", "selected_option": "推荐项"},
    )

    assert response.status_code == 422
