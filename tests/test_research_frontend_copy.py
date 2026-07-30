"""Regression checks for research-page networking disclosure copy."""

from pathlib import Path

PAGE = Path("frontend/app/(student)/research/page.tsx")


def test_generation_mode_copy_requires_explicit_search_trigger() -> None:
    source = PAGE.read_text(encoding="utf-8")

    expected_messages = (
        "当前为模型个性化建议：模型只影响个性化追问；字段顺序、状态保存与完成判定仍由规则控制。不会自动联网检索，受限学术检索仅在你主动点击后执行，也不会把建议当作论文事实。",
        "模型建议暂不可用，已安全降级为规则生成：不会自动联网检索，受限学术检索仅在你主动点击后执行，也不会把建议当作论文事实。",
        "当前为规则生成：未使用模型个性化建议，不会自动联网检索；受限学术检索仅在你主动点击后执行，也不会把建议当作论文事实。",
    )

    assert all(message in source for message in expected_messages)
    assert "不联网检索" not in source
