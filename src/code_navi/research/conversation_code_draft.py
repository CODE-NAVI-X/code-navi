"""Safe, preview-only experiment code draft generation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .conversation_schemas import (
    ConversationResearchPlan,
    ExperimentCodeDraft,
    ExperimentCodeDraftFile,
    ResearchProfile,
)
from .research_artifact_llm import ResearchArtifactGenerator


class _CodeDraftPersonalization(BaseModel):
    """The model may personalize labels, never executable file contents."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    assumptions: list[str] = Field(min_length=1, max_length=8)
    to_verify_items: list[str] = Field(min_length=1, max_length=8)
    provenance_note: str = Field(min_length=1, max_length=1000)


def build_experiment_code_draft(
    profile: ResearchProfile,
    *,
    plan: ConversationResearchPlan | None,
    generator: ResearchArtifactGenerator | None = None,
    conversation_id: str | None = None,
) -> ExperimentCodeDraft:
    """Create a fixed, synthetic-data preview only after the caller confirms intent."""
    if plan is None:
        raise ValueError("当前科研画像尚未形成规则研究计划，不能生成代码草案。")
    topic = profile.topic or "待确认研究主题"
    rules = ExperimentCodeDraft(
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
                path="requirements.txt",
                content="# 依赖由用户在确认后手动填写；系统不会安装任何依赖。",
            ),
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
        run_instructions=[
            "先人工确认 README 中的数据、指标和许可 TODO；系统不会安装依赖或执行命令。"
        ],
        assumptions=["默认使用合成数据，不读取真实数据路径。"],
        to_verify_items=["真实数据许可、基线、指标、硬件和运行方式需要用户与导师确认。"],
        provenance_note="这是只读网页预览：不写入用户项目、不安装依赖、不执行命令或代码。模板默认使用合成数据；真实数据路径、指标、基线和运行命令需在用户与导师确认后另行处理。",
    )
    if generator is None:
        return rules
    if conversation_id is None:
        raise ValueError("conversation_id is required for model code draft generation")
    outcome = generator.generate(
        kind="experiment_code_draft",
        conversation_id=conversation_id,
        context={
            "profile": profile.model_dump(mode="json"),
            "research_plan": plan.model_dump(mode="json"),
            "safe_template_contract": {
                "code_files": "server-owned fixed templates; the model cannot modify them",
                "default_data": "synthetic only",
            },
            "required_json_shape": {
                "title": "string",
                "assumptions": "string[]",
                "to_verify_items": "string[]",
                "provenance_note": "string",
            },
        },
    )
    if outcome.status == "unavailable":
        return rules
    if outcome.status != "generated" or outcome.text is None:
        return rules.model_copy(update={"generation_mode": "rules_fallback"})
    try:
        personalization = _CodeDraftPersonalization.model_validate_json(outcome.text)
        return rules.model_copy(
            update={
                "title": personalization.title,
                "assumptions": personalization.assumptions,
                "to_verify_items": personalization.to_verify_items,
                "provenance_note": personalization.provenance_note,
                "generation_mode": "llm",
                "run_id": outcome.run_id,
                "event_count": outcome.event_count,
            }
        )
    except ValueError:
        return rules.model_copy(update={"generation_mode": "rules_fallback"})
