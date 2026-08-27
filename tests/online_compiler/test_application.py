from __future__ import annotations

import base64
import io
from uuid import UUID

from docx import Document

from code_navi.online_compiler.ai_evaluation import AiEvaluator, ProblemOrganizer
from code_navi.online_compiler.application import (
    MAX_UPLOADED_PROBLEM_TEXT_BYTES,
    CompilerApplication,
)
from code_navi.online_compiler.config import Settings
from code_navi.online_compiler.evaluation import AiFeedback, QualityRubric, RuleAssessment
from code_navi.online_compiler.learning_records import LearningRecordStore
from code_navi.online_compiler.piston import ExecutionLimits, ExecutionResult, RuntimeInfo
from code_navi.online_compiler.problem_imports import ImportedProblem


class FakePistonGateway:
    def __init__(self) -> None:
        self.runtime = RuntimeInfo("python", "3.12.0", ("py",))
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
        return ExecutionResult(
            outcome="success",
            stdout="hello\n",
            stderr="",
            exit_code=0,
            signal=None,
            status=None,
            wall_time_ms=12,
            cpu_time_ms=8,
            memory_bytes=1_024,
            runtime=self.runtime,
        )


class OutcomePistonGateway(FakePistonGateway):
    def __init__(self, outcome: str) -> None:
        super().__init__()
        self.outcome = outcome

    def execute_python(
        self,
        source: str,
        stdin: str,
        *,
        version: str,
        limits: ExecutionLimits,
    ) -> ExecutionResult:
        result = super().execute_python(source, stdin, version=version, limits=limits)
        return replace(result, outcome=self.outcome)


class UnavailablePistonGateway(FakePistonGateway):
    def list_runtimes(self) -> tuple[RuntimeInfo, ...]:
        raise PistonUnavailableError("Piston is unavailable")

    def execute_python(
        self,
        source: str,
        stdin: str,
        *,
        version: str,
        limits: ExecutionLimits,
    ) -> ExecutionResult:
        raise PistonUnavailableError("Piston is unavailable")


class FakeAiEvaluator(AiEvaluator):
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(
        self,
        source: str,
        result: ExecutionResult,
        assessment: RuleAssessment,
        learner_id: str | None,
    ) -> AiFeedback:
        self.calls += 1
        assert source
        assert result.outcome == assessment.category == "success"
        return AiFeedback("命名清晰。", ("增加边界用例",), QualityRubric(90, 80, 70))


class FakeProblemOrganizer(ProblemOrganizer):
    def organize(
        self, problems: list[ImportedProblem], learner_id: str | None = None
    ) -> tuple[list[ImportedProblem], list[str]]:
        assert learner_id == "learner-1"
        return list(reversed(problems)), ["AI 仅调整了练习顺序。"]


def _base64_bytes(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _docx_bytes(lines: list[str]) -> bytes:
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _minimal_pdf_bytes(text_lines: list[str]) -> bytes:
    escaped = [
        line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        for line in text_lines
    ]
    stream = (
        "BT /F1 12 Tf 72 720 Td "
        + " Tj T* ".join(f"({line})" for line in escaped)
        + " Tj ET"
    ).encode("ascii")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        (
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
        ),
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        (
            b"5 0 obj\n<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"\nendstream\nendobj\n"
        ),
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)
    xref_at = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    )
    pdf.extend(trailer.encode("ascii"))
    return bytes(pdf)


class FakePracticeSetPlanner:
    def plan_practice_set(
        self,
        request: dict[str, object],
        candidates: list[dict[str, object]],
        learner_id: str | None = None,
    ) -> dict[str, object]:
        assert request["prompt"]
        assert learner_id == "learner-1"
        return {
            "orderedProblems": [
                {
                    "id": candidates[-1]["id"],
                    "generationReason": "AI 建议先做这道题来承接学习目标。",
                }
            ],
            "rationale": "AI 按目标重新排列了练习顺序。",
            "coverage": ["AI 覆盖"],
            "warnings": ["AI 未生成隐藏测试。"],
        }


def test_runtime_status_exposes_pinned_runtime_and_limits() -> None:
    app = CompilerApplication(FakePistonGateway(), Settings())

    response = app.runtime_status()

    assert response.status_code == 200
    assert response.body["ready"] is True
    assert response.body["version"] == "3.12.0"
    assert response.body["limits"]["wallTimeMs"] == 2_000


def test_runtime_status_reports_piston_unavailable_without_student_error() -> None:
    app = CompilerApplication(UnavailablePistonGateway(), Settings())

    response = app.runtime_status()

    assert response.status_code == 503
    assert response.body == {
        "ready": False,
        "message": "执行服务暂时不可用，请稍后重试。",
    }


def test_execute_defaults_to_python_when_language_is_missing() -> None:
    gateway = FakePistonGateway()
    app = CompilerApplication(gateway, Settings())

    response = app.execute({"source": "print('hello')"})

    assert response.status_code == 200
    assert response.body["outcome"] == "success"
    assert gateway.calls[0][2] == "3.12.0"


def test_execute_rejects_unsupported_language_before_gateway_call() -> None:
    gateway = FakePistonGateway()
    app = CompilerApplication(gateway, Settings())

    response = app.execute({"language": "javascript", "source": "console.log(1)"})

    assert response.status_code == 400
    assert "只支持 Python" in response.body["error"]
    assert gateway.calls == []


def test_execute_rejects_source_over_server_limit() -> None:
    gateway = FakePistonGateway()
    app = CompilerApplication(gateway, Settings(max_source_bytes=8))

    response = app.execute({"language": "python", "source": "print('too long')"})

    assert response.status_code == 400
    assert "不能超过" in response.body["error"]
    assert gateway.calls == []


def test_execute_passes_valid_source_with_server_owned_limits() -> None:
    gateway = FakePistonGateway()
    app = CompilerApplication(gateway, Settings())

    response = app.execute(
        {
            "language": "python",
            "source": "print(input())",
            "stdin": "hello\n",
            "runtime": "python:2.7.18",
            "command": "unsafe-command",
            "args": ["--unsafe"],
            "limits": {"wallTimeMs": 1},
        }
    )

    assert response.status_code == 200
    assert response.body["outcome"] == "success"
    assert response.body["stdout"] == "hello\n"
    source, stdin, version, limits = gateway.calls[0]
    assert source == "print(input())"
    assert stdin == "hello\n"
    assert version == "3.12.0"
    assert limits.wall_time_ms == 2_000
    assert limits.memory_bytes == 128 * 1024 * 1024


@pytest.mark.parametrize(
    ("outcome", "category"),
    [
        ("success", "success"),
        ("compile_error", "syntax_error"),
        ("runtime_error", "runtime_error"),
        ("time_limit", "time_limit"),
        ("output_limit", "output_limit"),
        ("system_error", "system_error"),
    ],
)
def test_python_execution_contract_preserves_outcome_fields_and_classification(
    outcome: str, category: str
) -> None:
    app = CompilerApplication(OutcomePistonGateway(outcome), Settings())

    response = app.execute({"language": "python", "source": "print('hello')"})

    assert response.status_code == 200
    assert response.body["outcome"] == outcome
    assert response.body["assessment"]["category"] == category
    assert set(response.body) == {
        "outcome",
        "stdout",
        "stderr",
        "exitCode",
        "signal",
        "status",
        "metrics",
        "runtime",
        "assessment",
        "ai",
        "record",
        "serviceTiming",
    }


def test_execute_reports_piston_unavailable_as_service_error() -> None:
    app = CompilerApplication(UnavailablePistonGateway(), Settings())

    response = app.execute({"language": "python", "source": "print('hello')"})

    assert response.status_code == 503
    assert response.body == {
        "error": "执行服务暂时不可用，请确认 Piston 与 Python 运行时已经启动。"
    }


def test_execute_adds_rule_assessment_without_claiming_correctness() -> None:
    app = CompilerApplication(FakePistonGateway(), Settings())

    response = app.execute({"language": "python", "source": "print('hello')"})

    assert response.body["assessment"]["category"] == "success"
    assert "尚未使用题目测试用例" in response.body["assessment"]["summary"]
    assert response.body["ai"]["status"] == "disabled"


def test_execute_and_history_use_anonymous_learner_uuid(tmp_path) -> None:
    store = LearningRecordStore(tmp_path / "records.sqlite3")
    app = CompilerApplication(FakePistonGateway(), Settings(), record_store=store)
    learner_id = "fd5f93a4-36c9-4f8d-9a73-71af013a4368"

    executed = app.execute(
        {
            "language": "python",
            "source": "print('hello')",
            "learnerId": learner_id,
        }
    )
    history = app.learning_records(learner_id)

    assert executed.body["record"]["category"] == "success"
    assert history.status_code == 200
    assert len(history.body["records"]) == 1


def test_execute_record_does_not_store_source_or_stdin(tmp_path) -> None:
    database = tmp_path / "records.sqlite3"
    store = LearningRecordStore(database)
    app = CompilerApplication(FakePistonGateway(), Settings(), record_store=store)
    source = "print('source-baseline-marker')"
    stdin = "stdin-baseline-marker\n"

    response = app.execute(
        {
            "language": "python",
            "source": source,
            "stdin": stdin,
            "learnerId": "fd5f93a4-36c9-4f8d-9a73-71af013a4368",
        }
    )

    assert response.status_code == 200
    raw_database = database.read_bytes()
    assert source.encode() not in raw_database
    assert stdin.encode() not in raw_database


def test_history_rejects_non_uuid_identity() -> None:
    app = CompilerApplication(FakePistonGateway(), Settings())

    response = app.learning_records("../other-user")

    assert response.status_code == 400
    assert "UUID" in response.body["error"]


def test_ai_feedback_runs_after_execution_and_updates_pending_record(tmp_path) -> None:
    learner_id = "fd5f93a4-36c9-4f8d-9a73-71af013a4368"
    evaluator = FakeAiEvaluator()
    app = CompilerApplication(
        FakePistonGateway(),
        Settings(),
        evaluator=evaluator,
        ai_status="ready",
        record_store=LearningRecordStore(tmp_path / "records.sqlite3"),
    )

    executed = app.execute(
        {"language": "python", "source": "print('ok')", "learnerId": learner_id}
    )

    assert executed.body["assessment"]["category"] == "success"
    assert executed.body["ai"]["status"] == "pending"
    evaluation_id = executed.body["ai"]["evaluationId"]
    assert UUID(evaluation_id).version == 4
    assert evaluator.calls == 0
    assert executed.body["record"]["aiStatus"] == "pending"

    evaluated = app.evaluate({"evaluationId": evaluation_id, "learnerId": learner_id})
    history = app.learning_records(learner_id)

    assert evaluated.status_code == 200
    assert evaluated.body["ai"]["status"] == "completed"
    assert evaluated.body["ai"]["quality"]["overall"] == 80
    assert evaluated.body["ai"]["scoreType"] == "ai_code_quality_reference"
    assert evaluator.calls == 1
    assert len(history.body["records"]) == 1
    assert history.body["records"][0]["aiStatus"] == "completed"
    assert history.body["records"][0]["referenceScore"] == 80


def test_evaluation_ticket_is_bound_to_learner() -> None:
    owner_id = "fd5f93a4-36c9-4f8d-9a73-71af013a4368"
    other_id = "4875cc24-c870-486b-9e2e-863642c2cf34"
    evaluator = FakeAiEvaluator()
    app = CompilerApplication(
        FakePistonGateway(), Settings(), evaluator=evaluator, ai_status="ready"
    )
    executed = app.execute(
        {"language": "python", "source": "print('ok')", "learnerId": owner_id}
    )

    rejected = app.evaluate(
        {"evaluationId": executed.body["ai"]["evaluationId"], "learnerId": other_id}
    )

    assert rejected.status_code == 404
    assert evaluator.calls == 0


def test_execute_can_disable_ai_for_one_run() -> None:
    evaluator = FakeAiEvaluator()
    app = CompilerApplication(
        FakePistonGateway(), Settings(), evaluator=evaluator, ai_status="ready"
    )

    response = app.execute(
        {"language": "python", "source": "print('ok')", "enableAi": False}
    )

    assert response.status_code == 200
    assert response.body["ai"]["status"] == "disabled"
    assert "evaluationId" not in response.body["ai"]
    assert evaluator.calls == 0


def test_problem_import_analyzes_and_orders_uploaded_text() -> None:
    app = CompilerApplication(FakePistonGateway(), Settings())

    response = app.analyze_problem_import(
        {
            "text": """
题目一：括号序列校验
描述：判断只包含圆括号、方括号和花括号的字符串是否正确闭合。
输入：一行括号字符串
输出：VALID 或 INVALID
样例：{[()]}

题目二：整数列表求和
描述：读取一行以空格分隔的整数，输出所有整数之和。
输入：空格分隔的整数
输出：一个整数
样例：12 8 -3 5
"""
        }
    )

    assert response.status_code == 200
    assert response.body["source"] == "deterministic_rule"
    titles = [item["title"] for item in response.body["problems"]]
    assert titles == ["整数列表求和", "括号序列校验"]
    first = response.body["problems"][0]
    assert first["difficulty"] == "easy"
    assert "列表" in first["tags"]
    assert first["starterCode"]


def test_problem_import_rejects_invalid_payload_before_gateway_call() -> None:
    gateway = FakePistonGateway()
    app = CompilerApplication(gateway, Settings())

    response = app.analyze_problem_import({"text": ""})

    assert response.status_code == 400
    assert "text" in response.body["error"]
    assert gateway.calls == []


def test_problem_import_does_not_fabricate_problem_from_plain_notes() -> None:
    app = CompilerApplication(FakePistonGateway(), Settings())

    response = app.analyze_problem_import({"text": "今天下午讨论项目进度，记得带电脑。"})

    assert response.status_code == 200
    assert response.body["problems"] == []
    assert "未能" in response.body["warnings"][0]


def test_problem_import_does_not_fabricate_problem_from_empty_json() -> None:
    app = CompilerApplication(FakePistonGateway(), Settings())

    response = app.analyze_problem_import({"filename": "problems.json", "text": "[]"})

    assert response.status_code == 200
    assert response.body["problems"] == []
    assert "未能" in response.body["warnings"][0]


def test_problem_import_accepts_json_file_and_extracts_sample_tests() -> None:
    app = CompilerApplication(FakePistonGateway(), Settings())

    response = app.analyze_problem_import(
        {
            "filename": "题库.json",
            "text": (
                '[{"title":"回文","description":"判断字符串是否回文",'
                '"input":"一行字符串","output":"YES 或 NO",'
                '"sampleTests":[{"stdin":"level","expectedOutput":"YES"}]}]'
            ),
        }
    )

    assert response.status_code == 200
    problem = response.body["problems"][0]
    assert problem["title"] == "回文"
    assert problem["sampleTests"] == [{"stdin": "level", "expectedOutput": "YES"}]


def test_problem_import_accepts_csv_file() -> None:
    app = CompilerApplication(FakePistonGateway(), Settings())

    response = app.analyze_problem_import(
        {
            "filename": "题库.csv",
            "text": "title,description,input,output\n求和,输出两个数之和,两个整数,一个整数\n",
        }
    )

    assert response.status_code == 200
    assert response.body["problems"][0]["title"] == "求和"


def test_problem_import_accepts_docx_file() -> None:
    app = CompilerApplication(FakePistonGateway(), Settings())
    raw = _docx_bytes(
        [
            "题目：矩阵行和",
            "描述：读取一个矩阵，输出每一行的和。",
            "输入：第一行包含 n 和 m，后续 n 行包含整数。",
            "输出：每行一个整数。",
        ]
    )

    response = app.analyze_problem_import(
        {"filename": "题库.docx", "text": "", "contentBase64": _base64_bytes(raw)}
    )

    assert response.status_code == 200
    problem = response.body["problems"][0]
    assert problem["title"] == "矩阵行和"
    assert problem["inputHint"] == "第一行包含 n 和 m，后续 n 行包含整数。"


def test_problem_import_accepts_pdf_file() -> None:
    app = CompilerApplication(FakePistonGateway(), Settings())
    raw = _minimal_pdf_bytes(
        [
            "Problem: Sum Two Numbers",
            "Description: Add two integers.",
            "Input: two integers",
            "Output: one integer",
        ]
    )

    response = app.analyze_problem_import(
        {"filename": "problems.pdf", "text": "", "contentBase64": _base64_bytes(raw)}
    )

    assert response.status_code == 200
    problem = response.body["problems"][0]
    assert problem["title"] == "Sum Two Numbers"
    assert problem["outputHint"] == "one integer"


def test_problem_import_reports_ai_organization_source_when_changed() -> None:
    app = CompilerApplication(
        FakePistonGateway(),
        Settings(),
        organizer=FakeProblemOrganizer(),
    )

    response = app.analyze_problem_import(
        {
            "learnerId": "learner-1",
            "text": """
题目一：整数列表求和
描述：读取一行以空格分隔的整数，输出所有整数之和。
输入：空格分隔的整数
输出：一个整数

题目二：字符串回文判断
描述：判断字符串是否为回文。
输入：一行字符串
输出：YES 或 NO
""",
        }
    )

    assert response.status_code == 200
    assert response.body["source"] == "rules_with_ai_organization"
    assert response.body["warnings"] == ["AI 仅调整了练习顺序。"]


def test_problem_set_generation_uses_built_in_judgeable_problems() -> None:
    app = CompilerApplication(FakePistonGateway(), Settings())

    response = app.generate_problem_set(
        {
            "prompt": "我想练习循环和列表",
            "targetCount": 3,
            "difficultyRange": ["easy", "hard"],
            "knowledgeTags": ["循环", "列表"],
        }
    )

    assert response.status_code == 200
    assert response.body["source"] == "deterministic_rule"
    problems = response.body["orderedProblems"]
    assert len(problems) == 3
    assert problems[0]["source"] == "built_in"
    assert problems[0]["judgeable"] is True
    assert "problemId" in problems[0]
    assert response.body["coverage"]


def test_problem_set_generation_can_include_uploaded_session_problems() -> None:
    app = CompilerApplication(FakePistonGateway(), Settings())

    response = app.generate_problem_set(
        {
            "prompt": "练习栈",
            "targetCount": 2,
            "includeUploadedProblems": True,
            "uploadedProblems": [
                {
                    "id": "uploaded-brackets",
                    "title": "自定义括号题",
                    "description": "判断括号是否匹配。",
                    "difficulty": "hard",
                    "tags": ["栈"],
                    "source": "text = input().strip()\n",
                    "inputHint": "一行括号",
                    "outputHint": "VALID 或 INVALID",
                }
            ],
        }
    )

    assert response.status_code == 200
    problems = response.body["orderedProblems"]
    assert any(problem["source"] == "uploaded" for problem in problems)
    uploaded = next(problem for problem in problems if problem["source"] == "uploaded")
    assert uploaded["judgeable"] is False
    assert uploaded["limitations"] == ["未进入服务端题库，不支持隐藏测试判题。"]


def test_problem_set_generation_rejects_oversized_uploaded_problem_fields() -> None:
    app = CompilerApplication(FakePistonGateway(), Settings())

    response = app.generate_problem_set(
        {
            "prompt": "练习数组",
            "uploadedProblems": [
                {
                    "id": "oversized",
                    "title": "超长题面",
                    "description": "x" * (MAX_UPLOADED_PROBLEM_TEXT_BYTES + 1),
                }
            ],
        }
    )

    assert response.status_code == 400
    assert "uploadedProblems[0].description" in response.body["error"]


def test_problem_set_generation_reports_ai_planning_source_when_available() -> None:
    app = CompilerApplication(
        FakePistonGateway(),
        Settings(),
        practice_set_planner=FakePracticeSetPlanner(),
    )

    response = app.generate_problem_set(
        {"prompt": "练习输入输出", "targetCount": 2, "learnerId": "learner-1"}
    )

    assert response.status_code == 200
    assert response.body["source"] == "rules_with_ai_planning"
    assert response.body["rationale"] == "AI 按目标重新排列了练习顺序。"
    assert "AI 未生成隐藏测试。" in response.body["warnings"]
    assert response.body["orderedProblems"][0]["generationReason"].startswith("AI 建议")


def test_problem_set_generation_rejects_invalid_payload() -> None:
    app = CompilerApplication(FakePistonGateway(), Settings())

    response = app.generate_problem_set({"prompt": ""})

    assert response.status_code == 400
    assert "prompt" in response.body["error"]
