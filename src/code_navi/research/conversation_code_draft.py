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
from .research_generation import ResearchGenerationError, require_generated_artifact


class _CodeDraftPreview(BaseModel):
    """A preview-only code scaffold generated from bounded research context."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    directory_tree: list[str] = Field(min_length=1, max_length=20)
    dependencies: list[str] = Field(default_factory=list, max_length=10)
    files: list[ExperimentCodeDraftFile] = Field(min_length=1, max_length=10)
    run_instructions: list[str] = Field(min_length=1, max_length=6)
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
    """Create one LLM-authored, preview-only scaffold after explicit confirmation."""
    if plan is None:
        raise ValueError("当前科研画像尚未形成规则研究计划，不能生成代码草案。")
    if generator is None:
        raise ResearchGenerationError(
            "provider_unavailable", "experiment_code_draft: generator is unavailable"
        )
    if conversation_id is None:
        raise ValueError("conversation_id is required for model code draft generation")
    outcome = generator.generate(
        kind="experiment_code_draft",
        conversation_id=conversation_id,
        context={
            "profile": profile.model_dump(mode="json"),
            "research_plan": plan.model_dump(mode="json"),
            "safe_template_contract": {
                "preview_only": (
                    "do not write files, install dependencies, access local paths, or execute code"
                ),
                "missing_method_detail": (
                    "emit a minimal scaffold with TODO markers, not paper-faithful code"
                ),
            },
            "required_json_shape": {
                "title": "string",
                "directory_tree": "string[]",
                "dependencies": "string[]",
                "files": "[{path:string, content:string}]",
                "run_instructions": "string[]",
                "assumptions": "string[]",
                "to_verify_items": "string[]",
                "provenance_note": "string",
            },
        },
    )
    try:
        preview = _CodeDraftPreview.model_validate_json(
            require_generated_artifact(outcome, kind="experiment_code_draft")
        )
        _assert_safe_preview(preview)
        return ExperimentCodeDraft(
            title=preview.title,
            directory_tree=preview.directory_tree,
            dependencies=preview.dependencies,
            files=preview.files,
            run_instructions=preview.run_instructions,
            assumptions=preview.assumptions,
            to_verify_items=preview.to_verify_items,
            provenance_note=preview.provenance_note,
            generation_mode="llm",
            run_id=outcome.run_id,
            event_count=outcome.event_count,
        )
    except ResearchGenerationError:
        raise
    except ValueError as error:
        raise ResearchGenerationError(
            "invalid_output", "experiment_code_draft: output validation failed"
        ) from error


def _assert_safe_preview(draft: _CodeDraftPreview) -> None:
    blocked = ("api_key", "secret", "password", "subprocess", "os.system")
    if any(token in item.content.casefold() for item in draft.files for token in blocked):
        raise ValueError("model code draft contains a blocked secret or execution primitive")
