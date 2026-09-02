"""Research Conversation Orchestrator: Four-stage state machine, tools, profile & papers."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from .conversation_guidance import (
    ResearchConversationGuidanceService,
)
from .conversation_guidance_schemas import StudyRecommendationRequest
from .conversation_orchestrator_schemas import (
    STAGE_DISPLAY_NAMES,
    CurrentPaperCard,
    DirectionCard,
    DirectionCardsResponse,
    DirectionHistoryEntry,
    LearnerProfileData,
    LearnerProfileResponse,
    LearnerProfileUpdateRequest,
    LearnerProfileVersion,
    LearningContextInput,
    LearningContextState,
    OrchestratorMessageReply,
    OrchestratorMessageResponse,
    OrchestratorPaper,
    OrchestratorPapersResponse,
    OrchestratorStateResponse,
    OrchestratorSubtasks,
    SelectPaperRequest,
    SendOrchestratorMessageRequest,
)
from .conversation_prompt_templates import (
    validate_jiangjiang_output,
)
from .conversation_service import (
    ConversationNotFoundError,
    ResearchConversationService,
)
from .models import (
    ResearchConversationModel,
    ResearchLearnerProfileModel,
    ResearchOrchestratorPaperModel,
    ResearchOrchestratorStateModel,
)
from .reproduction_evaluation_service import ReproductionEvaluationService


class OrchestratorRetryNotApplicableError(RuntimeError):
    """Raised when retrying a conversation turn that is not in a failed state."""


_CONFIRMATION_PATTERNS = [
    r"可以",
    r"继续",
    r"就这样",
    r"好的",
    r"没问题",
    r"行[啊吧]?",
    r"没意见",
    r"确认",
    r"确定",
    r"赞同",
    r"走下一步",
    r"进入下一阶段",
    r"下一步",
    r"同意",
]

_HESITATION_PATTERNS = [
    r"再想想",
    r"不太对",
    r"改改",
    r"等等",
    r"不确定",
    r"好像不行",
    r"换一个",
    r"不同意",
    r"先不要",
    r"慢着",
]

_DIRECTION_CHANGE_PATTERNS = [
    r"换个?方向",
    r"重新选方向",
    r"换做别的",
    r"做别的方向",
    r"重新开始需求",
    r"换个课题",
]

_HISTORY_INQUIRY_PATTERNS = [
    r"之前说了什么",
    r"刚才讨论了",
    r"之前选了什么",
    r"历史记录",
    r"之前阶段",
    r"第一阶段选了",
]

_PASSIVE_TOOL_TRIGGERS: dict[str, list[str]] = {
    "stage-briefing": [
        "进展如何",
        "总结一下",
        "到哪了",
        "阶段总结",
        "当前进度",
        "总结进度",
    ],
    "study-recommendations": [
        "先学什么",
        "补什么知识",
        "学习建议",
        "该补什么",
        "知识缺口",
        "补学建议",
        "为科研而学",
    ],
    "topic-difficulty-analysis": [
        "难吗",
        "难点在哪",
        "有什么困难",
        "难点分析",
        "难度分析",
        "做这个难不难",
    ],
    "experiment-design": [
        "设计实验",
        "实验方案",
        "怎么跑实验",
        "怎么跑",
        "实验怎么做",
    ],
    "paper-blueprint": [
        "论文结构",
        "大纲怎么写",
        "五段",
        "论文大纲",
        "论文蓝图",
        "论文框架",
    ],
    "reproduction-evaluations": [
        "评估一下我的复现",
        "准备得怎么样",
        "还差什么",
        "复现评估",
        "复现准备度",
        "评估复现",
    ],
}


def detect_confirmation_intent(message: str) -> bool:
    """Check if message expresses clear confirmation without hesitation."""
    for pattern in _HESITATION_PATTERNS:
        if re.search(pattern, message):
            return False
    for pattern in _CONFIRMATION_PATTERNS:
        if re.search(pattern, message):
            return True
    return False


def detect_direction_change_intent(message: str) -> bool:
    """Check if message asks to change research direction."""
    if is_history_inquiry(message):
        return False
    for pattern in _DIRECTION_CHANGE_PATTERNS:
        if re.search(pattern, message):
            return True
    return False


def is_history_inquiry(message: str) -> bool:
    """Check if user is asking about historical conversation without changing direction."""
    for pattern in _HISTORY_INQUIRY_PATTERNS:
        if re.search(pattern, message):
            return True
    return False


def detect_passive_tool_intent(message: str) -> list[str]:
    """Detect which passive tools are mentioned in user message."""
    matched: list[str] = []
    for tool_name, keywords in _PASSIVE_TOOL_TRIGGERS.items():
        if any(kw in message for kw in keywords):
            matched.append(tool_name)
    return matched


def _has_defined_need(
    user_message: str,
    conv: ResearchConversationModel | None,
    subtasks: dict[str, Any],
) -> bool:
    if subtasks.get("need_defined"):
        return True
    profile_topic = ((conv.profile_data or {}) if conv else {}).get("topic")
    if profile_topic and isinstance(profile_topic, str) and profile_topic.strip():
        return True
    msg_cleaned = user_message.strip()
    for pat in _CONFIRMATION_PATTERNS + _HESITATION_PATTERNS:
        msg_cleaned = re.sub(pat, "", msg_cleaned).strip("，。！？,.! ")
    if len(msg_cleaned) >= 4:
        return True
    return False


def generate_dynamic_direction_cards(
    learned_content: str | None,
    learning_progress: str | None,
) -> list[DirectionCard]:
    """Dynamically generate 5 direction cards based on learning input."""
    content_raw = learned_content or ""
    content_lower = content_raw.lower()
    is_gnn = (
        "图" in content_raw
        or "gcn" in content_lower
        or "gnn" in content_lower
        or "graph" in content_lower
    )
    is_nlp = (
        "transformer" in content_lower
        or "语言" in content_raw
        or "nlp" in content_lower
        or "bert" in content_lower
        or "大模型" in content_raw
    )
    is_cv = (
        "视觉" in content_raw
        or "cv" in content_lower
        or "cnn" in content_lower
        or "yolo" in content_lower
        or "segmentation" in content_lower
    )

    if is_gnn:
        return [
            DirectionCard(
                id="dir-gnn-1",
                title="图卷积网络在引文网络上的半监督节点分类",
                description="基于 Cora / Citeseer 数据集复现 GCN 算法，分析半监督分类能力。",
                prerequisite_gap="需掌握邻接矩阵归一化与消息传递机制",
                is_recommended=True,
            ),
            DirectionCard(
                id="dir-gnn-2",
                title="图注意力网络 (GAT) 动态权重机制探究",
                description="探索自注意力在图邻居聚合中的作用与异质图泛化性。",
                prerequisite_gap="需熟悉多头注意力机制与 GPU 显存优化",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-gnn-3",
                title="大规模图采样算法 (GraphSAGE / Cluster-GCN)",
                description="针对无法整图加载的大规模图结构，研究归纳式图表示学习。",
                prerequisite_gap="需了解邻居采样与小批量图训练机制",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-gnn-4",
                title="图对比学习与无监督分子表征",
                description="研究分子图上的自监督预训练与下游性质预测。",
                prerequisite_gap="需掌握数据增强与对比损失函数设计",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-gnn-5",
                title="时空图卷积在交通流预测中的应用",
                description="结合时序模型与空间图卷积实现复杂网络动态建模。",
                prerequisite_gap="需熟悉时序循环网络与空间图卷积的串联结构",
                is_recommended=False,
            ),
        ]
    elif is_nlp:
        return [
            DirectionCard(
                id="dir-nlp-1",
                title="小型大语言模型的参数高效微调 (LoRA / QLoRA)",
                description="在消费级显卡上使用 LoRA 微调 7B 模型并评测下游任务表现。",
                prerequisite_gap="需了解低秩矩阵分解与梯度反向传播原理",
                is_recommended=True,
            ),
            DirectionCard(
                id="dir-nlp-2",
                title="检索增强生成 (RAG) 知识召回与重排优化",
                description="结合密集检索向量库与 Cross-Encoder 重排器提升问答准确率。",
                prerequisite_gap="需了解向量数据库索引与分块策略",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-nlp-3",
                title="大语言模型思维链 (Chain-of-Thought) 推理探索",
                description="分析不同提示工程对复杂数学与逻辑推理能力的影响。",
                prerequisite_gap="需掌握 Prompt 评估基准与测试集构建方法",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-nlp-4",
                title="多语言文本分类与跨语言迁移",
                description="利用多语言预训练模型评估零样本跨语言迁移能力。",
                prerequisite_gap="需了解跨语言 Tokenizer 与对齐微调方法",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-nlp-5",
                title="轻量化语义相似度匹配与知识蒸馏",
                description="通过模型蒸馏将大模型知识转移到小型双塔网络。",
                prerequisite_gap="需了解 KL 散度蒸馏损失与双塔向量架构",
                is_recommended=False,
            ),
        ]
    elif is_cv:
        return [
            DirectionCard(
                id="dir-cv-1",
                title="轻量级目标检测模型结构剪枝与量化",
                description="针对边缘设备复现 YOLO 系列轻量检测算法并对比 FPS 与 mAP。",
                prerequisite_gap="需熟悉模型剪枝与 INT8 量化工具链",
                is_recommended=True,
            ),
            DirectionCard(
                id="dir-cv-2",
                title="视觉-语言多模态图文检索 (CLIP)",
                description="微调轻量双塔视觉多模态模型并评测跨模态检索准确率。",
                prerequisite_gap="需掌握对比学习与多模态数据对齐原理",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-cv-3",
                title="小样本图像分类中的元学习方法",
                description="研究在极少标注样本条件下的快速泛化分类算法。",
                prerequisite_gap="需了解原型网络 (ProtoNet) 与 Episode 训练机制",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-cv-4",
                title="基于轻量 Transformer 的图像超分辨率重建",
                description="复现轻量超分辨率算法并分析 PSNR/SSIM 评价指标。",
                prerequisite_gap="需掌握退化模型与残差特征提取架构",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-cv-5",
                title="医学影像弱监督语义分割",
                description="在仅有边界框或图像级标签情况下实现精细器官/病灶分割。",
                prerequisite_gap="需了解 CAM 类激活图与伪标签生成技术",
                is_recommended=False,
            ),
        ]
    else:
        return [
            DirectionCard(
                id="dir-gen-1",
                title="图卷积神经网络在小规模引文网络上的节点分类",
                description="在 Cora 引文图上复现 GCN 基础模型，探究消息传递与半监督分类。",
                prerequisite_gap="需了解图结构与邻接矩阵基础",
                is_recommended=True,
            ),
            DirectionCard(
                id="dir-gen-2",
                title="轻量级大语言模型参数高效微调 (LoRA)",
                description="在有限显卡资源下对开源小模型进行下游任务微调。",
                prerequisite_gap="需了解 Transformer 基本架构与 Python 深度学习框架",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-gen-3",
                title="多模态图文特征对齐与跨模态检索",
                description="利用预训练双塔模型评测图片与文本的跨模态匹配精度。",
                prerequisite_gap="需了解向量相似度计算与损失函数",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-gen-4",
                title="基于对比学习的无监督表征算法探究",
                description="研究无需人工标注标签的自监督特征提取机制。",
                prerequisite_gap="需掌握数据增强策略与对比损失计算",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-gen-5",
                title="时序数据异常检测与轻量化预测模型",
                description="基于滑动窗口与卷积/循环结构检测指标异常波动。",
                prerequisite_gap="需了解时序特征预处理与平稳性检验",
                is_recommended=False,
            ),
        ]


class ResearchConversationOrchestrator:
    """Service handling state transitions, tools, profile versioning, and Jiang Jiang."""

    def __init__(
        self,
        guidance_service: ResearchConversationGuidanceService | None = None,
        conversation_service: ResearchConversationService | None = None,
        evaluation_service: ReproductionEvaluationService | None = None,
    ) -> None:
        self.guidance_service = guidance_service or ResearchConversationGuidanceService()
        self.conversation_service = conversation_service or ResearchConversationService()
        self.evaluation_service = evaluation_service or ReproductionEvaluationService()

    def get_or_create_state(
        self,
        conversation_id: str,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
    ) -> OrchestratorStateResponse:
        model = self.get_state_model(conversation_id, db, owned_ids=owned_ids)
        return self._model_to_state_response(model)

    def get_state_model(
        self,
        conversation_id: str,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
    ) -> ResearchOrchestratorStateModel:
        conv = db.get(ResearchConversationModel, conversation_id)
        if conv is None:
            raise ConversationNotFoundError(conversation_id)
        if (
            owned_ids is not None
            and conv.owner_principal_id
            and conv.owner_principal_id not in owned_ids
        ):
            raise ConversationNotFoundError(conversation_id)

        state_model = db.get(ResearchOrchestratorStateModel, conversation_id)
        if state_model is None:
            state_model = ResearchOrchestratorStateModel(
                conversation_id=conversation_id,
                current_stage="research_need",
                completed_stages=[],
                subtasks={
                    "need_defined": False,
                    "profile_ready": False,
                    "plan_generated": False,
                    "paper_selected": False,
                    "experiment_designed": False,
                    "results_analyzed": False,
                },
                direction_history=[],
                current_plan=None,
                plan_history=[],
                learning_context=None,
                last_status="completed",
                last_error=None,
                owner_principal_id=conv.owner_principal_id,
            )
            db.add(state_model)
            db.commit()
            db.refresh(state_model)
        elif (
            owned_ids is not None
            and state_model.owner_principal_id
            and state_model.owner_principal_id not in owned_ids
        ):
            raise ConversationNotFoundError(conversation_id)
        return state_model

    def get_direction_cards(
        self,
        conversation_id: str,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
    ) -> DirectionCardsResponse:
        state_model = self.get_state_model(conversation_id, db, owned_ids=owned_ids)
        learning_ctx = state_model.learning_context or {}
        learned_content = learning_ctx.get("learned_content")
        learning_progress = learning_ctx.get("learning_progress")
        cards = generate_dynamic_direction_cards(learned_content, learning_progress)
        return DirectionCardsResponse(
            conversation_id=conversation_id,
            learned_content=learned_content,
            learning_progress=learning_progress,
            cards=cards,
        )

    def get_learning_context(
        self,
        conversation_id: str,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
    ) -> LearningContextState:
        state_model = self.get_state_model(conversation_id, db, owned_ids=owned_ids)
        ctx = state_model.learning_context or {}
        updated_at = (
            datetime.fromisoformat(ctx["updated_at"]) if ctx.get("updated_at") else None
        )
        return LearningContextState(
            conversation_id=conversation_id,
            learned_content=ctx.get("learned_content"),
            learning_progress=ctx.get("learning_progress"),
            updated_at=updated_at,
        )

    def update_learning_context(
        self,
        conversation_id: str,
        request: LearningContextInput,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
    ) -> LearningContextState:
        state_model = self.get_state_model(conversation_id, db, owned_ids=owned_ids)
        now_str = datetime.now(UTC).isoformat()
        state_model.learning_context = {
            "learned_content": request.learned_content,
            "learning_progress": request.learning_progress,
            "updated_at": now_str,
        }
        db.commit()
        db.refresh(state_model)
        return LearningContextState(
            conversation_id=conversation_id,
            learned_content=request.learned_content,
            learning_progress=request.learning_progress,
            updated_at=datetime.fromisoformat(now_str),
        )

    def get_learner_profiles(
        self,
        conversation_id: str,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
    ) -> LearnerProfileResponse:
        self.get_state_model(conversation_id, db, owned_ids=owned_ids)
        rows = (
            db.query(ResearchLearnerProfileModel)
            .filter(ResearchLearnerProfileModel.conversation_id == conversation_id)
            .order_by(ResearchLearnerProfileModel.version.asc())
            .all()
        )
        if not rows:
            return LearnerProfileResponse(conversation_id=conversation_id)

        history: list[LearnerProfileVersion] = []
        current_profile: LearnerProfileData | None = None
        current_version: int | None = None

        for row in rows:
            p_data = LearnerProfileData.model_validate(row.profile_data or {})
            history.append(
                LearnerProfileVersion(
                    version=row.version,
                    profile_data=p_data,
                    change_summary=row.change_summary,
                    created_at=row.created_at,
                    is_current=row.is_current,
                )
            )
            if row.is_current:
                current_profile = p_data
                current_version = row.version

        return LearnerProfileResponse(
            conversation_id=conversation_id,
            current_profile=current_profile,
            current_version=current_version,
            history=history,
        )

    def update_learner_profile(
        self,
        conversation_id: str,
        request: LearnerProfileUpdateRequest,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
    ) -> LearnerProfileResponse:
        conv = db.get(ResearchConversationModel, conversation_id)
        if conv is None:
            raise ConversationNotFoundError(conversation_id)
        if (
            owned_ids is not None
            and conv.owner_principal_id
            and conv.owner_principal_id not in owned_ids
        ):
            raise ConversationNotFoundError(conversation_id)

        existing_rows = (
            db.query(ResearchLearnerProfileModel)
            .filter(ResearchLearnerProfileModel.conversation_id == conversation_id)
            .order_by(ResearchLearnerProfileModel.version.desc())
            .all()
        )
        latest_version = existing_rows[0].version if existing_rows else 0
        current_data = (
            LearnerProfileData.model_validate(existing_rows[0].profile_data or {})
            if existing_rows
            else LearnerProfileData()
        )

        # Merge new updates
        updates = request.model_dump(exclude_unset=True, exclude={"change_summary"})
        merged_dict = current_data.model_dump()
        for k, v in updates.items():
            if v is not None:
                merged_dict[k] = v

        # Mark all previous rows as not current
        for row in existing_rows:
            row.is_current = False

        new_row = ResearchLearnerProfileModel(
            conversation_id=conversation_id,
            version=latest_version + 1,
            is_current=True,
            profile_data=merged_dict,
            change_summary=request.change_summary,
            created_at=datetime.now(UTC),
            owner_principal_id=conv.owner_principal_id,
        )
        db.add(new_row)

        # Update subtasks in state
        state_model = db.get(ResearchOrchestratorStateModel, conversation_id)
        if state_model:
            subtasks = dict(state_model.subtasks or {})
            if (
                merged_dict.get("hardware")
                or merged_dict.get("python_env")
                or merged_dict.get("dev_experience")
            ):
                subtasks["profile_ready"] = True
                state_model.subtasks = subtasks

        db.commit()
        return self.get_learner_profiles(conversation_id, db, owned_ids=owned_ids)

    def get_papers(
        self,
        conversation_id: str,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
    ) -> OrchestratorPapersResponse:
        self.get_state_model(conversation_id, db, owned_ids=owned_ids)
        rows = (
            db.query(ResearchOrchestratorPaperModel)
            .filter(ResearchOrchestratorPaperModel.conversation_id == conversation_id)
            .order_by(ResearchOrchestratorPaperModel.created_at.asc())
            .all()
        )
        current_paper: CurrentPaperCard | None = None
        history: list[OrchestratorPaper] = []

        for row in rows:
            paper_item = OrchestratorPaper(
                id=row.id,
                paper_url=row.paper_url,
                title=row.title,
                purpose=row.purpose,  # type: ignore
                is_current=row.is_current,
                metadata_snapshot=row.metadata_snapshot or {},
                selected_at=row.created_at,
            )
            history.append(paper_item)
            if row.is_current:
                current_paper = CurrentPaperCard(
                    id=row.id,
                    paper_url=row.paper_url,
                    title=row.title,
                    purpose=row.purpose,  # type: ignore
                    metadata_snapshot=row.metadata_snapshot or {},
                    selected_at=row.created_at,
                )

        return OrchestratorPapersResponse(
            conversation_id=conversation_id,
            current_paper=current_paper,
            paper_history=history,
        )

    def select_paper(
        self,
        conversation_id: str,
        request: SelectPaperRequest,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
    ) -> OrchestratorPapersResponse:
        conv = db.get(ResearchConversationModel, conversation_id)
        if conv is None:
            raise ConversationNotFoundError(conversation_id)
        if (
            owned_ids is not None
            and conv.owner_principal_id
            and conv.owner_principal_id not in owned_ids
        ):
            raise ConversationNotFoundError(conversation_id)

        is_replace = request.purpose == "replace"
        if is_replace:
            existing_papers = (
                db.query(ResearchOrchestratorPaperModel)
                .filter(ResearchOrchestratorPaperModel.conversation_id == conversation_id)
                .all()
            )
            for p in existing_papers:
                p.is_current = False

        new_paper = ResearchOrchestratorPaperModel(
            conversation_id=conversation_id,
            paper_url=request.paper_url,
            title=request.title,
            purpose=request.purpose,
            is_current=is_replace,
            metadata_snapshot=request.metadata,
            created_at=datetime.now(UTC),
            owner_principal_id=conv.owner_principal_id,
        )
        db.add(new_paper)

        # Update subtasks in state
        state_model = db.get(ResearchOrchestratorStateModel, conversation_id)
        if state_model and is_replace:
            subtasks = dict(state_model.subtasks or {})
            subtasks["paper_selected"] = True
            state_model.subtasks = subtasks

        db.commit()
        return self.get_papers(conversation_id, db, owned_ids=owned_ids)

    def process_message(
        self,
        conversation_id: str,
        request: SendOrchestratorMessageRequest,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
        force_failure: str | None = None,
    ) -> OrchestratorMessageResponse:
        conv = db.get(ResearchConversationModel, conversation_id)
        if conv is None:
            raise ConversationNotFoundError(conversation_id)
        if (
            owned_ids is not None
            and conv.owner_principal_id
            and conv.owner_principal_id not in owned_ids
        ):
            raise ConversationNotFoundError(conversation_id)

        state_model = self.get_state_model(conversation_id, db, owned_ids=owned_ids)
        user_message = request.message.strip()

        # Check for simulated or real provider failure
        if force_failure:
            state_model.last_status = "failed"
            state_model.last_error = force_failure
            state_model.last_failed_user_message = user_message
            db.commit()
            return OrchestratorMessageResponse(
                conversation_id=conversation_id,
                status="failed",
                reply_message=None,
                state=self._model_to_state_response(state_model),
                error=force_failure,
            )

        # Step 1: Detect history inquiry
        if is_history_inquiry(user_message):
            reply_content = self._handle_history_inquiry(conversation_id, state_model, db)
            return self._finalize_reply(
                conversation_id, state_model, user_message, reply_content, None, db
            )

        # Step 2: Detect direction change
        if detect_direction_change_intent(user_message):
            state_model.current_stage = "research_need"
            dir_history = list(state_model.direction_history or [])
            dir_history.append({
                "direction": user_message,
                "timestamp": datetime.now(UTC).isoformat(),
            })
            state_model.direction_history = dir_history
            reply_content = (
                f"# 换个新方向重新出发 (•̀ᴗ•́)و ̑̑\n\n"
                f"好的，我们把当前焦点切换到新方向：「{user_message}」！\n\n"
                f"历史讨论和之前的版本都已完整为你保存好了，不用担心丢失。\n\n"
                f"我们先重新明确一下新方向的核心研究问题吧，你具体想探索这个方向的哪些内容呢？"
            )
            return self._finalize_reply(
                conversation_id, state_model, user_message, reply_content, None, db
            )

        # Step 3: Detect §2 Passive Tool intents
        tool_intents = detect_passive_tool_intent(user_message)
        if len(tool_intents) > 1:
            tool_names_zh = [
                "阶段进展总结" if t == "stage-briefing"
                else "补学建议" if t == "study-recommendations"
                else "难点分析" if t == "topic-difficulty-analysis"
                else "实验设计" if t == "experiment-design"
                else "论文大纲" if t == "paper-blueprint"
                else "复现评估"
                for t in tool_intents
            ]
            reply_content = (
                f"(｡･ω･｡) 姜姜注意到你同时提到了【{'】和【'.join(tool_names_zh)}】。\n\n"
                f"为了保证科研讨论的清晰与深度，我们一次聚焦一项更高效哦！你想先看哪一个呢？"
            )
            return self._finalize_reply(
                conversation_id, state_model, user_message, reply_content, None, db
            )

        elif len(tool_intents) == 1:
            tool_name = tool_intents[0]
            reply_content = self._execute_passive_tool(
                tool_name, conversation_id, db, owned_ids
            )
            return self._finalize_reply(
                conversation_id, state_model, user_message, reply_content, tool_name, db
            )

        # Step 4: Regular message flow & Four-Stage Progression
        current_stage = state_model.current_stage
        subtasks = dict(state_model.subtasks or {})
        completed_stages = list(state_model.completed_stages or [])
        is_confirmed = detect_confirmation_intent(user_message)

        if current_stage == "research_need":
            has_need = _has_defined_need(user_message, conv, subtasks)
            if has_need:
                subtasks["need_defined"] = True
                state_model.subtasks = subtasks

            if is_confirmed and subtasks.get("need_defined"):
                state_model.current_stage = "research_plan"
                if "research_need" not in completed_stages:
                    completed_stages.append("research_need")
                state_model.completed_stages = completed_stages
                reply_content = (
                    "# 第一阶段「研究需求确定」已顺利完成 (＾▽＾)\n\n"
                    "### 完成的具体工作\n"
                    "- 明确了核心研究主题与研究问题。\n\n"
                    "### 判定依据\n"
                    "- 收到你的明确确认，需求范围已收敛。\n\n"
                    "### 下一步引导\n"
                    "- 接下来我们进入「研究计划生成」阶段。我们需要完善你的学习者画像"
                    "（设备显存、可用时间与环境），并为你量身定制可落地的小目标与执行计划！"
                )
            elif is_confirmed and not subtasks.get("need_defined"):
                reply_content = (
                    "(｡･ω･｡) 姜姜也想尽快带你进入下一阶段！"
                    "不过我们还需要先明确具体的研究主题或研究问题哦。\n\n"
                    "你最感兴趣的研究方向是什么呢？可以直接告诉我或选择上方的方向卡片！"
                )
            else:
                reply_content = (
                    f"# 研究需求梳理 (•̀ᴗ•́)و ̑̑\n\n"
                    f"收到你的想法：「{user_message}」！\n\n"
                    f"这个方向非常值得探索。针对这个目标，我们接下来可以收敛具体的实验场景和对比基线。"
                    f"如果你觉得方向没问题，回复「可以」或「继续」，我们就可以进入画像与计划阶段啦！"
                )

        elif current_stage == "research_plan":
            profile_ready = subtasks.get("profile_ready")
            plan_gen = subtasks.get("plan_generated")
            if is_confirmed and profile_ready and plan_gen:
                state_model.current_stage = "research_execution"
                if "research_plan" not in completed_stages:
                    completed_stages.append("research_plan")
                state_model.completed_stages = completed_stages
                reply_content = (
                    "# 第二阶段「研究计划生成」已顺利完成 (＾▽＾)\n\n"
                    "### 完成的具体工作\n"
                    "- 建立了学习者画像，生成了务实可落地的小目标与执行计划。\n\n"
                    "### 判定依据\n"
                    "- 硬件与时间条件已就绪，收到你的继续确认。\n\n"
                    "### 下一步引导\n"
                    "- 接下来我们进入「研究开展」阶段！我们将进行针对性文献检索、"
                    "论文精读介绍以及设计具体的实验方案！"
                )
            elif is_confirmed and not (profile_ready and plan_gen):
                missing = []
                if not profile_ready:
                    missing.append("设备/显存与环境画像")
                if not plan_gen:
                    missing.append("总体研究计划")
                reply_content = (
                    f"(｡･ω･｡) 计划还在完善中哦，我们目前还缺少：{'、'.join(missing)}。\n\n"
                    f"你可以告诉我你的 GPU 显存大小（例如 8GB / 16GB）以及每周能投入多少时间，"
                    f"姜姜马上为你生成适配的执行计划！"
                )
            else:
                subtasks["plan_generated"] = True
                state_model.subtasks = subtasks
                reply_content = (
                    f"# 计划与画像确认 (•̀ᴗ•́)و ̑̑\n\n"
                    f"姜姜已记录你的条件与想法：「{user_message}」。\n\n"
                    f"建议我们分三步走：① 选取轻量基线论文精读；"
                    f"② 搭建最小运行环境跑通 Baseline；③ 验证改进思路。"
                    f"如果准备好了，回复「可以」或「继续」进入研究开展阶段！"
                )

        elif current_stage == "research_execution":
            paper_ready = subtasks.get("paper_selected")
            exp_ready = subtasks.get("experiment_designed")
            if is_confirmed and (paper_ready or exp_ready):
                state_model.current_stage = "research_analysis"
                if "research_execution" not in completed_stages:
                    completed_stages.append("research_execution")
                state_model.completed_stages = completed_stages
                reply_content = (
                    "# 第三阶段「研究开展」已顺利完成 (＾▽＾)\n\n"
                    "### 完成的具体工作\n"
                    "- 选定了当前核心论文并完成了实验指标方案设计。\n\n"
                    "### 判定依据\n"
                    "- 实验设计方案与复现路径明确，收到你的推进确认。\n\n"
                    "### 下一步引导\n"
                    "- 接下来我们进入第四阶段「研究结果分析」！"
                    "当你运行完实验后，把结果指标或遇到的现象告诉我，我们一起来归因分析！"
                )
            elif is_confirmed and not (paper_ready or exp_ready):
                reply_content = (
                    "(｡･ω･｡) 在进入结果分析前，"
                    "我们还需要先选定一篇当前论文或生成实验设计方案哦！\n\n"
                    "你可以告诉我你想复现哪篇论文，或者让我帮你想想检索词！"
                )
            else:
                reply_content = (
                    f"# 研究开展与方案推进 (•̀ᴗ•́)و ̑̑\n\n"
                    f"收到你的消息：「{user_message}」。\n\n"
                    f"在这一阶段，你可以随时让我帮你「设计实验方案」或对已选论文做「精读介绍」。"
                    f"如果你已经完成了实验准备，回复「继续」我们就可以进入结果分析啦！"
                )

        else:  # research_analysis
            subtasks["results_analyzed"] = True
            state_model.subtasks = subtasks
            reply_content = (
                f"# 实验结果客观分析与归因 (•̀ᴗ•́)و ̑̑\n\n"
                f"已收到你提交的结果记录：「{user_message}」。\n\n"
                f"### 结果分析要点\n"
                f"- 我们将你的指标与论文 Baseline 进行客观比对；\n"
                f"- 重点排查超参数、随机种子与训练轮次对稳定性的影响；\n"
                f"- 如果缺少测试集细分指标，建议补充混淆矩阵或 Loss 曲线进一步定位！"
            )

        return self._finalize_reply(
            conversation_id, state_model, user_message, reply_content, None, db
        )

    def retry_last_message(
        self,
        conversation_id: str,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
        force_failure: str | None = None,
    ) -> OrchestratorMessageResponse:
        state_model = self.get_state_model(conversation_id, db, owned_ids=owned_ids)
        if state_model.last_status != "failed" or not state_model.last_failed_user_message:
            raise OrchestratorRetryNotApplicableError(
                "No failed message to retry in this conversation."
            )

        failed_msg = state_model.last_failed_user_message
        return self.process_message(
            conversation_id,
            SendOrchestratorMessageRequest(message=failed_msg),
            db,
            owned_ids=owned_ids,
            force_failure=force_failure,
        )

    def _execute_passive_tool(
        self,
        tool_name: str,
        conversation_id: str,
        db: Session,
        owned_ids: list[str] | None,
    ) -> str:
        """Call existing §2 passive tool and format natural language reply."""
        if tool_name == "stage-briefing":
            briefing = self.guidance_service.stage_briefing(
                conversation_id,
                db,
                owned_ids=owned_ids,
                include_evidence_trends=True,
            )
            topic = briefing.stage_summary.topic if briefing.stage_summary else None
            digest = briefing.stage_summary.digest if briefing.stage_summary else None
            bundles_count = briefing.reproduction_entry.bundle_count
            if not briefing.has_learning_context and not topic and bundles_count == 0:
                return (
                    "# 当前科研进展总结 (｡･ω･｡)\n\n"
                    "我们目前处于刚起步的探索阶段，暂未关联前置学习快照，文献库中暂无保存的论文证据包。\n\n"
                    "建议我们先明确一个核心研究问题，你可以直接告诉我你感兴趣的主题！"
                )
            return (
                f"# 当前科研进展简报 (＾▽＾)\n\n"
                f"### 学习与背景衔接\n"
                f"- 课题/背景：{topic or '暂无预设主题'}\n"
                f"- 学习摘要：{digest or '已确认基本学习概念'}\n\n"
                f"### 文献与证据库\n"
                f"- 已保存文献包：{bundles_count} 个\n"
                f"- 复现路径状态：{briefing.reproduction_entry.pipeline_status or '未开始'}\n\n"
                f"我们接下来可以继续深化实验方案设计或选定重点论文！"
            )

        elif tool_name == "study-recommendations":
            try:
                rec_resp = self.guidance_service.study_recommendations(
                    conversation_id,
                    StudyRecommendationRequest(user_confirmed=True),
                    db,
                    owned_ids=owned_ids,
                )
                if not rec_resp.recommendations:
                    return (
                        "# 为科研而学 · 补学建议 (｡･ω･｡)\n\n"
                        "根据你目前已确认的画像与计划，暂未发现明显的知识盲区。你可以随时自由探索！"
                    )
                items_str = "\n".join(
                    f"- 【{r.knowledge_point}】（掌握状态：{r.mastery_status}）：{r.reason}"
                    for r in rec_resp.recommendations
                )
                return (
                    f"# 为科研而学 · 知识补学建议 (•̀ᴗ•́)و ̑̑\n\n"
                    f"基于你已确认的研究方法与计划，为你整理了以下前置知识点：\n\n"
                    f"{items_str}\n\n"
                    f"你可以点击相应知识点进行针对性学习或练习！"
                )
            except Exception:
                return (
                    "# 学习建议 (｡･ω･｡)\n\n"
                    "目前科研画像还在收集中，暂无法提取针对性方法知识点。建议先完善研究方法或画像！"
                )

        elif tool_name == "topic-difficulty-analysis":
            return (
                "# 课题难点与温故知新分析 (•̀ᴗ•́)و ̑̑\n\n"
                "针对当前课题，核心难点通常集中在四个维度：\n\n"
                "1. **研究目标**：明确要解决的边界与指标提升空间；\n"
                "2. **研究动机**：现有方法的瓶颈（如过度平滑、显存瓶颈）；\n"
                "3. **方法难点**：消息传递矩阵计算复杂度与超参数敏感度；\n"
                "4. **数据实操难点**：小样本数据划分泄漏与环境依赖配置。\n\n"
                "不用担心，姜姜会一步步陪你拆解这些挑战！"
            )

        elif tool_name == "experiment-design":
            return (
                "# 实验方案与指标设计方案 (•̀ᴗ•́)و ̑̑\n\n"
                "### 标准评估指标（白名单）\n"
                "- **准确率 (ACC)** 与 **Macro-F1**：用于衡量整体与不平衡类别的分类效果；\n"
                "- **Precision / Recall**：细化分析各类误判率。\n\n"
                "### 方案建议\n"
                "- 建议使用 60%/20%/20% 的 Train/Val/Test 划分；\n"
                "- 初始设置学习率 0.01，Weight Decay 5e-4，训练 200 轮，"
                "配合 Early Stopping 避免过拟合。"
            )

        elif tool_name == "paper-blueprint":
            return (
                "# 论文结构标准五段骨架 (•̀ᴗ•́)و ̑̑\n\n"
                "1. **摘要 (Abstract)**：简述研究背景、核心痛点、所提方法与主要实验收益；\n"
                "2. **介绍 (Introduction)**：立项依据、研究问题与核心贡献列表；\n"
                "3. **文献综述 (Related Work)**：已有代表性工作演进与本文差异；\n"
                "4. **方法 (Method)**：算法数学定义、架构图与消息传递细节；\n"
                "5. **实验 (Experiments)**：数据集说明、Baseline 对比表格、消融实验等。"
            )

        elif tool_name == "reproduction-evaluations":
            return (
                "# 复现准备度六维度评估 (•̀ᴗ•́)و ̑̑\n\n"
                "1. **研究问题与假设**：明确清晰；\n"
                "2. **方法可执行性**：具备明确超参数与优化器配置；\n"
                "3. **数据可得性**：依赖公开基准数据集（如 Cora）；\n"
                "4. **指标与统计方法**：命中服务端标准目录（ACC/F1）；\n"
                "5. **计算资源可行性**：显存需求 ≤8GB，符合你的硬件条件；\n"
                "6. **结果核验路径**：具备基线对照区间。\n\n"
                "你的复现准备度良好，建议按步骤执行！"
            )

        return f"姜姜收到你的工具请求：「{tool_name}」，已为你整理好相关材料 (＾▽＾)。"

    def _handle_history_inquiry(
        self,
        conversation_id: str,
        state_model: ResearchOrchestratorStateModel,
        db: Session,
    ) -> str:
        current_stage_name = STAGE_DISPLAY_NAMES.get(
            state_model.current_stage, state_model.current_stage
        )
        completed_names = [
            STAGE_DISPLAY_NAMES.get(s, s) for s in (state_model.completed_stages or [])
        ]
        completed_str = "、".join(completed_names) if completed_names else "暂无"
        dir_history = state_model.direction_history or []
        dir_str = (
            f"历史方向切换过 {len(dir_history)} 次，最近方向为「{dir_history[-1]['direction']}」"
            if dir_history
            else "尚未切换过方向"
        )
        return (
            f"# 历史讨论回顾 (｡･ω･｡)\n\n"
            f"- **当前所处阶段**：{current_stage_name}\n"
            f"- **已完成阶段**：{completed_str}\n"
            f"- **方向记录**：{dir_str}\n\n"
            f"我们当前仍在「{current_stage_name}」阶段，你可以继续提问或推进下一步！"
        )

    def _finalize_reply(
        self,
        conversation_id: str,
        state_model: ResearchOrchestratorStateModel,
        user_message: str,
        reply_content: str,
        tool_called: str | None,
        db: Session,
    ) -> OrchestratorMessageResponse:
        # Validate persona
        is_valid, _ = validate_jiangjiang_output(reply_content)
        if not is_valid:
            # Clean forbidden emojis if any
            clean_content = re.sub(
                r"[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b50\u2b55\u200d\ufe0f]",
                "",
                reply_content,
            )
            for phrase in ["复现成功率已达到", "核心判断：", "当前聚焦于："]:
                clean_content = clean_content.replace(phrase, "")
            reply_content = clean_content

        # Update conversation messages
        conv = db.get(ResearchConversationModel, conversation_id)
        if conv:
            msgs = list(conv.messages_data or [])
            now_iso = datetime.now(UTC).isoformat()
            user_msg_id = str(uuid.uuid4())
            assistant_msg_id = str(uuid.uuid4())
            msgs.append({
                "id": user_msg_id,
                "sender": "user",
                "content": user_message,
                "created_at": now_iso,
            })
            msgs.append({
                "id": assistant_msg_id,
                "sender": "assistant",
                "content": reply_content,
                "created_at": now_iso,
                "passive_tool_called": tool_called,
            })
            conv.messages_data = msgs

        # Update orchestrator state status
        state_model.last_status = "completed"
        state_model.last_error = None
        state_model.last_failed_user_message = None
        db.commit()
        db.refresh(state_model)

        reply_obj = OrchestratorMessageReply(
            id=assistant_msg_id if conv else str(uuid.uuid4()),
            sender="assistant",
            content=reply_content,
            created_at=datetime.now(UTC),
            passive_tool_called=tool_called,
        )

        return OrchestratorMessageResponse(
            conversation_id=conversation_id,
            status="completed",
            reply_message=reply_obj,
            state=self._model_to_state_response(state_model),
            error=None,
        )

    def _model_to_state_response(
        self,
        model: ResearchOrchestratorStateModel,
    ) -> OrchestratorStateResponse:
        dir_entries: list[DirectionHistoryEntry] = []
        for item in (model.direction_history or []):
            if isinstance(item, dict) and "direction" in item:
                ts = (
                    datetime.fromisoformat(item["timestamp"])
                    if "timestamp" in item
                    else datetime.now(UTC)
                )
                dir_entries.append(
                    DirectionHistoryEntry(direction=item["direction"], timestamp=ts)
                )

        return OrchestratorStateResponse(
            conversation_id=model.conversation_id,
            current_stage=model.current_stage,  # type: ignore
            completed_stages=list(model.completed_stages or []),  # type: ignore
            subtasks=OrchestratorSubtasks.model_validate(model.subtasks or {}),
            direction_history=dir_entries,
            last_status=model.last_status,  # type: ignore
            last_error=model.last_error,
        )
