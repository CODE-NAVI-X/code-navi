"use client";

import { Component, type ReactNode, useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Download, Link as LinkIcon, Network } from "lucide-react";

import type { ResearchMindMap, ResearchMindMapNode } from "@/lib/api/research";

import {
  buildResearchMindMapSvg,
  layoutResearchMindMap,
  STATUS_COLORS,
  STATUS_LABEL,
  type MindMapFlowNode,
} from "./researchMindMapGraph";

const STATUS_STYLE = {
  confirmed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300",
  inference: "bg-sky-100 text-sky-800 dark:bg-sky-950/50 dark:text-sky-300",
  to_verify: "bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300",
  evidence: "bg-violet-100 text-violet-800 dark:bg-violet-950/50 dark:text-violet-300",
  risk: "bg-rose-100 text-rose-800 dark:bg-rose-950/50 dark:text-rose-300",
};

function downloadSvg(mindmap: ResearchMindMap) {
  const url = URL.createObjectURL(new Blob([buildResearchMindMapSvg(mindmap)], { type: "image/svg+xml" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "research-mindmap.svg";
  anchor.click();
  URL.revokeObjectURL(url);
}

function NodeDetails({ node }: { node: ResearchMindMapNode }) {
  return (
    <aside className="rounded-xl border border-slate-200 bg-slate-50/80 p-3 text-xs dark:border-zinc-800 dark:bg-zinc-950/50">
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-semibold text-slate-900 dark:text-zinc-100">{node.label}</h3>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${STATUS_STYLE[node.status]}`}>{STATUS_LABEL[node.status]}</span>
      </div>
      <p className="mt-2 leading-5 text-slate-600 dark:text-zinc-400">{node.detail}</p>
      <p className="mt-2 text-[10px] leading-4 text-slate-500 dark:text-zinc-500">事实边界：{STATUS_LABEL[node.status]}。{node.status === "evidence" ? "仅代表已保存的来源元数据或摘要范围。" : "不代表未经保存来源验证的论文事实。"}</p>
      {node.sources.length > 0 ? (
        <div className="mt-3 space-y-2 border-t border-slate-200 pt-2 dark:border-zinc-800">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-zinc-500">来源（仅点击后在新标签页打开）</p>
          {node.sources.map((source) => (
            <a key={`${source.url}-${source.accessed_at}`} href={source.url} target="_blank" rel="noreferrer" className="flex items-start gap-1 text-teal-700 underline dark:text-teal-300">
              <LinkIcon className="mt-0.5 h-3 w-3 shrink-0" />
              <span>{source.label} · {new Date(source.accessed_at).toLocaleString()}</span>
            </a>
          ))}
        </div>
      ) : <p className="mt-3 text-[10px] text-slate-500 dark:text-zinc-500">暂无外部来源；此节点仅来自已保存画像或规则计划。</p>}
    </aside>
  );
}

function ResearchMapNode({ data }: NodeProps<MindMapFlowNode>) {
  const { node, isRoot } = data;
  const colors = STATUS_COLORS[node.status];
  return (
    <div className="min-w-[236px] rounded-xl border-2 px-3 py-2 shadow-sm" style={{ backgroundColor: colors.fill, borderColor: colors.stroke, color: colors.text, boxShadow: isRoot ? `0 0 0 3px ${colors.stroke}33` : undefined }}>
      <Handle type="target" position={Position.Left} className="!border-0 !bg-transparent" />
      <p className="line-clamp-2 text-xs font-bold leading-5">{node.label}</p>
      <span className="mt-2 inline-flex rounded-full bg-white/70 px-2 py-0.5 text-[10px] font-semibold">{STATUS_LABEL[node.status]}</span>
      <Handle type="source" position={Position.Right} className="!border-0 !bg-transparent" />
    </div>
  );
}

const nodeTypes = { researchMindMap: ResearchMapNode };

function InteractiveMindMap({ mindmap }: { mindmap: ResearchMindMap }) {
  const graph = useMemo(() => layoutResearchMindMap(mindmap), [mindmap]);
  const [nodes, setNodes, onNodesChange] = useNodesState<MindMapFlowNode>(graph.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(graph.edges);
  const [selectedNodeId, setSelectedNodeId] = useState(mindmap.root_node_id);
  const selectedNode = mindmap.nodes.find((node) => node.id === selectedNodeId)
    ?? mindmap.nodes.find((node) => node.id === mindmap.root_node_id)
    ?? mindmap.nodes[0];

  useEffect(() => {
    setNodes(graph.nodes);
    setEdges(graph.edges);
  }, [graph, setEdges, setNodes]);

  return (
    <div className="mt-4 grid gap-3 xl:grid-cols-[minmax(0,1fr)_17rem]">
      <div className="min-h-[460px] overflow-hidden rounded-xl border border-slate-200 bg-slate-950 dark:border-zinc-800" aria-label="可交互研究思维导图">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={(_, clickedNode) => setSelectedNodeId(clickedNode.id)}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.22 }}
          minZoom={0.25}
          maxZoom={1.8}
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable
          proOptions={{ hideAttribution: true }}
          defaultEdgeOptions={{ style: { stroke: "#94a3b8", strokeWidth: 2 } }}
        >
          <Background color="#334155" gap={18} size={1} />
          <Controls className="!border-slate-700 !bg-slate-900 !fill-slate-100" />
          <MiniMap nodeColor="#14b8a6" className="!border-slate-700 !bg-slate-900" maskColor="rgba(15, 23, 42, 0.55)" />
        </ReactFlow>
      </div>
      {selectedNode ? <NodeDetails node={selectedNode} /> : null}
    </div>
  );
}

function MindMapFallback({ mindmap }: { mindmap: ResearchMindMap }) {
  return (
    <div className="mt-4">
      <p className="rounded-xl border border-amber-200 bg-amber-50/70 p-3 text-[11px] leading-5 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-200">交互导图本地渲染不可用，已回退到节点详情清单；不会联网。</p>
      <ul className="mt-3 space-y-2">
        {mindmap.nodes.map((node) => <li key={node.id}><NodeDetails node={node} /></li>)}
      </ul>
    </div>
  );
}

class MindMapRendererBoundary extends Component<{ children?: ReactNode; fallback: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    return this.state.hasError ? this.props.fallback : this.props.children;
  }
}

export function ResearchMindMapPanel({ mindmap }: { mindmap: ResearchMindMap }) {
  return (
    <section className="rounded-2xl border border-teal-200 bg-white p-4 shadow-sm dark:border-teal-900/70 dark:bg-zinc-900/80">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="rounded-xl bg-teal-100 p-2 text-teal-700 dark:bg-teal-950/50 dark:text-teal-300"><Network className="h-4 w-4" /></span>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">Research mind map</p>
            <h2 className="mt-1 text-sm font-bold text-slate-900 dark:text-zinc-100">研究思维导图</h2>
          </div>
        </div>
        <button type="button" onClick={() => downloadSvg(mindmap)} className="inline-flex items-center gap-1 rounded-lg border border-teal-200 px-2 py-1 text-[11px] font-medium text-teal-800 hover:bg-teal-50 dark:border-teal-900 dark:text-teal-300 dark:hover:bg-teal-950/30">
          <Download className="h-3.5 w-3.5" /> 导出 SVG
        </button>
      </div>
      <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50/70 p-3 text-[11px] leading-5 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-200">
        此导图只整理已保存画像、规则计划与已有证据包；不联网、不调用模型。可缩放、平移或拖拽节点；点击节点查看事实边界和来源。
      </p>
      <MindMapRendererBoundary fallback={<MindMapFallback mindmap={mindmap} />}>
        <InteractiveMindMap mindmap={mindmap} />
      </MindMapRendererBoundary>
      <p className="mt-3 text-[10px] leading-5 text-slate-500 dark:text-zinc-500">{mindmap.provenance_note}</p>
    </section>
  );
}
