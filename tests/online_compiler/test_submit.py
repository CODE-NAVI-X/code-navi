from __future__ import annotations

from code_navi.online_compiler.ai_evaluation import AiTutor
from code_navi.online_compiler.application import CompilerApplication
from code_navi.online_compiler.config import Settings
from code_navi.online_compiler.piston import ExecutionLimits, ExecutionResult, RuntimeInfo


class FakeRunner:
    def __init__(self) -> None:
        self.runtime = RuntimeInfo("python", "3.12.0")
        self.calls: list[str] = []

    def list_runtimes(self) -> tuple[RuntimeInfo, ...]:
        return (self.runtime,)

    def execute_python(
        self, source: str, stdin: str, *, version: str, limits: ExecutionLimits
    ) -> ExecutionResult:
        self.calls.append(stdin)
        outputs = {
            "level\n": "YES\n",
            "python\n": "NO\n",
            "secret\n": "wrong\n",
        }
        return ExecutionResult(
            outcome="success",
            stdout=outputs.get(stdin, "wrong\n"),
            stderr="",
            exit_code=0,
            signal=None,
            status=None,
            wall_time_ms=1,
            cpu_time_ms=1,
            memory_bytes=1,
            runtime=self.runtime,
        )


class FakeTutor(AiTutor):
    def __init__(self) -> None:
        self.context: dict[str, object] | None = None

    def chat(self, message, context, history, learner_id):
        self.context = context
        return {"reply": "先检查输入和输出的对应关系。", "strategy": "hint", "blocked": False}


def test_submit_runs_server_owned_hidden_tests_and_redacts_hidden_data() -> None:
    runner = FakeRunner()
    app = CompilerApplication(runner, Settings())

    response = app.submit({"problemId": "palindrome", "problemVersion": 1, "source": "print('x')"})

    assert response.status_code == 200
    assert response.body["verdict"] == "wrong_answer"
    assert response.body["score"] == 50.0
    hidden = [item for item in response.body["testResults"] if item["hidden"]]
    assert hidden
    assert all("testId" not in item for item in hidden)
    assert all("stdout" not in item and "stderr" not in item for item in hidden)
    assert "secret\n" not in str(response.body)


def test_guidance_context_contains_public_tests_but_not_hidden_tests() -> None:
    runner = FakeRunner()
    tutor = FakeTutor()
    app = CompilerApplication(runner, Settings(), tutor=tutor, ai_status="ready")
    submitted = app.submit({"problemId": "palindrome", "source": "print('x')"})

    guidance = app.guidance(
        {
            "submissionId": submitted.body["submissionId"],
            "message": "为什么没有通过？",
        }
    )

    assert guidance.status_code == 200
    assert tutor.context is not None
    assert len(tutor.context["publicTests"]) == 2
    assert "secret" not in str(tutor.context)
