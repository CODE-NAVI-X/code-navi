"""Standard metrics catalog and rule-based helpers for experiment design.

Pure rule-based catalog (no LLM calls) defining standard metrics per task type,
inferring task type from research profile, and normalizing model-suggested metrics.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

TaskType = Literal[
    "classification",
    "regression",
    "clustering",
    "retrieval",
    "generation",
    "other",
]


class StandardMetricDefinition(BaseModel):
    """Immutable specification for a metric in the standard catalog."""

    name: str = Field(min_length=1, max_length=64)
    aliases: list[str] = Field(default_factory=list)
    definition: str = Field(min_length=1, max_length=300)
    formula: str | None = Field(default=None, max_length=300)
    higher_is_better: bool = True
    applies_to_task_type: list[TaskType] = Field(min_length=1)


# Standard metrics catalog matching contract §2.4
STANDARD_METRICS: list[StandardMetricDefinition] = [
    # classification: ACC, Precision, Recall, F1, AUC
    StandardMetricDefinition(
        name="ACC",
        aliases=["accuracy", "准确率", "acc"],
        definition="预测正确的样本数占总样本数的比例。",
        formula="Accuracy = (TP + TN) / (TP + TN + FP + FN)",
        higher_is_better=True,
        applies_to_task_type=["classification"],
    ),
    StandardMetricDefinition(
        name="Precision",
        aliases=["精确率", "查准率", "precision"],
        definition="预测为正例的样本中真正为正例的比例。",
        formula="Precision = TP / (TP + FP)",
        higher_is_better=True,
        applies_to_task_type=["classification"],
    ),
    StandardMetricDefinition(
        name="Recall",
        aliases=["召回率", "查全率", "recall"],
        definition="真实正例样本中被正确预测为正例的比例。",
        formula="Recall = TP / (TP + FN)",
        higher_is_better=True,
        applies_to_task_type=["classification"],
    ),
    StandardMetricDefinition(
        name="F1",
        aliases=["f1-score", "f1 score", "f1", "f1值"],
        definition="Precision 与 Recall 的调和平均数，综合衡量查准与查全能力。",
        formula="F1 = 2 * (Precision * Recall) / (Precision + Recall)",
        higher_is_better=True,
        applies_to_task_type=["classification"],
    ),
    StandardMetricDefinition(
        name="AUC",
        aliases=["roc-auc", "auc-roc", "roc_auc", "auc"],
        definition="ROC 曲线下的面积，衡量二分类排序能力，不受分类阈值影响。",
        formula="AUC = P(Score(positive) > Score(negative))",
        higher_is_better=True,
        applies_to_task_type=["classification"],
    ),
    # regression: RMSE, MAE, R²
    StandardMetricDefinition(
        name="RMSE",
        aliases=["root mean squared error", "均方根误差", "rmse"],
        definition="均方误差的算术平方根，对大误差有较高惩罚权重。",
        formula="RMSE = sqrt(sum((y_i - y_hat_i)^2) / n)",
        higher_is_better=False,
        applies_to_task_type=["regression"],
    ),
    StandardMetricDefinition(
        name="MAE",
        aliases=["mean absolute error", "平均绝对误差", "mae"],
        definition="预测值与真实值差值绝对值的平均值，稳健反映线性误差。",
        formula="MAE = sum(|y_i - y_hat_i|) / n",
        higher_is_better=False,
        applies_to_task_type=["regression"],
    ),
    StandardMetricDefinition(
        name="R²",
        aliases=["r2", "r-squared", "r squared", "决定系数", "r^2"],
        definition="决定系数，表征模型对因变量方差的解释比例，最大为 1.0。",
        formula="R^2 = 1 - (sum((y_i - y_hat_i)^2) / sum((y_i - y_mean)^2))",
        higher_is_better=True,
        applies_to_task_type=["regression"],
    ),
    # clustering: Silhouette, ARI, NMI
    StandardMetricDefinition(
        name="Silhouette",
        aliases=["轮廓系数", "silhouette score", "silhouette coefficient", "silhouette"],
        definition="轮廓系数，结合类内紧密度与类间分离度评估聚类质量，范围 [-1, 1]。",
        formula="s(i) = (b(i) - a(i)) / max(a(i), b(i))",
        higher_is_better=True,
        applies_to_task_type=["clustering"],
    ),
    StandardMetricDefinition(
        name="ARI",
        aliases=["adjusted rand index", "调整兰德系数", "ari"],
        definition="调整兰德指数，校正随机聚类重叠后的聚类划分一致性度量。",
        formula="ARI = (RI - Expected_RI) / (max(RI) - Expected_RI)",
        higher_is_better=True,
        applies_to_task_type=["clustering"],
    ),
    StandardMetricDefinition(
        name="NMI",
        aliases=["normalized mutual information", "标准互信息", "归一化互信息", "nmi"],
        definition="归一化互信息，评估真实标签与聚类簇之间的信息重合度，范围 [0, 1]。",
        formula="NMI(Y, C) = 2 * I(Y; C) / [H(Y) + H(C)]",
        higher_is_better=True,
        applies_to_task_type=["clustering"],
    ),
    # retrieval: MRR, NDCG, Recall@K
    StandardMetricDefinition(
        name="MRR",
        aliases=["mean reciprocal rank", "平均倒数排名", "mrr"],
        definition="平均倒数排名，衡量第一个相关结果出现排名的倒数均值。",
        formula="MRR = (1 / |Q|) * sum(1 / rank_i)",
        higher_is_better=True,
        applies_to_task_type=["retrieval"],
    ),
    StandardMetricDefinition(
        name="NDCG",
        aliases=["ndcg@k", "normalized discounted cumulative gain", "ndcg"],
        definition="归一化折损累积增益，兼顾检索相关度和排序位置权重的评价指标。",
        formula="NDCG@K = DCG@K / IDCG@K",
        higher_is_better=True,
        applies_to_task_type=["retrieval"],
    ),
    StandardMetricDefinition(
        name="Recall@K",
        aliases=["recall@k", "top-k recall", "topk recall", "recall@"],
        definition="前 K 个检索结果中召回的相关条目占全部相关条目的比例。",
        formula="Recall@K = |Relevant_in_TopK| / |Total_Relevant|",
        higher_is_better=True,
        applies_to_task_type=["retrieval"],
    ),
    # generation: BLEU, ROUGE, 人工评估说明
    StandardMetricDefinition(
        name="BLEU",
        aliases=["bleu-4", "bleu score", "bleu"],
        definition="基于 n-gram 精确率与长度惩罚的文本生成质量自动评估指标。",
        formula="BLEU = BP * exp(sum(w_n * log(p_n)))",
        higher_is_better=True,
        applies_to_task_type=["generation"],
    ),
    StandardMetricDefinition(
        name="ROUGE",
        aliases=["rouge-l", "rouge-1", "rouge-2", "rouge"],
        definition="基于 n-gram 及最长公共子序列召回率的文本摘要与生成评估指标。",
        formula="ROUGE-L = LCS(Reference, Candidate) / Length(Reference)",
        higher_is_better=True,
        applies_to_task_type=["generation"],
    ),
    StandardMetricDefinition(
        name="人工评估说明",
        aliases=["human evaluation", "人工评估", "人工评分", "expert evaluation"],
        definition="通过制定评分量表由人工评估者对生成文本的流畅性、准确性、合理性进行定性/定量评定。",
        formula=None,
        higher_is_better=True,
        applies_to_task_type=["generation"],
    ),
]

_LOOKUP_MAP: dict[str, StandardMetricDefinition] = {}
for _metric in STANDARD_METRICS:
    _LOOKUP_MAP[_metric.name.casefold()] = _metric
    for _alias in _metric.aliases:
        _LOOKUP_MAP[_alias.casefold()] = _metric


def find_standard_metric(name: str) -> StandardMetricDefinition | None:
    """Find a standard metric definition by name or alias (case-insensitive)."""
    normalized = name.strip().casefold()
    if normalized in _LOOKUP_MAP:
        return _LOOKUP_MAP[normalized]
    # Check prefix matches
    if normalized.startswith("recall@") or normalized.startswith("top-k recall"):
        return _LOOKUP_MAP["recall@k"]
    if normalized.startswith("ndcg"):
        return _LOOKUP_MAP["ndcg"]
    return None


_NUMERIC_ASSERTION_RE = re.compile(
    r"(?:(?:达到|大于|超过|约为|约|达|>=|<=|>|<|=|>=)?\s*\d+(?:\.\d+)?%?)"
    r"|(?:准确率\s*\d+%)"
    r"|(?:\b\d+(?:\.\d+)?%\b)",
    re.IGNORECASE,
)


def strip_numeric_assertion(text: str) -> str:
    """Strip fabricated numeric assertions like '准确率 92%' or '>=0.85' from text."""
    cleaned = _NUMERIC_ASSERTION_RE.sub("", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.replace("（）", "").replace("()", "").strip(" ,;；，。")
    return cleaned or text.strip()


def infer_task_type(
    *,
    methods: list[str] | None = None,
    research_questions: list[str] | None = None,
    topic: str | None = None,
) -> TaskType:
    """Infer task type from research profile methods, questions, and topic via rules."""
    text_chunks: list[str] = []
    if topic:
        text_chunks.append(topic)
    if methods:
        text_chunks.extend(methods)
    if research_questions:
        text_chunks.extend(research_questions)

    combined = " ".join(text_chunks).lower()
    if not combined.strip():
        return "other"

    if re.search(r"检索|搜索|retrieval|ranking|search|倒排|推荐|recommend", combined):
        return "retrieval"
    if re.search(r"聚类|分群|cluster|clustering|k-means|kmeans|dbscan", combined):
        return "clustering"
    if re.search(r"回归|预测数值|房价|趋势|regression|time series|时序预测|连续值", combined):
        return "regression"
    if re.search(r"生成|摘要|问答|翻译|代码生成|generation|llm|对话|gpt|prompt|agent", combined):
        return "generation"
    if re.search(r"分类|识别|检测|判断|情绪|classification|classifier|detec", combined):
        return "classification"

    return "other"
