# 实验方案 Skill

- 名称：`experiment_design`；版本：`0.2.0`。
- 输入：规则研究计划和已确认科研画像；输出：`experiment-design.v1`。
- 权限/副作用：无；不联网、不写入、不安装依赖、不执行实验或代码。

输出仅含标记为 `inference` 或 `to_verify` 的假设、变量、数据/基线、指标、步骤、资源、风险与导师确认项。未知数据、样本、设备和许可始终保留为待确认。

未配置 DeepSeek 时使用基础规则。已配置 `CODE_NAVI_PROVIDER=deepseek` 和 `DEEPSEEK_API_KEY` 时，模型只能根据已确认画像、规则研究计划和已保存的元数据/摘要范围，生成个性化方案表达；它不能确认资源、修改计划、联网、写文件、安装依赖或运行代码。模型输出必须通过 `experiment-design.v1` JSON、数量和事实边界校验；无 Key、超时、网络错误、非 JSON、字段缺失或超限时改用规则降级。测试样例：`python -m pytest tests/test_research_artifact_llm.py tests/test_research_mindmap.py -q`。

仅借鉴 `qinyan-academic-skills` 的 `hypothesis-generation`（MIT）的“假设—可检验预测—验证”结构；未复制代码、Prompt 或模板。
