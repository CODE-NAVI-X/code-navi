"""Static frontend contract checks for the Issue #82 project navigator."""

from pathlib import Path

PRACTICE_PAGE = Path("frontend/app/(student)/learning/practice/page.tsx")
PROJECT_PAGE = Path("frontend/app/(student)/learning/projects/page.tsx")
PRACTICE_API = Path("frontend/lib/api/practice.ts")


def test_project_navigation_is_reachable_from_practice() -> None:
    source = PRACTICE_PAGE.read_text(encoding="utf-8")

    assert 'router.push("/learning/projects")' in source
    assert "浏览项目代码" in source


def test_project_page_uses_api_client_and_handles_offline_states() -> None:
    source = PROJECT_PAGE.read_text(encoding="utf-8")

    assert "uploadCodeProject" in source
    assert "fetchCodeProject" in source
    assert "fetchCodeProjectFile" in source
    assert "explainCodeProject" in source
    assert "generateProjectCodeFill" in source
    assert "PracticeApiError" in source
    assert "项目总大小不能超过 2 MB" in source
    assert 'role="alert"' in source
    assert "sidebarHidden" in source
    assert "fullscreen" in source


def test_project_api_keeps_upload_tree_and_file_reading_separate() -> None:
    source = PRACTICE_API.read_text(encoding="utf-8")

    assert '"/api/v1/practice/projects"' in source
    assert "fetchCodeProject" in source
    assert "fetchCodeProjectFile" in source
    assert "explainCodeProject" in source
    assert "generateProjectCodeFill" in source
    assert "content_base64" in source
