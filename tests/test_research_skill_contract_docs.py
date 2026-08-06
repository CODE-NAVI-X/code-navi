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
        ):
            assert phrase in document
