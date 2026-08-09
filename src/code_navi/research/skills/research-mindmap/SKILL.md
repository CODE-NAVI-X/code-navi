---
name: research-mindmap
description: 从已保存科研画像、规则计划与 EvidenceBundle 确定性构建可追溯研究思维导图。
---

# 研究思维导图

## 版本与用途

- 版本：`0.2.0`
- 用途：提供 `research-mindmap.v1` 的节点、边、状态与来源数据，并在前端渲染交互式节点连线图和真实 SVG 导出。

## 输入与输出

- 输入：已保存的 `ResearchProfile`、`research-plan.v1`、EvidenceBundle 和会话标识。
- 输出：`root_node_id`、`nodes`、后端确定的 `edges`、来源信息及 provenance；无计划或无证据时仍保留安全的 `to_verify` 节点。

## 规则层与模型层边界

- 规则层确定性读取保存状态并构造真实关系、五类状态（已确认/建议/待验证/来源证据/风险）和事实边界。
- 本 Skill 不调用模型；前端只能布局和展示后端节点/边，不能添加事实或伪造连接。

## 权限、来源与副作用

- 不联网，不读取论文全文，不调用 Tool；来源链接仅在用户点击时由浏览器新标签打开。
- 不写会话或用户项目，不安装依赖、不执行代码。SVG 只导出节点、连线、颜色和可见文字。

## 失败与规则降级

图谱渲染异常时前端显示本地节点详情清单；无计划/证据时安全显示待验证节点。当前支持 SVG，PNG 因需额外栅格化/截图方案且未验证稳定性，作为后续增强而非已实现能力。

## 测试样例

- `tests/test_research_mindmap.py`：节点/边、来源详情、空计划/证据降级和 SVG 内容。
- `tests/test_research_mindmap_graph_frontend.py`：XYFlow、Dagre、真实边映射、五种状态和无自动请求契约。

## 外部参考与许可证

前端使用 `@xyflow/react` 和 `@dagrejs/dagre` 做渲染/层级布局；两者均为 MIT 许可证。仅借鉴其 API，不复制示例、资源或运行时图数据。
