"""Eight Prompt templates, Jiang Jiang system persona, and output validation."""

from __future__ import annotations

import re
from collections.abc import Sequence
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
3. 严格禁止在输出中包含任何 Emoji 图标
   （例如 🌟、🎉、✨、🚀、🔥、💡、✍️、🎯、📌、📚、🔬、💪、👏、😊 等全部严禁出现，出现即违约）；
   只能使用标准中文汉字、英文、标点符号或纯文本颜文字（如 (＾▽＾)、(｡･ω･｡)、(•̀ᴗ•́)و ̑̑ 等）；
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
6. 遇到信息不足时，主动亲切地向用户追问，不自作主张做出假设；
7. 学习记录边界：严禁由学习端记录推断或评价用户的理解程度、掌握程度、动手能力、
   基础扎实度或研究潜力；严禁声称用户“能力够得着”、“又迈了一步”、“有意识地拓展”、
   “很有科研潜力”、“起点扎实”或“进阶到”；
   所有学习记录只能作为客观记录复述（如‘学习端记录显示...’），
   且必须明确声明实际经验与掌握情况需用户确认。
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

_ABSOLUTE_HARDWARE_FEASIBILITY_PATTERN = re.compile(
    r"(?:显存|GPU|算力|设备|配置|CPU|RTX\s*\d+|这个条件|这个配置|当前条件|你的设备)"
    r"[^。！？!?\n]{0,80}"
    r"(?:完全够用|够用|完全可以|肯定可以|一定可以|绝对可以|毫无压力|直接训练即可|可行|能跑|可以运行)",
    re.IGNORECASE,
)

_QUALIFIED_HARDWARE_CONTEXT_PATTERN = re.compile(
    r"(?:很多|部分|某些)[^。！？!?\n]{0,40}(?:数据集|任务|场景)",
    re.IGNORECASE,
)

_HARDWARE_UNCERTAINTY_PATTERN = re.compile(
    r"(?:可行性|能否运行|是否能运行|是否可行)[^。！？!?\n]{0,24}"
    r"(?:需要|需|取决于|仍待|待)[^。！？!?\n]{0,24}(?:确认|核验|测试|验证)",
    re.IGNORECASE,
)

_NEGATED_PROCESS_TERM_PATTERN = re.compile(
    r"(?:不会|不应|不要|不能|严禁|不得|避免)[^。！？!?\n]{0,24}(?:完成|跑通)",
    re.IGNORECASE,
)

RESEARCH_SOURCE_SCOPE_PREFIX_WELCOME = (
    "说明：以下内容基于学习端记录与通用技术概览，尚未执行正式检索；"
    "具体论文、实现细节和实验结论仍需在你确认后核验。"
)

RESEARCH_SOURCE_SCOPE_PREFIX_CLARIFICATION = (
    "说明：以下内容基于你提出的探索方向与通用技术概览，尚未执行正式检索；"
    "具体论文、实现细节和实验结论仍需在你确认后核验。"
)

RESEARCH_SOURCE_SCOPE_PREFIX_TRANSITION = (
    "说明：以下计划框架基于会话状态中已确认的研究方向与通用技术概览，尚未执行正式检索；"
    "具体论文、实现细节、设备需求和实验结论仍需在你确认后核验。"
)

RESEARCH_SOURCE_SCOPE_PREFIX_EXECUTION = (
    "说明：以下内容基于会话状态中已确认的研究方向、当前可用的论文/实验信息及通用技术概览，"
    "尚未执行正式检索；具体论文细节、实现细节和实验结论仍需在你确认后核验。"
)

RESEARCH_SOURCE_SCOPE_PREFIX = RESEARCH_SOURCE_SCOPE_PREFIX_WELCOME


def get_source_scope_prefix(template_name: str) -> str:
    """Return context-appropriate source scope prefix for the given prompt template."""
    if template_name == "welcome_and_bridge":
        return RESEARCH_SOURCE_SCOPE_PREFIX_WELCOME
    if template_name == "need_clarification":
        return RESEARCH_SOURCE_SCOPE_PREFIX_CLARIFICATION
    if template_name == "stage_transition":
        return RESEARCH_SOURCE_SCOPE_PREFIX_TRANSITION
    if template_name in {
        "search_guidance",
        "paper_intro",
        "experiment_design",
        "result_analysis",
    }:
        return RESEARCH_SOURCE_SCOPE_PREFIX_EXECUTION
    return RESEARCH_SOURCE_SCOPE_PREFIX_WELCOME


_PUNCTUATION_DELIMITERS = set("。！？!?；;，,\n\r\t|｜")
_TRANSITION_WORDS = ["但是", "然而", "不过", "反而", "可是", "并且", "但", "却", "且"]

_REPRODUCTION_CLAIM_PATTERN = re.compile(
    r"(?:"
    # 1. Rate and percentage claims (e.g. 复现率, 复现成功率, 实验完成率, reproduction success rate)
    r"reproduction\s+success\s+rate|"
    r"(?:复现|重现|再现)(?:的)?(?:成功)?率|"
    r"(?:实验|复现|重现|再现|复刻)(?:的)?完成率|"
    # 2. 跑通实验 / 通过验证
    r"(?:已(?:经)?)?(?:成功)?跑通(?:了)?(?:论文)?(?:的)?(?:复现|重现|再现|复刻)?(?:实验)?|"
    r"(?:复现|重现|再现|复刻)?(?:实验)?(?:验证)?(?:已(?:经)?)?通过(?:了)?(?:论文)?(?:的)?(?:复现|重现|再现|复刻)?(?:实验)?(?:的)?验证|"
    r"(?:已(?:经)?)?通过(?:了)?(?:论文)?(?:的)?(?:复现|重现|再现|复刻)(?:实验)?(?:验证)?|"
    r"(?:复现|重现|再现|复刻)?(?:实验)?(?:验证)(?:已(?:经)?)?通过|"
    # 3. 完成复现 / 复现完成 / 复现验证完成 / 复现实验验证完成
    r"完成(?:了|已经|已)?(?:复现|重现|再现|复刻)|"
    r"(?:复现|重现|再现|复刻)(?:实验)?(?:验证)?(?:已经完成|已完成|完成了|完成)|"
    r"(?:实验)?(?:验证)(?:已经完成|已完成|完成了|完成)|"
    # 4. 复现可靠 / 确认复现 / 复现成立 / 推进下一阶段
    r"(?:确认|判定|断定|证明)(?:了)?(?:复现|重现|再现|复刻)|"
    r"(?:复现|重现|再现|复刻)(?:可靠|成立|有效|闭环|达标|通过|成功)|"
    r"(?:复现|重现|再现|复刻)(?:已经)?可(?:以)?(?:推进|进入)(?:到)?(?:下一阶段|下个阶段)|"
    r"可以(?:推进|进入)(?:到)?(?:下一阶段|下个阶段)|"
    # 5. 主体(实验结果/复现结果/复现指标/指标/结果) + 连接(和/与/跟)
    #    + 对象(原论文/论文/论文基线/原论文基线/基线/论文结论/论文结果/论文指标)
    #    + 结论(完全/基本/大致)?(一致/吻合/相同)
    r"(?:实验结果|复现结果|复现指标|指标|结果)(?:和|与|跟)(?:原论文|论文|论文基线|原论文基线|基线|论文结论|论文结果|论文指标)(?:完全|基本|大致)?(?:一致|吻合|相同)|"
    r"(?:与|和|跟)(?:原论文|论文|论文基线|原论文基线|基线)(?:中的)?(?:实验)?(?:结果|结论|指标)(?:完全|基本|大致)?(?:一致|吻合|相同)|"
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

# Fingerprint 1: 实验/复现结果 ↔ (原)论文(结果)
_FINGERPRINT_RESULT_PAPER_RESULT = re.compile(
    r"(?:"
    r"(?:实验结果|复现结果|结果)(?:和|与|跟)(?:原论文|论文)(?:中的)?(?:实验)?结果"
    r"(?:完全|基本|大致)?(?:一致|吻合|相同)|"
    r"(?:与|和|跟)(?:原论文|论文)(?:中的)?(?:实验)?结果(?:完全|基本|大致)?(?:一致|吻合|相同)|"
    r"(?:实验结果|复现结果)(?:和|与|跟)(?:原论文|论文)(?:完全|基本|大致)?(?:一致|吻合|相同)"
    r")",
    re.IGNORECASE,
)

# Fingerprint 2: 实验/复现结果 ↔ (原)论文结论
_FINGERPRINT_RESULT_PAPER_CONCLUSION = re.compile(
    r"(?:"
    r"(?:实验结果|复现结果|结果)(?:和|与|跟)(?:原论文|论文)(?:中的)?(?:论文)?结论"
    r"(?:完全|基本|大致)?(?:一致|吻合|相同)|"
    r"(?:与|和|跟)(?:原论文|论文)(?:中的)?(?:论文)?结论(?:完全|基本|大致)?(?:一致|吻合|相同)"
    r")",
    re.IGNORECASE,
)

# Fingerprint 3: (复现)指标 ↔ (原)论文(指标)
_FINGERPRINT_METRIC_PAPER_METRIC = re.compile(
    r"(?:"
    r"(?:复现指标|指标)(?:和|与|跟)(?:原论文|论文)(?:中的)?(?:论文)?指标"
    r"(?:完全|基本|大致)?(?:一致|吻合|相同)|"
    r"(?:与|和|跟)(?:原论文|论文)(?:中的)?(?:论文)?指标(?:完全|基本|大致)?(?:一致|吻合|相同)|"
    r"(?:复现指标|指标)(?:和|与|跟)(?:原论文|论文)(?:完全|基本|大致)?(?:一致|吻合|相同)"
    r")",
    re.IGNORECASE,
)

# Fingerprint 4: (复现)指标/结果 达到或超过 (原)论文基线/指标
_FINGERPRINT_METRIC_BASELINE = re.compile(
    r"(?:"
    r"(?:复现)?(?:指标|结果)(?:已|已经)?达到(?:原论文|论文)?(?:基线|指标)|"
    r"(?:复现)?(?:指标|结果)超过(?:原论文|论文)?(?:基线|指标)"
    r")",
    re.IGNORECASE,
)

_FINGERPRINTS = (
    ("result_paper_result", _FINGERPRINT_RESULT_PAPER_RESULT),
    ("result_paper_conclusion", _FINGERPRINT_RESULT_PAPER_CONCLUSION),
    ("metric_paper_metric", _FINGERPRINT_METRIC_PAPER_METRIC),
    ("metric_baseline", _FINGERPRINT_METRIC_BASELINE),
)


_EVIDENCE_QUESTION_PATTERN = re.compile(
    r"[?？]|(?:是否|是不是|有没有|能否|可否|为何|为什么|怎么|怎样|如何|什么|哪|请问|吗$|吗[，。；\s])",
    re.IGNORECASE,
)

_EVIDENCE_CONDITION_PATTERN = re.compile(
    r"(?:如果|若|哪怕|即使|即便|假使|假设|要是|若是|如若|一旦|假如)",
    re.IGNORECASE,
)

_EVIDENCE_NEGATION_PATTERN = re.compile(
    r"(?:没有|尚未|未曾|未能|并未|未有|未做|未进行|未对比|不代表|不能|无法|并不|不是|暂无|毫无|未得到)",
    re.IGNORECASE,
)


def _is_asserted_evidence_clause(clause: str) -> bool:
    c = clause.strip()
    if not c:
        return False
    if bool(_EVIDENCE_QUESTION_PATTERN.search(c)):
        return False
    if bool(_EVIDENCE_CONDITION_PATTERN.search(c)):
        return False
    if bool(_EVIDENCE_NEGATION_PATTERN.search(c)):
        return False
    return True


def _get_supported_evidence_fingerprints(
    evidence_context: Sequence[str] | str | None,
) -> set[str]:
    if evidence_context is None:
        return set()
    if isinstance(evidence_context, str):
        items = [evidence_context]
    else:
        items = list(evidence_context)

    supported: set[str] = set()
    for item in items:
        if not item or not isinstance(item, str):
            continue
        clauses = _split_into_clauses(item)
        if not clauses:
            clauses = [(0, len(item), item)]
        for _, _, clause_text in clauses:
            if not _is_asserted_evidence_clause(clause_text):
                continue
            for fp_name, fp_pattern in _FINGERPRINTS:
                if fp_pattern.search(clause_text):
                    supported.add(fp_name)

    return supported


def _get_claim_fingerprint(claim_text: str) -> str | None:
    for fp_name, fp_pattern in _FINGERPRINTS:
        if fp_pattern.search(claim_text):
            return fp_name
    return None



_LOCAL_PREFIX_DELIMITER_PATTERN = re.compile(
    r"[\n\r；;。\.！？!\?，,、/]|(?:\s*和\s*|\s*及\s*|\s*且\s*|\s*但\s*)"
)

_ADJACENT_POST_TO_VERIFY_PATTERN = re.compile(
    r"^[；;\s，,\n]*"
    r"(?:(?:且|并|但|还)?(?:仍|尚|还)?(?:待核验|需核验|待确认|需确认|有待核验)[；;\s，,\n]*)*"
    r"(?:to_verify|待核验|需核验|尚待核验|有待核验|需确认|待确认|仍需核验|还需核验)"
    r"[:：]?",
    re.IGNORECASE,
)


_USER_SOURCE_PREFIX_PATTERN = re.compile(
    r"(?:fact|事实)?[:：]?\s*"
    r"(?:由|据|根据|依据|基于)?"
    r"(?:用户|学生)"
    r"(?:报告|提供|反馈|表示|声称|称|输入|提交)"
    r"[“‘\"'’「『（(【\[\s]{0,5}$",
    re.IGNORECASE,
)

_TO_VERIFY_PATTERN = re.compile(
    r"(?:to_verify|待核验|需核验|尚待核验|有待核验|需确认|待确认|核验|查验)",
    re.IGNORECASE,
)

_LEARNING_RECORD_PREFIX_PATTERN = re.compile(
    r"(?:"
    r"学习端(?:记录)?(?:显示|情况)?|"
    r"当前(?:学习)?进度记录(?:为)?|进度记录(?:为)?|"
    r"已学内容|已学知识|学习内容|学习记录|学习轨迹"
    r")",
    re.IGNORECASE,
)

_NEGATION_PREFIX_PATTERN = re.compile(
    r"(?:"
    # Inspection / to_verify phrases
    r"需核验|待核验|需确认|待确认|核验|查验|需明确|需界定|是否|能否|可否|到底|究竟|"
    # Negations with optional leading adverbs (e.g. 也不能, 并不能, 还不能)
    r"(?:也|并|仍|还|暂|暂时|目前|均|都)?"
    r"(?:"
    r"尚不足以|难以|无法|切勿|切忌|不可|未曾|并未|未有|尚未|未能|未形成|不足以|不足|"
    r"还没|还没有|没有|未|"
    r"不能|不应|无需|严禁|不得|禁止|避免|不要|难言|难下|"
    r"不|并不|绝不|不代表|不等于|不等同于|不等同|不构成|并非|不是|不视为|不算作|不算|≠|!="
    r")"
    r")"
    r"(?:[“‘\"'’「『（(【\[\s*~_:\*、，,/]|把|将|因为|因|由于|根据|依据|凭借|单凭|仅凭|由此|因此|据此|轻易|直接|盲目|贸然|简单|提前|就|而|去|来|前述|目前|当前|已有|现有|这些|上述|结果|指标|数据|已确认的|已确认|已有的|所谓的|某种|一个|这项|这些|所谓|"
    r"熟练|掌握|具备|拥有|实战|实操|实践|经验|实践经验|代码经验|程度|掌握程度|科研能力|研究能力|科研|研究|编程|编码|独立|已|已经|或|或者|和|以及|你|您|其|同学|用户|学生|"
    r"(?:急于|急着|轻易|直接|盲目|贸然|过早|过急|立刻|马上)?(?:判定为|认定为|追求|谈及|提及|轻信|盖章为|盖章|定性为|定论为|定论|定义为|断言为|视作|视为|说明|定义|宣称|断定|判为|判定|认定|认为|得出|下达|形成|确认|宣布|言说|轻言|妄下|妄言|给出|下|声称|断言|说)){0,30}"
    r"[“‘\"'’「『（(【\[\s*~_:\*、，,/]{0,4}$",
    re.IGNORECASE,
)

_CONDITION_PREFIX_PATTERN = re.compile(
    r"(?:即使|即便|哪怕|假使|假设|如果未来|如果|若|要是|若是|如若|假如)"
    r"(?:[“\"'「『（(【\[\s]|你|还|尚未|还没|没有|暂未|并不|不能|并非|(?:用户|学生)?(?:报告|提供|反馈|表示|声称|称|输入)?|(?:未来|后续|最终)?(?:形成|达成|达到|实现|得出|出现|能够)?){0,20}"
    r"[“\"'「『（(【\[\s]{0,2}$"
)

_QUESTION_PREFIX_PATTERN = re.compile(
    r"(?:"
    r"为什么|为何|怎会|怎可|凭何|何以|怎能|"
    r"你有没有|有没有|你是否|是否|能否|可否|请问|是不是|"
    r"你亲手|亲手|有写过|写过|跑过|尝试过"
    r")",
    re.IGNORECASE,
)

_QUESTION_SUFFIX_PATTERN = re.compile(
    r"^[^\n\r。！？!?]*(?:[?？]|吗[，。；\s\n\r?？]|吗$)",
    re.IGNORECASE,
)

_SUGGESTION_PREFIX_PATTERN = re.compile(
    r"(?:"
    r"建议|推荐|不妨|可以尝试|尝试|先尝试|动手|亲自|亲手去|去|来|"
    r"建议你|建议您|可以|希望你|希望您|计划|准备|旨在|以便|为了|争取|"
    r"能|能够|便于|利于|有助于|助力|先|"
    r"路径[0-9一二三四五六七八九十]*[：:]?|"
    r"调试|小规模测试|本地测试|代码调试|测试运行|"
    r"比如|例如|譬如|如[：:]?|"
    r"把|将|想|想要|试图|意向|意图|打算|倾向|偏向|偏好|选择|"
    r"在|本地|云端|环境|服务器|平台|"
    r"第[0-9一二三四五六七八九十]+[步阶段期周天月次]|阶段|步骤|任务|目标|清单|"
    r"[-*•]?\s*(?:\*\*)?(?:[A-Za-z0-9]|[甲乙丙丁戊己庚辛壬癸])+(?:\*\*)?[.)、:]\s*(?:\[\s*\])?|"
    r"demo|Demo|baseline|Baseline|示例|样例|demo流程|样例代码"
    r")",
    re.IGNORECASE,
)

_UNGROUNDED_MASTERY_CLAIM_PATTERN = re.compile(
    r"(?:"
    r"(?<!不)(?<!并不)(?<!绝不)(?<!不等于)(?:这)?(?:说明|证明|表明|意味着|可以看出)[^，。；\n]*(?:基本功|基础|功底|能力|水平|入口|理解|掌握|熟悉|框架|认知框架|理解框架|路径|学习路径|准备)[^，。；\n]*(?:扎实|过硬|很强|过人|具备|成型|深入|初步|有了|形成|成熟|比较成熟|充分|就绪)|"
    r"(?:你的|你|这个|从学习记录看[^，。；\n]*你的)[^，。；\n]*(?:基本功|基础|功底|起点|图神经网络基础|GNN基础)[^，。；\n]*(?:扎实|过硬|很稳|稳固|很棒|不错|成熟)|"
    r"(?:打下|打牢|奠定|拥有|具备|有着)了?[^，。；\n]*(?:扎实|过硬|稳固|深厚|良好|系统)?的?(?:基本功|基础|功底|基石)|"
    r"(?:你|根据学习记录[^，。；\n]*)(?:目前|现在|已经|已)?(?:完全)?掌握(?:了|的)?|"
    r"(?:已经|已|完全)掌握(?:了|的)?|"
    r"掌握了(?:GCN|图神经网络|节点分类|算法|技术|知识|推导|核心|范式|机制)?|"
    r"(?:你)?(?:已经|已)?(?:有|具备|拥有)(?:用[^，。；\n]*)?(?:实践经验|实操经验|实操能力|动手能力|代码经验)|"
    r"(?:你)(?:已经|已)?具备(?:了)?[^，。；\n]*(?:能力|水平|基础|入口|条件|资格)|"
    r"(?:这|此)?(?:表明|说明|体现)[^，。；\n]*(?:你)?(?:已经|已)?(?:具备|准备好|就绪|准备就绪)[^，。；\n]*(?:充分准备|进入|开展|开始|科研|研究|课题|深入|实验)|"
    r"(?:你)(?:已经|已)?(?:准备好|就绪|准备就绪)[^，。；\n]*(?:充分准备|进入|开展|开始)[^，。；\n]*(?:科研|研究|课题|深入|实验)|"
    r"(?:你)(?:大概|已经|已)?(?:知道|明白|搞懂|理解)(?:了)?[^，。；\n]*(?:怎么|如何|怎样|机制|原理|概念|架构|流程)[^，。；\n]*(?:聚合|训练|实现|构建|设计|分类|采样)|"
    r"(?:你)(?:已经|已)?(?:理解|搞懂|吃透|弄通)(?:了)?[^，。；\n]*(?:机制|原理|概念|算法|架构|逻辑|流程)|"
    r"(?:这|此)?(?:说明|看出|证明)[^，。；\n]*(?:你)?(?:已经|已)?(?:摸到|摸清|摸索出|触碰到了?|掌握了?)[^，。；\n]*(?:支线|技术支线|脉络|核心脉络|主线|脉络|门道|精髓|范式)|"
    r"(?:你)(?:已经|已)?(?:摸到|摸清|摸索出|触碰到了?|掌握了?)[^，。；\n]*(?:支线|技术支线|脉络|核心脉络|主线|脉络|门道|精髓|范式)|"
    r"(?:你)?(?:对[^，。；\n]*)?(?:已经|已)?(?:有|具备|拥有|形成|建立了?)[^，。；\n]*(?:(?:系统|深入|扎实|全面|透彻|清晰|完整|深刻)的?(?:理解|认识|认知|掌握)|认知框架|理解框架|认知体系|认知)|"
    r"(?:看来你|看到你|你)?(?:已经|已)?完成(?:了)?[^，。；\n]*(?:学习跨度|跨度|算法学习|数学推导|节点分类|学习任务|推导和节点分类)|"
    r"(?:你)?从[^，。；\n]*(?:进阶|过渡|跨越|延伸)到[^，。；\n]*|"
    r"(?:这)?(?:一|两)?步迈得[^，。；\n]*(?:自然|顺畅|扎实|稳健|快)|"
    r"(?:你)?(?:当前)?能力够得着|"
    r"(?:这个)?(?:选择)?(?:很有|极具|富有)?科研潜力|"
    r"又往前迈了一步|"
    r"(?:开始)?有意识地拓展|"
    r"(?:看来你)?(?:刚刚|已经|已)?打通了?[^，。；\n]*(?:任督二脉|脉络|链路|逻辑)"
    r")",
    re.IGNORECASE,
)

_STRICT_LEARNING_EVALUATION_PATTERN = re.compile(
    r"(?:"
    r"能力(?:够得着|达到|足够|符合|适合|较强|很强|过关|过硬|足可|能够)|"
    r"够得着|"
    r"能力上(?:完全)?(?:够得着|达到|足够|没问题)|"
    r"又往前迈了一步|"
    r"迈出了?(?:扎实|重要|坚实|关键)?的一步|"
    r"(?:开始)?有意识地拓展|"
    r"(?:很有|极具|富有|具备)?科研潜力|"
    r"有潜力|"
    r"基础(?:足以|足以支撑|足可)|"
    r"(?:打下|打牢|奠定|拥有|具备|有着)了?[^，。；\n]*(?:扎实|过硬|稳固|深厚|良好|系统)?的?(?:基本功|基础|功底|基石)|"
    r"(?:形成|建立)了?系统(?:的)?(?:理解|认识|认知|框架)|"
    r"系统的理解|"
    r"起点(?:很|十分|非常)?(?:扎实|高|好|稳)|"
    r"(?:很好|不错|极佳|扎实)的起点|"
    r"迈得(?:很|十分)?(?:自然|顺畅|快|扎实)|"
    r"学习路径(?:已经)?(?:比较)?成熟|"
    r"准备好进入更深入的研究|"
    r"已掌握|掌握了|"
    r"做过[^，。；\n]*(?:实验|任务|分类|推导|复现|项目|工程)"
    r")",
    re.IGNORECASE,
)

_SUFFIX_BOUNDARY_PATTERN = re.compile(
    r"^[”\"'」』）)】\]\s*~_：:|｜]*(?:"
    r"不代表|不等于|不等同于|不构成|并不|并非|不是|不意味着|"
    r"尚未|仍未|还未|未形成|尚未形成|尚未构成|未构成|尚不能|仍不能|未有|"
    r"这个结论尚未|这结论尚未|结论尚未|尚未被|尚待|未确认|未形成|存在疑问|难以确认|不成立|的结论尚不能下|的结论仍不能下|"
    r"当作结论|作为结论|等当作|等作为|的结论|的判定|的判定结论|"
    r"是两回事|两回事|不同概念|不是一回事|不能混为一谈|不能等同|"
    r"(?:通常|往往|一般|首先)?(?:至少)?(?:需要|须|需|应当|必须)(?:满足|符合|具备|达成|对照)?|"
    r"的前提|的条件|的标准|的定义|的判定标准|的确认标准|的核验标准|"
    r"还需要|仍需|尚需|还需要更多|仍需要|有待|"
    r"否[，,\s]|否认|未完成|未通过|不成立|未达成|待定|暂无|尚未|待核验|不足|"
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


def _extract_evidence_text(evidence_context: Sequence[str] | str | None) -> str:
    if evidence_context is None:
        return ""
    if isinstance(evidence_context, str):
        return evidence_context
    return " \n ".join(str(item) for item in evidence_context if item)


def _extract_user_asserted_evidence_text(
    evidence_context: Sequence[str] | str | None,
) -> str:
    """Extract only user-asserted text from evidence context, excluding learning records."""
    if evidence_context is None:
        return ""
    if isinstance(evidence_context, str):
        items = [evidence_context]
    else:
        items = list(evidence_context)
    user_items: list[str] = []
    for item in items:
        s = str(item).strip()
        if any(
            s.startswith(prefix)
            for prefix in (
                "已学内容：",
                "已学内容:",
                "学习进度：",
                "学习进度:",
                "学习端记录",
                "当前进度记录",
            )
        ):
            continue
        user_items.append(s)
    return " \n ".join(user_items)


def _contains_ungrounded_reproduction_success_claim(
    text: str,
    *,
    evidence_context: Sequence[str] | str | None = None,
) -> bool:
    """Check if text contains ungrounded affirmative reproduction success claims.

    1. Splits text into isolated local semantic clauses.
    2. Evaluates claims against clause or local negation/condition/suffix boundaries.
    3. Prevents cross-clause negation leaks.
    4. Enforces verifiable, locally bound user-source provenance and adjacent post to_verify.
    """
    supported_evidence_fps = _get_supported_evidence_fingerprints(evidence_context)

    clauses = _split_into_clauses(text)
    if not clauses:
        clauses = [(0, len(text), text)]

    for clause_start, _, clause_str in clauses:
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
            local_suffix = clause_str[m.end():]
            # Process-validation wording is not a reproduction-success claim when
            # it explicitly refers to environment/runtime checks or a planned
            # training/evaluation workflow without mentioning reproduction/papers.
            if m.group() == "验证通过" and "运行验证通过" in clause_str:
                continue
            if (
                m.group() == "跑通"
                and "流程" in local_suffix
                and not re.search(r"复现|重现|再现|复刻|论文|实验", clause_str)
            ):
                continue
            if m.group() == "跑通" and _NEGATED_PROCESS_TERM_PATTERN.search(clause_str):
                continue
            prefix_boundary = bool(
                _NEGATION_PREFIX_PATTERN.search(local_prefix)
                or _CONDITION_PREFIX_PATTERN.search(local_prefix)
            )
            if prefix_boundary:
                continue

            suffix_boundary = bool(_SUFFIX_BOUNDARY_PATTERN.search(local_suffix))
            if suffix_boundary:
                continue

            global_start = clause_start + m.start()
            global_end = clause_start + m.end()
            following_text = text[global_end:]

            # If the claim is inside a question clause or question sentence, allow it as an inquiry
            is_question = bool(
                _QUESTION_PREFIX_PATTERN.search(local_prefix)
                or _QUESTION_PREFIX_PATTERN.search(clause_prefix)
                or _QUESTION_SUFFIX_PATTERN.search(following_text)
                or _QUESTION_SUFFIX_PATTERN.search(local_suffix)
            )
            if is_question:
                continue

            # If the claim is inside a suggestion / preparation recommendation, allow it as advice
            is_suggestion = bool(
                _SUGGESTION_PREFIX_PATTERN.search(local_prefix)
                or _SUGGESTION_PREFIX_PATTERN.search(clause_prefix)
            )
            if is_suggestion and not any(
                w in m.group()
                for w in ("成功", "成立", "闭环", "达标", "通过了", "已通过", "确认", "判定")
            ):
                continue

            # 1. Immediate local segment before this match must be a user source tag
            preceding_text = text[:global_start]
            last_delim = None
            for dm in _LOCAL_PREFIX_DELIMITER_PATTERN.finditer(preceding_text):
                last_delim = dm
            if last_delim is not None:
                local_segment = preceding_text[last_delim.end():].strip()
            else:
                local_segment = preceding_text.strip()
            has_local_user_source = bool(_USER_SOURCE_PREFIX_PATTERN.search(local_segment))

            # 2. to_verify must be adjacent and post-positioned to this fact claim
            has_adjacent_to_verify = bool(
                _ADJACENT_POST_TO_VERIFY_PATTERN.search(following_text)
            )

            # 3. Claim fingerprint must be supported by matching user evidence fingerprint
            matched_claim = m.group()
            claim_fp = _get_claim_fingerprint(matched_claim)
            fp_supported = claim_fp is not None and claim_fp in supported_evidence_fps

            if has_local_user_source and has_adjacent_to_verify and fp_supported:
                continue

            has_unbounded_claim = True
            break

        if has_unbounded_claim:
            return True

    return False


def _contains_ungrounded_mastery_claim(
    text: str,
    *,
    evidence_context: Sequence[str] | str | None = None,
) -> bool:
    """Check if text contains ungrounded mastery/capability claims."""
    clauses = _split_into_clauses(text)
    if not clauses:
        clauses = [(0, len(text), text)]

    for _, _, clause_str in clauses:
        matches = list(_UNGROUNDED_MASTERY_CLAIM_PATTERN.finditer(clause_str))
        if not matches:
            continue

        first_match = matches[0]
        clause_prefix = clause_str[:first_match.start()]
        if bool(
            _NEGATION_PREFIX_PATTERN.search(clause_prefix)
            or _CONDITION_PREFIX_PATTERN.search(clause_prefix)
        ):
            continue

        for m in matches:
            local_prefix = clause_str[:m.start()]
            if bool(
                _NEGATION_PREFIX_PATTERN.search(local_prefix)
                or _CONDITION_PREFIX_PATTERN.search(local_prefix)
            ):
                continue
            local_suffix = clause_str[m.end():]
            if bool(_SUFFIX_BOUNDARY_PATTERN.search(local_suffix)):
                continue

            # If user explicitly asserted their own mastery/capability in evidence_context, allow it
            evidence_text = _extract_user_asserted_evidence_text(evidence_context)
            if evidence_text and bool(_UNGROUNDED_MASTERY_CLAIM_PATTERN.search(evidence_text)):
                continue

            return True

    return False


def _contains_learning_record_evaluation(
    text: str,
    *,
    evidence_context: Sequence[str] | str | None = None,
) -> bool:
    """Check if text contains ungrounded learning evaluation in strict mode."""
    clauses = _split_into_clauses(text)
    if not clauses:
        clauses = [(0, len(text), text)]

    for _, _, clause_str in clauses:
        matches = list(_STRICT_LEARNING_EVALUATION_PATTERN.finditer(clause_str))
        if not matches:
            continue

        first_match = matches[0]
        clause_prefix = clause_str[:first_match.start()]
        if bool(
            _NEGATION_PREFIX_PATTERN.search(clause_prefix)
            or _CONDITION_PREFIX_PATTERN.search(clause_prefix)
        ):
            continue

        for m in matches:
            local_prefix = clause_str[:m.start()]
            if bool(
                _NEGATION_PREFIX_PATTERN.search(local_prefix)
                or _CONDITION_PREFIX_PATTERN.search(local_prefix)
            ):
                continue
            local_suffix = clause_str[m.end():]
            if bool(_SUFFIX_BOUNDARY_PATTERN.search(local_suffix)):
                continue

            if bool(
                _QUESTION_PREFIX_PATTERN.search(local_prefix)
                or _QUESTION_PREFIX_PATTERN.search(clause_prefix)
                or _QUESTION_SUFFIX_PATTERN.search(local_suffix)
            ):
                continue

            evidence_text = _extract_user_asserted_evidence_text(evidence_context)
            if evidence_text and bool(_STRICT_LEARNING_EVALUATION_PATTERN.search(evidence_text)):
                continue

            return True

_SCOPE_GEN_PATTERN = re.compile(
    r"(?:"
    r"基于学习记录(?:生成)?|基于你刚确认的研究方向|基于你确认的研究方向|基于用户确认的研究方向|"
    r"基于确认方向|基于当前确认|探索方向|方向建议|通用技术概览|技术概览|计划框架"
    r")"
)
_SCOPE_UNRETRIEVED_PATTERN = re.compile(
    r"(?:未执行正式检索|尚未执行正式检索|未做正式检索|尚未检索|未开展检索|未进行检索)"
)
_SCOPE_VERIFY_PATTERN = re.compile(
    r"(?:需(?:在)?(?:你|用户)?确认后核验|仍需(?:在)?(?:你|用户)?确认后核验|仍需核验|需核验|待核验|需按论文或官方文档核验)"
)

_TECHNICAL_TOPIC_PATTERN = re.compile(
    r"(?:"
    r"卡片[一二三四五1-5]|推荐(?:研究)?方向|研究方向卡片|方向卡片|前置知识缺口|"
    r"引文网络|自注意力|图注意力|异质图|邻居采样|小批量图训练|时空图卷积|图对比学习|"
    r"归纳式(?:学习|图表示|泛化)?|采样邻居|新节点(?:直接)?生成表征|降(?:低)?复杂度|"
    r"针对无法整图加载|无法整图加载|下游性质预测|消息传递机制|邻接矩阵归一化|"
    r"分子图表示|图卷积消息传递|整图读出|性质预测头|设备配置直接影响实验方案设计|"
    r"设备配置直接影响|影响实验方案设计|小目标拆解计划"
    r")"
)

_USER_MENTION_PREFIX_PATTERN = re.compile(
    r"(?:"
    r"你(?:提到|说|表达|输入|反馈|表示|想做|想探索|想应用|想了解)|"
    r"用户(?:提到|说|表达|输入|反馈|表示|想做|想探索|想应用|想了解)|"
    r"确定核心研究主题[：:]|选定方向[：:]|选定主题[：:]"
    r")",
    re.IGNORECASE,
)


def _requires_natural_source_scope(text: str) -> bool:
    """Determine if text contains technical statements or overviews requiring source_scope."""
    clauses = _split_into_clauses(text)
    if not clauses:
        clauses = [(0, len(text), text)]

    for clause_start, _, clause_str in clauses:
        matches = list(_TECHNICAL_TOPIC_PATTERN.finditer(clause_str))
        if not matches:
            continue
        for m in matches:
            local_prefix = clause_str[:m.start()]
            if (
                _LEARNING_RECORD_PREFIX_PATTERN.search(local_prefix)
                or _USER_MENTION_PREFIX_PATTERN.search(local_prefix)
            ):
                continue
            preceding = text[:clause_start + m.start()]
            last_seg = preceding.split("\n")[-1]
            if (
                _LEARNING_RECORD_PREFIX_PATTERN.search(last_seg)
                or _USER_MENTION_PREFIX_PATTERN.search(last_seg)
            ):
                continue
            following_local = clause_str[m.end():]
            if (
                _QUESTION_PREFIX_PATTERN.search(local_prefix)
                or _QUESTION_SUFFIX_PATTERN.search(following_local)
            ):
                continue
            if (
                _NEGATION_PREFIX_PATTERN.search(local_prefix)
                or _CONDITION_PREFIX_PATTERN.search(local_prefix)
            ):
                continue
            return True
    return False


def _has_valid_natural_source_scope(text: str) -> bool:
    """Check whether text includes natural language source_scope covering 3 essential aspects."""
    return bool(
        _SCOPE_GEN_PATTERN.search(text)
        and _SCOPE_UNRETRIEVED_PATTERN.search(text)
        and _SCOPE_VERIFY_PATTERN.search(text)
    )


def _has_scope_before_first_technical_claim(text: str) -> bool:
    """Check that source_scope declaration appears before the first technical claim in text.

    Returns True if no technical claims present, or if scope precedes the first technical claim.
    Returns False if technical claims precede the scope (scope in middle/end doesn't protect start).
    """
    tech_match = _TECHNICAL_TOPIC_PATTERN.search(text)
    if tech_match is None:
        return True  # No technical claims → position check trivially passes

    # Find the earliest position of any scope component
    scope_matches = [
        m.start()
        for p in (_SCOPE_GEN_PATTERN, _SCOPE_UNRETRIEVED_PATTERN, _SCOPE_VERIFY_PATTERN)
        if (m := p.search(text)) is not None
    ]
    if not scope_matches:
        return False  # No scope at all

    scope_start = min(scope_matches)
    # Scope must start at or before first technical claim
    return scope_start <= tech_match.start()


# Pattern for detecting explicit user attribution clauses in model output.
# Targets forms like: 根据你上一轮的选择（小分子药物）
# Avoids matching temporal/scopal 在你确认后核验 by only capturing
# parenthetical or already-confirmed forms.
_USER_ATTRIBUTION_PATTERN = re.compile(
    r"(?:"
    # Form 1: explicit parenthetical — 根据你(上一轮)的选择（VALUE）
    r"根据你(?:上一轮)?(?:的)?(?:选择|确认|决定)[（(]([^）)\n]{1,40})[）)]|"
    # Form 2: you already chose — 你已选择/选定/确认了 VALUE
    r"你已(?:选择|选定|确认)(?:了)?([^\n，。！？；]{1,30})(?=[，。！？\n]|$)"
    r")"
)


def _contains_unsupported_user_attribution(
    text: str,
    *,
    evidence_context: Sequence[str] | str | None = None,
) -> tuple[bool, str | None]:
    """Detect if model attributes a specific choice to the user that doesn't appear in evidence.

    Returns (True, extracted_attribution) if unsupported attribution is found.
    Returns (False, None) if all attributions are traceable to user evidence.
    """
    matches = list(_USER_ATTRIBUTION_PATTERN.finditer(text))
    if not matches:
        return False, None

    evidence_text = _extract_user_asserted_evidence_text(evidence_context)

    for m in matches:
        # Extract the attributed value from whichever capture group matched
        attributed = next((g for g in m.groups() if g is not None), None)
        if not attributed:
            continue
        attributed = attributed.strip().strip("（(）)").strip()
        if not attributed:
            continue

        # Check if the attributed value appears in user evidence (substring match)
        if attributed and attributed not in evidence_text:
            return True, attributed

    return False, None


def validate_jiangjiang_output(
    text: str,
    *,
    evidence_context: Sequence[str] | str | None = None,
    learning_record_mode: bool = False,
) -> tuple[bool, str | None]:
    """Validate model output against persona rules (no emoji/forbidden phrase/false claims)."""
    if _EMOJI_PATTERN.search(text):
        return False, "Output contains forbidden emoji characters."
    for phrase in _FORBIDDEN_PHRASES:
        if phrase in text:
            return False, f"Output contains forbidden phrase or unproven claim: {phrase}"
    for hardware_match in _ABSOLUTE_HARDWARE_FEASIBILITY_PATTERN.finditer(text):
        local_prefix = text[: hardware_match.start()]
        if _NEGATION_PREFIX_PATTERN.search(local_prefix) or _CONDITION_PREFIX_PATTERN.search(
            local_prefix
        ):
            continue
        sentence_prefix = local_prefix.rsplit("\n", 1)[-1].rsplit("。", 1)[-1]
        if _QUALIFIED_HARDWARE_CONTEXT_PATTERN.search(sentence_prefix):
            continue
        sentence_text = text[local_prefix.rfind("\n") + 1 :].split("\n", 1)[0]
        if _HARDWARE_UNCERTAINTY_PATTERN.search(sentence_text):
            continue
        return (
            False,
            "Output makes an absolute hardware-feasibility claim without verified "
            "experiment evidence",
        )
    if _requires_natural_source_scope(text):
        if not _has_valid_natural_source_scope(text):
            return (
                False,
                "Output contains technical statements or direction overviews without "
                "natural language source_scope",
            )
        if not _has_scope_before_first_technical_claim(text):
            return (
                False,
                "Output contains technical statements before source_scope: "
                "source_scope must be the first paragraph before any technical claims",
            )
    has_bad_attribution, attributed_value = _contains_unsupported_user_attribution(
        text, evidence_context=evidence_context
    )
    if has_bad_attribution:
        return (
            False,
            f"Output attributes unconfirmed choice to user: "
            f"'{attributed_value}' not found in user message history",
        )
    if learning_record_mode:
        if _contains_learning_record_evaluation(text, evidence_context=evidence_context):
            return (
                False,
                "Output contains ungrounded learning evaluation or capability claim "
                "in learning record mode",
            )
    if _contains_ungrounded_mastery_claim(text, evidence_context=evidence_context):
        return (
            False,
            "Output contains ungrounded mastery or capability claim inferred from learning records",
        )
    if _contains_ungrounded_reproduction_success_claim(text, evidence_context=evidence_context):
        return False, "Output contains ungrounded affirmative reproduction success claim: 复现成功"
    return True, None



# 固定开场白：新建科研会话的空态欢迎与学习端桥接欢迎语共用这一份文本，
# 保证两个入口的话术一致。第三段的否定表述（"不代表已经掌握…"）必须与
# validate_jiangjiang_output 的边界校验兼容，改写时需重新过校验。
RESEARCH_WELCOME_OPENING = (
    "(｡･ω･｡) 欢迎来到科研工作台！我是姜姜～\n\n"
    "这里不是一上来就让你填表或做实验，而是陪你把“我想做什么研究”慢慢聊清楚："
    "从选方向、补前置知识，到设计实验、看结果，我们一步一步来。\n\n"
    "学习端记录会作为方向建议的来源，但不代表已经掌握相关知识、具备实验能力或能够完成复现。\n\n"
    "我会先根据学习内容准备几个可探索方向。你可以选一个感兴趣的，"
    "也可以直接告诉我：你现在最想研究什么？"
)


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
        "1. 回复必须以下面的固定开场白开头（逐字使用，包括颜文字与分段，不得改写或增删）：\n"
        f"{RESEARCH_WELCOME_OPENING}\n"
        "2. 若存在学习端输入，固定开场白之后必须另起一段，客观引用学习端记录：\n"
        "   '学习端记录显示你已学习：<已学内容>，当前进度记录为：<学习进度>。'\n"
        "   并立即附带：'这些学习记录不代表已掌握或具备研究能力，实际理解与代码经验仍需确认。'\n"
        "3. 若上方给出了 5 个推荐研究方向，必须逐一清晰展示每个卡片的完整标题与描述；\n"
        "   若推荐研究方向为空（空态），不得虚构方向卡，直接以固定开场白的追问结束；\n"
        "4. 鼓励同学从这 5 个卡片中选择一个感兴趣的方向，或者自由输入自己想做的其他方向；\n"
        "5. 事实边界红线与严格学习记录模式约束（绝对遵守）：\n"
        "   - 提及学习端输入时，必须严格表述为‘学习端记录显示你已学习...，当前进度记录为...’；\n"
        "   - 严禁将学习记录改写为‘你已经完成了...’、‘你已掌握...’、‘你在学习端打下了扎实的基础’、"
        "‘说明你已经对...有了系统/深入理解’、‘具备了开展科研的能力’等任何主谓判断或能力肯定；\n"
        "   - 严格学习记录模式：所有学习记录必须立即明确附带"
        "‘这些学习记录不代表已掌握或具备研究能力，实际理解与代码经验仍需确认’；\n"
        "   - 严禁评价用户的能力"
        "（严禁输出‘能力够得着’、‘能力适合’、‘能力足够’等任何关于用户能力的推测、假定或建议）；\n"
        "   - 严禁评价用户的学习进步、拓展或进阶"
        "（严禁称赞‘又往前迈了一步’、‘有意识地拓展’、‘迈出了扎实一步’、‘迈得很自然’、‘进阶到’）；\n"
        "   - 严禁评价用户选择或研究方向的潜力"
        "（严禁输出‘很有科研潜力’、‘极具潜力’、‘有潜力’、‘很有科研前景’）；\n"
        "   - 严禁评价基础扎实度或起点"
        "（严禁称‘起点很扎实’、‘基础很稳’、‘很好的起点’、‘底子扎实’、‘基础扎实’、‘基础很棒’、‘打下了扎实基础’）；\n"
        "   - 严禁声称用户‘已掌握’、‘掌握了’、‘掌握的知识’、‘做过节点分类’或‘做过实验’；\n"
        "   - 严禁输出‘你已有的储备’、‘有看懂能力’、‘很懂’、‘说明你’、‘具备’、"
        "‘评测跑过’或‘跑通过流程’；\n"
        "   - 禁止把学习记录夸大为‘学会知识’、掌握度断言、理解程度断言、"
        "质量或起点评价（严禁称‘起点很扎实’）、实践经验断言或已跑通实验断言"
        "（严禁声称用户‘掌握了两大范式/核心机制’或‘完成了学习跨度’）；\n"
        "   - 严禁由已学内容或学习进度推断用户的掌握度、理解程度、认知框架、动手能力、"
        "实践经验、基本功、研究能力、研究入口或进阶路径评价"
        "（严禁声称用户‘已掌握’、‘已具备能力/入口’、‘说明基础扎实/很稳’、‘具备实践经验’、"
        "‘进阶到...’、‘迈得很自然’、‘学习路径成熟’、‘准备好进入更深入研究’、"
        "‘形成了认知框架/理解框架’、‘完成了学习跨度’、‘摸到了技术支线/脉络’、‘理解了机制’、"
        "‘打通任督二脉’、‘大概知道了怎么做’、‘已跑通流程’、‘至少跑通过流程’或‘硬核通行证’）；\n"
        "   - 严禁声称或断言用户‘做过实验’、‘跑通过流程’、‘接触了基础数据集’或‘已完成复现’；"
        "必须用提问向用户确认其实际实验和代码经验"
        "（例如：‘实际经验仍需你确认’、‘是否有实际运行训练流程的经历’）；\n"
        "   - 严禁在当前阶段下任何‘复现成功’、‘已完成复现’、‘跑通’或‘通过’的断言结论；\n"
        "   - 来源范围边界说明（source_scope 约束）：在展示推荐方向卡片或任何通用技术概览之前，"
        "必须首先包含如下自然语言说明：‘说明：以下内容基于学习端记录与通用技术概览，"
        "尚未执行正式检索；具体论文、实现细节和实验结论仍需在你确认后核验。’；\n"
        "   - 严禁使用任何 Emoji 图标"
        "（例如 😊、🚀、🔥、💡 等，只允许使用颜文字如 (｡･ω･｡)）。\n"
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
    )
    if extra_context:
        context += f"其他上下文：{extra_context}\n"

    rules = (
        "1. 梳理并明确具体研究问题与需求核心；\n"
        "2. 若用户选择的方向与前置知识跨度较大，温馨说明前置知识缺口并给出补学建议，"
        "但尊重用户的探索意愿，不阻止；\n"
        "3. 追问 1~2 个关键问题以收敛研究范围；禁止在信息模糊时盲目宣称需求已完成；\n"
        "4. 事实边界与严格学习记录模式约束（绝对遵守）：\n"
        "   - 提及学习记录时只能客观复述为‘学习端记录显示...，当前进度记录为...’，"
        "严禁任何推论、评价、赞美或意图升级；\n"
        "   - 严格学习记录模式：所有学习记录必须立即明确附带"
        "‘这些记录不等于掌握程度、代码经验或研究能力，仍需你确认’；\n"
        "   - 严禁评价用户的能力"
        "（严禁出现‘能力够得着’、‘能力适合’、‘能力足够’等任何关于用户能力的推测、假定或建议）；\n"
        "   - 严禁评价用户的学习进步、拓展或进阶"
        "（严禁称赞‘又往前迈了一步’、‘又迈了一步’、‘有意识地拓展’、‘进阶到’、‘迈得很自然’）；\n"
        "   - 严禁评价用户的选择或研究方向的潜力"
        "（严禁称‘很有科研潜力’、‘极具潜力’、‘很有潜力’、‘有潜力’、‘很有科研前景’）；\n"
        "   - 严禁评价用户基础扎实度或质量"
        "（严禁称‘起点很扎实’、‘基础很稳’、‘很好的起点’、‘基础扎实’、‘底子扎实’）；\n"
        "   - 严禁断言用户‘已掌握’、‘掌握了’、‘做过节点分类’或‘做过实验’；\n"
        "   - 严禁断言用户‘掌握了两大范式/核心算法’、‘完成了学习跨度’、‘起点很扎实’、‘基础很稳’、"
        "‘有了认知框架/理解框架’、‘摸到了技术支线/核心脉络’、‘理解了机制/原理’、‘准备好进入深入研究’、"
        "‘底子扎实’、‘基础扎实’、‘很懂’或‘具备入口’；\n"
        "   - 严禁声称或断言用户‘做过实验’、‘跑通过流程’、‘接触了基础数据集’或‘已完成复现’；\n"
        "   - 严禁在当前阶段下任何‘复现成功’、‘已完成复现’、‘跑通’或‘通过’的断言结论；\n"
        "   - 用户归因禁止（attribution 约束）：严禁把你自己提出的候选项（如 A/B/C 选项、示例、\n"
        "建议子方向）写成用户已确认或选定的事实；若用户未在消息中明确选择某选项，\n"
        "只能说‘请你选择/确认具体方向’，禁止使用‘根据你上一轮的选择（XXX）’这类措辞，\n"
        "除非用户消息中出现了 XXX 这个词；\n"
        "   - 来源范围边界说明（source_scope 约束）：若涉及推荐方向、"
        "算法机制说明（如邻居采样、归纳式表征）或通用技术概览，"
        "必须首先包含如下自然语言说明：‘说明：以下内容基于你提出的探索方向与通用技术概览，"
        "尚未执行正式检索；具体论文、实现细节和实验结论仍需在你确认后核验。’；\n"
        "   - 严禁使用任何 Emoji 图标（例如 😊、🚀、🔥、💡 等，只允许使用颜文字如 (｡･ω･｡)）。\n"
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
        "4. 不得保证设备一定可行或声称‘完全够用’；只能说明限制、条件与待验证的小规模替代方案；\n"
        "   不得使用‘能跑’、‘可以运行’、‘可行’等确定性硬件结论，即使搭配‘经典模型’也不例外；\n"
        "5. 事实边界与红线约束（绝对遵守）：\n"
        "   - 严禁出现‘核心判断’、‘当前聚焦于’、‘完成百分比’等空泛违约词；\n"
        "   - 严禁由前置学习记录推断用户的实践经验、掌握度或动手能力；\n"
        "   - 严禁在当前阶段下任何‘复现成功’、‘已完成复现’、‘跑通’或‘通过’的断言结论；\n"
        "   - 计划与建议请使用‘运行验证’或‘小规模测试’，严禁断言复现已完成；\n"
        "   - 最终文本不得出现‘复现成功’或‘成功复现’字样；只陈述限制、条件和待验证方案；\n"
        "   - 严禁使用任何 Emoji 图标（例如 😊、🚀、🔥、💡 等，只允许使用颜文字如 (｡･ω･｡)）。\n"
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
        "1. 本轮只做论文信息解读，不是复现实验；开头必须先说明未执行代码、未完成实验，"
        "不能得出复现成功结论。\n"
        "2. 严格按照五步桥梁结构介绍论文：\n"
        "   ① 研究问题：论文试图解决什么核心问题；\n"
        "   ② 核心创新点：论文提出了什么新思路/新结构；\n"
        "   ③ 核心方法：具体算法设计与技术要点（公式使用标准 LaTeX 书写）；\n"
        "   ④ 与用户目标的关系：这篇论文如何助力用户的研究需求；\n"
        "   ⑤ 复现难点与避坑提示：基于用户硬件与经验可能遇到的挑战。\n"
        "3. 严禁臆测论文未提供的内容；无法由标题、链接或摘要确认的细节必须标记为待核验；\n"
        "4. 不得评价用户的能力、基础、眼光或研究潜力，不得把学习记录改写为掌握度或实践经验；\n"
        "5. 不得保证设备可行或声称 CPU/GPU 一定能运行；不得使用‘能跑’、‘可以运行’、\n"
        "   ‘可行’等确定性硬件结论；\n"
        "6. 不得声称复现成功、实验完成或流程已跑通；与用户目标的关系只能作为待确认建议；\n"
        "7. 最终文本不得出现‘复现成功’或‘成功复现’字样；用‘尚待核验’描述复现关系；\n"
        "8. 不得使用‘掌握’‘基础’‘能力’‘经验’评价用户；只陈述论文材料和待核验项；\n"
        "9. 公式必须规范；严禁使用 Emoji。\n"
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
    plan_layer: str = "preliminary",
) -> dict[str, Any]:
    """Template 6: Experiment Design (实验方案，初步/具体两层).

    ``plan_layer="preliminary"`` produces the plain-language preliminary plan
    (what will be reproduced, which methods, what to prepare); it is generated
    only after the paper is selected and understood, and must be confirmed by
    the user before the specific plan is produced.  ``plan_layer="specific"``
    refines it into the concrete plan (model, data flow, code flow, schedule,
    tasks, acceptance checklist) and MUST inherit the confirmed stage-two
    overall plan instead of creating a conflicting second schedule.
    """
    paper_title = paper.title if paper else "未绑定特定论文"
    metrics_str = ", ".join(standard_metrics)
    profile_hw = profile.hardware or "未提供显存/设备"

    context = (
        f"【依托论文】\n{paper_title}\n\n"
        f"【用户硬件与条件】\n{profile_hw}\n\n"
        f"【白名单标准评估指标】\n{metrics_str}\n"
    )
    if plan_notes:
        context += f"\n【已确认的总体计划（第二阶段）】\n{plan_notes}\n"

    shared_rules = (
        "指标优先从标准指标目录选取；若有非标准指标需明确标注待核验 (to_verify)；\n"
        "方案必须考虑同学实际显存大小与计算资源，给出合适的 Batch Size 与训练轮次建议；\n"
        "严禁以 Accuracy、F1、Loss、论文基线值或任何数值区间定义、暗示或设定\n"
        "“复现成功 / 通过 / 达标”的指标阈值、区间或判定标准；\n"
        "论文报告值或预期指标只能表述为“论文报告的参考值”“基线参考区间”或\n"
        "“待核验的一致性对比”，不构成复现结论；\n"
        "即使后续实验数值接近论文基线，也不得输出“视为复现成功”或“判定复现成功”；\n"
        "必须明确写清：evidence_linked、指标接近、计划完成或记录完整均不代表复现成功；\n"
        "缺少可追溯结果时继续标记 to_verify 并追问；\n"
        "严禁断言百分之百复现或伪造实验准确率；严禁使用 Emoji。\n"
    )
    if plan_layer == "specific":
        task = "具体实验方案（细化模型、数据流、代码流程、实验日程、任务与验收标准）"
        rules = (
            "1. 本轮输出【具体实验方案】：在已确认的初步方案之上细化模型结构、数据流、\n"
            "   代码流程、实验日程、任务拆分与验收标准；方法与术语必须与依托论文一致；\n"
            "2. 日程必须继承【已确认的总体计划（第二阶段）】的时间安排；若提供了总体计划，\n"
            "   严禁生成与之冲突的第二套日程，只能在其框架内细化；未提供时先追问总体计划；\n"
            "3. 方案依据必须写清来自依托论文、用户画像、设备与可投入时间；信息不足时\n"
            "   逐项追问，不得编造；\n"
            "4. " + shared_rules
        )
    else:
        task = "初步实验方案（通俗说明准备复现什么、用到哪些方法、先做哪些准备）"
        rules = (
            "1. 本轮输出【初步实验方案】：用通俗语言说明准备复现什么、会用到哪些方法、\n"
            "   要先做哪些准备；不展开具体代码流程与逐日日程；\n"
            "2. 明确说明这是初步方案，需用户确认后才会细化为具体实验方案；\n"
            "3. 不得声称代码已执行、实验已完成、流程已跑通或复现成功；\n"
            "   所有准备项都还未发生，只描述计划；\n"
            "4. " + shared_rules
        )
    return {
        "template_name": "experiment_design",
        "plan_layer": plan_layer,
        "system": JIANGJIANG_SYSTEM_PERSONA,
        "task": task,
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
        "1. 开头必须说明‘当前仅分析待核验观测’，本轮不能得出复现成功结论；\n"
        "2. 客观分析用户实验指标与基线的差距，从超参数、数据划分等角度给出归因；\n"
        "3. 若用户提供的信息不完整（如缺少 loss 曲线、缺少测试集划分），明确追问缺失项；\n"
        "4. 事实边界与红线约束（绝对遵守）：\n"
        "   - 对信息不完整的输入，只写缺失字段、待核验项和下一步核对动作；\n"
        "   - 严禁声称、断言或判定当前实验“复现成功”、“成功复现”、"
        "“复现成立”、“已复现”或“确认复现”；\n"
        "   - 严禁宣称指标在某范围内“就可以视为复现成功”或“属于成功复现的合理范围”；\n"
        "   - 严禁伪造实验成功或声称复现已闭环，必须明确指出：指标接近论文不代表复现成功，"
        "仍需核验实验配置、随机种子、数据划分与多次运行方差；\n"
        "   - 优先使用“尚未形成可确认的复现结论”、“复现闭环尚待验证”等严谨客观表述；\n"
        "   - 最终文本不得出现‘复现成功’或‘成功复现’字样；只保留待核验与缺失信息；\n"
        "   - 严禁使用 Emoji 图标（如 😊、🚀、🎉 等，只允许颜文字如 (｡･ω･｡)）。\n"
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
        "3. 禁用空泛套话；事实边界与红线约束（绝对遵守）：\n"
        "   - 严禁断言“复现成功”、“已完成复现”或“跑通流程”；\n"
        "   - 严禁出现“核心判断”、“当前聚焦于”、“完成百分比”等违约词；\n"
        "   - 严禁由前置学习记录推断用户的实践经验、掌握度、基本功或动手能力；\n"
        "   - 仅客观复述用户确认与下一阶段规划，严禁评价用户的学习质量、基础扎实度、"
        "科研能力、潜力、准备度或进展程度（严禁称赞‘迈出了扎实一步’、‘迈出关键一步’、‘很有潜力’等）；\n"
        "   - 用户归因禁止（attribution 约束）：严禁把你自己提出的候选项（如 A/B/C 选项、示例、\n"
        "建议子方向）写成用户已确认或选定的事实；若用户未在消息中明确选择某选项，\n"
        "只能说“请你选择/确认具体方向”，禁止使用“根据你上一轮的选择（XXX）”这类措辞，\n"
        "除非用户消息中出现了 XXX 这个词；\n"
        "   - 来源范围边界说明（source_scope 约束）：若提及技术框架（如分子图表示、"
        "消息传递、整图读出、预测头）、设备配置影响或实验方案建议，"
        "必须在此类技术内容之前包含自然语言说明：‘说明：以下计划框架基于你刚确认的研究方向与通用技术概览，"
        "尚未执行正式检索；具体论文、实现细节、设备需求和实验结论仍需在你确认后核验。’；\n"
        "   - 严禁使用任何 Emoji 图标（例如 😊、🚀、🔥、💡 等，只允许使用颜文字如 (｡･ω･｡)）。\n"
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
