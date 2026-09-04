"""Research Conversation Orchestrator: Four-stage state machine, tools, profile & papers."""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Callable, Generator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from sqlalchemy.orm import Session

from code_navi.providers import ProviderSettings, create_provider

from .conversation_guidance import (
    ResearchConversationGuidanceService,
    StudyRecommendationsNotConfirmedError,
)
from .conversation_guidance_schemas import (
    StudyRecommendationRequest,
)
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
    JIANGJIANG_SYSTEM_PERSONA,
    build_experiment_design_prompt,
    build_need_clarification_prompt,
    build_paper_intro_prompt,
    build_profile_and_plan_prompt,
    build_result_analysis_prompt,
    build_search_guidance_prompt,
    build_stage_transition_prompt,
    build_welcome_prompt,
    get_source_scope_prefix,
    validate_jiangjiang_output,
)
from .conversation_service import (
    ConversationNotFoundError,
    ResearchConversationService,
)
from .llm import DEEPSEEK_DEFAULT_MODEL, DeepSeekGuidanceProvider
from .metrics_catalog import STANDARD_METRICS, infer_task_type
from .models import (
    ResearchConversationModel,
    ResearchLearnerProfileModel,
    ResearchOrchestratorPaperModel,
    ResearchOrchestratorStateModel,
)
from .reproduction_evaluation_service import ReproductionEvaluationService


class OrchestratorRetryNotApplicableError(RuntimeError):
    """Raised when retrying a conversation turn that is not in a failed state."""


@dataclass(frozen=True, slots=True)
class OrchestratorLlmOutcome:
    """Result of an orchestrator LLM completion request."""

    status: Literal["generated", "unavailable", "failed"]
    reply_text: str | None = None
    reason: str | None = None


class OrchestratorLlmGenerator(Protocol):
    """Application boundary for orchestrator Agent wording."""

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Sequence[dict[str, object]] = (),
        conversation_id: str,
    ) -> OrchestratorLlmOutcome: ...


class RuntimeOrchestratorLlmGenerator:
    """Invokes real configured provider (DeepSeek/OpenAI) using existing provider configuration."""

    def __init__(
        self,
        provider_factory: Callable[[], object] | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.provider_factory = provider_factory
        self.timeout_seconds = timeout_seconds

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        conversation_history: Sequence[dict[str, object]] = (),
        conversation_id: str,
    ) -> OrchestratorLlmOutcome:
        try:
            provider = self._resolve_provider()
            if provider is None:
                return OrchestratorLlmOutcome(
                    status="unavailable",
                    reason="Provider not configured",
                )

            if hasattr(provider, "generate_chat_completion"):
                text = provider.generate_chat_completion(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    history=conversation_history,
                )
                return OrchestratorLlmOutcome(status="generated", reply_text=text)

            # OpenAI or DeepSeek client
            client = getattr(provider, "client", provider)
            if hasattr(client, "chat") and hasattr(client.chat, "completions"):
                messages = [{"role": "system", "content": system_prompt}]
                for msg in conversation_history:
                    role = "assistant" if msg.get("role") == "assistant" else "user"
                    content = str(msg.get("content") or "")
                    if content:
                        messages.append({"role": role, "content": content})
                messages.append({"role": "user", "content": user_prompt})

                model = getattr(provider, "model", DEEPSEEK_DEFAULT_MODEL)
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=2500,
                    extra_body={"thinking": {"type": "disabled"}},
                )
                text = response.choices[0].message.content
                return OrchestratorLlmOutcome(status="generated", reply_text=text)

            return OrchestratorLlmOutcome(status="unavailable", reason="Unknown provider shape")
        except (TimeoutError, Exception) as err:
            return OrchestratorLlmOutcome(status="failed", reason=str(err))

    def _resolve_provider(self) -> object | None:
        if self.provider_factory is not None:
            return self.provider_factory()
        settings = ProviderSettings.resolve(timeout=self.timeout_seconds)
        is_deepseek = settings.name == "deepseek" or (
            settings.name == "mock" and bool(os.getenv("DEEPSEEK_API_KEY"))
        )
        if is_deepseek:
            if not os.getenv("DEEPSEEK_API_KEY"):
                return None
            return DeepSeekGuidanceProvider(timeout_seconds=self.timeout_seconds)
        is_openai = settings.name == "openai" or (
            settings.name == "mock" and bool(os.getenv("OPENAI_API_KEY"))
        )
        if is_openai:
            if not os.getenv("OPENAI_API_KEY"):
                return None
            return create_provider(settings)
        return None


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


_OPENING_GREETING_PATTERNS = [
    r"^(?:你好|您好|hello|hi|嗨|哈喽|姜姜你好|姜姜好|你好姜姜|初次见面)"
    r"(?:[，,\s]*.*?(?:姜姜|开始科研|进入科研|开启科研|我想开始做科研|我想做科研|想开始做科研|做科研|科研|开始|进入))?[!！~。.\s]*$",
    r"^(?:开始|开始科研|进入科研|开启科研|进入|我想开始做科研|我想做科研|想开始做科研)[!！~。.\s]*$",
]


def is_opening_greeting_intent(message: str) -> bool:
    """Check if message expresses a fresh session opening/greeting intent."""
    msg = message.strip()
    return any(re.match(p, msg, re.IGNORECASE) for p in _OPENING_GREETING_PATTERNS)


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
    if is_opening_greeting_intent(user_message):
        return False
    if detect_confirmation_intent(user_message):
        return False
    msg_cleaned = user_message.strip()
    for pat in _CONFIRMATION_PATTERNS + _HESITATION_PATTERNS:
        msg_cleaned = re.sub(pat, "", msg_cleaned).strip("，。！？,.! ")
    if len(msg_cleaned) >= 4:
        return True
    return False


def _has_traceable_experiment_results(user_message: str) -> bool:
    """Check if user message provides verifiable, traceable experimental results evidence.

    To satisfy R1 safety bounds, results_analyzed is only set when the user provides:
    1. Quantifiable results (metrics with explicit values, e.g. Accuracy=83.5%, Loss=0.24);
    2. Traceable experimental context/configuration (dataset, architecture, or hyperparameters);
    3. Asserted, already-occurred observation, trend, or explicit baseline comparison.

    Ungrounded desires ("还需要提升"), inquiries ("如何提升？"), or isolated numbers do not qualify.
    """
    msg = user_message.lower()

    # 1. Quantifiable results check (metrics with concrete values / logs)
    has_metrics = bool(
        re.search(
            r"(?:accuracy|acc|macro-f1|micro-f1|f1|loss|bleu|rouge|mrr|map|auc|recall|precision"
            r"|top-1|top-5|准确率|损失|召回率|精确率)"
            r"[^\w\n]{0,10}"
            r"(?:[:=达到为是提升降低超]|\s+)?\s*"
            r"\d+(?:\.\d+)?%?",
            msg,
        )
        or re.search(r"(?:epoch|iter(?:ation)?)\s*\d+.*(?:loss|acc|eval|val)\s*[:=]\s*\d+", msg)
    )
    if not has_metrics:
        return False

    # 2. Traceable experimental context / config (dataset, model, or hyperparameters)
    has_dataset = bool(
        re.search(
            r"(?:cora|citeseer|pubmed|ogb|mnist|cifar|imagenet|glue|squad|cmmlu|ceval|humaneval"
            r"|测试集|验证集|训练集|数据集|test\s*set|val\s*set|dataset|benchmark)",
            msg,
        )
    )
    has_hyperparam = bool(
        re.search(
            r"(?:lr|learning\s*rate|学习率|batch_size|batch\s*size|bs|epoch|轮数|轮次|step|步数"
            r"|seed|随机种子|种子|weight_decay|dropout|optimizer|优化器|adam|sgd)\s*[:=为是\s]\s*\d+",
            msg,
        )
        or re.search(r"(?:训练|跑了|跑完)\s*\d+\s*(?:个)?\s*(?:epoch|轮|步)", msg)
    )
    has_model = bool(
        re.search(
            r"(?:gcn|gat|graphsage|gin|bert|roberta|transformer|llama|qwen|resnet|yolo"
            r"|模型|网络|算法|架构)",
            msg,
        )
    )
    has_config = (has_dataset or has_hyperparam) and (has_dataset or has_model or has_hyperparam)
    if not has_config:
        return False

    # 3. Asserted, already-occurred observation, trend, or baseline comparison
    # Exclude future desires or inquiry phrases from counting as asserted observations
    cleaned_for_phenomenon = re.sub(
        r"(?:如何|怎样|怎么|如何去|怎么去|还需要|需要|还要|希望|能否|想|打算|准备)\s*"
        r"(?:提升|提高|改进|优化|改善|调整)",
        "",
        msg,
    )

    # Must contain an explicit comparative relation / predicate against baseline
    # Merely listing "baseline=79.2%" or "基线 79%" without a comparative predicate does not qualify
    has_baseline = bool(
        re.search(
            r"(?:相比|对比|相较于|较|比)\s*(?:baseline|基线|对照组|对比组|sota|原始模型)"
            r"[^\n]{0,30}"
            r"(?:提升|提高|增加|降低|减少|高出|低出|胜过|超越|超出|落后|改善|优于|差于|好于)",
            cleaned_for_phenomenon,
        )
        or re.search(
            r"(?:高于|低于|超过|胜过|落后于|好于|差于|优于)\s*(?:baseline|基线|对照组|对比组|sota|原始模型)",
            cleaned_for_phenomenon,
        )
        or re.search(
            r"(?:提升|提高|增加|高出|超出|降低|减少)\s*(?:了)?\s*\d+(?:\.\d+)?\s*(?:%|个百分点)",
            cleaned_for_phenomenon,
        )
    )

    has_phenomenon = bool(
        re.search(
            r"(?:明显提升|显著提升|大幅提升|提升明显|提升了|提高了|下降了|降低了|持续下降"
            r"|收敛于|快速收敛|平稳收敛|未见收敛|收敛稳定|出现过拟合|发生欠拟合|过拟合现象"
            r"|梯度消失|梯度爆炸|消融实验表明|误差分析发现|性能瓶颈在"
            r"|converged|overfitting|ablation)",
            cleaned_for_phenomenon,
        )
    )

    has_analysis_evidence = has_baseline or has_phenomenon
    if not has_analysis_evidence:
        return False

    return True


def generate_dynamic_direction_cards(
    learned_content: str | None,
    learning_progress: str | None,
) -> list[DirectionCard]:
    """Dynamically generate direction cards only when learning input exists."""
    content_raw = (learned_content or "").strip()
    progress_raw = (learning_progress or "").strip()

    # Empty state: when no learning input, return empty list (no hardcoded fake cards)
    if not content_raw and not progress_raw:
        return []

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
                title="图神经网络在引文网络上的节点分类",
                description="针对图拓扑结构复现基础图神经网络，分析节点分类表现。",
                prerequisite_gap="需掌握邻接矩阵归一化与消息传递机制",
                is_recommended=True,
            ),
            DirectionCard(
                id="dir-gnn-2",
                title="图注意力机制动态权重探究",
                description="探索自注意力在图邻居聚合中的作用与异质图泛化性。",
                prerequisite_gap="需熟悉多头注意力机制与 GPU 显存优化",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-gnn-3",
                title="大规模图采样算法",
                description="针对无法整图加载的大规模图结构，研究归纳式图表示学习。",
                prerequisite_gap="需了解邻居采样与小批量图训练机制",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-gnn-4",
                title="图对比学习与无监督表征",
                description="研究图结构上的自监督预训练与下游性质预测。",
                prerequisite_gap="需掌握数据增强与对比损失函数设计",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-gnn-5",
                title="时空图卷积网络应用",
                description="结合时序模型与空间图卷积实现复杂网络动态建模。",
                prerequisite_gap="需熟悉时序循环网络与空间图卷积的串联结构",
                is_recommended=False,
            ),
        ]
    elif is_nlp:
        return [
            DirectionCard(
                id="dir-nlp-1",
                title="语言模型的参数高效微调",
                description="在有限显存资源下对模型进行下游任务微调并评测表现。",
                prerequisite_gap="需了解低秩矩阵分解与梯度反向传播原理",
                is_recommended=True,
            ),
            DirectionCard(
                id="dir-nlp-2",
                title="检索增强生成 (RAG) 知识召回优化",
                description="结合密集检索向量库与重排器提升问答准确率。",
                prerequisite_gap="需了解向量数据库索引与分块策略",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-nlp-3",
                title="提示工程与思维链推理探索",
                description="分析不同提示策略对复杂逻辑推理能力的影响。",
                prerequisite_gap="需掌握 Prompt 评估基准与测试集构建方法",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-nlp-4",
                title="跨语言迁移与文本分类",
                description="利用多语言预训练模型评估零样本跨语言迁移能力。",
                prerequisite_gap="需了解跨语言 Tokenizer 与对齐微调方法",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-nlp-5",
                title="轻量化语义匹配与知识蒸馏",
                description="通过模型蒸馏将大模型知识转移到小型双塔网络。",
                prerequisite_gap="需了解 KL 散度蒸馏损失与双塔向量架构",
                is_recommended=False,
            ),
        ]
    elif is_cv:
        return [
            DirectionCard(
                id="dir-cv-1",
                title="轻量级目标检测模型剪枝与量化",
                description="针对边缘设备复现轻量检测算法并对比帧率与精度。",
                prerequisite_gap="需熟悉模型剪枝与量化工具链",
                is_recommended=True,
            ),
            DirectionCard(
                id="dir-cv-2",
                title="多模态图文检索与特征对齐",
                description="微调轻量双塔视觉多模态模型并评测跨模态检索准确率。",
                prerequisite_gap="需掌握对比学习与多模态数据对齐原理",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-cv-3",
                title="小样本图像分类元学习方法",
                description="研究在极少标注样本条件下的快速泛化分类算法。",
                prerequisite_gap="需了解元学习与 Episode 训练机制",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-cv-4",
                title="图像超分辨率重建算法探究",
                description="复现轻量超分辨率算法并分析评价指标。",
                prerequisite_gap="需掌握退化模型与残差特征提取架构",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-cv-5",
                title="弱监督图像语义分割",
                description="在仅有弱标注情况下实现精细目标分割。",
                prerequisite_gap="需了解类激活图与伪标签生成技术",
                is_recommended=False,
            ),
        ]
    else:
        # General adaptive directions based on user's text
        base_title = content_raw[:15]
        return [
            DirectionCard(
                id="dir-adp-1",
                title=f"{base_title} 基础算法复现与评测",
                description=f"围绕「{content_raw[:30]}」构建基础模型并完成标准评测。",
                prerequisite_gap="需熟悉相关基础理论与 Python 深度学习框架",
                is_recommended=True,
            ),
            DirectionCard(
                id="dir-adp-2",
                title=f"{base_title} 轻量化与效率优化",
                description="在受限硬件条件下探究模型的计算与显存优化。",
                prerequisite_gap="需掌握模型量化或剪枝技术",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-adp-3",
                title=f"{base_title} 特征增强与鲁棒性分析",
                description="探究数据扰动与特征提取对下游任务稳定性的影响。",
                prerequisite_gap="需了解数据增强与鲁棒性评测基准",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-adp-4",
                title=f"{base_title} 无监督与自监督表征探究",
                description="研究在无大量人工标注条件下的特征学习能力。",
                prerequisite_gap="需掌握对比学习与自监督损失设计",
                is_recommended=False,
            ),
            DirectionCard(
                id="dir-adp-5",
                title=f"{base_title} 跨领域迁移与泛化性验证",
                description="评估模型在不同分布测试集上的泛化表现。",
                prerequisite_gap="需熟悉域适应与迁移学习策略",
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
        llm_generator: OrchestratorLlmGenerator | None = None,
    ) -> None:
        self.guidance_service = guidance_service or ResearchConversationGuidanceService()
        self.conversation_service = conversation_service or ResearchConversationService()
        self.evaluation_service = evaluation_service or ReproductionEvaluationService()
        self.llm_generator = llm_generator or RuntimeOrchestratorLlmGenerator()

    @staticmethod
    def _collect_traceable_evidence_context(
        user_message: str,
        conv: ResearchConversationModel,
    ) -> list[str]:
        evidence = [user_message]
        for msg in (conv.messages_data or []):
            sender = msg.get("sender") or msg.get("role")
            if sender in ("user", "human"):
                content = msg.get("content")
                if content and isinstance(content, str):
                    evidence.append(content)
        return evidence

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
        now_dt = datetime.now(UTC)
        ctx = {
            "learned_content": request.learned_content,
            "learning_progress": request.learning_progress,
            "updated_at": now_dt.isoformat(),
        }
        state_model.learning_context = ctx
        db.commit()
        return LearningContextState(
            conversation_id=conversation_id,
            learned_content=request.learned_content,
            learning_progress=request.learning_progress,
            updated_at=now_dt,
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
        current_profile: LearnerProfileData | None = None
        current_version: int | None = None
        history: list[LearnerProfileVersion] = []

        for row in rows:
            p_data = row.profile_data or {}
            history_item = LearnerProfileVersion(
                version=row.version,
                profile_data=LearnerProfileData(**p_data),
                change_summary=row.change_summary,
                created_at=row.created_at,
                is_current=row.is_current,
            )
            history.append(history_item)
            if row.is_current:
                current_version = row.version
                current_profile = LearnerProfileData(
                    domain_familiarity=p_data.get("domain_familiarity"),
                    dev_experience=p_data.get("dev_experience"),
                    projects=p_data.get("projects"),
                    hardware=p_data.get("hardware"),
                    os=p_data.get("os"),
                    python_env=p_data.get("python_env"),
                    weekly_hours=p_data.get("weekly_hours"),
                    grade=p_data.get("grade"),
                    major=p_data.get("major"),
                )

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

        existing_profiles = (
            db.query(ResearchLearnerProfileModel)
            .filter(ResearchLearnerProfileModel.conversation_id == conversation_id)
            .order_by(ResearchLearnerProfileModel.version.desc())
            .all()
        )

        current_row = existing_profiles[0] if existing_profiles else None
        current_data = dict(current_row.profile_data or {}) if current_row else {}

        # Merge updates
        updates = request.model_dump(exclude_unset=True)
        has_change = False
        for k, v in updates.items():
            if v is not None and current_data.get(k) != v:
                current_data[k] = v
                has_change = True

        if has_change or not current_row:
            for p in existing_profiles:
                p.is_current = False

            next_version = (current_row.version + 1) if current_row else 1
            new_profile_row = ResearchLearnerProfileModel(
                conversation_id=conversation_id,
                version=next_version,
                is_current=True,
                profile_data=current_data,
                change_summary=f"更新了画像字段: {', '.join(updates.keys())}",
                created_at=datetime.now(UTC),
                owner_principal_id=conv.owner_principal_id,
            )
            db.add(new_profile_row)

            # Update subtasks in state
            state_model = db.get(ResearchOrchestratorStateModel, conversation_id)
            if state_model:
                subtasks = dict(state_model.subtasks or {})
                if current_data.get("hardware") or current_data.get("dev_experience"):
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

    def stream_message(
        self,
        conversation_id: str,
        request: SendOrchestratorMessageRequest,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
    ) -> Generator[str, None, None]:
        """Stream orchestrator thinking lifecycle events (thinking -> completed/failed)."""
        state_model = self.get_state_model(conversation_id, db, owned_ids=owned_ids)
        # P1: Persist thinking state in DB before yielding event: thinking
        state_model.last_status = "thinking"
        db.commit()
        db.refresh(state_model)

        thinking_payload = {
            "status": "thinking",
            "stage": state_model.current_stage,
            "message": "姜姜正在思考...",
        }
        yield f"event: thinking\ndata: {json.dumps(thinking_payload, ensure_ascii=False)}\n\n"

        outcome = self.process_message(conversation_id, request, db, owned_ids=owned_ids)
        if outcome.status == "completed":
            yield f"event: completed\ndata: {outcome.model_dump_json()}\n\n"
        else:
            yield f"event: failed\ndata: {outcome.model_dump_json()}\n\n"

    def process_message(
        self,
        conversation_id: str,
        request: SendOrchestratorMessageRequest,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
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

        # Step 1: Detect history inquiry (deterministic, no stage advancement)
        if is_history_inquiry(user_message):
            reply_content = self._handle_history_inquiry(conversation_id, state_model, db)
            return self._finalize_reply(
                conversation_id, state_model, user_message, reply_content, None, db
            )

        # Step 2: Detect direction change (deterministic, resets active workflow)
        if detect_direction_change_intent(user_message):
            state_model.current_stage = "research_need"
            dir_history = list(state_model.direction_history or [])
            dir_history.append({
                "direction": user_message,
                "timestamp": datetime.now(UTC).isoformat(),
            })
            state_model.direction_history = dir_history
            # Reset active workflow subtasks for new direction while keeping history
            subtasks = dict(state_model.subtasks or {})
            subtasks["need_defined"] = False
            subtasks["plan_generated"] = False
            subtasks["paper_selected"] = False
            subtasks["experiment_designed"] = False
            subtasks["results_analyzed"] = False
            state_model.subtasks = subtasks

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
            tool_material, is_empty = self._fetch_passive_tool_material(
                tool_name, conversation_id, db, owned_ids, user_message=user_message
            )
            prompt_data = self._build_passive_tool_prompt(
                tool_name, tool_material, is_empty, user_message
            )
            history_msgs = conv.messages_data or []
            outcome = self.llm_generator.generate(
                system_prompt=prompt_data["system_prompt"],
                user_prompt=prompt_data["user_prompt"],
                conversation_history=history_msgs,
                conversation_id=conversation_id,
            )
            # P0: Treat unavailable / failed equally - must not succeed
            if (
                outcome.status != "generated"
                or not outcome.reply_text
                or not outcome.reply_text.strip()
            ):
                err_msg = (
                    outcome.reason
                    or f"Model provider unavailable or failed for tool {tool_name}"
                )
                state_model.last_status = "failed"
                state_model.last_error = err_msg
                state_model.last_failed_user_message = user_message
                db.commit()
                return OrchestratorMessageResponse(
                    conversation_id=conversation_id,
                    status="failed",
                    reply_message=None,
                    state=self._model_to_state_response(state_model),
                    error=err_msg,
                )

            reply_content = outcome.reply_text.strip()
            evidence_ctx = self._collect_traceable_evidence_context(user_message, conv)
            valid, val_reason = validate_jiangjiang_output(
                reply_content,
                evidence_context=evidence_ctx,
                learning_record_mode=False,
            )
            if not valid:
                err_msg = f"Jiang Jiang output boundary validation failure: {val_reason}"
                state_model.last_status = "failed"
                state_model.last_error = err_msg
                state_model.last_failed_user_message = user_message
                db.commit()
                return OrchestratorMessageResponse(
                    conversation_id=conversation_id,
                    status="failed",
                    reply_message=None,
                    state=self._model_to_state_response(state_model),
                    error=err_msg,
                )

            # Passive tool calls do NOT advance stage
            return self._finalize_reply(
                conversation_id, state_model, user_message, reply_content, tool_name, db
            )

        # Step 4: Regular message flow & Four-Stage Progression
        current_stage = state_model.current_stage
        subtasks = dict(state_model.subtasks or {})
        completed_stages = list(state_model.completed_stages or [])
        is_confirmed = detect_confirmation_intent(user_message)

        # Build prompt from one of 8 templates with confirmed context
        prompt_data = self._select_prompt_template(
            conversation_id, current_stage, subtasks, user_message, is_confirmed, db, owned_ids
        )

        history_msgs = conv.messages_data or []
        outcome = self.llm_generator.generate(
            system_prompt=prompt_data["system_prompt"],
            user_prompt=prompt_data["user_prompt"],
            conversation_history=history_msgs,
            conversation_id=conversation_id,
        )

        # P0: Treat unavailable / failed equally - must not advance stage or subtasks!
        if (
            outcome.status != "generated"
            or not outcome.reply_text
            or not outcome.reply_text.strip()
        ):
            err_msg = outcome.reason or "Model provider unavailable or failed"
            state_model.last_status = "failed"
            state_model.last_error = err_msg
            state_model.last_failed_user_message = user_message
            db.commit()
            return OrchestratorMessageResponse(
                conversation_id=conversation_id,
                status="failed",
                reply_message=None,
                state=self._model_to_state_response(state_model),
                error=err_msg,
            )

        reply_content = outcome.reply_text.strip()
        template_name = prompt_data.get("template_name", "")
        if template_name in ("welcome_and_bridge", "need_clarification", "stage_transition"):
            # Deterministically ensure source_scope is the very first paragraph.
            # Do NOT use a conditional guard — even if the model self-inserted a scope phrase
            # somewhere in the middle, that does NOT protect the first paragraph.
            scope_prefix = get_source_scope_prefix(template_name)
            if not reply_content.startswith(scope_prefix):
                reply_content = f"{scope_prefix}\n\n{reply_content}"
        evidence_ctx = self._collect_traceable_evidence_context(user_message, conv)
        is_learning_mode = bool(prompt_data.get("is_learning_record_mode", False))
        valid, val_reason = validate_jiangjiang_output(
            reply_content,
            evidence_context=evidence_ctx,
            learning_record_mode=is_learning_mode,
        )
        if not valid:
            err_msg = f"Jiang Jiang output boundary validation failure: {val_reason}"
            state_model.last_status = "failed"
            state_model.last_error = err_msg
            state_model.last_failed_user_message = user_message
            db.commit()
            return OrchestratorMessageResponse(
                conversation_id=conversation_id,
                status="failed",
                reply_message=None,
                state=self._model_to_state_response(state_model),
                error=err_msg,
            )

        # ONLY when model output is successfully generated & validated: advance state machine
        if current_stage == "research_need":
            prior_need_defined = bool(subtasks.get("need_defined"))
            has_need = _has_defined_need(user_message, conv, subtasks)
            if has_need:
                subtasks["need_defined"] = True
                state_model.subtasks = subtasks

            # Must have prior verified need_defined plus explicit confirmation to advance
            if is_confirmed and prior_need_defined:
                state_model.current_stage = "research_plan"
                if "research_need" not in completed_stages:
                    completed_stages.append("research_need")
                state_model.completed_stages = completed_stages

        elif current_stage == "research_plan":
            profile_ready = subtasks.get("profile_ready")
            plan_gen = subtasks.get("plan_generated")
            if is_confirmed and profile_ready and plan_gen:
                state_model.current_stage = "research_execution"
                if "research_plan" not in completed_stages:
                    completed_stages.append("research_plan")
                state_model.completed_stages = completed_stages

        elif current_stage == "research_execution":
            paper_ready = subtasks.get("paper_selected")
            exp_ready = subtasks.get("experiment_designed")
            if is_confirmed and (paper_ready or exp_ready):
                state_model.current_stage = "research_analysis"
                if "research_execution" not in completed_stages:
                    completed_stages.append("research_execution")
                state_model.completed_stages = completed_stages

        elif current_stage == "research_analysis":
            if _has_traceable_experiment_results(user_message):
                subtasks["results_analyzed"] = True
                state_model.subtasks = subtasks

        return self._finalize_reply(
            conversation_id, state_model, user_message, reply_content, None, db
        )

    def retry_last_message(
        self,
        conversation_id: str,
        db: Session,
        *,
        owned_ids: list[str] | None = None,
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
        )

    def _select_prompt_template(
        self,
        conversation_id: str,
        current_stage: str,
        subtasks: dict[str, Any],
        user_message: str,
        is_confirmed: bool,
        db: Session,
        owned_ids: list[str] | None,
    ) -> dict[str, str]:
        """Select and assemble one of the 8 Prompt templates with confirmed context."""
        learning_ctx = self.get_learning_context(conversation_id, db, owned_ids=owned_ids)
        cards_resp = self.get_direction_cards(conversation_id, db, owned_ids=owned_ids)
        profiles_resp = self.get_learner_profiles(conversation_id, db, owned_ids=owned_ids)
        papers_resp = self.get_papers(conversation_id, db, owned_ids=owned_ids)

        if current_stage == "research_need":
            if is_confirmed and subtasks.get("need_defined"):
                tmpl = build_stage_transition_prompt(
                    from_stage="research_need",
                    to_stage="research_plan",
                    completed_subtasks=["明确核心研究主题与研究问题"],
                    next_goals="完善设备与时间画像，生成小目标执行计划",
                )
            elif not subtasks.get("need_defined") and (
                not user_message or is_opening_greeting_intent(user_message)
            ):
                tmpl = build_welcome_prompt(
                    learning_context=learning_ctx,
                    direction_cards=cards_resp.cards,
                )
            else:
                tmpl = build_need_clarification_prompt(
                    selected_direction=user_message,
                    user_message=user_message,
                    learned_content=learning_ctx.learned_content,
                )

        elif current_stage == "research_plan":
            if is_confirmed and subtasks.get("profile_ready") and subtasks.get("plan_generated"):
                tmpl = build_stage_transition_prompt(
                    from_stage="research_plan",
                    to_stage="research_execution",
                    completed_subtasks=["学习者画像已建立", "小目标执行计划已生成"],
                    next_goals="文献精准检索、论文精读介绍与实验方案设计",
                )
            else:
                prof = profiles_resp.current_profile or LearnerProfileData(version=1)
                tmpl = build_profile_and_plan_prompt(
                    research_goal=user_message or "研究课题规划",
                    profile=prof,
                    plan_candidate=None,
                )

        elif current_stage == "research_execution":
            paper_or_exp = subtasks.get("paper_selected") or subtasks.get("experiment_designed")
            if is_confirmed and paper_or_exp:
                tmpl = build_stage_transition_prompt(
                    from_stage="research_execution",
                    to_stage="research_analysis",
                    completed_subtasks=["选定核心论文或完成实验方案设计"],
                    next_goals="运行实验指标记录，进行客观归因与对比分析",
                )
            elif any(k in user_message for k in ["检索", "找论文", "搜索", "关键词"]):
                tmpl = build_search_guidance_prompt(
                    research_goal=user_message,
                    candidate_queries=[user_message],
                    sources=["OpenAlex", "Crossref", "arXiv"],
                )
            elif papers_resp.current_paper is not None:
                tmpl = build_paper_intro_prompt(
                    paper=papers_resp.current_paper,
                    profile=profiles_resp.current_profile,
                    research_goal="论文精读与复现",
                )
            else:
                prof = profiles_resp.current_profile or LearnerProfileData(version=1)
                task_type = infer_task_type(
                    topic=user_message,
                    research_questions=[user_message],
                )
                standard_metrics = [
                    m.name for m in STANDARD_METRICS if task_type in m.applies_to_task_type
                ]
                if not standard_metrics:
                    standard_metrics = ["待核验指标 (to_verify)"]
                tmpl = build_experiment_design_prompt(
                    paper=papers_resp.current_paper,
                    profile=prof,
                    standard_metrics=standard_metrics,
                )

        else:  # research_analysis
            hw = profiles_resp.current_profile.hardware if profiles_resp.current_profile else None
            tmpl = build_result_analysis_prompt(
                user_results=user_message,
                baseline_metrics=None,
                hardware_info=hw,
            )

        system_str = (
            f"{tmpl['system']}\n\n"
            f"【当前任务】\n{tmpl['task']}\n\n"
            f"【规则与指引】\n{tmpl['rules']}"
        )
        user_str = f"{tmpl['context']}\n\n【当前用户输入】\n{user_message}"
        template_name = tmpl.get("template_name", "")
        # Only the welcome template consumes learning-context records.  Direction
        # clarification must rely on the user's current message, avoiding mastery
        # or capability inferences from a stored learning snapshot.
        has_learning_record_input = bool(
            learning_ctx
            and (
                learning_ctx.learned_content
                or learning_ctx.learning_progress
            )
        )
        is_learning_record_mode = (
            template_name == "welcome_and_bridge" and has_learning_record_input
        )
        return {
            "system_prompt": system_str,
            "user_prompt": user_str,
            "template_name": template_name,
            "is_learning_record_mode": is_learning_record_mode,
        }

    def _fetch_passive_tool_material(
        self,
        tool_name: str,
        conversation_id: str,
        db: Session,
        owned_ids: list[str] | None,
        user_message: str = "",
    ) -> tuple[str, bool]:
        """Call existing §2 passive tool and return structured material and empty state flag."""
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
            is_empty = not briefing.has_learning_context and not topic and bundles_count == 0
            if is_empty:
                material = (
                    "【阶段进展总结（工具真实输出）】\n"
                    "- 学习快照状态：暂未关联前置学习快照\n"
                    "- 课题背景：暂未明确预设主题\n"
                    "- 文献库与证据包：已保存文献包 0 个\n"
                    "- 复现路径状态：未开始\n"
                    "- 核心提示：当前处于起步探索阶段，缺少前置输入事实，需先明确研究主题。"
                )
            else:
                material = (
                    "【阶段进展总结（工具真实输出）】\n"
                    f"- 课题/背景：{topic or '暂无预设主题'}\n"
                    f"- 学习摘要：{digest or '已确认基本学习概念'}\n"
                    f"- 已保存文献包数量：{bundles_count} 个\n"
                    f"- 复现路径状态：{briefing.reproduction_entry.pipeline_status or '未开始'}"
                )
            return material, is_empty

        elif tool_name == "study-recommendations":
            is_confirmed = detect_confirmation_intent(user_message)
            try:
                rec_resp = self.guidance_service.study_recommendations(
                    conversation_id,
                    StudyRecommendationRequest(user_confirmed=is_confirmed),
                    db,
                    owned_ids=owned_ids,
                )
                if not rec_resp.recommendations:
                    material = (
                        "【补学建议（工具真实输出）】\n"
                        "- 知识点推荐：当前已确认画像与计划下暂无明显知识盲区推荐项。"
                    )
                    return material, True
                items_str = "\n".join(
                    f"- 【{r.knowledge_point}】（掌握状态：{r.mastery_status}）：{r.reason}"
                    for r in rec_resp.recommendations
                )
                material = (
                    "【补学建议（工具真实输出）】\n"
                    f"前置知识点清单：\n{items_str}"
                )
                return material, False
            except StudyRecommendationsNotConfirmedError:
                return (
                    "【补学建议（工具真实输出）】\n"
                    "- 状态：前置条件不足（需要用户明确确认后才能生成补学建议）。",
                    True,
                )
            except Exception as err:
                return (
                    f"【补学建议（工具真实输出）】\n"
                    f"- 状态：画像未就绪（{err}），暂无法提取针对性方法知识点。",
                    True,
                )

        elif tool_name == "topic-difficulty-analysis":
            try:
                analysis = self.conversation_service.generate_topic_difficulty_analysis(
                    conversation_id, db
                )
                items_by_area: dict[str, list[str]] = {}
                for item in analysis.items:
                    items_by_area.setdefault(item.area, []).append(
                        f"- [{item.classification}] {item.content} (依据: {item.basis})"
                    )
                sections_text = "\n\n".join(
                    f"### {area}\n" + "\n".join(lines)
                    for area, lines in items_by_area.items()
                )
                material = (
                    "【课题难点分析（工具真实输出）】\n"
                    f"- 核心判断：{analysis.core_judgment}\n"
                    f"- 难点细分：\n{sections_text}\n"
                    f"- 下一步建议：{analysis.next_action}\n"
                    f"- 出处说明：{analysis.provenance_note}"
                )
                return material, False
            except Exception as err:
                return (
                    f"【课题难点分析（工具真实输出）】\n"
                    f"- 状态：暂无法生成难点分析（原因：{err}）。需先明确研究主题与画像。",
                    True,
                )

        elif tool_name == "experiment-design":
            try:
                design = self.conversation_service.generate_experiment_design(
                    conversation_id, db
                )
                if design is None:
                    return (
                        "【实验方案设计（工具真实输出）】\n"
                        "- 状态：前置条件不足，尚未达到实验方案生成条件，需先完善研究画像与计划。",
                        True,
                    )
                baselines_text = (
                    "\n".join(f"- {b.content}" for b in design.baselines)
                    or "- 暂无预设 Baseline"
                )
                metrics_text = "\n".join(
                    f"- **{m.name}**：{m.definition} ({'待验证' if m.to_verify else '标准指标'})"
                    for m in design.metric_specs
                ) or "- 暂无指标定义"
                steps_text = (
                    "\n".join(f"{i+1}. {s.content}" for i, s in enumerate(design.steps))
                    or "- 暂无实验步骤"
                )
                resources_text = (
                    "\n".join(f"- {r.content}" for r in design.resources)
                    or "- 暂无资源要求"
                )
                material = (
                    "【实验方案设计（工具真实输出）】\n"
                    f"- 核心假设：{design.hypothesis.content}\n"
                    f"- 对比基线：\n{baselines_text}\n"
                    f"- 评测指标：\n{metrics_text}\n"
                    f"- 实验步骤：\n{steps_text}\n"
                    f"- 计算资源需求：\n{resources_text}"
                )
                return material, False
            except Exception as err:
                return (
                    f"【实验方案设计（工具真实输出）】\n"
                    f"- 状态：暂无法生成实验方案（原因：{err}）。需先明确研究计划与选定核心论文。",
                    True,
                )

        elif tool_name == "paper-blueprint":
            try:
                blueprint = self.conversation_service.generate_paper_blueprint(
                    conversation_id, db
                )
                sections_text = "\n\n".join(
                    f"### {sec.title}\n- 写作要点：{sec.guidance}\n"
                    f"- 关联证据引用：{len(sec.evidence_references)} 条"
                    for sec in blueprint.sections
                )
                material = (
                    "【论文大纲蓝图（工具真实输出）】\n"
                    f"- 论文标题构想：{blueprint.title}\n"
                    f"- 五段结构大纲：\n{sections_text}\n"
                    f"- 出处说明：{blueprint.provenance_note}"
                )
                return material, False
            except Exception as err:
                return (
                    f"【论文大纲蓝图（工具真实输出）】\n"
                    f"- 状态：暂无法生成论文大纲（原因：{err}）。需先完善研究计划或保存文献证据。",
                    True,
                )

        elif tool_name == "reproduction-evaluations":
            try:
                eval_detail = self.evaluation_service.create(conversation_id, db)
                if eval_detail.pipeline_contract_status != "available":
                    return (
                        "【复现准备度六维度评估（工具真实输出）】\n"
                        "- 状态：尚未建立前置复现 Pipeline 或生成实验设计方案。\n"
                        "- 说明：缺少实验基线与数据条件，当前暂无法得出准备度良好结论，"
                        "需先选定论文或完成实验设计。",
                        True,
                    )
                dims_text = "\n".join(
                    f"- **{dim.dimension}**：{dim.status} (得分: {dim.score})"
                    for dim in eval_detail.dimension_results
                )
                tasks_text = "\n".join(
                    f"{i+1}. [{t.priority}] {t.title}：{t.description}"
                    for i, t in enumerate(eval_detail.tasks[:3])
                )
                material = (
                    "【复现准备度六维度评估（工具真实输出）】\n"
                    f"- 六维度评估结果：\n{dims_text}\n"
                    f"- 待改进任务 (Top 3)：\n{tasks_text or '- 暂无待改进任务'}"
                )
                return material, False
            except Exception as err:
                return (
                    "【复现准备度六维度评估（工具真实输出）】\n"
                    f"- 状态：暂无法生成复现评估（原因：{err}）。"
                    "需先选定核心论文或完成实验方案设计。",
                    True,
                )

        return f"【工具输出】已整理工具 {tool_name} 的相关信息。", False

    def _build_passive_tool_prompt(
        self,
        tool_name: str,
        tool_material: str,
        is_empty_state: bool,
        user_message: str,
    ) -> dict[str, str]:
        """Build strict prompt for Jiang Jiang to paraphrase real passive tool return data."""
        tool_display_name = {
            "stage-briefing": "阶段进展总结",
            "study-recommendations": "补学建议",
            "topic-difficulty-analysis": "难点分析",
            "experiment-design": "实验方案设计",
            "paper-blueprint": "论文大纲蓝图",
            "reproduction-evaluations": "复现准备度评估",
        }.get(tool_name, tool_name)

        system_prompt = (
            f"{JIANGJIANG_SYSTEM_PERSONA}\n\n"
            f"【被动工具复述任务与边界规则】\n"
            f"1. 你正在向同学解读【{tool_display_name}】工具的真实执行结果；\n"
            f"2. 必须严格以给定的【工具真实输出】为客观依据进行自然语言复述，"
            f"严禁捏造未经工具核实的指标、硬件配置或结论；\n"
            f"3. 若工具输出为前置条件不足或空态（is_empty_state={is_empty_state}），"
            f"必须诚实向同学说明当前缺少哪些前置事实或条件，严禁声称“准备度良好”或假造实验进展；\n"
            f"4. 严禁使用 Emoji 表情（必须使用颜文字如 (＾▽＾)、(•̀ᴗ•́)و ̑̑ 等）；"
            f"严禁假造百分比成功率。\n"
        )
        user_prompt = (
            f"{tool_material}\n\n"
            f"【用户消息】\n{user_message}"
        )
        return {"system_prompt": system_prompt, "user_prompt": user_prompt}

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
        history_str = (
            "、".join(f"「{name}」" for name in completed_names)
            if completed_names
            else "尚无已完成的前置阶段"
        )
        subtasks = state_model.subtasks or {}
        done_subs = [k for k, v in subtasks.items() if v]
        done_str = ", ".join(done_subs) if done_subs else "正在收集基础条件"

        return (
            f"# 历史讨论与进度回顾 (•̀ᴗ•́)و ̑̑\n\n"
            f"### 当前所处阶段\n- 我们当前正在**「{current_stage_name}」**推进。\n\n"
            f"### 已完成阶段\n- {history_str}。\n\n"
            f"### 已达成的子目标\n- 已确认事项：{done_str}。\n\n"
            f"所有历史记录均已完好保存，你可以随时继续当前阶段的讨论！"
        )

    def _finalize_reply(
        self,
        conversation_id: str,
        state_model: ResearchOrchestratorStateModel,
        user_message: str,
        reply_content: str,
        triggered_tool: str | None,
        db: Session,
    ) -> OrchestratorMessageResponse:
        conv = db.get(ResearchConversationModel, conversation_id)
        if conv is None:
            raise ConversationNotFoundError(conversation_id)

        now_dt = datetime.now(UTC)
        msgs = list(conv.messages_data or [])

        # User message
        msgs.append({
            "id": str(uuid.uuid4()),
            "role": "user",
            "content": user_message,
            "created_at": now_dt.isoformat(),
        })

        # Assistant message
        assistant_msg_id = str(uuid.uuid4())
        msgs.append({
            "id": assistant_msg_id,
            "role": "assistant",
            "content": reply_content,
            "triggered_tool": triggered_tool,
            "stage_at_time": state_model.current_stage,
            "created_at": now_dt.isoformat(),
        })
        conv.messages_data = msgs

        # Clear error state on success
        state_model.last_status = "completed"
        state_model.last_error = None
        state_model.last_failed_user_message = None

        db.commit()
        db.refresh(state_model)

        reply_msg = OrchestratorMessageReply(
            id=assistant_msg_id,
            sender="assistant",
            content=reply_content,
            passive_tool_called=triggered_tool,
            created_at=now_dt,
        )

        return OrchestratorMessageResponse(
            conversation_id=conversation_id,
            status="completed",
            reply_message=reply_msg,
            state=self._model_to_state_response(state_model),
            error=None,
        )

    def _model_to_state_response(
        self,
        model: ResearchOrchestratorStateModel,
    ) -> OrchestratorStateResponse:
        dir_history = [
            DirectionHistoryEntry(
                direction=item["direction"],
                timestamp=datetime.fromisoformat(item["timestamp"]),
            )
            for item in (model.direction_history or [])
        ]
        subtasks_data = model.subtasks or {}
        subtasks_obj = OrchestratorSubtasks(
            need_defined=bool(subtasks_data.get("need_defined")),
            profile_ready=bool(subtasks_data.get("profile_ready")),
            plan_generated=bool(subtasks_data.get("plan_generated")),
            paper_selected=bool(subtasks_data.get("paper_selected")),
            experiment_designed=bool(subtasks_data.get("experiment_designed")),
            results_analyzed=bool(subtasks_data.get("results_analyzed")),
        )
        return OrchestratorStateResponse(
            conversation_id=model.conversation_id,
            current_stage=model.current_stage,  # type: ignore
            completed_stages=model.completed_stages or [],
            subtasks=subtasks_obj,
            direction_history=dir_history,
            last_status=model.last_status or "completed",  # type: ignore
            last_error=model.last_error,
        )
