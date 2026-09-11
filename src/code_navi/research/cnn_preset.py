"""Deterministic, explicitly labelled CNN research-demo preset.

The preset is intentionally separate from live academic search: it provides a
stable scripted path for demos, writes an auditable demo evidence bundle, and
requires an explicit paper confirmation before the analysis stage.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

# 普通入口 `我想研究CNN` 走固定提问流程；固定答案仅由显式演示入口触发。
CNN_PRESET_TRIGGER_TEXT = "我想研究CNN演示"
CNN_PRESET_DEMO_SOURCE = "CNN research preset demo fixture"
CNN_PRESET_DEMO_NOTE = "固定演示候选，不代表本次实时检索结果"
CNN_FIRST_PAPER_TITLE = "Deep Residual Learning for Image Recognition"

CNN_RESEARCH_TOPIC = (
    "研究 CIFAR-10 数据集上，ResNet 模型在不同数据增强策略和随机种子下的 SHAP 解释稳定性。"
)
CNN_RESEARCH_QUESTION_RECORDED = (
    "在 CIFAR-10 和 ResNet-18 上，比较不同数据增强策略与随机种子对 SHAP 特征归因稳定性的影响。"
)

CNN_REPLY_INTRO = (
    "已进入 CNN 研究固定流程。\n\n"
    "本次研究主题已经固定为：\n\n"
    f"{CNN_RESEARCH_TOPIC}\n\n"
    "接下来我会依次完成：\n\n"
    "1. 明确研究问题；\n2. 确定实验计划；\n3. 展示固定的英文论文候选；\n"
    "4. 在你确认论文后进入结果分析。\n\n"
    "第一个问题：\n\n你希望研究 CNN 的哪一个方面？\n\n"
    "本次固定选择为：\n\n比较不同数据增强策略是否会影响 CNN 的 SHAP 特征归因稳定性。"
)
CNN_REPLY_QUESTION_RECORDED = (
    f"研究问题已记录：\n\n{CNN_RESEARCH_QUESTION_RECORDED}\n\n"
    "第二个问题：\n\n本次实验使用以下固定条件：\n\n"
    "- 数据集：CIFAR-10\n- 模型：ResNet-18\n- 输入尺寸：32×32\n"
    "- GPU：RTX 4060 8GB\n- 测试样本：64 张\n- 随机种子：0、1、2\n"
    "- 训练轮数：20 epoch\n- 解释方法：GradientSHAP\n"
    "- 稳定性指标：Spearman 相关系数、Top-10 特征重合率\n"
    "- 执行方式：先小规模验证，再决定是否扩大实验"
)
CNN_REPLY_PAPERS = (
    "实验方案已确认。\n\n现在进入英文论文候选阶段。\n\n"
    "已根据当前 CNN 研究主题生成 5 篇固定英文论文候选。\n\n"
    "说明：以下为 CNN 演示预设候选，用于稳定完成本次研究流程；"
    "不是随机论文，也不是中文论文。\n\n"
    f"来源：{CNN_PRESET_DEMO_SOURCE}\n性质：{CNN_PRESET_DEMO_NOTE}\n\n"
    "1. Deep Residual Learning for Image Recognition\n   用途：ResNet 模型和 CIFAR-10 复现基础\n\n"
    "2. A Survey on Image Data Augmentation for Deep Learning\n   用途：数据增强方法背景\n\n"
    "3. A Unified Approach to Interpreting Model Predictions\n   用途：SHAP 方法基础\n\n"
    "4. Grad-CAM: Visual Explanations from Deep Networks via Gradient-Based Localization\n"
    "   用途：CNN 可解释性参考\n\n"
    "5. SmoothGrad: Removing Noise by Adding Noise\n   用途：解释稳定性和噪声分析参考\n\n"
    "默认推荐第 1 篇，但“推荐”不等于选择，也不等于设置当前复现论文。"
)
CNN_REPLY_SELECT = (
    "你选择的是：\n\n"
    f"{CNN_FIRST_PAPER_TITLE}\n\n"
    "这篇论文将作为本次 ResNet/CIFAR-10 复现候选。\n\n"
    "请再次确认：\n\n是否将这篇论文设为当前复现论文？"
)
CNN_REPLY_CONFIRMED = (
    "论文确认完成。\n\n当前复现论文：\n\n"
    f"{CNN_FIRST_PAPER_TITLE}\n\n现在可以进入第四阶段：结果分析。"
)
CNN_REPLY_ANALYSIS = (
    "第四阶段已开启。\n\n本次固定分析任务：\n\n"
    "1. 使用 CIFAR-10 训练 ResNet-18；\n2. 比较无增强、基础增强和强化增强；\n"
    "3. 使用随机种子 0、1、2；\n4. 每组训练 20 epoch；\n5. 使用 64 张测试样本；\n"
    "6. 使用 GradientSHAP 生成特征归因；\n7. 计算 Spearman 相关系数；\n"
    "8. 计算 Top-10 特征重合率；\n9. 比较不同增强策略下的解释稳定性。\n\n"
    "注意：实验尚未执行，以上只是已确认的实验计划，不代表实验结果。"
)
CNN_REPLY_BLOCK_STAGE4 = "当前还不能进入第四阶段。\n\n请先明确确认一篇论文作为当前复现论文。"
CNN_REPLY_BLOCK_REPRODUCTION = (
    "目前没有足够的实验运行证据，不能确认“复现成功”。\n\n当前只能记录为待验证状态。"
)
CNN_REPLY_BLOCK_ANALYSIS = "当前论文尚未确认，暂不能开始结果分析。"
CNN_REPLY_FALLBACK = "当前正在执行 CNN 固定演示流程。\n\n请按照当前步骤完成确认，不要跳过论文确认。"

CNN_PRESET_PAPERS: tuple[dict[str, object], ...] = (
    {
        "title": CNN_FIRST_PAPER_TITLE,
        "authors": ["Kaiming He", "Xiangyu Zhang", "Shaoqing Ren", "Jian Sun"],
        "year": 2015,
        "url": "https://arxiv.org/abs/1512.03385",
        "identifier": "arXiv:1512.03385",
        "abstract_excerpt": (
            "Deeper neural networks are more difficult to train. We present a residual "
            "learning framework to ease the training of very deep networks."
        ),
        "provenance": (
            f"来源：{CNN_PRESET_DEMO_SOURCE}；用途：ResNet 模型和 CIFAR-10 复现基础；"
            f"{CNN_PRESET_DEMO_NOTE}。"
        ),
    },
    {
        "title": "A Survey on Image Data Augmentation for Deep Learning",
        "authors": ["Connor Shorten", "Taghi M. Khoshgoftaar"],
        "year": 2019,
        "url": "https://arxiv.org/abs/1904.12848",
        "identifier": "arXiv:1904.12848",
        "abstract_excerpt": (
            "This survey discusses data augmentation approaches for image classification "
            "deep learning models."
        ),
        "provenance": (
            f"来源：{CNN_PRESET_DEMO_SOURCE}；用途：数据增强方法背景；"
            f"{CNN_PRESET_DEMO_NOTE}。"
        ),
    },
    {
        "title": "A Unified Approach to Interpreting Model Predictions",
        "authors": ["Scott M. Lundberg", "Su-In Lee"],
        "year": 2017,
        "url": "https://arxiv.org/abs/1705.07874",
        "identifier": "arXiv:1705.07874",
        "abstract_excerpt": (
            "We present a unified framework for interpreting predictions: SHAP values "
            "assign each feature an importance for a particular prediction."
        ),
        "provenance": (
            f"来源：{CNN_PRESET_DEMO_SOURCE}；用途：SHAP 方法基础；"
            f"{CNN_PRESET_DEMO_NOTE}。"
        ),
    },
    {
        "title": "Grad-CAM: Visual Explanations from Deep Networks via Gradient-Based Localization",
        "authors": ["Ramprasaath R. Selvaraju", "Michael Cogswell", "Abhishek Das"],
        "year": 2016,
        "url": "https://arxiv.org/abs/1610.02391",
        "identifier": "arXiv:1610.02391",
        "abstract_excerpt": (
            "Grad-CAM uses the gradients of a target concept flowing into the final "
            "convolutional layer to produce a coarse localization map."
        ),
        "provenance": (
            f"来源：{CNN_PRESET_DEMO_SOURCE}；用途：CNN 可解释性参考；"
            f"{CNN_PRESET_DEMO_NOTE}。"
        ),
    },
    {
        "title": "SmoothGrad: Removing Noise by Adding Noise",
        "authors": ["Daniel Smilkov", "Nikhil Thorat", "Been Kim"],
        "year": 2017,
        "url": "https://arxiv.org/abs/1706.03825",
        "identifier": "arXiv:1706.03825",
        "abstract_excerpt": (
            "SmoothGrad sensitizes saliency maps by averaging sensitivity maps over noisy "
            "copies of the input."
        ),
        "provenance": (
            f"来源：{CNN_PRESET_DEMO_SOURCE}；用途：解释稳定性和噪声分析参考；"
            f"{CNN_PRESET_DEMO_NOTE}。"
        ),
    },
)

CNN_PRESET_PROGRESS_TEMPLATES = {
    "cnn_preset_intro": "await_question_record",
    "cnn_preset_question_recorded": "await_conditions",
    "cnn_preset_conditions": "await_conditions",
    "cnn_preset_papers": "await_select",
    "cnn_preset_select": "await_confirm",
    "cnn_preset_confirmed": "await_analysis",
    "cnn_preset_analysis": "finished",
}


def is_cnn_preset_trigger(message: str) -> bool:
    text = (message or "").strip()
    while text and text[-1] in "。.":
        text = text[:-1].rstrip()
    return text == CNN_PRESET_TRIGGER_TEXT


def cnn_preset_step(messages: Sequence[Mapping[str, object]]) -> str:
    for msg in reversed(messages or []):
        if msg.get("role") == "assistant":
            step = CNN_PRESET_PROGRESS_TEMPLATES.get(str(msg.get("template") or ""))
            if step is not None:
                return step
    return "trigger"


# Reproduction-success claims are handled before any preset step or fallback.
# This checks only the current user message; assistant history is never parsed
# as a new user claim by the orchestrator.
_REPRODUCTION_SUCCESS_MARKERS = ("复现成功", "实验成功", "成功复现")


def is_reproduction_success_claim(message: str) -> bool:
    """Return whether the current user message claims successful reproduction."""
    text = (message or "").strip()
    return any(marker in text for marker in _REPRODUCTION_SUCCESS_MARKERS)


def cnn_preset_refusal(message: str, *, paper_confirmed: bool) -> str | None:
    text = (message or "").strip()
    if not text:
        return None
    if is_reproduction_success_claim(text):
        return CNN_REPLY_BLOCK_REPRODUCTION
    if paper_confirmed:
        return None
    if "第四阶段" in text:
        return CNN_REPLY_BLOCK_STAGE4
    if any(token in text for token in ("结果分析", "继续分析", "开始分析")) or (
        text.rstrip("。.！!？?").endswith("分析")
    ):
        return CNN_REPLY_BLOCK_ANALYSIS
    return None


def cnn_preset_matches_step(step: str, message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if step == "await_question_record":
        return "确认" in text or "数据增强" in text
    if step == "await_conditions":
        return "确认" in text and ("实验方案" in text or "方案" in text)
    if step == "await_select":
        return any(
            key in text for key in ("第1篇", "第 1 篇", "第1个", "第一篇", "选择第")
        ) or ("选择" in text and "论文" in text)
    if step == "await_confirm":
        return "确认" in text
    if step == "await_analysis":
        return "分析" in text or "第四阶段" in text
    return False


def cnn_preset_fixed_replies() -> dict[str, str]:
    return {
        "intro": CNN_REPLY_INTRO,
        "question_recorded": CNN_REPLY_QUESTION_RECORDED,
        "papers": CNN_REPLY_PAPERS,
        "select": CNN_REPLY_SELECT,
        "confirmed": CNN_REPLY_CONFIRMED,
        "analysis": CNN_REPLY_ANALYSIS,
        "block_stage4": CNN_REPLY_BLOCK_STAGE4,
        "block_reproduction": CNN_REPLY_BLOCK_REPRODUCTION,
        "block_analysis": CNN_REPLY_BLOCK_ANALYSIS,
        "fallback": CNN_REPLY_FALLBACK,
    }


__all__ = [
    name
    for name in globals()
    if name.startswith("CNN_")
    or name.startswith("cnn_")
    or name == "is_cnn_preset_trigger"
]
