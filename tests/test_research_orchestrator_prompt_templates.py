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
        sources=["OpenAlex", "Crossref", "arXiv"],
    )
    assert "Graph Convolutional Networks" in prompt["context"]
    assert "arXiv" in prompt["context"]
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
