"""Safety contracts for local submission-readiness checks."""

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


def _draft() -> dict[str, str]:
    return {
        "title": "即时反馈的课堂研究",
        "format": "markdown",
        "content": (
            "# 即时反馈的课堂研究\n\n## 引言\n研究问题是即时反馈是否改善 Python 练习表现。"
            "\n\n## 方法\n使用匿名记录。\n\n## 实验\n实验显著提升了完成率。"
            "\n\n## 结论\n证明即时反馈有效。"
        ),
    }


def _review_and_revision(client: TestClient) -> tuple[dict[str, object], dict[str, object]]:
    conversation_id = _conversation(client)
    draft = client.post(
        f"/api/v1/research/conversations/{conversation_id}/paper-drafts", json=_draft()
    ).json()
    review = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/reviews",
        json={"user_confirmed": True},
    ).json()
    task = next(
        item
        for item in review["revision_tasks"]
        if item["finding_id"].startswith("unsupported-claim")
    )
    accepted = client.patch(
        f"/api/v1/research/paper-reviews/{review['review_id']}/revision-tasks/{task['task_id']}",
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200
    suggestion = client.post(
        f"/api/v1/research/paper-reviews/{review['review_id']}/revision-tasks/{task['task_id']}/suggestions",
        json={"user_confirmed": True},
    )
    assert suggestion.status_code == 201
    revision_response = client.post(
        f"/api/v1/research/revision-suggestions/{suggestion.json()['suggestion_id']}/apply",
        json={"action": "accepted"},
    )
    assert revision_response.status_code == 201
    revision = revision_response.json()
    return draft, revision


def test_submission_readiness_is_explicit_and_flags_unverified_claims(
    client: TestClient,
) -> None:
    draft, _revision = _review_and_revision(client)

    readiness = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/submission-readiness",
        json={"user_confirmed": True},
    )
    restored = client.get(f"/api/v1/research/paper-drafts/{draft['draft_id']}/submission-readiness")

    assert readiness.status_code == 201
    body = readiness.json()
    assert body["readiness_status"] == "not_ready"
    assert any(item["classification"] == "to_verify" for item in body["blockers"])
    assert any("venue" in item["message"].casefold() for item in body["manual_checks"])
    assert len(restored.json()) == 1


def test_export_requires_explicit_confirmation_and_redacts_sensitive_text(
    client: TestClient,
) -> None:
    draft, _revision = _review_and_revision(client)
    readiness = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/submission-readiness",
        json={"user_confirmed": True},
    )
    assert readiness.status_code == 201

    blocked = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/export-package",
        json={"user_confirmed": False},
    )
    exported = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/export-package",
        json={"user_confirmed": True},
    )

    assert blocked.status_code == 422
    assert exported.status_code == 200
    files = exported.json()["files"]
    assert {item["filename"].rsplit(".", 1)[-1] for item in files} == {"md", "json"}
    joined = "\n".join(item["content"] for item in files).casefold()
    assert "api_key=" not in joined
    assert "c:\\users\\" not in joined
    assert "对话记录" not in joined


def test_export_rejects_a_check_created_before_the_latest_revision(
    client: TestClient,
) -> None:
    conversation_id = _conversation(client)
    draft = client.post(
        f"/api/v1/research/conversations/{conversation_id}/paper-drafts", json=_draft()
    ).json()
    stale_check = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/submission-readiness",
        json={"user_confirmed": True},
    )
    assert stale_check.status_code == 201
    assert stale_check.json()["revision_id"] is None

    review = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/reviews",
        json={"user_confirmed": True},
    ).json()
    task = next(
        item
        for item in review["revision_tasks"]
        if item["finding_id"].startswith("unsupported-claim")
    )
    client.patch(
        f"/api/v1/research/paper-reviews/{review['review_id']}"
        f"/revision-tasks/{task['task_id']}",
        json={"status": "accepted"},
    )
    suggestion = client.post(
        f"/api/v1/research/paper-reviews/{review['review_id']}"
        f"/revision-tasks/{task['task_id']}/suggestions",
        json={"user_confirmed": True},
    ).json()
    revision = client.post(
        f"/api/v1/research/revision-suggestions/{suggestion['suggestion_id']}/apply",
        json={"action": "accepted"},
    )
    assert revision.status_code == 201

    exported = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/export-package",
        json={"user_confirmed": True},
    )

    assert exported.status_code == 409
    assert "checklist is stale" in exported.json()["detail"]


def test_export_rejects_a_revision_from_an_older_review(client: TestClient) -> None:
    draft, _revision = _review_and_revision(client)
    second_review = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/reviews",
        json={"user_confirmed": True},
    )
    assert second_review.status_code == 200
    readiness = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/submission-readiness",
        json={"user_confirmed": True},
    )
    assert readiness.status_code == 201

    exported = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/export-package",
        json={"user_confirmed": True},
    )

    assert exported.status_code == 409
    assert "latest review" in exported.json()["detail"]
