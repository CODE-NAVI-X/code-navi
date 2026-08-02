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
