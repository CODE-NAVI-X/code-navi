"""Deterministic, semantically related exercises for Mock practice contexts.

These fixtures keep the offline demo honest: a contextual request either maps
to a small, explicit topic family or is rejected instead of receiving an
unrelated placeholder exercise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MockContextFixture:
    """One offline exercise family keyed by a supported knowledge-point family."""

    key: str
    label: str
    aliases: tuple[str, ...]
    concept: dict[str, Any]
    code_fill: dict[str, Any]
    coding_problem: dict[str, Any]


_CNN = MockContextFixture(
    key="cnn",
    label="CNN",
    aliases=(
        "cnn",
        "卷积",
        "卷积神经网络",
        "池化",
        "pooling",
        "feature map",
        "特征图",
        "kernel",
        "卷积核",
    ),
    concept={
        "question": "在 CNN 中，卷积核滑过输入图像后首先得到什么，池化通常起什么作用？",
        "options": [
            {
                "label": "卷积产生 feature map（特征图），池化可降低空间尺寸并保留显著响应",
                "value": "A",
            },
            {"label": "卷积直接把每个像素转换成排序后的整数", "value": "B"},
            {"label": "池化负责把标签反向传播到数据集文件", "value": "C"},
            {"label": "卷积核只用于调整优化器的学习率", "value": "D"},
        ],
        "answer": ["A"],
        "analysis": (
            "卷积核在局部感受野上提取模式并形成特征图；池化通常做空间降采样，"
            "帮助压缩特征图并保留较强响应。"
        ),
        "points": 10,
    },
    code_fill={
        "title": "（Mock fixture）CNN 卷积核与特征图流水线",
        "reference_code": (
            "def cnn_block(image, kernel):\n"
            "    feature_map = convolve(image, kernel)\n"
            "    activated = relu(feature_map)\n"
            "    pooled = max_pool(activated)\n"
            "    return pooled\n"
        ),
        "code_masked": (
            "def cnn_block(image, kernel):\n"
            "    feature_map = ______\n"
            "    activated = relu(feature_map)\n"
            "    pooled = ______\n"
            "    return pooled\n"
        ),
        "blanks": [
            {
                "blank_id": "cnn-convolution",
                "answer": "convolve(image, kernel)",
                "alternate_answers": ["convolve(kernel, image)"],
                "hint": "用卷积核在输入图像上滑动，得到 feature map。",
                "step_no": 1,
            },
            {
                "blank_id": "cnn-pooling",
                "answer": "max_pool(activated)",
                "alternate_answers": ["max_pool(feature_map)"],
                "hint": "对激活后的特征图做池化，压缩空间尺寸。",
                "step_no": 2,
            },
        ],
        "steps": [
            {
                "step_no": 1,
                "title": "CNN 卷积生成特征图",
                "reason": "卷积核先从局部感受野提取图像模式，输出 feature map。",
                "sub_steps": ["读取 image 与 kernel", "执行卷积", "保留特征图"],
            },
            {
                "step_no": 2,
                "title": "池化压缩特征图",
                "reason": "池化降低空间分辨率，同时保留较强的局部响应。",
                "sub_steps": ["应用激活函数", "执行 max pooling", "返回池化结果"],
            },
        ],
    },
    coding_problem={
        "title": "（Mock fixture）CNN：用卷积核生成特征图",
        "description": (
            "给定一个单通道图像矩阵和一个卷积核，按步长 1 计算 valid convolution，"
            "输出 CNN 第一层得到的 feature map。"
        ),
        "starterCode": (
            "def valid_convolution(\n"
            "    image: list[list[int]], kernel: list[list[int]]\n"
            ") -> list[list[int]]:\n"
            "    # TODO: slide the kernel over image and build the feature map\n"
            "    pass\n"
        ),
        "inputHint": "输入图像矩阵与卷积核矩阵，卷积核不大于图像。",
        "outputHint": "输出 valid convolution 得到的二维 feature map。",
        "sampleTests": [
            {
                "input": "image=[[1,2,3],[4,5,6],[7,8,9]], kernel=[[1,0],[0,1]]",
                "output": "[[6,8],[12,14]]",
            }
        ],
    },
)


_RESNET = MockContextFixture(
    key="resnet",
    label="ResNet BasicBlock",
    aliases=(
        "resnet",
        "residual",
        "残差",
        "basicblock",
        "basic block",
        "残差块",
        "残差连接",
        "shortcut",
    ),
    concept={
        "question": (
            "ResNet 的 BasicBlock 在 forward 中把 residual/shortcut 加回主分支，"
            "核心目的是什么？"
        ),
        "options": [
            {
                "label": "形成残差连接，让块学习相对输入的增量并改善深层网络的梯度传播",
                "value": "A",
            },
            {"label": "把卷积层替换成数据集文件读取操作", "value": "B"},
            {"label": "保证每个 batch 的标签都按字母序排列", "value": "C"},
            {"label": "只为了把 feature map 转成字符串", "value": "D"},
        ],
        "answer": ["A"],
        "analysis": (
            "BasicBlock 保留输入作为 shortcut/residual，并与卷积主分支相加。"
            "这种 residual connection 让网络更容易学习增量，也有利于梯度传播。"
        ),
        "points": 10,
    },
    code_fill={
        "title": "（Mock fixture）ResNet BasicBlock 的 residual forward",
        "reference_code": (
            "class BasicBlock:\n"
            "    def forward(self, x):\n"
            "        residual = x\n"
            "        out = self.conv1(x)\n"
            "        out = self.relu(out)\n"
            "        out = self.conv2(out)\n"
            "        out = out + residual\n"
            "        return self.relu(out)\n"
        ),
        "code_masked": (
            "class BasicBlock:\n"
            "    def forward(self, x):\n"
            "        residual = x\n"
            "        out = ______\n"
            "        out = self.relu(out)\n"
            "        out = self.conv2(out)\n"
            "        out = ______\n"
            "        return self.relu(out)\n"
        ),
        "blanks": [
            {
                "blank_id": "resnet-conv1",
                "answer": "self.conv1(x)",
                "alternate_answers": [],
                "hint": "BasicBlock 的主分支先对输入执行第一层卷积。",
                "step_no": 1,
            },
            {
                "blank_id": "resnet-residual-add",
                "answer": "out + residual",
                "alternate_answers": ["residual + out"],
                "hint": "将卷积主分支与 shortcut 保存的 residual 相加。",
                "step_no": 2,
            },
        ],
        "steps": [
            {
                "step_no": 1,
                "title": "ResNet BasicBlock 主分支",
                "reason": "先沿 forward 路径计算卷积变换，得到待修正的主分支输出。",
                "sub_steps": ["保存 residual", "执行 conv1", "继续 conv2"],
            },
            {
                "step_no": 2,
                "title": "合并 residual connection",
                "reason": "shortcut 与主分支相加，构成 ResNet 的残差连接。",
                "sub_steps": ["取出 residual", "执行 out + residual", "再激活"],
            },
        ],
    },
    coding_problem={
        "title": "（Mock fixture）ResNet BasicBlock：实现 shortcut 相加",
        "description": (
            "实现一个简化的 ResNet BasicBlock forward：先计算主分支变换，"
            "再把 residual shortcut 加回输出，最后应用激活函数。"
        ),
        "starterCode": (
            "def basic_block_forward(x, conv1, conv2, relu):\n"
            "    residual = x\n"
            "    out = conv1(x)\n"
            "    out = conv2(out)\n"
            "    # TODO: residual connection and activation\n"
            "    return out\n"
        ),
        "inputHint": "输入张量 x，以及两个卷积变换和激活函数。",
        "outputHint": "返回加入 residual shortcut 后的激活结果。",
        "sampleTests": [
            {
                "input": "x=2, conv1=lambda v: v+1, conv2=lambda v: v*2",
                "output": "8",
            }
        ],
    },
)


_BINARY_TREE = MockContextFixture(
    key="binary_tree_traversal",
    label="二叉树遍历",
    aliases=(
        "二叉树",
        "二叉树遍历",
        "binary tree",
        "tree traversal",
        "先序",
        "前序",
        "中序",
        "后序",
        "preorder",
        "inorder",
        "postorder",
    ),
    concept={
        "question": "二叉树的 inorder（中序）遍历使用递归时，访问顺序是什么？",
        "options": [
            {"label": "先左子树，再根节点，最后右子树", "value": "A"},
            {"label": "先根节点，再左子树，最后右子树（这是 preorder）", "value": "B"},
            {"label": "只访问叶子节点，不递归左右子树", "value": "C"},
            {"label": "先右子树，再根节点，最后左子树", "value": "D"},
        ],
        "answer": ["A"],
        "analysis": (
            "中序遍历的递归结构是 left → root → right：先递归左子树，"
            "记录当前节点，再递归右子树；preorder 则是 root → left → right。"
        ),
        "points": 10,
    },
    code_fill={
        "title": "（Mock fixture）二叉树遍历：递归实现 inorder",
        "reference_code": (
            "def inorder(root):\n"
            "    result = []\n"
            "\n"
            "    def traverse(node):\n"
            "        if node is None:\n"
            "            return\n"
            "        traverse(node.left)\n"
            "        result.append(node.value)\n"
            "        traverse(node.right)\n"
            "\n"
            "    traverse(root)\n"
            "    return result\n"
        ),
        "code_masked": (
            "def inorder(root):\n"
            "    result = []\n"
            "\n"
            "    def traverse(node):\n"
            "        if node is None:\n"
            "            return\n"
            "        ______\n"
            "        result.append(node.value)\n"
            "        ______\n"
            "\n"
            "    traverse(root)\n"
            "    return result\n"
        ),
        "blanks": [
            {
                "blank_id": "tree-left-recursion",
                "answer": "traverse(node.left)",
                "alternate_answers": [],
                "hint": "中序遍历先递归访问当前节点的左子树。",
                "step_no": 1,
            },
            {
                "blank_id": "tree-right-recursion",
                "answer": "traverse(node.right)",
                "alternate_answers": [],
                "hint": "记录根节点后，再递归访问右子树。",
                "step_no": 2,
            },
        ],
        "steps": [
            {
                "step_no": 1,
                "title": "二叉树递归基线",
                "reason": "空节点必须停止递归，避免继续访问不存在的子树。",
                "sub_steps": ["判断 node is None", "递归返回"],
            },
            {
                "step_no": 2,
                "title": "inorder 的左根右顺序",
                "reason": "中序遍历固定为左子树、根节点、右子树，区别于 preorder。",
                "sub_steps": ["递归左子树", "记录当前值", "递归右子树"],
            },
        ],
    },
    coding_problem={
        "title": "（Mock fixture）二叉树遍历：输出 inorder 序列",
        "description": (
            "给定二叉树根节点，使用递归完成 inorder（左、根、右）遍历，"
            "返回所有节点值组成的序列。"
        ),
        "starterCode": (
            "def inorder(root):\n"
            "    result = []\n"
            "    # TODO: recurse left, visit root, then recurse right\n"
            "    return result\n"
        ),
        "inputHint": "输入二叉树根节点；空节点用 None 表示。",
        "outputHint": "返回 inorder 遍历得到的节点值列表。",
        "sampleTests": [{"input": "root=[2,1,3]", "output": "[1,2,3]"}],
    },
)


MOCK_CONTEXT_FIXTURES = (_CNN, _RESNET, _BINARY_TREE)


def _normalized(value: str) -> str:
    return " ".join(value.casefold().replace("_", " ").replace("-", " ").split())


def _fixture_for_name(name: str) -> MockContextFixture | None:
    normalized = _normalized(name)
    if not normalized:
        return None
    for fixture in MOCK_CONTEXT_FIXTURES:
        if any(alias in normalized for alias in fixture.aliases):
            return fixture
    return None


def resolve_mock_context_focus(
    knowledge_points: list[str],
) -> tuple[str, MockContextFixture] | None:
    """Choose the first supported point as the deterministic Mock focus.

    Learning supplies points in priority order.  A Mock fixture deliberately
    covers one point per set, so unsupported or lower-priority points do not
    make an otherwise supported request fail or get mislabeled.
    """
    for name in knowledge_points:
        fixture = _fixture_for_name(name)
        if fixture is not None:
            return name, fixture
    return None


def resolve_mock_context_fixture(knowledge_points: list[str]) -> MockContextFixture | None:
    """Return the fixture for the first supported knowledge point, if any."""
    resolved = resolve_mock_context_focus(knowledge_points)
    return resolved[1] if resolved is not None else None


__all__ = [
    "MOCK_CONTEXT_FIXTURES",
    "MockContextFixture",
    "resolve_mock_context_fixture",
    "resolve_mock_context_focus",
]
