"""Domain-owned agent declarations for compiler learning feedback."""

from kernel.core import KernelConfig
from kernel.runtime import AgentSpec

code_result_explainer_agent = AgentSpec(
    name="code_result_explainer",
    description="Explains one deterministic Python execution result for a student.",
    system_prompt=(
        "你是 Python 学习反馈助手。规则层给出的 category 是不可更改的执行事实；"
        "不要把运行成功解释为题目答案正确。结合源码、标准错误和规则结论，用中文解释原因并给出"
        "可操作建议。只输出一个 JSON 对象，不要 Markdown，结构必须为："
        '{"explanation":"...","suggestions":["..."],"quality":'
        '{"readability":0,"structure":0,"robustness":0}}。'
        "三个质量维度均为 0 到 100 的整数，只评价代码可读性、结构与健壮性，"
        "不评价题目正确性；信息不足时应降低分数并明确不确定性。"
    ),
    tool_names=(),
    default_config=KernelConfig(
        max_steps=1,
        max_tool_calls=0,
        retry_max_attempts=1,
        retry_backoff_seconds=0.25,
    ),
    output_format="json",
)

__all__ = ["code_result_explainer_agent"]

guided_code_tutor_agent = AgentSpec(
    name="guided_code_tutor",
    description=(
        "Guides a student through a failed programming submission "
        "without revealing a solution."
    ),
    system_prompt=(
        "你是 Python 编程教学引导助手。判题结果由服务端决定，不得修改 verdict 或 score。"
        "只能根据题目描述、学生代码、公开测试结果和对话历史提问或给出最小提示。"
        "绝不提供完整答案、完整代码、隐藏测试数据或隐藏测试期望输出。"
        '只输出 JSON：{"reply":"...","strategy":"question|hint|explanation","blocked":false}。'
    ),
    tool_names=(),
    default_config=KernelConfig(
        max_steps=1,
        max_tool_calls=0,
        retry_max_attempts=1,
        retry_backoff_seconds=0.25,
    ),
    output_format="json",
)

__all__.append("guided_code_tutor_agent")

problem_import_organizer_agent = AgentSpec(
    name="problem_import_organizer",
    description="Organizes rule-parsed programming exercises into a learning path.",
    system_prompt=(
        "你是编程练习题整理助手。只根据用户提供的规则解析结果整理题目，不能补造题意、"
        "输入输出、样例或隐藏测试事实。只能返回已有 importId 的建议。输出 JSON："
        '{"orderedProblems":[{"importId":"...","difficulty":"easy|medium|hard",'
        '"tags":["..."],"orderReason":"..."}],"warnings":["..."]}。'
        "排序优先体现基础语法、分支、循环、字符串/列表、字典/栈/算法的递进关系；"
        "题目样例不足时必须在 warnings 说明。"
    ),
    tool_names=(),
    default_config=KernelConfig(
        max_steps=1,
        max_tool_calls=0,
        retry_max_attempts=1,
        retry_backoff_seconds=0.25,
    ),
    output_format="json",
)

__all__.append("problem_import_organizer_agent")
