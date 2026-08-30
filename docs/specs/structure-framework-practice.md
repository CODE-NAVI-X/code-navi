# Structure and Framework Practice

结构与框架练习

| 状态 | 关联决策 | 当前计划 |
| --- | --- | --- |
| 原型进行中 | 待补充 | [结构与框架练习实施计划](../plans/structure-framework-practice-rollout.md) |

## 1. 产品目标

Practice 继续保留面向语言基础的代码运行与判题能力，同时增加不执行真实模型代码的“结构与框架练习”。目标用户是已经掌握基础语法的学生；他们需要理解代码结构、框架用法和算法流程，而不是重新学习语言语法。

本阶段不真实运行 CNN、不安装深度学习依赖，也不把静态练习结果描述为模型训练或推理成功。

## 2. 范围与边界

第一版支持两类服务端静态练习题，并按机器学习主题组织，学生可以选择 CNN、RNN、Transformer、线性模型、树模型、优化算法或聚类算法后再进入对应题目：

| 类型 | 用户行为 | 判题方式 |
| --- | --- | --- |
| `structure_sequence` | 按正确顺序排列模块或步骤 | 顺序是否匹配 |
| `framework_fill` | 补全框架代码中的关键片段 | 关键 token 是否齐备 |

示例内容覆盖 CNN、RNN/LSTM、Transformer、逻辑回归、决策树、梯度下降和 K-Means 等主题，避免练习内容被固定为单一 CNN 示例。

当前不接入 Piston，不新增语言，不访问真实数据库，不持久化用户答案。

## 3. 可验收行为

1. `GET /api/v1/compiler/structure-exercises` 返回不含答案和判题 token 的公开练习摘要。
2. `POST /api/v1/compiler/structure-exercises/{exercise_id}/submit` 用确定性规则判题，返回 verdict、score、feedback 和 explanation。
3. 正确答案返回 `accepted` 和 100 分。
4. 错误顺序或缺失 token 返回 `wrong_answer`，并给出位置或 token 级反馈。
5. 未知题目返回 404；缺少答案或答案类型错误返回 400。
6. 静态练习请求不调用 Piston，也不创建 PracticeOutcome、Activity 或学习记录。

## 4. 当前实现与限制

实现位于 `src/code_navi/online_compiler/structure_practice.py`，路由挂在现有 Compiler router 下。Practice 主页面不再使用“基础运行 / 结构与框架”双入口，而是直接展示统一练习题列表；列表提供题型分类，学生选择“结构排序”或“代码挖空”后进入具体练习页。题目当前为进程内存内置目录，不持久化，也不进入 Workspace 时间线。

结构排序支持同一道题内多级展开，每一级独立提交、独立判分，学生通过当前级别后可选择进入下一级。代码填空提供更完整的代码骨架，而非只有单行占位。

Practice 页面通过右上角用户菜单维护“语言基础”偏好；首次进入会询问一次。有基础时隐藏基础语法题与“语法编译”分类，无基础时优先展示基础语法题。

框架填空的规则比较目前是精确 token 匹配。它可以识别关键命名参数，但不解析 Python AST，也不判断代码语义；这不是代码执行或正确性证明。

## 5. 不变量

1. 公开 API 不返回 `answerSequence`、`requiredTokens` 或完整标准答案。
2. 判题只能来自服务端确定性规则，不依赖在线 Provider。
3. 静态练习不能调用 Piston，不能绕过代码执行资源限制。
4. 后续接入 PracticeOutcome 时，仍需遵守不保存敏感答案内容的安全边界。
