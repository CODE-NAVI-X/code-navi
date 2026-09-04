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
    RESEARCH_SOURCE_SCOPE_PREFIX_CLARIFICATION,
    RESEARCH_SOURCE_SCOPE_PREFIX_TRANSITION,
    RESEARCH_SOURCE_SCOPE_PREFIX_WELCOME,
    build_experiment_design_prompt,
    build_need_clarification_prompt,
    build_paper_intro_prompt,
    build_profile_and_plan_prompt,
    build_result_analysis_prompt,
    build_search_guidance_prompt,
    build_stage_transition_prompt,
    build_welcome_prompt,
    get_source_scope_prefix,
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

    # P1-A: Positive reproduction/recreation completion synonyms -> MUST FAIL
    p1_a_violation_cases = [
        "模型已经复现论文结果。",
        "模型复现了论文结果。",
        "我们完成了复现。",
        "复现实验完成了，可以进入下一阶段。",
        "已重现论文中的实验结果。",
        "模型成功地重现了论文结果。",
    ]
    for text in p1_a_violation_cases:
        is_valid, reason = validate_jiangjiang_output(text)
        assert not is_valid, f"P1-A violation text was falsely accepted: {text}"
        assert reason is not None

    # P1-B: Context-sensitive success rate / completion rate risk reminders -> MUST PASS
    p1_b_safe_cases = [
        "严禁声称复现成功率，当前结果仍待核验。",
        "不要把实验完成率当作结论。",
    ]
    for text in p1_b_safe_cases:
        is_valid, reason = validate_jiangjiang_output(text)
        assert is_valid, f"P1-B safe text was falsely rejected: {text} (reason: {reason})"
        assert reason is None

    # Final R4 violation cases -> MUST FAIL
    final_r4_violation_cases = [
        "复现率达到 98%。",
        "模型成功跑通了论文复现实验。",
        "GCN 的复现验证完成，可以进入下一阶段。",
        "论文结果被成功再现。",
    ]
    for text in final_r4_violation_cases:
        is_valid, reason = validate_jiangjiang_output(text)
        assert not is_valid, f"Final R4 violation text was falsely accepted: {text}"
        assert reason is not None

    # Final R4 safe boundary cases -> MUST PASS
    final_r4_safe_cases = [
        "不应轻易因为前述结果而断言复现成功。",
        "如果复现实验完成，仍需导师核验。",
    ]
    for text in final_r4_safe_cases:
        is_valid, reason = validate_jiangjiang_output(text)
        assert is_valid, f"Final R4 safe text was falsely rejected: {text} (reason: {reason})"
        assert reason is None

    # Evidence boundary violation cases -> MUST FAIL
    evidence_boundary_violation_cases = [
        "复现实验验证完成。",
        "指标达到 81%，说明复现结果与论文一致。",
        "复现验证已经完成，可以进入下一阶段。",
        "实验验证完成，说明已成功复现。",
        "指标达到 81%，因此复现结果与论文一致。",
    ]
    for text in evidence_boundary_violation_cases:
        is_valid, reason = validate_jiangjiang_output(text)
        assert not is_valid, f"Evidence boundary violation text was falsely accepted: {text}"
        assert reason is not None

    # Evidence boundary safe cases (conditions, verifications, calculation definitions) -> MUST PASS
    evidence_boundary_safe_cases = [
        "若实验完成率达到80%，也不能判为复现成功。",
        "实验完成率的计算口径仍待确认。",
        "需核验复现实验完成率的计算方式。",
    ]
    for text in evidence_boundary_safe_cases:
        is_valid, reason = validate_jiangjiang_output(text)
        assert is_valid, (
            f"Evidence boundary safe text was falsely rejected: {text} (reason: {reason})"
        )
        assert reason is None

    # P1-A: Ungrounded consistent / reliable / baseline claims -> MUST FAIL
    p1_a_consistent_reliable_violations = [
        "结果和原论文吻合，可以进入下一阶段。",
        "指标已达到论文基线，因此复现可靠。",
        "实验结果与论文结论一致。",
        "指标超过论文基线，因此可以确认复现。",
    ]
    for text in p1_a_consistent_reliable_violations:
        is_valid, reason = validate_jiangjiang_output(text)
        assert not is_valid, f"P1-A ungrounded text was falsely accepted: {text}"
        assert reason is not None

    # P1-B: Intra-clause compliant negation and boundary descriptions -> MUST PASS
    p1_b_intra_clause_safe_cases = [
        "实验完成率作为实验过程指标，而非复现结论。",
        "不应根据实验完成率就声称复现成功。",
        "实验完成率的计算口径仍待确认。",
        "若实验完成率达到80%，也不能判为复现成功。",
    ]
    for text in p1_b_intra_clause_safe_cases:
        is_valid, reason = validate_jiangjiang_output(text)
        assert is_valid, (
            f"P1-B intra-clause safe text was falsely rejected: {text} (reason: {reason})"
        )
        assert reason is None

    # Cross-clause mixed negation bypass -> MUST FAIL
    cross_clause_negation_bypass = [
        "不应根据实验完成率声称复现成功，但本轮已成功复现论文结果。",
    ]
    for text in cross_clause_negation_bypass:
        is_valid, reason = validate_jiangjiang_output(text)
        assert not is_valid, f"Cross clause bypass text was falsely accepted: {text}"
        assert reason is not None

    # Consistency and verification claim violations -> MUST FAIL
    consistency_verification_claim_violations = [
        "指标达到81%，复现结果和基线一致。",
        "指标达到81%，复现指标与论文一致。",
        "指标达到81%，结果与论文基本一致。",
        "复现实验已通过验证。",
        "复现验证通过。",
        "实验验证已通过。",
    ]
    for text in consistency_verification_claim_violations:
        is_valid, reason = validate_jiangjiang_output(text)
        assert not is_valid, f"Consistency/verification violation text was falsely accepted: {text}"
        assert reason is not None

    # Compound coordination safe cases -> MUST PASS
    compound_coordination_safe_cases = [
        "不应断言复现成功或复现实验完成。",
        "不得视为复现成功和复现验证完成。",
        "尚不足以认为复现成功、复现实验完成。",
    ]
    for text in compound_coordination_safe_cases:
        is_valid, reason = validate_jiangjiang_output(text)
        assert is_valid, (
            f"Compound coordination safe text was falsely rejected: {text} (reason: {reason})"
        )
        assert reason is None


def test_validate_jiangjiang_output_p1_reproduction_boundary_cases() -> None:
    """P1-A: Reject ungrounded affirmative completion claims with word order variants."""
    p1_a_violations = [
        "实验通过了复现验证。",
        "本轮实验已通过复现验证。",
        "验证表明实验已经复现成功。",
    ]
    for text in p1_a_violations:
        is_valid, reason = validate_jiangjiang_output(text)
        assert not is_valid, f"P1-A violation text was falsely accepted: {text}"
        assert reason is not None

    # P1-B: Conditional, negation, and risk boundary statements are safe without evidence
    p1_b_safe_cases = [
        "若用户报告实验结果与论文一致，仍需核验。",
        "即使实验结果与论文一致，也不能据此认定复现成功。",
        "实验完成率作为实验过程指标，而非复现结论。",
        "不应根据实验完成率就声称复现成功。",
    ]
    for text in p1_b_safe_cases:
        is_valid, reason = validate_jiangjiang_output(text)
        assert is_valid, f"P1-B safe text was falsely rejected: {text} (reason: {reason})"
        assert reason is None

    # P1-Provenance: Without traceable user evidence, claims of '用户报告' must be rejected
    unproven_user_reports = [
        "fact：用户报告实验结果与论文一致；to_verify：仍需核验。",
        "fact：用户报告实验结果与论文一致；to_verify：确认显存容量。",
    ]
    for text in unproven_user_reports:
        is_valid, reason = validate_jiangjiang_output(text)
        assert not is_valid, f"Unproven user report was falsely accepted without evidence: {text}"
        assert reason is not None

    # Irrelevant evidence does not substantiate consistency claim
    is_valid_irrelevant, reason_irrelevant = validate_jiangjiang_output(
        "fact：用户报告实验结果与论文一致；to_verify：确认显存容量。",
        evidence_context="我想研究图卷积网络并设计实验",
    )
    assert not is_valid_irrelevant, "Irrelevant evidence falsely substantiated consistency fact"
    assert reason_irrelevant is not None

    # With authentic user evidence, user-attributed fact + to_verify is accepted
    is_valid_proven, reason_proven = validate_jiangjiang_output(
        "fact：用户报告实验结果与论文一致；\nto_verify：仍需核验数据划分、随机种子和指标计算口径。",
        evidence_context="我观察到本次实验结果与论文结果一致，但还没有完成核验。",
    )
    assert is_valid_proven, f"Proven fact was falsely rejected: {reason_proven}"
    assert reason_proven is None

    # P1-C: Cross-clause affirmative reproduction conclusions must be rejected
    # even with user evidence
    p1_c_violations = [
        "fact：用户报告实验结果与论文一致；但姜姜确认已经复现成功。",
        "不应根据实验完成率声称复现成功，但本轮已成功复现论文结果。",
    ]
    for text in p1_c_violations:
        is_valid, reason = validate_jiangjiang_output(
            text,
            evidence_context="我观察到本次实验结果与论文结果一致，但还没有完成核验。",
        )
        assert not is_valid, f"P1-C violation text was falsely accepted: {text}"
        assert reason is not None

    # P1-Local-A: to_verify in prior sentence must not allow ungrounded fact in subsequent sentence
    is_valid_inv, reason_inv = validate_jiangjiang_output(
        "to_verify：仍需核验。用户报告实验结果与论文一致。",
        evidence_context="我观察到本次实验结果与论文结果一致，但还没有完成核验。",
    )
    assert not is_valid_inv, "Preceding to_verify falsely allowed subsequent statement"
    assert reason_inv is not None

    # P1-Local-B: User source tag must not leak across coordinators to Jiang Jiang confirmation
    jj_leak_cases = [
        "用户报告实验结果与论文一致、姜姜确认实验结果与论文一致；to_verify：仍需核验。",
        "用户报告实验结果与论文一致/姜姜确认实验结果与论文一致；to_verify：仍需核验。",
        "用户报告实验结果与论文一致和姜姜确认实验结果与论文一致；to_verify：仍需核验。",
    ]
    for text in jj_leak_cases:
        is_valid_jj, reason_jj = validate_jiangjiang_output(
            text,
            evidence_context="我观察到本次实验结果与论文结果一致，但还没有完成核验。",
        )
        assert not is_valid_jj, f"User source tag leaked to Jiang Jiang confirmation: {text}"
        assert reason_jj is not None

    # P1-Local-C: Category mismatch (result consistency cannot support baseline metric claim)
    is_valid_cat_mismatch, reason_cat_mismatch = validate_jiangjiang_output(
        "fact：用户报告指标达到论文基线；to_verify：仍需核验。",
        evidence_context="我观察到本次实验结果与论文结果一致，但还没有完成核验。",
    )
    assert not is_valid_cat_mismatch, "Evidence category mismatch was falsely accepted"
    assert reason_cat_mismatch is not None

    # Matching category 2 evidence allows category 2 claim
    is_valid_cat2, reason_cat2 = validate_jiangjiang_output(
        "fact：用户报告指标达到论文基线；to_verify：仍需核验。",
        evidence_context="我观察到本次复现指标已达到原论文基线，但尚未全面核验。",
    )
    assert is_valid_cat2, f"Matching category 2 evidence was falsely rejected: {reason_cat2}"
    assert reason_cat2 is None

    # P1-Fingerprints: Fine-grained fact fingerprint alignment
    fp_base_evidence = "我观察到本次实验结果与论文结果一致，但还没有完成核验。"
    fp_mismatch_violations = [
        "fact：用户报告复现指标与论文指标一致；to_verify：仍需核验。",
        "fact：用户报告指标与论文一致；to_verify：仍需核验。",
        "fact：用户报告实验结果与论文结论一致；to_verify：仍需核验。",
    ]
    for text in fp_mismatch_violations:
        is_valid_fp, reason_fp = validate_jiangjiang_output(
            text,
            evidence_context=fp_base_evidence,
        )
        assert not is_valid_fp, f"Fingerprint mismatch was falsely accepted: {text}"
        assert reason_fp is not None

    # Fine-grained matching allowed cases (synonyms and inline retention)
    fp_allowed_cases = [
        "fact：用户报告实验结果与论文结果一致；to_verify：仍需核验。",
        "fact：用户报告实验结果与论文结果吻合；to_verify：仍需核验。",
        "fact：用户报告实验结果与论文结果一致且仍待核验；to_verify：仍需核验。",
    ]
    for text in fp_allowed_cases:
        is_valid_ok, reason_ok = validate_jiangjiang_output(
            text,
            evidence_context=fp_base_evidence,
        )
        assert is_valid_ok, f"Fingerprint match was falsely rejected: {text} ({reason_ok})"
        assert reason_ok is None

    # P1-Assertive: Non-assertive user evidence (questions, conditions, risk boundaries, denials)
    non_assertive_evidences = [
        "如果实验结果与论文结果一致，我下一步应该做什么？",
        "即使实验结果与论文结果一致，也不能认定复现成功。",
        "实验结果是否与论文结果一致？",
        "我还没有实验结果。",
        "实验结果尚未与论文结果对比。",
    ]
    target_fact_text = "fact：用户报告实验结果与论文结果一致；to_verify：仍需核验。"
    for non_assertive_ev in non_assertive_evidences:
        is_valid_na, reason_na = validate_jiangjiang_output(
            target_fact_text,
            evidence_context=non_assertive_ev,
        )
        assert not is_valid_na, (
            f"Non-assertive evidence falsely substantiated fact: {non_assertive_ev}"
        )
        assert reason_na is not None

    # Explicit affirmative user observations allow the fact
    assertive_evidences = [
        "我观察到本次实验结果与论文结果一致，但还没有完成核验。",
        "本次实验结果与论文结果一致；随机种子和数据划分仍待核验。",
    ]
    for assertive_ev in assertive_evidences:
        is_valid_as, reason_as = validate_jiangjiang_output(
            target_fact_text,
            evidence_context=assertive_ev,
        )
        assert is_valid_as, (
            f"Assertive evidence was falsely rejected: {assertive_ev} ({reason_as})"
        )
        assert reason_as is None

    # S1-Target-A: Ungrounded mastery/capability claims inferred from learning records
    learning_evidence = (
        "已学内容：图卷积网络(GCN)数学推导与节点分类；"
        "学习进度：完成理论推导，准备开展真实实验"
    )
    mastery_violations = [
        "这说明你的线性代数和谱图论基本功已经很扎实了。",
        "你已经具备独立完成 GCN 复现实验的能力。",
        "你已经掌握了图神经网络的核心知识。",
        "你已经有用 GCN 做节点分类的实践经验。",
        "你目前掌握的基础，是这个领域非常关键的两块拼图。",
        "你大概知道了怎么在图上做邻居信息聚合。",
        "这说明你已经具备做比较深入研究的入口了。",
        "看来你刚刚打通了 GraphSAGE 的任督二脉。",
    ]
    for text in mastery_violations:
        is_valid_mv, reason_mv = validate_jiangjiang_output(
            text,
            evidence_context=learning_evidence,
        )
        assert not is_valid_mv, f"Mastery violation text was falsely accepted: {text}"
        assert reason_mv is not None

    mastery_compliant_cases = [
        "学习端记录显示你已学习 GCN 数学推导与节点分类相关内容。",
        "当前进度记录为已完成理论推导，接下来可以一起确认实验环境与数据集准备情况。",
        "这些学习记录不等于已经完成实验；是否跑通训练流程仍需你确认。",
        "学习端记录显示你已学习 GCN 数学推导与节点分类相关内容。",
        "当前进度记录为：完成理论推导，准备开展真实实验。",
        "学习端新增记录为：GraphSAGE 邻居采样与大规模图训练。",
        "这些记录不等于已具备编码、实验或研究能力；实际经验仍需你确认。",
        "如果你愿意，可以先确认是否有实际运行训练流程的经历。",
    ]
    for text in mastery_compliant_cases:
        is_valid_mc, reason_mc = validate_jiangjiang_output(
            text,
            evidence_context=learning_evidence,
        )
        assert is_valid_mc, f"Mastery compliant text was falsely rejected: {text} ({reason_mc})"
        assert reason_mc is None

    # S1-Target-B: Question and conditional context for '跑通过/复现/验证通过'
    question_compliant_cases = [
        "你亲手用 PyTorch Geometric 跑通过 Cora 数据集吗？",
        "你是否已经跑通过 Cora 的训练流程？",
        "如果还没有跑通过，我们可以从最小 CPU 基线开始。",
        (
            "你有没有写过 GCN 的训练循环？"
            "亲手用 PyTorch Geometric 或 DGL 跑通过 Cora/Citeseer 数据集？"
        ),
        "是否跑通过训练流程仍需你确认。",
    ]
    for text in question_compliant_cases:
        is_valid_qc, reason_qc = validate_jiangjiang_output(
            text,
            evidence_context=learning_evidence,
        )
        assert is_valid_qc, f"Question/conditional text was falsely rejected: {text} ({reason_qc})"
        assert reason_qc is None

    # Affirmative completion claims must continue to be rejected
    affirmative_violations = [
        "你已经跑通过 Cora 数据集，因此复现成功。",
        "GCN 已通过验证，可以进入下一阶段。",
        "实验结果与论文一致，所以已经完成复现。",
    ]
    for text in affirmative_violations:
        is_valid_av, reason_av = validate_jiangjiang_output(
            text,
            evidence_context=learning_evidence,
        )
        assert not is_valid_av, f"Affirmative completion text was falsely accepted: {text}"
        assert reason_av is not None

    # S1-Target-C: Strict learning record mode evaluations
    strict_violations = [
        "你当前能力够得着这个方向。",
        "又往前迈了一步呢。",
        "你在归纳式学习方向开始有意识地拓展了。",
        "这个选择很有科研潜力。",
        "你的基础足以开始深入研究。",
        "你已经形成了系统的理解。",
    ]
    for text in strict_violations:
        is_valid_sv, reason_sv = validate_jiangjiang_output(
            text,
            evidence_context=learning_evidence,
            learning_record_mode=True,
        )
        assert not is_valid_sv, f"Strict mode falsely accepted: {text}"
        assert reason_sv is not None

    strict_compliant_cases = [
        "学习端记录显示：已学习 GCN 数学推导与节点分类。",
        "当前进度记录为：新增学习 GraphSAGE 邻居采样与大规模图训练。",
        (
            "学习端记录显示：已学习 GCN 数学推导与节点分类；"
            "当前进度记录为完成理论推导，准备开展真实实验。"
        ),
        "这些学习记录不代表已掌握或具备研究能力，实际理解与代码经验仍需你确认。",
        "你提到想把 GraphSAGE 应用到研究中。",
        "这些学习记录不等于实践经验、掌握程度或研究能力，仍需你确认。",
        "如果你愿意，可以先确认是否运行过 GraphSAGE 的训练流程。",
    ]
    for text in strict_compliant_cases:
        is_valid_sc, reason_sc = validate_jiangjiang_output(
            text,
            evidence_context=learning_evidence,
            learning_record_mode=True,
        )
        assert is_valid_sc, f"Strict mode falsely rejected: {text} ({reason_sc})"
        assert reason_sc is None

    # Red Phase: Natural language source_scope boundaries
    # Technical statements without source_scope in learning record mode must be rejected
    technical_without_scope = [
        "GraphSAGE 可以泛化到新节点，邻居采样能够降低大规模图训练成本。",
        "下面是为你准备的 5 个研究方向卡片：卡片一：图拓扑结构节点分类。",
        "探索自注意力在图邻居聚合中的作用与异质图泛化性。",
    ]
    for text in technical_without_scope:
        is_valid_tws, reason_tws = validate_jiangjiang_output(
            text,
            evidence_context=learning_evidence,
            learning_record_mode=True,
        )
        assert not is_valid_tws, (
            f"Technical output without source_scope was falsely accepted: {text}"
        )
        assert reason_tws is not None
        assert "source_scope" in reason_tws

    # Technical statements with valid natural language source_scope must pass
    valid_scope_statement = (
        "说明：下面是基于学习记录生成的探索方向与通用技术概览，尚未执行正式检索；"
        "具体论文、实现细节和实验结论仍需在你确认后核验。\n\n"
        "下面是为你准备的 5 个研究方向卡片：卡片一：图拓扑结构节点分类。"
    )
    is_valid_vss, reason_vss = validate_jiangjiang_output(
        valid_scope_statement,
        evidence_context=learning_evidence,
        learning_record_mode=True,
    )
    assert is_valid_vss, (
        f"Technical output with valid source_scope was falsely rejected: {reason_vss}"
    )
    assert reason_vss is None


def test_validate_jiangjiang_output_stage_transition_source_scope() -> None:
    """Stage transition with technical overview/equipment impact requires natural source_scope."""
    # Without source_scope: MUST FAIL even if learning_record_mode=False
    invalid_stage_transition_text = (
        "# 阶段跃迁确认 (＾▽＾)\n\n"
        "收到你的确认，我们正式从「研究需求确定」进入「研究计划生成」阶段。\n\n"
        "**已完成的工作**\n"
        "- 确定核心研究主题：图卷积神经网络在生物分子图性质预测上的应用\n"
        "- 明确研究问题框架：分子图表示 + 图卷积消息传递 + 整图读出 + 性质预测\n\n"
        "做图神经网络训练，设备配置直接影响实验方案设计。\n\n"
        "**问题一：你的计算设备是什么？**\n"
        "请如实填写你的 GPU 型号与显存 (｡･ω･｡)"
    )
    is_valid, reason = validate_jiangjiang_output(
        invalid_stage_transition_text,
        learning_record_mode=False,
    )
    assert not is_valid, (
        "Stage transition with technical overview without source_scope must be rejected"
    )
    assert reason is not None
    assert "source_scope" in reason

    # With valid natural language source_scope: MUST PASS
    valid_stage_transition_text = (
        "# 阶段跃迁确认 (＾▽＾)\n\n"
        "收到你的确认，我们正式从「研究需求确定」进入「研究计划生成」阶段。\n\n"
        "说明：以下计划框架基于你刚确认的研究方向与通用技术概览，尚未执行正式检索；"
        "具体论文、实现细节、设备需求和实验结论仍需在你确认后核验。\n\n"
        "**已完成的工作**\n"
        "- 确定核心研究主题：图卷积神经网络在生物分子图性质预测上的应用\n"
        "- 明确研究问题框架：分子图表示 + 图卷积消息传递 + 整图读出 + 性质预测\n\n"
        "做图神经网络训练，设备配置直接影响实验方案设计。\n\n"
        "**问题一：你的计算设备是什么？**\n"
        "请如实填写你的 GPU 型号与显存 (｡･ω･｡)"
    )
    is_valid_ok, reason_ok = validate_jiangjiang_output(
        valid_stage_transition_text,
        learning_record_mode=False,
    )
    assert is_valid_ok, (
        f"Stage transition with valid source_scope was falsely rejected: {reason_ok}"
    )
    assert reason_ok is None


def test_validate_jiangjiang_output_source_scope_position() -> None:
    """Source scope must protect the entire text, occurring before any technical claims."""
    # Text where technical claims appear first, scope appears later:
    # Uses terms from _TECHNICAL_TOPIC_PATTERN: 分子图表示, 消息传递机制, 整图读出, 性质预测头
    scope_in_middle_text = (
        "# 收到，方向锁定 (＾▽＾)\n\n"
        "核心流程：分子图表示 → 消息传递机制 → 整图读出 → 性质预测头。\n\n"
        "说明：下面是基于学习记录生成的探索方向与通用技术概览，尚未执行正式检索；"
        "具体论文、实现细节和实验结论仍需在你确认后核验。\n\n"
        "请问你的计算设备是什么？"
    )
    is_valid, reason = validate_jiangjiang_output(
        scope_in_middle_text,
        learning_record_mode=False,
    )
    assert not is_valid, (
        "Technical statements appearing before source_scope must be rejected"
    )
    assert reason is not None
    assert "source_scope" in reason


def test_validate_jiangjiang_output_unsupported_user_attribution() -> None:
    """Attributing choices/decisions to the user that they never confirmed must be rejected."""
    # User message history only contains generic direction (no A/B/C reply, no "小分子药物"):
    evidence = ["我想做图卷积神经网络在生物分子图性质预测上的应用"]

    # Model asserts that user chose "小分子药物": MUST FAIL
    # Has scope at start so scope check passes; only attribution drives the failure
    unsupported_text = (
        "说明：以下计划框架基于你刚确认的研究方向与通用技术概览，尚未执行正式检索；"
        "具体论文、实现细节、设备需求和实验结论仍需在你确认后核验。\n\n"
        "根据你上一轮的选择（小分子药物），我为你准备了 3 个候选问题：\n"
        "问题 A：ESOL 溶解度预测"
    )
    is_valid, reason = validate_jiangjiang_output(
        unsupported_text,
        evidence_context=evidence,
        learning_record_mode=False,
    )
    assert not is_valid, (
        "Attributing unconfirmed choice '小分子药物' to user must be rejected"
    )
    assert reason is not None
    assert "user attribution" in reason or "unconfirmed choice" in reason

    # If user DID say "小分子药物", it should pass:
    supported_evidence = [
        "我想做图卷积神经网络在生物分子图性质预测上的应用",
        "我选 A 小分子药物",
    ]
    is_valid_ok, reason_ok = validate_jiangjiang_output(
        unsupported_text,
        evidence_context=supported_evidence,
        learning_record_mode=False,
    )
    assert is_valid_ok, f"Supported attribution was falsely rejected: {reason_ok}"
    assert reason_ok is None


def test_validate_jiangjiang_output_learning_record_mastery_and_capability_claims() -> None:
    """Verify that ungrounded mastery, capability, and progression claims are strictly rejected."""
    learning_evidence = [
        "你好姜姜，我刚学完图神经网络，想开始做科研",
        "已学内容：图卷积网络(GCN)数学推导与节点分类",
        "学习进度：完成理论推导，准备开展真实实验",
    ]

    violations = [
        "你已经完成了GCN数学推导和节点分类的理论学习，打下了扎实的基础。",
        "根据学习记录，你已经掌握了GCN的数学推导与节点分类。",
        "你从理论学习进阶到真实实验，具备了开展科研的能力。",
        "你已经对图神经网络有了系统深入的理解。",
        "你已经完成了从理论到实验的学习跨度。",
        "这表明你已经具备了开展课题研究的充分准备。",
        "你已经具备了很好的科研起点与科研能力。",
        "学习端记录显示你已经打下了扎实的图神经网络基础。",
    ]
    for text in violations:
        full_text = (
            "说明：下面是基于学习记录生成的探索方向与通用技术概览，尚未执行正式检索；"
            "具体论文、实现细节和实验结论仍需在你确认后核验。\n\n"
            f"{text}"
        )
        is_valid, reason = validate_jiangjiang_output(
            full_text,
            evidence_context=learning_evidence,
            learning_record_mode=True,
        )
        assert not is_valid, f"Mastery claim was falsely accepted: {text}"
        assert reason is not None

    compliant_cases = [
        (
            "说明：下面是基于学习记录生成的探索方向与通用技术概览，尚未执行正式检索；"
            "具体论文、实现细节和实验结论仍需在你确认后核验。\n\n"
            "学习端记录显示你已学习「图卷积网络(GCN)数学推导与节点分类」，"
            "当前进度记录为「完成理论推导，准备开展真实实验」。"
            "这些学习记录不代表已掌握或具备研究能力，实际理解与代码经验仍需确认。"
        ),
        (
            "说明：下面是基于学习记录生成的探索方向与通用技术概览，尚未执行正式检索；"
            "具体论文、实现细节和实验结论仍需在你确认后核验。\n\n"
            "学习端记录显示你学习过 GCN 数学推导与节点分类。"
            "这些记录不代表已掌握或具备科研能力，实际理解和代码经验仍需确认。"
        ),
    ]
    for text in compliant_cases:
        is_valid, reason = validate_jiangjiang_output(
            text,
            evidence_context=learning_evidence,
            learning_record_mode=True,
        )
        assert is_valid, f"Compliant learning record text was falsely rejected: {text} ({reason})"
        assert reason is None


def test_source_scope_prefix_welcome_no_confirmed_direction() -> None:
    """Verify S1 welcome scope prefix does not claim confirmed direction
    and specifies learning records.
    """
    assert "已确认方向" not in RESEARCH_SOURCE_SCOPE_PREFIX_WELCOME
    assert "学习端记录与通用技术概览" in RESEARCH_SOURCE_SCOPE_PREFIX_WELCOME
    assert "尚未执行正式检索" in RESEARCH_SOURCE_SCOPE_PREFIX_WELCOME


def test_source_scope_prefix_clarification() -> None:
    """Verify S2 clarification scope prefix specifies explored direction."""
    assert "探索方向" in RESEARCH_SOURCE_SCOPE_PREFIX_CLARIFICATION
    assert "尚未执行正式检索" in RESEARCH_SOURCE_SCOPE_PREFIX_CLARIFICATION


def test_source_scope_prefix_transition() -> None:
    """Verify S3 transition scope prefix specifies confirmed direction."""
    assert "你刚确认的研究方向与通用技术概览" in RESEARCH_SOURCE_SCOPE_PREFIX_TRANSITION
    assert "尚未执行正式检索" in RESEARCH_SOURCE_SCOPE_PREFIX_TRANSITION


def test_get_source_scope_prefix_dispatch() -> None:
    """Verify get_source_scope_prefix dispatches appropriate prefix per template."""
    assert get_source_scope_prefix("welcome_and_bridge") == RESEARCH_SOURCE_SCOPE_PREFIX_WELCOME
    assert (
        get_source_scope_prefix("need_clarification")
        == RESEARCH_SOURCE_SCOPE_PREFIX_CLARIFICATION
    )
    assert get_source_scope_prefix("stage_transition") == RESEARCH_SOURCE_SCOPE_PREFIX_TRANSITION
