"""Static structure and framework practice exercises.

This module is intentionally independent from the Piston execution path.  It
provides a small server-owned catalog of non-executable exercises, such as
ordering a CNN pipeline or completing a PyTorch layer, and grades them with
deterministic rules.  Nothing here runs student code, installs dependencies, or
touches the shared database.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = "structure-practice.v1"

DOMAIN_LABELS = {
    "cnn": "CNN 图像识别",
    "rnn": "RNN 序列建模",
    "transformer": "Transformer",
    "linear_models": "线性模型",
    "tree_models": "树模型",
    "optimization": "优化算法",
    "clustering": "聚类算法",
}


class StructureExerciseKind(StrEnum):
    """Supported static exercise interaction kinds."""

    STRUCTURE_SEQUENCE = "structure_sequence"
    FRAMEWORK_FILL = "framework_fill"


@dataclass(frozen=True, slots=True)
class StructureLevel:
    """One hierarchical ordering level within a sequence exercise."""

    level: int
    title: str
    instruction: str
    options: tuple[str, ...]
    answer_sequence: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.level < 1:
            raise ValueError("level must be >= 1")
        if not self.options or not self.answer_sequence:
            raise ValueError("level options and answer_sequence are required")
        if set(self.answer_sequence) != set(self.options):
            raise ValueError("answer_sequence must use exactly the declared options")


class StructureExerciseValidationError(ValueError):
    """The structure exercise request is invalid."""


class StructureExerciseNotFoundError(LookupError):
    """The requested structure exercise does not exist."""


@dataclass(frozen=True, slots=True)
class StructureExercise:
    """An immutable server-owned structure or framework exercise."""

    id: str
    title: str
    domain: str
    objective: str
    instruction: str
    kind: StructureExerciseKind
    prompt: str
    options: tuple[str, ...] = ()
    starter_code: str | None = None
    answer_sequence: tuple[str, ...] = ()
    required_tokens: tuple[str, ...] = ()
    hints: tuple[str, ...] = ()
    explanation: str = ""
    levels: tuple[StructureLevel, ...] = ()

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("id must be a non-empty string")
        if not self.title.strip():
            raise ValueError("title must be a non-empty string")
        if not self.domain.strip():
            raise ValueError("domain must be a non-empty string")
        if not self.objective.strip():
            raise ValueError("objective must be a non-empty string")
        if not self.instruction.strip():
            raise ValueError("instruction must be a non-empty string")
        if not self.prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        if not isinstance(self.kind, StructureExerciseKind):
            raise ValueError("kind must be a StructureExerciseKind")
        if self.kind is StructureExerciseKind.STRUCTURE_SEQUENCE:
            if self.levels:
                if self.options or self.answer_sequence:
                    raise ValueError("levels must be used without legacy options")
                level_numbers = [level.level for level in self.levels]
                if level_numbers != list(range(1, len(self.levels) + 1)):
                    raise ValueError("levels must be numbered sequentially from 1")
            elif not self.options or not self.answer_sequence:
                raise ValueError("sequence exercises require options and answer_sequence")
            elif set(self.answer_sequence) != set(self.options):
                raise ValueError("answer_sequence must use exactly the declared options")
        if self.kind is StructureExerciseKind.FRAMEWORK_FILL:
            if not self.required_tokens:
                raise ValueError("framework exercises require required_tokens")
            if self.starter_code is None:
                raise ValueError("framework exercises require starter_code")

    def as_summary(self) -> dict[str, Any]:
        """Return public exercise fields without the answer or grading rules."""

        payload: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "kind": self.kind.value,
            "domain": self.domain,
            "objective": self.objective,
            "instruction": self.instruction,
            "prompt": self.prompt,
            "options": list(self.options),
            "hints": list(self.hints),
        }
        if self.starter_code is not None:
            payload["starterCode"] = self.starter_code
        if self.levels:
            payload["levels"] = [
                {
                    "level": level.level,
                    "title": level.title,
                    "instruction": level.instruction,
                    "options": list(level.options),
                }
                for level in self.levels
            ]
        return payload


DEFAULT_EXERCISES = (
    StructureExercise(
        id="cnn-image-classification-pipeline",
        title="CNN 图像识别主干顺序",
        domain="cnn",
        objective="理解典型 CNN 图像分类任务的主干流程。",
        instruction="将下列模块按从输入图像到分类输出的顺序排列。",
        kind=StructureExerciseKind.STRUCTURE_SEQUENCE,
        prompt="输入一张图像后，典型 CNN 分类网络的主干步骤应该怎样组织？",
        levels=(
            StructureLevel(
                level=1,
                title="CNN 主干流程",
                instruction="按从输入图像到分类输出的顺序排列。",
                options=(
                    "读取并归一化图像",
                    "使用卷积层提取局部特征",
                    "使用 ReLU 增加非线性",
                    "使用池化层缩小空间尺寸",
                    "将特征展平为一维向量",
                    "使用全连接层输出类别",
                ),
                answer_sequence=(
                    "读取并归一化图像",
                    "使用卷积层提取局部特征",
                    "使用 ReLU 增加非线性",
                    "使用池化层缩小空间尺寸",
                    "将特征展平为一维向量",
                    "使用全连接层输出类别",
                ),
            ),
            StructureLevel(
                level=2,
                title="卷积层参数设计",
                instruction="按单个卷积层参数设计顺序排列。",
                options=(
                    "确定输入通道数",
                    "确定输出通道数",
                    "选择卷积核大小",
                    "设置 padding",
                    "设置 stride",
                ),
                answer_sequence=(
                    "确定输入通道数",
                    "确定输出通道数",
                    "选择卷积核大小",
                    "设置 padding",
                    "设置 stride",
                ),
            ),
            StructureLevel(
                level=3,
                title="卷积块内部结构",
                instruction="按卷积块内部模块顺序排列。",
                options=(
                    "Conv2d",
                    "BatchNorm2d",
                    "ReLU",
                    "MaxPool2d",
                ),
                answer_sequence=(
                    "Conv2d",
                    "BatchNorm2d",
                    "ReLU",
                    "MaxPool2d",
                ),
            ),
        ),
        hints=(
            "卷积层负责提取特征，激活函数增加非线性，池化层用于下采样。",
        ),
        explanation=(
            "典型流程是先准备图像数据，再用卷积层提取局部特征；"
            "激活函数让网络具备非线性表达；池化层降低空间尺寸；"
            "最后展平特征并由全连接层映射到类别。"
        ),
    ),
    StructureExercise(
        id="pytorch-conv2d-layer",
        title="补全 PyTorch 第一层卷积",
        domain="cnn",
        objective="理解 nn.Conv2d 的输入通道、输出通道和卷积核参数。",
        instruction="补全 __BLANK__，让第一个卷积块接收单通道输入并输出 32 通道，卷积核为 3x3。",
        kind=StructureExerciseKind.FRAMEWORK_FILL,
        prompt="下面是一个简单的 PyTorch 模型骨架，请补全第一个卷积层。",
        starter_code=(
            "import torch.nn as nn\n\n"
            "class SimpleCNN(nn.Module):\n"
            "    def __init__(self):\n"
            "        super().__init__()\n"
            "        self.features = nn.Sequential(\n"
            "            __BLANK__,\n"
            "            nn.BatchNorm2d(32),\n"
            "            nn.ReLU(),\n"
            "            nn.MaxPool2d(2),\n"
            "        )\n"
            "        self.fc = nn.Linear(32 * 14 * 14, 10)\n"
            "\n"
            "    def forward(self, x):\n"
            "        x = self.features(x)\n"
            "        x = x.view(x.size(0), -1)\n"
            "        return self.fc(x)\n"
        ),
        required_tokens=(
            "nn.Conv2d",
            "in_channels=1",
            "out_channels=32",
            "kernel_size=3",
        ),
        hints=(
            "PyTorch 卷积层是 nn.Conv2d。",
            "注意输入通道、输出通道和 kernel_size 三个关键参数。",
        ),
        explanation=(
            "第一个卷积层需要使用 nn.Conv2d，并明确 in_channels=1、"
            "out_channels=32 和 kernel_size=3。"
        ),
    ),
    StructureExercise(
        id="rnn-lstm-pipeline",
        title="LSTM 序列建模主干顺序",
        domain="rnn",
        objective="理解 LSTM 从输入序列到隐藏状态的基本流程。",
        instruction="将下列 LSTM 相关步骤按逻辑顺序排列。",
        kind=StructureExerciseKind.STRUCTURE_SEQUENCE,
        prompt="使用 LSTM 处理序列时，典型的计算顺序是什么？",
        options=(
            "将序列转换为向量表示",
            "计算遗忘门",
            "计算输入门和候选状态",
            "更新细胞状态",
            "计算输出门",
            "生成隐藏状态",
        ),
        answer_sequence=(
            "将序列转换为向量表示",
            "计算遗忘门",
            "计算输入门和候选状态",
            "更新细胞状态",
            "计算输出门",
            "生成隐藏状态",
        ),
        hints=(
            "LSTM 的门控机制按遗忘、输入、状态更新、输出顺序组织。",
        ),
        explanation=(
            "LSTM 先用嵌入表示输入，再依次计算遗忘门、输入门和候选状态，"
            "更新细胞状态，最后通过输出门产生隐藏状态。"
        ),
    ),
    StructureExercise(
        id="pytorch-lstm-layer",
        title="补全 PyTorch LSTM 层",
        domain="rnn",
        objective="理解 nn.LSTM 的输入维度、隐藏维度和 batch_first 参数。",
        instruction=(
            "补全 __BLANK__，让 LSTM 接收 10 维输入并输出 32 维隐藏状态，"
            "且输入格式为 batch-first。"
        ),
        kind=StructureExerciseKind.FRAMEWORK_FILL,
        prompt="下面是一个简单的序列模型骨架，请补全 LSTM 层。",
        starter_code=(
            "import torch.nn as nn\n\n"
            "class SequenceModel(nn.Module):\n"
            "    def __init__(self, num_classes):\n"
            "        super().__init__()\n"
            "        self.encoder = __BLANK__\n"
            "        self.fc = nn.Linear(32, num_classes)\n"
            "\n"
            "    def forward(self, x):\n"
            "        output, _ = self.encoder(x)\n"
            "        last = output[:, -1, :]\n"
            "        return self.fc(last)\n"
        ),
        required_tokens=(
            "nn.LSTM",
            "input_size=10",
            "hidden_size=32",
            "batch_first=True",
        ),
        hints=(
            "PyTorch 的 LSTM 层是 nn.LSTM。",
            "注意 input_size、hidden_size 和 batch_first 三个参数。",
        ),
        explanation=(
            "该层应使用 nn.LSTM，并设置 input_size=10、hidden_size=32 和 batch_first=True。"
        ),
    ),
    StructureExercise(
        id="transformer-encoder-pipeline",
        title="Transformer 编码器主干顺序",
        domain="transformer",
        objective="理解 Transformer 编码器中注意力与前馈模块的组织顺序。",
        instruction="将下列 Transformer 编码器步骤按典型顺序排列。",
        kind=StructureExerciseKind.STRUCTURE_SEQUENCE,
        prompt="Transformer 编码器一层中，典型计算顺序是什么？",
        options=(
            "输入嵌入",
            "加入位置编码",
            "计算自注意力",
            "注意力后残差连接与 LayerNorm",
            "前馈网络",
            "前馈后残差连接与 LayerNorm",
        ),
        answer_sequence=(
            "输入嵌入",
            "加入位置编码",
            "计算自注意力",
            "注意力后残差连接与 LayerNorm",
            "前馈网络",
            "前馈后残差连接与 LayerNorm",
        ),
        hints=(
            "注意力和前馈网络之后通常都有残差连接和 LayerNorm。",
        ),
        explanation=(
            "Transformer 编码器先对输入做嵌入和位置编码，再依次经过自注意力、"
            "残差加归一化、前馈网络和第二次残差加归一化。"
        ),
    ),
    StructureExercise(
        id="pytorch-transformer-layer",
        title="补全 PyTorch Transformer 编码器层",
        domain="transformer",
        objective="理解 nn.TransformerEncoderLayer 的关键维度参数。",
        instruction="补全 __BLANK__，让编码器使用 64 维特征和 4 个注意力头。",
        kind=StructureExerciseKind.FRAMEWORK_FILL,
        prompt="下面是一个 Transformer 编码器骨架，请补全编码器层。",
        starter_code=(
            "import torch.nn as nn\n\n"
            "class TextEncoder(nn.Module):\n"
            "    def __init__(self, d_model, nhead, num_layers):\n"
            "        super().__init__()\n"
            "        self.embedding = nn.Embedding(1000, d_model)\n"
            "        layer = __BLANK__\n"
            "        self.transformer = nn.TransformerEncoder(layer, num_layers=num_layers)\n"
            "\n"
            "    def forward(self, tokens):\n"
            "        embedded = self.embedding(tokens)\n"
            "        return self.transformer(embedded)\n"
        ),
        required_tokens=(
            "nn.TransformerEncoderLayer",
            "d_model=64",
            "nhead=4",
        ),
        hints=(
            "PyTorch 的编码器层是 nn.TransformerEncoderLayer。",
            "需要指定 d_model 和 nhead。",
        ),
        explanation=(
            "编码器层应使用 nn.TransformerEncoderLayer，并设置 d_model=64、nhead=4。"
        ),
    ),
    StructureExercise(
        id="logistic-regression-pipeline",
        title="逻辑回归训练流程",
        domain="linear_models",
        objective="理解逻辑回归从输入到概率输出的结构。",
        instruction="将下列逻辑回归步骤按典型顺序排列。",
        kind=StructureExerciseKind.STRUCTURE_SEQUENCE,
        prompt="训练逻辑回归模型时，典型流程是什么？",
        options=(
            "准备特征与标签",
            "线性变换得到 logits",
            "使用 sigmoid 得到概率",
            "计算交叉熵损失",
            "计算梯度并更新参数",
            "用阈值得到类别预测",
        ),
        answer_sequence=(
            "准备特征与标签",
            "线性变换得到 logits",
            "使用 sigmoid 得到概率",
            "计算交叉熵损失",
            "计算梯度并更新参数",
            "用阈值得到类别预测",
        ),
        hints=(
            "逻辑回归先得到线性输出，再映射到概率，最后根据阈值分类。",
        ),
        explanation=(
            "逻辑回归先做线性变换得到 logits，再用 sigmoid 映射到概率，"
            "训练时计算交叉熵损失并更新参数，推理时按阈值输出类别。"
        ),
    ),
    StructureExercise(
        id="sklearn-logistic-regression",
        title="补全 sklearn 逻辑回归",
        domain="linear_models",
        objective="理解 LogisticRegression 的常用结构。",
        instruction="补全 __BLANK__，创建使用 L2 正则的逻辑回归模型。",
        kind=StructureExerciseKind.FRAMEWORK_FILL,
        prompt="下面是 sklearn 逻辑回归代码骨架，请补全模型构造。",
        starter_code=(
            "from sklearn.linear_model import LogisticRegression\n\n"
            "model = __BLANK__\n"
            "model.fit(X_train, y_train)\n"
            "probabilities = model.predict_proba(X_test)[:, 1]\n"
            "predictions = (probabilities >= 0.5).astype(int)\n"
        ),
        required_tokens=(
            "LogisticRegression",
            "penalty='l2'",
        ),
        hints=(
            "sklearn 使用 LogisticRegression。",
            "L2 正则对应 penalty='l2'。",
        ),
        explanation=(
            "逻辑回归模型应使用 LogisticRegression，并通过 penalty='l2' 指定 L2 正则。"
        ),
    ),
    StructureExercise(
        id="decision-tree-pipeline",
        title="决策树构建流程",
        domain="tree_models",
        objective="理解决策树递归划分数据的过程。",
        instruction="将下列决策树构建步骤按典型顺序排列。",
        kind=StructureExerciseKind.STRUCTURE_SEQUENCE,
        prompt="构建决策树时，典型流程是什么？",
        options=(
            "选择当前数据集的划分特征",
            "根据特征分裂数据",
            "对子节点递归划分",
            "判断是否满足停止条件",
            "剪枝或设置最大深度",
            "用叶节点输出预测结果",
        ),
        answer_sequence=(
            "选择当前数据集的划分特征",
            "根据特征分裂数据",
            "对子节点递归划分",
            "判断是否满足停止条件",
            "剪枝或设置最大深度",
            "用叶节点输出预测结果",
        ),
        hints=(
            "决策树按特征分裂数据，并用停止条件控制树深度。",
        ),
        explanation=(
            "决策树先选择划分特征，再递归分裂数据；达到停止条件后停止，"
            "最后通过叶节点输出预测结果。"
        ),
    ),
    StructureExercise(
        id="sklearn-decision-tree",
        title="补全 sklearn 决策树",
        domain="tree_models",
        objective="理解 DecisionTreeClassifier 的最大深度参数。",
        instruction="补全 __BLANK__，创建最大深度为 5 的决策树分类器。",
        kind=StructureExerciseKind.FRAMEWORK_FILL,
        prompt="下面是 sklearn 决策树代码骨架，请补全模型构造。",
        starter_code="model = __BLANK__\nmodel.fit(X_train, y_train)\n",
        required_tokens=(
            "DecisionTreeClassifier",
            "max_depth=5",
        ),
        hints=(
            "sklearn 使用 DecisionTreeClassifier。",
            "最大深度参数是 max_depth。",
        ),
        explanation=(
            "决策树分类器应使用 DecisionTreeClassifier，并设置 max_depth=5。"
        ),
    ),
    StructureExercise(
        id="gradient-descent-loop",
        title="梯度下降迭代顺序",
        domain="optimization",
        objective="理解参数优化的标准迭代步骤。",
        instruction="将下列梯度下降步骤按典型顺序排列。",
        kind=StructureExerciseKind.STRUCTURE_SEQUENCE,
        prompt="训练模型时，梯度下降的迭代顺序是什么？",
        options=(
            "初始化参数",
            "计算模型预测",
            "计算损失函数",
            "计算梯度",
            "更新参数",
            "判断是否收敛",
        ),
        answer_sequence=(
            "初始化参数",
            "计算模型预测",
            "计算损失函数",
            "计算梯度",
            "更新参数",
            "判断是否收敛",
        ),
        hints=(
            "梯度下降按预测、损失、梯度、更新、收敛判断循环。",
        ),
        explanation=(
            "梯度下降先初始化参数，然后每轮计算预测和损失，反向求梯度，"
            "更新参数，并判断是否达到收敛条件。"
        ),
    ),
    StructureExercise(
        id="gradient-descent-update",
        title="补全参数更新表达式",
        domain="optimization",
        objective="理解学习率和梯度如何共同更新参数。",
        instruction="补全 __BLANK__，使用学习率 learning_rate 和梯度 grad 更新参数。",
        kind=StructureExerciseKind.FRAMEWORK_FILL,
        prompt="下面是梯度下降更新步骤，请补全参数更新。",
        starter_code="param = __BLANK__\n",
        required_tokens=(
            "param",
            "learning_rate",
            "grad",
        ),
        hints=(
            "参数应减去学习率乘以梯度。",
        ),
        explanation=(
            "梯度下降的参数更新应写成 param = param - learning_rate * grad。"
        ),
    ),
    StructureExercise(
        id="kmeans-pipeline",
        title="K-Means 聚类流程",
        domain="clustering",
        objective="理解 K-Means 交替更新中心和分配样本的过程。",
        instruction="将下列 K-Means 步骤按典型顺序排列。",
        kind=StructureExerciseKind.STRUCTURE_SEQUENCE,
        prompt="运行 K-Means 聚类时，典型流程是什么？",
        options=(
            "选择簇数量 K",
            "初始化簇中心",
            "把样本分配到最近中心",
            "重新计算簇中心",
            "判断中心是否稳定",
            "输出最终簇标签",
        ),
        answer_sequence=(
            "选择簇数量 K",
            "初始化簇中心",
            "把样本分配到最近中心",
            "重新计算簇中心",
            "判断中心是否稳定",
            "输出最终簇标签",
        ),
        hints=(
            "K-Means 通过分配样本和更新中心不断迭代。",
        ),
        explanation=(
            "K-Means 先设置簇数量并初始化中心，然后反复分配样本、更新中心，"
            "直到中心稳定，最后输出聚类标签。"
        ),
    ),
    StructureExercise(
        id="sklearn-kmeans",
        title="补全 sklearn K-Means",
        domain="clustering",
        objective="理解 KMeans 的簇数量和随机种子参数。",
        instruction="补全 __BLANK__，创建 3 个簇且结果可复现的 K-Means 模型。",
        kind=StructureExerciseKind.FRAMEWORK_FILL,
        prompt="下面是 sklearn K-Means 代码骨架，请补全模型构造。",
        starter_code="model = __BLANK__\nmodel.fit(X)\n",
        required_tokens=(
            "KMeans",
            "n_clusters=3",
            "random_state=42",
        ),
        hints=(
            "sklearn 使用 KMeans。",
            "需要指定 n_clusters 和 random_state。",
        ),
        explanation=(
            "K-Means 模型应使用 KMeans，并设置 n_clusters=3、random_state=42。"
        ),
    ),
)


def _clean_text(value: str) -> str:
    return value.strip()


def _sequence_result(exercise: StructureExercise, answer: Any) -> dict[str, Any]:
    if exercise.levels:
        return _multi_level_sequence_result(exercise, answer)
    return _single_level_sequence_result(exercise, answer)


def _single_level_sequence_result(exercise: StructureExercise, answer: Any) -> dict[str, Any]:
    if not isinstance(answer, list) or any(not isinstance(item, str) for item in answer):
        raise StructureExerciseValidationError("answer must be an ordered list of strings")
    normalized = tuple(_clean_text(item) for item in answer)
    if len(normalized) != len(exercise.answer_sequence):
        raise StructureExerciseValidationError(
            f"answer must contain {len(exercise.answer_sequence)} items"
        )
    feedback = []
    matched = 0
    for index, (submitted, expected) in enumerate(
        zip(normalized, exercise.answer_sequence, strict=True)
    ):
        correct = submitted == expected
        matched += int(correct)
        feedback.append(
            {
                "index": index,
                "status": "passed" if correct else "failed",
                "message": (
                    f"第 {index + 1} 个模块位置正确。"
                    if correct
                    else f"第 {index + 1} 个模块位置不正确。"
                ),
            }
        )
    accepted = matched == len(exercise.answer_sequence)
    score = round(matched / len(exercise.answer_sequence) * 100)
    return {
        "verdict": "accepted" if accepted else "wrong_answer",
        "score": score,
        "feedback": feedback,
        "explanation": exercise.explanation,
    }


def _multi_level_sequence_result(exercise: StructureExercise, answer: Any) -> dict[str, Any]:
    if not isinstance(answer, list) or len(answer) != len(exercise.levels):
        raise StructureExerciseValidationError(
            f"answer must contain {len(exercise.levels)} ordered levels"
        )
    feedback: list[dict[str, Any]] = []
    matched = 0
    total = 0
    for level, submitted_answer in zip(exercise.levels, answer, strict=True):
        if not isinstance(submitted_answer, list) or any(
            not isinstance(item, str) for item in submitted_answer
        ):
            raise StructureExerciseValidationError("each level answer must be a list of strings")
        normalized = tuple(_clean_text(item) for item in submitted_answer)
        if len(normalized) != len(level.answer_sequence):
            raise StructureExerciseValidationError(
                f"level {level.level} answer must contain {len(level.answer_sequence)} items"
            )
        for index, (submitted, expected) in enumerate(
            zip(normalized, level.answer_sequence, strict=True)
        ):
            correct = submitted == expected
            matched += int(correct)
            total += 1
            feedback.append(
                {
                    "level": level.level,
                    "index": index,
                    "status": "passed" if correct else "failed",
                    "message": (
                        f"第 {level.level} 级第 {index + 1} 个模块位置正确。"
                        if correct
                        else f"第 {level.level} 级第 {index + 1} 个模块位置不正确。"
                    ),
                }
            )
    accepted = matched == total
    score = round(matched / total * 100) if total else 0
    return {
        "verdict": "accepted" if accepted else "wrong_answer",
        "score": score,
        "feedback": feedback,
        "explanation": exercise.explanation,
    }


def _level_sequence_result(
    exercise: StructureExercise,
    level_number: int,
    answer: Any,
) -> dict[str, Any]:
    level = next((item for item in exercise.levels if item.level == level_number), None)
    if level is None:
        raise StructureExerciseValidationError(f"level {level_number} does not exist")
    if not isinstance(answer, list) or any(not isinstance(item, str) for item in answer):
        raise StructureExerciseValidationError("level answer must be an ordered list of strings")
    normalized = tuple(_clean_text(item) for item in answer)
    if len(normalized) != len(level.answer_sequence):
        raise StructureExerciseValidationError(
            f"level {level_number} answer must contain {len(level.answer_sequence)} items"
        )
    feedback: list[dict[str, Any]] = []
    matched = 0
    for index, (submitted, expected) in enumerate(
        zip(normalized, level.answer_sequence, strict=True)
    ):
        correct = submitted == expected
        matched += int(correct)
        feedback.append(
            {
                "level": level_number,
                "index": index,
                "status": "passed" if correct else "failed",
                "message": (
                    f"第 {level_number} 级第 {index + 1} 个模块位置正确。"
                    if correct
                    else f"第 {level_number} 级第 {index + 1} 个模块位置不正确。"
                ),
            }
        )
    accepted = matched == len(level.answer_sequence)
    score = round(matched / len(level.answer_sequence) * 100)
    return {
        "verdict": "accepted" if accepted else "wrong_answer",
        "score": score,
        "feedback": feedback,
        "explanation": exercise.explanation,
    }


def _framework_result(exercise: StructureExercise, answer: Any) -> dict[str, Any]:
    if not isinstance(answer, str) or not answer.strip():
        raise StructureExerciseValidationError("answer must be a non-empty string")
    source = _clean_text(answer)
    feedback = []
    matched = 0
    for token in exercise.required_tokens:
        correct = token in source
        matched += int(correct)
        feedback.append(
            {
                "token": token,
                "status": "passed" if correct else "failed",
                "message": (
                    f"已识别到 {token}。"
                    if correct
                    else f"未识别到 {token}，请检查卷积层定义。"
                ),
            }
        )
    accepted = matched == len(exercise.required_tokens)
    score = round(matched / len(exercise.required_tokens) * 100)
    return {
        "verdict": "accepted" if accepted else "wrong_answer",
        "score": score,
        "feedback": feedback,
        "explanation": exercise.explanation,
    }


class StructurePracticeService:
    """Resolve and grade server-owned structure exercises."""

    def __init__(self, exercises: tuple[StructureExercise, ...] = DEFAULT_EXERCISES) -> None:
        self._exercises = {exercise.id: exercise for exercise in exercises}

    def list_exercises(self) -> dict[str, Any]:
        topics = tuple(
            {
                "id": domain,
                "title": DOMAIN_LABELS.get(domain, domain),
                "count": sum(
                    exercise.domain == domain for exercise in self._exercises.values()
                ),
            }
            for domain in sorted(DOMAIN_LABELS)
            if any(exercise.domain == domain for exercise in self._exercises.values())
        )
        return {
            "schemaVersion": SCHEMA_VERSION,
            "topics": topics,
            "exercises": [exercise.as_summary() for exercise in self._exercises.values()],
        }

    def exercise_public_context(self, exercise_id: str) -> dict[str, Any]:
        """Return public context for AI evaluation without answer material."""
        exercise = self._exercises.get(exercise_id)
        if exercise is None:
            raise StructureExerciseNotFoundError("structure exercise not found")
        return exercise.as_summary()

    def submit(
        self,
        exercise_id: str,
        answer: Any,
        level: int | None = None,
    ) -> dict[str, Any]:
        exercise = self._exercises.get(exercise_id)
        if exercise is None:
            raise StructureExerciseNotFoundError("structure exercise not found")
        if exercise.kind is StructureExerciseKind.STRUCTURE_SEQUENCE:
            if level is not None and exercise.levels:
                return _level_sequence_result(exercise, level, answer)
            return _sequence_result(exercise, answer)
        return _framework_result(exercise, answer)


__all__ = [
    "SCHEMA_VERSION",
    "StructureExercise",
    "StructureExerciseKind",
    "StructureLevel",
    "StructureExerciseNotFoundError",
    "StructureExerciseValidationError",
    "StructurePracticeService",
]
