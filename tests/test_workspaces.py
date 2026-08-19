"""Direct API checks for the Persistent Workspace Foundation."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import Base, SessionLocal, engine  # noqa: E402
from code_navi.learning.models import NotebookItemModel  # noqa: E402
from code_navi.server import app  # noqa: E402
from code_navi.workspaces.models import (  # noqa: E402
    TaskModel,
    WorkspaceActivityModel,
    WorkspaceModel,
)
from code_navi.workspaces.service import WorkspaceService  # noqa: E402


@pytest.fixture(autouse=True)
def _force_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "mock")


@pytest.fixture(autouse=True)
def _isolated_event_logs(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODE_NAVI_EVENTS_DIR", str(tmp_path_factory.mktemp("events")))


@pytest.fixture(autouse=True)
def _fresh_tables() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


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


def test_personal_workspace_is_idempotent_and_task_first_uses_it(client: TestClient) -> None:
    profile = "profile-task-first"
    first = client.post(f"/api/v1/workspaces/personal?local_profile_id={profile}")
    second = client.post(f"/api/v1/workspaces/personal?local_profile_id={profile}")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["kind"] == "personal"

    task_response = client.post(
        "/api/v1/tasks",
        json={"local_profile_id": profile, "goal": "理解 Q-learning 更新过程"},
    )

    assert task_response.status_code == 201
    assert task_response.json()["workspace_id"] == first.json()["id"]
    assert task_response.json()["title"] == "理解 Q-learning 更新过程"


def test_workspace_first_reuses_task_service_and_hides_other_profiles(client: TestClient) -> None:
    profile = "profile-workspace-first"
    created_workspace = client.post(
        "/api/v1/workspaces",
        json={
            "local_profile_id": profile,
            "title": "计算机网络课程",
            "kind": "course",
        },
    )
    workspace_id = created_workspace.json()["id"]

    task_response = client.post(
        "/api/v1/tasks",
        json={
            "local_profile_id": profile,
            "workspace_id": workspace_id,
            "goal": "比较 Reno 与 Cubic",
        },
    )

    assert created_workspace.status_code == 201
    assert task_response.status_code == 201
    assert task_response.json()["workspace_id"] == workspace_id
    assert client.get(
        f"/api/v1/workspaces/{workspace_id}?local_profile_id=other-profile"
    ).status_code == 404
    assert client.get(
        f"/api/v1/tasks/{task_response.json()['id']}?local_profile_id=other-profile"
    ).status_code == 404


def test_learning_derives_one_safe_activity_in_the_requested_task_context(
    client: TestClient,
    db: Session,
) -> None:
    profile = "profile-learning-task"
    task = client.post(
        "/api/v1/tasks",
        json={"local_profile_id": profile, "goal": "理解 TCP 慢启动"},
    ).json()

    response = client.post(
        "/api/v1/learning/explain",
        json={
            "knowledge_point": "TCP 慢启动",
            "session_id": "sess-workspace-learning",
            "local_profile_id": profile,
            "workspace_id": task["workspace_id"],
            "task_id": task["id"],
        },
    )

    assert response.status_code == 200
    notebook_id = response.json()["notebook_item_id"]
    activity = db.query(WorkspaceActivityModel).one()
    assert activity.workspace_id == task["workspace_id"]
    assert activity.task_id == task["id"]
    assert activity.source_object_id == notebook_id
    assert activity.summary == "已保存“TCP 慢启动”的知识解析。"
    assert response.json()["summary"] not in activity.summary

    timeline = client.get(
        f"/api/v1/tasks/{task['id']}/activities?local_profile_id={profile}"
    )
    assert timeline.status_code == 200
    assert timeline.json()["items"][0]["id"] == activity.id

    source = db.query(NotebookItemModel).filter_by(id=notebook_id).one()
    context = WorkspaceService().resolve_learning_context(
        local_profile_id=profile,
        workspace_id=task["workspace_id"],
        task_id=task["id"],
        db=db,
    )
    retried = WorkspaceService().record_learning_activity(
        context=context,
        notebook_item=source,
        db=db,
    )
    assert retried.id == activity.id
    assert db.query(WorkspaceActivityModel).count() == 1


def test_direct_learning_uses_personal_workspace_without_a_task(
    client: TestClient,
    db: Session,
) -> None:
    profile = "profile-direct-learning"
    response = client.post(
        "/api/v1/learning/explain",
        json={
            "knowledge_point": "Dijkstra 算法",
            "session_id": "sess-direct-learning",
            "local_profile_id": profile,
        },
    )

    assert response.status_code == 200
    activity = db.query(WorkspaceActivityModel).one()
    workspace = db.query(WorkspaceModel).filter_by(id=activity.workspace_id).one()
    assert activity.task_id is None
    assert workspace.kind == "personal"
    assert workspace.owner_scope_id == profile


def test_learning_rejects_mismatched_context_before_saving_notebook(
    client: TestClient,
    db: Session,
) -> None:
    profile = "profile-mismatched-context"
    first_task = client.post(
        "/api/v1/tasks",
        json={"local_profile_id": profile, "goal": "第一个目标"},
    ).json()
    second_workspace = client.post(
        "/api/v1/workspaces",
        json={"local_profile_id": profile, "title": "第二工作区"},
    ).json()

    response = client.post(
        "/api/v1/learning/explain",
        json={
            "knowledge_point": "互斥上下文",
            "local_profile_id": profile,
            "workspace_id": second_workspace["id"],
            "task_id": first_task["id"],
        },
    )

    assert response.status_code == 409
    assert db.query(NotebookItemModel).count() == 0
    assert db.query(WorkspaceActivityModel).count() == 0
    assert db.query(TaskModel).count() == 1


def test_learning_context_resources_outside_the_profile_return_404_before_persisting(
    client: TestClient,
    db: Session,
) -> None:
    owner_profile = "profile-context-owner"
    other_profile = "profile-context-other"
    owner_task = client.post(
        "/api/v1/tasks",
        json={"local_profile_id": owner_profile, "goal": "仅属于原资料的任务"},
    ).json()
    owner_workspace = client.post(
        "/api/v1/workspaces",
        json={"local_profile_id": owner_profile, "title": "仅属于原资料的工作区"},
    ).json()

    for context in (
        {"task_id": "unknown-task"},
        {"task_id": owner_task["id"]},
        {"workspace_id": owner_workspace["id"]},
    ):
        response = client.post(
            "/api/v1/learning/explain",
            json={
                "knowledge_point": "不得持久化的上下文",
                "local_profile_id": other_profile,
                **context,
            },
        )
        assert response.status_code == 404

    assert db.query(NotebookItemModel).count() == 0
    assert db.query(WorkspaceActivityModel).count() == 0


def test_workspace_task_and_activity_lists_are_profile_scoped_and_bounded(
    client: TestClient,
) -> None:
    first_profile = "profile-list-first"
    second_profile = "profile-list-second"
    first_task = client.post(
        "/api/v1/tasks",
        json={"local_profile_id": first_profile, "goal": "第一个资料的个人任务"},
    ).json()
    first_workspace = client.post(
        "/api/v1/workspaces",
        json={"local_profile_id": first_profile, "title": "第一个资料的课程"},
    ).json()
    first_workspace_task = client.post(
        "/api/v1/tasks",
        json={
            "local_profile_id": first_profile,
            "workspace_id": first_workspace["id"],
            "goal": "第一个资料的课程任务",
        },
    ).json()
    second_task = client.post(
        "/api/v1/tasks",
        json={"local_profile_id": second_profile, "goal": "第二个资料的个人任务"},
    ).json()

    for topic, session_id in (("TCP", "sess-list-first-1"), ("UDP", "sess-list-first-2")):
        response = client.post(
            "/api/v1/learning/explain",
            json={
                "knowledge_point": topic,
                "session_id": session_id,
                "local_profile_id": first_profile,
                "workspace_id": first_task["workspace_id"],
                "task_id": first_task["id"],
            },
        )
        assert response.status_code == 200
    second_learning = client.post(
        "/api/v1/learning/explain",
        json={
            "knowledge_point": "DNS",
            "session_id": "sess-list-second",
            "local_profile_id": second_profile,
            "workspace_id": second_task["workspace_id"],
            "task_id": second_task["id"],
        },
    )
    assert second_learning.status_code == 200

    first_workspaces = client.get(
        f"/api/v1/workspaces?local_profile_id={first_profile}"
    ).json()["items"]
    second_workspaces = client.get(
        f"/api/v1/workspaces?local_profile_id={second_profile}"
    ).json()["items"]
    assert {workspace["id"] for workspace in first_workspaces} == {
        first_task["workspace_id"],
        first_workspace["id"],
    }
    assert {workspace["id"] for workspace in second_workspaces} == {second_task["workspace_id"]}
    assert len(
        client.get(f"/api/v1/workspaces?local_profile_id={first_profile}&limit=1").json()[
            "items"
        ]
    ) == 1

    first_recent_tasks = client.get(
        f"/api/v1/tasks/recent?local_profile_id={first_profile}"
    ).json()["items"]
    second_recent_tasks = client.get(
        f"/api/v1/tasks/recent?local_profile_id={second_profile}"
    ).json()["items"]
    assert {task["id"] for task in first_recent_tasks} == {
        first_task["id"],
        first_workspace_task["id"],
    }
    assert {task["id"] for task in second_recent_tasks} == {second_task["id"]}
    assert len(
        client.get(f"/api/v1/tasks/recent?local_profile_id={first_profile}&limit=1").json()[
            "items"
        ]
    ) == 1

    first_activities = client.get(
        f"/api/v1/tasks/{first_task['id']}/activities?local_profile_id={first_profile}"
    ).json()["items"]
    second_activities = client.get(
        f"/api/v1/tasks/{second_task['id']}/activities?local_profile_id={second_profile}"
    ).json()["items"]
    assert len(first_activities) == 2
    assert len(second_activities) == 1
    assert len(
        client.get(
            f"/api/v1/tasks/{first_task['id']}/activities?local_profile_id={first_profile}&limit=1"
        ).json()["items"]
    ) == 1

    assert client.get(
        f"/api/v1/workspaces?local_profile_id={first_profile}&limit=51"
    ).status_code == 422
    assert client.get(
        f"/api/v1/workspaces?local_profile_id={first_profile}&offset=-1"
    ).status_code == 422
    assert client.get(
        f"/api/v1/workspaces/{first_workspace['id']}/tasks?local_profile_id={first_profile}&limit=51"
    ).status_code == 422
    assert client.get(
        f"/api/v1/workspaces/{first_workspace['id']}/tasks?local_profile_id={first_profile}&offset=-1"
    ).status_code == 422
    assert client.get(
        f"/api/v1/tasks/{first_task['id']}/activities?local_profile_id={first_profile}&limit=51"
    ).status_code == 422
    assert client.get(
        f"/api/v1/tasks/{first_task['id']}/activities?local_profile_id={first_profile}&offset=-1"
    ).status_code == 422
