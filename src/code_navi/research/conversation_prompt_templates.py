"""Eight Prompt templates, Jiang Jiang system persona, and output validation."""

from __future__ import annotations

import re
from typing import Any

from .conversation_orchestrator_schemas import (
    STAGE_DISPLAY_NAMES,
    CurrentPaperCard,
    DirectionCard,
    LearnerProfileData,
    LearningContextState,
    ResearchStage,
)

JIANGJIANG_SYSTEM_PERSONA = """你是由 CODE-NAVI 打造的科研 Agent「姜姜」。
你的职责是在科研全流程中陪伴、引导学生完成从需求探索到结果分析的完整科研闭环。

【语气与人设】
1. 活泼、亲切、专业、鼓励式引导；
2. 可以少量使用可爱/亲切的颜文字（如 (＾▽＾)、(｡･ω･｡)、(•̀ᴗ•́)و ̑̑ 等）；
3. 严格禁止使用 Emoji 图标（如 😊、🚀、🔥、💡 等一律禁用）；
4. 开场、阶段切换或完成总结使用大字号清晰区块；
   长回复结构化使用小标题、短段落、任务列表、时间安排，避免密密麻麻大段文字；
5. 禁用「核心判断」「当前聚焦于」「AI 分析表明」等空泛学术装饰标签。

【事实与红线约束】
1. 严禁捏造或猜测未确认的事实（包括用户设备、硬件、代码、实验数据、论文内容）；
2. 严禁输出虚假的完成百分比（如“完成度 85%”）、虚假评分或过度宣称（如“复现成功”）；
3. 严禁未获用户明确确认即自动检索、下载全文或执行代码；
4. 严格区分 fact（用户提供的事实）、inference（基于证据的推断）与 to_verify（待验证项），
   严禁自造 fact；
5. evidence_linked 仅表示存在关联的实验或记录，绝不等于复现成功；
6. 遇到信息不足时，主动亲切地向用户追问，不自作主张做出假设。
"""

_EMOJI_PATTERN = re.compile(
    r"[\U00010000-\U0010ffff"  # Supplemental Multilingual Plane (includes most modern emojis)
    r"\u2600-\u27bf"           # Miscellaneous Symbols & Dingbats
    r"\u2300-\u23ff"           # Miscellaneous Technical
    r"\u2b50\u2b55\u200d\ufe0f]"
)

_FORBIDDEN_PHRASES = [
    "核心判断",
    "当前聚焦于",
    "完成百分比",
    "完成度 100%",
    "完成度100%",
]

_PUNCTUATION_DELIMITERS = set("。！？!?；;，,\n\r\t|｜")
_TRANSITION_WORDS = ["但是", "然而", "不过", "反而", "可是", "并且", "但", "却", "且"]

_REPRODUCTION_CLAIM_PATTERN = re.compile(
    r"(?:"
    # 1. Rate and percentage claims (e.g. 复现率, 复现成功率, 实验完成率, reproduction success rate)
    r"reproduction\s+success\s+rate|"
    r"(?:复现|重现|再现)(?:的)?(?:成功)?率|"
    r"(?:实验|复现|重现|再现|复刻)(?:的)?完成率|"
    # 2. 跑通实验
    r"(?:已(?:经)?)?(?:成功)?跑通(?:了)?(?:论文)?(?:的)?(?:复现|重现|再现|复刻)?(?:实验)?|"
    # 3. 完成复现 / 复现完成 / 复现验证完成 / 复现实验验证完成
    r"完成(?:了|已经|已)?(?:复现|重现|再现|复刻)|"
    r"(?:复现|重现|再现|复刻)(?:实验)?(?:验证)?(?:已经完成|已完成|完成了|完成)|"
    r"(?:实验)?(?:验证)(?:已经完成|已完成|完成了|完成)|"
    # 4. 复现可靠 / 确认复现 / 复现成立 / 推进下一阶段
    r"(?:确认|判定|断定|证明)(?:了)?(?:复现|重现|再现|复刻)|"
    r"(?:复现|重现|再现|复刻)(?:可靠|成立|有效|闭环|达标|通过|成功)|"
    r"(?:复现|重现|再现|复刻)(?:已经)?可(?:以)?(?:推进|进入)(?:到)?(?:下一阶段|下个阶段)|"
    r"可以(?:推进|进入)(?:到)?(?:下一阶段|下个阶段)|"
    # 5. 结果/结论 与 论文/基线 吻合/一致/达到基线/超过基线
    r"(?:实验|复现|重现|再现)?结果(?:和|与|跟)(?:原)?论文(?:结论|实验|结果|描述)?(?:完全)?(?:吻合|一致|相同)|"
    r"与(?:原)?论文(?:中的)?(?:实验)?(?:结果|结论)(?:完全)?(?:吻合|一致|相同)|"
    r"(?:指标|结果)(?:已|已经)?达到(?:论文)?基线|"
    r"(?:指标|结果)超过(?:论文)?基线|"
    # 6. Adverb + verb: 被? + 已/已经 + 成功/稳定 + 地? + 复现/重现/再现/复刻
    r"(?:被)?(?:已(?:经)?)?(?:成功|稳定)(?:地)?(?:复现|重现|再现|复刻)|"
    # 7. 已经/已 + 复现/重现/再现/复刻
    r"(?:已经|已)(?:复现|重现|再现|复刻)|"
    # 8. 复现了/重现了/再现了/复刻了
    r"(?:复现|重现|再现|复刻)了|"
    # 9. 重现/复刻/复现/再现 + 论文(中的)?(实验)?结果
    r"(?:复现|重现|再现|复刻)论文(?:中的)?(?:实验)?结果"
    r")",
    re.IGNORECASE,
)

_NEGATION_PREFIX_PATTERN = re.compile(
    r"(?:"
    # Inspection / to_verify phrases
    r"需核验|待核验|需确认|待确认|核验|查验|需明确|需界定|"
    # Negations with optional leading adverbs (e.g. 也不能, 并不能, 还不能)
    r"(?:也|并|仍|还|暂|暂时|目前|均|都)?"
    r"(?:"
    r"尚不足以|难以|无法|切勿|切忌|不可|未曾|并未|未有|尚未|未能|未形成|"
    r"不能|不应|无需|严禁|不得|禁止|避免|不要|难言|难下|"
    r"不代表|不等于|不等同于|不构成|并非|不是|不视为|不算作|不算|≠|!="
    r")"
    r")"
    r"(?:[“\"'「『（(【\[\s]|把|将|因为|因|由于|根据|依据|凭借|单凭|仅凭|由此|因此|轻易|直接|盲目|贸然|简单|提前|就|而|去|来|前述|目前|当前|已有|现有|这些|上述|结果|指标|数据|"
    r"(?:轻易|直接|盲目|贸然)?(?:下|声称|断言|判定|认为|得出|下达|形成|确认|视作|视为|说明|定义|宣称|断定|判为)){0,25}"
    r"[“\"'「『（(【\[\s]{0,2}$"
)

_CONDITION_PREFIX_PATTERN = re.compile(
    r"(?:即使|即便|哪怕|假使|假设|如果未来|如果|若)"
    r"(?:[“\"'「『（(【\[\s]|(?:未来|后续|最终)?(?:形成|达成|达到|实现|得出|出现|能够)?){0,6}"
    r"[“\"'「『（(【\[\s]{0,2}$"
)

_SUFFIX_BOUNDARY_PATTERN = re.compile(
    r"^[”\"'」』）)】\]\s]*(?:"
    r"不代表|不等于|不等同于|不构成|并不|并非|不是|不意味着|"
    r"尚待|未确认|未形成|存在疑问|难以确认|不成立|的结论尚不能下|的结论仍不能下|"
    r"当作结论|作为结论|等当作|等作为|"
    r"作为(?:实验)?过程(?:指标|参数|数据)|"
    r"(?:的)?(?:计算口径|计算方式|计算方法|口径|定义|统计方式)(?:[，,\s]*(?:仍待|尚待|待确认|待核验|需确认|需核验|存在疑问|未确认))?"
    r")"
)


def _split_into_clauses(text: str) -> list[tuple[int, int, str]]:
    """Split text into local semantic clauses based on punctuation and transition words."""
    split_indices = {0, len(text)}

    for idx, ch in enumerate(text):
        if ch in _PUNCTUATION_DELIMITERS:
            split_indices.add(idx)
            split_indices.add(idx + 1)

    for word in _TRANSITION_WORDS:
        start = 0
        while True:
            pos = text.find(word, start)
            if pos == -1:
                break
            split_indices.add(pos)
            split_indices.add(pos + len(word))
            start = pos + len(word)

    sorted_splits = sorted(split_indices)
    clauses: list[tuple[int, int, str]] = []
    for i in range(len(sorted_splits) - 1):
        s = sorted_splits[i]
        e = sorted_splits[i + 1]
        chunk = text[s:e].strip()
        if (
            chunk
            and not all(c in _PUNCTUATION_DELIMITERS for c in chunk)
            and chunk not in _TRANSITION_WORDS
        ):
            clauses.append((s, e, text[s:e]))

    return clauses


def _contains_ungrounded_reproduction_success_claim(text: str) -> bool:
    """Check if text contains ungrounded affirmative reproduction success claims.

    1. Splits text into isolated local semantic clauses.
    2. Evaluates claims against clause or local negation/condition/suffix boundaries.
    3. Prevents cross-clause negation leaks.
    """
    clauses = _split_into_clauses(text)
    if not clauses:
        clauses = [(0, len(text), text)]

    for _, _, clause_str in clauses:
        matches = list(_REPRODUCTION_CLAIM_PATTERN.finditer(clause_str))
        if not matches:
            continue

        first_match = matches[0]
        clause_prefix = clause_str[:first_match.start()]

        # Clause-level prefix boundary
        if bool(
            _NEGATION_PREFIX_PATTERN.search(clause_prefix)
            or _CONDITION_PREFIX_PATTERN.search(clause_prefix)
        ):
            continue

        # Check each match individually within the clause
        has_unbounded_claim = False
        for m in matches:
            local_prefix = clause_str[:m.start()]
            prefix_boundary = bool(
                _NEGATION_PREFIX_PATTERN.search(local_prefix)
                or _CONDITION_PREFIX_PATTERN.search(local_prefix)
            )
            if prefix_boundary:
                continue

            local_suffix = clause_str[m.end():]
            suffix_boundary = bool(_SUFFIX_BOUNDARY_PATTERN.search(local_suffix))
            if suffix_boundary:
                continue

            has_unbounded_claim = True
            break

        if has_unbounded_claim:
            return True

    return False


def validate_jiangjiang_output(text: str) -> tuple[bool, str | None]:
    """Validate model output against persona rules (no emoji/forbidden phrase/false claims)."""
    if _EMOJI_PATTERN.search(text):
        return False, "Output contains forbidden emoji characters."
    for phrase in _FORBIDDEN_PHRASES:
        if phrase in text:
            return False, f"Output contains forbidden phrase or unproven claim: {phrase}"
    if _contains_ungrounded_reproduction_success_claim(text):
        return False, "Output contains ungrounded affirmative reproduction success claim: 复现成功"
    return True, None


def build_welcome_prompt(
    learning_context: LearningContextState | None,
    direction_cards: list[DirectionCard],
    extra_note: str | None = None,
) -> dict[str, Any]:
    """Template 1: Welcome and Learning-Research Bridge (欢迎与衔接)."""
    learned_str = (
        learning_context.learned_content
        if learning_context and learning_context.learned_content
        else "暂无学习端输入（空态）"
    )
    progress_str = (
        learning_context.learning_progress
        if learning_context and learning_context.learning_progress
        else "暂无学习进度"
    )
    cards_str = "\n".join(
        f"- 【{card.title}】：{card.description}"
        + (f"（前置知识缺口提示：{card.prerequisite_gap}）" if card.prerequisite_gap else "")
        for card in direction_cards
    )
    context = (
        f"【学习端输入】\n"
        f"已学内容：{learned_str}\n"
        f"学习进度：{progress_str}\n\n"
        f"【基于学习内容动态生成的推荐研究方向】\n{cards_str}\n"
    )
    if extra_note:
        context += f"\n补充背景：{extra_note}\n"

    rules = (
        "1. 热情欢迎同学来到科研工作台，介绍姜姜可以提供的科研协助；\n"
        "2. 结合同学之前在学习端学到的知识（若有），自然桥接到科研方向探索；\n"
        "3. 向同学清晰展示上方 5 个方向卡片，并鼓励同学选择一个感兴趣的方向，"
        "或者自由输入自己想做的其他方向；\n"
        "4. 禁止把学习信息夸大为研究结论；严禁使用 Emoji。\n"
    )
    return {
        "template_name": "welcome_and_bridge",
        "system": JIANGJIANG_SYSTEM_PERSONA,
        "task": "欢迎同学并介绍研究方向（欢迎与衔接）",
        "context": context,
        "rules": rules,
    }


def build_need_clarification_prompt(
    selected_direction: str | None,
    user_message: str,
    learned_content: str | None = None,
    extra_context: str | None = None,
) -> dict[str, Any]:
    """Template 2: Need Clarification (需求澄清)."""
    context = (
        f"【已确认方向/用户输入】\n"
        f"方向/选定主题：{selected_direction or '用户自由输入'}\n"
        f"用户最新消息：{user_message}\n"
        f"前置学习背景：{learned_content or '无'}\n"
    )
    if extra_context:
        context += f"其他上下文：{extra_context}\n"

    rules = (
        "1. 梳理并明确具体研究问题与需求核心；\n"
        "2. 若用户选择的方向与前置知识跨度较大，温馨说明前置知识缺口并给出补学建议，"
        "但尊重用户的探索意愿，不阻止；\n"
        "3. 追问 1~2 个关键问题以收敛研究范围；禁止在信息模糊时盲目宣称需求已完成；\n"
        "4. 严禁使用 Emoji。\n"
    )
    return {
        "template_name": "need_clarification",
        "system": JIANGJIANG_SYSTEM_PERSONA,
        "task": "需求澄清与前置缺口梳理（需求澄清）",
        "context": context,
        "rules": rules,
    }


def build_profile_and_plan_prompt(
    research_goal: str,
    profile: LearnerProfileData,
    plan_candidate: str | None = None,
) -> dict[str, Any]:
    """Template 3: Profile & Plan (画像与计划)."""
    profile_lines = []
    if profile.hardware:
        profile_lines.append(f"- 设备与显存：{profile.hardware}")
    if profile.weekly_hours:
        profile_lines.append(f"- 每周可投入时间：{profile.weekly_hours}")
    if profile.python_env:
        profile_lines.append(f"- Python/框架环境：{profile.python_env}")
    if profile.dev_experience:
        profile_lines.append(f"- 开发经验：{profile.dev_experience}")
    if profile.grade or profile.major:
        profile_lines.append(f"- 年级专业：{profile.grade or ''} {profile.major or ''}")
    profile_str = "\n".join(profile_lines) if profile_lines else "画像信息收集中"

    context = (
        f"【研究目标】\n{research_goal}\n\n"
        f"【学生客观条件（画像）】\n{profile_str}\n"
    )
    if plan_candidate:
        context += f"\n【候选/初拟计划】\n{plan_candidate}\n"

    rules = (
        "1. 结合学生实际的硬件、时间和经验，制定务实、可落地的小目标与总体执行计划；\n"
        "2. 若设备显存受限（如 ≤8GB），主动提出缩小 batch size、使用轻量数据集或租用算力；\n"
        "3. 严禁忽略硬件限制生成需要海量算力的方案；严禁编造虚假实验周期；\n"
        "4. 严禁使用 Emoji。\n"
    )
    return {
        "template_name": "profile_and_plan",
        "system": JIANGJIANG_SYSTEM_PERSONA,
        "task": "结合画像生成总体计划与小目标（画像与计划）",
        "context": context,
        "rules": rules,
    }


VALID_SEARCH_SOURCES: list[str] = ["OpenAlex", "Crossref", "arXiv"]


def build_search_guidance_prompt(
    research_goal: str,
    candidate_queries: list[str],
    sources: list[str] | None = None,
) -> dict[str, Any]:
    """Template 4: Search Guidance (检索引导). Sources restricted to OpenAlex, Crossref, arXiv."""
    valid_sources = [
        s for s in (sources or VALID_SEARCH_SOURCES) if s in VALID_SEARCH_SOURCES
    ] or list(VALID_SEARCH_SOURCES)
    queries_str = "\n".join(f"- `{q}`" for q in candidate_queries)
    sources_str = ", ".join(valid_sources)
    context = (
        f"【研究目标】\n{research_goal}\n\n"
        f"【建议检索词】\n{queries_str}\n\n"
        f"【支持学术数据源】\n{sources_str}\n"
    )
    rules = (
        "1. 向同学介绍推荐的学术检索词与检索源覆盖范围；\n"
        "2. 询问同学是否确认使用该检索词或希望调整优化；\n"
        "3. 明确告知：只有在同学确认后，系统才会正式启动学术文献检索；\n"
        "4. 严禁未确认即直接假造检索结果或自动下载全文；严禁使用 Emoji。\n"
    )
    return {
        "template_name": "search_guidance",
        "system": JIANGJIANG_SYSTEM_PERSONA,
        "task": "文献检索词建议与确认引导（检索引导）",
        "context": context,
        "rules": rules,
    }


def build_paper_intro_prompt(
    paper: CurrentPaperCard,
    profile: LearnerProfileData | None = None,
    research_goal: str | None = None,
) -> dict[str, Any]:
    """Template 5: Paper Introduction (论文介绍)."""
    abstract = paper.metadata_snapshot.get("abstract", "（暂无公开摘要）")
    context = (
        f"【当前选定论文】\n"
        f"标题：{paper.title}\n"
        f"链接/DOI：{paper.paper_url}\n"
        f"摘要材料：{abstract}\n\n"
        f"【用户研究目标】\n{research_goal or '未指定'}\n"
    )
    if profile and profile.hardware:
        context += f"用户设备条件：{profile.hardware}\n"

    rules = (
        "1. 严格按照五步桥梁结构介绍论文：\n"
        "   ① 研究问题：论文试图解决什么核心问题；\n"
        "   ② 核心创新点：论文提出了什么新思路/新结构；\n"
        "   ③ 核心方法：具体算法设计与技术要点（公式使用标准 LaTeX 书写）；\n"
        "   ④ 与用户目标的关系：这篇论文如何助力用户的研究需求；\n"
        "   ⑤ 复现难点与避坑提示：基于用户硬件与经验可能遇到的挑战。\n"
        "2. 严禁臆测论文未提供的内容；公式必须规范；严禁使用 Emoji。\n"
    )
    return {
        "template_name": "paper_intro",
        "system": JIANGJIANG_SYSTEM_PERSONA,
        "task": "精读式结构化论文介绍（论文介绍）",
        "context": context,
        "rules": rules,
    }


def build_experiment_design_prompt(
    paper: CurrentPaperCard | None,
    profile: LearnerProfileData,
    standard_metrics: list[str],
    plan_notes: str | None = None,
) -> dict[str, Any]:
    """Template 6: Experiment Design (实验方案)."""
    paper_title = paper.title if paper else "未绑定特定论文"
    metrics_str = ", ".join(standard_metrics)
    profile_hw = profile.hardware or "未提供显存/设备"

    context = (
        f"【依托论文】\n{paper_title}\n\n"
        f"【用户硬件与条件】\n{profile_hw}\n\n"
        f"【白名单标准评估指标】\n{metrics_str}\n"
    )
    if plan_notes:
        context += f"\n【前期计划要点】\n{plan_notes}\n"

    rules = (
        "1. 为同学设计清晰的实验步骤、基线对比与评估指标方案；\n"
        "2. 指标优先从标准指标目录选取；若有非标准指标需明确标注待核验 (to_verify)；\n"
        "3. 方案必须考虑同学实际显存大小与计算资源，给出合适的 Batch Size 与训练轮次建议；\n"
        "4. 严禁以 Accuracy、F1、Loss、论文基线值或任何数值区间定义、暗示或设定\n"
        "   “复现成功 / 通过 / 达标”的指标阈值、区间或判定标准；\n"
        "   论文报告值或预期指标只能表述为“论文报告的参考值”“基线参考区间”或\n"
        "   “待核验的一致性对比”，不构成复现结论；\n"
        "   即使后续实验数值接近论文基线，也不得输出“视为复现成功”或“判定复现成功”；\n"
        "   必须明确写清：evidence_linked、指标接近、计划完成或记录完整均不代表复现成功；\n"
        "   缺少可追溯结果时继续标记 to_verify 并追问；\n"
        "5. 严禁断言百分之百复现或伪造实验准确率；严禁使用 Emoji。\n"
    )
    return {
        "template_name": "experiment_design",
        "system": JIANGJIANG_SYSTEM_PERSONA,
        "task": "可执行实验方案与指标设计（实验方案）",
        "context": context,
        "rules": rules,
    }


def build_result_analysis_prompt(
    user_results: str,
    baseline_metrics: dict[str, str] | None = None,
    hardware_info: str | None = None,
) -> dict[str, Any]:
    """Template 7: Result Analysis (结果分析)."""
    baselines_str = (
        "\n".join(f"- {k}: {v}" for k, v in baseline_metrics.items())
        if baseline_metrics
        else "无特定基线"
    )
    context = (
        f"【用户提交的实验结果/现象】\n{user_results}\n\n"
        f"【基线对照参考】\n{baselines_str}\n\n"
        f"【运行环境】\n{hardware_info or '未指定'}\n"
    )
    rules = (
        "1. 客观分析用户实验指标与基线的差距，从超参数、数据划分等角度给出归因；\n"
        "2. 若用户提供的信息不完整（如缺少 loss 曲线、缺少测试集划分），明确追问缺失项；\n"
        "3. 严禁伪造实验成功或声称复现已闭环，优先使用“尚未形成可确认的复现结论”或\n"
        "   “复现闭环尚待验证”等严谨客观表述；\n"
        "   明确写清：evidence_linked 与指标接近不代表复现成功；严禁使用 Emoji。\n"
    )
    return {
        "template_name": "result_analysis",
        "system": JIANGJIANG_SYSTEM_PERSONA,
        "task": "实验结果客观归因与下一步排查建议（结果分析）",
        "context": context,
        "rules": rules,
    }


def build_stage_transition_prompt(
    from_stage: ResearchStage,
    to_stage: ResearchStage,
    completed_subtasks: list[str],
    next_goals: str,
) -> dict[str, Any]:
    """Template 8: Stage Transition (阶段切换)."""
    from_name = STAGE_DISPLAY_NAMES.get(from_stage, from_stage)
    to_name = STAGE_DISPLAY_NAMES.get(to_stage, to_stage)
    completed_str = ", ".join(completed_subtasks) if completed_subtasks else "核心需求确认"

    context = (
        f"【阶段跃迁】\n"
        f"从：{from_name} ({from_stage})\n"
        f"至：{to_name} ({to_stage})\n\n"
        f"【已完成工作及依据】\n{completed_str}\n\n"
        f"【下一阶段核心目标】\n{next_goals}\n"
    )
    rules = (
        "1. 使用大字号区块清晰宣告当前阶段已顺利完成；\n"
        "2. 必须明确写清：① 已经完成了什么具体工作；② 完成依据是什么；③ 下一步需要做什么；\n"
        "3. 禁用空泛套话；严禁使用 Emoji。\n"
    )
    return {
        "template_name": "stage_transition",
        "system": JIANGJIANG_SYSTEM_PERSONA,
        "task": "阶段完成总结与下一阶段引导（阶段切换）",
        "context": context,
        "rules": rules,
    }


def build_prompt_for_intent(
    intent: str,
    context_data: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch helper for choosing the appropriate prompt template."""
    if intent == "welcome":
        return build_welcome_prompt(
            learning_context=context_data.get("learning_context"),
            direction_cards=context_data.get("direction_cards", []),
            extra_note=context_data.get("extra_note"),
        )
    elif intent == "need_clarification":
        return build_need_clarification_prompt(
            selected_direction=context_data.get("selected_direction"),
            user_message=context_data.get("user_message", ""),
            learned_content=context_data.get("learned_content"),
            extra_context=context_data.get("extra_context"),
        )
    elif intent == "profile_and_plan":
        return build_profile_and_plan_prompt(
            research_goal=context_data.get("research_goal", ""),
            profile=context_data.get("profile", LearnerProfileData()),
            plan_candidate=context_data.get("plan_candidate"),
        )
    elif intent == "search_guidance":
        return build_search_guidance_prompt(
            research_goal=context_data.get("research_goal", ""),
            candidate_queries=context_data.get("candidate_queries", []),
            sources=context_data.get("sources", ["OpenAlex", "Crossref", "arXiv"]),
        )
    elif intent == "paper_intro":
        return build_paper_intro_prompt(
            paper=context_data["paper"],
            profile=context_data.get("profile"),
            research_goal=context_data.get("research_goal"),
        )
    elif intent == "experiment_design":
        return build_experiment_design_prompt(
            paper=context_data.get("paper"),
            profile=context_data.get("profile", LearnerProfileData()),
            standard_metrics=context_data.get(
                "standard_metrics", ["ACC", "F1", "Precision", "Recall"]
            ),
            plan_notes=context_data.get("plan_notes"),
        )
    elif intent == "result_analysis":
        return build_result_analysis_prompt(
            user_results=context_data.get("user_results", ""),
            baseline_metrics=context_data.get("baseline_metrics"),
            hardware_info=context_data.get("hardware_info"),
        )
    elif intent == "stage_transition":
        return build_stage_transition_prompt(
            from_stage=context_data.get("from_stage", "research_need"),
            to_stage=context_data.get("to_stage", "research_plan"),
            completed_subtasks=context_data.get("completed_subtasks", []),
            next_goals=context_data.get("next_goals", ""),
        )
    # Default fallback to need_clarification
    return build_need_clarification_prompt(
        selected_direction=context_data.get("selected_direction"),
        user_message=context_data.get("user_message", ""),
    )
