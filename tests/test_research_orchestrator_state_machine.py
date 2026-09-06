"""Tests for the Four-Stage State Machine in Research Conversation Orchestration."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from code_navi.db import Base
from code_navi.research.academic import (
    AcademicSearchTool,
    AcademicSourceResult,
    PaperMetadata,
)
from code_navi.research.conversation_orchestrator import (
    ConversationNotFoundError,
    ResearchConversationOrchestrator,
    detect_confirmation_intent,
    detect_direction_change_intent,
    is_history_inquiry,
    is_opening_greeting_intent,
)
from code_navi.research.conversation_orchestrator_schemas import (
    CurrentPaperCard,
    LearnerProfileData,
    LearningContextInput,
    SelectPaperRequest,
    SendOrchestratorMessageRequest,
)
from code_navi.research.conversation_schemas import (
    AcademicSourceStatus,
    ConversationEvidenceBundle,
    CreateConversationEvidenceBundleRequest,
)
from code_navi.research.conversation_search_service import (
    ConversationSearchNotReadyError,
    ResearchConversationSearchService,
)
from code_navi.research.models import (
    ResearchConversationModel,
    ResearchOrchestratorStateModel,
)
from code_navi.research.schemas import AcademicPaperResult, EvidenceStatement


@pytest.fixture
def db_session(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "mock")
    database_url = f"sqlite:///{tmp_path / 'test_sm.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_intent_detection_confirmation() -> None:
    assert detect_confirmation_intent("可以，我觉得这个方向很好")
    assert detect_confirmation_intent("继续吧，进入下一步")
    assert detect_confirmation_intent("就这样")
    assert detect_confirmation_intent("好的，没问题")
    assert detect_confirmation_intent("行，走下一步")

    # Vague, hesitant, negative
    assert not detect_confirmation_intent("我想再想想")
    assert not detect_confirmation_intent("不太对，需要改改")
    assert not detect_confirmation_intent("等等，不确定")
    assert not detect_confirmation_intent("好像不行")
    assert not detect_confirmation_intent("无法确认的内容请标记为待核验")
    assert not detect_confirmation_intent("请确认需要哪些检索词")


def test_intent_detection_direction_change() -> None:
    assert detect_direction_change_intent("我想换个方向")
    assert detect_direction_change_intent("我想换个研究方向，改做图对比学习")
    assert detect_direction_change_intent("重新选方向")
    assert detect_direction_change_intent("换方向做别的")

    # Asking about history should NOT be treated as direction change
    assert not detect_direction_change_intent("之前说了什么？")
    assert not detect_direction_change_intent("我们刚才讨论了哪个方向？")
    assert is_history_inquiry("之前说了什么？")
    assert is_history_inquiry("我们刚才讨论了哪个方向？")


def test_reentry_learning_greeting_uses_welcome_intent() -> None:
    assert is_opening_greeting_intent(
        "你好姜姜，我回来继续做科研了，请结合我最近新增的学习内容帮我看看下一步。"
    )


def test_reentry_prompt_exposes_learning_delta(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator(llm_generator=FakeOrchestratorLlmGenerator())
    conv_id = "conv-learning-delta"
    db_session.add(ResearchConversationModel(id=conv_id, profile_data={}, messages_data=[]))
    db_session.commit()
    orchestrator.update_learning_context(
        conv_id,
        LearningContextInput(
            learned_content="图卷积网络(GCN)数学推导",
            learning_progress="完成理论推导",
        ),
        db_session,
    )
    orchestrator.update_learning_context(
        conv_id,
        LearningContextInput(
            learned_content="图卷积网络(GCN)数学推导；GraphSAGE 邻居采样",
            learning_progress="新增学习 GraphSAGE 邻居采样",
        ),
        db_session,
    )
    prompt = orchestrator._select_prompt_template(
        conv_id,
        current_stage="research_need",
        subtasks={"need_defined": False},
        user_message="你好姜姜，我回来继续做科研了，请结合我最近新增的学习内容帮我看看下一步。",
        is_confirmed=False,
        db=db_session,
        owned_ids=None,
    )
    assert prompt["template_name"] == "welcome_and_bridge"
    # P2-A consumption semantics: before any welcome turn has absorbed the
    # learning records, the first recovery surfaces them via the
    # first-absorption note (the delta wording is reserved for increments
    # over an already-absorbed baseline).
    assert "学习端记录" in prompt["user_prompt"]
    assert "GraphSAGE 邻居采样" in prompt["user_prompt"]


class FakeOrchestratorLlmGenerator:
    def generate(self, *, system_prompt: str, user_prompt: str, **kwargs):
        from code_navi.research.conversation_orchestrator import OrchestratorLlmOutcome
        return OrchestratorLlmOutcome(
            status="generated",
            reply_text="姜姜收到你的消息并为你明确了阶段目标 (•̀ᴗ•́)و ̑̑",
        )


def test_state_machine_advancement_requires_subtasks_and_confirmation(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator(llm_generator=FakeOrchestratorLlmGenerator())
    conv = ResearchConversationModel(id="conv-sm-1", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    # Initial state
    state = orchestrator.get_or_create_state("conv-sm-1", db_session)
    assert state.current_stage == "research_need"
    assert "research_need" not in state.completed_stages

    # 1. User says "可以", but need_defined is False -> does NOT advance
    resp = orchestrator.process_message(
        "conv-sm-1",
        SendOrchestratorMessageRequest(message="可以，继续吧"),
        db_session,
    )
    assert resp.state.current_stage == "research_need"

    # 2. Mark need_defined = True, but user message is hesitant -> does NOT advance
    state_model = db_session.get(ResearchOrchestratorStateModel, "conv-sm-1")
    state_model.subtasks = {"need_defined": True}
    db_session.commit()

    resp = orchestrator.process_message(
        "conv-sm-1",
        SendOrchestratorMessageRequest(message="我想再想想，等等看"),
        db_session,
    )
    assert resp.state.current_stage == "research_need"

    # 3. need_defined is True AND user confirms -> advances to research_plan
    resp = orchestrator.process_message(
        "conv-sm-1",
        SendOrchestratorMessageRequest(message="可以，确认这个需求，我们继续！"),
        db_session,
    )
    assert resp.state.current_stage == "research_plan"
    assert "research_need" in resp.state.completed_stages


def test_state_machine_direction_change_resets_to_research_need(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator()
    conv = ResearchConversationModel(id="conv-sm-2", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    # Move to research_execution
    state_model = ResearchOrchestratorStateModel(
        conversation_id="conv-sm-2",
        current_stage="research_execution",
        completed_stages=["research_need", "research_plan"],
        subtasks={"need_defined": True, "profile_ready": True, "plan_generated": True},
        direction_history=[],
        plan_history=[],
    )
    db_session.add(state_model)
    db_session.commit()

    # User asks to change direction
    resp = orchestrator.process_message(
        "conv-sm-2",
        SendOrchestratorMessageRequest(message="我想换个方向，做大模型多模态检索"),
        db_session,
    )
    assert resp.state.current_stage == "research_need"
    assert len(resp.state.direction_history) == 1
    assert (
        "大模型多模态检索" in resp.state.direction_history[0].direction
        or "换" in resp.state.direction_history[0].direction
    )


def test_asking_about_history_does_not_reset_stage(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator()
    conv = ResearchConversationModel(id="conv-sm-3", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    state_model = ResearchOrchestratorStateModel(
        conversation_id="conv-sm-3",
        current_stage="research_execution",
        completed_stages=["research_need", "research_plan"],
        subtasks={"need_defined": True, "profile_ready": True, "plan_generated": True},
        direction_history=[],
        plan_history=[],
    )
    db_session.add(state_model)
    db_session.commit()

    resp = orchestrator.process_message(
        "conv-sm-3",
        SendOrchestratorMessageRequest(message="我们之前第一阶段选了什么方向？"),
        db_session,
    )
    # Must remain in research_execution
    assert resp.state.current_stage == "research_execution"


def test_research_analysis_subtask_requires_traceable_experiment_results(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator(llm_generator=FakeOrchestratorLlmGenerator())
    conv = ResearchConversationModel(id="conv-sm-analysis", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.commit()

    def _create_state():
        state = db_session.get(ResearchOrchestratorStateModel, "conv-sm-analysis")
        if not state:
            state = ResearchOrchestratorStateModel(
                conversation_id="conv-sm-analysis",
                current_stage="research_analysis",
                completed_stages=["research_need", "research_plan", "research_execution"],
                subtasks={
                    "need_defined": True,
                    "profile_ready": True,
                    "plan_generated": True,
                    "paper_selected": True,
                    "experiment_designed": True,
                    "results_analyzed": False,
                },
                direction_history=[],
                plan_history=[],
            )
            db_session.add(state)
        else:
            state.subtasks = {
                "need_defined": True,
                "profile_ready": True,
                "plan_generated": True,
                "paper_selected": True,
                "experiment_designed": True,
                "results_analyzed": False,
            }
        db_session.commit()

    _create_state()

    # Case 1: Plain long message without experiment results -> False
    resp1 = orchestrator.process_message(
        "conv-sm-analysis",
        SendOrchestratorMessageRequest(message="这是一段很长的普通的讨论文本，我们接下来应该讨论什么呢？"),
        db_session,
    )
    assert resp1.state.subtasks.results_analyzed is False

    # Case 2: Pure confirmation word -> False
    resp2 = orchestrator.process_message(
        "conv-sm-analysis",
        SendOrchestratorMessageRequest(message="可以，确认"),
        db_session,
    )
    assert resp2.state.subtasks.results_analyzed is False

    # Case 3: Vague description without metrics or concrete logs -> False
    resp3 = orchestrator.process_message(
        "conv-sm-analysis",
        SendOrchestratorMessageRequest(message="我昨天在服务器上跑了实验，感觉运行得很顺利"),
        db_session,
    )
    assert resp3.state.subtasks.results_analyzed is False

    # Case 4: Isolated metric value -> False
    _create_state()
    resp4 = orchestrator.process_message(
        "conv-sm-analysis",
        SendOrchestratorMessageRequest(message="Accuracy: 83.5%"),
        db_session,
    )
    assert resp4.state.subtasks.results_analyzed is False

    # Case 5: Isolated baseline number -> False
    _create_state()
    resp5 = orchestrator.process_message(
        "conv-sm-analysis",
        SendOrchestratorMessageRequest(message="基线 79.2%"),
        db_session,
    )
    assert resp5.state.subtasks.results_analyzed is False

    # Case 6: Metrics and result but NO experimental config/context -> False
    _create_state()
    resp6 = orchestrator.process_message(
        "conv-sm-analysis",
        SendOrchestratorMessageRequest(
            message="评测结果出来了，Accuracy=83.5%，Loss=0.24，相比 baseline 79.2% 有明显提升"
        ),
        db_session,
    )
    assert resp6.state.subtasks.results_analyzed is False

    # Case 7: Metrics and config but NO observation/trend/baseline comparison -> False
    _create_state()
    resp7 = orchestrator.process_message(
        "conv-sm-analysis",
        SendOrchestratorMessageRequest(
            message=(
                "在 Cora 测试集使用 GCN 模型，lr=0.01、seed=42、训练 200 epoch；"
                "Accuracy=83.5%，Loss=0.24"
            )
        ),
        db_session,
    )
    assert resp7.state.subtasks.results_analyzed is False

    # Case 8: Questions asking how to improve without asserted baseline/trend -> False
    _create_state()
    resp8 = orchestrator.process_message(
        "conv-sm-analysis",
        SendOrchestratorMessageRequest(
            message="在 Cora 测试集使用 GCN，lr=0.01、seed=42，Accuracy=83.5%，如何提升？"
        ),
        db_session,
    )
    assert resp8.state.subtasks.results_analyzed is False

    # Case 9: Future intention / desires without asserted baseline/trend -> False
    _create_state()
    resp9 = orchestrator.process_message(
        "conv-sm-analysis",
        SendOrchestratorMessageRequest(
            message="在测试集上 Accuracy=83.5%，结果还需要提升"
        ),
        db_session,
    )
    assert resp9.state.subtasks.results_analyzed is False

    # Case 10: Listing baseline value without comparative conclusion + inquiry -> False
    _create_state()
    resp10 = orchestrator.process_message(
        "conv-sm-analysis",
        SendOrchestratorMessageRequest(
            message="在 Cora 测试集使用 GCN，lr=0.01，Accuracy=83.5%，baseline=79.2%，如何提升？"
        ),
        db_session,
    )
    assert resp10.state.subtasks.results_analyzed is False

    # Case 11: Complete evidence with explicit occurred baseline comparison -> True
    _create_state()
    resp11 = orchestrator.process_message(
        "conv-sm-analysis",
        SendOrchestratorMessageRequest(
            message=(
                "在 Cora 测试集使用 GCN，lr=0.01、seed=42、训练 200 epoch；"
                "Accuracy=83.5%，Loss=0.24，相比 baseline 79.2% 提升 4.3 个百分点。"
            )
        ),
        db_session,
    )
    assert resp11.state.subtasks.results_analyzed is True


def test_first_load_race_adopts_the_winner_state_row(db_session) -> None:
    """Parallel first-load requests must not fail with a UNIQUE violation.

    Regression: on a legacy conversation the state and direction-cards
    requests both ran check-then-insert; the loser raised
    ``UNIQUE constraint failed: research_orchestrator_states.conversation_id``
    and surfaced as HTTP 500.
    """
    orchestrator = ResearchConversationOrchestrator(llm_generator=FakeOrchestratorLlmGenerator())
    conv_id = "conv-state-race"
    db_session.add(ResearchConversationModel(id=conv_id, profile_data={}, messages_data=[]))
    db_session.commit()

    real_commit = db_session.commit
    rival_committed = {"done": False}

    def rival_wins_commit() -> None:
        if rival_committed["done"]:
            real_commit()
            return
        rival_committed["done"] = True
        # The rival request (the parallel direction-cards read) wins the race
        # and inserts its row before our commit lands.
        rival = sessionmaker(bind=db_session.get_bind())()
        try:
            rival.add(ResearchOrchestratorStateModel(conversation_id=conv_id))
            rival.commit()
        finally:
            rival.close()
        raise IntegrityError(
            "INSERT INTO research_orchestrator_states",
            {},
            Exception("UNIQUE constraint failed: research_orchestrator_states.conversation_id"),
        )

    db_session.commit = rival_wins_commit  # type: ignore[method-assign]
    try:
        state = orchestrator.get_state_model(conv_id, db_session)
    finally:
        db_session.commit = real_commit  # type: ignore[method-assign]

    assert state.conversation_id == conv_id
    again = orchestrator.get_state_model(conv_id, db_session)
    assert again.conversation_id == conv_id
    assert again.completed_stages == state.completed_stages


class SequencedOrchestratorLlmGenerator:
    """Fake LLM returning a distinct reply per call, for plan-version assertions."""

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls = 0

    def generate(self, *, system_prompt: str, user_prompt: str, **kwargs):
        from code_navi.research.conversation_orchestrator import OrchestratorLlmOutcome

        text = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return OrchestratorLlmOutcome(status="generated", reply_text=text)


def _make_plan_stage_state(db_session, conv_id: str) -> ResearchOrchestratorStateModel:
    state_model = ResearchOrchestratorStateModel(
        conversation_id=conv_id,
        current_stage="research_plan",
        completed_stages=["research_need"],
        subtasks={"need_defined": True, "profile_ready": True, "plan_generated": False},
        direction_history=[],
        plan_history=[],
    )
    db_session.add(state_model)
    db_session.commit()
    return state_model


def test_plan_generation_then_confirmation_completes_stage_two(db_session) -> None:
    """plan_generated must be set by deterministic rule after a plan is
    generated, so stage two can complete on a later explicit confirmation.

    Regression: no code path ever set ``plan_generated = True``, so the
    ``research_plan -> research_execution`` transition was unreachable.
    """
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=SequencedOrchestratorLlmGenerator(
            ["姜姜结合你的画像整理了一份执行计划，我们先从数据准备开始 (｡･ω･｡)"]
        )
    )
    conv = ResearchConversationModel(id="conv-plan-1", profile_data={}, messages_data=[])
    db_session.add(conv)
    _make_plan_stage_state(db_session, "conv-plan-1")

    # 1. Explicit confirmation while no plan exists yet: must NOT advance, but
    #    the generated plan marks the subtask for the NEXT turn.
    resp = orchestrator.process_message(
        "conv-plan-1",
        SendOrchestratorMessageRequest(message="可以，继续吧"),
        db_session,
    )
    assert resp.state.current_stage == "research_plan"
    assert resp.state.subtasks.plan_generated is True

    state_row = db_session.get(ResearchOrchestratorStateModel, "conv-plan-1")
    # The plan itself is NOT yet user-confirmed: no version may be recorded.
    assert state_row.current_plan is None
    assert state_row.plan_history == []

    # 2. Explicit confirmation after seeing the plan completes stage two.
    resp = orchestrator.process_message(
        "conv-plan-1",
        SendOrchestratorMessageRequest(message="可以，就按这个计划来"),
        db_session,
    )
    assert resp.state.current_stage == "research_execution"
    assert "research_plan" in resp.state.completed_stages

    state_row = db_session.get(ResearchOrchestratorStateModel, "conv-plan-1")
    assert state_row.current_plan is not None
    assert state_row.current_plan["version"] == 1
    assert "执行计划" in state_row.current_plan["content"]
    assert state_row.current_plan["confirmed_by"] == "user_confirmation"
    assert len(state_row.plan_history) == 1
    assert state_row.plan_history[0]["version"] == 1


def test_reconfirmed_plan_creates_version_two_and_keeps_history(db_session) -> None:
    """A second confirmed plan (e.g. after updating constraints) must create a
    new version; the latest confirmed version becomes current, old stays in
    history (contract §7)."""
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=SequencedOrchestratorLlmGenerator(
            [
                "姜姜结合你的画像整理了一份执行计划，我们先从数据准备开始 (｡･ω･｡)",
                "姜姜根据新的时间安排整理了第二版计划，先补齐前置知识再复现 (｡･ω･｡)",
            ]
        )
    )
    conv = ResearchConversationModel(id="conv-plan-2", profile_data={}, messages_data=[])
    db_session.add(conv)
    _make_plan_stage_state(db_session, "conv-plan-2")

    # First plan cycle.
    orchestrator.process_message(
        "conv-plan-2",
        SendOrchestratorMessageRequest(message="可以，继续吧"),
        db_session,
    )
    resp = orchestrator.process_message(
        "conv-plan-2",
        SendOrchestratorMessageRequest(message="可以，就按这个计划来"),
        db_session,
    )
    assert resp.state.current_stage == "research_execution"

    # Re-plan cycle (e.g. after a direction change reset the subtasks).
    state_row = db_session.get(ResearchOrchestratorStateModel, "conv-plan-2")
    state_row.current_stage = "research_plan"
    state_row.subtasks = {
        "need_defined": True,
        "profile_ready": True,
        "plan_generated": False,
    }
    db_session.commit()

    orchestrator.process_message(
        "conv-plan-2",
        SendOrchestratorMessageRequest(message="请根据新的每周时间安排更新计划"),
        db_session,
    )
    resp = orchestrator.process_message(
        "conv-plan-2",
        SendOrchestratorMessageRequest(message="可以，就按新的计划来"),
        db_session,
    )
    assert resp.state.current_stage == "research_execution"

    state_row = db_session.get(ResearchOrchestratorStateModel, "conv-plan-2")
    assert state_row.current_plan["version"] == 2
    assert "第二版计划" in state_row.current_plan["content"]
    assert len(state_row.plan_history) == 2
    assert state_row.plan_history[0]["version"] == 1
    assert "执行计划" in state_row.plan_history[0]["content"]
    assert state_row.plan_history[1]["version"] == 2


def _seed_current_paper(db_session, conversation_id: str) -> None:
    from code_navi.research.models import ResearchOrchestratorPaperModel

    db_session.add(
        ResearchOrchestratorPaperModel(
            conversation_id=conversation_id,
            paper_url="https://arxiv.org/abs/1609.02907",
            title="Semi-Supervised Classification with Graph Convolutional Networks",
            purpose="replace",
            is_current=True,
            metadata_snapshot={},
        )
    )
    db_session.commit()


def test_specific_experiment_plan_requires_current_paper(db_session) -> None:
    """具体实验方案的生成前提是已选当前论文（设计文档：初步/具体方案层次）。

    Without a current paper the orchestrator must NOT generate a specific
    experiment plan (must stay on retrieval / paper-introduction guidance),
    and ``experiment_designed`` must stay False.
    """
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=SequencedOrchestratorLlmGenerator(
            ["姜姜结合论文与你的设备整理了具体实验安排，我们先准备数据集 (｡･ω･｡)"]
        )
    )
    conv = ResearchConversationModel(id="conv-exec-1", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.add(
        ResearchOrchestratorStateModel(
            conversation_id="conv-exec-1",
            current_stage="research_execution",
            completed_stages=["research_need", "research_plan"],
            subtasks={
                "need_defined": True,
                "profile_ready": True,
                "plan_generated": True,
                "paper_selected": False,
                "experiment_designed": False,
            },
            direction_history=[],
            plan_history=[],
        )
    )
    db_session.commit()

    # 1. No current paper: a design request must not produce a specific
    #    experiment plan nor mark the subtask.
    resp = orchestrator.process_message(
        "conv-exec-1",
        SendOrchestratorMessageRequest(
            message="帮我制定一份具体的实验安排，包括数据准备和训练流程"
        ),
        db_session,
    )
    assert resp.state.current_stage == "research_execution"
    assert resp.state.subtasks.experiment_designed is False

    # 2. With the current paper selected (papers/select effect: current paper
    #    row + paper_selected subtask), the design request generates the
    #    PRELIMINARY plan (P2-C two-layer contract) without lighting the
    #    subtask.
    _seed_current_paper(db_session, "conv-exec-1")
    state_row = db_session.get(ResearchOrchestratorStateModel, "conv-exec-1")
    state_row.subtasks = {
        "need_defined": True,
        "profile_ready": True,
        "plan_generated": True,
        "paper_selected": True,
        "experiment_designed": False,
    }
    db_session.commit()
    resp = orchestrator.process_message(
        "conv-exec-1",
        SendOrchestratorMessageRequest(
            message="帮我制定一份具体的实验安排，包括数据准备和训练流程"
        ),
        db_session,
    )
    assert resp.state.current_stage == "research_execution"
    assert resp.state.subtasks.experiment_designed is False

    # 3. Explicit confirmation turns the preliminary plan into the SPECIFIC
    #    plan; only now does experiment_designed light up.
    resp = orchestrator.process_message(
        "conv-exec-1",
        SendOrchestratorMessageRequest(message="可以，就按初步方案细化。"),
        db_session,
    )
    assert resp.state.current_stage == "research_execution"
    assert resp.state.subtasks.experiment_designed is True

    # 4. Paper selected + specific plan generated + explicit confirmation:
    #    only now may research_analysis begin.
    resp = orchestrator.process_message(
        "conv-exec-1",
        SendOrchestratorMessageRequest(message="可以，确认进入结果分析"),
        db_session,
    )
    assert resp.state.current_stage == "research_analysis"
    assert "research_execution" in resp.state.completed_stages


def test_execution_stage_requires_paper_and_design_together(db_session) -> None:
    """已选当前论文但未完成实验方案：不能进入结果分析；反之亦然。"""
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=SequencedOrchestratorLlmGenerator(
            ["姜姜陪你继续推进当前阶段 (｡･ω･｡)"]
        )
    )
    conv = ResearchConversationModel(id="conv-exec-2", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.add(
        ResearchOrchestratorStateModel(
            conversation_id="conv-exec-2",
            current_stage="research_execution",
            completed_stages=["research_need", "research_plan"],
            subtasks={
                "need_defined": True,
                "profile_ready": True,
                "plan_generated": True,
                "paper_selected": True,
                "experiment_designed": False,
            },
            direction_history=[],
            plan_history=[],
        )
    )
    db_session.commit()

    # Paper selected but no experiment design yet: confirmation must NOT pass.
    resp = orchestrator.process_message(
        "conv-exec-2",
        SendOrchestratorMessageRequest(message="可以，确认进入结果分析"),
        db_session,
    )
    assert resp.state.current_stage == "research_execution"

    # Design exists but no paper selected: confirmation must NOT pass either.
    state_row = db_session.get(ResearchOrchestratorStateModel, "conv-exec-2")
    state_row.subtasks = {
        "need_defined": True,
        "profile_ready": True,
        "plan_generated": True,
        "paper_selected": False,
        "experiment_designed": True,
    }
    db_session.commit()
    resp = orchestrator.process_message(
        "conv-exec-2",
        SendOrchestratorMessageRequest(message="可以，确认进入结果分析"),
        db_session,
    )
    assert resp.state.current_stage == "research_execution"


def test_plan_snapshot_requires_traceable_plan_message(db_session) -> None:
    """P0-2: without a traceable ``profile_and_plan`` message, confirming the
    plan must not fabricate a version from the welcome / paper-intro /
    stage-transition reply (or any arbitrary assistant message)."""
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=SequencedOrchestratorLlmGenerator(
            ["姜姜陪你继续推进当前阶段 (｡･ω･｡)"]
        )
    )
    conv = ResearchConversationModel(
        id="conv-plan-3",
        profile_data={},
        messages_data=[
            {
                "message_id": "msg-welcome",
                "role": "assistant",
                "content": "(＾▽＾) 欢迎来到科研端！这是欢迎语，不是研究计划。",
                "template": "welcome_and_bridge",
                "created_at": "2026-09-05T09:00:00+00:00",
            }
        ],
    )
    db_session.add(conv)
    db_session.add(
        ResearchOrchestratorStateModel(
            conversation_id="conv-plan-3",
            current_stage="research_plan",
            completed_stages=["research_need"],
            subtasks={
                "need_defined": True,
                "profile_ready": True,
                "plan_generated": True,
            },
            direction_history=[],
            plan_history=[],
        )
    )
    db_session.commit()

    resp = orchestrator.process_message(
        "conv-plan-3",
        SendOrchestratorMessageRequest(message="可以，就按这个计划来"),
        db_session,
    )
    # The stage still completes (subtasks + confirmation are genuine), but no
    # plan version may be recorded without a traceable plan message.
    assert resp.state.current_stage == "research_execution"
    state_row = db_session.get(ResearchOrchestratorStateModel, "conv-plan-3")
    assert state_row.current_plan is None
    assert state_row.plan_history == []


def test_direction_change_preserves_history_while_resetting_stage(db_session) -> None:
    """换方向：保留历史，回到 research_need 重建当前方案（契约 §2）。

    Freeze that a direction change keeps ``completed_stages`` and records the
    new direction in ``direction_history`` instead of wiping history.
    """
    orchestrator = ResearchConversationOrchestrator()
    conv = ResearchConversationModel(id="conv-sm-dir-hist", profile_data={}, messages_data=[])
    db_session.add(conv)
    db_session.add(
        ResearchOrchestratorStateModel(
            conversation_id="conv-sm-dir-hist",
            current_stage="research_execution",
            completed_stages=["research_need", "research_plan"],
            subtasks={"need_defined": True, "profile_ready": True, "plan_generated": True},
            direction_history=[],
            plan_history=[],
        )
    )
    db_session.commit()

    resp = orchestrator.process_message(
        "conv-sm-dir-hist",
        SendOrchestratorMessageRequest(message="我想换个方向，改做图对比学习"),
        db_session,
    )
    assert resp.state.current_stage == "research_need"
    # History is preserved, not wiped.
    assert "research_need" in resp.state.completed_stages
    assert "research_plan" in resp.state.completed_stages
    assert len(resp.state.direction_history) == 1


def _put_learning(orchestrator, conv_id: str, learned: str, progress: str | None, db) -> None:
    orchestrator.update_learning_context(
        conv_id,
        LearningContextInput(learned_content=learned, learning_progress=progress),
        db,
    )


def _select_welcome_prompt(orchestrator, conv_id: str, db) -> dict:
    return orchestrator._select_prompt_template(
        conv_id,
        current_stage="research_need",
        subtasks={"need_defined": False},
        user_message="你好姜姜，我回来继续做科研了。",
        is_confirmed=False,
        db=db,
        owned_ids=None,
    )


def test_first_learning_write_welcome_and_cards(db_session) -> None:
    """1. 首次写入学习上下文：欢迎模板引用学习内容，方向卡正常生成。"""
    orchestrator = ResearchConversationOrchestrator(llm_generator=FakeOrchestratorLlmGenerator())
    conv_id = "conv-incr-1"
    db_session.add(ResearchConversationModel(id=conv_id, profile_data={}, messages_data=[]))
    db_session.commit()
    _put_learning(
        orchestrator, conv_id, "图卷积网络(GCN)谱卷积与消息传递", "完成理论推导", db_session
    )

    prompt = _select_welcome_prompt(orchestrator, conv_id, db_session)
    assert prompt["template_name"] == "welcome_and_bridge"
    assert "图卷积网络(GCN)" in prompt["user_prompt"]

    cards = orchestrator.get_direction_cards(conv_id, db_session).cards
    assert len(cards) == 5

    # A successful welcome turn marks the context as consumed.
    orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="你好姜姜，我回来继续做科研了。"),
        db_session,
    )
    state_row = db_session.get(ResearchOrchestratorStateModel, conv_id)
    ctx = state_row.learning_context or {}
    assert ctx["consumed_learned_content"] == "图卷积网络(GCN)谱卷积与消息传递"
    assert ctx["consumed_learning_progress"] == "完成理论推导"


def test_reentry_with_consumed_context_does_not_repeat_delta(db_session) -> None:
    """2. 同一学习上下文再次恢复：不得重复注入“新增学习内容”提示。"""
    orchestrator = ResearchConversationOrchestrator(llm_generator=FakeOrchestratorLlmGenerator())
    conv_id = "conv-incr-2"
    db_session.add(ResearchConversationModel(id=conv_id, profile_data={}, messages_data=[]))
    db_session.commit()
    _put_learning(orchestrator, conv_id, "GCN 谱方法", None, db_session)
    # First recovery absorbs the initial learning input.
    orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="你好姜姜，我回来继续做科研了。"),
        db_session,
    )
    # Real learning progress arrives afterwards.
    _put_learning(
        orchestrator, conv_id, "GCN 谱方法；GraphSAGE 邻居采样", "完成 GraphSAGE 推导", db_session
    )
    prompt = _select_welcome_prompt(orchestrator, conv_id, db_session)
    assert "新增学习内容" in prompt["user_prompt"]
    # The recovery turn absorbs the delta exactly once.
    orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="你好姜姜，我回来继续做科研了。"),
        db_session,
    )

    # Re-entry WITHOUT any new learning input (no re-PUT): no repeated delta.
    prompt = _select_welcome_prompt(orchestrator, conv_id, db_session)
    assert "新增学习内容" not in prompt["user_prompt"]

    # The confirm page re-PUTs the same values on every entry: still no delta,
    # and the consumed markers must survive the re-PUT.
    _put_learning(
        orchestrator,
        conv_id,
        "GCN 谱方法；GraphSAGE 邻居采样",
        "完成 GraphSAGE 推导",
        db_session,
    )
    prompt = _select_welcome_prompt(orchestrator, conv_id, db_session)
    assert "新增学习内容" not in prompt["user_prompt"]


def test_real_learning_change_explains_only_the_increment(db_session) -> None:
    """3. 真实新增后，下一次恢复只说明增量及其与当前研究的关系。"""
    orchestrator = ResearchConversationOrchestrator(llm_generator=FakeOrchestratorLlmGenerator())
    conv_id = "conv-incr-3"
    db_session.add(ResearchConversationModel(id=conv_id, profile_data={}, messages_data=[]))
    db_session.commit()
    _put_learning(orchestrator, conv_id, "GCN 谱方法", None, db_session)
    orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="你好姜姜，我回来继续做科研了。"),
        db_session,
    )

    _put_learning(
        orchestrator,
        conv_id,
        "GCN 谱方法；GraphSAGE 邻居采样",
        "完成 GraphSAGE 推导",
        db_session,
    )
    prompt = _select_welcome_prompt(orchestrator, conv_id, db_session)
    assert prompt["template_name"] == "welcome_and_bridge"
    assert "GraphSAGE 邻居采样" in prompt["user_prompt"]
    # The absorbed baseline stays visible; only the increment is explained.
    assert "GCN 谱方法" in prompt["user_prompt"]
    assert "与当前研究方向" in prompt["user_prompt"]
    assert "不得据此推断掌握度" in prompt["user_prompt"]

    # The historical learning content is preserved in the persisted context.
    state_row = db_session.get(ResearchOrchestratorStateModel, conv_id)
    ctx = state_row.learning_context or {}
    assert "GCN 谱方法" in (ctx.get("learned_content") or "")


PAPER_URL = "https://arxiv.org/abs/1609.02907"
PAPER_TITLE = "Semi-Supervised Classification with Graph Convolutional Networks"
CLICK_MESSAGE = f"我想选择这篇论文作为复现候选：《{PAPER_TITLE}》 {PAPER_URL}"


def _make_execution_state(db, conv_id: str) -> ResearchOrchestratorStateModel:
    state_model = ResearchOrchestratorStateModel(
        conversation_id=conv_id,
        current_stage="research_execution",
        completed_stages=["research_need", "research_plan"],
        subtasks={
            "need_defined": True,
            "profile_ready": True,
            "plan_generated": True,
            "paper_selected": False,
            "experiment_designed": False,
        },
        direction_history=[],
        plan_history=[],
    )
    db.add(state_model)
    db.commit()
    return state_model


def _last_message_template(db, conv_id: str) -> str | None:
    conv = db.get(ResearchConversationModel, conv_id)
    msgs = conv.messages_data or []
    return msgs[-1].get("template") if msgs else None


def test_paper_submission_only_introduces_without_selecting(db_session) -> None:
    """点击/提交候选论文只触发精读式介绍，不设置当前论文。"""
    orchestrator = ResearchConversationOrchestrator(llm_generator=FakeOrchestratorLlmGenerator())
    conv_id = "conv-paper-1"
    db_session.add(ResearchConversationModel(id=conv_id, profile_data={}, messages_data=[]))
    _make_execution_state(db_session, conv_id)

    resp = orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message=CLICK_MESSAGE),
        db_session,
    )
    assert resp.status == "completed"
    assert resp.state.current_stage == "research_execution"
    assert resp.state.subtasks.paper_selected is False
    papers = orchestrator.get_papers(conv_id, db_session)
    assert papers.current_paper is None
    # The turn must be the paper-introduction turn, not an unrelated template.
    assert _last_message_template(db_session, conv_id) == "paper_intro"


def test_explicit_confirmation_after_intro_selects_current_paper(db_session) -> None:
    """明确确认（就选这篇）之后才写入单一当前论文并点亮 paper_selected。"""
    orchestrator = ResearchConversationOrchestrator(llm_generator=FakeOrchestratorLlmGenerator())
    conv_id = "conv-paper-2"
    db_session.add(ResearchConversationModel(id=conv_id, profile_data={}, messages_data=[]))
    _make_execution_state(db_session, conv_id)

    orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message=CLICK_MESSAGE),
        db_session,
    )
    resp = orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="可以，就选这篇。"),
        db_session,
    )
    papers = orchestrator.get_papers(conv_id, db_session)
    assert papers.current_paper is not None
    assert papers.current_paper.paper_url == PAPER_URL
    assert papers.current_paper.purpose == "replace"
    assert resp.state.subtasks.paper_selected is True
    # Selection alone does not complete the execution stage.
    assert resp.state.current_stage == "research_execution"


def test_vague_answer_does_not_select_paper(db_session) -> None:
    """模糊答复不选择论文，停留在介绍/确认。"""
    orchestrator = ResearchConversationOrchestrator(llm_generator=FakeOrchestratorLlmGenerator())
    conv_id = "conv-paper-3"
    db_session.add(ResearchConversationModel(id=conv_id, profile_data={}, messages_data=[]))
    _make_execution_state(db_session, conv_id)

    orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message=CLICK_MESSAGE),
        db_session,
    )
    resp = orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="让我再想想，还不太确定"),
        db_session,
    )
    papers = orchestrator.get_papers(conv_id, db_session)
    assert papers.current_paper is None
    assert resp.state.subtasks.paper_selected is False
    assert resp.state.current_stage == "research_execution"


def test_new_candidate_with_current_paper_asks_purpose_first(db_session) -> None:
    """已有当前论文时提交新论文：先问 replace / compare / cite，不直接替换。"""
    orchestrator = ResearchConversationOrchestrator(llm_generator=FakeOrchestratorLlmGenerator())
    conv_id = "conv-paper-4"
    db_session.add(ResearchConversationModel(id=conv_id, profile_data={}, messages_data=[]))
    _make_execution_state(db_session, conv_id)
    orchestrator.select_paper(
        conv_id,
        SelectPaperRequest(paper_url=PAPER_URL, title=PAPER_TITLE, purpose="replace", metadata={}),
        db_session,
    )
    other_url = "https://arxiv.org/abs/2009.13805"

    resp = orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(
            message=f"我想选择这篇论文作为复现候选：《Graph Attention Networks》 {other_url}"
        ),
        db_session,
    )
    papers = orchestrator.get_papers(conv_id, db_session)
    assert papers.current_paper is not None
    assert papers.current_paper.paper_url == PAPER_URL  # unchanged
    assert resp.reply_message is not None
    reply_text = resp.reply_message.content
    assert "替换" in reply_text and "对比" in reply_text and "引用" in reply_text


def test_purpose_answers_map_to_replace_compare_cite(db_session) -> None:
    """replace 更新当前论文；compare/cite 只记录历史、不覆盖当前论文。"""
    orchestrator = ResearchConversationOrchestrator(llm_generator=FakeOrchestratorLlmGenerator())
    conv_id = "conv-paper-5"
    db_session.add(ResearchConversationModel(id=conv_id, profile_data={}, messages_data=[]))
    _make_execution_state(db_session, conv_id)
    orchestrator.select_paper(
        conv_id,
        SelectPaperRequest(paper_url=PAPER_URL, title=PAPER_TITLE, purpose="replace", metadata={}),
        db_session,
    )
    url_b = "https://arxiv.org/abs/1710.10903"
    url_c = "https://arxiv.org/abs/1810.04805"

    # compare: history only, current unchanged.
    orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message=f"我想选择这篇论文作为复现候选：《GAT》 {url_b}"),
        db_session,
    )
    resp = orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="这篇用于对比阅读。"),
        db_session,
    )
    papers = orchestrator.get_papers(conv_id, db_session)
    assert papers.current_paper is not None
    assert papers.current_paper.paper_url == PAPER_URL
    assert any(p.paper_url == url_b and p.purpose == "compare" for p in papers.paper_history)

    # cite: history only, current unchanged.
    orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message=f"我想选择这篇论文作为复现候选：《BERT》 {url_c}"),
        db_session,
    )
    orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="这篇仅作引用整理。"),
        db_session,
    )
    papers = orchestrator.get_papers(conv_id, db_session)
    assert papers.current_paper.paper_url == PAPER_URL
    assert any(p.paper_url == url_c and p.purpose == "cite" for p in papers.paper_history)

    # replace: current paper switches.
    url_d = "https://arxiv.org/abs/1811.05268"
    orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(
            message=f"我想选择这篇论文作为复现候选：《GraphSAGE》 {url_d}"
        ),
        db_session,
    )
    orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="就替换吧，把这篇设为当前论文。"),
        db_session,
    )
    papers = orchestrator.get_papers(conv_id, db_session)
    assert papers.current_paper is not None
    assert papers.current_paper.paper_url == url_d
    assert papers.current_paper.purpose == "replace"
    assert resp.state.subtasks.paper_selected is True


def test_paper_flow_respects_owner_404_isolation(db_session) -> None:
    """跨 owner 访问论文确认流返回 404 隔离（不泄露存在性）。"""
    orchestrator = ResearchConversationOrchestrator(llm_generator=FakeOrchestratorLlmGenerator())
    conv_id = "conv-paper-6"
    db_session.add(
        ResearchConversationModel(
            id=conv_id, profile_data={}, messages_data=[], owner_principal_id="owner-a"
        )
    )
    _make_execution_state(db_session, conv_id)

    with pytest.raises(ConversationNotFoundError):
        orchestrator.process_message(
            conv_id,
            SendOrchestratorMessageRequest(message=CLICK_MESSAGE),
            db_session,
            owned_ids=["owner-b"],
        )
    with pytest.raises(ConversationNotFoundError):
        orchestrator.get_papers(conv_id, db_session, owned_ids=["owner-b"])


def test_preliminary_and_specific_plans_are_two_steps(db_session) -> None:
    """P2-C: 初步方案与具体实验方案分两步；仅具体方案点亮 experiment_designed。"""
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=SequencedOrchestratorLlmGenerator(
            [
                "姜姜先用通俗语言整理初步方案：准备复现什么、用到哪些方法 (｡･ω･｡)",
                "姜姜把初步方案细化为具体实验方案，日程继承第二阶段总体计划 (｡･ω･｡)",
            ]
        )
    )
    conv_id = "conv-twolayer-1"
    db_session.add(ResearchConversationModel(id=conv_id, profile_data={}, messages_data=[]))
    state_row = _make_execution_state(db_session, conv_id)
    _seed_current_paper(db_session, conv_id)
    state_row.subtasks = {
        "need_defined": True,
        "profile_ready": True,
        "plan_generated": True,
        "paper_selected": True,
        "experiment_designed": False,
    }
    db_session.commit()

    # Step 1: preliminary plan request -> generated, but experiment_designed
    # must stay False (a preliminary plan alone cannot unlock analysis).
    resp = orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="帮我制定一份初步方案，先看看要做哪些准备"),
        db_session,
    )
    assert resp.state.current_stage == "research_execution"
    assert resp.state.subtasks.experiment_designed is False
    conv = db_session.get(ResearchConversationModel, conv_id)
    last = (conv.messages_data or [])[-1]
    assert last["template"] == "experiment_design"
    assert last["plan_layer"] == "preliminary"

    # Step 2: user confirms the preliminary plan -> the SPECIFIC plan is
    # generated (model/data flow/schedule inherited from the overall plan),
    # and only now experiment_designed lights up.
    resp = orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="可以，初步方案就这样，细化成具体方案吧"),
        db_session,
    )
    assert resp.state.current_stage == "research_execution"
    assert resp.state.subtasks.experiment_designed is True
    conv = db_session.get(ResearchConversationModel, conv_id)
    last = (conv.messages_data or [])[-1]
    assert last["plan_layer"] == "specific"

    # Step 3: explicit confirmation completes the execution stage.
    resp = orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="可以，确认进入结果分析"),
        db_session,
    )
    assert resp.state.current_stage == "research_analysis"


def test_specific_plan_prompt_inherits_overall_plan(db_session) -> None:
    """具体方案必须继承第二阶段总体计划，不能生成冲突的第二套日程。"""
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=FakeOrchestratorLlmGenerator()
    )
    conv_id = "conv-twolayer-2"
    db_session.add(ResearchConversationModel(id=conv_id, profile_data={}, messages_data=[]))
    state_row = _make_execution_state(db_session, conv_id)
    _seed_current_paper(db_session, conv_id)
    plan_entry = {
        "version": 1,
        "content": "总体计划：第1-3天准备数据，第4-6天复现基线并记录。",
        "confirmed_by": "user_confirmation",
    }
    state_row.current_plan = plan_entry
    state_row.plan_history = [plan_entry]
    # Preliminary plan already generated and confirmed next.
    conv = db_session.get(ResearchConversationModel, conv_id)
    conv.messages_data = [
        {
            "message_id": "m1",
            "role": "assistant",
            "content": "初步方案内容",
            "template": "experiment_design",
            "plan_layer": "preliminary",
            "created_at": "2026-09-05T09:00:00+00:00",
        }
    ]
    db_session.commit()

    prompt = orchestrator._select_prompt_template(
        conv_id,
        current_stage="research_execution",
        subtasks={
            "need_defined": True,
            "profile_ready": True,
            "plan_generated": True,
            "paper_selected": True,
            "experiment_designed": False,
        },
        user_message="可以，就按初步方案细化。",
        is_confirmed=True,
        db=db_session,
        owned_ids=None,
    )
    assert prompt["template_name"] == "experiment_design"
    assert prompt["plan_layer"] == "specific"
    assert "第1-3天准备数据" in prompt["user_prompt"]
    assert "继承" in prompt["user_prompt"] or "总体计划" in prompt["user_prompt"]


def test_two_layer_plan_template_boundary_rules() -> None:
    """初步方案不得宣称已执行/完成；具体方案必须继承总体计划。"""
    from code_navi.research.conversation_prompt_templates import (
        build_experiment_design_prompt,
    )

    profile = LearnerProfileData(version=1)
    paper = CurrentPaperCard(
        id="p1",
        paper_url=PAPER_URL,
        title=PAPER_TITLE,
        purpose="replace",
        selected_at=datetime.now(UTC),
    )
    preliminary = build_experiment_design_prompt(
        paper=paper, profile=profile, standard_metrics=["Accuracy"], plan_layer="preliminary"
    )
    specific = build_experiment_design_prompt(
        paper=paper, profile=profile, standard_metrics=["Accuracy"], plan_layer="specific"
    )
    assert "初步方案" in preliminary["task"] + preliminary["rules"]
    assert "不得声称" in preliminary["rules"] and "复现成功" in preliminary["rules"]
    assert "具体实验方案" in specific["task"] + specific["rules"]
    assert "继承" in specific["rules"] and "第二套日程" in specific["rules"]
    assert "验收标准" in specific["rules"]


# ---------------- P3-A: formal search -> candidate cards -> confirm ----------------

class FakeSearchService:
    """Stands in for the real ResearchConversationSearchService.search()."""

    def __init__(self, bundle=None, error: Exception | None = None) -> None:
        self.bundle = bundle
        self.error = error
        self.calls: list[str] = []

    def search(self, conversation_id, request, db):
        self.calls.append(request.query or "")
        if self.error is not None:
            raise self.error
        return self.bundle


def _make_evidence_bundle(conv_id: str, papers: list) -> ConversationEvidenceBundle:
    return ConversationEvidenceBundle(
        bundle_id="bundle-1",
        conversation_id=conv_id,
        query="GCN oversmoothing",
        requested_sources=["openalex", "crossref", "arxiv"],
        allowed_sources=["openalex", "crossref", "arxiv"],
        queried_sources=["openalex", "crossref", "arxiv"],
        source_statuses=[
            AcademicSourceStatus(
                source="arxiv", status="success", accessed_at=datetime.now(UTC)
            ),
        ],
        searched_at=datetime.now(UTC),
        papers=papers,
        source_links=[None for _ in papers],
        failure_reasons=[],
        provenance_note="metadata and abstract only",
    )


def _real_paper(title: str, url: str, year: int = 2017) -> AcademicPaperResult:
    return AcademicPaperResult(
        title=title,
        authors=["Kipf", "Welling"],
        year=year,
        source_name="arXiv",
        url=url,
        accessed_at=datetime.now(UTC),
        information_scope="metadata_and_abstract_only",
        metadata_evidence=[],
        supporting_snippets=[],
        abstract_excerpt="Graph convolutional networks (GCNs) oversmooth with depth.",
        relevance=EvidenceStatement(
            content="与检索词直接相关",
            classification="fact",
            basis="来自检索结果的元数据匹配",
        ),
        verification=EvidenceStatement(
            content="元数据来自公开检索来源",
            classification="fact",
            basis="检索来源记录",
        ),
        full_text_available=False,
    )


def test_unconfirmed_search_terms_do_not_trigger_real_search(db_session) -> None:
    """1. 未明确确认检索词，不得触发正式检索。"""
    search_service = FakeSearchService()
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=FakeOrchestratorLlmGenerator(), search_service=search_service
    )
    conv_id = "conv-search-1"
    db_session.add(ResearchConversationModel(id=conv_id, profile_data={}, messages_data=[]))
    _make_execution_state(db_session, conv_id)

    resp = orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="我想检索一下 GCN 过平滑的相关论文"),
        db_session,
    )
    assert search_service.calls == []  # no network search without confirmation
    assert resp.state.current_stage == "research_execution"


def test_confirmed_search_runs_real_search_and_lists_candidates(db_session) -> None:
    """2. 明确确认后真实检索，回复只列真实检索结果的标题/来源/年份。"""
    paper = _real_paper(PAPER_TITLE, PAPER_URL)
    search_service = FakeSearchService(
        bundle=_make_evidence_bundle("conv-search-2", [paper])
    )
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=FakeOrchestratorLlmGenerator(), search_service=search_service
    )
    conv_id = "conv-search-2"
    db_session.add(ResearchConversationModel(id=conv_id, profile_data={}, messages_data=[]))
    _make_execution_state(db_session, conv_id)

    resp = orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="确认检索：GCN oversmoothing"),
        db_session,
    )
    # The search ran once with the user's terms (trigger words stripped).
    assert len(search_service.calls) == 1
    assert "GCN oversmoothing" in search_service.calls[0]
    assert "确认检索" not in search_service.calls[0]
    # The reply presents the REAL result metadata only.
    reply_text = resp.reply_message.content
    assert PAPER_TITLE in reply_text
    assert "arXiv" in reply_text
    assert "2017" in reply_text
    assert PAPER_URL in reply_text
    # Selection state untouched: candidates are not papers yet.
    papers = orchestrator.get_papers(conv_id, db_session)
    assert papers.current_paper is None
    assert resp.state.subtasks.paper_selected is False
    assert resp.state.current_stage == "research_execution"


def test_search_empty_state_is_explicit(db_session) -> None:
    """6a. 检索无结果时明确空态，不编造候选。"""
    search_service = FakeSearchService(
        bundle=_make_evidence_bundle("conv-search-3", [])
    )
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=FakeOrchestratorLlmGenerator(), search_service=search_service
    )
    conv_id = "conv-search-3"
    db_session.add(ResearchConversationModel(id=conv_id, profile_data={}, messages_data=[]))
    _make_execution_state(db_session, conv_id)

    resp = orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="确认检索：非常生僻的查询词"),
        db_session,
    )
    reply_text = resp.reply_message.content
    assert "没有检索到" in reply_text or "无结果" in reply_text
    assert PAPER_TITLE not in reply_text


def test_search_failure_is_explicit(db_session) -> None:
    """6b. 检索服务失败时显式说明，不编造结果。"""
    search_service = FakeSearchService(error=RuntimeError("all sources timed out"))
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=FakeOrchestratorLlmGenerator(), search_service=search_service
    )
    conv_id = "conv-search-4"
    db_session.add(ResearchConversationModel(id=conv_id, profile_data={}, messages_data=[]))
    _make_execution_state(db_session, conv_id)

    resp = orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="确认检索：GCN oversmoothing"),
        db_session,
    )
    reply_text = resp.reply_message.content
    assert "未成功" in reply_text or "失败" in reply_text or "暂时无法" in reply_text
    assert PAPER_TITLE not in reply_text


def test_search_flow_respects_owner_404_isolation(db_session) -> None:
    """6c. 跨 owner 无法触发检索（404 隔离不回归）。"""
    search_service = FakeSearchService()
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=FakeOrchestratorLlmGenerator(), search_service=search_service
    )
    conv_id = "conv-search-5"
    db_session.add(
        ResearchConversationModel(
            id=conv_id, profile_data={}, messages_data=[], owner_principal_id="owner-a"
        )
    )
    _make_execution_state(db_session, conv_id)

    with pytest.raises(ConversationNotFoundError):
        orchestrator.process_message(
            conv_id,
            SendOrchestratorMessageRequest(message="确认检索：GCN oversmoothing"),
            db_session,
            owned_ids=["owner-b"],
        )
    assert search_service.calls == []


class SinglePaperArxivSource:
    """Deterministic arXiv source for the real search-service integration path."""

    def search(self, query: str) -> AcademicSourceResult:
        return AcademicSourceResult.success(
            "arxiv",
            [
                PaperMetadata(
                    title=PAPER_TITLE,
                    authors=["Thomas Kipf", "Max Welling"],
                    year=2017,
                    source_name="arXiv",
                    url=PAPER_URL,
                    identifier="arXiv:1609.02907",
                    abstract_excerpt=f"Evidence for {query}",
                    accessed_at=datetime(2026, 8, 3, tzinfo=UTC),
                )
            ],
        )


def test_confirmed_user_query_runs_real_search_service_on_sparse_profile(db_session) -> None:
    """P3-A 集成：确认检索词经真实检索服务出候选；画像就绪门控只拦自动计划。"""
    search_service = ResearchConversationSearchService(
        search_tool=AcademicSearchTool({"arxiv": SinglePaperArxivSource()})
    )
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=FakeOrchestratorLlmGenerator(), search_service=search_service
    )
    conv_id = "conv-search-real-1"
    db_session.add(
        ResearchConversationModel(
            id=conv_id,
            profile_data={"topic": "图卷积网络 (GCN) 的研究延展与论文复现准备"},
            messages_data=[],
        )
    )
    _make_execution_state(db_session, conv_id)

    resp = orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="确认检索：GCN oversmoothing"),
        db_session,
    )
    reply_text = resp.reply_message.content
    assert PAPER_TITLE in reply_text
    assert "arXiv" in reply_text
    assert "2017" in reply_text
    assert PAPER_URL in reply_text
    # 候选不是当前论文：点击后介绍、明确确认才选定。
    papers = orchestrator.get_papers(conv_id, db_session)
    assert papers.current_paper is None
    assert resp.state.subtasks.paper_selected is False
    # 真实检索 bundle 持久化，作为前端候选论文卡的数据源。
    bundles = search_service.list_bundles(conv_id, db_session)
    assert len(bundles) == 1
    assert bundles[0].papers[0].url == PAPER_URL
    # 同一稀疏画像下，缺少用户检索词的自动计划仍被就绪门控拒绝。
    with pytest.raises(ConversationSearchNotReadyError):
        search_service.search(
            conv_id, CreateConversationEvidenceBundleRequest(), db_session
        )


# ---------------- P3-B: passive experiment-design tool must not bypass gates ----------------

class PromptCapturingGenerator(FakeOrchestratorLlmGenerator):
    def __init__(self) -> None:
        self.system_prompts: list[str] = []
        self.user_prompts: list[str] = []
        self.calls = 0

    def generate(self, *, system_prompt: str, user_prompt: str, **kwargs):
        from code_navi.research.conversation_orchestrator import OrchestratorLlmOutcome

        self.system_prompts.append(system_prompt)
        self.user_prompts.append(user_prompt)
        self.calls += 1
        return OrchestratorLlmOutcome(
            status="generated",
            reply_text="姜姜基于工具真实输出为你解释实验设计素材 (｡･ω･｡)",
        )


@pytest.mark.parametrize(
    "message",
    ["帮我设计实验", "实验方案怎么做", "怎么跑"],
)
def test_passive_experiment_design_does_not_bypass_two_layer_gate(
    db_session, message
) -> None:
    """P3-B: 被动 experiment-design 工具不点亮 experiment_designed、不推进阶段，
    且姜姜必须询问是否基于工具结果生成初步实验方案。"""
    generator = PromptCapturingGenerator()
    orchestrator = ResearchConversationOrchestrator(llm_generator=generator)
    conv_id = f"conv-p3b-{abs(hash(message))}"
    db_session.add(ResearchConversationModel(id=conv_id, profile_data={}, messages_data=[]))
    state_row = _make_execution_state(db_session, conv_id)
    _seed_current_paper(db_session, conv_id)
    state_row.subtasks = {
        "need_defined": True,
        "profile_ready": True,
        "plan_generated": True,
        "paper_selected": True,
        "experiment_designed": False,
    }
    db_session.commit()

    resp = orchestrator.process_message(
        conv_id, SendOrchestratorMessageRequest(message=message), db_session
    )
    assert resp.reply_message is not None
    assert resp.reply_message.passive_tool_called == "experiment-design"
    # Two-layer gate untouched by the passive tool.
    assert resp.state.subtasks.experiment_designed is False
    assert resp.state.current_stage == "research_execution"
    # With a current paper, 姜姜 must ask about generating the preliminary plan.
    assert any("初步实验方案" in p for p in generator.system_prompts)


@pytest.mark.parametrize(
    "message",
    ["帮我设计实验", "实验方案怎么做", "怎么跑"],
)
def test_passive_experiment_design_without_paper_prompts_selection(
    db_session, message
) -> None:
    """P3-B: 无当前论文时提示先检索/选定论文，不生成具体方案。"""
    generator = PromptCapturingGenerator()
    orchestrator = ResearchConversationOrchestrator(llm_generator=generator)
    conv_id = f"conv-p3b-nopaper-{abs(hash(message))}"
    db_session.add(ResearchConversationModel(id=conv_id, profile_data={}, messages_data=[]))
    _make_execution_state(db_session, conv_id)

    resp = orchestrator.process_message(
        conv_id, SendOrchestratorMessageRequest(message=message), db_session
    )
    assert resp.reply_message is not None
    assert resp.reply_message.passive_tool_called == "experiment-design"
    assert resp.state.subtasks.experiment_designed is False
    assert resp.state.current_stage == "research_execution"
    assert any("选定论文" in p or "检索" in p for p in generator.system_prompts)


def test_experiment_plan_unified_preliminary_to_specific_progression(
    db_session,
) -> None:
    """Unify 草案、具体方案与可推进状态:
    1. Passive tool when paper is selected and ready records preliminary plan_layer;
    2. Confirmation turn ('确认初步方案，生成具体方案') bypasses passive tool trap
       and generates specific plan;
    3. Specific plan lights experiment_designed = True (achieving 可推进状态).
    """
    class SpecificPlanGenerator:
        def generate(self, *, system_prompt: str, user_prompt: str, **kwargs):
            from code_navi.research.conversation_orchestrator import OrchestratorLlmOutcome
            # Specific plan discussing hardware parameters in a legitimate plan
            return OrchestratorLlmOutcome(
                status="generated",
                reply_text=(
                    "说明：以下内容基于会话状态中已确认的研究方向、当前可用的论文/实验信息及通用技术概览，"
                    "尚未执行正式检索；具体论文细节、实现细节和实验结论仍需在你确认后核验。\n\n"
                    "【具体实验方案】\n"
                    "基于你的 8GB 显存设备，我们将 batch size 设为 4，使用梯度累积，"
                    "在当前硬件配置下方案可行，满足基线实验条件。\n"
                    "任务拆分与验收标准已就绪。"
                ),
            )

    generator = SpecificPlanGenerator()
    orchestrator = ResearchConversationOrchestrator(llm_generator=generator)
    conv_id = "conv-unified-plan-progression"
    db_session.add(
        ResearchConversationModel(
            id=conv_id,
            profile_data={
                "topic": "SQL 注入检测",
                "methods": ["词法分析", "深度学习分类"],
                "hardware": "RTX 4060 8GB 显存",
            },
            messages_data=[
                {
                    "message_id": "msg-1",
                    "role": "assistant",
                    "content": "【初步实验方案草案】准备复现基线分类器并对比准确率。",
                    "template": "experiment_design",
                    "plan_layer": "preliminary",
                }
            ],
        )
    )
    state_row = _make_execution_state(db_session, conv_id)
    _seed_current_paper(db_session, conv_id)
    state_row.subtasks = {
        "need_defined": True,
        "profile_ready": True,
        "plan_generated": True,
        "paper_selected": True,
        "experiment_designed": False,
    }
    db_session.commit()

    # User confirms preliminary plan and requests specific experiment design:
    resp = orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="确认初步方案，请生成具体实验方案"),
        db_session,
    )
    assert resp.reply_message is not None
    # Must NOT be intercepted as a passive tool call
    assert resp.reply_message.passive_tool_called is None
    # Must successfully light experiment_designed (可推进状态)
    assert resp.state.subtasks.experiment_designed is True
    assert resp.state.current_stage == "research_execution"
    assert "具体实验方案" in resp.reply_message.content


def test_passive_experiment_design_draft_records_preliminary_and_advances_on_confirm(
    db_session,
) -> None:
    """Test passive experiment-design tool when ready records preliminary plan_layer,
    enabling the next user confirmation to advance to specific plan without getting stuck."""
    class FlowGenerator:
        def generate(self, *, system_prompt: str, user_prompt: str, **kwargs):
            from code_navi.research.conversation_orchestrator import OrchestratorLlmOutcome
            if "具体实验方案" in system_prompt or "具体方案" in system_prompt:
                return OrchestratorLlmOutcome(
                    status="generated",
                    reply_text=(
                        "说明：以下内容基于会话状态中已确认的研究方向、当前可用的论文/实验信息及通用技术概览，"
                        "尚未执行正式检索；具体论文细节、实现细节和实验结论仍需在你确认后核验。\n\n"
                        "【具体实验方案】\n"
                        "细化模型结构、数据流、代码流程、日程与验收标准已就绪。"
                    ),
                )
            return OrchestratorLlmOutcome(
                status="generated",
                reply_text=(
                    "说明：以下内容基于会话状态中已确认的研究方向、当前可用的论文/实验信息及通用技术概览，"
                    "尚未执行正式检索；具体论文细节、实现细节和实验结论仍需在你确认后核验。\n\n"
                    "【初步实验方案草案】\n"
                    "根据工具结果，准备复现基线并评估指标。"
                ),
            )

    from research_llm_fakes import ContextAwareArtifactGenerator

    generator = FlowGenerator()
    orchestrator = ResearchConversationOrchestrator(llm_generator=generator)
    orchestrator.conversation_service.artifact_generator = ContextAwareArtifactGenerator()
    conv_id = "conv-passive-draft-confirm"
    db_session.add(
        ResearchConversationModel(
            id=conv_id,
            profile_data={
                "topic": "SQL 注入检测",
                "research_questions": ["如何提高注入攻击的检测准确率？"],
                "methods": ["词法分析", "深度学习分类"],
                "constraints": ["显存 8GB 限制"],
            },
            messages_data=[],
        )
    )
    state_row = _make_execution_state(db_session, conv_id)
    _seed_current_paper(db_session, conv_id)
    state_row.subtasks = {
        "need_defined": True,
        "profile_ready": True,
        "plan_generated": True,
        "paper_selected": True,
        "experiment_designed": False,
    }
    db_session.commit()

    # Step 1: User asks for experiment design (triggers passive tool)
    resp1 = orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="实验方案怎么做"),
        db_session,
    )
    assert resp1.reply_message is not None
    assert resp1.reply_message.passive_tool_called == "experiment-design"
    assert resp1.state.subtasks.experiment_designed is False

    # Check that conv recorded template="experiment_design" and plan_layer="preliminary"
    conv_row = db_session.get(ResearchConversationModel, conv_id)
    last_assistant_msg = [m for m in conv_row.messages_data if m.get("role") == "assistant"][-1]
    assert last_assistant_msg.get("template") == "experiment_design"
    assert last_assistant_msg.get("plan_layer") == "preliminary"

    # Step 2: User confirms the preliminary draft
    resp2 = orchestrator.process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="好的确认，请给出具体实验方案"),
        db_session,
    )
    assert resp2.reply_message is not None
    assert resp2.reply_message.passive_tool_called is None
    # Now in advancing state (可推进状态)
    assert resp2.state.subtasks.experiment_designed is True
    assert "具体实验方案" in resp2.reply_message.content


