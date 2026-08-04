import dagre from "@dagrejs/dagre";
import type { Edge, Node } from "@xyflow/react";

import type {
  ResearchMindMap,
  ResearchMindMapNode,
  ResearchMindMapNodeStatus,
} from "@/lib/api/research";

export const STATUS_LABEL: Record<ResearchMindMapNodeStatus, string> = {
  confirmed: "已确认",
  inference: "建议",
  to_verify: "待验证",
  evidence: "来源证据",
  risk: "风险",
};

export const STATUS_COLORS: Record<ResearchMindMapNodeStatus, { fill: string; stroke: string; text: string }> = {
  confirmed: { fill: "#d1fae5", stroke: "#059669", text: "#065f46" },
  inference: { fill: "#e0f2fe", stroke: "#0284c7", text: "#075985" },
  to_verify: { fill: "#fef3c7", stroke: "#d97706", text: "#92400e" },
  evidence: { fill: "#ede9fe", stroke: "#7c3aed", text: "#5b21b6" },
  risk: { fill: "#ffe4e6", stroke: "#e11d48", text: "#9f1239" },
};

export const MINDMAP_NODE_WIDTH = 236;
export const MINDMAP_NODE_HEIGHT = 96;

export type MindMapNodeData = {
  node: ResearchMindMapNode;
  isRoot: boolean;
};

export type MindMapFlowNode = Node<MindMapNodeData, "researchMindMap">;
export type MindMapFlowEdge = Edge<{ relation: string }>;

export type MindMapGraph = {
  nodes: MindMapFlowNode[];
  edges: MindMapFlowEdge[];
};

function escapeXml(value: string) {
  return value.replace(/[<>&"']/g, (character) => ({
    "<": "&lt;",
    ">": "&gt;",
    "&": "&amp;",
    '"': "&quot;",
    "'": "&apos;",
  })[character] ?? character);
}

function singleLine(value: string, maximum = 28) {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > maximum ? `${normalized.slice(0, maximum - 1)}…` : normalized;
}

/** Maps only the persisted research-mindmap.v1 edges into a Dagre hierarchy. */
export function layoutResearchMindMap(mindmap: ResearchMindMap): MindMapGraph {
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({ rankdir: "LR", ranksep: 84, nodesep: 34, marginx: 32, marginy: 32 });
  graph.setDefaultEdgeLabel(() => ({}));

  const nodeIds = new Set(mindmap.nodes.map((node) => node.id));
  for (const node of mindmap.nodes) {
    graph.setNode(node.id, { width: MINDMAP_NODE_WIDTH, height: MINDMAP_NODE_HEIGHT });
  }

  const persistedEdges = mindmap.edges.filter(
    (edge) => nodeIds.has(edge.source_id) && nodeIds.has(edge.target_id),
  );
  for (const edge of persistedEdges) {
    graph.setEdge(edge.source_id, edge.target_id);
  }
  dagre.layout(graph);

  const nodes: MindMapFlowNode[] = mindmap.nodes.map((node) => {
    const position = graph.node(node.id) as { x: number; y: number };
    return {
      id: node.id,
      type: "researchMindMap",
      position: {
        x: position.x - MINDMAP_NODE_WIDTH / 2,
        y: position.y - MINDMAP_NODE_HEIGHT / 2,
      },
      data: { node, isRoot: node.id === mindmap.root_node_id },
    };
  });

  const edges: MindMapFlowEdge[] = persistedEdges.map((edge) => ({
    id: `${edge.source_id}-${edge.target_id}`,
    source: edge.source_id,
    target: edge.target_id,
    label: edge.relation,
    data: { relation: edge.relation },
    type: "smoothstep",
    animated: false,
  }));

  return { nodes, edges };
}

/** Creates a self-contained SVG with the same boxes, colors, and persisted edges. */
export function buildResearchMindMapSvg(mindmap: ResearchMindMap) {
  const { nodes, edges } = layoutResearchMindMap(mindmap);
  const left = Math.min(...nodes.map((node) => node.position.x), 0) - 32;
  const top = Math.min(...nodes.map((node) => node.position.y), 0) - 32;
  const right = Math.max(...nodes.map((node) => node.position.x + MINDMAP_NODE_WIDTH), 760) + 32;
  const bottom = Math.max(...nodes.map((node) => node.position.y + MINDMAP_NODE_HEIGHT), 420) + 32;
  const byId = new Map(nodes.map((node) => [node.id, node]));

  const edgeSvg = edges.map((edge) => {
    const source = byId.get(edge.source);
    const target = byId.get(edge.target);
    if (!source || !target) return "";
    const startX = source.position.x + MINDMAP_NODE_WIDTH;
    const startY = source.position.y + MINDMAP_NODE_HEIGHT / 2;
    const endX = target.position.x;
    const endY = target.position.y + MINDMAP_NODE_HEIGHT / 2;
    const middleX = (startX + endX) / 2;
    return `<path d="M ${startX} ${startY} C ${middleX} ${startY}, ${middleX} ${endY}, ${endX} ${endY}" fill="none" stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"/>`;
  }).join("");

  const nodeSvg = nodes.map((flowNode) => {
    const { node, isRoot } = flowNode.data;
    const colors = STATUS_COLORS[node.status];
    const title = singleLine(node.label, 30);
    const status = STATUS_LABEL[node.status];
    return `<g><rect x="${flowNode.position.x}" y="${flowNode.position.y}" width="${MINDMAP_NODE_WIDTH}" height="${MINDMAP_NODE_HEIGHT}" rx="14" fill="${colors.fill}" stroke="${colors.stroke}" stroke-width="${isRoot ? 3 : 2}"/><text x="${flowNode.position.x + 16}" y="${flowNode.position.y + 38}" fill="${colors.text}" font-family="Arial, sans-serif" font-size="15" font-weight="700">${escapeXml(title)}</text><text x="${flowNode.position.x + 16}" y="${flowNode.position.y + 67}" fill="${colors.text}" font-family="Arial, sans-serif" font-size="12">${escapeXml(status)}</text></g>`;
  }).join("");

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${right - left}" height="${bottom - top}" viewBox="${left} ${top} ${right - left} ${bottom - top}" role="img" aria-label="研究思维导图"><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b"/></marker></defs><rect x="${left}" y="${top}" width="${right - left}" height="${bottom - top}" fill="#ffffff"/>${edgeSvg}${nodeSvg}</svg>`;
}
