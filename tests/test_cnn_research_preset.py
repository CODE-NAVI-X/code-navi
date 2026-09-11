"""API contract for the explicitly labelled, deterministic CNN demo flow."""

from code_navi.research.cnn_research_preset import CNN_RESEARCH_PRESET


def test_cnn_preset_requires_paper_confirmation_before_analysis() -> None:
    opening = CNN_RESEARCH_PRESET.reply("我想研究 CNN。", None)
    assert opening is not None
    assert opening.step == "question"
    assert "CNN 固定演示流程" in opening.content

    blocked = CNN_RESEARCH_PRESET.reply("进入第四阶段。", opening.step)
    assert blocked is not None
    assert blocked.step == "question"
    assert "当前还不能进入第四阶段" in blocked.content

    conditions = CNN_RESEARCH_PRESET.reply(
        "我确认研究不同数据增强策略对 CNN SHAP 解释稳定性的影响。", opening.step
    )
    assert conditions is not None
    papers = CNN_RESEARCH_PRESET.reply("确认，按这个固定实验方案继续。", conditions.step)
    assert papers is not None
    assert "演示预设数据" in papers.content
    confirmation = CNN_RESEARCH_PRESET.reply("我选择第1篇论文。", papers.step)
    assert confirmation is not None
    analysis = CNN_RESEARCH_PRESET.reply(
        "确认，将这篇论文设为当前复现论文。", confirmation.step
    )
    assert analysis is not None
    assert analysis.step == "analysis"
    assert "实验尚未执行" in analysis.content


def test_cnn_preset_never_claims_reproduction_success() -> None:
    reply = CNN_RESEARCH_PRESET.reply("复现成功。", "analysis")
    assert reply is not None
    assert "不能确认“复现成功”" in reply.content
