from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import Base, SessionLocal, engine  # noqa: E402
from code_navi.online_compiler.application import CompilerApplication
from code_navi.online_compiler.config import Settings
from code_navi.online_compiler.models import PracticeOutcomeModel
from code_navi.online_compiler.piston import ExecutionLimits, ExecutionResult, RuntimeInfo
from code_navi.online_compiler.practice_integration import PracticeIntegrationService
from code_navi.online_compiler.router import get_compiler_application
from code_navi.server import app
from code_navi.workspaces.models import WorkspaceActivityModel, WorkspaceModel

LEARNER_ID = "fd5f93a4-36c9-4f8d-9a73-71af013a4368"
ATTEMPT_ID = "5f2b51c7-aad9-4dd0-a3d9-173d378591ba"


class FakePistonGateway:
    def __init__(self, *, outcome: str = "success") -> None:
        self.runtime = RuntimeInfo("python", "3.12.0", ("py",))
        self.outcome = outcome
        self.calls: list[tuple[str, str, str, ExecutionLimits]] = []

    def list_runtimes(self) -> tuple[RuntimeInfo, ...]:
        return (self.runtime,)

    def execute_python(
        self,
        source: str,
        stdin: str,
        *,
        version: str,
        limits: ExecutionLimits,
    ) -> ExecutionResult:
        self.calls.append((source, stdin, version, limits))
        failing = self.outcome not in {"success", "system_error"}
        return ExecutionResult(
            outcome=self.outcome,
            stdout="hello\n",
            stderr="RuntimeError: boom\n" if failing else "",
            exit_code=1 if failing else 0,
            signal=None,
            status="XX" if self.outcome == "system_error" else None,
            wall_time_ms=12,
            cpu_time_ms=8,
            memory_bytes=1_024,
            runtime=self.runtime,
        )


@pytest.fixture(autouse=True)
def _fresh_tables() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_compiler_api_execute_uses_main_fastapi_router() -> None:
    gateway = FakePistonGateway()
    compiler = CompilerApplication(gateway, Settings())
    app.dependency_overrides[get_compiler_application] = lambda: compiler

    try:
        with TestClient(app) as client:
            runtime = client.get("/api/v1/compiler/runtime")
            executed = client.post(
                "/api/v1/compiler/execute",
                json={"source": "print('hello')"},
            )
    finally:
        app.dependency_overrides.pop(get_compiler_application, None)

    assert runtime.status_code == 200
    assert runtime.json()["ready"] is True
    assert runtime.json()["language"] == "Python"
    assert runtime.json()["version"] == "3.12.0"
    assert runtime.json()["limits"] == {
        "wallTimeMs": 2_000,
        "memoryBytes": 134_217_728,
        "sourceBytes": 65_536,
    }
    assert executed.status_code == 200
    assert executed.json()["outcome"] == "success"
    assert gateway.calls[0][0] == "print('hello')"


def test_compiler_api_rejects_invalid_payload_without_gateway_call() -> None:
    gateway = FakePistonGateway()
    compiler = CompilerApplication(gateway, Settings())
    app.dependency_overrides[get_compiler_application] = lambda: compiler

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/compiler/execute",
                json={"language": "javascript", "source": "console.log(1)"},
            )
    finally:
        app.dependency_overrides.pop(get_compiler_application, None)

    assert response.status_code == 400
    assert "Python" in response.json()["error"]
    assert gateway.calls == []


def test_practice_launch_execute_persists_safe_outcome_and_workspace_activity() -> None:
    gateway = FakePistonGateway(outcome="runtime_error")
    compiler = CompilerApplication(gateway, Settings())
    app.dependency_overrides[get_compiler_application] = lambda: compiler
    source = "print(input())\nraise RuntimeError('boom')"
    stdin = "private stdin\n"

    try:
        with TestClient(app) as client:
            launch = client.post(
                "/api/v1/compiler/launches",
                json={
                    "localProfileId": "profile-practice-default",
                    "learnerId": LEARNER_ID,
                    "focus": {"type": "topic", "label": "循环调试"},
                },
            )
            executed = client.post(
                "/api/v1/compiler/execute",
                json={
                    "language": "python",
                    "source": source,
                    "stdin": stdin,
                    "launchId": launch.json()["launchId"],
                    "learnerId": LEARNER_ID,
                    "attemptId": ATTEMPT_ID,
                    "enableAi": False,
                },
            )
            timeline = client.get(
                "/api/v1/workspaces/"
                f"{launch.json()['workspaceId']}/activities?local_profile_id=profile-practice-default"
            )
            restored = client.get(
                "/api/v1/compiler/outcomes/"
                f"{executed.json()['practiceOutcome']['outcomeId']}"
                "?localProfileId=profile-practice-default"
            )
    finally:
        app.dependency_overrides.pop(get_compiler_application, None)

    assert launch.status_code == 201
    assert launch.json()["taskId"] is None
    assert executed.status_code == 200
    assert executed.json()["practiceOutcome"]["category"] == "runtime_error"
    assert executed.json()["practiceOutcome"]["severity"] == "error"
    assert executed.json()["practiceOutcome"]["verdict"] == "runtime_error"
    assert executed.json()["practiceOutcome"]["knowledgeGapKind"] == "runtime_error"
    assert timeline.status_code == 200
    assert timeline.json()["items"][0]["capability"] == "practice"
    assert timeline.json()["items"][0]["source_object_id"] == executed.json()["practiceOutcome"][
        "outcomeId"
    ]
    assert restored.status_code == 200
    assert restored.json()["safeResult"]["kind"] == "compiler_execute.v1"
    assert source not in restored.text
    assert stdin.strip() not in restored.text

    db = SessionLocal()
    try:
        outcome = db.query(PracticeOutcomeModel).one()
        activity = db.query(WorkspaceActivityModel).one()
        workspace = db.query(WorkspaceModel).filter_by(id=launch.json()["workspaceId"]).one()
    finally:
        db.close()

    assert outcome.task_id is None
    assert outcome.knowledge_gap_kind == "runtime_error"
    assert outcome.safe_result_data
    assert source not in outcome.safe_result_data
    assert stdin.strip() not in outcome.safe_result_data
    assert "stdout" not in outcome.safe_result_data
    assert activity.source_object_id == outcome.id
    assert workspace.kind == "personal"


def test_execute_without_launch_stays_compatible_and_creates_no_activity() -> None:
    gateway = FakePistonGateway()
    compiler = CompilerApplication(gateway, Settings())
    app.dependency_overrides[get_compiler_application] = lambda: compiler

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/compiler/execute",
                json={"language": "python", "source": "print('hello')"},
            )
    finally:
        app.dependency_overrides.pop(get_compiler_application, None)

    assert response.status_code == 200
    assert "practiceOutcome" not in response.json()

    db = SessionLocal()
    try:
        assert db.query(PracticeOutcomeModel).count() == 0
        assert db.query(WorkspaceActivityModel).count() == 0
    finally:
        db.close()


@pytest.mark.parametrize(
    ("endpoint", "launch_mode", "payload"),
    (
        (
            "/api/v1/compiler/execute",
            "free_run",
            {"language": "python", "source": "print('hello')"},
        ),
        (
            "/api/v1/compiler/execute",
            "free_run",
            {"language": "python", "source": "print('hello')", "attemptId": "not-a-uuid"},
        ),
        (
            "/api/v1/compiler/submit",
            "problem_submit",
            {"problemId": "palindrome", "problemVersion": 1, "source": "print('x')"},
        ),
        (
            "/api/v1/compiler/submit",
            "problem_submit",
            {
                "problemId": "palindrome",
                "problemVersion": 1,
                "source": "print('x')",
                "attemptId": "not-a-uuid",
            },
        ),
    ),
)
def test_launch_requests_require_valid_attempt_id_before_execution(
    endpoint: str,
    launch_mode: str,
    payload: dict[str, object],
) -> None:
    gateway = FakePistonGateway()
    compiler = CompilerApplication(gateway, Settings())
    app.dependency_overrides[get_compiler_application] = lambda: compiler

    try:
        with TestClient(app) as client:
            launch = client.post(
                "/api/v1/compiler/launches",
                json={
                    "localProfileId": "profile-attempt-required",
                    "learnerId": LEARNER_ID,
                    "mode": launch_mode,
                },
            ).json()
            response = client.post(
                endpoint,
                json={**payload, "launchId": launch["launchId"], "learnerId": LEARNER_ID},
            )
    finally:
        app.dependency_overrides.pop(get_compiler_application, None)

    assert response.status_code == 400
    assert gateway.calls == []

    db = SessionLocal()
    try:
        assert db.query(PracticeOutcomeModel).count() == 0
        assert db.query(WorkspaceActivityModel).count() == 0
    finally:
        db.close()


def test_launch_rejects_cross_owner_workspace_before_execution() -> None:
    gateway = FakePistonGateway()
    compiler = CompilerApplication(gateway, Settings())
    app.dependency_overrides[get_compiler_application] = lambda: compiler

    try:
        with TestClient(app) as client:
            workspace = client.post(
                "/api/v1/workspaces",
                json={"local_profile_id": "owner-profile", "title": "Owner"},
            ).json()
            launch = client.post(
                "/api/v1/compiler/launches",
                json={
                    "localProfileId": "other-profile",
                    "learnerId": LEARNER_ID,
                    "workspaceId": workspace["id"],
                },
            )
    finally:
        app.dependency_overrides.pop(get_compiler_application, None)

    assert launch.status_code == 404
    assert gateway.calls == []


@pytest.mark.parametrize(
    ("endpoint", "launch_mode", "payload"),
    (
        (
            "/api/v1/compiler/execute",
            "problem_submit",
            {"language": "python", "source": "print('hello')", "attemptId": ATTEMPT_ID},
        ),
        (
            "/api/v1/compiler/submit",
            "free_run",
            {
                "problemId": "palindrome",
                "problemVersion": 1,
                "source": "print('x')",
                "attemptId": ATTEMPT_ID,
            },
        ),
    ),
)
def test_launch_mode_must_match_compiler_action_before_execution(
    endpoint: str,
    launch_mode: str,
    payload: dict[str, object],
) -> None:
    gateway = FakePistonGateway()
    compiler = CompilerApplication(gateway, Settings())
    app.dependency_overrides[get_compiler_application] = lambda: compiler

    try:
        with TestClient(app) as client:
            launch = client.post(
                "/api/v1/compiler/launches",
                json={
                    "localProfileId": "profile-mode-check",
                    "learnerId": LEARNER_ID,
                    "mode": launch_mode,
                },
            ).json()
            response = client.post(
                endpoint,
                json={**payload, "launchId": launch["launchId"], "learnerId": LEARNER_ID},
            )
    finally:
        app.dependency_overrides.pop(get_compiler_application, None)

    assert response.status_code == 400
    assert gateway.calls == []

    db = SessionLocal()
    try:
        assert db.query(PracticeOutcomeModel).count() == 0
        assert db.query(WorkspaceActivityModel).count() == 0
    finally:
        db.close()


def test_system_error_execute_does_not_persist_practice_outcome() -> None:
    gateway = FakePistonGateway(outcome="system_error")
    compiler = CompilerApplication(gateway, Settings())
    app.dependency_overrides[get_compiler_application] = lambda: compiler

    try:
        with TestClient(app) as client:
            launch = client.post(
                "/api/v1/compiler/launches",
                json={"localProfileId": "profile-system-error", "learnerId": LEARNER_ID},
            )
            response = client.post(
                "/api/v1/compiler/execute",
                json={
                    "language": "python",
                    "source": "print('hello')",
                    "launchId": launch.json()["launchId"],
                    "learnerId": LEARNER_ID,
                    "attemptId": ATTEMPT_ID,
                },
            )
    finally:
        app.dependency_overrides.pop(get_compiler_application, None)

    assert response.status_code == 200
    assert response.json()["assessment"]["category"] == "system_error"
    assert "practiceOutcome" not in response.json()

    db = SessionLocal()
    try:
        assert db.query(PracticeOutcomeModel).count() == 0
        assert db.query(WorkspaceActivityModel).count() == 0
    finally:
        db.close()


def test_submit_with_launch_persists_safe_judgement_without_hidden_data() -> None:
    gateway = FakePistonGateway()
    compiler = CompilerApplication(gateway, Settings())
    app.dependency_overrides[get_compiler_application] = lambda: compiler

    try:
        with TestClient(app) as client:
            launch = client.post(
                "/api/v1/compiler/launches",
                json={
                    "localProfileId": "profile-submit",
                    "learnerId": LEARNER_ID,
                    "mode": "problem_submit",
                },
            )
            submitted = client.post(
                "/api/v1/compiler/submit",
                json={
                    "problemId": "palindrome",
                    "problemVersion": 1,
                    "source": "print('x')",
                    "launchId": launch.json()["launchId"],
                    "learnerId": LEARNER_ID,
                    "attemptId": ATTEMPT_ID,
                },
            )
    finally:
        app.dependency_overrides.pop(get_compiler_application, None)

    assert submitted.status_code == 200
    assert submitted.json()["verdict"] == "wrong_answer"
    assert submitted.json()["practiceOutcome"]["category"] == "wrong_answer"
    assert submitted.json()["practiceOutcome"]["severity"] == "error"
    assert submitted.json()["practiceOutcome"]["verdict"] == "wrong_answer"
    assert submitted.json()["practiceOutcome"]["knowledgeGapKind"] == "wrong_answer"

    db = SessionLocal()
    try:
        outcome = db.query(PracticeOutcomeModel).one()
        activity = db.query(WorkspaceActivityModel).one()
    finally:
        db.close()

    assert outcome.mode == "submit"
    assert outcome.problem_id == "palindrome"
    assert outcome.problem_version == "1"
    assert outcome.knowledge_gap_kind == "wrong_answer"
    assert "stdout" not in outcome.safe_result_data
    assert "stderr" not in outcome.safe_result_data
    assert "testId" not in outcome.safe_result_data
    assert "level" not in outcome.safe_result_data
    assert activity.source_object_id == outcome.id


def test_submit_compile_error_forms_syntax_knowledge_gap() -> None:
    gateway = FakePistonGateway(outcome="compile_error")
    compiler = CompilerApplication(gateway, Settings())
    app.dependency_overrides[get_compiler_application] = lambda: compiler

    try:
        with TestClient(app) as client:
            launch = client.post(
                "/api/v1/compiler/launches",
                json={
                    "localProfileId": "profile-submit-compile-error",
                    "learnerId": LEARNER_ID,
                    "mode": "problem_submit",
                },
            )
            submitted = client.post(
                "/api/v1/compiler/submit",
                json={
                    "problemId": "palindrome",
                    "problemVersion": 1,
                    "source": "print('x'",
                    "launchId": launch.json()["launchId"],
                    "learnerId": LEARNER_ID,
                    "attemptId": ATTEMPT_ID,
                },
            )
    finally:
        app.dependency_overrides.pop(get_compiler_application, None)

    assert submitted.status_code == 200
    assert submitted.json()["verdict"] == "compile_error"
    assert submitted.json()["practiceOutcome"]["category"] == "compile_error"
    assert submitted.json()["practiceOutcome"]["knowledgeGapKind"] == "syntax_error"

    db = SessionLocal()
    try:
        outcome = db.query(PracticeOutcomeModel).one()
    finally:
        db.close()

    assert outcome.knowledge_gap_kind == "syntax_error"


def test_attempt_id_deduplicates_outcome_without_treating_launch_as_attempt_key() -> None:
    gateway = FakePistonGateway(outcome="runtime_error")
    compiler = CompilerApplication(gateway, Settings())
    app.dependency_overrides[get_compiler_application] = lambda: compiler

    try:
        with TestClient(app) as client:
            launch = client.post(
                "/api/v1/compiler/launches",
                json={"localProfileId": "profile-idem", "learnerId": LEARNER_ID},
            ).json()
            payload = {
                "language": "python",
                "source": "raise RuntimeError('boom')",
                "launchId": launch["launchId"],
                "learnerId": LEARNER_ID,
                "attemptId": ATTEMPT_ID,
            }
            first = client.post("/api/v1/compiler/execute", json=payload)
            second = client.post("/api/v1/compiler/execute", json=payload)
            third = client.post(
                "/api/v1/compiler/execute",
                json={**payload, "attemptId": "dbd7d563-4162-44f8-ae62-6d40908be7ea"},
            )
    finally:
        app.dependency_overrides.pop(get_compiler_application, None)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200
    assert first.json()["practiceOutcome"]["outcomeId"] == second.json()["practiceOutcome"][
        "outcomeId"
    ]
    assert first.json()["practiceOutcome"]["outcomeId"] != third.json()["practiceOutcome"][
        "outcomeId"
    ]

    db = SessionLocal()
    try:
        assert db.query(PracticeOutcomeModel).count() == 2
        assert db.query(WorkspaceActivityModel).count() == 2
    finally:
        db.close()


def test_activity_integrity_error_without_existing_source_activity_rolls_back_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PracticeIntegrationService()
    db = SessionLocal()
    try:
        launch = service.create_launch(
            {"localProfileId": "profile-activity-error", "learnerId": LEARNER_ID},
            db,
        )
        flush_count = 0
        original_flush = db.flush

        def fail_activity_flush(*args, **kwargs):
            nonlocal flush_count
            flush_count += 1
            if flush_count == 2:
                raise IntegrityError("INSERT INTO workspace_activities", {}, Exception("boom"))
            return original_flush(*args, **kwargs)

        monkeypatch.setattr(db, "flush", fail_activity_flush)

        with pytest.raises(IntegrityError):
            service.record_execute_outcome(
                launch=launch,
                response_body={
                    "outcome": "success",
                    "runtime": {"language": "python", "version": "3.12.0"},
                    "metrics": {"wallTimeMs": 1, "cpuTimeMs": 1, "memoryBytes": 1},
                    "assessment": {
                        "category": "success",
                        "severity": "success",
                        "title": "运行成功",
                        "summary": "程序正常结束。",
                    },
                },
                request_payload={"attemptId": ATTEMPT_ID},
                db=db,
            )
        db.rollback()
        assert db.query(PracticeOutcomeModel).count() == 0
        assert db.query(WorkspaceActivityModel).count() == 0
    finally:
        db.close()


def test_compiler_api_analyzes_uploaded_problem_text() -> None:
    compiler = CompilerApplication(FakePistonGateway(), Settings())
    app.dependency_overrides[get_compiler_application] = lambda: compiler

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/compiler/problem-imports/analyze",
                json={
                    "text": (
                        "题目：字符串回文判断\n"
                        "描述：判断字符串是否为回文。\n"
                        "输入：一行字符串\n"
                        "输出：YES 或 NO"
                    )
                },
            )
    finally:
        app.dependency_overrides.pop(get_compiler_application, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "deterministic_rule"
    assert payload["problems"][0]["title"] == "字符串回文判断"
    assert "字符串" in payload["problems"][0]["tags"]


def test_compiler_api_generates_practice_set() -> None:
    compiler = CompilerApplication(FakePistonGateway(), Settings())
    app.dependency_overrides[get_compiler_application] = lambda: compiler

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/compiler/problem-sets/generate",
                json={"prompt": "练习循环和列表", "targetCount": 2},
            )
    finally:
        app.dependency_overrides.pop(get_compiler_application, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "deterministic_rule"
    assert len(payload["orderedProblems"]) == 2
    assert payload["orderedProblems"][0]["source"] == "built_in"
