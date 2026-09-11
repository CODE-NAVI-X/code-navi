"""Negative confirmation guards for the dynamic CNN question flow."""

from __future__ import annotations

import pytest

from code_navi.research.cnn_flow import (
    build_cnn_flow_queries,
    classify_answer,
    cnn_flow_matches_step,
    cnn_flow_suggestion_adopted,
    cnn_flow_summary_confirmed,
)


@pytest.mark.parametrize(
    "message",
    ["不确认", "我不确认", "不同意", "不准确", "我不认为以上内容准确", "不选择这篇论文"],
)
def test_summary_negations_are_not_confirmations(message: str) -> None:
    assert cnn_flow_summary_confirmed(message) is False


@pytest.mark.parametrize(
    "message",
    ["不采用这个方案", "我不同意", "不可以", "不想采用", "是否采用这个方案"],
)
def test_suggestion_negations_are_not_adoptions(message: str) -> None:
    assert cnn_flow_suggestion_adopted(message) is False


@pytest.mark.parametrize(
    "message", ["不确认", "我不确认", "不同意", "不选择这篇论文", "换一篇"],
)
def test_paper_confirmation_negations_do_not_advance(message: str) -> None:
    assert cnn_flow_matches_step("await_confirm", message) is False


def test_direction_recommendation_is_not_recorded_as_user_direction() -> None:
    assert classify_answer("direction", "请推荐") == "recommend"


def test_dynamic_query_strips_only_a_display_option_prefix() -> None:
    answers = {
        "direction": {
            "raw": "我选 A：研究数据增强是否影响 CNN 的解释稳定性",
            "value": "我选 A：研究数据增强是否影响 CNN 的解释稳定性",
            "confirmed": True,
            "suggested": False,
        }
    }

    queries = build_cnn_flow_queries(answers)

    assert queries is not None
    assert queries["query_zh"] == "研究数据增强是否影响 CNN 的解释稳定性"
    assert not queries["query_en"].startswith("A ")
