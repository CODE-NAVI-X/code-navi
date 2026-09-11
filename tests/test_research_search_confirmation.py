"""检索确认链路 / 英文标题过滤 / 红线边界的契约测试。

浏览器真实验收事实（2026-09-11，研究开展阶段）：

1. 用户明确确认四组检索词后，后端**没有真正检索**（不落新的 evidence bundle），
   页面显示“检索尚未实际执行，暂无结果”，并要求点击一个不存在的“检索”按钮；
2. 随后点击“进入结果分析”，系统**隐式触发了一次检索**，并拉回 4 篇与主题
   完全无关的中文论文（慢性乙肝指南 / HUVEC 成管实验 / 新冠防控 / APTox）；
3. 正常输入（选择计算粒度、输入“GPU 显存约 8GB”、确认检索词）触发红线误拦截：
   “复现成功”与 “Output attributes unconfirmed choice to user”。

本文件把三类边界钉死：

- 检索确认必须走既有真实检索链路（元数据、source status、provenance 全部保留）；
- 阶段切换句（“可以进入结果分析”）**不得**被当成检索确认，从而杜绝隐式检索；
- 候选论文只保留可保守确认的英文标题，中文/中文为主标题一律不进候选。
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
from code_navi.research.clarification_options import extract_clarification_options
from code_navi.research.conversation_orchestrator import (
    OrchestratorLlmOutcome,
    ResearchConversationOrchestrator,
    build_search_confirmation_clarification,
    is_stage_transition_statement,
)
from code_navi.research.conversation_orchestrator_schemas import (
    SendOrchestratorMessageRequest,
)
from code_navi.research.conversation_prompt_templates import validate_jiangjiang_output
from code_navi.research.conversation_schemas import (
    AcademicSourceStatus,
    ConversationEvidenceBundle,
)
from code_navi.research.models import (
    ResearchConversationModel,
    ResearchOrchestratorStateModel,
)
from code_navi.research.paper_language import (
    filter_english_titles,
    is_english_title,
)
from code_navi.research.schemas import AcademicPaperResult, EvidenceStatement

# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------

PAPER_TITLE = "Semi-Supervised Classification with Graph Convolutional Networks"
PAPER_URL = "https://arxiv.org/abs/1609.02907"

#: 第一轮检索留下的无关论文（浏览器证据里的真实标题类型）。
UNRELATED_EN_TITLE = "Exoplanet atmospheric retrieval with JWST transit spectra"
#: 那次隐式检索拉回的无关中文论文（浏览器证据）。
UNRELATED_ZH_TITLES = [
    "慢性乙型肝炎防治指南（2022年版）",
    "HUVEC 成管实验和结果分析",
    "新型冠状病毒肺炎防控方案解读",
    "APTox：化学混合物毒性预测",
]

#: 用户在浏览器里确认的四组检索词。
CONFIRMED_QUERIES = [
    "data augmentation explanation stability attribution robustness",
    "SHAP stability reproducibility faithfulness metric",
    "CIFAR-10 ResNet data augmentation configuration",
    "attribution similarity cosine rank correlation",
]

#: 上一轮 assistant 正是“检索词建议与确认引导”，里面写着建议检索词。
SEARCH_GUIDANCE_MESSAGE = {
    "role": "assistant",
    "template": "search_guidance",
    "content": (
        "说明：以下内容基于你提出的探索方向与通用技术概览，尚未执行正式检索。\n\n"
        "【建议检索词】\n"
        f"- `{CONFIRMED_QUERIES[0]}`\n"
        f"- `{CONFIRMED_QUERIES[1]}`\n"
        f"- `{CONFIRMED_QUERIES[2]}`\n"
        f"- `{CONFIRMED_QUERIES[3]}`\n\n"
        "是否确认使用上述检索词开始正式检索？"
    ),
}


@pytest.fixture
def db_session(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CODE_NAVI_PROVIDER", "mock")
    engine = create_engine(f"sqlite:///{tmp_path / 'search_confirmation.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


class FakeLlm:
    """最小假生成器：正文不含复现成功断言，避免误触红线。"""

    def generate(self, *, system_prompt, user_prompt, conversation_history=(), conversation_id):
        return OrchestratorLlmOutcome(
            status="generated",
            reply_text="(｡･ω･｡) 收到，我们继续推进当前研究阶段。",
        )


class RecordingSearchService:
    """像真实检索服务一样：每次 search 新增一条 bundle，读取按 created_at.desc() 返回。"""

    def __init__(self, next_bundles=None, saved_bundles=None, error: Exception | None = None):
        self.next_bundles = list(next_bundles or [])
        self.saved_bundles = list(saved_bundles or [])
        self.error = error
        self.calls: list[str] = []

    def search(self, conversation_id, request, db):
        self.calls.append(request.query or "")
        if self.error is not None:
            raise self.error
        if not self.next_bundles:
            raise AssertionError("unexpected extra search call")
        bundle = self.next_bundles.pop(0)
        # 真实服务每次都 INSERT 一条新记录；这里插入最前，模拟 created_at.desc()。
        self.saved_bundles.insert(0, bundle)
        return bundle

    def list_bundles(self, conversation_id, db):
        return list(self.saved_bundles)


def _make_state(db, conv_id: str, stage: str) -> None:
    if stage == "research_execution":
        db.add(
            ResearchOrchestratorStateModel(
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
        )
    else:
        db.add(
            ResearchOrchestratorStateModel(
                conversation_id=conv_id,
                current_stage=stage,
                completed_stages=[],
                subtasks={"need_defined": False, "profile_ready": False},
                direction_history=[],
                plan_history=[],
            )
        )
    db.commit()


def _make_conversation(
    db,
    conv_id: str,
    *,
    stage: str = "research_execution",
    messages=None,
) -> None:
    db.add(
        ResearchConversationModel(
            id=conv_id,
            profile_data={"topic": "CIFAR-10 特征归因稳定性"},
            messages_data=list(messages or []),
        )
    )
    _make_state(db, conv_id, stage)


def _orchestrator(search_service) -> ResearchConversationOrchestrator:
    return ResearchConversationOrchestrator(
        llm_generator=FakeLlm(), search_service=search_service
    )


def _real_paper(title: str, url: str = PAPER_URL) -> AcademicPaperResult:
    return AcademicPaperResult(
        title=title,
        authors=["Kipf", "Welling"],
        year=2017,
        source_name="arXiv",
        url=url,
        accessed_at=datetime.now(UTC),
        information_scope="metadata_and_abstract_only",
        metadata_evidence=[],
        supporting_snippets=[],
        abstract_excerpt="Graph convolutional networks oversmooth with depth.",
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


def _bundle(conv_id: str, papers: list, query: str = "CIFAR-10 ResNet SHAP"):
    return ConversationEvidenceBundle(
        bundle_id=f"bundle-{conv_id}-{len(papers)}",
        conversation_id=conv_id,
        query=query,
        requested_sources=["arxiv"],
        allowed_sources=["arxiv"],
        queried_sources=["arxiv"],
        source_statuses=[
            AcademicSourceStatus(
                source="arxiv",
                status="success" if papers else "no_results",
                accessed_at=datetime.now(UTC),
                reason=None if papers else "no matching metadata",
            ),
        ],
        searched_at=datetime.now(UTC),
        papers=papers,
        source_links=[None for _ in papers],
        failure_reasons=[] if papers else ["no matching metadata"],
        provenance_note="结果仅来自用户显式选择且代码允许的学术来源。",
    )


# ---------------------------------------------------------------------------
# A. 明确确认检索词 → 必须真正触发检索（问题一）
# ---------------------------------------------------------------------------


def test_search_confirmation_options_carry_the_confirmed_queries() -> None:
    """结构化确认选项必须承载真实检索词本身。

    这是三件事的共同前提：消息里带动作词（触发检索）、带可解析的检索词、
    并且模型回显这些词时能追溯到用户原话（不误触“编造用户选择”红线）。
    """
    next_question, answers = build_search_confirmation_clarification(CONFIRMED_QUERIES)

    assert next_question.endswith("？")
    assert len(answers) >= 2
    assert "检索" in answers[0]
    for query in CONFIRMED_QUERIES:
        assert query in answers[0], f"确认选项未承载检索词：{query}"


def test_confirming_search_terms_runs_the_real_search(db_session) -> None:
    """1. 用户确认检索词后，既有真实搜索服务被调用，并落新的 evidence bundle。"""
    conv_id = "conv-confirm-1"
    search_service = RecordingSearchService(next_bundles=[_bundle(conv_id, [_real_paper(PAPER_TITLE)])])
    _make_conversation(db_session, conv_id, messages=[SEARCH_GUIDANCE_MESSAGE])

    _, answers = build_search_confirmation_clarification(CONFIRMED_QUERIES)
    click_message = f"我选 A：{answers[0]}"

    resp = _orchestrator(search_service).process_message(
        conv_id, SendOrchestratorMessageRequest(message=click_message), db_session
    )

    assert len(search_service.calls) == 1
    # 检索词来自用户确认的内容，而不是确认语本身。
    assert "CIFAR-10" in search_service.calls[0]
    assert "确认" not in search_service.calls[0]
    assert resp.reply_message is not None
    assert _bundle_persisted(search_service)

def _bundle_persisted(search_service) -> bool:
    return len(search_service.saved_bundles) == 1


def test_explicit_trigger_phrase_from_browser_runs_the_real_search(db_session) -> None:
    """2. 浏览器里用户实际发出的确认句也要能触发检索。"""
    conv_id = "conv-confirm-2"
    search_service = RecordingSearchService(next_bundles=[_bundle(conv_id, [_real_paper(PAPER_TITLE)])])
    _make_conversation(db_session, conv_id, messages=[SEARCH_GUIDANCE_MESSAGE])

    resp = _orchestrator(search_service).process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="现在触发，按上述四组关键词检索"),
        db_session,
    )

    assert len(search_service.calls) == 1
    # 用户自己没写具体词，回退到上一轮 assistant 给出的建议检索词。
    assert "CIFAR-10" in search_service.calls[0]
    assert resp.reply_message is not None
    assert "已为你完成正式文献检索" in resp.reply_message.content


def test_empty_search_result_persists_new_empty_bundle_and_keeps_metadata(db_session) -> None:
    """3/6. 空结果要落一个新的空 bundle，且保留 source status / provenance。"""
    conv_id = "conv-confirm-3"
    old_bundle = _bundle(conv_id, [_real_paper(UNRELATED_EN_TITLE)], query="old query")
    search_service = RecordingSearchService(
        next_bundles=[_bundle(conv_id, [], query="data augmentation SHAP")],
        saved_bundles=[old_bundle],
    )
    _make_conversation(db_session, conv_id, messages=[SEARCH_GUIDANCE_MESSAGE])

    resp = _orchestrator(search_service).process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="现在触发，按上述四组关键词检索"),
        db_session,
    )

    assert len(search_service.calls) == 1
    # 新的一次检索真的写进库里，且落在最前（created_at.desc() 的最新一条）。
    assert search_service.saved_bundles[0].papers == []
    assert search_service.saved_bundles[0].source_statuses[0].status == "no_results"
    assert search_service.saved_bundles[0].provenance_note
    # 如实说明空态，不回退到更早那批无关论文。
    assert UNRELATED_EN_TITLE not in resp.reply_message.content
    assert "没有检索到合适的论文" in resp.reply_message.content


def test_source_failure_is_reported_without_fabricating_success(db_session) -> None:
    """4/5. 来源失败时如实报告，不伪造“已完成检索”，也不落新 bundle。"""
    conv_id = "conv-confirm-4"
    search_service = RecordingSearchService(error=RuntimeError("arXiv unavailable"))
    _make_conversation(db_session, conv_id, messages=[SEARCH_GUIDANCE_MESSAGE])

    resp = _orchestrator(search_service).process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="现在触发，按上述四组关键词检索"),
        db_session,
    )

    assert len(search_service.calls) == 1
    assert search_service.saved_bundles == []
    assert "已为你完成正式文献检索" not in resp.reply_message.content
    assert "没有编造任何检索结果" in resp.reply_message.content


def test_rerun_search_twice_uses_the_same_cached_query_once_per_turn(db_session) -> None:
    """9. 同一确认句每次只触发一次检索（不重复调用 source）。"""
    conv_id = "conv-confirm-5"
    search_service = RecordingSearchService(
        next_bundles=[
            _bundle(conv_id, [_real_paper(PAPER_TITLE)]),
            _bundle(conv_id, [_real_paper(PAPER_TITLE)]),
        ]
    )
    _make_conversation(db_session, conv_id, messages=[SEARCH_GUIDANCE_MESSAGE])

    orchestrator = _orchestrator(search_service)
    for _ in range(2):
        orchestrator.process_message(
            conv_id,
            SendOrchestratorMessageRequest(message="现在触发，按上述四组关键词检索"),
            db_session,
        )

    assert len(search_service.calls) == 2  # 一次请求一次检索，没有一次请求触发两次


def test_search_confirmation_cannot_bypass_stage_precondition(db_session) -> None:
    """7. 画像/阶段前置条件不满足时，明确检索动作也不能绕过门控。"""
    conv_id = "conv-confirm-6"
    search_service = RecordingSearchService(next_bundles=[_bundle(conv_id, [_real_paper(PAPER_TITLE)])])
    _make_conversation(db_session, conv_id, stage="research_need")

    _orchestrator(search_service).process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="现在触发，按上述四组关键词检索"),
        db_session,
    )

    assert search_service.calls == []


# ---------------------------------------------------------------------------
# B. 阶段切换句不得被当成检索确认（问题二）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "文献精读与实验方案已完成，可以进入结果分析。",
        "研究计划没问题，可以继续进入研究开展。",
        "我已明确研究需求，就这样，可以进入下一步。",
        "可以进入下一阶段。",
        "我们先进入论文精读阶段。",
    ],
)
def test_stage_transition_statement_is_recognized(message: str) -> None:
    assert is_stage_transition_statement(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "现在触发，按上述四组关键词检索",
        "请基于已确认主题重新检索",
    ],
)
def test_search_action_is_not_a_stage_transition(message: str) -> None:
    assert is_stage_transition_statement(message) is False


def test_enter_analysis_click_does_not_trigger_a_hidden_search(db_session) -> None:
    """10. 点击「进入结果分析」不能隐式发起检索。

    上一轮恰好停留在“确认检索词”的引导上（用户正是停在这一步），
    该句又含「可以」——旧实现因此把它当成检索确认，静默检索并拉回无关论文。
    """
    conv_id = "conv-transition-1"
    search_service = RecordingSearchService(next_bundles=[_bundle(conv_id, [_real_paper(PAPER_TITLE)])])
    _make_conversation(db_session, conv_id, messages=[SEARCH_GUIDANCE_MESSAGE])

    resp = _orchestrator(search_service).process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="文献精读与实验方案已完成，可以进入结果分析。"),
        db_session,
    )

    assert search_service.calls == []
    assert search_service.saved_bundles == []
    assert "已为你完成正式文献检索" not in resp.reply_message.content


def test_repeated_analysis_clicks_do_not_repeat_search_or_candidates(db_session) -> None:
    """重复点击既不能重复检索，也不能多出候选。"""
    conv_id = "conv-transition-2"
    search_service = RecordingSearchService(next_bundles=[_bundle(conv_id, [_real_paper(PAPER_TITLE)])])
    _make_conversation(db_session, conv_id, messages=[SEARCH_GUIDANCE_MESSAGE])

    orchestrator = _orchestrator(search_service)
    for _ in range(3):
        orchestrator.process_message(
            conv_id,
            SendOrchestratorMessageRequest(
                message="文献精读与实验方案已完成，可以进入结果分析。"
            ),
            db_session,
        )

    assert search_service.calls == []
    papers = orchestrator.get_papers(conv_id, db_session)
    assert papers.current_paper is None


# ---------------------------------------------------------------------------
# C. 检索词解析：确认语本身不能当检索词（问题三的输入侧）
# ---------------------------------------------------------------------------


def test_confirmation_sentence_is_resolved_to_the_confirmed_terms(db_session) -> None:
    """确认句里的“我选 A：/确认/按这些检索词开始正式检索”不得进入检索词。"""
    conv_id = "conv-query-1"
    search_service = RecordingSearchService(next_bundles=[_bundle(conv_id, [_real_paper(PAPER_TITLE)])])
    _make_conversation(db_session, conv_id, messages=[SEARCH_GUIDANCE_MESSAGE])

    _orchestrator(search_service).process_message(
        conv_id,
        SendOrchestratorMessageRequest(
            message="我选 A：确认，按这些检索词开始正式检索：CIFAR-10 ResNet-18 SHAP"
        ),
        db_session,
    )

    assert len(search_service.calls) == 1
    query = search_service.calls[0]
    assert "CIFAR-10" in query and "ResNet-18" in query
    for framing in ("我选", "确认", "按这些检索词", "开始正式检索"):
        assert framing not in query


def test_all_guidance_queries_are_offered_not_only_the_first(db_session) -> None:
    """用户确认的是“四组关键词”，回退解析必须给出全部建议检索词。"""
    conv_id = "conv-query-2"
    search_service = RecordingSearchService(next_bundles=[_bundle(conv_id, [_real_paper(PAPER_TITLE)])])
    _make_conversation(db_session, conv_id, messages=[SEARCH_GUIDANCE_MESSAGE])

    _orchestrator(search_service).process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="现在触发，按上述四组关键词检索"),
        db_session,
    )

    query = search_service.calls[0]
    assert "explanation stability" in query
    assert "cosine rank correlation" in query


# ---------------------------------------------------------------------------
# D. 候选论文只保留可保守确认的英文标题（问题三）
# ---------------------------------------------------------------------------


def test_pure_chinese_title_is_rejected() -> None:
    assert is_english_title("慢性乙型肝炎防治指南（2022年版）") is False


@pytest.mark.parametrize(
    "title",
    [
        "HUVEC 成管实验和结果分析",
        "基于深度学习的 CIFAR-10 图像分类方法",
        "新型冠状病毒肺炎防控方案解读",
    ],
)
def test_cjk_dominant_mixed_title_is_rejected(title: str) -> None:
    assert is_english_title(title) is False


@pytest.mark.parametrize(
    "title",
    [
        "Semi-Supervised Classification with Graph Convolutional Networks",
        "Deep Learning for Image Classification",
        "SHAP-based attribution stability under data augmentation",
    ],
)
def test_english_title_is_kept(title: str) -> None:
    assert is_english_title(title) is True


@pytest.mark.parametrize("title", ["", "   ", "1234 5678", "2024"])
def test_title_without_letters_cannot_be_confirmed_as_english(title: str) -> None:
    """无法保守确认英文的标题必须过滤，不能靠猜。"""
    assert is_english_title(title) is False


def test_filter_keeps_order_and_drops_only_non_english() -> None:
    papers = [
        {"title": "Deep Learning for Image Classification"},
        {"title": "慢性乙型肝炎防治指南（2022年版）"},
        {"title": "HUVEC 成管实验和结果分析"},
        {"title": "SHAP-based attribution stability"},
    ]
    kept = [paper["title"] for paper in filter_english_titles(papers)]
    assert kept == [
        "Deep Learning for Image Classification",
        "SHAP-based attribution stability",
    ]


def _stub_client(source: str, papers: list[tuple[str, str]]):
    class _Stub:
        def search(self, query: str) -> AcademicSourceResult:
            return AcademicSourceResult.success(
                source,
                [
                    PaperMetadata(
                        title=title,
                        authors=["Some Author"],
                        year=2023,
                        source_name="arXiv",
                        url=url,
                        identifier=url,
                        abstract_excerpt=None,
                        accessed_at=datetime.now(UTC),
                    )
                    for title, url in papers
                ],
            )

    return _Stub()


def test_academic_search_tool_drops_chinese_titles_from_any_source() -> None:
    """来源名不等于语言：arXiv 返回中文标题也必须过滤。"""
    tool = AcademicSearchTool(
        source_clients={
            "arxiv": _stub_client(
                "arxiv",
                [
                    ("Attribution stability under augmentation", "https://arxiv.org/abs/1"),
                    (UNRELATED_ZH_TITLES[0], "https://arxiv.org/abs/2"),
                ],
            )
        }
    )

    payload = tool.search("session-1", "attribution stability", ["arxiv"])

    titles = [paper["title"] for paper in payload["papers"]]
    assert titles == ["Attribution stability under augmentation"]
    # 来源本身调用成功，source status / provenance 原样保留。
    assert payload["source_statuses"][0]["status"] == "success"
    assert payload["queried_sources"] == ["arxiv"]
    assert payload["provenance_note"]


def test_academic_search_tool_returns_empty_when_only_chinese_titles() -> None:
    """过滤后为空必须如实返回空候选，不得用无关论文补位。"""
    tool = AcademicSearchTool(
        source_clients={
            "arxiv": _stub_client(
                "arxiv",
                [(title, f"https://arxiv.org/abs/{index}") for index, title in enumerate(UNRELATED_ZH_TITLES)],
            )
        }
    )

    payload = tool.search("session-2", "attribution stability", ["arxiv"])

    assert payload["papers"] == []
    assert payload["source_statuses"][0]["status"] == "success"


# ---------------------------------------------------------------------------
# E. 红线边界（问题五）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "你可以进入下一阶段，我们开始数据增强实验。",
        "这一阶段已经完成，可以进入下一阶段规划。",
        "研究需求已明确，可以进入研究计划阶段。",
    ],
)
def test_stage_transition_wording_is_not_a_reproduction_success_claim(text: str) -> None:
    """阶段推进措辞不是复现成功断言，不得拦截正常对话。"""
    valid, reason = validate_jiangjiang_output(text, evidence_context=["用户：GPU 显存约 8GB"])
    assert valid is True, reason


@pytest.mark.parametrize(
    "text",
    [
        "本次复现成功了。",
        "实验验证已完成，指标与论文基线完全一致。",
        "已成功跑通论文实验。",
        "复现已经可以推进下一阶段。",
        "学生已经完成复现。",
    ],
)
def test_real_reproduction_success_claims_are_still_blocked(text: str) -> None:
    """真正的复现成功断言必须继续被拦截，红线不得被削弱。"""
    valid, reason = validate_jiangjiang_output(text, evidence_context=["用户：GPU 显存约 8GB"])
    assert valid is False
    assert reason is not None and "复现成功" in reason


@pytest.mark.parametrize(
    "text",
    [
        "你的设备显存约 8GB，具体能否稳定运行仍需在选定论文后用实际环境测试。",
        "时间上按一到两周规划主体实验，实际进度仍以每次运行记录为准。",
        "研究设计上先确认计算粒度，再分别报告不同增强配置的结论。",
        "下面这四条检索词由你确认；具体论文是否相关仍需你亲自核验。",
    ],
)
def test_normal_inputs_do_not_trip_the_reproduction_success_redline(text: str) -> None:
    valid, reason = validate_jiangjiang_output(text, evidence_context=["用户：GPU 显存约 8GB"])
    assert valid is True, reason


def test_echoing_confirmed_search_terms_is_traceable_to_the_user() -> None:
    """用户通过确认选项给出了检索词，模型回显这些词不算“编造用户选择”。"""
    _, answers = build_search_confirmation_clarification(CONFIRMED_QUERIES)
    user_message = f"我选 A：{answers[0]}"

    valid, reason = validate_jiangjiang_output(
        f"你已确认的检索词：{CONFIRMED_QUERIES[0]}。",
        evidence_context=[user_message],
    )

    assert valid is True, reason


def test_system_context_does_not_become_a_user_confirmation() -> None:
    """系统上下文/模型建议不得被当成用户已确认的选择。"""
    valid, reason = validate_jiangjiang_output(
        "你已确认研究方向为小分子药物设计。",
        evidence_context=["用户：我想做图像分类的鲁棒性研究"],
    )

    assert valid is False
    assert reason is not None and "unconfirmed choice" in reason


# ---------------------------------------------------------------------------
# F. 结构化澄清选项（问题四）
# ---------------------------------------------------------------------------


def test_numbered_question_line_still_yields_clickable_options() -> None:
    """编号问句（真实模型常见写法）也必须产出结构化选项。"""
    text = (
        "3. 你的 GPU 显存大概是多少？\n"
        "1. 8GB 左右\n"
        "2. 12GB 左右\n"
        "3. 16GB 及以上\n"
    )

    question, answers = extract_clarification_options(text)

    assert question == "你的 GPU 显存大概是多少？"
    assert answers == ["8GB 左右", "12GB 左右", "16GB 及以上"]


def test_plain_numbered_plan_steps_are_not_turned_into_options() -> None:
    """普通编号执行步骤（5 条计划）不得被误判成选择题。"""
    text = (
        "执行计划：\n"
        "1. 复现基线配置\n"
        "2. 增加弱增强\n"
        "3. 训练 3 个随机种子\n"
        "4. 计算 Spearman 秩相关\n"
        "5. 汇总不同增强配置的报告\n"
    )

    assert extract_clarification_options(text) == (None, [])


def test_too_many_candidates_keeps_question_without_fake_options() -> None:
    text = "你打算用几个随机种子？\n1. 1\n2. 2\n3. 3\n4. 4\n5. 5\n"

    question, answers = extract_clarification_options(text)

    assert question == "你打算用几个随机种子？"
    assert answers == []


def test_search_guidance_turn_exposes_structured_confirmation_options(db_session) -> None:
    """检索确认轮必须由后端确定性给出 next_question / suggested_answers。"""
    conv_id = "conv-options-1"
    search_service = RecordingSearchService(next_bundles=[_bundle(conv_id, [_real_paper(PAPER_TITLE)])])
    _make_conversation(db_session, conv_id)

    resp = _orchestrator(search_service).process_message(
        conv_id,
        SendOrchestratorMessageRequest(message="请推荐检索词，我还没确认。"),
        db_session,
    )

    assert search_service.calls == []  # 只是在要建议，不触发检索
    assert resp.reply_message is not None
    assert resp.reply_message.next_question
    assert len(resp.reply_message.suggested_answers) >= 2
    assert any("检索" in answer for answer in resp.reply_message.suggested_answers)
    # 结构化字段同时写进持久化消息，历史恢复路径才不会丢。
    conv = db_session.get(ResearchConversationModel, conv_id)
    last = conv.messages_data[-1]
    assert last["next_question"] == resp.reply_message.next_question
    assert last["suggested_answers"] == resp.reply_message.suggested_answers
