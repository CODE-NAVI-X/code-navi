"""Static contract checks for the homepage resume data sources."""

from pathlib import Path


def test_homepage_uses_current_flow_and_portrait_contracts() -> None:
    source = Path("frontend/app/page.tsx").read_text(encoding="utf-8")

    assert "flowPayload?.masteredKnowledgePoint.name" in source
    assert "overview?.research.conversations[0]" in source
    assert "flowPayload?.knowledgePoint" not in source
    assert "overview?.conversations?.[0]" not in source
