"""Tests for the Four-Stage State Machine in Research Conversation Orchestration."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from code_navi.db import Base
from code_navi.research.conversation_orchestrator import (
    ResearchConversationOrchestrator,
    detect_confirmation_intent,
    detect_direction_change_intent,
    is_history_inquiry,
    is_opening_greeting_intent,
)
from code_navi.research.conversation_orchestrator_schemas import (
    LearningContextInput,
    SendOrchestratorMessageRequest,
)
from code_navi.research.models import (
    ResearchConversationModel,
    ResearchOrchestratorStateModel,
)


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
    assert "新增学习内容" in prompt["user_prompt"]
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


def test_experiment_design_generation_enables_execution_stage_completion(db_session) -> None:
    """experiment_designed must be set after an experiment design is generated
    in the regular flow, so research_execution can complete via confirmation.
    """
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=SequencedOrchestratorLlmGenerator(
            ["姜姜结合论文与你的设备整理了具体实验安排，我们先准备数据集 (｡･ω･｡)"]
        )
    )
    conv = ResearchConversationModel(id="conv-exec-1", profile_data={}, messages_data=[])
    db_session.add(conv)
    state_model = ResearchOrchestratorStateModel(
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
    db_session.add(state_model)
    db_session.commit()

    # No paper selected yet; a regular (non-passive-tool) design request goes
    # through the experiment_design template and marks the subtask.
    resp = orchestrator.process_message(
        "conv-exec-1",
        SendOrchestratorMessageRequest(
            message="帮我制定一份具体的实验安排，包括数据准备和训练流程"
        ),
        db_session,
    )
    assert resp.state.current_stage == "research_execution"
    assert resp.state.subtasks.experiment_designed is True

    # Confirmation afterwards completes the execution stage.
    resp = orchestrator.process_message(
        "conv-exec-1",
        SendOrchestratorMessageRequest(message="可以，确认进入结果分析"),
        db_session,
    )
    assert resp.state.current_stage == "research_analysis"
    assert "research_execution" in resp.state.completed_stages


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
