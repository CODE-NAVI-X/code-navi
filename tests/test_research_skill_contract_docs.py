"""Keep the local research-demo Skill contracts and scope statements reviewable."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPOSITORY_ROOT / "src" / "code_navi" / "research" / "skills"

REQUIRED_CONTRACT_HEADINGS = (
    "版本",
    "输入与输出",
    "规则层与模型层边界",
    "权限、来源与副作用",
    "失败与规则降级",
    "测试样例",
    "外部参考与许可证",
)

SKILL_NAMES = (
    "research-clarification",
    "academic-search",
    "paper-analysis",
    "topic-difficulty-analysis",
    "experiment-design",
    "experiment-code-draft",
    "experiment-evidence",
    "paper-blueprint",
    "paper-draft-review",
    "paper-revision",
    "citation-scaffold",
    "paper-export",
    "submission-readiness",
    "research-mindmap",
    "reproduction-evaluation",
)


def test_research_skill_docs_declare_the_same_minimum_contract() -> None:
    for skill_name in SKILL_NAMES:
        content = (SKILL_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        for heading in REQUIRED_CONTRACT_HEADINGS:
            assert heading in content, f"{skill_name} 缺少 Skill 契约：{heading}"


def test_public_paper_skill_docs_keep_the_minimum_contract() -> None:
    for skill_name in (
        "paper_draft_review",
        "paper_revision",
        "citation_scaffold",
        "submission_readiness",
        "paper_export",
        "reproduction_evaluation",
    ):
        content = (REPOSITORY_ROOT / "docs" / "skills" / skill_name / "SKILL.md").read_text(
            encoding="utf-8"
        )
        for heading in REQUIRED_CONTRACT_HEADINGS:
            assert heading in content, f"{skill_name} 文档 Skill 缺少契约：{heading}"


def test_public_mindmap_skill_documents_the_focus_workspace_and_svg_limit() -> None:
    content = (REPOSITORY_ROOT / "docs" / "skills" / "research-mindmap" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    for phrase in (
        "摘要卡",
        "专注导图工作区",
        "@xyflow/react",
        "@dagrejs/dagre",
        "不联网",
        "不读论文全文",
        "不调用模型",
        "不写文件",
        "SVG",
        "PNG 尚未实现",
    ):
        assert phrase in content


def test_research_demo_docs_describe_the_closed_loop_and_non_goals() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    roadmap = (REPOSITORY_ROOT / "docs" / "product" / "roadmap.md").read_text(encoding="utf-8")

    for document in (readme, roadmap):
        for phrase in (
            "用户主动",
            "EvidenceBundle",
            "论文全文下载与精读",
            "自动检索",
            "自动写入项目",
            "自动安装依赖",
            "自动执行代码",
            "多 Agent/MCP",
            "PNG",
            "实验结果证据包",
            "论文蓝图",
            "结构化审稿",
            "修订任务",
            "投稿前检查",
            "受控导出",
            "引用占位",
        ):
            assert phrase in document


def test_external_skill_evaluation_records_adoption_boundaries() -> None:
    evaluation = (REPOSITORY_ROOT / "docs" / "research-skill-evaluation.md").read_text(
        encoding="utf-8"
    )
    evo_notes = (
        REPOSITORY_ROOT / "docs" / "references" / "evo_scientist_experiment_notes.md"
    ).read_text(encoding="utf-8")
    clarification_skill = (SKILL_ROOT / "research-clarification" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    for phrase in (
        "qinyan-academic-skills",
        "academic-research-skills",
        "苏格拉底",
        "不直接接入",
        "CC BY-NC 4.0",
        "五字段",
        "自动联网",
    ):
        assert phrase in evaluation
    for phrase in ("EvoScientist", "论文直接支持的事实", "设计推断", "仍需验证"):
        assert phrase in evo_notes
    for phrase in ("苏格拉底式", "一次只追问一个未确认维度"):
        assert phrase in clarification_skill


def test_paper_assistance_demo_checklist_covers_the_reviewable_local_flow() -> None:
    checklist = (
        REPOSITORY_ROOT / "docs" / "research-paper-assistance-demo-checklist.md"
    ).read_text(encoding="utf-8")

    for phrase in (
        "演示前置条件",
        "本地启动命令",
        "EvidenceBundle",
        "实验结果证据包",
        "结构化审稿",
        "逐段候选改写",
        "引用占位",
        "参考文献雏形",
        "投稿前检查",
        "Markdown / JSON",
        "不自动联网",
        "不自动写入",
        "不自动安装依赖",
        "不自动执行代码",
        "不自动投稿",
        "无 DeepSeek Key",
        "正式导出",
        "投稿适配",
        "文献管理",
        "实验材料整理",
    ):
        assert phrase in checklist
