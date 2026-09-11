"""Deterministic, clearly labelled CNN script used only for the product demo."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CnnPresetReply:
    step: str
    content: str


class CnnResearchPreset:
    """A fixed, non-searching conversation flow for the CNN recording path."""

    marker = "cnn-research-preset.v1"

    def reply(self, message: str, step: str | None) -> CnnPresetReply | None:
        normalized = "".join(message.lower().split()).replace("。", "")
        if step is None and normalized in {"我想研究cnn", "我想研究卷积神经网络"}:
            return CnnPresetReply("question", self._opening())
        if step is None:
            return None
        if "复现成功" in message:
            return CnnPresetReply(
                step,
                "目前没有足够的实验运行证据，不能确认“复现成功”。\n\n"
                "当前只能记录为待验证状态。",
            )
        if step in {"question", "conditions", "papers", "paper_confirmation"} and "第四阶段" in message:
            return CnnPresetReply(
                step, "当前还不能进入第四阶段。\n\n请先明确确认一篇论文作为当前复现论文。"
            )
        if step in {"question", "conditions", "papers", "paper_confirmation"} and "继续分析" in message:
            return CnnPresetReply(step, "当前论文尚未确认，暂不能开始结果分析。")
        if step == "question" and "确认研究不同数据增强策略" in message:
            return CnnPresetReply("conditions", self._conditions())
        if step == "conditions" and "确认" in message and "固定实验方案" in message:
            return CnnPresetReply("papers", self._papers())
        if step == "papers" and ("选择第1篇" in message or "选择第1篇论文" in message):
            return CnnPresetReply("paper_confirmation", self._paper_confirmation())
        if step == "paper_confirmation" and "确认" in message and "当前复现论文" in message:
            return CnnPresetReply("analysis", self._analysis())
        return CnnPresetReply(
            step, "CNN 固定演示流程只接受当前步骤的预设确认语句，请按屏幕中的固定脚本继续。"
        )

    @staticmethod
    def _opening() -> str:
        return """## CNN 固定演示流程

已进入 CNN 研究固定流程。

本次研究主题已经固定为：研究 CIFAR-10 数据集上，ResNet 模型在不同数据增强策略和随机种子下的
SHAP 解释稳定性。

接下来依次明确研究问题、确认实验计划、展示固定英文论文候选，并在论文二次确认后进入结果分析。

第一个问题：你希望研究 CNN 的哪一个方面？

本次固定选择为：比较不同数据增强策略是否会影响 CNN 的 SHAP 特征归因稳定性。"""

    @staticmethod
    def _conditions() -> str:
        return """研究问题已记录：在 CIFAR-10 和 ResNet-18 上，比较不同数据增强策略与随机种子对
SHAP 特征归因稳定性的影响。

第二个问题：本次实验使用以下固定条件：

- 数据集：CIFAR-10；模型：ResNet-18；输入尺寸：32×32
- GPU：RTX 4060 8GB；测试样本：64 张；随机种子：0、1、2
- 训练轮数：20 epoch；解释方法：GradientSHAP
- 稳定性指标：Spearman 相关系数、Top-10 特征重合率
- 执行方式：先小规模验证，再决定是否扩大实验

请回复：确认，按这个固定实验方案继续。"""

    @staticmethod
    def _papers() -> str:
        return """实验方案已确认。现在进入英文论文候选阶段。

### 论文候选：演示预设数据

以下是 CNN 演示预设候选，不是随机论文，也不是实时检索结果。

1. **Deep Residual Learning for Image Recognition**：ResNet 模型和 CIFAR-10 复现基础
2. **A Survey on Image Data Augmentation for Deep Learning**：数据增强方法背景
3. **A Unified Approach to Interpreting Model Predictions**：SHAP 方法基础
4. **Grad-CAM: Visual Explanations from Deep Networks via Gradient-Based Localization**：
   CNN 可解释性参考
5. **SmoothGrad: Removing Noise by Adding Noise**：解释稳定性和噪声分析参考

本次默认推荐第 1 篇作为复现候选。"""

    @staticmethod
    def _paper_confirmation() -> str:
        return """你选择的是：**Deep Residual Learning for Image Recognition**。

这篇论文将作为本次 ResNet/CIFAR-10 复现候选。请再次确认：是否将这篇论文设为当前复现论文？"""

    @staticmethod
    def _analysis() -> str:
        return """论文确认完成。当前复现论文：**Deep Residual Learning for Image Recognition**。

## 第四阶段：结果分析

本次固定分析任务：

1. 使用 CIFAR-10 训练 ResNet-18，并比较无增强、基础增强和强化增强；
2. 使用随机种子 0、1、2；每组训练 20 epoch；使用 64 张测试样本；
3. 使用 GradientSHAP 生成特征归因，计算 Spearman 相关系数和 Top-10 特征重合率；
4. 比较不同增强策略下的解释稳定性。

注意：实验尚未执行，以上只是已确认的实验计划，不代表实验结果。"""


CNN_RESEARCH_PRESET = CnnResearchPreset()
