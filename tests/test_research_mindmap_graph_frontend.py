"""Static contract checks for the interactive research mind-map frontend."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "frontend" / "components" / "research" / "ResearchMindMapPanel.tsx"
GRAPH = ROOT / "frontend" / "components" / "research" / "researchMindMapGraph.ts"


def test_mindmap_uses_real_graph_nodes_edges_and_hierarchical_layout() -> None:
    panel_source = PANEL.read_text(encoding="utf-8")
    graph_source = GRAPH.read_text(encoding="utf-8")

    assert "@xyflow/react" in panel_source
    assert "ReactFlow" in panel_source
    assert "onNodeClick" in panel_source
    assert "@dagrejs/dagre" in graph_source
    assert "dagre.layout" in graph_source
    assert "source: edge.source_id" in graph_source
    assert "target: edge.target_id" in graph_source


def test_mindmap_preserves_status_boundaries_sources_and_real_svg_geometry() -> None:
    panel_source = PANEL.read_text(encoding="utf-8")
    graph_source = GRAPH.read_text(encoding="utf-8")

    for label in ("已确认", "建议", "待验证", "来源证据", "风险"):
        assert label in graph_source
    assert "target=\"_blank\"" in panel_source
    assert "rel=\"noreferrer\"" in panel_source
    assert "source.label" in panel_source
    assert "source.accessed_at" in panel_source
    assert "已保存来源范围" in panel_source
    assert "<rect" in graph_source
    assert "<path" in graph_source
    assert "结构化节点清单" not in graph_source
    assert "fetch(" not in panel_source


def test_mindmap_uses_a_summary_then_focus_workspace_with_an_on_demand_drawer() -> None:
    panel_source = PANEL.read_text(encoding="utf-8")
    graph_source = GRAPH.read_text(encoding="utf-8")

    for phrase in ("展开科研导图", "状态筛选", "适配画布", "关闭详情", "导出 SVG"):
        assert phrase in panel_source
    assert "useState<string | null>(null)" in panel_source
    assert "h-[420px]" in panel_source
    assert "sm:h-[540px]" in panel_source
    assert "fitView" in panel_source
    assert "event.stopPropagation()" in panel_source
    assert "positionOverrides" in panel_source
    assert "onNodeDragStop" in panel_source
    assert "summary" in panel_source
    assert "nodeTier" in graph_source
    assert "primary" in graph_source
    assert "secondary" in graph_source
    assert "width: dimensions.width" in graph_source
    assert "return { ...TIER_DIMENSIONS[tier] }" in graph_source
