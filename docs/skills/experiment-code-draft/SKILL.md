# 实验代码草案 Skill

- 名称：`experiment_code_draft`；版本：`0.2.0`。
- 输入：用户在网页明确确认，以及已形成的规则研究计划。
- 输出：`experiment-code-draft.v1` 的目录树、依赖提示、README、数据加载/基线/评测模板、运行说明、假设和待核验项。

该 Skill 不需要网络或工具权限，但必须由用户显式确认触发。它不写入用户项目、不安装依赖、不执行命令或代码，默认合成数据；真实路径、密钥、指标和运行步骤全部保留为后续人工确认事项。

可选 DeepSeek 只在确认请求和规则研究计划已存在时生成 JSON 代码草案。规则层会拒绝密钥、Token、私有/绝对路径、网络下载、自动安装、`subprocess`/Shell 执行模式和缺失的安全模板文件；无 Key、超时、网络错误、非 JSON、字段缺失、超长或安全校验失败时返回规则模板并标记规则降级。网页仅提供“复制代码”和“下载草案文本”，导出的只是浏览器内已生成文本，不会写入学生项目。测试样例：`python -m pytest tests/test_research_artifact_llm.py tests/test_research_mindmap.py -q`。
