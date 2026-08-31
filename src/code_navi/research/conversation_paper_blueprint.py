"""LLM-authored paper blueprints constrained by already saved local evidence."""

from __future__ import annotations

from .conversation_schemas import (
    ConversationEvidenceBundle,
    ConversationResearchPlan,
    ExperimentEvidenceBundle,
    PaperBlueprint,
    PaperBlueprintReference,
    ResearchProfile,
)
from .research_artifact_llm import ResearchArtifactGenerator
from .research_generation import ResearchGenerationError, require_generated_artifact


def build_paper_blueprint(
    profile: ResearchProfile,
    *,
    conversation_id: str,
    plan: ConversationResearchPlan | None,
    academic_evidence: list[ConversationEvidenceBundle],
    experiment_evidence: list[ExperimentEvidenceBundle],
    generator: ResearchArtifactGenerator | None = None,
) -> PaperBlueprint:
    """Generate a writing outline; rules validate evidence rather than author it."""
    if generator is None:
        raise ResearchGenerationError(
            "provider_unavailable", "paper_blueprint: generator is unavailable"
        )
    references = [
        *_profile_references(profile),
        *_plan_references(plan),
        *_academic_references(academic_evidence),
        *_experiment_fact_references(experiment_evidence),
    ]
    allowed_references = {_reference_key(reference): reference for reference in references}
    outcome = generator.generate(
        kind="paper_blueprint",
        conversation_id=conversation_id,
        context={
            "research_profile": profile.model_dump(mode="json"),
            "research_plan": plan.model_dump(mode="json") if plan else None,
            "academic_evidence": [item.model_dump(mode="json") for item in academic_evidence],
            "experiment_evidence": [
                item.model_dump(mode="json") for item in experiment_evidence
            ],
            "allowed_evidence_references": [
                item.model_dump(mode="json") for item in references
            ],
            "source_boundary": {
                "allowed_classifications_for_generated_guidance": ["inference", "to_verify"],
                "forbidden": [
                    "不得把元数据或摘要外的信息写成事实。",
                    "没有用户提交的运行记录时不得写实验结果、Accuracy 或复现成功。",
                    "不得声称论文已投稿、录用或经过同行评审。",
                ],
            },
            "required_json_shape": {
                "schema_version": "paper-blueprint.v1",
                "all_fields": "Return a complete PaperBlueprint JSON object.",
                "sections": ["引言", "相关工作", "方法", "实验", "讨论", "结论"],
                "evidence_references": "must exactly match allowed_evidence_references",
            },
        },
    )
    try:
        generated = PaperBlueprint.model_validate_json(
            require_generated_artifact(outcome, kind="paper_blueprint")
        )
        _validate_generated_blueprint(generated, conversation_id, allowed_references)
    except ResearchGenerationError:
        raise
    except ValueError as error:
        raise ResearchGenerationError(
            "invalid_output", "paper_blueprint: boundary validation failed"
        ) from error
    return generated.model_copy(
        update={
            "generation_mode": "llm",
            "run_id": outcome.run_id,
            "event_count": outcome.event_count,
            "provenance_note": (
                "本论文蓝图由模型基于当前科研画像、研究计划、用户主动保存的论文元数据/"
                "摘要和用户提交实验文本生成。规则程序仅校验可引用来源与事实边界；"
                "系统未阅读论文全文、运行实验或作出投稿判断。"
            ),
        }
    )


def _validate_generated_blueprint(
    blueprint: PaperBlueprint,
    conversation_id: str,
    allowed_references: dict[tuple[str, str | None, str, str | None], PaperBlueprintReference],
) -> None:
    if blueprint.conversation_id != conversation_id:
        raise ValueError("model changed paper blueprint conversation identity")
    entries = [
        *blueprint.candidate_titles,
        blueprint.target_submission_direction,
        *blueprint.abstract_requirements,
        blueprint.submission_readiness,
        *blueprint.gaps,
        *(section.writing_goal for section in blueprint.sections),
        *(entry for section in blueprint.sections for entry in section.missing_evidence),
    ]
    if any(entry.classification == "fact" for entry in entries):
        raise ValueError("model cannot introduce fact-classified writing guidance")
    for section in blueprint.sections:
        for reference in [*section.evidence_references, *section.citation_placeholders]:
            canonical = allowed_references.get(_reference_key(reference))
            if canonical is None or reference != canonical:
                raise ValueError("model referenced evidence outside the saved conversation")


def _reference_key(
    reference: PaperBlueprintReference,
) -> tuple[str, str | None, str, str | None]:
    return (reference.source_type, reference.bundle_id, reference.label, reference.source_url)


def _profile_references(profile: ResearchProfile) -> list[PaperBlueprintReference]:
    values = [
        profile.topic,
        *profile.research_questions,
        *profile.candidate_questions,
        profile.context,
    ]
    return [
        PaperBlueprintReference(
            source_type="research_profile",
            label=value,
            classification="fact",
            information_scope="user_confirmed_profile",
        )
        for value in values
        if value
    ][:8]


def _plan_references(plan: ConversationResearchPlan | None) -> list[PaperBlueprintReference]:
    if plan is None:
        return []
    entries = [
        plan.research_goal,
        *plan.candidate_methods_or_baselines,
        *plan.suggested_datasets_or_metrics,
    ]
    return [
        PaperBlueprintReference(
            source_type="research_plan",
            label=entry.content,
            classification=entry.classification,
            information_scope="rules_plan_suggestion",
        )
        for entry in entries
    ][:10]


def _academic_references(
    bundles: list[ConversationEvidenceBundle],
) -> list[PaperBlueprintReference]:
    return [
        PaperBlueprintReference(
            source_type="academic_evidence",
            bundle_id=bundle.bundle_id,
            label=paper.title,
            classification="fact",
            source_url=paper.url,
            information_scope="metadata_and_abstract_only",
        )
        for bundle in bundles
        for paper in bundle.papers
    ][:24]


def _experiment_fact_references(
    bundles: list[ExperimentEvidenceBundle],
) -> list[PaperBlueprintReference]:
    return [
        PaperBlueprintReference(
            source_type="experiment_evidence",
            bundle_id=bundle.bundle_id,
            label=item.content,
            classification="fact",
            information_scope="user_submitted_text_unverified",
        )
        for bundle in bundles
        for item in [bundle.experiment_name, bundle.goal, *bundle.items]
        if item.classification == "fact"
    ][:24]
