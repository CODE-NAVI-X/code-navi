"""Static catalogue for structure/framework practice (contract §1).

The exercises in this module are deliberately rules-only and non-executable.
They teach how code is organised and how framework components fit together;
they never run a model, train a network or execute user code.  The service
archives these as ``code_fill`` items through ``POST /api/v1/practice/sets/generate``
and grades them with the deterministic rule path from §1.4.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StructureTopic:
    """One selectable practice topic."""

    id: str
    title: str
    description: str


@dataclass(frozen=True)
class StructureBlank:
    """One blank, including its server-only grading material."""

    blank_id: str
    answer: str
    alternate_answers: tuple[str, ...]
    hint: str
    step_no: int


@dataclass(frozen=True)
class StructureStep:
    """One ordered build step and why it is ordered that way."""

    step_no: int
    title: str
    reason: str
    sub_steps: tuple[str, ...]


@dataclass(frozen=True)
class StructureExercise:
    """One static code-fill exercise."""

    id: str
    topic_id: str
    title: str
    objective: str
    instruction: str
    code_masked: str
    reference_code: str
    blanks: tuple[StructureBlank, ...]
    steps: tuple[StructureStep, ...]


TOPICS: tuple[StructureTopic, ...] = (
    StructureTopic(
        id="cnn-image-recognition",
        title="CNN 图像识别",
        description="卷积、池化、全连接与分类头的结构顺序。",
    ),
    StructureTopic(
        id="rnn-sequence-modeling",
        title="RNN 序列建模",
        description="循环单元、时间步展开与序列输出的组织方式。",
    ),
    StructureTopic(
        id="transformer",
        title="Transformer",
        description="多头注意力、残差连接与前馈网络的模块组合。",
    ),
    StructureTopic(
        id="linear-model",
        title="线性模型",
        description="线性层、损失函数与参数更新之间的数据流。",
    ),
    StructureTopic(
        id="tree-model",
        title="树模型",
        description="特征分裂、叶子分数与集成结构的组织。",
    ),
    StructureTopic(
        id="optimization",
        title="优化算法",
        description="梯度、学习率与优化器状态更新的框架逻辑。",
    ),
    StructureTopic(
        id="clustering",
        title="聚类算法",
        description="距离计算、中心更新与收敛判断的结构。",
    ),
    StructureTopic(
        id="data-pipeline",
        title="数据处理流水线",
        description="Dataset、Dataloader、变换与批次组装的框架。",
    ),
)


EXERCISES: tuple[StructureExercise, ...] = (
    # ------------------------------------------------------------------
    # CNN 图像识别
    # ------------------------------------------------------------------
    StructureExercise(
        id="cnn-feature-extractor",
        topic_id="cnn-image-recognition",
        title="CNN 特征提取器结构",
        objective="理解卷积块、池化和展平进入全连接层的顺序。",
        instruction="补全特征提取器中缺少的核心逻辑；只做静态结构判断，不执行训练。",
        code_masked="""class CnnFeatureExtractor(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 32, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(______),
            nn.ReLU(),
            nn.Linear(64 * 8 * 8, 10),
        )

    def forward(self, x):
        x = self.features(______)
        return self.classifier(x)
""",
        reference_code="""class CnnFeatureExtractor(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 32, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(64 * 8 * 8),
            nn.ReLU(),
            nn.Linear(64 * 8 * 8, 10),
        )

    def forward(self, x):
        x = self.features(x)
        return self.classifier(x)
""",
        blanks=(
            StructureBlank(
                blank_id="cnn-flatten-dim",
                answer="64 * 8 * 8",
                alternate_answers=("8 * 8 * 64",),
                hint="经过两次 2x2 池化后，32x32 输入变为 8x8，通道数为 64。",
                step_no=1,
            ),
            StructureBlank(
                blank_id="cnn-forward-input",
                answer="x",
                alternate_answers=(),
                hint="特征提取模块接收原始输入张量。",
                step_no=2,
            ),
        ),
        steps=(
            StructureStep(
                step_no=1,
                title="构造特征提取器",
                reason="先定义卷积与池化层次，固定空间特征提取骨架。",
                sub_steps=("堆叠卷积与激活", "逐步降采样"),
            ),
            StructureStep(
                step_no=2,
                title="接入分类头",
                reason="特征图展平后才能进入全连接层完成分类。",
                sub_steps=("展平特征图", "线性映射到类别数"),
            ),
        ),
    ),
    StructureExercise(
        id="cnn-training-step",
        topic_id="cnn-image-recognition",
        title="CNN 单步训练结构",
        objective="理解前向、损失、反向传播和优化器更新的框架顺序。",
        instruction="补全训练步骤中的核心调用；此处只检查代码结构，不真正训练模型。",
        code_masked="""def train_step(model, images, labels, criterion, optimizer):
    optimizer.zero_grad()
    logits = model(______)
    loss = criterion(______)
    loss.backward()
    optimizer.______()
    return loss.item()
""",
        reference_code="""def train_step(model, images, labels, criterion, optimizer):
    optimizer.zero_grad()
    logits = model(images)
    loss = criterion(logits, labels)
    loss.backward()
    optimizer.step()
    return loss.item()
""",
        blanks=(
            StructureBlank(
                blank_id="cnn-forward",
                answer="images",
                alternate_answers=(),
                hint="前向计算接收当前批次图像。",
                step_no=1,
            ),
            StructureBlank(
                blank_id="cnn-loss",
                answer="logits, labels",
                alternate_answers=("labels, logits",),
                hint="损失函数需要模型输出和真实标签。",
                step_no=2,
            ),
            StructureBlank(
                blank_id="cnn-optimizer",
                answer="step",
                alternate_answers=(),
                hint="反向传播后需要执行一次参数更新。",
                step_no=3,
            ),
        ),
        steps=(
            StructureStep(
                step_no=1,
                title="清零梯度",
                reason="避免上一批次的梯度残留。",
                sub_steps=("zero_grad",),
            ),
            StructureStep(
                step_no=2,
                title="前向与损失",
                reason="先得到预测，再用标签计算可导损失。",
                sub_steps=("模型前向", "计算 loss"),
            ),
            StructureStep(
                step_no=3,
                title="反向与更新",
                reason="梯度回传后由优化器更新参数。",
                sub_steps=("backward", "optimizer.step"),
            ),
        ),
    ),
    # ------------------------------------------------------------------
    # RNN 序列建模
    # ------------------------------------------------------------------
    StructureExercise(
        id="rnn-loop-structure",
        topic_id="rnn-sequence-modeling",
        title="RNN 时间步展开",
        objective="理解循环单元在时间步上逐步更新隐藏状态的写法。",
        instruction="补全循环结构中的核心逻辑；只检查结构，不运行序列模型。",
        code_masked="""def run_rnn(cell, inputs, hidden):
    outputs = []
    for token in inputs:
        hidden = cell(______)
        outputs.append(______)
    return outputs, hidden
""",
        reference_code="""def run_rnn(cell, inputs, hidden):
    outputs = []
    for token in inputs:
        hidden = cell(token, hidden)
        outputs.append(hidden)
    return outputs, hidden
""",
        blanks=(
            StructureBlank(
                blank_id="rnn-step",
                answer="token, hidden",
                alternate_answers=("hidden, token",),
                hint="RNN 单元同时接收当前输入和上一步隐藏状态。",
                step_no=1,
            ),
            StructureBlank(
                blank_id="rnn-output",
                answer="hidden",
                alternate_answers=(),
                hint="每个时间步需要保存新的隐藏状态作为输出。",
                step_no=2,
            ),
        ),
        steps=(
            StructureStep(
                step_no=1,
                title="逐时间步调用单元",
                reason="RNN 的核心是按序列顺序传递隐藏状态。",
                sub_steps=("取当前 token", "传入上一 hidden"),
            ),
            StructureStep(
                step_no=2,
                title="收集并返回序列",
                reason="下游任务可能需要全部时间步输出，也可能只需要最终状态。",
                sub_steps=("追加输出", "返回最终 hidden"),
            ),
        ),
    ),
    StructureExercise(
        id="rnn-many-to-one",
        topic_id="rnn-sequence-modeling",
        title="RNN 多对一分类",
        objective="理解序列编码后取最后时间步输出进行分类的框架。",
        instruction="补全编码器与分类器衔接的核心逻辑。",
        code_masked="""class SequenceClassifier(nn.Module):
    def __init__(self, input_size, hidden_size, num_classes):
        super().__init__()
        self.rnn = nn.RNN(input_size, hidden_size, batch_first=True)
        self.fc = nn.Linear(hidden_size, num_classes)

    def forward(self, x):
        output, _ = self.rnn(______)
        last = output[:, ______, :]
        return self.fc(last)
""",
        reference_code="""class SequenceClassifier(nn.Module):
    def __init__(self, input_size, hidden_size, num_classes):
        super().__init__()
        self.rnn = nn.RNN(input_size, hidden_size, batch_first=True)
        self.fc = nn.Linear(hidden_size, num_classes)

    def forward(self, x):
        output, _ = self.rnn(x)
        last = output[:, -1, :]
        return self.fc(last)
""",
        blanks=(
            StructureBlank(
                blank_id="rnn-input",
                answer="x",
                alternate_answers=(),
                hint="序列编码器接收 batch-first 输入。",
                step_no=1,
            ),
            StructureBlank(
                blank_id="rnn-last-step",
                answer="-1",
                alternate_answers=("output.size(1) - 1",),
                hint="多对一分类通常取最后一个时间步输出。",
                step_no=2,
            ),
        ),
        steps=(
            StructureStep(
                step_no=1,
                title="编码整条序列",
                reason="RNN 依次处理所有 token，输出每个时间步的隐藏状态。",
                sub_steps=("输入序列", "得到 output"),
            ),
            StructureStep(
                step_no=2,
                title="取出末步并分类",
                reason="多对一任务只关心读完整个序列后的最终表示。",
                sub_steps=("取最后时间步", "线性分类"),
            ),
        ),
    ),
    # ------------------------------------------------------------------
    # Transformer
    # ------------------------------------------------------------------
    StructureExercise(
        id="transformer-attention",
        topic_id="transformer",
        title="Transformer 自注意力结构",
        objective="理解 Q、K、V 与缩放点积注意力的框架组合。",
        instruction="补全注意力计算中的核心表达式；仅静态核对结构。",
        code_masked="""def scaled_dot_product_attention(q, k, v):
    d_k = q.size(-1)
    scores = torch.matmul(q, k.transpose(-2, -1)) / ______
    attention = torch.softmax(______, dim=-1)
    return torch.matmul(______, v)
""",
        reference_code="""def scaled_dot_product_attention(q, k, v):
    d_k = q.size(-1)
    scores = torch.matmul(q, k.transpose(-2, -1)) / math.sqrt(d_k)
    attention = torch.softmax(scores, dim=-1)
    return torch.matmul(attention, v)
""",
        blanks=(
            StructureBlank(
                blank_id="attn-scale",
                answer="math.sqrt(d_k)",
                alternate_answers=("d_k ** 0.5",),
                hint="点积结果需要按维度平方根缩放，避免 softmax 梯度过小。",
                step_no=1,
            ),
            StructureBlank(
                blank_id="attn-softmax",
                answer="scores",
                alternate_answers=(),
                hint="缩放后的分数要沿最后一个维度归一化。",
                step_no=2,
            ),
            StructureBlank(
                blank_id="attn-value",
                answer="attention",
                alternate_answers=(),
                hint="加权平均需要将注意力权重作用到 value。",
                step_no=3,
            ),
        ),
        steps=(
            StructureStep(
                step_no=1,
                title="计算缩放分数",
                reason="点积反映 query 与 key 的相似度，缩放保证数值稳定。",
                sub_steps=("矩阵乘", "除以 sqrt(d_k)"),
            ),
            StructureStep(
                step_no=2,
                title="归一化为注意力权重",
                reason="softmax 让权重非负且和为 1。",
                sub_steps=("softmax",),
            ),
            StructureStep(
                step_no=3,
                title="聚合 value",
                reason="用注意力权重加权 value 得到上下文表示。",
                sub_steps=("加权求和",),
            ),
        ),
    ),
    StructureExercise(
        id="transformer-residual",
        topic_id="transformer",
        title="Transformer 残差与归一化",
        objective="理解子层残差连接和 LayerNorm 的框架顺序。",
        instruction="补全残差连接结构中的核心调用。",
        code_masked="""class TransformerBlock(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.norm1 = nn.LayerNorm(dim)
        self.attn = MultiHeadAttention(dim)
        self.norm2 = nn.LayerNorm(dim)
        self.mlp = Mlp(dim)

    def forward(self, x):
        x = x + self.attn(self.norm1(______))
        x = x + self.mlp(self.norm2(______))
        return x
""",
        reference_code="""class TransformerBlock(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.norm1 = nn.LayerNorm(dim)
        self.attn = MultiHeadAttention(dim)
        self.norm2 = nn.LayerNorm(dim)
        self.mlp = Mlp(dim)

    def forward(self, x):
        x = x + self.attn(self.norm1(x))
        x = x + self.mlp(self.norm2(x))
        return x
""",
        blanks=(
            StructureBlank(
                blank_id="residual-norm1",
                answer="x",
                alternate_answers=(),
                hint="每个子层先归一化，再执行注意力。",
                step_no=1,
            ),
            StructureBlank(
                blank_id="residual-norm2",
                answer="x",
                alternate_answers=(),
                hint="第二个残差块同样先归一化当前输入。",
                step_no=2,
            ),
        ),
        steps=(
            StructureStep(
                step_no=1,
                title="注意力子层加残差",
                reason="LayerNorm 后接注意力和残差，稳定深层网络训练。",
                sub_steps=("norm1", "attn", "残差相加"),
            ),
            StructureStep(
                step_no=2,
                title="前馈子层加残差",
                reason="MLP 增强表达能力，残差保留原始信号。",
                sub_steps=("norm2", "mlp", "残差相加"),
            ),
        ),
    ),
    # ------------------------------------------------------------------
    # 线性模型
    # ------------------------------------------------------------------
    StructureExercise(
        id="linear-forward",
        topic_id="linear-model",
        title="线性模型前向结构",
        objective="理解特征与权重相乘再加偏置的框架。",
        instruction="补全线性变换的核心表达式。",
        code_masked="""class LinearModel(nn.Module):
    def __init__(self, in_features, out_features):
        super().__init__()
        self.weight = nn.Parameter(torch.randn(out_features, in_features))
        self.bias = nn.Parameter(torch.randn(out_features))

    def forward(self, x):
        return x @ self.weight.______ + self.bias
""",
        reference_code="""class LinearModel(nn.Module):
    def __init__(self, in_features, out_features):
        super().__init__()
        self.weight = nn.Parameter(torch.randn(out_features, in_features))
        self.bias = nn.Parameter(torch.randn(out_features))

    def forward(self, x):
        return x @ self.weight.transpose(0, 1) + self.bias
""",
        blanks=(
            StructureBlank(
                blank_id="linear-transpose",
                answer="transpose(0, 1)",
                alternate_answers=("t()", "T"),
                hint="权重形状为 out x in，需要转置后才能与输入做矩阵乘。",
                step_no=1,
            ),
        ),
        steps=(
            StructureStep(
                step_no=1,
                title="矩阵乘并加偏置",
                reason="线性层本质是 y = xW^T + b。",
                sub_steps=("权重转置", "加偏置"),
            ),
        ),
    ),
    StructureExercise(
        id="linear-training-loop",
        topic_id="linear-model",
        title="线性模型训练闭环",
        objective="理解损失、梯度清零和参数更新的顺序。",
        instruction="补全训练循环中的核心步骤；不执行模型训练。",
        code_masked="""def fit_linear(model, loader, optimizer, criterion):
    for x, y in loader:
        pred = model(______)
        loss = criterion(______)
        optimizer.zero_grad()
        loss.backward()
        optimizer.______()
""",
        reference_code="""def fit_linear(model, loader, optimizer, criterion):
    for x, y in loader:
        pred = model(x)
        loss = criterion(pred, y)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
""",
        blanks=(
            StructureBlank(
                blank_id="linear-forward",
                answer="x",
                alternate_answers=(),
                hint="模型需要接收当前批次特征。",
                step_no=1,
            ),
            StructureBlank(
                blank_id="linear-loss",
                answer="pred, y",
                alternate_answers=("y, pred",),
                hint="损失函数需要预测值与标签。",
                step_no=2,
            ),
            StructureBlank(
                blank_id="linear-step",
                answer="step",
                alternate_answers=(),
                hint="完成反向传播后更新参数。",
                step_no=3,
            ),
        ),
        steps=(
            StructureStep(
                step_no=1,
                title="前向预测",
                reason="先获得模型输出。",
                sub_steps=("model(x)",),
            ),
            StructureStep(
                step_no=2,
                title="计算损失",
                reason="比较预测和标签。",
                sub_steps=("criterion",),
            ),
            StructureStep(
                step_no=3,
                title="反向与更新",
                reason="梯度回传后更新模型参数。",
                sub_steps=("backward", "step"),
            ),
        ),
    ),
    # ------------------------------------------------------------------
    # 树模型
    # ------------------------------------------------------------------
    StructureExercise(
        id="tree-split-structure",
        topic_id="tree-model",
        title="决策树分裂结构",
        objective="理解节点按特征阈值分裂的框架。",
        instruction="补全树节点分裂条件的核心表达式。",
        code_masked="""class TreeNode:
    def predict_one(self, x):
        if self.is_leaf:
            return self.value
        if x[self.feature] <= self.______:
            return self.left.predict_one(x)
        return self.right.predict_one(______)
""",
        reference_code="""class TreeNode:
    def predict_one(self, x):
        if self.is_leaf:
            return self.value
        if x[self.feature] <= self.threshold:
            return self.left.predict_one(x)
        return self.right.predict_one(x)
""",
        blanks=(
            StructureBlank(
                blank_id="tree-threshold",
                answer="threshold",
                alternate_answers=(),
                hint="节点根据当前特征与分裂阈值比较。",
                step_no=1,
            ),
            StructureBlank(
                blank_id="tree-right",
                answer="x",
                alternate_answers=(),
                hint="右子树同样接收同一条样本。",
                step_no=2,
            ),
        ),
        steps=(
            StructureStep(
                step_no=1,
                title="判断是否叶子",
                reason="叶子节点直接返回预测值。",
                sub_steps=("is_leaf",),
            ),
            StructureStep(
                step_no=2,
                title="按阈值分支",
                reason="样本根据特征值进入左或右子树。",
                sub_steps=("比较阈值", "递归预测"),
            ),
        ),
    ),
    StructureExercise(
        id="tree-ensemble-structure",
        topic_id="tree-model",
        title="树集成结构",
        objective="理解多棵树共同打分并求和的框架。",
        instruction="补全集成预测的核心逻辑。",
        code_masked="""class TreeEnsemble:
    def __init__(self, trees, learning_rate):
        self.trees = trees
        self.learning_rate = learning_rate

    def predict(self, x):
        score = 0.0
        for tree in self.trees:
            score += self.learning_rate * tree.______
        return ______
""",
        reference_code="""class TreeEnsemble:
    def __init__(self, trees, learning_rate):
        self.trees = trees
        self.learning_rate = learning_rate

    def predict(self, x):
        score = 0.0
        for tree in self.trees:
            score += self.learning_rate * tree.predict(x)
        return score
""",
        blanks=(
            StructureBlank(
                blank_id="ensemble-tree-score",
                answer="predict(x)",
                alternate_answers=("predict_one(x)",),
                hint="每棵树输出一个叶子分数。",
                step_no=1,
            ),
            StructureBlank(
                blank_id="ensemble-return",
                answer="score",
                alternate_answers=(),
                hint="集成预测是加权分数累加后的结果。",
                step_no=2,
            ),
        ),
        steps=(
            StructureStep(
                step_no=1,
                title="逐树累加",
                reason="梯度提升树通过多棵树逐步修正残差。",
                sub_steps=("遍历 trees", "乘学习率"),
            ),
            StructureStep(
                step_no=2,
                title="返回总分数",
                reason="所有树的加权和构成最终输出。",
                sub_steps=("求和",),
            ),
        ),
    ),
    # ------------------------------------------------------------------
    # 优化算法
    # ------------------------------------------------------------------
    StructureExercise(
        id="optimizer-sgd",
        topic_id="optimization",
        title="SGD 参数更新结构",
        objective="理解梯度下降中参数沿负梯度方向更新的框架。",
        instruction="补全参数更新公式的核心表达式。",
        code_masked="""def sgd_step(param, grad, lr):
    param.data = param.data - lr * ______
""",
        reference_code="""def sgd_step(param, grad, lr):
    param.data = param.data - lr * grad
""",
        blanks=(
            StructureBlank(
                blank_id="sgd-grad",
                answer="grad",
                alternate_answers=(),
                hint="参数应沿负梯度方向移动。",
                step_no=1,
            ),
        ),
        steps=(
            StructureStep(
                step_no=1,
                title="更新参数",
                reason="梯度下降以学习率缩放梯度。",
                sub_steps=("lr * grad", "param.data -"),
            ),
        ),
    ),
    StructureExercise(
        id="optimizer-adam",
        topic_id="optimization",
        title="Adam 一阶二阶矩结构",
        objective="理解 Adam 维护一阶、二阶矩并修正偏差的框架。",
        instruction="补全 Adam 更新中的核心表达式。",
        code_masked="""def adam_step(param, grad, m, v, t, lr, beta1, beta2, eps):
    m = beta1 * m + (1 - beta1) * ______
    v = beta2 * v + (1 - beta2) * grad * grad
    m_hat = m / (1 - beta1 ** t)
    v_hat = v / (1 - beta2 ** t)
    param.data = param.data - lr * m_hat / (v_hat.______ + eps)
""",
        reference_code="""def adam_step(param, grad, m, v, t, lr, beta1, beta2, eps):
    m = beta1 * m + (1 - beta1) * grad
    v = beta2 * v + (1 - beta2) * grad * grad
    m_hat = m / (1 - beta1 ** t)
    v_hat = v / (1 - beta2 ** t)
    param.data = param.data - lr * m_hat / (v_hat.sqrt() + eps)
""",
        blanks=(
            StructureBlank(
                blank_id="adam-m",
                answer="grad",
                alternate_answers=(),
                hint="一阶矩是梯度的指数移动平均。",
                step_no=1,
            ),
            StructureBlank(
                blank_id="adam-v",
                answer="sqrt",
                alternate_answers=("** 0.5",),
                hint="更新时需要对二阶矩取平方根。",
                step_no=2,
            ),
        ),
        steps=(
            StructureStep(
                step_no=1,
                title="更新一阶与二阶矩",
                reason="Adam 结合动量与自适应学习率。",
                sub_steps=("更新 m", "更新 v"),
            ),
            StructureStep(
                step_no=2,
                title="偏差修正与参数更新",
                reason="修正早期矩估计偏差，再用自适应步长更新。",
                sub_steps=("m_hat", "v_hat", "参数更新"),
            ),
        ),
    ),
    # ------------------------------------------------------------------
    # 聚类算法
    # ------------------------------------------------------------------
    StructureExercise(
        id="clustering-assign",
        topic_id="clustering",
        title="K-Means 样本分配结构",
        objective="理解每个样本被分配给最近中心的结构。",
        instruction="补全距离计算和最近中心选择的核心逻辑。",
        code_masked="""def assign_clusters(data, centers):
    labels = []
    for point in data:
        distances = [torch.norm(point - center) for center in ______]
        labels.append(______)
    return labels
""",
        reference_code="""def assign_clusters(data, centers):
    labels = []
    for point in data:
        distances = [torch.norm(point - center) for center in centers]
        labels.append(distances.index(min(distances)))
    return labels
""",
        blanks=(
            StructureBlank(
                blank_id="cluster-centers",
                answer="centers",
                alternate_answers=(),
                hint="距离需要与所有聚类中心计算。",
                step_no=1,
            ),
            StructureBlank(
                blank_id="cluster-nearest",
                answer="distances.index(min(distances))",
                alternate_answers=("min(range(len(distances)), key=distances.__getitem__)",),
                hint="选择距离最小的中心索引作为标签。",
                step_no=2,
            ),
        ),
        steps=(
            StructureStep(
                step_no=1,
                title="计算到各中心距离",
                reason="最近邻分配依赖样本与所有中心的距离。",
                sub_steps=("遍历 centers", "计算 norm"),
            ),
            StructureStep(
                step_no=2,
                title="选择最近中心",
                reason="样本标签是距离最小中心的索引。",
                sub_steps=("取 min", "记录索引"),
            ),
        ),
    ),
    StructureExercise(
        id="clustering-update",
        topic_id="clustering",
        title="K-Means 中心更新结构",
        objective="理解按簇内样本均值更新中心的结构。",
        instruction="补全中心更新的核心表达式。",
        code_masked="""def update_centers(data, labels, k):
    centers = []
    for cluster in range(k):
        members = [point for point, label in zip(data, labels) if label == ______]
        centers.append(sum(members) / len(______))
    return centers
""",
        reference_code="""def update_centers(data, labels, k):
    centers = []
    for cluster in range(k):
        members = [point for point, label in zip(data, labels) if label == cluster]
        centers.append(sum(members) / len(members))
    return centers
""",
        blanks=(
            StructureBlank(
                blank_id="cluster-filter",
                answer="cluster",
                alternate_answers=(),
                hint="筛选属于当前簇的样本。",
                step_no=1,
            ),
            StructureBlank(
                blank_id="cluster-mean",
                answer="members",
                alternate_answers=(),
                hint="新中心是成员样本的平均值。",
                step_no=2,
            ),
        ),
        steps=(
            StructureStep(
                step_no=1,
                title="筛选簇成员",
                reason="每个中心只由属于该簇的样本更新。",
                sub_steps=("zip data/labels", "过滤当前簇"),
            ),
            StructureStep(
                step_no=2,
                title="计算均值",
                reason="均值是当前簇的代表点。",
                sub_steps=("求和", "除以数量"),
            ),
        ),
    ),
    # ------------------------------------------------------------------
    # 数据处理流水线
    # ------------------------------------------------------------------
    StructureExercise(
        id="dataset-class",
        topic_id="data-pipeline",
        title="PyTorch Dataset 结构",
        objective="理解 Dataset 需要实现 __len__ 与 __getitem__ 的框架。",
        instruction="补全数据集中两个核心方法的逻辑。",
        code_masked="""class ExampleDataset(Dataset):
    def __init__(self, samples):
        self.samples = samples

    def __len__(self):
        return len(self.______)

    def __getitem__(self, index):
        return self.samples[______]
""",
        reference_code="""class ExampleDataset(Dataset):
    def __init__(self, samples):
        self.samples = samples

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, index):
        return self.samples[index]
""",
        blanks=(
            StructureBlank(
                blank_id="dataset-len",
                answer="samples",
                alternate_answers=(),
                hint="数据集长度应返回样本数量。",
                step_no=1,
            ),
            StructureBlank(
                blank_id="dataset-getitem",
                answer="index",
                alternate_answers=(),
                hint="按索引返回一条样本。",
                step_no=2,
            ),
        ),
        steps=(
            StructureStep(
                step_no=1,
                title="实现长度方法",
                reason="DataLoader 需要知道总样本数。",
                sub_steps=("len(self.samples)",),
            ),
            StructureStep(
                step_no=2,
                title="实现索引方法",
                reason="DataLoader 通过索引批量取数据。",
                sub_steps=("self.samples[index]",),
            ),
        ),
    ),
    StructureExercise(
        id="dataloader-pipeline",
        topic_id="data-pipeline",
        title="DataLoader 流水线结构",
        objective="理解 Dataset 经过 DataLoader 组装 batch 的框架。",
        instruction="补全数据加载流水线中的核心参数。",
        code_masked="""dataset = ExampleDataset(samples)
loader = DataLoader(
    dataset,
    batch_size=______,
    shuffle=True,
    collate_fn=______,
)
""",
        reference_code="""dataset = ExampleDataset(samples)
loader = DataLoader(
    dataset,
    batch_size=32,
    shuffle=True,
    collate_fn=default_collate,
)
""",
        blanks=(
            StructureBlank(
                blank_id="loader-batch",
                answer="32",
                alternate_answers=("16", "64"),
                hint="batch_size 需要是正整数；这里约定一个常见批次大小。",
                step_no=1,
            ),
            StructureBlank(
                blank_id="loader-collate",
                answer="default_collate",
                alternate_answers=("None",),
                hint="默认使用 default_collate 将样本组装成张量批次。",
                step_no=2,
            ),
        ),
        steps=(
            StructureStep(
                step_no=1,
                title="设置批次大小",
                reason="DataLoader 按 batch_size 切分数据。",
                sub_steps=("batch_size=32",),
            ),
            StructureStep(
                step_no=2,
                title="设置组装函数",
                reason="collate_fn 决定如何把单条样本合并成 batch。",
                sub_steps=("default_collate",),
            ),
        ),
    ),
)


def topic_by_id(topic_id: str) -> StructureTopic | None:
    """Return the topic with ``topic_id`` or ``None``."""
    return next((topic for topic in TOPICS if topic.id == topic_id), None)


def exercises_for_topic(topic_id: str) -> list[StructureExercise]:
    """Return exercises in catalogue order for one topic."""
    return [exercise for exercise in EXERCISES if exercise.topic_id == topic_id]


def exercise_by_id(exercise_id: str) -> StructureExercise | None:
    """Return one catalogue exercise by id."""
    return next((exercise for exercise in EXERCISES if exercise.id == exercise_id), None)


__all__ = [
    "EXERCISES",
    "TOPICS",
    "StructureBlank",
    "StructureExercise",
    "StructureStep",
    "StructureTopic",
    "exercise_by_id",
    "exercises_for_topic",
    "topic_by_id",
]
