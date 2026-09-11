"""CNN 固定**提问**流程（CNN_FLOW）的契约测试。

产品变更（Issue #122 / PR #129）：CNN 入口只固定**提问流程、问题顺序、状态流转
和确认门控**；研究方向、数据集、模型、GPU、样本数、随机种子、epoch、解释方法、
指标、实验规模与最终论文，必须由用户逐项输入并确认。

禁止再做的事：在普通 CNN 入口中写死 CIFAR-10 / ResNet-18 / 32×32 / RTX 4060 /
64 张 / 0、1、2 / 20 epoch / GradientSHAP / Spearman / Top-10 等任何实验条件，
也不能自动确认它们。固定演示候选只能走明确隔离的演示触发（`我想研究CNN演示`）。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from code_navi.db import Base
from code_navi.research.academic import (
    AcademicSearchTool,
    AcademicSourceResult,
    PaperMetadata,
)
from code_navi.research.cnn_flow import (
    CNN_FLOW_DEMO_TRIGGER_TEXT,
    CNN_FLOW_QUESTIONS,
    cnn_flow_question_reply,
    cnn_flow_recorded_reply,
    cnn_flow_reply_intro,
    cnn_flow_suggestion_reply,
    is_cnn_flow_trigger,
)
from code_navi.research.conversation_orchestrator import (
    OrchestratorLlmOutcome,
    ResearchConversationOrchestrator,
)
from code_navi.research.conversation_orchestrator_schemas import (
    SendOrchestratorMessageRequest,
)
from code_navi.research.conversation_search_service import ResearchConversationSearchService
from code_navi.research.models import (
    ResearchConversationModel,
    ResearchOrchestratorStateModel,
)

TRIGGER = "我想研究CNN。"
DEMO_TRIGGER = "我想研究CNN演示。"

#: 普通入口的初始回复里**不得出现**的写死实验条件
FORBIDDEN_FIXED_CONDITIONS = (
    "CIFAR-10",
    "ResNet-18",
    "32×32",
    "RTX 4060",
    "64 张",
    "0、1、2",
    "20 epoch",
    "GradientSHAP",
    "Spearman",
    "Top-10",
    "SHAP 解释稳定性",
)


class QueryRecordingSource:
    """记录真实传入 source 的 query，并返回与 query 主题一致的英文论文。"""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query: str) -> AcademicSourceResult:
        self.queries.append(query)
        return AcademicSourceResult.success(
            "arxiv",
            [
                PaperMetadata(
                    title=f"Study of {query} under augmentation",
                    authors=["Ada"],
                    year=2025,
                    source_name="arXiv",
                    url=f"https://arxiv.org/abs/9000.{len(self.queries):04d}",
                    identifier=f"arXiv:9000.{len(self.queries):04d}",
                    abstract_excerpt=f"This study examines {query} with attribution stability.",
                    accessed_at=datetime.now(UTC),
                )
            ],
        )


@pytest.fixture
def db_session(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "mock")
    engine = create_engine(f"sqlite:///{tmp_path / 'cnn_flow.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_conversation(db, conv_id: str, source: QueryRecordingSource | None = None):
    db.add(ResearchConversationModel(id=conv_id, profile_data={}, messages_data=[]))
    db.add(
        ResearchOrchestratorStateModel(
            conversation_id=conv_id,
            current_stage="research_need",
            completed_stages=[],
            subtasks={
                "need_defined": False,
                "profile_ready": False,
                "plan_generated": False,
                "paper_selected": False,
                "experiment_designed": False,
                "results_analyzed": False,
            },
            direction_history=[],
            plan_history=[],
        )
    )
    db.commit()
    llm = CountingLlm()
    if source is None:
        source = QueryRecordingSource()
    service = ResearchConversationSearchService(
        search_tool=AcademicSearchTool({"arxiv": source})
    )
    orchestrator = ResearchConversationOrchestrator(
        llm_generator=llm, search_service=service
    )
    return orchestrator, llm, source


class CountingLlm:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *, system_prompt, user_prompt, conversation_history=(), conversation_id):
        self.calls += 1
        return OrchestratorLlmOutcome(status="generated", reply_text="原有流程回复 (｡･ω･｡)")


def _send(orchestrator, db, conv_id: str, message: str):
    return orchestrator.process_message(
        conv_id, SendOrchestratorMessageRequest(message=message), db
    )


def _assistant_texts(db, conv_id: str) -> list[str]:
    conv = db.get(ResearchConversationModel, conv_id)
    return [
        str(msg.get("content") or "")
        for msg in (conv.messages_data or [])
        if msg.get("role") == "assistant"
    ]


def _flow_state(orchestrator, db, conv_id: str) -> dict:
    state = orchestrator.get_state_model(conv_id, db)
    return (state.subtasks or {}).get("cnn_flow") or {}


# ---------------------------------------------------------------------------
# A. 入口：不写死任何实验条件，一次只问一个问题
# ---------------------------------------------------------------------------


def test_trigger_enters_the_fixed_question_flow(db_session) -> None:
    conv_id = "flow-1"
    orchestrator, llm, _ = _make_conversation(db_session, conv_id)

    resp = _send(orchestrator, db_session, conv_id, TRIGGER)

    assert resp.status == "completed"
    assert llm.calls == 0  # 提问流程不经过 LLM
    texts = _assistant_texts(db_session, conv_id)
    assert len(texts) == 1
    assert "好呀，那我们就从 CNN 开始吧～" in texts[0]
    assert "你更想从 CNN 的哪一块开始？" in texts[0]


def test_public_trigger_accepts_lowercase_cnn_without_internal_flow_wording() -> None:
    """用户输入大小写变体时仍进入自然逐项提问，不能暴露实现标签。"""
    assert is_cnn_flow_trigger("我想研究cnn") is True
    reply = cnn_flow_reply_intro()
    assert "固定流程" not in reply
    assert "主题已经固定" not in reply
    assert "演示预设" not in reply


def test_cnn_dialogue_copy_is_warm_and_not_form_like() -> None:
    """固定的是推进顺序，不应把姜姜说成冷冰冰的表单。"""
    assert "好呀" in cnn_flow_reply_intro()
    assert "不用一次把所有条件都想好" in cnn_flow_reply_intro()
    assert "(｡•̀ᴗ-)✧" in cnn_flow_reply_intro()
    assert "为什么要问" in cnn_flow_question_reply("dataset")
    assert "已记录" not in cnn_flow_recorded_reply("dataset", "CIFAR-10")
    assert "收到" in cnn_flow_recorded_reply("dataset", "CIFAR-10")
    assert "(๑•̀ㅂ•́)و✧" in cnn_flow_recorded_reply("dataset", "CIFAR-10")
    assert "尚未确认" in cnn_flow_suggestion_reply("dataset")
    assert all("问题 2：" not in question for _, question, _ in CNN_FLOW_QUESTIONS)


def test_broad_direction_choice_asks_focus_before_dataset(db_session) -> None:
    """宽泛的机制/鲁棒性/可解释性方向必须先细化，不能直接跳到数据集。"""
    conv_id = "flow-direction-focus"
    orchestrator, _, _ = _make_conversation(db_session, conv_id)

    _send(orchestrator, db_session, conv_id, TRIGGER)
    _send(orchestrator, db_session, conv_id, "研究 CNN 的机制、鲁棒性或可解释性")
    focus_prompt = _assistant_texts(db_session, conv_id)[-1]

    assert "先选一个你最想看的切口" in focus_prompt
    assert "机制" in focus_prompt and "鲁棒性" in focus_prompt and "可解释性" in focus_prompt
    assert "数据集" not in focus_prompt

    _send(orchestrator, db_session, conv_id, "我想先看特征可解释性")
    next_prompt = _assistant_texts(db_session, conv_id)[-1]
    assert "数据集" in next_prompt
    direction = _flow_state(orchestrator, db_session, conv_id)["answers"]["direction"]
    assert "特征可解释性" in direction["value"]


@pytest.mark.parametrize(
    "forbidden",
    FORBIDDEN_FIXED_CONDITIONS,
)
def test_entry_reply_does_not_hardcode_any_experiment_condition(
    db_session, forbidden: str
) -> None:
    """2-9：初始回复不得写死任何实验条件。"""
    conv_id = f"flow-entry-{abs(hash(forbidden)) % 10 ** 9}"
    orchestrator, _, _ = _make_conversation(db_session, conv_id)

    _send(orchestrator, db_session, conv_id, TRIGGER)

    for text in _assistant_texts(db_session, conv_id):
        assert forbidden not in text, f"入口回复写死了实验条件：{forbidden}"


def test_only_one_question_is_asked_at_a_time(db_session) -> None:
    """10/11：一次只问一个问题；第一个回复里不得出现后续问题。"""
    conv_id = "flow-2"
    orchestrator, _, _ = _make_conversation(db_session, conv_id)

    _send(orchestrator, db_session, conv_id, TRIGGER)

    text = _assistant_texts(db_session, conv_id)[0]
    assert "你更想从 CNN 的哪一块开始？" in text
    assert "你准备使用什么数据集？" not in text
    assert "你准备使用什么 CNN 模型？" not in text


def test_question_order_is_fixed(db_session) -> None:
    conv_id = "flow-3"
    orchestrator, _, _ = _make_conversation(db_session, conv_id)
    _send(orchestrator, db_session, conv_id, TRIGGER)

    _send(orchestrator, db_session, conv_id, "我想研究数据增强是否会影响 CNN 的解释稳定性。")
    assert "你准备使用什么数据集？" in _assistant_texts(db_session, conv_id)[1]

    _send(orchestrator, db_session, conv_id, "CIFAR-10")
    assert "你准备使用什么 CNN 模型？" in _assistant_texts(db_session, conv_id)[2]

    _send(orchestrator, db_session, conv_id, "ResNet-18")
    assert "输入图像尺寸" in _assistant_texts(db_session, conv_id)[3]


# ---------------------------------------------------------------------------
# B. 逐项保存：原始回答、结构化字段、确认状态
# ---------------------------------------------------------------------------


def test_answers_are_recorded_with_raw_text_and_confirmed_flag(db_session) -> None:
    """12/13：用户原始中文回答不会丢失，结构化字段同时保存。"""
    conv_id = "flow-4"
    orchestrator, _, _ = _make_conversation(db_session, conv_id)
    _send(orchestrator, db_session, conv_id, TRIGGER)
    raw = "我想研究数据增强是否会影响 CNN 的解释稳定性。"
    _send(orchestrator, db_session, conv_id, raw)

    answers = _flow_state(orchestrator, db_session, conv_id)["answers"]
    assert answers["direction"]["raw"] == raw  # 原始回答不丢
    assert answers["direction"]["confirmed"] is True
    assert answers["direction"]["suggested"] is False
    # 系统确认时只能复述用户说过的内容
    assert "数据增强" in _assistant_texts(db_session, conv_id)[1]


def test_recommendation_is_not_auto_confirmed(db_session) -> None:
    """14：用户说“请推荐”时，建议值不得自动变成已确认值。"""
    conv_id = "flow-5"
    orchestrator, _, _ = _make_conversation(db_session, conv_id)
    _send(orchestrator, db_session, conv_id, TRIGGER)
    _send(orchestrator, db_session, conv_id, "研究数据增强对 CNN 的影响")
    _send(orchestrator, db_session, conv_id, "请推荐")

    flow = _flow_state(orchestrator, db_session, conv_id)
    dataset = flow["answers"]["dataset"]
    assert dataset["confirmed"] is False
    assert dataset["suggested"] is True
    assert "尚未确认" in _assistant_texts(db_session, conv_id)[-1]
    assert "你觉得这个起点合适吗" in _assistant_texts(db_session, conv_id)[-1]


def test_explicit_confirmation_adopts_the_suggestion(db_session) -> None:
    """15：用户明确确认建议后，才写入 confirmed 条件。"""
    conv_id = "flow-6"
    orchestrator, _, _ = _make_conversation(db_session, conv_id)
    _send(orchestrator, db_session, conv_id, TRIGGER)
    _send(orchestrator, db_session, conv_id, "研究数据增强对 CNN 的影响")
    _send(orchestrator, db_session, conv_id, "请推荐")
    _send(orchestrator, db_session, conv_id, "确认，采用这个方案")

    dataset = _flow_state(orchestrator, db_session, conv_id)["answers"]["dataset"]
    assert dataset["confirmed"] is True
    assert dataset["suggested"] is True
    assert dataset["value"] == "CIFAR-10"
    # 之后才进入下一个问题（模型）
    assert "你准备使用什么 CNN 模型？" in _assistant_texts(db_session, conv_id)[-1]


def test_rejected_suggestion_does_not_become_a_confirmed_answer(db_session) -> None:
    """否定系统建议时，字段仍待确认，不能把否定句保存成实验条件。"""
    conv_id = "flow-reject-suggestion"
    orchestrator, _, _ = _make_conversation(db_session, conv_id)
    _send(orchestrator, db_session, conv_id, TRIGGER)
    _send(orchestrator, db_session, conv_id, "研究数据增强对 CNN 的影响")
    _send(orchestrator, db_session, conv_id, "请推荐")

    response = _send(orchestrator, db_session, conv_id, "不采用这个方案")

    flow = _flow_state(orchestrator, db_session, conv_id)
    dataset = flow["answers"]["dataset"]
    assert flow["phase"] == "confirm_suggestion"
    assert dataset["confirmed"] is False
    assert dataset["suggested"] is True
    assert dataset["value"] == "CIFAR-10"
    assert "尚未确认" in _assistant_texts(db_session, conv_id)[-1]
    assert "你准备使用什么 CNN 模型？" not in response.reply_message.content


# ---------------------------------------------------------------------------
# C. 汇总与阶段门控
# ---------------------------------------------------------------------------


def _fill_all_fields(db, conv_id: str, orchestrator) -> None:
    script = [
        TRIGGER,
        "研究数据增强对 CNN 解释稳定性的影响",
        "CIFAR-10",
        "ResNet-18",
        "32×32",
        "RTX 4060 8GB",
        "64 张",
        "0、1、2",
        "20 epoch",
        "GradientSHAP",
        "Spearman 相关系数、Top-10 特征重合率",
        "先小规模验证，再决定是否扩大实验",
    ]
    for message in script:
        _send(orchestrator, db, conv_id, message)


def test_summary_only_contains_user_answers(db_session) -> None:
    """16/17：汇总只来自用户回答；缺失字段显示“未确定”。"""
    conv_id = "flow-7"
    orchestrator, _, _ = _make_conversation(db_session, conv_id)
    # 只回答研究方向与数据集，其余直接让全部字段走完（用“还没有”）
    for message in (
        TRIGGER,
        "研究数据增强对 CNN 解释稳定性的影响",
        "CIFAR-10",
        "ResNet-18",
        "不确定",
        "还没有 GPU",
        "还没有决定",
        "请推荐",
        "确认，采用这个方案",
        "请推荐",
        "确认，采用这个方案",
        "请推荐",
        "确认，采用这个方案",
        "请推荐",
        "确认，采用这个方案",
        "先小规模验证",
    ):
        _send(orchestrator, db_session, conv_id, message)

    summary = _assistant_texts(db_session, conv_id)[-1]
    assert "研究方向" in summary and "研究数据增强对 CNN 解释稳定性的影响" in summary
    assert "数据集" in summary and "CIFAR-10" in summary
    assert "输入尺寸" in summary and "未确定" in summary
    assert "回复“确认”，我再帮你开始论文检索" in summary


def test_stage_four_requires_explicit_summary_confirmation(db_session) -> None:
    """18：用户确认汇总后才保存画像并进入论文检索阶段。"""
    conv_id = "flow-8"
    orchestrator, _, source = _make_conversation(db_session, conv_id)
    _fill_all_fields(db_session, conv_id, orchestrator)
    assert source.queries == []  # 未确认汇总前不得检索

    conv = db_session.get(ResearchConversationModel, conv_id)
    profile_before = dict(conv.profile_data or {})

    response = _send(orchestrator, db_session, conv_id, "确认，以上内容准确。")

    assert len(source.queries) == 1  # 确认后才检索
    conv = db_session.get(ResearchConversationModel, conv_id)
    assert (conv.profile_data or {}) != profile_before  # 研究画像已保存
    content = response.reply_message.content or ""
    assert "英文标题已过滤" not in content
    assert "第三阶段" in content
    assert "文献精读" in content
    assert "实验方案" in content


def test_query_uses_user_confirmed_terms_and_no_display_labels(db_session) -> None:
    """19/20/21：query 只用用户真实确认的数据，且无选项字母/界面文字。"""
    conv_id = "flow-9"
    orchestrator, _, source = _make_conversation(db_session, conv_id)
    _fill_all_fields(db_session, conv_id, orchestrator)
    _send(orchestrator, db_session, conv_id, "确认，以上内容准确。")

    query = source.queries[0]
    for label in ("我选", "确认", "A ", "B ", "选项"):
        assert label not in query, f"界面文字进入 query：{query!r}"
    # 用户确认的条件必须出现在 supplemental query 里
    assert "CIFAR-10" in query
    assert "ResNet" in query
    assert "data augmentation" in query or "augmentation" in query
    assert "SHAP" in query or "attribution" in query


def test_chinese_and_english_queries_are_stored_separately(db_session) -> None:
    """22：原始中文 query 与 supplemental English query 分开保存，不互相覆盖。"""
    conv_id = "flow-10"
    orchestrator, _, _ = _make_conversation(db_session, conv_id)
    _fill_all_fields(db_session, conv_id, orchestrator)
    _send(orchestrator, db_session, conv_id, "确认，以上内容准确。")

    flow = _flow_state(orchestrator, db_session, conv_id)
    assert flow["query_zh"]
    assert flow["query_en"]
    assert flow["query_zh"] != flow["query_en"]
    # 原始中文描述保留用户原话
    assert "研究数据增强对 CNN 解释稳定性的影响" in flow["query_zh"]


def test_bundle_keeps_schema_provenance_and_passes_filters(db_session) -> None:
    """23/24/25：bundle 语义保留；英文过滤/相关度门禁继续生效。"""
    from code_navi.research.paper_language import filter_english_titles

    conv_id = "flow-11"
    orchestrator, _, _ = _make_conversation(db_session, conv_id)
    _fill_all_fields(db_session, conv_id, orchestrator)
    _send(orchestrator, db_session, conv_id, "确认，以上内容准确。")

    bundles = orchestrator.search_service.list_bundles(conv_id, db_session)
    assert len(bundles) == 1
    bundle = bundles[0]
    assert bundle.query  # supplemental English query
    assert bundle.provenance_note
    assert bundle.queried_sources == ["arxiv"]
    papers = [paper.model_dump() for paper in bundle.papers]
    assert [p["title"] for p in filter_english_titles(papers)] == [
        p["title"] for p in papers
    ]


# ---------------------------------------------------------------------------
# D. 论文确认与第四阶段
# ---------------------------------------------------------------------------


def _run_to_candidates(db, conv_id: str, orchestrator) -> str:
    _fill_all_fields(db, conv_id, orchestrator)
    _send(orchestrator, db, conv_id, "确认，以上内容准确。")
    bundle = orchestrator.search_service.list_bundles(conv_id, db)[0]
    return bundle.papers[0]


def test_clicking_candidate_only_pends(db_session) -> None:
    """26：点击候选不得自动设置 current_paper。"""
    conv_id = "flow-12"
    orchestrator, _, _ = _make_conversation(db_session, conv_id)
    paper = _run_to_candidates(db_session, conv_id, orchestrator)

    _send(
        orchestrator,
        db_session,
        conv_id,
        f"我想选择这篇论文作为复现候选：《{paper.title}》 {paper.url}",
    )

    assert orchestrator.get_papers(conv_id, db_session).current_paper is None


def test_explicit_confirmation_sets_current_paper(db_session) -> None:
    """27：明确确认后才设置 current_paper。"""
    conv_id = "flow-13"
    orchestrator, _, _ = _make_conversation(db_session, conv_id)
    paper = _run_to_candidates(db_session, conv_id, orchestrator)
    _send(
        orchestrator,
        db_session,
        conv_id,
        f"我想选择这篇论文作为复现候选：《{paper.title}》 {paper.url}",
    )
    _send(orchestrator, db_session, conv_id, "确认，将这篇论文设为当前复现论文。")

    papers = orchestrator.get_papers(conv_id, db_session)
    assert papers.current_paper is not None
    assert papers.current_paper.title == paper.title


def test_rejected_paper_confirmation_does_not_set_current_paper(db_session) -> None:
    """论文二次确认的否定回答不能推进或设置 current_paper。"""
    conv_id = "flow-reject-paper"
    orchestrator, _, _ = _make_conversation(db_session, conv_id)
    paper = _run_to_candidates(db_session, conv_id, orchestrator)
    _send(
        orchestrator,
        db_session,
        conv_id,
        f"我想选择这篇论文作为复现候选：《{paper.title}》 {paper.url}",
    )

    response = _send(orchestrator, db_session, conv_id, "不确认")

    assert orchestrator.get_papers(conv_id, db_session).current_paper is None
    assert _flow_state(orchestrator, db_session, conv_id)["phase"] == "await_confirm"
    assert "当前论文尚未确认" not in response.reply_message.content


def test_stage_four_uses_user_confirmed_conditions_and_marks_missing(db_session) -> None:
    """28/29/30：第四阶段只显示用户确认的条件；缺失显示“未确定”。"""
    conv_id = "flow-14"
    orchestrator, _, _ = _make_conversation(db_session, conv_id)
    # 故意不给输入尺寸（说“不确定”），验证第四阶段显示“未确定”而不是伪造默认值。
    for message in (
        TRIGGER,
        "研究数据增强对 CNN 解释稳定性的影响",
        "CIFAR-10",
        "ResNet-18",
        "不确定",
        "RTX 4060 8GB",
        "64 张",
        "0、1、2",
        "20 epoch",
        "GradientSHAP",
        "Spearman 相关系数、Top-10 特征重合率",
        "先小规模验证，再决定是否扩大实验",
        "确认，以上内容准确。",
    ):
        _send(orchestrator, db_session, conv_id, message)
    paper = orchestrator.search_service.list_bundles(conv_id, db_session)[0].papers[0]
    _send(
        orchestrator,
        db_session,
        conv_id,
        f"我想选择这篇论文作为复现候选：《{paper.title}》 {paper.url}",
    )
    _send(orchestrator, db_session, conv_id, "确认，将这篇论文设为当前复现论文。")
    _send(orchestrator, db_session, conv_id, "进入第四阶段。")

    state = orchestrator.get_state_model(conv_id, db_session)
    assert state.current_stage == "research_analysis"
    assert "research_execution" in (state.completed_stages or [])

    text = _assistant_texts(db_session, conv_id)[-1]
    assert "数据集：CIFAR-10" in text
    assert "模型：ResNet-18" in text
    # 用户没给输入尺寸 → 未确定，不得伪造
    assert "输入尺寸：未确定" in text
    assert "32×32" not in text


def test_reproduction_success_redline_still_works_in_stage_four(db_session) -> None:
    """31/32：第四阶段「复现成功」仍触发证据红线；assistant 文本不算用户声明。"""
    conv_id = "flow-15"
    orchestrator, _, _ = _make_conversation(db_session, conv_id)
    paper = _run_to_candidates(db_session, conv_id, orchestrator)
    _send(
        orchestrator,
        db_session,
        conv_id,
        f"我想选择这篇论文作为复现候选：《{paper.title}》 {paper.url}",
    )
    _send(orchestrator, db_session, conv_id, "确认，将这篇论文设为当前复现论文。")
    _send(orchestrator, db_session, conv_id, "进入第四阶段。")

    resp = _send(orchestrator, db_session, conv_id, "复现成功")

    content = resp.reply_message.content or ""
    assert "目前没有足够的实验运行证据" in content
    assert "当前正在执行 CNN 固定演示流程" not in content
    assert "不要跳过论文确认" not in content
    assert orchestrator.get_papers(conv_id, db_session).current_paper is not None


# ---------------------------------------------------------------------------
# E. 演示路径隔离与非 CNN 回归
# ---------------------------------------------------------------------------


def test_demo_trigger_is_isolated_from_the_normal_entry(db_session) -> None:
    """普通入口不得使用演示候选；演示触发单独存在。"""
    assert CNN_FLOW_DEMO_TRIGGER_TEXT == "我想研究CNN演示"

    conv_id = "flow-demo"
    orchestrator, _, _ = _make_conversation(db_session, conv_id)
    _send(orchestrator, db_session, conv_id, DEMO_TRIGGER)

    texts = _assistant_texts(db_session, conv_id)
    assert any("已进入 CNN 研究固定流程" in text for text in texts)
    # 演示路径才会出现演示候选来源
    assert any("演示" in text for text in texts) or any(
        "固定" in text for text in texts
    )


def test_normal_entry_never_produces_demo_candidates(db_session) -> None:
    from code_navi.research.cnn_preset import CNN_PRESET_DEMO_SOURCE

    conv_id = "flow-no-demo"
    orchestrator, _, _ = _make_conversation(db_session, conv_id)
    _fill_all_fields(db_session, conv_id, orchestrator)
    _send(orchestrator, db_session, conv_id, "确认，以上内容准确。")

    for bundle in orchestrator.search_service.list_bundles(conv_id, db_session):
        for paper in bundle.papers:
            assert paper.source_name != CNN_PRESET_DEMO_SOURCE


def test_non_cnn_topic_keeps_the_normal_flow(db_session) -> None:
    """37：非 CNN 主题不进入 CNN 固定流程。"""
    conv_id = "flow-normal"
    orchestrator, llm, _ = _make_conversation(db_session, conv_id)

    resp = _send(
        orchestrator,
        db_session,
        conv_id,
        "我想研究 CNN 的可解释性，应该从哪里开始？请给我一些建议。",
    )

    assert resp.status == "completed"
    assert llm.calls == 1
    for text in _assistant_texts(db_session, conv_id):
        assert "我知道了，你想围绕 CNN 开展研究" not in text
