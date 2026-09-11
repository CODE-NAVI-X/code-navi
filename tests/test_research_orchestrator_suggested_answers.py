"""结构化澄清选项（next_question / suggested_answers）贯通编排器。

背景：前端此前只能从姜姜正文里碰巧写出的 A/B/C/D 解析出可点击选项，
而真实模型常返回“1. … 2. …”这种编号建议，于是页面上没有按钮。
本文件锁定“结构化字段是唯一可靠来源”这一契约：
一轮澄清后，响应与持久化消息都必须带上一道待答问题与 2~4 条建议答案。
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from code_navi.db import Base
from code_navi.research.clarification_options import extract_clarification_options
from code_navi.research.conversation_orchestrator import (
    OrchestratorLlmOutcome,
    ResearchConversationOrchestrator,
)
from code_navi.research.conversation_orchestrator_schemas import (
    SendOrchestratorMessageRequest,
)
from code_navi.research.models import ResearchConversationModel

# 真实模型常见写法之一：题干 + 编号建议
NUMBERED_CLARIFICATION_REPLY = "\n".join(
    [
        "我想先确认一个关键问题，再帮你把范围收窄。",
        "",
        "你希望这次主要研究 CNN 的哪个层面？",
        "1. 应用层：用 CNN 完成一个具体任务",
        "2. 方法层：改进 CNN 的结构或训练方法",
        "3. 理解层：分析 CNN 的机制与可解释性",
        "",
        "选一个最接近的就行，也可以直接补充你自己的想法。",
    ]
)

# 同一题目的另一种常见写法：字母标号
LETTER_CLARIFICATION_REPLY = "\n".join(
    [
        "你希望这次主要研究 CNN 的哪个层面？",
        "A. 应用层：用 CNN 完成一个具体任务",
        "B. 方法层：改进 CNN 的结构或训练方法",
        "C. 理解层：分析 CNN 的机制与可解释性",
    ]
)

# 只有问题、没有可靠建议：必须保留自由输入，不伪造选项
OPEN_QUESTION_REPLY = "\n".join(
    [
        "我想先确认一个关键问题。",
        "",
        "你希望这次研究解决什么具体场景下的什么问题？",
        "",
        "说说你的想法就好，没有标准答案。",
    ]
)

# 普通编号执行步骤，不是选择题
NUMBERED_PLAN_REPLY = "\n".join(
    [
        "下面是我建议的推进路径：",
        "1. 先确认研究问题与评价指标",
        "2. 再挑选一篇可复现的基线论文",
        "3. 最后在本地跑通最小实验",
    ]
)


class FakeOrchestratorLlmGenerator:
    def __init__(self, responses: list[str | OrchestratorLlmOutcome] | None = None) -> None:
        self.responses = list(responses or [])

    def generate(
        self, *, system_prompt: str, user_prompt: str, **_kwargs
    ) -> OrchestratorLlmOutcome:
        if not self.responses:
            return OrchestratorLlmOutcome(status="generated", reply_text="[Fake LLM Reply] 好的。")
        resp = self.responses.pop(0)
        if isinstance(resp, OrchestratorLlmOutcome):
            return resp
        return OrchestratorLlmOutcome(status="generated", reply_text=resp)


@pytest.fixture
def db_session(tmp_path):
    db_file = tmp_path / "test_suggested_answers.db"
    test_engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        test_engine.dispose()


def _stored_assistant_messages(db_session, conversation_id: str) -> list[dict]:
    conv = db_session.get(ResearchConversationModel, conversation_id)
    db_session.refresh(conv)
    return [item for item in (conv.messages_data or []) if item.get("role") == "assistant"]


# --------------------------------------------------------------------------
# 1. 提取器：只认“题干 + 紧邻的 2~4 条候选”，不认普通编号步骤
# --------------------------------------------------------------------------


def test_extracts_numbered_options_attached_to_a_question() -> None:
    question, options = extract_clarification_options(NUMBERED_CLARIFICATION_REPLY)

    assert question == "你希望这次主要研究 CNN 的哪个层面？"
    assert options == [
        "应用层：用 CNN 完成一个具体任务",
        "方法层：改进 CNN 的结构或训练方法",
        "理解层：分析 CNN 的机制与可解释性",
    ]


def test_extracts_letter_options_attached_to_a_question() -> None:
    question, options = extract_clarification_options(LETTER_CLARIFICATION_REPLY)

    assert question == "你希望这次主要研究 CNN 的哪个层面？"
    assert options == [
        "应用层：用 CNN 完成一个具体任务",
        "方法层：改进 CNN 的结构或训练方法",
        "理解层：分析 CNN 的机制与可解释性",
    ]


def test_numbered_plan_steps_are_not_treated_as_options() -> None:
    question, options = extract_clarification_options(NUMBERED_PLAN_REPLY)

    assert options == []
    assert question is None


def test_question_without_adjacent_list_keeps_free_input() -> None:
    question, options = extract_clarification_options(OPEN_QUESTION_REPLY)

    # 问题本身要保留下来（前端据此判断“仍在等用户回答”），但绝不伪造选项
    assert question == "你希望这次研究解决什么具体场景下的什么问题？"
    assert options == []


def test_more_than_four_items_are_not_options() -> None:
    reply = "\n".join(
        [
            "你想先做哪一步？",
            "1. 准备数据",
            "2. 搭建基线",
            "3. 调参",
            "4. 跑对比",
            "5. 写报告",
        ]
    )
    _question, options = extract_clarification_options(reply)
    assert options == []


def test_single_item_is_not_options() -> None:
    reply = "\n".join(["你想先做哪一步？", "1. 准备数据"])
    _question, options = extract_clarification_options(reply)
    assert options == []


def test_list_separated_from_question_by_prose_is_not_attached() -> None:
    reply = "\n".join(
        [
            "你想先做哪一步？",
            "",
            "下面先给出我建议的整体节奏：",
            "1. 准备数据",
            "2. 搭建基线",
        ]
    )
    _question, options = extract_clarification_options(reply)
    assert options == []


def test_bold_option_labels_are_cleaned_for_display() -> None:
    reply = "\n".join(
        [
            "你更想从哪个角度切入？",
            "- **应用**：直接解决一个具体任务",
            "- **方法**：改进现有结构",
        ]
    )
    question, options = extract_clarification_options(reply)
    assert question == "你更想从哪个角度切入？"
    assert options == ["应用：直接解决一个具体任务", "方法：改进现有结构"]


# --------------------------------------------------------------------------
# 2. 编排器：一轮正常澄清后，响应 + 持久化都要带结构化字段
# --------------------------------------------------------------------------


def test_clarification_turn_returns_and_persists_structured_options(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=FakeOrchestratorLlmGenerator([NUMBERED_CLARIFICATION_REPLY])
    )
    db_session.add(
        ResearchConversationModel(id="conv-sa-1", profile_data={}, messages_data=[])
    )
    db_session.commit()

    resp = orchestrator.process_message(
        "conv-sa-1",
        SendOrchestratorMessageRequest(message="我想研究 CNN"),
        db_session,
    )

    assert resp.status == "completed"
    assert resp.reply_message is not None

    # (a) 响应里必须带上结构化字段，而不是只留一段 Markdown
    assert resp.reply_message.next_question == "你希望这次主要研究 CNN 的哪个层面？"
    assert resp.reply_message.suggested_answers == [
        "应用层：用 CNN 完成一个具体任务",
        "方法层：改进 CNN 的结构或训练方法",
        "理解层：分析 CNN 的机制与可解释性",
    ]

    # (b) 持久化消息也必须带上，重新加载历史会话时才不会丢
    stored = _stored_assistant_messages(db_session, "conv-sa-1")
    assert len(stored) == 1
    assert stored[0]["next_question"] == "你希望这次主要研究 CNN 的哪个层面？"
    assert stored[0]["suggested_answers"] == [
        "应用层：用 CNN 完成一个具体任务",
        "方法层：改进 CNN 的结构或训练方法",
        "理解层：分析 CNN 的机制与可解释性",
    ]


def test_stream_completed_event_carries_structured_options(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=FakeOrchestratorLlmGenerator([NUMBERED_CLARIFICATION_REPLY])
    )
    db_session.add(
        ResearchConversationModel(id="conv-sa-stream", profile_data={}, messages_data=[])
    )
    db_session.commit()

    events = list(
        orchestrator.stream_message(
            "conv-sa-stream",
            SendOrchestratorMessageRequest(message="我想研究 CNN"),
            db_session,
        )
    )
    completed = [
        json.loads(chunk.split("data:", 1)[1].strip())
        for chunk in events
        if chunk.startswith("event: completed")
    ]

    assert len(completed) == 1
    payload = completed[0]
    assert payload["reply_message"]["next_question"] == "你希望这次主要研究 CNN 的哪个层面？"
    assert len(payload["reply_message"]["suggested_answers"]) == 3


def test_retry_turn_also_returns_structured_options(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=FakeOrchestratorLlmGenerator(
            [
                OrchestratorLlmOutcome(status="failed", reason="provider exploded"),
                NUMBERED_CLARIFICATION_REPLY,
            ]
        )
    )
    db_session.add(
        ResearchConversationModel(id="conv-sa-retry", profile_data={}, messages_data=[])
    )
    db_session.commit()

    first = orchestrator.process_message(
        "conv-sa-retry",
        SendOrchestratorMessageRequest(message="我想研究 CNN"),
        db_session,
    )
    assert first.status == "failed"
    assert first.reply_message is None

    retried = orchestrator.retry_last_message("conv-sa-retry", db_session)

    assert retried.status == "completed"
    assert retried.reply_message is not None
    assert retried.reply_message.next_question == "你希望这次主要研究 CNN 的哪个层面？"
    assert len(retried.reply_message.suggested_answers) == 3


def test_open_question_turn_keeps_free_input_without_fabricated_options(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=FakeOrchestratorLlmGenerator([OPEN_QUESTION_REPLY])
    )
    db_session.add(
        ResearchConversationModel(id="conv-sa-open", profile_data={}, messages_data=[])
    )
    db_session.commit()

    resp = orchestrator.process_message(
        "conv-sa-open",
        SendOrchestratorMessageRequest(message="我想研究 CNN"),
        db_session,
    )

    assert resp.status == "completed"
    assert resp.reply_message is not None
    # 没有可靠建议时不得伪造选项，前端据此保持自由输入
    assert resp.reply_message.suggested_answers == []


def test_provider_failure_never_fabricates_options(db_session) -> None:
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=FakeOrchestratorLlmGenerator(
            [OrchestratorLlmOutcome(status="unavailable", reason="Provider down")]
        )
    )
    db_session.add(
        ResearchConversationModel(id="conv-sa-fail", profile_data={}, messages_data=[])
    )
    db_session.commit()

    resp = orchestrator.process_message(
        "conv-sa-fail",
        SendOrchestratorMessageRequest(message="我想研究 CNN"),
        db_session,
    )

    assert resp.status == "failed"
    assert resp.reply_message is None
    # 失败轮不落任何 assistant 消息 → 页面不会冒出伪造选项，重试语义不变
    assert _stored_assistant_messages(db_session, "conv-sa-fail") == []


def test_red_line_failure_never_fabricates_options(db_session) -> None:
    """红线失败（未经验证的“复现成功”断言）不得落消息，自然也不会冒出选项。"""
    violating_reply = "\n".join(
        [
            "我们已经复现成功了，效果非常好。",
            "",
            "你想先做哪一步？",
            "1. 准备数据",
            "2. 搭建基线",
        ]
    )
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=FakeOrchestratorLlmGenerator([violating_reply])
    )
    db_session.add(
        ResearchConversationModel(id="conv-sa-redline", profile_data={}, messages_data=[])
    )
    db_session.commit()

    resp = orchestrator.process_message(
        "conv-sa-redline",
        SendOrchestratorMessageRequest(message="我想研究 CNN"),
        db_session,
    )

    # 失败语义不变：不返回回复、不落 assistant 消息
    assert resp.status == "failed"
    assert resp.reply_message is None
    assert _stored_assistant_messages(db_session, "conv-sa-redline") == []
    assert resp.error is not None

    # 重试语义不变：仍可重试，且重试成功后才有选项
    state = orchestrator.get_state_model("conv-sa-redline", db_session)
    assert state.last_status == "failed"
