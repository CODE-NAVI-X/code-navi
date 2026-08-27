import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.auth.rate_limiter import get_rate_limiter
from code_navi.db import Base, engine
from code_navi.server import app


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
    get_rate_limiter().reset()
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    get_rate_limiter().reset()


def _create_user_and_login(
    client: TestClient,
    email: str,
    password: str = "Password123!",
    display_name: str = "Test User",
) -> dict[str, str]:
    """Register and login a user, returning headers with CSRF and cookies."""
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "displayName": display_name},
    )
    res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert res.status_code == 200, res.text
    csrf_token = res.json()["csrfToken"]
    return {"X-CSRF-Token": csrf_token}


def test_workspaces_cross_principal_isolation() -> None:
    """User B cannot view or mutate User A's workspace or task."""
    client_a = TestClient(app)
    headers_a = _create_user_and_login(client_a, "alice_ws@example.com")

    client_b = TestClient(app)
    headers_b = _create_user_and_login(client_b, "bob_ws@example.com")

    # Alice creates a workspace
    create_res = client_a.post(
        "/api/v1/workspaces",
        json={"title": "Alice Workspace", "kind": "course"},
        headers=headers_a,
    )
    assert create_res.status_code == 201, create_res.text
    workspace_id = create_res.json()["id"]

    # Alice creates a task
    task_res = client_a.post(
        "/api/v1/tasks",
        json={"workspace_id": workspace_id, "goal": "Alice Learning Goal"},
        headers=headers_a,
    )
    assert task_res.status_code == 201, task_res.text
    task_id = task_res.json()["id"]

    # Bob attempts to get Alice's workspace -> 404
    bob_get_ws = client_b.get(f"/api/v1/workspaces/{workspace_id}", headers=headers_b)
    assert bob_get_ws.status_code == 404

    # Bob attempts to get Alice's task -> 404
    bob_get_task = client_b.get(f"/api/v1/tasks/{task_id}", headers=headers_b)
    assert bob_get_task.status_code == 404

    # Bob lists workspaces -> does not contain Alice's workspace
    bob_list_ws = client_b.get("/api/v1/workspaces", headers=headers_b)
    assert bob_list_ws.status_code == 200
    assert not any(w["id"] == workspace_id for w in bob_list_ws.json()["items"])


def test_learning_cross_principal_isolation() -> None:
    """User B cannot access User A's presentations, quizzes, or notebook items."""
    client_a = TestClient(app)
    headers_a = _create_user_and_login(client_a, "alice_learn@example.com")

    client_b = TestClient(app)
    headers_b = _create_user_and_login(client_b, "bob_learn@example.com")

    # Alice generates a quiz
    quiz_res = client_a.post(
        "/api/v1/learning/quiz/generate",
        json={"knowledge_point": "Python Async", "session_id": "alice-sess-1"},
        headers=headers_a,
    )
    assert quiz_res.status_code == 200
    quiz_id = quiz_res.json()["quiz_id"]

    # Bob attempts to export/load Alice's quiz -> 404
    bob_quiz_export = client_b.get(
        f"/api/v1/learning/quiz/export-docx?quiz_id={quiz_id}&session_id=alice-sess-1",
        headers=headers_b,
    )
    assert bob_quiz_export.status_code == 404

    # Alice creates a presentation note
    client_a.post(
        "/api/v1/learning/explain",
        json={"knowledge_point": "Binary Search", "session_id": "alice-sess-1"},
        headers=headers_a,
    )

    # Bob lists notebook items for alice-sess-1 -> empty because Bob doesn't own Alice's principal
    bob_notebook = client_b.get(
        "/api/v1/learning/notebook?session_id=alice-sess-1",
        headers=headers_b,
    )
    assert bob_notebook.status_code == 200
    assert len(bob_notebook.json()) == 0


def test_research_cross_principal_isolation() -> None:
    """User B cannot access User A's research conversations."""
    client_a = TestClient(app)
    headers_a = _create_user_and_login(client_a, "alice_research@example.com")

    client_b = TestClient(app)
    headers_b = _create_user_and_login(client_b, "bob_research@example.com")

    # Alice creates a research conversation
    conv_res = client_a.post(
        "/api/v1/research/conversations",
        json={"initial_message": "我想研究 Neural Radiance Fields"},
        headers=headers_a,
    )
    assert conv_res.status_code == 201, conv_res.text
    conversation_id = conv_res.json()["conversation_id"]

    # Bob attempts to read Alice's conversation -> 404
    bob_get_conv = client_b.get(
        f"/api/v1/research/conversations/{conversation_id}",
        headers=headers_b,
    )
    assert bob_get_conv.status_code == 404


def test_context_transfers_cross_principal_isolation() -> None:
    """User B cannot read, update, or delete User A's context transfer draft."""
    client_a = TestClient(app)
    headers_a = _create_user_and_login(client_a, "alice_transfer@example.com")

    client_b = TestClient(app)
    headers_b = _create_user_and_login(client_b, "bob_transfer@example.com")

    # Alice creates a notebook item via explain
    explain_res = client_a.post(
        "/api/v1/learning/explain",
        json={"knowledge_point": "Quick Sort", "session_id": "alice-sess-trans"},
        headers=headers_a,
    )
    assert explain_res.status_code == 200

    # Get Alice's notebook item id
    notebook_res = client_a.get(
        "/api/v1/learning/notebook?session_id=alice-sess-trans",
        headers=headers_a,
    )
    assert notebook_res.status_code == 200
    items = notebook_res.json()
    assert len(items) > 0
    note_id = items[0]["id"]

    # Alice creates a context transfer draft
    create_transfer_res = client_a.post(
        "/api/v1/context-transfers",
        json={
            "source_module": "learning",
            "source_object": {"type": "notebook_item", "id": note_id},
            "source_scope_id": "alice-sess-trans",
            "target_module": "research",
            "selected_parts": ["summary"],
        },
        headers=headers_a,
    )
    assert create_transfer_res.status_code == 201
    transfer_id = create_transfer_res.json()["id"]

    # Bob tries to access Alice's transfer -> 404
    bob_get_transfer = client_b.get(
        f"/api/v1/context-transfers/{transfer_id}?source_scope_id=alice-sess-trans",
        headers=headers_b,
    )
    assert bob_get_transfer.status_code == 404

    # Bob tries to delete Alice's transfer -> 404
    bob_del_transfer = client_b.delete(
        f"/api/v1/context-transfers/{transfer_id}?source_scope_id=alice-sess-trans",
        headers=headers_b,
    )
    assert bob_del_transfer.status_code == 404


def test_claimed_guest_session_ownership() -> None:
    """When a guest session is claimed, User A owns the guest's workspaces."""
    guest_client = TestClient(app)
    # Start guest session
    session_res = guest_client.get("/api/v1/auth/session")
    assert session_res.status_code == 200
    guest_csrf = session_res.json()["csrfToken"]
    guest_headers = {"X-CSRF-Token": guest_csrf}

    # Guest creates a workspace
    create_res = guest_client.post(
        "/api/v1/workspaces",
        json={"title": "Guest Workspace", "kind": "general"},
        headers=guest_headers,
    )
    assert create_res.status_code == 201, create_res.text
    ws_id = create_res.json()["id"]

    # Register and link the guest session to User A
    reg_res = guest_client.post(
        "/api/v1/auth/register",
        json={
            "email": "claimed_guest@example.com",
            "password": "Password123!",
            "displayName": "Guest User",
            "claimGuestData": True,
        },
        headers=guest_headers,
    )
    assert reg_res.status_code == 201, reg_res.text
    user_a_csrf = reg_res.json()["csrfToken"]
    user_a_headers = {"X-CSRF-Token": user_a_csrf}

    # User A can still access the workspace
    user_a_get_ws = guest_client.get(f"/api/v1/workspaces/{ws_id}", headers=user_a_headers)
    assert user_a_get_ws.status_code == 200
    assert user_a_get_ws.json()["id"] == ws_id

    # User B cannot access the claimed workspace
    client_b = TestClient(app)
    headers_b = _create_user_and_login(client_b, "intruder@example.com")
    bob_get_ws = client_b.get(f"/api/v1/workspaces/{ws_id}", headers=headers_b)
    assert bob_get_ws.status_code == 404
