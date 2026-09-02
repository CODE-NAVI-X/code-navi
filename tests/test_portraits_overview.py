"""Contract tests for unified portraits overview read endpoint (contract §4.1)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

os.environ["LEARNING_DATABASE_URL"] = "sqlite:///:memory:"
os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.auth.rate_limiter import get_rate_limiter  # noqa: E402
from code_navi.context_transfer.models import ContextTransferModel  # noqa: E402
from code_navi.db import Base, SessionLocal, engine  # noqa: E402
from code_navi.learning_profile.models import (  # noqa: E402
    ConfusionMarkModel,
    QuizAttemptModel,
)
from code_navi.online_compiler.models import (  # noqa: E402
    PracticeLaunchModel,
    PracticeOutcomeModel,
)
from code_navi.practice.models import (  # noqa: E402
    CodeFillAttemptModel,
    PracticeSetModel,
)
from code_navi.research.models import (  # noqa: E402
    ResearchConversationModel,
    ResearchEvidenceBundleModel,
    ResearchReproductionEvaluationModel,
    ResearchReproductionPipelineModel,
)
from code_navi.server import app  # noqa: E402
from code_navi.workspaces.models import WorkspaceModel  # noqa: E402

PROFILE_A = "22222222-2222-4222-8222-222222222222"
PROFILE_B = "33333333-3333-4333-8333-333333333333"


@pytest.fixture(autouse=True)
def fresh_tables() -> Generator[None, None, None]:
    """Isolate each test in a clean in-memory database."""
    get_rate_limiter().reset()
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    get_rate_limiter().reset()


@pytest.fixture
def db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def _create_user_and_login(client: TestClient, email: str) -> dict[str, str]:
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "displayName": "Portrait Test"},
    )
    res = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert res.status_code == 200, res.text
    return {"X-CSRF-Token": res.json()["csrfToken"]}


def _add_quiz_attempt(
    db: Session,
    *,
    knowledge_point: str,
    score: int,
    max_score: int,
    graded: bool = True,
    profile_id: str = PROFILE_A,
    session_id: str = "sess-1",
    owner_principal_id: str | None = None,
) -> None:
    attempt = QuizAttemptModel(
        attempt_id=str(uuid.uuid4()),
        quiz_id="quiz-1",
        session_id=session_id,
        knowledge_point=knowledge_point,
        profile_id=profile_id,
        user_id=owner_principal_id or "poc-user",
        owner_principal_id=owner_principal_id,
        question_id="q1",
        question_type="single",
        points=max_score,
        score=score,
        max_score=max_score,
        correct=score >= max_score,
        graded=graded,
        graded_by="rules",
        is_mock=False,
        comment=None,
    )
    db.add(attempt)
    db.commit()


def _add_confusion_mark(
    db: Session,
    *,
    knowledge_point: str,
    source_ref: str,
    source_type: str = "explain",
    status: str = "confused",
    profile_id: str = PROFILE_A,
    session_id: str = "sess-1",
    owner_principal_id: str | None = None,
) -> None:
    mark = ConfusionMarkModel(
        session_id=session_id,
        profile_id=profile_id,
        user_id=owner_principal_id or "poc-user",
        owner_principal_id=owner_principal_id,
        knowledge_point=knowledge_point,
        source_type=source_type,
        source_ref=source_ref,
        status=status,
    )
    db.add(mark)
    db.commit()


def _add_code_fill(
    db: Session,
    *,
    set_id: str,
    item_id: str = "item-01",
    topic: str = "动态规划",
    score: int = 0,
    max_score: int = 2,
    profile_id: str = PROFILE_A,
    owner_principal_id: str | None = None,
) -> None:
    db.add(
        PracticeSetModel(
            set_id=set_id,
            kind="code_practice",
            context_snapshot={
                "request": {"topic": topic},
                "coverage": [topic],
            },
            profile_id=profile_id,
            generation_mode="mock",
            provider_name="mock",
            owner_principal_id=owner_principal_id,
        )
    )
    db.add(
        CodeFillAttemptModel(
            attempt_id=str(uuid.uuid4()),
            item_id=item_id,
            set_id=set_id,
            score=score,
            max_score=max_score,
            graded_by="rules",
            is_mock=False,
            graded=True,
            comment="挖空判定未通过",
            owner_principal_id=owner_principal_id,
        )
    )
    db.commit()


def _add_practice_outcome(
    db: Session,
    *,
    local_profile_id: str = "local-prof-1",
    learner_id: str = PROFILE_A,
    focus_label: str = "循环调试",
    summary: str = "运行时错误：ZeroDivisionError",
    owner_principal_id: str | None = None,
) -> None:
    workspace = WorkspaceModel(
        owner_scope_id=owner_principal_id or local_profile_id,
        personal_owner_scope_id=None,
        owner_principal_id=owner_principal_id,
        title="Practice workspace",
        kind="general",
    )
    db.add(workspace)
    db.flush()
    launch = PracticeLaunchModel(
        local_profile_id=local_profile_id,
        learner_id=learner_id,
        workspace_id=workspace.id,
        task_id=None,
        source_activity_id=None,
        capability="practice",
        mode="free_run",
        focus_type="topic",
        focus_id="loop-debugging",
        focus_label=focus_label,
        owner_principal_id=owner_principal_id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(launch)
    db.flush()
    outcome = PracticeOutcomeModel(
        launch_id=launch.id,
        local_profile_id=local_profile_id,
        learner_id=learner_id,
        workspace_id=workspace.id,
        task_id=None,
        mode="execute",
        idempotency_key=str(uuid.uuid4()),
        problem_id=None,
        problem_version=None,
        verdict="runtime_error",
        category="runtime_error",
        severity="error",
        score=None,
        summary=summary,
        safe_result_data='{"kind":"compiler_execute.v1"}',
        knowledge_gap_kind="runtime_error",
        owner_principal_id=owner_principal_id,
    )
    db.add(outcome)
    db.commit()


def _add_research_conversation(
    db: Session,
    *,
    topic: str = "图神经网络",
    methods: list[str] | None = None,
    data_requirements: str | None = None,
    owner_principal_id: str | None = None,
    context_provenance: dict[str, object] | None = None,
) -> ResearchConversationModel:
    conv = ResearchConversationModel(
        profile_data={
            "topic": topic,
            "methods": methods or ["GCN", "GraphSAGE"],
            "data_requirements": data_requirements or "公开分子图数据集",
        },
        messages_data=[],
        owner_principal_id=owner_principal_id,
        context_provenance=context_provenance,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


# ---------------------------------------------------------------------------
# Contract tests: Shape, empty state, parameters
# ---------------------------------------------------------------------------


class TestPortraitsOverviewContract:
    def test_empty_state_returns_200_with_clean_structure(self, client: TestClient) -> None:
        """New user zero-data returns 200 OK without errors."""
        response = client.get(f"/api/v1/portraits/overview?profile_id={PROFILE_A}")
        assert response.status_code == 200
        payload = response.json()

        assert payload["profile_id"] == PROFILE_A
        assert payload["generated_by"] == "rules"
        assert "generated_at" in payload

        learning = payload["learning"]
        assert learning["mastery"] == {
            "graded_attempts": 0,
            "strong_points": [],
            "weak_points": [],
            "insufficient_sample": True,
        }
        assert learning["review_queue"] == {
            "active_confusion_marks": 0,
            "top_surfaces": [],
        }
        assert learning["knowledge_gaps"] == []

        research = payload["research"]
        assert research["conversations"] == []

        bridges = payload["bridges"]
        assert bridges["learning_to_research"] == {
            "latest_transfer_id": None,
            "confirmed": False,
            "has_mastery_snapshot": False,
        }
        assert bridges["research_to_learning"] == {
            "pending_study_recommendations": 0,
        }

    def test_invalid_profile_id_returns_422(self, client: TestClient) -> None:
        response = client.get("/api/v1/portraits/overview?profile_id=not-a-uuid")
        assert response.status_code == 422

    def test_missing_profile_id_returns_422(self, client: TestClient) -> None:
        response = client.get("/api/v1/portraits/overview")
        assert response.status_code == 422

    def test_invalid_local_profile_id_returns_422(self, client: TestClient) -> None:
        response = client.get(
            f"/api/v1/portraits/overview?profile_id={PROFILE_A}&local_profile_id=bad-uuid"
        )
        assert response.status_code == 422

    def test_conversation_limit_boundary_validation(self, client: TestClient) -> None:
        low = client.get(
            f"/api/v1/portraits/overview?profile_id={PROFILE_A}&conversation_limit=0"
        )
        assert low.status_code == 422

        high = client.get(
            f"/api/v1/portraits/overview?profile_id={PROFILE_A}&conversation_limit=11"
        )
        assert high.status_code == 422


# ---------------------------------------------------------------------------
# Learning aggregation tests
# ---------------------------------------------------------------------------


class TestPortraitsOverviewLearningSlice:
    def test_mastery_and_strengths_weaknesses(self, client: TestClient, db: Session) -> None:
        # 3 attempts for "集合" (100% mastery -> strength)
        for _ in range(3):
            _add_quiz_attempt(db, knowledge_point="集合", score=10, max_score=10)
        # 3 attempts for "函数" (20% mastery -> weakness)
        for _ in range(3):
            _add_quiz_attempt(db, knowledge_point="函数", score=2, max_score=10)
        # 1 attempt for "概率" (insufficient sample)
        _add_quiz_attempt(db, knowledge_point="概率", score=10, max_score=10)

        response = client.get(f"/api/v1/portraits/overview?profile_id={PROFILE_A}")
        assert response.status_code == 200
        mastery = response.json()["learning"]["mastery"]

        assert mastery["graded_attempts"] == 7
        assert "集合" in mastery["strong_points"]
        assert "函数" in mastery["weak_points"]
        assert mastery["insufficient_sample"] is False

    def test_review_queue_surface_sorting(self, client: TestClient, db: Session) -> None:
        # Add 3 explain marks, 2 ppt marks, 1 quiz mark
        for idx in range(3):
            _add_confusion_mark(
                db,
                knowledge_point="集合",
                source_ref=f"explain:{idx}",
                source_type="explain",
            )
        for idx in range(2):
            _add_confusion_mark(
                db,
                knowledge_point="集合",
                source_ref=f"ppt:{idx}",
                source_type="ppt_page",
            )
        _add_confusion_mark(
            db,
            knowledge_point="集合",
            source_ref="quiz:1",
            source_type="quiz_question",
        )

        response = client.get(f"/api/v1/portraits/overview?profile_id={PROFILE_A}")
        assert response.status_code == 200
        queue = response.json()["learning"]["review_queue"]

        assert queue["active_confusion_marks"] == 6
        assert queue["top_surfaces"] == ["explain", "ppt_page", "quiz_question"]

    def test_knowledge_gaps_includes_code_fill_and_practice(
        self, client: TestClient, db: Session
    ) -> None:
        _add_quiz_attempt(db, knowledge_point="集合", score=0, max_score=10)
        _add_confusion_mark(
            db, knowledge_point="函数", source_ref="explain:函数", source_type="explain"
        )
        _add_code_fill(db, set_id="set-1", topic="动态规划")
        _add_practice_outcome(
            db,
            local_profile_id="22222222-2222-4222-8222-333333333333",
            learner_id=PROFILE_A,
            focus_label="循环调试",
        )

        response = client.get(
            f"/api/v1/portraits/overview?profile_id={PROFILE_A}"
            "&local_profile_id=22222222-2222-4222-8222-333333333333"
        )
        assert response.status_code == 200
        gaps = response.json()["learning"]["knowledge_gaps"]
        assert len(gaps) <= 8

        source_types = {item["source_type"] for item in gaps}
        assert "quiz_attempt" in source_types
        assert "confusion_mark" in source_types
        assert "code_fill_attempt" in source_types
        assert "practice_outcome" in source_types

        for item in gaps:
            assert "knowledge_point" in item
            assert "source_type" in item
            assert "summary" in item


# ---------------------------------------------------------------------------
# Research slice tests
# ---------------------------------------------------------------------------


class TestPortraitsOverviewResearchSlice:
    def test_research_conversations_with_readiness_and_bundles(
        self, client: TestClient, db: Session
    ) -> None:
        conv = _add_research_conversation(db, topic="大语言模型微调")
        # Add evidence bundle
        db.add(
            ResearchEvidenceBundleModel(
                conversation_id=conv.id,
                bundle_data={"papers": [{"title": "Paper A"}]},
            )
        )
        # Add reproduction pipeline
        db.add(
            ResearchReproductionPipelineModel(
                id=str(uuid.uuid4()),
                conversation_id=conv.id,
                pipeline_data={"tasks": [{"status": "evidence_linked"}]},
            )
        )
        # Add evaluation
        db.add(
            ResearchReproductionEvaluationModel(
                id=str(uuid.uuid4()),
                conversation_id=conv.id,
                evaluation_data={"total_score": 8, "schema_version": "v2"},
            )
        )
        db.commit()

        response = client.get(f"/api/v1/portraits/overview?profile_id={PROFILE_A}")
        assert response.status_code == 200
        convs = response.json()["research"]["conversations"]
        assert len(convs) == 1

        c = convs[0]
        assert c["conversation_id"] == conv.id
        assert c["topic"] == "大语言模型微调"
        assert c["evidence_bundle_count"] == 1
        assert c["reproduction_pipeline_status"] == "evidence_linked"
        assert c["readiness"] == "8/12"

    def test_conversation_limit_enforced(self, client: TestClient, db: Session) -> None:
        for idx in range(5):
            _add_research_conversation(db, topic=f"Topic {idx}")

        response = client.get(
            f"/api/v1/portraits/overview?profile_id={PROFILE_A}&conversation_limit=2"
        )
        assert response.status_code == 200
        convs = response.json()["research"]["conversations"]
        assert len(convs) == 2


# ---------------------------------------------------------------------------
# Bridges slice tests
# ---------------------------------------------------------------------------


class TestPortraitsOverviewBridgesSlice:
    def test_bridges_learning_to_research_and_study_recommendations(
        self, client: TestClient, db: Session
    ) -> None:
        conv = _add_research_conversation(
            db,
            topic="图神经网络",
            methods=["PyTorch", "GNN"],
            data_requirements="公开数据集",
            context_provenance={
                "learning_mastery_snapshot": {"strong": ["PyTorch"], "weak": []}
            },
        )
        transfer = ContextTransferModel(
            source_module="learning",
            source_object_type="notebook_item",
            source_object_id=str(uuid.uuid4()),
            source_scope_id="scope-1",
            target_module="research",
            topic="图神经网络",
            summary="学习摘要",
            selected_content=[],
            status="confirmed",
            confirmed_conversation_id=conv.id,
            confirmed_at=datetime.now(UTC),
        )
        db.add(transfer)
        db.commit()

        response = client.get(f"/api/v1/portraits/overview?profile_id={PROFILE_A}")
        assert response.status_code == 200
        bridges = response.json()["bridges"]

        l2r = bridges["learning_to_research"]
        assert l2r["latest_transfer_id"] == transfer.id
        assert l2r["confirmed"] is True
        assert l2r["has_mastery_snapshot"] is True

        r2l = bridges["research_to_learning"]
        assert r2l["pending_study_recommendations"] > 0


# ---------------------------------------------------------------------------
# Auth and owner isolation tests
# ---------------------------------------------------------------------------


class TestPortraitsOverviewAuthIsolation:
    def test_authenticated_user_isolation(self, client: TestClient, db: Session) -> None:
        client_a = TestClient(app)
        client_b = TestClient(app)
        headers_a = _create_user_and_login(client_a, "alice_portrait@example.com")
        headers_b = _create_user_and_login(client_b, "bob_portrait@example.com")

        # Create Alice's research conversation
        conv_res = client_a.post(
            "/api/v1/research/conversations",
            json={"initial_message": "Alice's research on Transformers"},
            headers=headers_a,
        )
        assert conv_res.status_code == 201

        # Alice checks overview
        res_a = client_a.get(
            f"/api/v1/portraits/overview?profile_id={PROFILE_A}",
            headers=headers_a,
        )
        assert res_a.status_code == 200
        assert len(res_a.json()["research"]["conversations"]) == 1

        # Bob checks overview -> sees 0 research conversations
        res_b = client_b.get(
            f"/api/v1/portraits/overview?profile_id={PROFILE_A}",
            headers=headers_b,
        )
        assert res_b.status_code == 200
        assert len(res_b.json()["research"]["conversations"]) == 0
