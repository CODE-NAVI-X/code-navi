"""Deterministic, source-aware research mind-map construction."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from .conversation_schemas import (
    ConversationEvidenceBundle,
    ConversationResearchPlan,
    ExperimentEvidenceBundle,
    PaperAnalysis,
    ResearchMindMap,
    ResearchMindMapEdge,
    ResearchMindMapNode,
    ResearchMindMapSource,
    ResearchProfile,
    UnderstandingCheck,
)
from .research_artifact_llm import ResearchArtifactGenerator
from .research_generation import ResearchGenerationError, require_generated_artifact


def build_research_mindmap(
    profile: ResearchProfile,
    *,
    plan: ConversationResearchPlan | None,
    evidence_bundles: list[ConversationEvidenceBundle],
) -> ResearchMindMap:
    """Build a graph from saved state only; never access a model or the network."""
    nodes: list[ResearchMindMapNode] = []
    edges: list[ResearchMindMapEdge] = []

    _add(
        nodes,
        "topic",
        profile.topic or "研究主题待确认",
        "confirmed" if profile.topic else "to_verify",
        "用户已确认的主题" if profile.topic else "需要先补充研究对象或现象。",
    )
    _add_profile_node(
        nodes,
        edges,
        "core-question",
        "核心问题",
        profile.research_questions or profile.candidate_questions,
        "研究问题尚待确认；当前不能把主题当作问题。",
        section_key="research_question",
    )
    _add_profile_node(
        nodes,
        edges,
        "method-data",
        "方法与数据",
        [*profile.methods, profile.data_requirements or ""],
        "方法、数据或样本条件尚待确认。",
        section_key="core_method",
    )
    _add_profile_node(
        nodes,
        edges,
        "constraints",
        "约束条件",
        profile.constraints,
        "时间、资源、伦理或范围约束尚待确认。",
    )
    _add_profile_node(
        nodes,
        edges,
        "expected-output",
        "预期交付物",
        [profile.expected_output or ""],
        "预期交付物尚待确认。",
    )
    _add_profile_node(
        nodes,
        edges,
        "background-motivation",
        "研究背景与动机",
        [profile.context or ""],
        "研究背景与动机仍待用户或导师补充。",
    )

    if plan is not None:
        _add(
            nodes,
            "research-plan",
            "规则研究计划",
            "inference",
            "由已确认科研画像离线整理的建议，不是已验证结论。",
        )
        edges.append(
            ResearchMindMapEdge(
                source_id="topic", target_id="research-plan", relation="形成建议计划"
            )
        )
        _add(
            nodes,
            "risks",
            "主要风险与规避",
            "risk",
            _join(item.risk.content for item in plan.risks_and_mitigations),
        )
        edges.append(
            ResearchMindMapEdge(
                source_id="research-plan", target_id="risks", relation="需要先处理的风险"
            )
        )
        pending_values = [entry.content for entry in plan.pending_items]
    else:
        _add(
            nodes,
            "research-plan",
            "研究计划待准备",
            "to_verify",
            "科研画像尚未达到生成结构化研究计划的建议条件。",
        )
        edges.append(
            ResearchMindMapEdge(
                source_id="topic", target_id="research-plan", relation="等待画像完善"
            )
        )
        pending_values = []

    pending_values.extend(profile.uncertainties)
    _add(
        nodes,
        "to-verify",
        "待验证项",
        "to_verify",
        _join(pending_values)
        if pending_values
        else "当前未记录额外待验证项；仍需人工核验所有建议。",
        section_key="to_verify",
    )
    edges.append(
        ResearchMindMapEdge(
            source_id="research-plan", target_id="to-verify", relation="保留不确定性"
        )
    )

    _add(
        nodes,
        "dataset",
        "数据集与数据条件",
        "confirmed" if profile.data_requirements else "to_verify",
        profile.data_requirements or "数据集、划分、许可与可得性均待核验。",
    )
    _add(
        nodes,
        "experiment",
        "实验设计",
        "inference" if plan is not None else "to_verify",
        "研究计划中的实验步骤是建议；尚未执行、也不代表实验结果。"
        if plan is not None
        else "需要先形成研究计划，再由用户确认实验设计。",
    )
    _add(
        nodes,
        "metrics",
        "指标与评价",
        "to_verify",
        "指标、数据划分、阈值与 Accuracy 等数值必须由原文或实验记录核验。",
    )
    _add(
        nodes,
        "contribution",
        "可能贡献",
        "to_verify",
        "贡献需要在明确对照、证据和人工判断后再表述，当前不能作为事实。",
    )
    _add(
        nodes,
        "limitations",
        "局限与风险",
        "to_verify",
        "当前只可列出待核验的限制；不能由摘要或建议推断实验结论。",
    )
    _add(
        nodes,
        "reproduction",
        "复现边界",
        "to_verify",
        "尚未运行论文代码、安装依赖或验证指标；仅可生成待人工核对的复现计划。",
    )
    _add(
        nodes,
        "user-evidence",
        "用户实验记录",
        "to_verify",
        "尚无用户主动提交的实验记录。",
        section_key="experiment_evidence",
    )
    _add(
        nodes,
        "next-step",
        "唯一下一步",
        "inference",
        "先确认当前缺失信息，再由用户主动检索或保存论文来源。",
    )

    evidence_count = _add_evidence_nodes(nodes, edges, evidence_bundles)
    if evidence_count:
        edges.append(
            ResearchMindMapEdge(
                source_id="research-plan",
                target_id="literature-evidence",
                relation="关联已保存证据",
            )
        )

    for node_id in (
        "core-question", "method-data", "background-motivation", "constraints", "expected-output",
        "dataset", "experiment", "metrics", "contribution", "limitations", "reproduction",
        "user-evidence", "next-step",
    ):
        edges.append(
            ResearchMindMapEdge(source_id="topic", target_id=node_id, relation="研究画像维度")
        )
    return ResearchMindMap(
        root_node_id="topic",
        nodes=nodes,
        edges=edges,
        provenance_note=(
            "导图只读取已校验的科研画像、规则研究计划与已保存的 EvidenceBundle；"
            "不访问模型或网络。来源节点只代表已保存的元数据/摘要范围，不表示已阅读全文或验证论文结论。"
        ),
    )


def build_generated_research_mindmap(
    profile: ResearchProfile,
    *,
    plan: ConversationResearchPlan | None,
    evidence_bundles: list[ConversationEvidenceBundle],
    generator: ResearchArtifactGenerator | None,
    conversation_id: str | None,
    paper_analysis: PaperAnalysis | None = None,
    understanding_checks: list[UnderstandingCheck] | None = None,
    experiment_evidence: list[ExperimentEvidenceBundle] | None = None,
) -> ResearchMindMap:
    """Generate source-bounded prose for a program-owned research map."""
    if generator is None:
        raise ResearchGenerationError(
            "provider_unavailable", "research_mindmap: generator is unavailable"
        )
    if conversation_id is None:
        raise ValueError("conversation_id is required for model mind-map generation")

    base = _with_user_evidence(
        build_research_mindmap(profile, plan=plan, evidence_bundles=evidence_bundles),
        experiment_evidence or [],
    )
    context = {
        "profile": profile.model_dump(mode="json"),
        "research_plan": plan.model_dump(mode="json") if plan else None,
        "saved_papers": _saved_paper_context(evidence_bundles),
        "paper_analysis": paper_analysis.model_dump(mode="json") if paper_analysis else None,
        "understanding_checks": [
            check.model_dump(mode="json") for check in (understanding_checks or [])
        ],
        "experiment_evidence": [
            item.model_dump(mode="json") for item in (experiment_evidence or [])
        ],
        "program_owned_nodes": [
            {"id": node.id, "label": node.label, "status": node.status, "detail": node.detail}
            for node in base.nodes
        ],
        "source_boundary": {
            "model_may_only": ["rewrite node detail", "recommend one next action"],
            "program_controls": ["node id", "label", "status", "section key", "sources", "edges"],
            "forbidden": [
                "不得新增事实、论文全文内容、实验结果或复现成功。",
                "不得改变来源范围、用户归属、DOM 锚点或节点关系。",
            ],
        },
        "required_json_shape": {
            "node_details": [{"id": "known node id", "detail": "source-bounded text"}],
            "recommended_next_action": "one user-controlled action",
        },
    }
    outcome = generator.generate(
        kind="research_mindmap", context=context, conversation_id=conversation_id
    )
    try:
        payload = json.loads(require_generated_artifact(outcome, kind="research_mindmap"))
        if not isinstance(payload, dict) or not isinstance(payload.get("node_details"), list):
            raise ValueError("mindmap output is missing node_details")
        allowed_ids = {node.id for node in base.nodes}
        updates: dict[str, str] = {}
        for item in payload["node_details"]:
            if not isinstance(item, dict):
                raise ValueError("mindmap node detail must be an object")
            node_id, detail = item.get("id"), item.get("detail")
            if not isinstance(node_id, str) or node_id not in allowed_ids:
                raise ValueError("model supplied an unknown mindmap node id")
            if node_id in updates or not isinstance(detail, str) or not detail.strip():
                raise ValueError("model supplied an invalid mindmap node detail")
            updates[node_id] = _bounded(detail, 1000)
        next_action = payload.get("recommended_next_action")
        if next_action is not None and (
            not isinstance(next_action, str) or not next_action.strip()
        ):
            raise ValueError("model supplied an invalid next action")
        nodes = [
            node.model_copy(update={"detail": updates.get(node.id, node.detail)})
            for node in base.nodes
        ]
        if isinstance(next_action, str):
            nodes = [
                node.model_copy(update={"detail": _bounded(next_action, 1000)})
                if node.id == "next-step"
                else node
                for node in nodes
            ]
        return base.model_copy(
            update={
                "nodes": nodes,
                "generation_mode": "llm",
                "run_id": outcome.run_id,
                "event_count": outcome.event_count,
                "generated_at": datetime.now(UTC),
                "provenance_note": (
                    "本导图由模型仅根据已保存科研画像、规则计划、EvidenceBundle、"
                    "已保存分析与用户实验记录组织；程序固定节点、状态、来源与跳转锚点。"
                    "不联网、不下载论文全文、不读取私有文件、不执行代码；待核验项不代表事实或复现成功。"
                ),
            }
        )
    except ResearchGenerationError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ResearchGenerationError(
            "invalid_output", "research_mindmap: boundary validation failed"
        ) from error


def _with_user_evidence(
    mindmap: ResearchMindMap,
    evidence: list[ExperimentEvidenceBundle],
) -> ResearchMindMap:
    if not evidence:
        return mindmap
    return mindmap.model_copy(
        update={
            "nodes": [
                node.model_copy(
                    update={
                        "status": "evidence",
                        "detail": (
                            "存在用户主动提交的实验记录；"
                            "该关联不代表实验正确、复现完成或复现成功。"
                        ),
                    }
                )
                if node.id == "user-evidence"
                else node
                for node in mindmap.nodes
            ]
        }
    )


def _saved_paper_context(
    bundles: list[ConversationEvidenceBundle],
) -> list[dict[str, object]]:
    return [
        {
            "bundle_id": bundle.bundle_id,
            "title": paper.title,
            "url": paper.url,
            "source_name": paper.source_name,
            "abstract_excerpt": paper.abstract_excerpt,
            "information_scope": paper.information_scope,
        }
        for bundle in bundles
        for paper in bundle.papers
    ][:8]


def _add_profile_node(
    nodes: list[ResearchMindMapNode],
    edges: list[ResearchMindMapEdge],
    node_id: str,
    label: str,
    values: list[str],
    missing_detail: str,
    *,
    section_key: str | None = None,
) -> None:
    non_blank = [value for value in values if value]
    _add(
        nodes,
        node_id,
        label,
        "confirmed" if non_blank else "to_verify",
        _join(non_blank) if non_blank else missing_detail,
        section_key=section_key,
    )


def _add_evidence_nodes(
    nodes: list[ResearchMindMapNode],
    edges: list[ResearchMindMapEdge],
    bundles: list[ConversationEvidenceBundle],
) -> int:
    papers = [paper for bundle in bundles for paper in bundle.papers][:6]
    if not papers:
        return 0
    _add(
        nodes,
        "literature-evidence",
        "已保存的文献证据",
        "evidence",
        "仅展示用户已显式触发并保存的指定学术来源元数据与摘要。",
    )
    for index, paper in enumerate(papers, start=1):
        node_id = f"evidence-{index}"
        _add(
            nodes,
            node_id,
            paper.title,
            "evidence",
            paper.abstract_excerpt or "来源仅提供论文元数据；摘要不可用。",
            sources=[
                ResearchMindMapSource(
                    label=f"{paper.source_name}（{paper.information_scope}）",
                    url=paper.url,
                    accessed_at=paper.accessed_at,
                )
            ],
        )
        edges.append(
            ResearchMindMapEdge(
                source_id="literature-evidence", target_id=node_id, relation="来源元数据或摘要"
            )
        )
    return len(papers)


def _add(
    nodes: list[ResearchMindMapNode],
    node_id: str,
    label: str,
    status: str,
    detail: str,
    *,
    sources: list[ResearchMindMapSource] | None = None,
    section_key: str | None = None,
) -> None:
    nodes.append(
        ResearchMindMapNode(
            id=node_id,
            label=_bounded(label, 500),
            status=status,
            detail=_bounded(detail, 1000),
            section_key=section_key,
            sources=sources or [],
        )
    )


def _join(values: object) -> str:
    return "；".join(_bounded(str(value), 240) for value in values if str(value).strip())


def _bounded(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 1]}…"
