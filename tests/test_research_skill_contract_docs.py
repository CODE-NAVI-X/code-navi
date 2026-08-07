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
    "research-mindmap",
)


def test_research_skill_docs_declare_the_same_minimum_contract() -> None:
    for skill_name in SKILL_NAMES:
        content = (SKILL_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        for heading in REQUIRED_CONTRACT_HEADINGS:
            assert heading in content, f"{skill_name} 缺少 Skill 契约：{heading}"


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
        ):
            assert phrase in document


def test_external_skill_evaluation_records_adoption_boundaries() -> None:
    evaluation = (
        REPOSITORY_ROOT / "docs" / "research-skill-evaluation.md"
    ).read_text(encoding="utf-8")
    evo_notes = (
        REPOSITORY_ROOT / "docs" / "references" / "evo_scientist_experiment_notes.md"
    ).read_text(encoding="utf-8")
    clarification_skill = (
        SKILL_ROOT / "research-clarification" / "SKILL.md"
    ).read_text(encoding="utf-8")

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
