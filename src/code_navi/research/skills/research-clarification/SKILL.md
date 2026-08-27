---
name: research-clarification
description: 以可恢复对话收集学生确认的研究画像，并在规则控制下提供可选的模型个性化追问。
---

# 科研需求澄清

## 版本与用途

- 版本：`1.2.0`
- 用途：将模糊想法整理为可审阅的 `ResearchProfile`，为规则研究计划和用户主动的学术检索提供输入。

## 对话策略

1. When `confirmed_learning_context` is present, treat its topic, summary, and selected content as
   user-confirmed background. Do not ask the user to repeat information already explicit there.
   Keep general learning material as background; do not turn it into an unexpressed research
   question, method, dataset, constraint, or conclusion.
2. Extract every dimension explicitly stated in the latest message. Preserve prior facts unless
   the user corrects or clears them.
3. Keep guesses out of the profile. Put plausible but unconfirmed ideas in `assumptions` and
   missing information in `uncertainties`.
4. Ask at most one primary question per turn. Choose the question that most improves feasibility
   or distinguishes candidate directions.
5. Treat suggested answers as optional shortcuts. Always accept free text and interpret short
   answers against the previous assistant question.
6. Never repeat the same question after the user selects one of its suggestions. Confirm the
   effect of the answer, update the profile, and advance or explicitly explain why it is unusable.
7. When the user asks to continue narrowing, ask about the most useful unresolved dimension,
   such as motivation, research question, method, evidence preference, scope, or constraint.
8. When the user asks to review, summarize known facts, assumptions, and uncertainties, then ask
   for corrections without pretending that the profile is final.
9. When the profile can support a search and the user explicitly asks to prepare or start search,
   set `intent` and `recommended_action` to `prepare_search`, set `next_question` to null, and
   provide no suggested answers. State that clarification is complete and that the academic-search
   Skill must be invoked separately with explicit user confirmation.
10. Do not create or decide a `research_plan`. When the validated profile reaches plan readiness,
    the application derives `research-plan.v1` deterministically outside the model decision.

## 输入与输出

- 输入：Runtime 显式 `conversation_history`、当前用户消息、已保存 `ResearchProfile`，以及可选的 `confirmed_learning_context`。当前用户消息只出现在本轮结构化输入中，历史不再重复编码为 JSON 字段。
- 输出：更新后的会话、`ResearchProfile`、下一轮问题/三个可选建议、`generation_mode`；画像可支撑规划时由应用生成规则 `research-plan.v1`。

## 规则层与模型层边界

- 规则层唯一管理会话标识、画像保存与恢复、确认状态、字段完整性、研究计划就绪判定和事实边界。
- 已配置 DeepSeek 时，模型只能返回经校验的追问 JSON（回复、下一问、三个选项及受限建议值），不能改写已确认事实、决定流程或触发检索。
- 用户说“不知道/有什么推荐吗”时，仅校验通过的建议值可填充当前缺口；否则保留缺口，不把原话写成研究事实。
- Never repeat the same question after a user selects a suggestion; confirm the saved effect and advance to the most useful unresolved dimension.
- 完成澄清后的联网交接只能交给独立的 `academic-search` Skill，并继续要求用户明确确认。

## 苏格拉底式提问策略

- 模型在规则已指定的当前缺口内，一次只追问一个未确认维度；不把多个问题、完整研究题目或隐含结论塞给学生。
- 优先按“概念如何界定/如何观察 → 需要什么证据或数据 → 有何替代解释 → 资源与时间是否可行”选择与上下文最贴近的一问；用户可拒绝、改写或自由输入。
- 该策略只改善模型个性化表达。规则兜底仍使用固定问题和三个建议，五字段、会话恢复、完成判定、联网权限和事实标签不受模型控制。

## 权限、来源与副作用

- 不需要联网权限；不访问论文、网页或外部资料源。
- 只写入应用的科研会话/画像持久化状态；不写用户项目、不安装依赖、不执行命令或代码。

## 失败与规则降级

缺少 Provider 或密钥、超时、网络错误、非 JSON、字段缺失或越界输出时，返回原有规则问题与三个固定建议，且不中断会话。模型回复从不作为论文事实。

## 测试样例

- `tests/test_research_conversation.py`：对话推进、画像恢复和规则研究计划。
- `tests/test_research_deepseek.py`、`tests/test_research_llm.py`：模型成功、非法输出/无密钥降级，以及“不知道”建议值边界。

## 外部参考与许可证

本地评估过 `Imbad0202/academic-research-skills` 的苏格拉底式提问思路（`CC BY-NC 4.0`）与 `LeonChaoX/qinyan-academic-skills`（仓库 `MIT`），仅参考一次一问、可观察证据和可行性检查的设计，不复制其 Prompt、Skill、Agent Runtime 或脚本。完整选择记录见 [外部 Skill 评估](../../../../../docs/research-skill-evaluation.md)。
