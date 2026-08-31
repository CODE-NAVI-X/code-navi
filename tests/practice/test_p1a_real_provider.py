"""Provider-path tests for the P1-A real backend.

These tests never call a real provider. They monkeypatch the service boundary to
prove that code-fill generation, static grading and symbol explanation correctly
consume validated model output and fall back to rules otherwise.
"""

from __future__ import annotations

import json
import os
from collections.abc import Generator
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

os.environ["CODE_NAVI_DATABASE_URL"] = "sqlite:///:memory:"

from code_navi.db import Base, SessionLocal, engine  # noqa: E402
from code_navi.practice.models import (  # noqa: E402
    PracticeSetItemModel,
    PracticeSetModel,
)
from code_navi.practice.schemas import (  # noqa: E402
    CodeFillGradeRequest,
    ExplainSymbolRequest,
    PracticeSetGenerateRequest,
)
from code_navi.practice.service import (  # noqa: E402
    PracticeSetService,
)
from code_navi.server import app  # noqa: E402,F401


def _attempt_id() -> str:
    return str(uuid4())


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


def _generation_request() -> PracticeSetGenerateRequest:
    return PracticeSetGenerateRequest(kind="code_practice", topic="循环", count=3)


def _model_output(output_text: str) -> SimpleNamespace:
    return SimpleNamespace(output_text=output_text)


def test_code_fill_generation_parses_model_output(monkeypatch: pytest.MonkeyPatch) -> None:
    service = PracticeSetService()
    monkeypatch.setattr(service, "_provider_name", lambda: "deepseek")
    model_json = {
        "items": [
            {
                "title": "求和",
                "complexity": "light",
                "judge_mode": "llm_static",
                "reference_code": "def total(items):\n    return sum(items)\n",
                "code_masked": "def total(items):\n    return ______\n",
                "blanks": [
                    {
                        "blank_id": "sum-call",
                        "answer": "sum(items)",
                        "alternate_answers": [],
                        "hint": "求和",
                        "step_no": 1,
                    },
                    {
                        "blank_id": "return-value",
                        "answer": "sum(items)",
                        "alternate_answers": [],
                        "hint": "返回结果",
                        "step_no": 2,
                    },
                ],
                "steps": [
                    {
                        "step_no": 1,
                        "title": "计算并返回",
                        "reason": "一次完成",
                        "sub_steps": ["sum", "return"],
                    }
                ],
            }
        ]
    }
    monkeypatch.setattr(
        service,
        "_run_agent",
        lambda **kwargs: (_model_output(json.dumps(model_json)), "deepseek"),
    )

    specs, provider_name, used_model = service._generate_code_fill_specs(_generation_request())

    assert provider_name == "deepseek"
    assert used_model is True
    assert len(specs) == 1
    assert specs[0][0]["judge_mode"] == "llm_static"
    assert specs[0][1]["reference_code"].startswith("def total")


def test_generation_falls_back_to_rules_when_provider_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PracticeSetService()
    monkeypatch.setattr(service, "_provider_name", lambda: "deepseek")

    def fail_run(**kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(service, "_run_agent", fail_run)

    specs, provider_name, used_model = service._generate_code_fill_specs(
        _generation_request()
    )

    assert used_model is False
    assert provider_name == "rules"
    assert len(specs) == 3


def test_grade_code_fill_uses_model_when_configured(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
) -> None:
    service = PracticeSetService()
    set_id = "set-model-grade"
    item_id = "item-01"
    db.add(
        PracticeSetModel(
            set_id=set_id,
            kind="code_practice",
            generation_mode="model",
            provider_name="deepseek",
        )
    )
    db.add(
        PracticeSetItemModel(
            set_id=set_id,
            item_id=item_id,
            position=1,
            item_kind="code_fill",
            payload={"judge_mode": "llm_static"},
            judge_secret={
                "blanks": [
                    {
                        "blank_id": "blank-1",
                        "answer": "total + value",
                        "alternate_answers": [],
                        "hint": "累加",
                        "step_no": 1,
                    }
                ],
                "reference_code": "def average(nums):\n    total = 0\n",
            },
        )
    )
    db.commit()

    monkeypatch.setattr(service, "_provider_name", lambda: "deepseek")
    monkeypatch.setattr(
        service,
        "_run_agent",
        lambda **kwargs: (
            _model_output(
                json.dumps(
                    {
                        "results": [
                            {
                                "blank_id": "blank-1",
                                "correct": False,
                                "score": 0,
                                "comment": "等价写法不成立",
                            }
                        ]
                    }
                )
            ),
            "deepseek",
        ),
    )

    response = service.grade_code_fill(
        CodeFillGradeRequest(
            set_id=set_id,
            item_id=item_id,
            attempt_id=_attempt_id(),
            blank_answers=[{"blank_id": "blank-1", "value": "x"}],
        ),
        db,
    )

    assert response.provider_name == "deepseek"
    assert response.results[0].graded_by == "model"
    assert response.results[0].correct is False


def test_mock_grade_does_not_run_agent(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
) -> None:
    service = PracticeSetService()
    set_id = "set-mock-grade"
    item_id = "item-mock"
    db.add(
        PracticeSetModel(
            set_id=set_id,
            kind="code_practice",
            generation_mode="mock",
            provider_name="mock",
        )
    )
    db.add(
        PracticeSetItemModel(
            set_id=set_id,
            item_id=item_id,
            position=1,
            item_kind="code_fill",
            payload={"judge_mode": "llm_static"},
            judge_secret={
                "blanks": [
                    {
                        "blank_id": "blank-1",
                        "answer": "total + value",
                        "alternate_answers": [],
                        "hint": "累加",
                        "step_no": 1,
                    }
                ],
                "reference_code": "def average(nums):\n    total = 0\n",
            },
        )
    )
    db.commit()

    def must_not_run(**kwargs):
        raise AssertionError("mock grade must not run the kernel loop")

    monkeypatch.setattr(service, "_run_agent", must_not_run)

    response = service.grade_code_fill(
        CodeFillGradeRequest(
            set_id=set_id,
            item_id=item_id,
            attempt_id=_attempt_id(),
            blank_answers=[{"blank_id": "blank-1", "value": "x"}],
        ),
        db,
    )

    assert response.results[0].graded_by == "rules"


def test_explain_symbol_uses_model_and_caches(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
) -> None:
    service = PracticeSetService()
    set_id = "set-explain-model"
    item_id = "item-explain"
    db.add(
        PracticeSetModel(
            set_id=set_id,
            kind="code_practice",
            generation_mode="model",
            provider_name="deepseek",
        )
    )
    db.add(
        PracticeSetItemModel(
            set_id=set_id,
            item_id=item_id,
            position=1,
            item_kind="code_fill",
            payload={"judge_mode": "llm_static"},
            judge_secret={"blanks": [], "reference_code": ""},
        )
    )
    db.commit()

    monkeypatch.setattr(service, "_provider_name", lambda: "deepseek")
    monkeypatch.setattr(
        service,
        "_run_agent",
        lambda **kwargs: (
            _model_output(json.dumps({"explanation": "这是一个求和函数。"})),
            "deepseek",
        ),
    )
    request = ExplainSymbolRequest(
        set_id=set_id,
        item_id=item_id,
        symbol={
            "name": "sum_items",
            "kind": "function",
            "code_excerpt": "def sum_items(items):\n    return sum(items)",
        },
    )

    first = service.explain_symbol(request, db)
    second = service.explain_symbol(request, db)

    assert first.source == "model"
    assert first.cached is False
    assert second.source == "model"
    assert second.cached is True


def test_parser_derives_server_side_complexity() -> None:
    service = PracticeSetService()
    reference_code = "def f():\n" + "    x = 1\n" * 220
    model = {
        "items": [
            {
                "title": "long",
                "complexity": "light",
                "judge_mode": "llm_static",
                "reference_code": reference_code,
                "code_masked": reference_code,
                "blanks": [
                    {
                        "blank_id": "b1",
                        "answer": "x",
                        "alternate_answers": [],
                        "hint": "h",
                        "step_no": 1,
                    },
                    {
                        "blank_id": "b2",
                        "answer": "x",
                        "alternate_answers": [],
                        "hint": "h",
                        "step_no": 2,
                    },
                ],
                "steps": [
                    {
                        "step_no": 1,
                        "title": "t",
                        "reason": "r",
                        "sub_steps": [],
                    }
                ],
            }
        ]
    }

    specs = service._parse_code_fill_items(json.dumps(model), 1, "topic")

    assert specs is not None
    assert specs[0][0]["complexity"] == "heavy"
    assert specs[0][0]["judge_mode"] == "explain_only"


def test_parser_dedupes_and_truncates_blank_ids() -> None:
    service = PracticeSetService()
    blank_id = "b" * 100
    model = {
        "items": [
            {
                "title": "dup",
                "reference_code": "def f():\n    return 1\n",
                "code_masked": "def f():\n    return ______\n",
                "blanks": [
                    {"blank_id": blank_id, "answer": "1", "hint": "h", "step_no": 1},
                    {"blank_id": blank_id, "answer": "1", "hint": "h", "step_no": 2},
                ],
                "steps": [
                    {
                        "step_no": 1,
                        "title": "t",
                        "reason": "r",
                        "sub_steps": [],
                    }
                ],
            }
        ]
    }

    specs = service._parse_code_fill_items(json.dumps(model), 1, "topic")

    assert specs is None
