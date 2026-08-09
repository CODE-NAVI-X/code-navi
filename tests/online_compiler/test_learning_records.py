from __future__ import annotations

from pathlib import Path

from code_navi.online_compiler.evaluation import AiFeedback, QualityRubric, RuleAssessment
from code_navi.online_compiler.learning_records import LearningRecordStore
from code_navi.online_compiler.piston import ExecutionResult, RuntimeInfo


def test_record_store_keeps_feedback_but_not_raw_source_or_input(tmp_path: Path) -> None:
    database = tmp_path / "records.sqlite3"
    store = LearningRecordStore(database)
    source = "print('private-learning-code')"
    result = ExecutionResult(
        "success",
        "private-program-output",
        "",
        0,
        None,
        None,
        5,
        4,
        1_024,
        RuntimeInfo("python", "3.12.0"),
    )
    assessment = RuleAssessment("success", "success", "运行成功", "当前输入下正常结束。")
    feedback = AiFeedback("代码结构简单。", ("补充函数封装",), QualityRubric(80, 70, 60))

    created = store.add(
        "fd5f93a4-36c9-4f8d-9a73-71af013a4368",
        source,
        result,
        assessment,
        ai_status="completed",
        feedback=feedback,
    )
    records = store.list_for("fd5f93a4-36c9-4f8d-9a73-71af013a4368")

    assert records == (created,)
    assert records[0].reference_score == 70
    assert "source" not in records[0].as_dict()
    assert "stdin" not in records[0].as_dict()
    raw_database = database.read_bytes()
    assert source.encode() not in raw_database
    assert b"private-program-output" not in raw_database


def test_record_queries_are_isolated_by_learner_id(tmp_path: Path) -> None:
    store = LearningRecordStore(tmp_path / "records.sqlite3")
    result = ExecutionResult(
        "time_limit",
        "",
        "",
        None,
        None,
        "TO",
        2_001,
        2_000,
        1_024,
        RuntimeInfo("python", "3.12.0"),
    )
    assessment = RuleAssessment("time_limit", "warning", "运行超时", "超过时间限制。")
    first_id = "fd5f93a4-36c9-4f8d-9a73-71af013a4368"
    second_id = "4875cc24-c870-486b-9e2e-863642c2cf34"

    store.add(first_id, "while True: pass", result, assessment, ai_status="disabled", feedback=None)

    assert len(store.list_for(first_id)) == 1
    assert store.list_for(second_id) == ()


def test_pending_record_can_be_updated_with_ai_feedback(tmp_path: Path) -> None:
    store = LearningRecordStore(tmp_path / "records.sqlite3")
    learner_id = "fd5f93a4-36c9-4f8d-9a73-71af013a4368"
    result = ExecutionResult(
        "success",
        "ok\n",
        "",
        0,
        None,
        None,
        5,
        4,
        1_024,
        RuntimeInfo("python", "3.12.0"),
    )
    assessment = RuleAssessment("success", "success", "运行成功", "当前输入下正常结束。")
    pending = store.add(
        learner_id, "print('ok')", result, assessment, ai_status="pending", feedback=None
    )
    feedback = AiFeedback("代码结构简单。", ("补充边界用例",), QualityRubric(80, 70, 60))

    updated = store.update_feedback(
        pending.record_id,
        learner_id,
        ai_status="completed",
        feedback=feedback,
    )

    assert updated is not None
    assert updated.ai_status == "completed"
    assert updated.reference_score == 70
    assert len(store.list_for(learner_id)) == 1
