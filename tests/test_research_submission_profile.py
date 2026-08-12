"""API contracts for the user-configured, rules-only submission profile."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

os.environ["LEARNING_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import engine  # noqa: E402
from code_navi.learning.models import Base  # noqa: E402
from code_navi.research.conversation_agent import (  # noqa: E402
    ConversationDecisionOutcome,
    ResearchConversationDecision,
)
from code_navi.research.conversation_schemas import ResearchProfilePatch  # noqa: E402
from code_navi.research.router import _conversation_service  # noqa: E402
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


class ReadyDecisionGenerator:
    def generate(self, **_: object) -> ConversationDecisionOutcome:
        return ConversationDecisionOutcome.generated(
            ResearchConversationDecision(
                reply="研究画像已整理。",
                intent="clarify",
                profile_patch=ResearchProfilePatch(
                    topic="生成式 AI 编程学习反馈",
                    research_questions=["即时反馈是否改善 Python 练习表现？"],
                    context="30 名本科生课程",
                    methods=["小规模对照研究"],
                    data_requirements="匿名学习记录",
                    constraints=["两周", "没有 GPU"],
                    expected_output="课程项目报告",
                ),
                candidate_questions=["即时反馈是否改善 Python 练习表现？"],
                assumptions=[],
                uncertainties=["伦理与随机分组待确认"],
                next_question="是否查看计划？",
                suggested_answers=["查看计划", "补充条件", "继续讨论"],
                recommended_action="review_profile",
            ),
            run_id="test-ready",
            event_count=1,
        )


def _conversation(client: TestClient) -> str:
    original = _conversation_service.decision_generator
    _conversation_service.decision_generator = ReadyDecisionGenerator()
    try:
        response = client.post(
            "/api/v1/research/conversations",
            json={"initial_message": "我研究 Python 反馈"},
        )
    finally:
        _conversation_service.decision_generator = original
    assert response.status_code == 201
    return response.json()["conversation_id"]


def test_submission_profile_is_user_saved_and_restorable(client: TestClient) -> None:
    conversation_id = _conversation(client)
    payload = {
        "target_venue": "教育技术方向会议",
        "anonymity_required": True,
        "length_or_section_requirements": "六个主要章节，篇幅待导师确认",
        "ethics_and_data_requirements": "需匿名化并核对数据许可",
        "user_notes": "不抓取会议官网规则",
    }

    saved = client.put(
        f"/api/v1/research/conversations/{conversation_id}/submission-profile", json=payload
    )
    restored = client.get(f"/api/v1/research/conversations/{conversation_id}/submission-profile")

    assert saved.status_code == 200
    assert restored.status_code == 200
    assert saved.json()["target_venue"] == "教育技术方向会议"
    assert saved.json()["anonymity_required"] is True
    assert restored.json() == saved.json()


def test_submission_readiness_keeps_missing_venue_as_to_verify(client: TestClient) -> None:
    conversation_id = _conversation(client)
    draft = client.post(
        f"/api/v1/research/conversations/{conversation_id}/paper-drafts",
        json={
            "title": "课堂研究",
            "format": "markdown",
            "content": "# 课堂研究\n\n## 引言\n待补充",
        },
    ).json()

    readiness = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/submission-readiness",
        json={"user_confirmed": True},
    )

    assert readiness.status_code == 201
    pending_venue = next(
        item for item in readiness.json()["manual_checks"] if item["id"] == "target-venue-pending"
    )
    assert pending_venue["classification"] == "to_verify"
    assert "待用户确认" in pending_venue["message"]


def test_anonymous_profile_surfaces_identity_and_ethics_gaps(client: TestClient) -> None:
    conversation_id = _conversation(client)
    saved = client.put(
        f"/api/v1/research/conversations/{conversation_id}/submission-profile",
        json={
            "target_venue": "教育技术方向会议",
            "anonymity_required": True,
            "ethics_and_data_requirements": "需要匿名化、伦理与数据许可说明",
        },
    )
    assert saved.status_code == 200
    draft = client.post(
        f"/api/v1/research/conversations/{conversation_id}/paper-drafts",
        json={
            "title": "课堂研究",
            "format": "markdown",
            "content": "# 课堂研究\n\n姓名：陈同学\n\n## 引言\n待补充",
        },
    ).json()

    readiness = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/submission-readiness",
        json={"user_confirmed": True},
    )

    assert readiness.status_code == 201
    body = readiness.json()
    assert body["submission_profile"]["target_venue"] == "教育技术方向会议"
    assert any(item["id"] == "anonymity-risk" for item in body["blockers"])
    assert any(item["id"] == "ethics-data-requirements-pending" for item in body["manual_checks"])
