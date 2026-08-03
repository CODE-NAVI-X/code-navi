"""Deterministic, source-aware research mind-map construction."""

from __future__ import annotations

from .conversation_schemas import (
    ConversationEvidenceBundle,
    ConversationResearchPlan,
    ResearchMindMap,
    ResearchMindMapEdge,
    ResearchMindMapNode,
    ResearchMindMapSource,
    ResearchProfile,
)


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
    )
    _add_profile_node(
        nodes,
        edges,
        "method-data",
        "方法与数据",
        [*profile.methods, profile.data_requirements or ""],
        "方法、数据或样本条件尚待确认。",
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
    )
    edges.append(
        ResearchMindMapEdge(
            source_id="research-plan", target_id="to-verify", relation="保留不确定性"
        )
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

    for node_id in ("core-question", "method-data", "constraints", "expected-output"):
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


def _add_profile_node(
    nodes: list[ResearchMindMapNode],
    edges: list[ResearchMindMapEdge],
    node_id: str,
    label: str,
    values: list[str],
    missing_detail: str,
) -> None:
    non_blank = [value for value in values if value]
    _add(
        nodes,
        node_id,
        label,
        "confirmed" if non_blank else "to_verify",
        _join(non_blank) if non_blank else missing_detail,
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
) -> None:
    nodes.append(
        ResearchMindMapNode(
            id=node_id,
            label=_bounded(label, 500),
            status=status,
            detail=_bounded(detail, 1000),
            sources=sources or [],
        )
    )


def _join(values: object) -> str:
    return "；".join(_bounded(str(value), 240) for value in values if str(value).strip())


def _bounded(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 1]}…"
