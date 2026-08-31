"""Checkpoint-5 contracts: user-submitted reading reports stay user-sourced.

A reading report is the user's own summary of a saved paper.  It is stored as
``user_submitted_text_unverified`` per conversation, never mixed into the
paper-analysis facts, and is only returned to the owning conversation.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

os.environ["LEARNING_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import engine  # noqa: E402
from code_navi.learning.models import Base  # noqa: E402
from code_navi.server import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_tables() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def _create_conversation(client: TestClient) -> str:
    response = client.post("/api/v1/research/conversations", json={})
    assert response.status_code == 201
    return response.json()["conversation_id"]


def test_reading_report_saves_with_user_source_and_restores(client: TestClient) -> None:
    conversation_id = _create_conversation(client)

    saved = client.post(
        f"/api/v1/research/conversations/{conversation_id}/reading-reports",
        json={
            "paper_url": "https://arxiv.org/abs/1609.02907",
            "title": "Semi-Supervised Classification with Graph Convolutional Networks",
            "content": "我的理解：GCN 用简化的谱卷积在图上做半监督分类，Cora 是主要评测数据集。",
        },
    )
    assert saved.status_code == 201
    report = saved.json()[0]
    assert report["source_scope"] == "user_submitted_text_unverified"
    assert report["paper_url"].endswith("1609.02907")
    assert report["content"].startswith("我的理解")

    restored = client.get(
        f"/api/v1/research/conversations/{conversation_id}/reading-reports"
    )
    assert restored.status_code == 200
    assert len(restored.json()) == 1
    assert restored.json()[0]["report_id"] == report["report_id"]


def test_reading_report_requires_content_and_paper_url(client: TestClient) -> None:
    conversation_id = _create_conversation(client)

    rejected = client.post(
        f"/api/v1/research/conversations/{conversation_id}/reading-reports",
        json={"paper_url": "", "title": "x", "content": ""},
    )
    assert rejected.status_code == 422


def test_reading_reports_are_isolated_between_conversations(client: TestClient) -> None:
    first = _create_conversation(client)
    second = _create_conversation(client)

    client.post(
        f"/api/v1/research/conversations/{first}/reading-reports",
        json={"paper_url": "https://example.test/a", "title": "A", "content": "第一会话的阅读记录"},
    )

    other = client.get(
        f"/api/v1/research/conversations/{second}/reading-reports"
    )
    assert other.status_code == 200
    assert other.json() == []
