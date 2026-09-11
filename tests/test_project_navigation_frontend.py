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
    assert "set_id=${encodeURIComponent(practice.set_id)}" in source
    assert "PracticeApiError" in source
    assert "项目总大小不能超过 2 MB" in source
    assert 'role="alert"' in source
    assert "sidebarHidden" in source
    assert "fullscreen" in source
    assert "onSelect={(symbol) => onSelect(node.file, symbol)}" in source
    assert "selectedLine" in source
    assert "打开文件（第 ${symbol.line} 行）" in source


def test_project_api_keeps_upload_tree_and_file_reading_separate() -> None:
    source = PRACTICE_API.read_text(encoding="utf-8")

    assert '"/api/v1/practice/projects"' in source
    assert "fetchCodeProject" in source
    assert "fetchCodeProjectFile" in source
    assert "explainCodeProject" in source
    assert "generateProjectCodeFill" in source
    assert "content_base64" in source


def test_practice_page_restores_project_generated_code_fill_sets() -> None:
    source = Path("frontend/app/(student)/learning/practice/page.tsx").read_text(encoding="utf-8")
    api = Path("frontend/lib/api/practice.ts").read_text(encoding="utf-8")

    assert 'searchParams.get("set_id")' in source
    assert "fetchPracticeSet(restoredSetId)" in source
    assert "restoredStructureSet" in source
    assert "fetchPracticeSet" in api


def test_project_navigation_scrolls_to_target_line_and_highlights() -> None:
    source = PROJECT_PAGE.read_text(encoding="utf-8")

    assert "targetLineRef" in source
    assert "scrollIntoView" in source
    assert "ref={isTargetLine ? targetLineRef : undefined}" in source
    assert "data-line-number={lineNumber}" in source
    assert 'aria-current={isTargetLine ? "location" : undefined}' in source


def test_project_navigation_behavioral_vitest_is_wired() -> None:
    vitest_path = Path("frontend/test/project-navigation.test.tsx")
    assert vitest_path.exists()
    test_source = vitest_path.read_text(encoding="utf-8")
    assert "scrolls and highlights a symbol after its file content loads" in test_source
    assert "clears the previous symbol target when a normal file is selected" in test_source
    assert "scrollIntoView" in test_source

