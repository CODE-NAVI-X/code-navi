"""Safe, preview-only experiment code draft generation."""

from __future__ import annotations

from .conversation_schemas import (
    ConversationResearchPlan,
    ExperimentCodeDraft,
    ExperimentCodeDraftFile,
    ResearchProfile,
)


def build_experiment_code_draft(
    profile: ResearchProfile, *, plan: ConversationResearchPlan | None
) -> ExperimentCodeDraft:
    """Create a fixed, synthetic-data preview only after the caller confirms intent."""
    if plan is None:
        raise ValueError("当前科研画像尚未形成规则研究计划，不能生成代码草案。")
    topic = profile.topic or "待确认研究主题"
    return ExperimentCodeDraft(
        title=f"{topic}：实验代码草案预览",
        directory_tree=[
            "README.md",
            "requirements.txt",
            "src/",
            "src/data.py",
            "src/baseline.py",
            "src/evaluate.py",
            "data/",
        ],
        dependencies=["Python 3.11+（未安装）"],
        files=[
            ExperimentCodeDraftFile(
                path="README.md",
                content="# 实验草案\n\n仅预览；替换 TODO 前不要运行。默认不读取真实数据。",
            ),
            ExperimentCodeDraftFile(
                path="src/data.py",
                content=(
                    "def load_data():\n"
                    "    # TODO: 用户确认数据路径、许可与脱敏范围后再替换。\n"
                    '    return [{"input": "synthetic", "label": 0}]\n'
                ),
            ),
            ExperimentCodeDraftFile(
                path="src/baseline.py",
                content=(
                    "def predict(rows):\n"
                    "    # TODO: 明确基线与对照条件。\n"
                    "    return [0 for _ in rows]\n"
                ),
            ),
            ExperimentCodeDraftFile(
                path="src/evaluate.py",
                content=(
                    "def evaluate(predictions, labels):\n"
                    "    # TODO: 经导师确认后定义主指标与成功阈值。\n"
                    '    return {"metric": None, "status": "to_verify"}\n'
                ),
            ),
        ],
        provenance_note="这是只读网页预览：不写入用户项目、不安装依赖、不执行命令或代码。模板默认使用合成数据；真实数据路径、指标、基线和运行命令需在用户与导师确认后另行处理。",
    )
