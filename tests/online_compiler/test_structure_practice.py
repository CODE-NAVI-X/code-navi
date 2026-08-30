from __future__ import annotations

import os

os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from fastapi.testclient import TestClient

from code_navi.practice.structure_practice import (
    DEFAULT_EXERCISES,
    StructureExerciseKind,
    StructurePracticeService,
)
from code_navi.server import app


def _single_level_sequence_exercise():
    return next(
        item
        for item in DEFAULT_EXERCISES
        if item.kind is StructureExerciseKind.STRUCTURE_SEQUENCE and not item.levels
    )


def test_list_exercises_does_not_expose_answers_or_grading_tokens() -> None:
    service = StructurePracticeService()

    response = service.list_exercises()

    assert response["schemaVersion"] == "structure-practice.v1"
    assert response["topics"]
    assert len(response["topics"]) >= 5
    assert all(topic["count"] > 0 for topic in response["topics"])
    assert len(response["exercises"]) >= 6
    for exercise in response["exercises"]:
        assert "answerSequence" not in exercise
        assert "requiredTokens" not in exercise
        assert "explanation" not in exercise


def test_sequence_exercise_accepts_correct_order() -> None:
    service = StructurePracticeService()
    exercise = _single_level_sequence_exercise()

    result = service.submit(exercise.id, list(exercise.answer_sequence))

    assert result["verdict"] == "accepted"
    assert result["score"] == 100
    assert all(item["status"] == "passed" for item in result["feedback"])


def test_sequence_exercise_marks_wrong_positions_without_returning_answer() -> None:
    service = StructurePracticeService()
    exercise = _single_level_sequence_exercise()
    wrong = [exercise.answer_sequence[1], *exercise.answer_sequence[1:]]

    result = service.submit(exercise.id, wrong)

    assert result["verdict"] == "wrong_answer"
    assert 0 < result["score"] < 100
    assert any(item["status"] == "failed" for item in result["feedback"])
    assert "answerSequence" not in result


def test_framework_exercise_accepts_required_pytorch_tokens() -> None:
    service = StructurePracticeService()
    exercise = next(
        item
        for item in DEFAULT_EXERCISES
        if item.kind is StructureExerciseKind.FRAMEWORK_FILL
    )

    result = service.submit(
        exercise.id,
        "nn.Conv2d(in_channels=1, out_channels=32, kernel_size=3)",
    )

    assert result["verdict"] == "accepted"
    assert result["score"] == 100
    assert all(item["status"] == "passed" for item in result["feedback"])


def test_framework_exercise_reports_missing_required_token() -> None:
    service = StructurePracticeService()
    exercise = next(
        item
        for item in DEFAULT_EXERCISES
        if item.kind is StructureExerciseKind.FRAMEWORK_FILL
    )

    result = service.submit(exercise.id, "nn.Conv2d(1, 32, 3)")

    assert result["verdict"] == "wrong_answer"
    assert result["score"] < 100
    assert any(item["status"] == "failed" for item in result["feedback"])


def test_structure_exercise_api_returns_list_and_grade_without_piston() -> None:
    with TestClient(app) as client:
        listed = client.get("/api/v1/practice/structure-exercises")
        exercise_id = listed.json()["exercises"][0]["id"]
        exercise = next(item for item in DEFAULT_EXERCISES if item.id == exercise_id)
        if exercise.levels:
            answer = [list(level.answer_sequence) for level in exercise.levels]
        else:
            answer = list(exercise.answer_sequence)
        submitted = client.post(
            f"/api/v1/practice/structure-exercises/{exercise_id}/submit",
            json={"answer": answer},
        )

    assert listed.status_code == 200
    assert listed.json()["schemaVersion"] == "structure-practice.v1"
    assert submitted.status_code == 200
    assert submitted.json()["verdict"] == "accepted"


def test_structure_exercise_api_rejects_unknown_exercise() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/practice/structure-exercises/not-found/submit",
            json={"answer": ["anything"]},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "structure exercise not found"
