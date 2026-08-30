"""Safety contracts for local paper drafts, reviews, tasks and revisions."""

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
from code_navi.research.research_artifact_llm import ArtifactLlmOutcome  # noqa: E402
from code_navi.research.router import _conversation_service  # noqa: E402
from code_navi.server import app  # noqa: E402
from research_llm_fakes import ContextAwareArtifactGenerator  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_tables() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def restore_generators() -> Generator[None, None, None]:
    decision = _conversation_service.decision_generator
    artifact = _conversation_service.artifact_generator
    _conversation_service.artifact_generator = ContextAwareArtifactGenerator()
    yield
    _conversation_service.decision_generator = decision
    _conversation_service.artifact_generator = artifact


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


class StaticArtifactGenerator:
    def __init__(self, outcome: ArtifactLlmOutcome) -> None:
        self.outcome = outcome

    def generate(self, **_: object) -> ArtifactLlmOutcome:
        return self.outcome


def _conversation(client: TestClient) -> str:
    _conversation_service.decision_generator = ReadyDecisionGenerator()
    response = client.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我研究 Python 反馈"},
    )
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


def test_draft_is_explicitly_created_restored_and_limited(client: TestClient) -> None:
    conversation_id = _conversation(client)
    created = client.post(
        f"/api/v1/research/conversations/{conversation_id}/paper-drafts", json=_draft()
    )
    restored = client.get(f"/api/v1/research/conversations/{conversation_id}/paper-drafts")
    too_long = client.post(
        f"/api/v1/research/conversations/{conversation_id}/paper-drafts",
        json={**_draft(), "content": "x" * 60001},
    )

    assert created.status_code == 201
    assert created.json()["format"] == "markdown"
    assert len(restored.json()) == 1
    assert restored.json()[0]["content"] == _draft()["content"]
    assert too_long.status_code == 422


def test_rules_review_marks_unsupported_significance_as_to_verify(client: TestClient) -> None:
    conversation_id = _conversation(client)
    draft = client.post(
        f"/api/v1/research/conversations/{conversation_id}/paper-drafts", json=_draft()
    ).json()

    review = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/reviews",
        json={"user_confirmed": True},
    )

    assert review.status_code == 200
    findings = review.json()["findings"]
    claim = next(item for item in findings if "显著" in item["issue"])
    assert claim["severity"] == "major"
    assert claim["classification"] == "to_verify"
    assert review.json()["generation_mode"] == "llm"


def test_invalid_model_review_is_rejected_with_a_generation_error(client: TestClient) -> None:
    _conversation_service.artifact_generator = ContextAwareArtifactGenerator(
        {"paper_review": ArtifactLlmOutcome.generated("not-json")}
    )
    conversation_id = _conversation(client)
    draft = client.post(
        f"/api/v1/research/conversations/{conversation_id}/paper-drafts", json=_draft()
    ).json()

    review = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/reviews",
        json={"user_confirmed": True},
    )

    assert review.status_code == 422
    assert review.json()["detail"]["code"] == "research_generation_failed"
    assert review.json()["detail"]["stage"] == "invalid_output"


def test_valid_model_only_enhances_existing_rule_explanations(client: TestClient) -> None:
    _conversation_service.artifact_generator = ContextAwareArtifactGenerator(
        {
            "paper_review": ArtifactLlmOutcome.generated(
                '{"explanations":[{"finding_id":"unsupported-claim-1",'
                '"why_it_matters":"当前结果表述需要可追溯的实验事实。",'
                '"recommended_action":"保留待补充结果占位符。"}]}'
            )
        }
    )
    conversation_id = _conversation(client)
    draft = client.post(
        f"/api/v1/research/conversations/{conversation_id}/paper-drafts", json=_draft()
    ).json()

    review = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/reviews",
        json={"user_confirmed": True},
    ).json()
    claim = next(item for item in review["findings"] if item["id"] == "unsupported-claim-1")

    assert review["generation_mode"] == "llm"
    assert claim["severity"] == "major"
    assert claim["classification"] == "to_verify"
    assert claim["recommended_action"] == "保留待补充结果占位符。"


def test_bulk_revision_preview_is_retired_in_favor_of_confirmed_candidates(
    client: TestClient,
) -> None:
    conversation_id = _conversation(client)
    draft = client.post(
        f"/api/v1/research/conversations/{conversation_id}/paper-drafts", json=_draft()
    ).json()
    review = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/reviews",
        json={"user_confirmed": True},
    ).json()
    task = review["revision_tasks"][0]

    blocked = client.post(f"/api/v1/research/paper-reviews/{review['review_id']}/revisions")
    accepted = client.patch(
        f"/api/v1/research/paper-reviews/{review['review_id']}/revision-tasks/{task['task_id']}",
        json={"status": "accepted"},
    )
    revision = client.post(f"/api/v1/research/paper-reviews/{review['review_id']}/revisions")

    assert blocked.status_code == 409
    assert accepted.status_code == 200
    assert revision.status_code == 409
    assert "逐段生成并确认候选改写" in revision.json()["detail"]


def test_accepted_task_creates_a_persisted_paragraph_suggestion_and_manual_version(
    client: TestClient,
) -> None:
    conversation_id = _conversation(client)
    draft = client.post(
        f"/api/v1/research/conversations/{conversation_id}/paper-drafts", json=_draft()
    ).json()
    review = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/reviews",
        json={"user_confirmed": True},
    ).json()
    task = next(
        item for item in review["revision_tasks"] if item["finding_id"] == "unsupported-claim-1"
    )

    blocked = client.post(
        f"/api/v1/research/paper-reviews/{review['review_id']}/revision-tasks/{task['task_id']}/suggestions",
        json={"user_confirmed": True},
    )
    client.patch(
        f"/api/v1/research/paper-reviews/{review['review_id']}/revision-tasks/{task['task_id']}",
        json={"status": "accepted"},
    )
    suggestion = client.post(
        f"/api/v1/research/paper-reviews/{review['review_id']}/revision-tasks/{task['task_id']}/suggestions",
        json={"user_confirmed": True},
    )

    assert blocked.status_code == 409
    assert suggestion.status_code == 201
    candidate = suggestion.json()
    assert candidate["original_excerpt"] in draft["content"]
    assert candidate["classification"] == "to_verify"
    assert "[待补充实验结果]" in candidate["candidate_text"]

    revised = client.post(
        f"/api/v1/research/revision-suggestions/{candidate['suggestion_id']}/apply",
        json={"action": "accepted", "candidate_text": "[待补充实验结果：需人工核对]"},
    )
    restored = client.get(f"/api/v1/research/paper-drafts/{draft['draft_id']}/revisions")

    assert revised.status_code == 201
    assert revised.json()["content"] != draft["content"]
    assert revised.json()["parent_revision_id"] is None
    assert revised.json()["applied_suggestion_ids"] == [candidate["suggestion_id"]]
    assert "用户手动编辑" in revised.json()["change_summary"][0]
    assert restored.json()[0]["revision_id"] == revised.json()["revision_id"]
    persisted_review = client.get(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/reviews"
    ).json()[0]
    assert (
        next(
            item
            for item in persisted_review["revision_tasks"]
            if item["task_id"] == task["task_id"]
        )["status"]
        == "completed"
    )


def test_next_suggestion_uses_latest_revision_when_tasks_share_a_paragraph(
    client: TestClient,
) -> None:
    conversation_id = _conversation(client)
    draft = client.post(
        f"/api/v1/research/conversations/{conversation_id}/paper-drafts",
        json={"title": "待完善初稿", "format": "plain_text", "content": "现有研究说明。"},
    ).json()
    review = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/reviews",
        json={"user_confirmed": True},
    ).json()
    tasks = [
        next(item for item in review["revision_tasks"] if item["finding_id"] == finding_id)
        for finding_id in ("missing-摘要", "missing-引言")
    ]

    revisions = []
    for task in tasks:
        accepted = client.patch(
            f"/api/v1/research/paper-reviews/{review['review_id']}"
            f"/revision-tasks/{task['task_id']}",
            json={"status": "accepted"},
        )
        assert accepted.status_code == 200
        suggestion = client.post(
            f"/api/v1/research/paper-reviews/{review['review_id']}"
            f"/revision-tasks/{task['task_id']}/suggestions",
            json={"user_confirmed": True},
        )
        assert suggestion.status_code == 201
        applied = client.post(
            f"/api/v1/research/revision-suggestions/"
            f"{suggestion.json()['suggestion_id']}/apply",
            json={"action": "accepted"},
        )
        assert applied.status_code == 201
        revisions.append(applied.json())

    assert revisions[1]["parent_revision_id"] == revisions[0]["revision_id"]
    assert "补充“摘要”小节" in revisions[1]["content"]
    assert "补充“引言”小节" in revisions[1]["content"]


def test_invalid_model_suggestion_is_rejected_without_promoting_claim_to_fact(
    client: TestClient,
) -> None:
    _conversation_service.artifact_generator = ContextAwareArtifactGenerator(
        {
            "revision_suggestion": ArtifactLlmOutcome.generated(
                '{"candidate_text":"实验显著提升且证明有效"}'
            )
        }
    )
    conversation_id = _conversation(client)
    draft = client.post(
        f"/api/v1/research/conversations/{conversation_id}/paper-drafts", json=_draft()
    ).json()
    review = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/reviews",
        json={"user_confirmed": True},
    ).json()
    task = next(
        item for item in review["revision_tasks"] if item["finding_id"] == "unsupported-claim-1"
    )
    client.patch(
        f"/api/v1/research/paper-reviews/{review['review_id']}/revision-tasks/{task['task_id']}",
        json={"status": "accepted"},
    )

    suggestion = client.post(
        f"/api/v1/research/paper-reviews/{review['review_id']}/revision-tasks/{task['task_id']}/suggestions",
        json={"user_confirmed": True},
    )

    assert suggestion.status_code == 422
    assert suggestion.json()["detail"]["code"] == "research_generation_failed"
    assert suggestion.json()["detail"]["stage"] == "invalid_output"


def test_valid_model_candidate_is_restorable_without_changing_rule_boundary(
    client: TestClient,
) -> None:
    _conversation_service.artifact_generator = ContextAwareArtifactGenerator(
        {
            "revision_suggestion": ArtifactLlmOutcome.generated(
                '{"candidate_text":"[待补充实验结果]",'
                '"rationale":"先补充已保存的对照与指标记录。",'
                '"to_verify_items":["差异需统计检验"]}'
            )
        }
    )
    conversation_id = _conversation(client)
    draft = client.post(
        f"/api/v1/research/conversations/{conversation_id}/paper-drafts", json=_draft()
    ).json()
    review = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/reviews",
        json={"user_confirmed": True},
    ).json()
    task = next(
        item for item in review["revision_tasks"] if item["finding_id"] == "unsupported-claim-1"
    )
    client.patch(
        f"/api/v1/research/paper-reviews/{review['review_id']}/revision-tasks/{task['task_id']}",
        json={"status": "accepted"},
    )

    created = client.post(
        f"/api/v1/research/paper-reviews/{review['review_id']}/revision-tasks/{task['task_id']}/suggestions",
        json={"user_confirmed": True},
    )
    restored = client.get(
        f"/api/v1/research/paper-reviews/{review['review_id']}/revision-tasks/{task['task_id']}/suggestions"
    )

    assert created.status_code == 201
    assert created.json()["generation_mode"] == "llm"
    assert created.json()["classification"] == "to_verify"
    assert restored.json()[0]["suggestion_id"] == created.json()["suggestion_id"]


def test_skipping_candidate_persists_task_decision_without_creating_revision(
    client: TestClient,
) -> None:
    conversation_id = _conversation(client)
    draft = client.post(
        f"/api/v1/research/conversations/{conversation_id}/paper-drafts", json=_draft()
    ).json()
    review = client.post(
        f"/api/v1/research/paper-drafts/{draft['draft_id']}/reviews",
        json={"user_confirmed": True},
    ).json()
    task = next(
        task for task in review["revision_tasks"] if task["finding_id"] == "unsupported-claim-1"
    )
    client.patch(
        f"/api/v1/research/paper-reviews/{review['review_id']}/revision-tasks/{task['task_id']}",
        json={"status": "accepted"},
    )
    suggestion = client.post(
        f"/api/v1/research/paper-reviews/{review['review_id']}/revision-tasks/{task['task_id']}/suggestions",
        json={"user_confirmed": True},
    ).json()

    skipped = client.post(
        f"/api/v1/research/revision-suggestions/{suggestion['suggestion_id']}/apply",
        json={"action": "skipped"},
    )
    updated = client.get(f"/api/v1/research/paper-drafts/{draft['draft_id']}/reviews")
    revisions = client.get(f"/api/v1/research/paper-drafts/{draft['draft_id']}/revisions")

    assert skipped.status_code == 201
    assert skipped.json() is None
    assert (
        next(
            item
            for item in updated.json()[0]["revision_tasks"]
            if item["task_id"] == task["task_id"]
        )["status"]
        == "skipped"
    )
    assert revisions.json() == []
