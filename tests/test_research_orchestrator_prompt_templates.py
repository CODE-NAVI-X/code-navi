"""Tests for the 8 research conversation prompt templates and Jiang Jiang persona."""

from __future__ import annotations

from code_navi.research.conversation_orchestrator_schemas import (
    CurrentPaperCard,
    DirectionCard,
    LearnerProfileData,
    LearningContextState,
)
from code_navi.research.conversation_prompt_templates import (
    JIANGJIANG_SYSTEM_PERSONA,
    build_experiment_design_prompt,
    build_need_clarification_prompt,
    build_paper_intro_prompt,
    build_profile_and_plan_prompt,
    build_result_analysis_prompt,
    build_search_guidance_prompt,
    build_stage_transition_prompt,
    build_welcome_prompt,
    validate_jiangjiang_output,
)


def test_persona_contains_core_rules() -> None:
    assert "姜姜" in JIANGJIANG_SYSTEM_PERSONA
    assert "emoji" in JIANGJIANG_SYSTEM_PERSONA or "Emoji" in JIANGJIANG_SYSTEM_PERSONA
    assert "颜文字" in JIANGJIANG_SYSTEM_PERSONA
    assert "百分比" in JIANGJIANG_SYSTEM_PERSONA


def test_build_welcome_prompt() -> None:
    learning_context = LearningContextState(
        conversation_id="c1",
        learned_content="图神经网络与图卷积 (GCN)",
        learning_progress="已完成节点分类章节",
    )
    direction_cards = [
        DirectionCard(id="d1", title="图卷积节点分类", description="基于 Cora 的分类"),
        DirectionCard(id="d2", title="动态图表示学习", description="时序图网络"),
    ]
    prompt = build_welcome_prompt(
        learning_context=learning_context,
        direction_cards=direction_cards,
    )
    assert prompt["system"]
    assert "图神经网络与图卷积" in prompt["context"]
    assert "图卷积节点分类" in prompt["context"]
    assert "禁止" in prompt["rules"] or "约束" in prompt["rules"]


def test_build_need_clarification_prompt() -> None:
    prompt = build_need_clarification_prompt(
        selected_direction="图注意力网络用于生物分子分类",
        user_message="我想试试用 GAT 做分子性质预测",
        learned_content="基础图卷积 (GCN)",
    )
    assert "图注意力网络" in prompt["context"]
    assert "分子性质预测" in prompt["context"]
    assert "需求澄清" in prompt["task"]


def test_build_profile_and_plan_prompt() -> None:
    profile = LearnerProfileData(
        hardware="RTX 4060 (8GB 显存)",
        weekly_hours="10 小时/周",
        python_env="Python 3.11, PyTorch 2.1",
        dev_experience="有 Python 与深度学习基础",
    )
    prompt = build_profile_and_plan_prompt(
        research_goal="在小型基准数据集上复现 GAT 节点分类",
        profile=profile,
    )
    assert "RTX 4060" in prompt["context"]
    assert "8GB 显存" in prompt["context"]
    assert "计划" in prompt["task"]


def test_build_search_guidance_prompt() -> None:
    prompt = build_search_guidance_prompt(
        research_goal="图卷积网络在引文网络上的节点分类",
        candidate_queries=[
            "Graph Convolutional Networks node classification",
            "Semi-supervised GCN Cora",
        ],
        sources=["OpenAlex", "Crossref", "arXiv", "Semantic Scholar", "DBLP"],
    )
    assert "Graph Convolutional Networks" in prompt["context"]
    assert "OpenAlex" in prompt["context"]
    assert "Crossref" in prompt["context"]
    assert "arXiv" in prompt["context"]
    # P1: Semantic Scholar and DBLP must be filtered out!
    assert "Semantic Scholar" not in prompt["context"]
    assert "DBLP" not in prompt["context"]
    assert "确认" in prompt["task"]


def test_build_paper_intro_prompt() -> None:
    paper = CurrentPaperCard(
        id="p1",
        paper_url="https://arxiv.org/abs/1609.02907",
        title="Semi-Supervised Classification with Graph Convolutional Networks",
        purpose="replace",
        metadata_snapshot={
            "abstract": "We present a scalable approach for semi-supervised learning on graph data."
        },
        selected_at="2026-09-02T10:00:00Z",
    )
    profile = LearnerProfileData(hardware="8GB 显存")
    prompt = build_paper_intro_prompt(paper=paper, profile=profile, research_goal="复现 GCN")
    assert "Semi-Supervised Classification with Graph Convolutional Networks" in prompt["context"]
    assert "研究问题" in prompt["rules"] and "创新点" in prompt["rules"]


def test_build_experiment_design_prompt() -> None:
    paper = CurrentPaperCard(
        id="p1",
        paper_url="https://arxiv.org/abs/1609.02907",
        title="Semi-Supervised Classification with Graph Convolutional Networks",
        purpose="replace",
        selected_at="2026-09-02T10:00:00Z",
    )
    profile = LearnerProfileData(hardware="8GB 显存")
    prompt = build_experiment_design_prompt(
        paper=paper,
        profile=profile,
        standard_metrics=["ACC", "F1", "Precision", "Recall"],
    )
    assert "standard_metrics" in prompt["context"] or "ACC" in prompt["context"]
    assert "实验方案" in prompt["task"]


def test_build_result_analysis_prompt() -> None:
    prompt = build_result_analysis_prompt(
        user_results="跑了 200 个 epoch，测试集 Accuracy 是 80.5%，比论文里的 81.5% 略低",
        baseline_metrics={"ACC": "81.5%"},
        hardware_info="8GB 显存",
    )
    assert "80.5%" in prompt["context"]
    assert "结果分析" in prompt["task"]


def test_build_stage_transition_prompt() -> None:
    prompt = build_stage_transition_prompt(
        from_stage="research_need",
        to_stage="research_plan",
        completed_subtasks=["need_defined", "profile_ready"],
        next_goals="生成总体计划与小目标",
    )
    assert "research_need" in prompt["context"] or "研究需求确定" in prompt["context"]
    assert "阶段切换" in prompt["task"]


def test_validate_jiangjiang_output_detects_emojis_and_forbidden_patterns() -> None:
    clean_text = "你好呀！我是姜姜 (＾▽＾)。我们来讨论一下你的研究需求吧！"
    is_valid, reason = validate_jiangjiang_output(clean_text)
    assert is_valid
    assert reason is None

    emoji_text = "你好呀！我是姜姜 😊。我们来看看吧！"
    is_valid, reason = validate_jiangjiang_output(emoji_text)
    assert not is_valid
    assert "emoji" in reason.casefold()

    percentage_fake_text = "恭喜你！当前复现成功率已达到 98%！"
    is_valid, reason = validate_jiangjiang_output(percentage_fake_text)
    assert not is_valid
    assert "复现成功" in reason or "百分比" in reason


def test_build_experiment_design_prompt_rules_reproduction_boundaries() -> None:
    """A. T6 Prompt rules: strictly forbid defining reproduction success thresholds."""
    paper = CurrentPaperCard(
        id="p-gcn",
        paper_url="https://arxiv.org/abs/1609.02907",
        title="Semi-Supervised Classification with Graph Convolutional Networks",
        purpose="replace",
        selected_at="2026-09-02T10:00:00Z",
    )
    profile = LearnerProfileData(hardware="8GB 显存")
    prompt = build_experiment_design_prompt(
        paper=paper,
        profile=profile,
        standard_metrics=["ACC", "F1"],
    )
    rules = prompt["rules"]

    # 1. Must forbid defining reproduction success / passing / standard thresholds
    assert any(k in rules for k in ["严禁", "不得", "禁止"])
    assert any(k in rules for k in ["阈值", "判定标准", "定义", "区间"])
    assert "复现成功" in rules or "通过" in rules or "达标" in rules

    # 2. Metric values can only be baseline reference / to_verify comparison
    assert "参考" in rules or "待核验" in rules or "对照" in rules

    # 3. Must forbid "视为复现成功" / "判定复现成功" even if metrics are close
    assert "视为复现成功" in rules or "判定复现成功" in rules or "说明复现成功" in rules

    # 4. Must state evidence_linked != reproduction success
    assert "evidence_linked" in rules and ("不代表复现成功" in rules or "不等于复现成功" in rules)


def test_validate_jiangjiang_output_reproduction_success_boundary_semantics() -> None:
    """B. Output validator: allows compliant negations, rejects affirmative claims."""
    # Compliant statements with explicit negation / boundary limitation -> MUST PASS
    compliant_cases = [
        "目前还不能下“复现成功”的结论，仍需核验数据划分、训练动态与论文描述。",
        "尚未确认复现成功；当前指标只能作为与论文基线的待核验对照。",
        "evidence_linked 不等于复现成功，仍需要人工核验。",
        "指标接近论文并不代表复现成功，仍需核验随机种子与实验环境。",
        "严禁声称复现成功，当前仅完成了第一轮基线记录。",
        "实验结果与论文基线存在差异，未能复现成功，需要进一步排查。",
        "避免轻易下复现成功结论，需补充完整消融实验。",
    ]
    for text in compliant_cases:
        is_valid, reason = validate_jiangjiang_output(text)
        assert is_valid, f"Compliant text was falsely rejected: {text} (reason: {reason})"
        assert reason is None

    # Affirmative / ungrounded reproduction success claims -> MUST FAIL
    violation_cases = [
        "若 Accuracy 落在 80.0% - 82.5%，即可视为复现成功。",
        "本次实验已复现成功。",
        "指标接近论文，因此可以判定复现成功。",
        "复现成功率达到 98%。",
        "GCN 模型在 Cora 上复现成功了。",
        "实验结果充分说明复现成功。",
        "复现成功率 100%",
        "本方案证明复现成功。",
    ]
    for text in violation_cases:
        is_valid, reason = validate_jiangjiang_output(text)
        assert not is_valid, f"Violation text was falsely accepted: {text}"
        assert reason is not None

    # Mixed clause violations (negation in first clause followed by positive claim) -> MUST FAIL
    mixed_clause_violations = [
        "尚未确认复现成功但已复现成功。",
        "不能认为复现成功但已复现成功。",
        "不要说复现成功但已复现成功。",
        "未复现成功但已复现成功。",
        "不算复现成功但算复现成功。",
        "不代表复现成功但本次已复现成功。",
    ]
    for text in mixed_clause_violations:
        is_valid, reason = validate_jiangjiang_output(text)
        assert not is_valid, f"Mixed clause violation was falsely accepted: {text}"
        assert reason is not None

    # Safe boundary and conditional statements -> MUST PASS
    safe_boundary_cases = [
        "复现成功不代表论文结论正确，仍需人工核验。",
        "即使复现成功，也不等于论文可投稿。",
        "如果未来形成复现闭环，仍需导师核验论文结论。",
        "尚未确认复现成功；当前指标仅作待核验对照。",
    ]
    for text in safe_boundary_cases:
        is_valid, reason = validate_jiangjiang_output(text)
        assert is_valid, f"Safe boundary text was falsely rejected: {text} (reason: {reason})"
        assert reason is None

    # Semantic reproduction-claim and percentage violations -> MUST FAIL
    semantic_violation_cases = [
        "本轮复现的成功率达到 98%。",
        "reproduction success rate 达到 98%。",
        "Accuracy 超过 81% 即算复现通过。",
        "本次已成功复现 GCN。",
        "本轮实验完成率为 85%。",
    ]
    for text in semantic_violation_cases:
        is_valid, reason = validate_jiangjiang_output(text)
        assert not is_valid, f"Semantic violation text was falsely accepted: {text}"
        assert reason is not None

    # Additional safe boundary cases -> MUST PASS
    additional_safe_cases = [
        "无需声称复现成功，当前结果仍待核验。",
        "不应声称复现成功，当前结果仍待核验。",
        "尚不足以断言复现成功，仍需补充数据划分与随机种子。",
        "实验不稳定，尚未确认复现成功。",
    ]
    for text in additional_safe_cases:
        is_valid, reason = validate_jiangjiang_output(text)
        assert is_valid, f"Additional safe text was falsely rejected: {text} (reason: {reason})"
        assert reason is None

    # Remaining violation cases (unrelated negation or new reproduction terms) -> MUST FAIL
    remaining_violation_cases = [
        "实验不稳定且已复现成功。",
        "数据不完整且本轮复现成功。",
        "模型已稳定重现论文结果。",
        "本实验已成功复刻论文结果。",
        "复现实验已经完成，可以进入下一阶段。",
    ]
    for text in remaining_violation_cases:
        is_valid, reason = validate_jiangjiang_output(text)
        assert not is_valid, f"Remaining violation text was falsely accepted: {text}"
        assert reason is not None
