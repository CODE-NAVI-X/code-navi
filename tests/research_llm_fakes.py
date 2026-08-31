"""Context-aware fake research-artifact generators for tests.

Each builder reads the validated context the service assembles and returns
schema-valid JSON, so tests exercise the real LLM-driven boundary checks
without any network or real provider.
"""

from __future__ import annotations

import json

from code_navi.research.research_artifact_llm import ArtifactLlmOutcome


class ContextAwareArtifactGenerator:
    """Return valid per-kind JSON built from the provided context."""

    def __init__(self, overrides: dict[str, ArtifactLlmOutcome] | None = None) -> None:
        self.overrides = overrides or {}
        self.calls: list[str] = []
        self.contexts: list[dict[str, object]] = []

    def generate(
        self,
        *,
        kind: str,
        context: dict[str, object],
        conversation_id: str,
    ) -> ArtifactLlmOutcome:
        self.calls.append(kind)
        self.contexts.append(context)
        if kind in self.overrides:
            return self.overrides[kind]
        builder = _BUILDERS.get(kind)
        if builder is None:
            return ArtifactLlmOutcome.failed(f"no fake builder for {kind}")
        return ArtifactLlmOutcome.generated(builder(context, conversation_id))


def _entry(content: str, classification: str = "inference") -> dict[str, str]:
    return {"content": content, "classification": classification, "basis": "模型基于已保存上下文。"}


def _contract_entry(content: str, classification: str = "inference") -> dict[str, str]:
    """Plan entry that satisfies the checkpoint-3 evidence contract."""
    return {
        **_entry(content, classification),
        "relevance": "与当前已确认研究问题直接相关。",
        "suggested_action": "先核对来源范围，再执行下一步。",
    }


def _topic(context: dict[str, object], conversation_id: str) -> str:
    scope = str(context.get("evidence_scope") or "profile_and_plan_only")
    return json.dumps(
        {
            "title": "模型难点分析",
            "information_scope": scope,
            "core_judgment": "当前画像已覆盖研究问题，实验设置与数据条件仍是主要缺口。",
            "items": [
                {
                    "area": "方法难点",
                    "content": "建议预先固定对照条件与可观察输出。",
                    "classification": "inference",
                    "basis": "已确认研究问题。",
                    "source_scope": "profile_and_plan_only",
                    "relevance": "决定两周 MVP 能否给出可信比较。",
                    "suggested_action": "在检索文献后固定一条对照实验设计。",
                },
                {
                    "area": "数据难点",
                    "content": "数据来源与许可待确认。",
                    "classification": "to_verify",
                    "basis": "当前画像未验证数据条件。",
                    "source_scope": "profile_and_plan_only",
                    "relevance": "影响全部训练与评估步骤的可行性。",
                    "suggested_action": "先确认数据来源和许可，再安排实验。",
                },
            ],
            "next_action": "补充数据条件后生成研究计划。",
            "provenance_note": "模型基于已确认画像生成。",
        },
        ensure_ascii=False,
    )


def _paper_analysis(context: dict[str, object], conversation_id: str) -> str:
    paper = context.get("paper") or {}
    abstract = bool(paper.get("abstract_excerpt"))
    full_text = bool(context.get("paper_reading"))
    scope = "full_text_user_triggered" if full_text else "metadata_and_abstract_only"
    return json.dumps(
        {
            "title": str(paper.get("title") or "模型分析"),
            "paper_url": str(paper.get("url") or ""),
            "information_scope": scope,
            "abstract_available": abstract,
            "core_judgment": "该论文与当前研究问题直接相关，但当前来源范围外的细节仍待核验。",
            "items": [
                {
                    "area": "方法难点",
                    "content": (
                        f"需结合论文《{paper.get('title') or '选中论文'}》"
                        "核验方法定义与对照条件。"
                    ),
                    "classification": "to_verify",
                    "basis": "仅元数据和摘要范围。",
                    "source_scope": scope,
                    "relevance": "决定当前复现任务的模型模块设计。",
                    "suggested_action": "先在元数据范围记录待核验的方法条件。",
                }
            ],
            "summary": "当前来源范围已覆盖问题定位；方法细节与实验设置仍需正文核验。",
            "next_action": "核对可复现部分后再决定是否读取正文。",
            "provenance_note": (
                "模型基于已保存论文正文片段生成。"
                if full_text
                else "模型基于已保存元数据/摘要生成。"
            ),
        },
        ensure_ascii=False,
    )


def _experiment(context: dict[str, object], conversation_id: str) -> str:
    verify = {"content": "样本量与许可待确认。", "classification": "to_verify", "basis": "约束。"}
    return json.dumps(
        {
            "hypothesis": _entry("建议检验可观察差异。"),
            "variables": [_entry("预先固定自变量。")],
            "data_sources": [verify],
            "baselines": [_entry("候选基线。")],
            "metrics": [verify],
            "steps": [_entry("第一周最小检查。")],
            "resources": [verify],
            "risks": [_entry("样本不足风险。")],
            "advisor_confirmation_items": [verify],
            "provenance_note": "模型基于已确认画像生成。",
        },
        ensure_ascii=False,
    )


def _code_draft(context: dict[str, object], conversation_id: str) -> str:
    return json.dumps(
        {
            "title": "实验代码草案预览",
            "directory_tree": ["README.md", "src/", "src/data.py", "data/"],
            "dependencies": ["Python 3.11+（未安装）"],
            "files": [
                {
                    "path": "src/data.py",
                    "content": "def load_data():\n    # TODO: 确认数据许可\n    return []\n",
                }
            ],
            "run_instructions": ["先人工确认 TODO。"],
            "assumptions": ["默认合成数据。"],
            "to_verify_items": ["真实数据许可待确认。"],
            "provenance_note": "模型生成预览；不执行代码。",
        },
        ensure_ascii=False,
    )


def _reproduction(context: dict[str, object], conversation_id: str) -> str:
    bundle = context.get("selected_evidence_bundle") or {}
    paper = bundle.get("paper") or {}
    scope = "profile_and_plan_only"

    def item(content: str, classification: str = "to_verify") -> dict[str, str]:
        return {
            "content": content,
            "classification": classification,
            "basis": "模型基于已保存上下文。",
            "source_scope": scope,
        }

    def task(task_id: str) -> dict[str, object]:
        return {
            "task_id": task_id,
            "title": f"任务 {task_id}",
            "description": "学习脚手架任务，不含可执行代码。",
            "classification": "inference",
            "basis": "模型生成的任务建议。",
            "source_scope": scope,
            "status": "not_started",
            "evidence_links": [],
        }

    # 用户条件不进入模型载荷：模型不能引入 fact；builder 会在校验后把
    # user_provided_conditions 的用户事实与验收条件占位补进 resources/goal。
    return json.dumps(
        {
            "schema_version": "reproduction-pipeline.v1",
            "pipeline_id": "pipeline-model",
            "conversation_id": conversation_id,
            "source_bundle_id": str(bundle.get("bundle_id") or ""),
            "selected_paper": {
                "url": str(paper.get("url") or ""),
                "title": str(paper.get("title") or ""),
                "source_name": str(paper.get("source_name") or "source"),
                "year": paper.get("year"),
                "identifier": paper.get("identifier"),
                "abstract_scope": "metadata_and_abstract",
                "abstract_excerpt": paper.get("abstract_excerpt"),
            },
            "reproduction_goal": item("定义可确认的复现目标。", "inference"),
            "research_question": item("研究问题。", "inference"),
            "known_method": item("方法细节待核验。"),
            "data_and_sample_conditions": [item("数据集与样本范围待核验。")],
            "candidate_baselines": [item("候选基线待确认。", "inference")],
            "metrics": [item("主指标与阈值待确认。")],
            "experiment_steps": [item("先记录输入与对照。", "inference")],
            "resources": [item("设备与时间待确认。")],
            "risks": [item("摘要不足以证明可复现性。")],
            "ethics": [item("数据治理与伦理待确认。")],
            "acceptance_criteria": [
                item(
                    "以论文原始基线为验收参照；数据划分、超参数与 Accuracy 数值保持待核验。"
                )
            ],
            "confirmation_items": [item("确认边界后再人工实验。")],
            "tasks": [task("confirm-python-environment"), task("compare-python-baseline")],
            "two_week_mvp": [item("两周 MVP 范围待确认。", "inference")],
            "created_at": "2026-08-15T00:00:00+00:00",
            "provenance_note": "模型生成；边界由规则校验。",
        },
        ensure_ascii=False,
    )


def _blueprint(context: dict[str, object], conversation_id: str) -> str:
    refs = context.get("allowed_evidence_references") or []
    academic = [
        r for r in refs if isinstance(r, dict) and r.get("source_type") == "academic_evidence"
    ]
    experiment = [
        r for r in refs if isinstance(r, dict) and r.get("source_type") == "experiment_evidence"
    ]

    def section(
        name: str,
        goal: str,
        evidence: list[dict[str, object]] | None = None,
        citations: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        return {
            "section": name,
            "writing_goal": _entry(goal),
            "evidence_references": evidence or [],
            "missing_evidence": [_entry("补充待核验证据。", "to_verify")],
            "forbidden_claims": [],
            "citation_placeholders": citations or [],
        }

    sections = [
        section("引言", "说明研究问题与边界。"),
        section("相关工作", "整理已保存来源。", evidence=academic, citations=academic),
        section("方法", "描述方法。"),
        section("实验", "报告实验。", evidence=experiment),
        section("讨论", "讨论。"),
        section("结论", "结论。"),
    ]
    return json.dumps(
        {
            "schema_version": "paper-blueprint.v1",
            "conversation_id": conversation_id,
            "candidate_titles": [_entry("候选标题")],
            "target_submission_direction": _entry("目标方向待确认。", "to_verify"),
            "abstract_requirements": [_entry("a"), _entry("b"), _entry("c"), _entry("d")],
            "sections": sections,
            "submission_readiness": _entry("尚未投稿就绪。", "to_verify"),
            "gaps": [_entry("缺口。")],
            "provenance_note": "模型生成。",
        },
        ensure_ascii=False,
    )


def _review(context: dict[str, object], conversation_id: str) -> str:
    findings = context.get("rule_findings") or []
    explanations = [
        {
            "finding_id": str(f.get("id")),
            "why_it_matters": str(f.get("why_it_matters") or "该问题影响证据可追溯性。"),
            "recommended_action": str(f.get("recommended_action") or "保留待验证占位。"),
        }
        for f in findings
        if isinstance(f, dict)
    ]
    return json.dumps({"explanations": explanations}, ensure_ascii=False)


def _revision_suggestion(context: dict[str, object], conversation_id: str) -> str:
    candidate = str(context.get("rules_candidate") or "[待补充实验结果]")
    return json.dumps(
        {
            "candidate_text": candidate,
            "rationale": "模型确认候选并保持事实边界。",
            "to_verify_items": [],
        },
        ensure_ascii=False,
    )


def _understanding_question(context: dict[str, object], conversation_id: str) -> str:
    paper = context.get("paper") or {}
    title = str(paper.get("title") or "")
    section_key = str(context.get("section_key") or "research_question")
    source_scope = str(context.get("source_scope") or "metadata_only")
    if "Graph Convolutional" in title:
        question = "用你自己的话说说 GCN 在 Cora 上要解决什么问题？"
        basis = "依据：摘要（fact）指向半监督节点分类；Cora 划分与 Accuracy 为 to_verify。"
    else:
        question = f"用你自己的话说说当前章节（{section_key}）要解决什么问题？"
        basis = "依据来自来源摘要/元数据（fact/inference）；全文细节为 to_verify。"
    return json.dumps(
        {
            "question": question,
            "question_basis": basis,
            "source_scope": source_scope,
            "example": None,
        },
        ensure_ascii=False,
    )


def _understanding_assessment(context: dict[str, object], conversation_id: str) -> str:
    answer = str(context.get("user_answer") or "")
    understood = any(token in answer for token in ("半监督", "节点分类", "图卷积", "GCN"))
    level = "understood" if understood else "needs_explanation"
    if understood:
        return json.dumps(
            {
                "assessment": "你正确说明了论文要解决的核心问题；数据集划分与 Accuracy 仍需核验。",
                "correct_points": ["论文面向半监督节点分类任务"],
                "missing_points": [],
                "explanation": "GCN 通过邻接矩阵归一化传播标签信息，适合标注稀缺的图数据。",
                "example": "在 Cora 引文网络上，少量标注节点借助图结构传播标签。",
                "recommended_next_action": "进入下一章节",
                "assessment_level": level,
            },
            ensure_ascii=False,
        )
    return json.dumps(
        {
            "assessment": "回答未覆盖论文要解决的核心问题，请补充半监督节点分类的目标。",
            "correct_points": [],
            "missing_points": ["需要说明论文要解决的核心问题"],
            "explanation": None,
            "example": None,
            "recommended_next_action": "重新回答本节",
            "assessment_level": level,
        },
        ensure_ascii=False,
    )


def _research_mindmap(context: dict[str, object], conversation_id: str) -> str:
    nodes = context.get("program_owned_nodes") or []
    return json.dumps(
        {
            "node_details": [
                {
                    "id": str(node.get("id") or ""),
                    "detail": f"围绕{node.get('label') or '当前节点'}整理已保存范围内的信息。",
                }
                for node in nodes
                if isinstance(node, dict)
            ],
            "recommended_next_action": "由用户确认一个待核验项后再继续。",
        },
        ensure_ascii=False,
    )


def _research_plan(context: dict[str, object], conversation_id: str) -> str:
    return json.dumps(
        {
            "research_title": _contract_entry("模型生成的研究题目。"),
            "research_goal": _contract_entry("模型生成的研究目标。"),
            "candidate_methods_or_baselines": [_contract_entry("模型生成的候选方法。")],
            "suggested_datasets_or_metrics": [
                _contract_entry("数据与指标待核验。", "to_verify")
            ],
            "two_week_mvp_plan": [_contract_entry("模型生成的两周验证步骤。")],
            "risks_and_mitigations": [
                {
                    "risk": _contract_entry("模型生成的风险。", "to_verify"),
                    "mitigation": _contract_entry("模型生成的规避建议."),
                }
            ],
            "suggested_search_keywords": ["模型生成关键词"],
            "pending_items": [],
            "core_judgment": "画像已达到计划准入条件；数据条件仍需核验。",
            "next_action": "由用户主动发起受限检索并保存论文。",
            "provenance_note": "模型生成。",
        },
        ensure_ascii=False,
    )


_BUILDERS = {
    "topic_difficulty_analysis": _topic,
    "paper_analysis": _paper_analysis,
    "experiment_design": _experiment,
    "experiment_code_draft": _code_draft,
    "reproduction_pipeline": _reproduction,
    "paper_blueprint": _blueprint,
    "paper_review": _review,
    "revision_suggestion": _revision_suggestion,
    "understanding_question": _understanding_question,
    "understanding_assessment": _understanding_assessment,
    "research_mindmap": _research_mindmap,
    "research_plan": _research_plan,
}
