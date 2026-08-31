# 结构与框架练习实施计划

| 状态 | 关联 Spec |
| --- | --- |
| 当前 Epic | [Structure and Framework Practice](../specs/structure-framework-practice.md) |

## 1. 目标与完成条件

在现有 Practice 中增加不执行真实代码的静态练习模式。第一版先跑通后端最小闭环，证明题目列表、规则判题和错误反馈可用，再向前端扩展。

## 2. 实施顺序

| 切片 | 范围 | 状态 |
| --- | --- | --- |
| 后端静态练习服务 | 模型、内置 CNN/PyTorch 题目、规则判题 | 原型完成 |
| Compiler API | 练习列表与提交接口，不接入 Piston | 原型完成 |
| 后端测试 | 正确/错误/缺失/未知题目与 API 边界 | 本地验证完成 |
| 前端模式 | Practice 主页面统一练习题列表，增加题型分类；点击结构与框架题目进入具体练习页 | 实现完成，lint/build 通过，待浏览器联调 |
| 语言基础偏好 | 首次进入弹窗，右上角用户菜单可修改，按基础过滤题型和分类 | 实现完成，待浏览器联调 |
| 多级结构排序 | 同一道题内逐级提交、逐级核对，通过后选择进入下一级 | 实现完成，后端测试通过 |
| 代码填空代码量 | 提供更完整的 CNN/LSTM/Transformer/线性模型代码骨架 | 实现完成，后端测试通过 |
| 持久化与复盘 | 按需要接入 PracticeOutcome 或安全作答摘要 | 未开始 |

## 3. 最小纵向闭环

1. 前端调用 `GET /api/v1/compiler/structure-exercises` 获取题目。
2. 学生在具体练习页提交排序或填空答案。
3. 服务端返回规则 verdict、score 和 feedback。
4. 页面显示通过/未通过状态与解析，不显示标准答案。

后端闭环已通过局部测试。前端接入前不宣称该模式在产品页面可用。

## 4. 预计修改范围

| 领域 | 路径 |
| --- | --- |
| 静态练习服务 | `src/code_navi/online_compiler/structure_practice.py` |
| API | `src/code_navi/online_compiler/router.py` |
| 前端 API | `frontend/lib/api/compiler.ts` |
| 前端页面 | `frontend/app/(student)/practice/page.tsx` |
| 验证 | `tests/online_compiler/test_structure_practice.py` |

## 5. 接口与数据边界

1. 静态练习不调用 `PistonClient`，不执行学生代码。
2. 提交响应只返回规则反馈和解析，不返回完整标准答案。
3. 第一版不新增 Alembic revision；题目目录为进程内存。
4. 前端不能提交服务端未提供的答案结构、判题规则或标准答案。

## 6. 最小验证

1. 列表接口不泄漏答案或判题 token。
2. 排序题的正确与错误顺序均有反馈。
3. 框架填空题的完整和缺失 token 均有反馈。
4. 未知题目、缺少答案和错误答案类型分别返回对应状态码。
5. 现有 Python 执行 API 回归不受影响。

## 7. 退出条件

Spec 定义的列表、提交、判题、隐私和边界条件已在本地验证完成，且前端模式能独立进入、提交和恢复显示结果。当前只有后端闭环，因此尚未达到本地验证完成。
