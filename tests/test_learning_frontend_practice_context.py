"""Static contract checks for the §3.1 practice-context.v1 frontend hand-off."""

from __future__ import annotations

from pathlib import Path

PRACTICE_CONTEXT = Path("frontend/lib/practice-context.ts")
LEARNING_CONTEXT = Path("frontend/lib/learning-context.ts")
FLOW_STORE = Path("frontend/lib/store/flow-store.ts")
DIALOG = Path("frontend/components/learning/PracticeContextDialog.tsx")
GO_CARD = Path("frontend/components/learning/DownstreamGoCard.tsx")
PRACTICE_PAGE = Path("frontend/app/(student)/learning/practice/page.tsx")
PRACTICE_API = Path("frontend/lib/api/practice.ts")


def test_practice_context_v1_is_built_in_one_shared_module() -> None:
    source = PRACTICE_CONTEXT.read_text(encoding="utf-8")

    assert '"practice-context.v1"' in source or "practice-context.v1" in source
    assert "source_session_id" in source
    assert "knowledge_points" in source
    assert "objective" in source
    assert "notes_summary" in source
    # The helper module is the single construction point for the structure.
    assert "buildPracticeContextV1" in source
    assert "isPracticeContextV1" in source


def test_mastery_uses_real_portrait_values_or_null() -> None:
    source = PRACTICE_CONTEXT.read_text(encoding="utf-8")

    # Red line: mastery only from the real portrait; no value → null, offline → null.
    assert "fetchProfile" in source
    assert "fetchKnowledgePointMastery" in source
    assert "result[masteryKey(name)] = null" in source
    assert "catch" in source
    assert "value < 0 || value > 1" in source


def test_flow_payload_upgrade_stays_backward_compatible() -> None:
    store = FLOW_STORE.read_text(encoding="utf-8")
    learning = LEARNING_CONTEXT.read_text(encoding="utf-8")

    assert "practiceContext?: PracticeContextV1" in store
    # Old cached payloads (no context block / corrupted block) must keep loading.
    assert "isPracticeContextV1(parsed.practiceContext)" in store
    assert "delete parsed.practiceContext" in store
    # The unified exit still exists and stores the optional context.
    assert "practiceContext: options.practiceContext" in learning
    # URL stays a light pointer: the canonical query keys are kept.
    assert "LEARNING_CONTEXT_QUERY_KEYS" in learning
    assert '"/learning/practice"' in learning


def test_context_is_reviewable_before_the_jump() -> None:
    dialog = DIALOG.read_text(encoding="utf-8")
    go_card = GO_CARD.read_text(encoding="utf-8")

    # 查看/修改/清除 three states on the pre-jump dialog.
    assert "确认并跳转" in dialog
    assert "清除上下文" in dialog
    assert "取消" in dialog
    assert "学习目标" in dialog
    # The only entry point goes through the shared helper, not its own assembly.
    assert 'from "@/lib/learning-context"' in go_card
    assert "navigateToPractice" in go_card
    assert "PracticeContextDialog" in go_card


def test_context_body_is_submitted_through_the_generate_gateway() -> None:
    api = PRACTICE_API.read_text(encoding="utf-8")
    page = PRACTICE_PAGE.read_text(encoding="utf-8")

    assert '"/api/v1/practice/sets/generate"' in api
    assert "context: payload.context" in api
    # The practice page consumes the structure and passes it to generation.
    assert "practiceContext" in page
    assert "generatePracticeSetWithContext" in page
    assert "已带入学习上下文" in page


def test_learning_direct_entry_starts_core_structure_practice() -> None:
    page = PRACTICE_PAGE.read_text(encoding="utf-8")

    assert 'useState<PracticeView>("start")' in page
    assert "isPracticeContextV1(practiceContextCandidate)" in page
    assert 'setView("structure")' in page
    assert "fetchStructureExercises" in page
    assert "ContextStructureWorkspace" in page
    assert "gatewayItemToContextStructureItem" in page
    assert "题目绑定知识点" in page


def test_no_third_entry_point_assembles_the_structure() -> None:
    frontend_dir = Path("frontend")
    allowed = {
        PRACTICE_CONTEXT.resolve(),
        PRACTICE_API.resolve(),
        (Path("frontend") / "components" / "learning" / "PracticeContextDialog.tsx").resolve(),
        (Path("frontend") / "app" / "(student)" / "learning" / "practice" / "page.tsx").resolve(),
    }
    offenders = [
        path
        for path in frontend_dir.rglob("*.ts*")
        if "source_session_id" in path.read_text(encoding="utf-8")
        and path.resolve() not in allowed
    ]
    assert offenders == []
