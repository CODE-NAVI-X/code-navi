"""Regression coverage for Issue #82 project upload and navigation APIs."""

from __future__ import annotations

import base64
import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import Base, engine  # noqa: E402
from code_navi.server import app  # noqa: E402


def _encoded(content: str) -> str:
    return base64.b64encode(content.encode("utf-8")).decode("ascii")


def _project_payload(files: list[dict[str, str]] | None = None) -> dict[str, object]:
    return {
        "name": "cnn-demo",
        "files": files
        or [
            {
                "path": "src/model.py",
                "content_base64": _encoded('''class Net:
    """Small example."""

    def forward(self, image):
        return image


def train():
    return Net()
'''),
            },
            {
                "path": "README.md",
                "content_base64": _encoded("# CNN demo\n\n```python\ntrain()\n```\n"),
            },
        ],
    }


@pytest.fixture(autouse=True)
def _fresh_tables() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def _login(client: TestClient, email: str) -> None:
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "displayName": "Project User"},
    )
    assert registered.status_code == 201, registered.text
    logged_in = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert logged_in.status_code == 200, logged_in.text


def test_upload_project_returns_tree_metrics_and_method_symbols(client: TestClient) -> None:
    response = client.post("/api/v1/practice/projects", json=_project_payload())

    assert response.status_code == 200, response.text
    project = response.json()
    assert project["name"] == "cnn-demo"
    assert project["metrics"] == {"files": 2, "bytes": 154, "lines": 14}
    python_file = next(item for item in project["files"] if item["path"] == "src/model.py")
    assert [
        (symbol["kind"], symbol["name"], symbol["line"]) for symbol in python_file["symbols"]
    ] == [
        ("class", "Net", 1),
        ("method", "Net.forward", 4),
        ("function", "train", 8),
    ]


def test_project_tree_and_file_content_roundtrip(client: TestClient) -> None:
    uploaded = client.post("/api/v1/practice/projects", json=_project_payload()).json()
    project_id = uploaded["project_id"]

    tree = client.get(f"/api/v1/practice/projects/{project_id}")
    content = client.get(f"/api/v1/practice/projects/{project_id}/files/src/model.py")

    assert tree.status_code == 200
    assert tree.json()["files"] == uploaded["files"]
    assert content.status_code == 200
    assert content.json()["path"] == "src/model.py"
    assert "def forward" in content.json()["content"]
    assert content.json()["symbols"][1]["kind"] == "method"


@pytest.mark.parametrize(
    ("files", "status_code"),
    [
        ([{"path": "script.js", "content_base64": _encoded("console.log(1)")}], 415),
        ([{"path": "data/train.py", "content_base64": _encoded("x = 1")}], 400),
        ([{"path": "../secret.py", "content_base64": _encoded("x = 1")}], 400),
        (
            [
                {"path": "main.py", "content_base64": _encoded("x = 1")},
                {"path": "main.py", "content_base64": _encoded("x = 2")},
            ],
            400,
        ),
        ([{"path": "main.py", "content_base64": "not-base64"}], 400),
        ([{"path": "dataset.py", "content_base64": _encoded("import pickle\n")}], 400),
    ],
)
def test_project_upload_rejects_invalid_files(
    client: TestClient, files: list[dict[str, str]], status_code: int
) -> None:
    response = client.post("/api/v1/practice/projects", json=_project_payload(files))

    assert response.status_code == status_code


def test_project_upload_rejects_total_size_and_file_count(client: TestClient) -> None:
    oversized = client.post(
        "/api/v1/practice/projects",
        json=_project_payload(
            [{"path": "large.py", "content_base64": _encoded("x" * (2 * 1024 * 1024 + 1))}]
        ),
    )
    too_many = client.post(
        "/api/v1/practice/projects",
        json=_project_payload(
            [
                {"path": f"module_{index}.py", "content_base64": _encoded("x = 1")}
                for index in range(51)
            ]
        ),
    )

    assert oversized.status_code == 413
    assert too_many.status_code == 422


def test_project_read_returns_404_for_missing_project_or_file(client: TestClient) -> None:
    missing = client.get("/api/v1/practice/projects/missing-project")
    uploaded = client.post("/api/v1/practice/projects", json=_project_payload()).json()
    missing_file = client.get(f"/api/v1/practice/projects/{uploaded['project_id']}/files/nope.py")

    assert missing.status_code == 404
    assert missing_file.status_code == 404


def test_project_read_is_isolated_by_authenticated_owner() -> None:
    owner = TestClient(app)
    other = TestClient(app)
    _login(owner, "project-owner@example.com")
    _login(other, "project-other@example.com")
    uploaded = owner.post("/api/v1/practice/projects", json=_project_payload())
    assert uploaded.status_code == 200, uploaded.text
    project_id = uploaded.json()["project_id"]

    assert other.get(f"/api/v1/practice/projects/{project_id}").status_code == 404
    assert (
        other.get(f"/api/v1/practice/projects/{project_id}/files/src/model.py").status_code == 404
    )


def _logic_project_payload() -> dict[str, object]:
    return _project_payload(
        [
            {
                "path": "src/logic.py",
                "content_base64": _encoded(
                    "def normalize(values):\n"
                    "    total = sum(values)\n"
                    "    if total <= 0:\n"
                    "        return [0 for _ in values]\n"
                    "    return [value / total for value in values]\n"
                ),
            }
        ]
    )


def test_project_explanation_labels_rule_claims(client: TestClient) -> None:
    project_id = client.post("/api/v1/practice/projects", json=_logic_project_payload()).json()[
        "project_id"
    ]

    response = client.post(
        f"/api/v1/practice/projects/{project_id}/explain",
        json={"path": "src/logic.py", "symbol": "normalize"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "rules"
    assert body["entries"][0]["symbol"] == "normalize"
    assert body["entries"][0]["fact"]
    assert body["entries"][0]["inference"]
    assert body["entries"][0]["to_verify"]


def test_project_code_fill_is_judgeable_without_answer_leak(client: TestClient) -> None:
    project_id = client.post("/api/v1/practice/projects", json=_logic_project_payload()).json()[
        "project_id"
    ]
    response = client.post(
        f"/api/v1/practice/projects/{project_id}/code-fill",
        json={"path": "src/logic.py", "symbol": "normalize"},
    )

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["item_kind"] == "code_fill"
    assert item["payload"]["source"] == "upload_derived"
    assert "sum(values)" not in str(item)
    assert "answer" not in str(item["payload"])

    graded = client.post(
        "/api/v1/practice/code-fill/grade",
        json={
            "set_id": response.json()["set_id"],
            "item_id": item["item_id"],
            "attempt_id": "0d75c9a8-b681-4bc0-9f5a-60541872d8dd",
            "blank_answers": [
                {"blank_id": blank["blank_id"], "value": "incorrect"}
                for blank in item["payload"]["blanks"]
            ],
        },
    )
    assert graded.status_code == 200, graded.text
    assert graded.json()["graded"] is True


def test_project_explain_and_generation_are_owner_isolated() -> None:
    owner = TestClient(app)
    other = TestClient(app)
    _login(owner, "project-ai-owner@example.com")
    _login(other, "project-ai-other@example.com")
    project_id = owner.post("/api/v1/practice/projects", json=_logic_project_payload()).json()[
        "project_id"
    ]

    assert other.post(f"/api/v1/practice/projects/{project_id}/explain", json={}).status_code == 404
    assert (
        other.post(
            f"/api/v1/practice/projects/{project_id}/code-fill",
            json={"path": "src/logic.py"},
        ).status_code
        == 404
    )
