"""Application-owned orchestration for conversational research clarification."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Literal, Protocol

from sqlalchemy.orm import Session

from code_navi.context_transfer.schemas import ConfirmedContextProvenance

from .conversation_agent import (
    ConversationDecisionOutcome,
    RuntimeConversationDecisionGenerator,
)
from .conversation_citation_quality import build_citation_quality_check
from .conversation_citation_scaffold import build_citation_candidate, build_selected_citation
from .conversation_code_draft import build_experiment_code_draft
from .conversation_difficulty import build_topic_difficulty_analysis
from .conversation_experiment import build_experiment_design
from .conversation_mindmap import build_research_mindmap
from .conversation_paper_blueprint import build_paper_blueprint
from .conversation_paper_review import (
    build_revision_from_suggestion,
    build_revision_suggestion,
    build_rules_paper_review,
    parse_paper_sections,
)
from .conversation_plan import build_conversation_research_plan
from .conversation_reference_draft import build_reference_draft_package
from .conversation_schemas import (
    ApplyRevisionSuggestionRequest,
    CitationCandidate,
    CitationQualityCheck,
    ConversationEvidenceBundle,
    CreateExperimentEvidenceBundleRequest,
    CreatePaperDraftRequest,
    CreateResearchConversationRequest,
    CreateSelectedCitationRequest,
    ExperimentCodeDraft,
    ExperimentDesign,
    ExperimentEvidenceBundle,
    ExperimentEvidenceItem,
    PaperBlueprint,
    PaperDraft,
    PaperExportPackage,
    PaperReview,
    PaperRevision,
    ReferenceDraftPackage,
    ReferenceEntryDraft,
    ResearchConversationDecision,
    ResearchConversationMessage,
    ResearchConversationResponse,
    ResearchProfile,
    ResearchProfilePatch,
    ResearchReadiness,
    RevisionSuggestion,
    SelectedCitation,
    SendResearchMessageRequest,
    SubmissionReadinessCheck,
    TopicDifficultyAnalysis,
    UpdateRevisionTaskRequest,
    UpdateSelectedCitationRequest,
)
from .conversation_submission import build_paper_export_package, build_submission_readiness
from .models import (
    ResearchCitationQualityCheckModel,
    ResearchConversationModel,
    ResearchEvidenceBundleModel,
    ResearchExperimentEvidenceBundleModel,
    ResearchPaperDraftModel,
    ResearchPaperReviewModel,
    ResearchPaperRevisionModel,
    ResearchRevisionSuggestionModel,
    ResearchSelectedCitationModel,
    ResearchSubmissionReadinessModel,
)
from .research_artifact_llm import (
    ResearchArtifactGenerator,
    RuntimeResearchArtifactGenerator,
)


class ConversationNotFoundError(LookupError):
    """Raised when a requested research conversation does not exist."""


class CitationSourceNotFoundError(LookupError):
    """Raised when a citation request escapes the current conversation evidence."""


class SelectedCitationNotFoundError(LookupError):
    """Raised when a requested local citation selection does not exist."""


class ConversationDecisionGenerator(Protocol):
    """Application boundary for an online or deterministic decision generator."""

    def generate(
        self,
        *,
        profile: ResearchProfile,
        messages: list[ResearchConversationMessage],
        user_message: str,
        conversation_id: str,
        confirmed_context: ConfirmedContextProvenance | None = None,
    ) -> ConversationDecisionOutcome: ...


class ResearchConversationService:
    """Persist dialogue while keeping profile mutations validated and auditable."""

    def __init__(
        self,
        decision_generator: ConversationDecisionGenerator | None = None,
        artifact_generator: ResearchArtifactGenerator | None = None,
    ) -> None:
        self.decision_generator = decision_generator or RuntimeConversationDecisionGenerator()
        self.artifact_generator = artifact_generator or RuntimeResearchArtifactGenerator()

    def create(
        self,
        request: CreateResearchConversationRequest,
        db: Session,
    ) -> ResearchConversationResponse:
        """Create a conversation and optionally process its first user message."""
        conversation = ResearchConversationModel(
            profile_data=ResearchProfile().model_dump(mode="json"),
            messages_data=[],
        )
        db.add(conversation)
        db.flush()
        if request.initial_message:
            self._process_message(conversation, request.initial_message, db)
        else:
            welcome = ResearchConversationDecision(
                reply=(
                    "先不用按表格回答。请用自己的话说说你最近想研究的现象、"
                    "困惑或项目背景，我会边聊边整理研究画像。"
                ),
                intent="explore",
                uncertainties=["尚未了解用户的初步研究想法"],
                next_question="你最近最想弄清楚、比较或解决的事情是什么？",
                suggested_answers=[
                    "我有一个模糊想法",
                    "我有项目但没有研究问题",
                    "我想先比较几个方向",
                ],
            )
            self._append_assistant(
                conversation,
                welcome,
                generation_mode="rules",
            )
            conversation.profile_data = _apply_decision(ResearchProfile(), welcome).model_dump(
                mode="json"
            )
            db.commit()
            db.refresh(conversation)
        return self._to_response(conversation, db)

    def create_from_confirmed_context(
        self,
        provenance: ConfirmedContextProvenance,
        db: Session,
        *,
        commit: bool = True,
    ) -> ResearchConversationResponse:
        """Create a rules-only conversation from one final confirmed snapshot."""
        profile = ResearchProfile(
            topic=provenance.topic,
            uncertainties=[
                "具体研究问题仍需确认",
                "研究对象、方法、数据条件和完成标准仍需在对话中确认",
            ],
        )
        conversation = ResearchConversationModel(
            profile_data=profile.model_dump(mode="json"),
            messages_data=[],
            context_provenance=provenance.model_dump(mode="json"),
        )
        db.add(conversation)
        db.flush()
        selected_labels = "、".join(item.label for item in provenance.selected_content)
        user_message = (
            "我已检查并确认从 Learning 带入本科研会话的上下文。\n"
            f"研究主题：{provenance.topic}\n"
            f"学习摘要：{provenance.summary[:1000]}"
        )
        if selected_labels:
            user_message += f"\n保留内容：{selected_labels}"
        self._append_user(conversation, user_message)
        self._append_assistant(
            conversation,
            ResearchConversationDecision(
                reply=(
                    f"已接收并记录你确认的 Learning 上下文，当前研究主题是“{provenance.topic}”。"
                    "接下来可以在此基础上收敛研究问题；原始学习笔记不会被科研会话修改。"
                ),
                intent="clarify",
                uncertainties=list(profile.uncertainties),
                next_question="你希望围绕这个主题优先比较、解释还是解决什么具体问题？",
                suggested_answers=[
                    "比较不同方法的效果",
                    "解释关键影响因素",
                    "形成一个可执行实验",
                ],
            ),
            generation_mode="rules",
        )
        if commit:
            db.commit()
            db.refresh(conversation)
        else:
            db.flush()
        return self._to_response(conversation, db)

    def send_message(
        self,
        conversation_id: str,
        request: SendResearchMessageRequest,
        db: Session,
    ) -> ResearchConversationResponse:
        """Process one free-form user message and return the restorable state."""
        conversation = self._get_model(conversation_id, db)
        self._process_message(conversation, request.message, db)
        return self._to_response(conversation, db)

    def get(self, conversation_id: str, db: Session) -> ResearchConversationResponse:
        """Restore a conversation without invoking a model or external service."""
        return self._to_response(self._get_model(conversation_id, db), db)

    def generate_topic_difficulty_analysis(
        self,
        conversation_id: str,
        db: Session,
    ) -> TopicDifficultyAnalysis:
        """Generate personalized wording only after the dedicated endpoint is called."""
        conversation = self._get_model(conversation_id, db)
        profile = ResearchProfile.model_validate(conversation.profile_data)
        readiness = assess_readiness(profile)
        plan = build_conversation_research_plan(
            profile, ready_for_plan=readiness.stage == "ready_for_plan"
        )
        bundles = self._evidence_bundles(conversation.id, db)
        return build_topic_difficulty_analysis(
            profile,
            plan=plan,
            evidence_bundles=bundles,
            generator=self.artifact_generator,
            conversation_id=conversation.id,
        )

    def generate_experiment_design(
        self,
        conversation_id: str,
        db: Session,
    ) -> ExperimentDesign | None:
        """Generate a personalized experiment design after explicit confirmation."""
        conversation = self._get_model(conversation_id, db)
        profile = ResearchProfile.model_validate(conversation.profile_data)
        readiness = assess_readiness(profile)
        plan = build_conversation_research_plan(
            profile, ready_for_plan=readiness.stage == "ready_for_plan"
        )
        return build_experiment_design(
            profile,
            plan=plan,
            generator=self.artifact_generator,
            conversation_id=conversation.id,
        )

    def create_experiment_code_draft(
        self,
        conversation_id: str,
        db: Session,
    ) -> ExperimentCodeDraft:
        """Generate only the confirmed preview, without re-running other artefact calls."""
        conversation = self._get_model(conversation_id, db)
        profile = ResearchProfile.model_validate(conversation.profile_data)
        readiness = assess_readiness(profile)
        plan = build_conversation_research_plan(
            profile, ready_for_plan=readiness.stage == "ready_for_plan"
        )
        return build_experiment_code_draft(
            profile,
            plan=plan,
            generator=self.artifact_generator,
            conversation_id=conversation.id,
        )

    def create_experiment_evidence_bundle(
        self,
        conversation_id: str,
        request: CreateExperimentEvidenceBundleRequest,
        db: Session,
    ) -> ExperimentEvidenceBundle:
        """Persist explicit user text only; this operation has no model or network path."""
        self._get_model(conversation_id, db)
        submitted_at = datetime.now(UTC)
        basis = f"用户于 {submitted_at.isoformat()} 显式提交；系统未复核其真实性。"
        bundle = ExperimentEvidenceBundle(
            bundle_id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            experiment_name=ExperimentEvidenceItem(
                category="setup",
                content=request.experiment_name,
                classification="fact",
                basis=basis,
            ),
            goal=ExperimentEvidenceItem(
                category="setup",
                content=request.goal,
                classification="fact",
                basis=basis,
            ),
            items=[
                ExperimentEvidenceItem(
                    **item.model_dump(),
                    basis=(
                        basis
                        if item.classification == "fact"
                        else (
                            f"用户于 {submitted_at.isoformat()} 标记为"
                            f"{_classification_label(item.classification)}；系统未补造或验证。"
                        )
                    ),
                )
                for item in request.items
            ],
            submitted_at=submitted_at,
            provenance_note=(
                "本证据包仅保存用户主动粘贴的文本、表格文本或图表说明；其中 fact "
                "表示用户报告事实，未由系统读取原始数据、运行代码或独立复核。"
            ),
        )
        db.add(
            ResearchExperimentEvidenceBundleModel(
                id=bundle.bundle_id,
                conversation_id=conversation_id,
                bundle_data=bundle.model_dump(mode="json"),
                created_at=submitted_at,
            )
        )
        db.commit()
        return bundle

    def list_experiment_evidence_bundles(
        self,
        conversation_id: str,
        db: Session,
    ) -> list[ExperimentEvidenceBundle]:
        self._get_model(conversation_id, db)
        return self._experiment_evidence_bundles(conversation_id, db)

    def generate_paper_blueprint(
        self,
        conversation_id: str,
        db: Session,
    ) -> PaperBlueprint:
        """Build a rules-only, traceable outline after an explicit user action."""
        conversation = self._get_model(conversation_id, db)
        profile = ResearchProfile.model_validate(conversation.profile_data)
        readiness = assess_readiness(profile)
        plan = build_conversation_research_plan(
            profile, ready_for_plan=readiness.stage == "ready_for_plan"
        )
        return build_paper_blueprint(
            profile,
            conversation_id=conversation.id,
            plan=plan,
            academic_evidence=self._evidence_bundles(conversation.id, db),
            experiment_evidence=self._experiment_evidence_bundles(conversation.id, db),
        )

    def create_paper_draft(
        self, conversation_id: str, request: CreatePaperDraftRequest, db: Session
    ) -> PaperDraft:
        """Persist only an explicitly pasted text draft; no local file is read."""
        self._get_model(conversation_id, db)
        previous = (
            db.query(ResearchPaperDraftModel)
            .filter(ResearchPaperDraftModel.conversation_id == conversation_id)
            .count()
        )
        created_at = datetime.now(UTC)
        draft = PaperDraft(
            draft_id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            title=request.title,
            content=request.content,
            format=request.format,
            version=previous + 1,
            sections=parse_paper_sections(request.content, format=request.format),
            created_at=created_at,
        )
        db.add(
            ResearchPaperDraftModel(
                id=draft.draft_id,
                conversation_id=conversation_id,
                draft_data=draft.model_dump(mode="json"),
                created_at=created_at,
            )
        )
        db.commit()
        return draft

    def list_paper_drafts(self, conversation_id: str, db: Session) -> list[PaperDraft]:
        self._get_model(conversation_id, db)
        records = (
            db.query(ResearchPaperDraftModel)
            .filter(ResearchPaperDraftModel.conversation_id == conversation_id)
            .order_by(ResearchPaperDraftModel.created_at.desc())
            .all()
        )
        return [PaperDraft.model_validate(record.draft_data) for record in records]

    def list_citation_candidates(
        self, conversation_id: str, db: Session
    ) -> list[CitationCandidate]:
        """Derive candidate sources from saved local evidence without any search call."""
        self._get_model(conversation_id, db)
        candidates: list[CitationCandidate] = []
        for bundle in self._evidence_bundles(conversation_id, db):
            candidates.extend(
                build_citation_candidate(conversation_id, bundle, paper) for paper in bundle.papers
            )
        return candidates

    def create_selected_citation(
        self,
        conversation_id: str,
        request: CreateSelectedCitationRequest,
        db: Session,
    ) -> SelectedCitation:
        """Persist one user choice after proving the source belongs to this conversation."""
        self._get_model(conversation_id, db)
        bundle_record = (
            db.query(ResearchEvidenceBundleModel)
            .filter(
                ResearchEvidenceBundleModel.id == request.evidence_bundle_id,
                ResearchEvidenceBundleModel.conversation_id == conversation_id,
            )
            .first()
        )
        if bundle_record is None:
            raise CitationSourceNotFoundError(request.evidence_bundle_id)
        bundle = ConversationEvidenceBundle.model_validate(bundle_record.bundle_data)
        paper = next((item for item in bundle.papers if item.url == request.paper_url), None)
        if paper is None:
            raise CitationSourceNotFoundError(request.paper_url)
        created_at = datetime.now(UTC)
        selection_id = str(uuid.uuid4())
        selected = build_selected_citation(
            build_citation_candidate(conversation_id, bundle, paper),
            request,
            selected_citation_id=selection_id,
            created_at=created_at,
        )
        db.add(
            ResearchSelectedCitationModel(
                id=selection_id,
                conversation_id=conversation_id,
                selection_data=selected.model_dump(mode="json"),
                created_at=created_at,
            )
        )
        db.commit()
        return selected

    def list_selected_citations(self, conversation_id: str, db: Session) -> list[SelectedCitation]:
        """Restore explicit user selections without reading paper text or the network."""
        self._get_model(conversation_id, db)
        records = (
            db.query(ResearchSelectedCitationModel)
            .filter(ResearchSelectedCitationModel.conversation_id == conversation_id)
            .order_by(ResearchSelectedCitationModel.created_at.desc())
            .all()
        )
        return [SelectedCitation.model_validate(record.selection_data) for record in records]

    def update_selected_citation(
        self,
        selected_citation_id: str,
        request: UpdateSelectedCitationRequest,
        db: Session,
    ) -> SelectedCitation:
        """Record an explicit insert/skip state; it never changes a paper document."""
        record = db.get(ResearchSelectedCitationModel, selected_citation_id)
        if record is None:
            raise SelectedCitationNotFoundError(selected_citation_id)
        selected = SelectedCitation.model_validate(record.selection_data)
        updated = selected.model_copy(update={"status": request.status})
        record.selection_data = updated.model_dump(mode="json")
        db.commit()
        return updated

    def list_reference_entry_drafts(
        self, conversation_id: str, db: Session
    ) -> list[ReferenceEntryDraft]:
        """Return only active user choices as a locally derived, reviewable draft."""
        return [
            selected.reference_entry
            for selected in self.list_selected_citations(conversation_id, db)
            if selected.status != "skipped"
        ]

    def get_reference_draft_package(
        self, conversation_id: str, db: Session
    ) -> ReferenceDraftPackage:
        """Return deterministic copy text without search, full text, or draft mutation."""
        self._get_model(conversation_id, db)
        return build_reference_draft_package(
            conversation_id,
            self.list_selected_citations(conversation_id, db),
        )

    def create_citation_quality_check(
        self, conversation_id: str, db: Session
    ) -> CitationQualityCheck:
        """Persist one explicit offline check over this conversation's saved selections."""
        self._get_model(conversation_id, db)
        checked_at = datetime.now(UTC)
        check_id = str(uuid.uuid4())
        check = build_citation_quality_check(
            conversation_id,
            self.list_selected_citations(conversation_id, db),
            check_id=check_id,
            checked_at=checked_at,
        )
        db.add(
            ResearchCitationQualityCheckModel(
                id=check_id,
                conversation_id=conversation_id,
                check_data=check.model_dump(mode="json"),
                created_at=checked_at,
            )
        )
        db.commit()
        return check

    def list_citation_quality_checks(
        self, conversation_id: str, db: Session
    ) -> list[CitationQualityCheck]:
        """Restore checks for one conversation without running search or changing a draft."""
        self._get_model(conversation_id, db)
        records = (
            db.query(ResearchCitationQualityCheckModel)
            .filter(ResearchCitationQualityCheckModel.conversation_id == conversation_id)
            .order_by(ResearchCitationQualityCheckModel.created_at.desc())
            .all()
        )
        return [CitationQualityCheck.model_validate(record.check_data) for record in records]

    def create_paper_review(self, draft_id: str, db: Session) -> PaperReview:
        draft = self._get_paper_draft(draft_id, db)
        conversation = self._get_model(draft.conversation_id, db)
        profile = ResearchProfile.model_validate(conversation.profile_data)
        readiness = assess_readiness(profile)
        plan = build_conversation_research_plan(
            profile, ready_for_plan=readiness.stage == "ready_for_plan"
        )
        blueprint = build_paper_blueprint(
            profile,
            conversation_id=draft.conversation_id,
            plan=plan,
            academic_evidence=self._evidence_bundles(draft.conversation_id, db),
            experiment_evidence=self._experiment_evidence_bundles(draft.conversation_id, db),
        )
        review = build_rules_paper_review(
            draft,
            profile=profile,
            blueprint=blueprint,
            academic_evidence=self._evidence_bundles(draft.conversation_id, db),
            experiment_evidence=self._experiment_evidence_bundles(draft.conversation_id, db),
            generator=self.artifact_generator,
            conversation_id=draft.conversation_id,
        )
        db.add(
            ResearchPaperReviewModel(
                id=review.review_id,
                draft_id=draft_id,
                conversation_id=draft.conversation_id,
                review_data=review.model_dump(mode="json"),
                created_at=review.created_at,
            )
        )
        db.commit()
        return review

    def list_paper_reviews(self, draft_id: str, db: Session) -> list[PaperReview]:
        self._get_paper_draft(draft_id, db)
        records = (
            db.query(ResearchPaperReviewModel)
            .filter(ResearchPaperReviewModel.draft_id == draft_id)
            .order_by(ResearchPaperReviewModel.created_at.desc())
            .all()
        )
        return [PaperReview.model_validate(record.review_data) for record in records]

    def update_revision_task(
        self, review_id: str, task_id: str, request: UpdateRevisionTaskRequest, db: Session
    ) -> PaperReview:
        record = self._get_paper_review_record(review_id, db)
        review = PaperReview.model_validate(record.review_data)
        found = False
        now = datetime.now(UTC)
        tasks = []
        for task in review.revision_tasks:
            if task.task_id == task_id:
                found = True
                tasks.append(task.model_copy(update={"status": request.status, "updated_at": now}))
            else:
                tasks.append(task)
        if not found:
            raise LookupError(task_id)
        updated = review.model_copy(update={"revision_tasks": tasks})
        record.review_data = updated.model_dump(mode="json")
        db.commit()
        return updated

    def create_revision_suggestion(
        self, review_id: str, task_id: str, db: Session
    ) -> RevisionSuggestion:
        record = self._get_paper_review_record(review_id, db)
        review = PaperReview.model_validate(record.review_data)
        draft = self._get_paper_draft(review.draft_id, db)
        latest = self._latest_paper_revision(draft.draft_id, db)
        suggestion_draft = (
            draft
            if latest is None
            else draft.model_copy(
                update={
                    "content": latest.content,
                    "sections": parse_paper_sections(latest.content, format=draft.format),
                }
            )
        )
        suggestion = build_revision_suggestion(
            review,
            suggestion_draft,
            task_id,
            generator=self.artifact_generator,
            conversation_id=draft.conversation_id,
        )
        db.add(
            ResearchRevisionSuggestionModel(
                id=suggestion.suggestion_id,
                draft_id=draft.draft_id,
                review_id=review_id,
                revision_task_id=task_id,
                suggestion_data=suggestion.model_dump(mode="json"),
                created_at=suggestion.created_at,
            )
        )
        db.commit()
        return suggestion

    def list_revision_suggestions(
        self, review_id: str, task_id: str, db: Session
    ) -> list[RevisionSuggestion]:
        self._get_paper_review_record(review_id, db)
        records = (
            db.query(ResearchRevisionSuggestionModel)
            .filter(
                ResearchRevisionSuggestionModel.review_id == review_id,
                ResearchRevisionSuggestionModel.revision_task_id == task_id,
            )
            .order_by(ResearchRevisionSuggestionModel.created_at.desc())
            .all()
        )
        return [RevisionSuggestion.model_validate(item.suggestion_data) for item in records]

    def apply_revision_suggestion(
        self, suggestion_id: str, request: ApplyRevisionSuggestionRequest, db: Session
    ) -> PaperRevision | None:
        record = db.get(ResearchRevisionSuggestionModel, suggestion_id)
        if record is None:
            raise LookupError(suggestion_id)
        suggestion = RevisionSuggestion.model_validate(record.suggestion_data)
        if request.action == "skipped":
            review_record = self._get_paper_review_record(record.review_id, db)
            review = PaperReview.model_validate(review_record.review_data)
            now = datetime.now(UTC)
            tasks = [
                task.model_copy(update={"status": "skipped", "updated_at": now})
                if task.task_id == suggestion.revision_task_id
                else task
                for task in review.revision_tasks
            ]
            review_record.review_data = review.model_copy(
                update={"revision_tasks": tasks}
            ).model_dump(mode="json")
            db.commit()
            return None
        review_record = self._get_paper_review_record(record.review_id, db)
        review = PaperReview.model_validate(review_record.review_data)
        draft = self._get_paper_draft(suggestion.draft_id, db)
        latest = self._latest_paper_revision(draft.draft_id, db)
        existing = (
            db.query(ResearchPaperRevisionModel)
            .filter(ResearchPaperRevisionModel.parent_draft_id == draft.draft_id)
            .count()
        )
        revision = build_revision_from_suggestion(
            review,
            draft,
            suggestion,
            version=draft.version + existing + 1,
            parent_revision_id=latest.revision_id if latest else None,
            base_content=latest.content if latest else draft.content,
            candidate_text=request.candidate_text,
        )
        db.add(
            ResearchPaperRevisionModel(
                id=revision.revision_id,
                parent_draft_id=draft.draft_id,
                review_id=review.review_id,
                revision_data=revision.model_dump(mode="json"),
                created_at=revision.created_at,
            )
        )
        now = datetime.now(UTC)
        review_record.review_data = review.model_copy(
            update={
                "revision_tasks": [
                    task.model_copy(update={"status": "completed", "updated_at": now})
                    if task.task_id == suggestion.revision_task_id
                    else task
                    for task in review.revision_tasks
                ]
            }
        ).model_dump(mode="json")
        db.commit()
        return revision

    def list_paper_revisions(self, draft_id: str, db: Session) -> list[PaperRevision]:
        self._get_paper_draft(draft_id, db)
        records = (
            db.query(ResearchPaperRevisionModel)
            .filter(ResearchPaperRevisionModel.parent_draft_id == draft_id)
            .order_by(ResearchPaperRevisionModel.created_at.desc())
            .all()
        )
        return [PaperRevision.model_validate(record.revision_data) for record in records]

    def create_submission_readiness(self, draft_id: str, db: Session) -> SubmissionReadinessCheck:
        """Persist an explicit, rules-only checklist without evaluating acceptance."""
        draft = self._get_paper_draft(draft_id, db)
        review = self._latest_paper_review(draft_id, db)
        revision = self._latest_paper_revision(draft_id, db)
        check = build_submission_readiness(
            draft,
            review,
            revision,
            has_academic_evidence=bool(self._evidence_bundles(draft.conversation_id, db)),
            has_experiment_evidence=bool(
                self._experiment_evidence_bundles(draft.conversation_id, db)
            ),
        )
        db.add(
            ResearchSubmissionReadinessModel(
                id=check.check_id,
                draft_id=draft_id,
                conversation_id=draft.conversation_id,
                check_data=check.model_dump(mode="json"),
                created_at=check.created_at,
            )
        )
        db.commit()
        return check

    def list_submission_readiness(
        self, draft_id: str, db: Session
    ) -> list[SubmissionReadinessCheck]:
        self._get_paper_draft(draft_id, db)
        records = (
            db.query(ResearchSubmissionReadinessModel)
            .filter(ResearchSubmissionReadinessModel.draft_id == draft_id)
            .order_by(ResearchSubmissionReadinessModel.created_at.desc())
            .all()
        )
        return [SubmissionReadinessCheck.model_validate(record.check_data) for record in records]

    def create_paper_export_package(self, draft_id: str, db: Session) -> PaperExportPackage:
        """Return sanitized text only after the user separately created all prerequisites."""
        draft = self._get_paper_draft(draft_id, db)
        review = self._latest_paper_review(draft_id, db)
        revision = self._latest_paper_revision(draft_id, db)
        checks = self.list_submission_readiness(draft_id, db)
        if review is None or revision is None or not checks:
            raise ValueError(
                "Create a review, a revision preview, and an explicit submission checklist first."
            )
        readiness = checks[0]
        if revision.review_id != review.review_id:
            raise ValueError(
                "The latest revision does not belong to the latest review; "
                "apply a revision from the current review before exporting."
            )
        if readiness.revision_id != revision.revision_id:
            raise ValueError(
                "The submission checklist is stale; create a new checklist for the latest "
                "revision before exporting."
            )
        return build_paper_export_package(draft, review, revision, readiness)

    @staticmethod
    def _get_paper_draft(draft_id: str, db: Session) -> PaperDraft:
        record = db.get(ResearchPaperDraftModel, draft_id)
        if record is None:
            raise LookupError(draft_id)
        return PaperDraft.model_validate(record.draft_data)

    @staticmethod
    def _get_paper_review_record(review_id: str, db: Session) -> ResearchPaperReviewModel:
        record = db.get(ResearchPaperReviewModel, review_id)
        if record is None:
            raise LookupError(review_id)
        return record

    @staticmethod
    def _latest_paper_review(draft_id: str, db: Session) -> PaperReview | None:
        record = (
            db.query(ResearchPaperReviewModel)
            .filter(ResearchPaperReviewModel.draft_id == draft_id)
            .order_by(ResearchPaperReviewModel.created_at.desc())
            .first()
        )
        return PaperReview.model_validate(record.review_data) if record is not None else None

    @staticmethod
    def _latest_paper_revision(draft_id: str, db: Session) -> PaperRevision | None:
        record = (
            db.query(ResearchPaperRevisionModel)
            .filter(ResearchPaperRevisionModel.parent_draft_id == draft_id)
            .order_by(ResearchPaperRevisionModel.created_at.desc())
            .first()
        )
        return PaperRevision.model_validate(record.revision_data) if record is not None else None

    @staticmethod
    def _get_model(conversation_id: str, db: Session) -> ResearchConversationModel:
        conversation = db.get(ResearchConversationModel, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(conversation_id)
        return conversation

    def _process_message(
        self,
        conversation: ResearchConversationModel,
        user_message: str,
        db: Session,
    ) -> None:
        profile = ResearchProfile.model_validate(conversation.profile_data)
        existing_messages = _messages(conversation)
        confirmed_context = _confirmed_context(conversation)
        self._append_user(conversation, user_message)
        outcome = self.decision_generator.generate(
            profile=profile,
            messages=existing_messages,
            user_message=user_message,
            conversation_id=conversation.id,
            confirmed_context=confirmed_context,
        )
        if outcome.status == "generated" and outcome.decision is not None:
            decision = _enforce_runtime_decision(
                profile,
                existing_messages,
                user_message,
                outcome.decision,
            )
            mode = "agent"
        else:
            decision = _fallback_decision(
                profile,
                user_message,
                existing_messages,
                confirmed_context=confirmed_context,
            )
            mode = "rules_fallback" if outcome.status == "failed" else "rules"
        updated_profile = _apply_decision(profile, decision)
        conversation.profile_data = updated_profile.model_dump(mode="json")
        self._append_assistant(
            conversation,
            decision,
            generation_mode=mode,
            run_id=outcome.run_id,
            event_count=outcome.event_count,
        )
        db.commit()
        db.refresh(conversation)

    @staticmethod
    def _append_user(conversation: ResearchConversationModel, content: str) -> None:
        message = ResearchConversationMessage(
            message_id=str(uuid.uuid4()),
            role="user",
            content=content,
            created_at=datetime.now(UTC),
        )
        conversation.messages_data = [
            *conversation.messages_data,
            message.model_dump(mode="json"),
        ]

    @staticmethod
    def _append_assistant(
        conversation: ResearchConversationModel,
        decision: ResearchConversationDecision,
        *,
        generation_mode: Literal["agent", "rules", "rules_fallback"],
        run_id: str | None = None,
        event_count: int = 0,
    ) -> None:
        message = ResearchConversationMessage(
            message_id=str(uuid.uuid4()),
            role="assistant",
            content=decision.reply,
            created_at=datetime.now(UTC),
            generation_mode=generation_mode,
            run_id=run_id,
            event_count=event_count,
            intent=decision.intent,
            next_question=decision.next_question,
            suggested_answers=decision.suggested_answers,
            candidate_questions=decision.candidate_questions,
            recommended_action=decision.recommended_action,
        )
        conversation.messages_data = [
            *conversation.messages_data,
            message.model_dump(mode="json"),
        ]

    def _to_response(
        self,
        conversation: ResearchConversationModel,
        db: Session,
    ) -> ResearchConversationResponse:
        profile = ResearchProfile.model_validate(conversation.profile_data)
        messages = _messages(conversation)
        assistant = next(
            (message for message in reversed(messages) if message.role == "assistant"),
            None,
        )
        if assistant is None:
            raise ValueError("research conversation has no assistant message")
        readiness = assess_readiness(profile)
        plan = build_conversation_research_plan(
            profile,
            ready_for_plan=readiness.stage == "ready_for_plan",
        )
        bundles = self._evidence_bundles(conversation.id, db)
        return ResearchConversationResponse(
            conversation_id=conversation.id,
            next_skill=(
                "academic-search" if assistant.recommended_action == "prepare_search" else None
            ),
            profile=profile,
            readiness=readiness,
            stage=readiness.stage,
            ready_for_plan=readiness.stage == "ready_for_plan",
            research_plan=plan,
            research_mindmap=build_research_mindmap(
                profile,
                plan=plan,
                evidence_bundles=bundles,
            ),
            topic_difficulty_analysis=build_topic_difficulty_analysis(
                profile,
                plan=plan,
                evidence_bundles=bundles,
            ),
            experiment_design=build_experiment_design(profile, plan=plan),
            reply=assistant.content,
            generation_mode=assistant.generation_mode or "rules",
            recommended_action=assistant.recommended_action or "continue_dialogue",
            next_question=assistant.next_question,
            suggested_answers=assistant.suggested_answers,
            candidate_questions=profile.candidate_questions,
            messages=messages,
            last_run_id=assistant.run_id,
            context_provenance=(
                ConfirmedContextProvenance.model_validate(conversation.context_provenance)
                if conversation.context_provenance
                else None
            ),
        )

    @staticmethod
    def _evidence_bundles(
        conversation_id: str,
        db: Session,
    ) -> list[ConversationEvidenceBundle]:
        records = (
            db.query(ResearchEvidenceBundleModel)
            .filter(ResearchEvidenceBundleModel.conversation_id == conversation_id)
            .order_by(ResearchEvidenceBundleModel.created_at.desc())
            .all()
        )
        return [ConversationEvidenceBundle.model_validate(record.bundle_data) for record in records]

    @staticmethod
    def _experiment_evidence_bundles(
        conversation_id: str,
        db: Session,
    ) -> list[ExperimentEvidenceBundle]:
        records = (
            db.query(ResearchExperimentEvidenceBundleModel)
            .filter(ResearchExperimentEvidenceBundleModel.conversation_id == conversation_id)
            .order_by(ResearchExperimentEvidenceBundleModel.created_at.desc())
            .all()
        )
        return [ExperimentEvidenceBundle.model_validate(record.bundle_data) for record in records]


def _messages(conversation: ResearchConversationModel) -> list[ResearchConversationMessage]:
    return [
        ResearchConversationMessage.model_validate(message)
        for message in conversation.messages_data
    ]


def _classification_label(classification: str) -> str:
    return {"inference": "建议", "to_verify": "待验证"}.get(classification, "事实")


def _confirmed_context(
    conversation: ResearchConversationModel,
) -> ConfirmedContextProvenance | None:
    if not conversation.context_provenance:
        return None
    return ConfirmedContextProvenance.model_validate(conversation.context_provenance)


def _apply_decision(
    profile: ResearchProfile,
    decision: ResearchConversationDecision,
) -> ResearchProfile:
    data = profile.model_dump(mode="json")
    patch = decision.profile_patch.model_dump(mode="json", exclude_none=True)
    clear_fields = patch.pop("clear_fields", [])
    for field in clear_fields:
        data[field] = [] if isinstance(data[field], list) else None
    for field, value in patch.items():
        data[field] = value
    if decision.candidate_questions:
        data["candidate_questions"] = decision.candidate_questions
    data["assumptions"] = decision.assumptions
    data["uncertainties"] = decision.uncertainties
    return ResearchProfile.model_validate(data)


def assess_readiness(profile: ResearchProfile) -> ResearchReadiness:
    """Calculate explainable readiness without imposing a fixed questionnaire."""
    score = 0
    reasons: list[str] = []
    if profile.topic:
        score += 20
    else:
        reasons.append("还没有形成可描述的研究主题")
    if profile.research_questions or profile.candidate_questions:
        score += 25
    else:
        reasons.append("还没有候选研究问题")
    if profile.context:
        score += 15
    else:
        reasons.append("研究对象或应用场景仍不清楚")
    if profile.motivation:
        score += 10
    if profile.methods or profile.data_requirements:
        score += 10
    else:
        reasons.append("数据或研究路径尚未讨论")
    if profile.constraints:
        score += 10
    if profile.expected_output:
        score += 5
    if profile.evidence_preferences or profile.time_scope:
        score += 5
    if score < 35:
        stage = "exploring"
    elif score < 70:
        stage = "focusing"
    else:
        stage = "ready_for_plan"
    return ResearchReadiness(
        score=score,
        stage=stage,
        can_prepare_search=bool(
            profile.topic and (profile.research_questions or profile.candidate_questions)
        ),
        reasons=reasons,
    )


def _enforce_runtime_decision(
    profile: ResearchProfile,
    messages: list[ResearchConversationMessage],
    user_message: str,
    decision: ResearchConversationDecision,
) -> ResearchConversationDecision:
    """Enforce critical Skill transitions even when a model ignores its instructions."""
    provisional = _apply_decision(profile, decision)
    if (
        _requests_prepare_search(user_message)
        and assess_readiness(provisional).stage == "ready_for_plan"
    ):
        return decision.model_copy(
            update={
                "reply": (
                    "需求确认 Skill 已完成本轮澄清，当前画像已经可以形成检索约束。"
                    "下一步应由信息源检索 Skill 接管，并且只在你明确触发后访问允许的学术来源。"
                ),
                "intent": "prepare_search",
                "next_question": None,
                "suggested_answers": [],
                "recommended_action": "prepare_search",
            }
        )
    previous = next(
        (item for item in reversed(messages) if item.role == "assistant"),
        None,
    )
    answered_suggestion = bool(
        previous and user_message.strip() in previous.suggested_answers and previous.next_question
    )
    if (
        answered_suggestion
        and decision.next_question
        and decision.next_question.strip() == previous.next_question.strip()
    ):
        question, suggestions, uncertainties = _next_dialogue_step(provisional)
        if question.strip() == previous.next_question.strip():
            question, suggestions, uncertainties = _narrowing_step(provisional)
        return decision.model_copy(
            update={
                "next_question": question,
                "suggested_answers": suggestions,
                "uncertainties": uncertainties,
            }
        )
    return decision


def _fallback_decision(
    profile: ResearchProfile,
    user_message: str,
    messages: list[ResearchConversationMessage] | None = None,
    *,
    confirmed_context: ConfirmedContextProvenance | None = None,
) -> ResearchConversationDecision:
    """Provide a dynamic, non-fabricating dialogue step when no model is available."""
    patch = _fallback_patch(profile, messages or [], user_message)
    provisional = _apply_patch_only(profile, patch)
    candidate_questions = list(provisional.candidate_questions)
    if provisional.topic and not (
        provisional.research_questions or provisional.candidate_questions
    ):
        candidate_questions = [
            f"{provisional.topic}会带来什么可观察的效果或变化？",
            f"{provisional.topic}在不同方法或场景之间有什么差异？",
            f"哪些因素会影响{provisional.topic}的结果？",
        ]
    readiness = assess_readiness(provisional)
    if _requests_prepare_search(user_message) and readiness.stage == "ready_for_plan":
        return ResearchConversationDecision(
            reply=(
                "需求确认 Skill 已完成本轮澄清，当前画像已经可以形成检索约束。"
                "下一步应由信息源检索 Skill 接管；它只会在你明确触发后访问允许的学术来源。"
            ),
            intent="prepare_search",
            profile_patch=patch,
            candidate_questions=candidate_questions,
            assumptions=list(provisional.assumptions),
            uncertainties=list(provisional.uncertainties),
            next_question=None,
            suggested_answers=[],
            recommended_action="prepare_search",
        )
    if _requests_profile_review(user_message):
        return ResearchConversationDecision(
            reply=_profile_review_reply(provisional, confirmed_context),
            intent="summarize",
            profile_patch=patch,
            candidate_questions=candidate_questions,
            assumptions=list(provisional.assumptions),
            uncertainties=list(provisional.uncertainties),
            next_question="当前画像中哪一项需要修改或补充？",
            suggested_answers=["修改研究问题", "补充研究方法", "准备探索性检索"],
            recommended_action="review_profile",
        )
    continuing_narrowing = _requests_continue_narrowing(user_message)
    if continuing_narrowing:
        question, suggestions, uncertainties = _narrowing_step(provisional)
    else:
        question, suggestions, uncertainties = _next_dialogue_step(provisional)
    uncertainties = list(dict.fromkeys([*uncertainties, *_explicit_uncertainties(user_message)]))
    reply = (
        "我已经先记录你明确表达的信息。当前没有可用的模型个性化分析，"
        "我们仍可以通过自由对话继续收窄方向。"
    )
    if confirmed_context:
        reply = (
            "我已结合你确认的 Learning 背景记录本轮信息。已有背景会继续作为已知条件，"
            "接下来只澄清研究问题、场景、方法和数据等尚未明确的部分。"
        )
    if patch.expected_output:
        reply = (
            f"已记录你的预期产出是“{patch.expected_output}”。这不会直接生成或承诺一篇论文；"
            "我们会先把研究问题、方法与证据来源约束整理清楚。"
        )
    return ResearchConversationDecision(
        reply=reply,
        intent="explore" if not provisional.topic else "clarify",
        profile_patch=patch,
        candidate_questions=candidate_questions,
        uncertainties=uncertainties,
        next_question=question,
        suggested_answers=suggestions,
        recommended_action=(
            "continue_dialogue"
            if continuing_narrowing or readiness.stage != "ready_for_plan"
            else "review_profile"
        ),
    )


def _fallback_patch(
    profile: ResearchProfile,
    messages: list[ResearchConversationMessage],
    message: str,
) -> ResearchProfilePatch:
    if (
        _requests_prepare_search(message)
        or _requests_profile_review(message)
        or _requests_continue_narrowing(message)
    ):
        return ResearchProfilePatch()
    topic: str | None = None
    match = re.search(r"(?:我想|希望|准备)?(?:研究|探索|了解)([^，。；,;？?]+)", message)
    explicitly_reframes_topic = any(
        marker in message for marker in ("改成", "换成", "主题是", "方向改为")
    )
    if match and (profile.topic is None or explicitly_reframes_topic):
        candidate = match.group(1).strip("：: ")
        if candidate not in {"什么", "一下", "这个", "这个方向"} and len(candidate) >= 2:
            topic = candidate
    context: str | None = None
    context_match = re.search(r"(?:面向|针对)([^，。；,;]+)", message)
    if context_match:
        context = context_match.group(1).strip()
    active_question = next(
        (
            item.next_question
            for item in reversed(messages)
            if item.role == "assistant" and item.next_question
        ),
        None,
    )
    if (
        context is None
        and profile.context is None
        and active_question
        and _asks_for_context(active_question)
        and not _is_uncertainty(message)
    ):
        context = message.strip()
    constraints: list[str] = []
    markers = (
        "公开数据",
        "数据不好找",
        "不训练模型",
        "不想自己训练模型",
        "时间有限",
        "两周内",
        "本科生",
    )
    constraints.extend(marker for marker in markers if marker in message)
    expected_output = next(
        (value for value in ("论文", "文献综述", "开题报告", "原型系统") if value in message),
        None,
    )
    research_questions: list[str] | None = None
    if any(marker in message for marker in ("是否", "如何", "为什么", "影响", "比较")):
        research_questions = [message.strip()]
    methods: list[str] | None = None
    data_requirements: str | None = None
    if (
        profile.context
        and not (profile.methods or profile.data_requirements)
        and active_question
        and _asks_for_data_or_method(active_question)
        and not _is_uncertainty(message)
    ):
        method_names = [
            method
            for marker, method in (
                ("问卷", "问卷"),
                ("访谈", "访谈"),
                ("对照实验", "对照实验"),
            )
            if marker in message
        ]
        if "实验" in message and "对照实验" not in message:
            method_names.append("实验")
        methods = list(dict.fromkeys(method_names)) or None
        if methods is None or any(marker in message for marker in ("数据", "材料", "案例", "样本")):
            data_requirements = message.strip()
    return ResearchProfilePatch(
        topic=topic,
        context=context,
        methods=methods,
        data_requirements=data_requirements,
        constraints=constraints or None,
        expected_output=expected_output,
        research_questions=research_questions,
    )


def _apply_patch_only(
    profile: ResearchProfile,
    patch: ResearchProfilePatch,
) -> ResearchProfile:
    decision = ResearchConversationDecision(
        reply="继续澄清。",
        intent="clarify",
        profile_patch=patch,
    )
    return _apply_decision(profile, decision)


def _next_dialogue_step(
    profile: ResearchProfile,
) -> tuple[str, list[str], list[str]]:
    if not profile.topic:
        return (
            "先不考虑正式题目：你最近遇到的哪个现象、问题或项目最让你想继续了解？",
            ["从课程或项目出发", "从感兴趣的技术出发", "先比较几个方向"],
            ["尚未识别初步研究主题"],
        )
    if not (profile.research_questions or profile.candidate_questions):
        return (
            f"围绕“{profile.topic}”，你更想比较效果、解释原因，还是解决一个具体问题？",
            ["比较不同方案", "分析影响因素", "解决实际问题"],
            ["研究主题已有，但研究问题还没有收窄"],
        )
    if not profile.context:
        return (
            "这个问题准备放在哪类人群、数据、课程或项目场景中研究？",
            ["公开数据集", "真实课程或用户", "已有项目案例"],
            ["研究对象或场景尚未确认"],
        )
    if not (profile.methods or profile.data_requirements):
        return (
            "为了判断是否做得动，你现在能获得哪些数据、样本或项目材料？",
            ["只能使用公开材料", "可以做问卷或访谈", "可以运行对照实验"],
            ["数据可得性和实施路径尚未确认"],
        )
    return (
        "要继续收窄研究问题，还是先检查当前研究画像并准备探索性检索？",
        ["继续收窄", "检查研究画像", "准备探索性检索"],
        list(profile.uncertainties),
    )


def _narrowing_step(
    profile: ResearchProfile,
) -> tuple[str, list[str], list[str]]:
    """Ask a useful unresolved dimension instead of repeating the completion choice."""
    if not profile.motivation:
        return (
            "你希望这项研究最终解释什么现象，或帮助解决什么实际问题？",
            ["解释行为或机制", "比较不同方案效果", "改进一个实际项目"],
            ["研究动机和尚未解决的问题需要进一步明确"],
        )
    if not profile.research_questions and profile.candidate_questions:
        return (
            "这些候选问题中，你最希望优先验证哪一个？也可以直接改写成自己的问题。",
            list(profile.candidate_questions[:3]),
            ["候选研究问题尚未由用户确认"],
        )
    if not profile.methods:
        return (
            "基于现有场景和数据条件，你倾向用什么方法分析或验证这个问题？",
            ["案例比较", "问卷或访谈", "实验或仿真"],
            ["研究方法尚未明确"],
        )
    if not profile.evidence_preferences:
        return (
            "后续检索时，你希望优先参考哪些类型的可信来源？",
            ["同行评审期刊", "高质量会议论文", "权威机构报告"],
            ["证据来源偏好尚未明确"],
        )
    if not profile.time_scope:
        return (
            "你希望研究和文献证据重点覆盖哪个时间范围？",
            ["近三年", "近五年", "不限年份但优先经典与最新研究"],
            ["研究和证据的时间范围尚未明确"],
        )
    return (
        "目前画像已经较完整。你还想进一步比较哪个变量、对象或边界条件？",
        ["细化研究变量", "缩小研究对象", "检查研究画像"],
        list(profile.uncertainties),
    )


def _requests_prepare_search(message: str) -> bool:
    normalized = message.replace(" ", "")
    return any(
        marker in normalized
        for marker in (
            "准备探索性检索",
            "开始探索性检索",
            "准备检索",
            "开始检索",
            "搜索文献",
            "检索文献",
        )
    )


def _requests_profile_review(message: str) -> bool:
    normalized = message.replace(" ", "")
    return any(marker in normalized for marker in ("检查研究画像", "查看研究画像", "总结画像"))


def _requests_continue_narrowing(message: str) -> bool:
    normalized = message.replace(" ", "")
    return any(marker in normalized for marker in ("继续收窄", "继续细化", "继续澄清"))


def _profile_review_reply(
    profile: ResearchProfile,
    confirmed_context: ConfirmedContextProvenance | None = None,
) -> str:
    lines = ["请检查当前科研画像："]
    if confirmed_context:
        lines.append(f"- 已确认学习背景：{confirmed_context.summary[:300]}")
    for label, value in (
        ("研究主题", profile.topic),
        ("研究动机", profile.motivation),
        ("对象与场景", profile.context),
        ("方法路径", "、".join(profile.methods) or None),
        ("数据需求", profile.data_requirements),
        ("预期产出", profile.expected_output),
    ):
        lines.append(f"- {label}：{value or '尚未明确'}")
    if profile.uncertainties:
        lines.append("- 待确认：" + "；".join(profile.uncertainties))
    return "\n".join(lines)


def _is_uncertainty(message: str) -> bool:
    normalized = message.replace(" ", "")
    return any(
        marker in normalized for marker in ("不知道", "不清楚", "没想好", "帮我分析", "帮我推荐")
    )


def _asks_for_context(question: str) -> bool:
    return "哪类人群" in question or "场景中研究" in question


def _asks_for_data_or_method(question: str) -> bool:
    return "哪些数据" in question or "哪些数据、样本或项目材料" in question


def _explicit_uncertainties(message: str) -> list[str]:
    normalized = message.replace(" ", "")
    uncertainties: list[str] = []
    data_uncertainty = (
        r"数据(?:来源|从哪里来|怎么获取)?.{0,6}"
        r"(?:不(?:太)?清楚|不知道|没想好)"
    )
    if re.search(data_uncertainty, normalized):
        uncertainties.append("数据来源或获取方式尚不清楚")
    if _is_uncertainty(message) and not uncertainties:
        uncertainties.append("用户表示当前方向仍不确定，需要继续共同探索")
    return uncertainties


__all__ = [
    "ConversationDecisionGenerator",
    "ConversationNotFoundError",
    "ResearchConversationService",
    "assess_readiness",
]
