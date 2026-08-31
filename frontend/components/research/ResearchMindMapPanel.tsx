"use client";

import { Component, type KeyboardEvent, type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type NodeProps,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Download,
  Link as LinkIcon,
  Loader2,
  Maximize2,
  Minimize2,
  Network,
  RotateCcw,
  SlidersHorizontal,
  X,
} from "lucide-react";

import type {
  PaperAnalysis,
  ResearchMindMap,
  ResearchMindMapNode,
  ResearchMindMapNodeStatus,
} from "@/lib/api/research";
import { ResearchApiError, generateResearchMindMap } from "@/lib/api/research";

import {
  buildResearchMindMapSvg,
  layoutResearchMindMap,
  STATUS_COLORS,
  STATUS_LABEL,
  type MindMapFlowEdge,
  type MindMapFlowNode,
} from "./researchMindMapGraph";

const STATUS_STYLE = {
  confirmed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300",
  inference: "bg-sky-100 text-sky-800 dark:bg-sky-950/50 dark:text-sky-300",
  to_verify: "bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300",
  evidence: "bg-violet-100 text-violet-800 dark:bg-violet-950/50 dark:text-violet-300",
  risk: "bg-rose-100 text-rose-800 dark:bg-rose-950/50 dark:text-rose-300",
};

const ALL_STATUSES: ResearchMindMapNodeStatus[] = [
  "confirmed",
  "inference",
  "to_verify",
  "evidence",
  "risk",
];

function jumpToPaperAnalysis(sectionKey: string | null) {
  if (!sectionKey) return;
  const target = document.getElementById(`paper-analysis-section-${sectionKey}`);
  if (!target) return;
  target.scrollIntoView({ behavior: "smooth", block: "start" });
  target.focus({ preventScroll: true });
}

function downloadSvg(mindmap: ResearchMindMap) {
  const url = URL.createObjectURL(new Blob([buildResearchMindMapSvg(mindmap)], { type: "image/svg+xml" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "research-mindmap.svg";
  anchor.click();
  URL.revokeObjectURL(url);
}

function NodeDetails({ node, onClose }: { node: ResearchMindMapNode; onClose?: () => void }) {
  return (
    <aside className="rounded-2xl border border-slate-700/80 bg-zinc-950/95 p-4 text-xs shadow-2xl backdrop-blur dark:border-zinc-700" aria-label="节点详情">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-300">节点详情</p>
          <h3 className="mt-1 font-semibold text-zinc-100">{node.label}</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className={`shrink-0 rounded-full px-2 py-1 text-xs font-semibold ${STATUS_STYLE[node.status]}`}>{STATUS_LABEL[node.status]}</span>
          {onClose ? <button type="button" onClick={onClose} aria-label="关闭详情" className="rounded-lg p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"><X className="h-4 w-4" /></button> : null}
        </div>
      </div>
      <p className="mt-3 leading-5 text-zinc-300">{node.detail}</p>
      <p className="mt-3 rounded-xl bg-zinc-900 px-3 py-2 text-sm leading-6 text-zinc-300">事实边界：{STATUS_LABEL[node.status]}。{node.status === "evidence" ? "仅代表已保存的来源元数据或摘要范围。" : "不代表未经保存来源验证的论文事实。"}</p>
      {node.sources.length > 0 ? (
        <div className="mt-3 space-y-2 border-t border-zinc-800 pt-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-400">来源（仅点击后在新标签页打开）</p>
          {node.sources.map((source) => (
            <a key={`${source.url}-${source.accessed_at}`} href={source.url} target="_blank" rel="noreferrer" className="flex items-start gap-2 rounded-xl bg-zinc-900 px-3 py-2 text-teal-300 underline underline-offset-2 hover:bg-zinc-800">
              <LinkIcon className="mt-0.5 h-3 w-3 shrink-0" />
              <span>{source.label} · {new Date(source.accessed_at).toLocaleString()} · 已保存来源范围</span>
            </a>
          ))}
        </div>
      ) : <p className="mt-3 text-xs text-zinc-400">暂无外部来源；此节点仅来自已保存画像或规则计划。</p>}
    </aside>
  );
}

function ResearchMapNode({ data }: NodeProps<MindMapFlowNode>) {
  const { node, isRoot, nodeTier, summary } = data;
  const colors = STATUS_COLORS[node.status];
  const hierarchyClass = isRoot
    ? "min-w-[300px] border-[3px] px-4 py-3 shadow-lg"
    : nodeTier === "primary"
      ? "min-w-[258px] border-2 px-3.5 py-2.5 shadow-md"
      : "min-w-[236px] border-2 px-3 py-2 shadow-sm";
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if ((event.key === "Enter" || event.key === " ") && node.section_key) {
      event.preventDefault();
      jumpToPaperAnalysis(node.section_key);
    }
  }
  return (
    <div role={node.section_key ? "button" : undefined} tabIndex={node.section_key ? 0 : undefined} onKeyDown={onKeyDown} className={`rounded-2xl ${hierarchyClass}`} style={{ backgroundColor: colors.fill, borderColor: colors.stroke, color: colors.text, boxShadow: isRoot ? `0 0 0 4px ${colors.stroke}33` : undefined }}>
      <Handle type="target" position={Position.Left} className="!border-0 !bg-transparent" />
      <p className={isRoot ? "line-clamp-2 text-sm font-extrabold leading-5" : "line-clamp-2 text-xs font-bold leading-5"}>{node.label}</p>
      <p className="mt-1 line-clamp-2 text-xs leading-5 opacity-85">{summary}</p>
      <span className="mt-2 inline-flex rounded-full bg-white/70 px-2 py-1 text-xs font-semibold">{STATUS_LABEL[node.status]}</span>
      <Handle type="source" position={Position.Right} className="!border-0 !bg-transparent" />
    </div>
  );
}

const nodeTypes = { researchMindMap: ResearchMapNode };

function InteractiveMindMap({ mindmap, onCollapse }: { mindmap: ResearchMindMap; onCollapse: () => void }) {
  const graph = useMemo(() => layoutResearchMindMap(mindmap), [mindmap]);
  const [activeStatuses, setActiveStatuses] = useState<ResearchMindMapNodeStatus[]>(ALL_STATUSES);
  const [positionOverrides, setPositionOverrides] = useState<Record<string, { x: number; y: number }>>({});
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance<MindMapFlowNode, MindMapFlowEdge> | null>(null);
  const activeStatusSet = useMemo(() => new Set(activeStatuses), [activeStatuses]);
  const visibleNodes = useMemo(
    () => graph.nodes.map((node) => ({ ...node, hidden: !activeStatusSet.has(node.data.node.status) })),
    [activeStatusSet, graph.nodes],
  );
  const visibleNodeIds = useMemo(
    () => new Set(visibleNodes.filter((node) => !node.hidden).map((node) => node.id)),
    [visibleNodes],
  );
  const visibleEdges = useMemo(
    () => graph.edges.map((edge) => ({ ...edge, hidden: !visibleNodeIds.has(edge.source) || !visibleNodeIds.has(edge.target) })),
    [graph.edges, visibleNodeIds],
  );
  const nodes = useMemo(
    () => visibleNodes.map((node) => ({ ...node, position: positionOverrides[node.id] ?? node.position })),
    [positionOverrides, visibleNodes],
  );
  const selectedNode = selectedNodeId ? mindmap.nodes.find((node) => node.id === selectedNodeId) : undefined;

  const fitGraph = useCallback(() => {
    flowInstance?.fitView({ padding: 0.2, duration: 220, maxZoom: 1.15 });
  }, [flowInstance]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(fitGraph);
    return () => window.cancelAnimationFrame(frame);
  }, [fitGraph, nodes, visibleEdges]);

  function toggleStatus(status: ResearchMindMapNodeStatus) {
    if (selectedNode?.status === status && activeStatuses.includes(status)) setSelectedNodeId(null);
    setActiveStatuses((current) => current.includes(status)
      ? current.filter((item) => item !== status)
      : [...current, status]);
  }

  return (
    <div className="mt-4 rounded-2xl border border-zinc-800 bg-zinc-950 p-3 text-zinc-100 sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 pb-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.16em] text-teal-300">专注导图工作区</p>
          <p className="mt-1 text-sm leading-6 text-zinc-300">仅布局已保存节点与后端 edges；筛选只隐藏视图，不增加关系或调用网络。</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1 text-sm font-semibold text-zinc-300"><SlidersHorizontal className="h-4 w-4" /> 状态筛选</span>
          {ALL_STATUSES.map((status) => <button key={status} type="button" onClick={() => toggleStatus(status)} aria-pressed={activeStatuses.includes(status)} className={`min-h-10 rounded-full border px-3 text-sm font-semibold transition ${activeStatuses.includes(status) ? STATUS_STYLE[status] : "border-zinc-700 bg-zinc-900 text-zinc-400"}`}>{STATUS_LABEL[status]}</button>)}
          <button type="button" onClick={fitGraph} className="min-h-10 rounded-lg border border-zinc-700 px-3 text-sm font-semibold text-zinc-200 hover:bg-zinc-800">适配画布</button>
          <button type="button" onClick={() => downloadSvg(mindmap)} className="inline-flex min-h-10 items-center gap-1 rounded-lg border border-teal-800 bg-teal-950/40 px-3 text-sm font-semibold text-teal-200 hover:bg-teal-950"><Download className="h-4 w-4" /> 导出 SVG</button>
          <button type="button" onClick={onCollapse} className="inline-flex min-h-10 items-center gap-1 rounded-lg border border-zinc-700 px-3 text-sm font-semibold text-zinc-200 hover:bg-zinc-800"><Minimize2 className="h-4 w-4" /> 收起</button>
        </div>
      </div>
      <div
        className="relative mt-3 h-[420px] overflow-hidden rounded-xl border border-zinc-800 bg-slate-950 sm:h-[540px]"
        aria-label="可交互研究思维导图"
      >
        <ReactFlow<MindMapFlowNode, MindMapFlowEdge>
          className="h-full w-full"
          nodes={nodes}
          edges={visibleEdges}
          onNodeDragStop={(_, draggedNode) => setPositionOverrides((current) => ({
            ...current,
            [draggedNode.id]: draggedNode.position,
          }))}
          onNodeClick={(event, clickedNode) => {
            event.stopPropagation();
            setSelectedNodeId(clickedNode.id);
            jumpToPaperAnalysis(clickedNode.data.node.section_key);
          }}
          nodeTypes={nodeTypes}
          onInit={setFlowInstance}
          fitView
          fitViewOptions={{ padding: 0.2, maxZoom: 1.15 }}
          minZoom={0.25}
          maxZoom={1.8}
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable
          proOptions={{ hideAttribution: true }}
          defaultEdgeOptions={{ style: { stroke: "#94a3b8", strokeWidth: 2 } }}
        >
          <Background color="#334155" gap={18} size={1} />
          <Controls className="!border-zinc-700 !bg-zinc-900 !fill-zinc-100" />
          <MiniMap nodeColor="#14b8a6" className="!border-zinc-700 !bg-zinc-900" maskColor="rgba(15, 23, 42, 0.55)" />
        </ReactFlow>
        {selectedNode ? <div className="absolute inset-x-3 bottom-3 z-10 lg:inset-x-auto lg:right-3 lg:top-3 lg:bottom-auto lg:w-[21rem]"><NodeDetails node={selectedNode} onClose={() => setSelectedNodeId(null)} /></div> : null}
      </div>
      {!selectedNode ? <p className="mt-3 text-center text-sm text-zinc-400">点击节点可查看依据、事实边界与已保存来源；详情不会占用默认画布。</p> : null}
    </div>
  );
}

function MindMapFallback({ mindmap }: { mindmap: ResearchMindMap }) {
  return (
    <div className="mt-4">
      <p className="rounded-xl border border-amber-200 bg-amber-50/70 p-4 text-sm leading-6 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-200">交互导图本地渲染不可用，已回退到节点详情清单；不会联网。</p>
      <ul className="mt-3 space-y-2">{mindmap.nodes.map((node) => <li key={node.id}><NodeDetails node={node} /></li>)}</ul>
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

function MindMapSummary({ mindmap, onExpand }: { mindmap: ResearchMindMap; onExpand: () => void }) {
  const root = mindmap.nodes.find((node) => node.id === mindmap.root_node_id) ?? mindmap.nodes[0];
  const confirmedCount = mindmap.nodes.filter((node) => node.status === "confirmed").length;
  const evidenceCount = mindmap.nodes.reduce((count, node) => count + node.sources.length, 0);
  const pendingCount = mindmap.nodes.filter((node) => node.status === "risk" || node.status === "to_verify").length;
  const plan = mindmap.nodes.find((node) => node.id === "research-plan");
  const planLabel = plan?.status === "inference" ? "模型研究计划已形成" : "研究计划待完善";
  return (
    <div className="mt-4 rounded-2xl border border-zinc-800 bg-gradient-to-br from-zinc-950 to-slate-900 p-4 text-zinc-100 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold uppercase tracking-[0.16em] text-teal-300">Research overview</p>
          <h3 className="mt-1 truncate text-base font-bold sm:text-lg">{root?.label ?? "研究主题待确认"}</h3>
          <p className="mt-1 text-xs text-zinc-400">{planLabel} · 展开后可查看真实节点与后端关系。</p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={onExpand} className="inline-flex min-h-10 items-center gap-1.5 rounded-xl bg-teal-400 px-4 text-sm font-bold text-zinc-950 hover:bg-teal-300"><Maximize2 className="h-4 w-4" /> 展开科研导图</button>
          <button type="button" onClick={() => downloadSvg(mindmap)} className="inline-flex min-h-10 items-center gap-1.5 rounded-xl border border-zinc-700 px-4 text-sm font-semibold text-zinc-200 hover:bg-zinc-800"><Download className="h-4 w-4" /> 导出 SVG</button>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          ["已确认项", confirmedCount, "confirmed"],
          ["待验证/风险", pendingCount, "to_verify"],
          ["已保存证据", evidenceCount, "evidence"],
          ["后端关系", mindmap.edges.length, "inference"],
        ].map(([label, value, status]) => <div key={String(label)} className="rounded-xl border border-zinc-800 bg-zinc-900/80 p-3"><p className="text-xs text-zinc-400">{label}</p><p className={`mt-1 text-lg font-bold ${STATUS_STYLE[status as ResearchMindMapNodeStatus]}`}>{value}</p></div>)}
      </div>
      <p className="mt-4 text-sm leading-6 text-zinc-300">导图只读取已保存 ResearchProfile、模型研究计划与 EvidenceBundle；不联网、不读论文全文、不写文件。</p>
    </div>
  );
}

export function ResearchMindMapPanel({
  conversationId,
  mindmap,
  selectedPaperTitle,
  paperAnalysis,
  onGenerated,
}: {
  conversationId: string;
  mindmap: ResearchMindMap | null;
  selectedPaperTitle?: string | null;
  paperAnalysis?: PaperAnalysis | null;
  onGenerated: (mindmap: ResearchMindMap) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationError, setGenerationError] = useState<string | null>(null);

  const generate = useCallback(async () => {
    setIsGenerating(true);
    setGenerationError(null);
    try {
      onGenerated(await generateResearchMindMap(conversationId));
    } catch (error) {
      if (error instanceof ResearchApiError) {
        setGenerationError(error.message);
      } else {
        setGenerationError("模型当前不可用、请求超时或返回结果未通过校验。");
      }
    } finally {
      setIsGenerating(false);
    }
  }, [conversationId, onGenerated]);

  return (
    <section className="app-card rounded-2xl p-4">
      <div className="flex items-start gap-3">
        <span className="rounded-xl bg-slate-100 p-2 text-slate-700 dark:bg-zinc-800 dark:text-zinc-200"><Network className="h-4 w-4" /></span>
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-zinc-400">Research mind map</p>
          <h2 className="mt-1 text-xl font-bold text-slate-900 dark:text-zinc-100">研究思维导图</h2>
        </div>
      </div>
      <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50/70 p-4 text-sm leading-6 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-200">
        <p>模型只会在你点击后，根据已保存状态组织导图内容；不会联网、下载论文全文、读取私有文件或执行代码。</p>
        <button
          type="button"
          disabled={isGenerating}
          onClick={() => void generate()}
          className="mt-3 inline-flex min-h-10 items-center gap-2 rounded-xl bg-amber-900 px-4 text-sm font-bold text-white transition hover:bg-amber-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-amber-300 dark:text-amber-950 dark:hover:bg-amber-200"
        >
          {isGenerating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Network className="h-4 w-4" />}
          {isGenerating ? "正在生成导图…" : "生成科研思维导图"}
        </button>
      </div>
      {generationError && (
        <div role="alert" className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-950 dark:border-rose-900/60 dark:bg-rose-950/20 dark:text-rose-100">
          <p className="font-bold">本次未生成科研建议</p>
          <p className="mt-1">模型当前不可用、请求超时或返回结果未通过校验。系统没有使用规则模板替代本次分析。</p>
          <p className="mt-1 text-sm">错误摘要：{generationError}</p>
          <button type="button" onClick={() => void generate()} className="mt-3 inline-flex min-h-10 items-center gap-2 rounded-xl border border-rose-300 px-4 text-sm font-semibold hover:bg-rose-100 dark:border-rose-800 dark:hover:bg-rose-950/40">
            <RotateCcw className="h-4 w-4" /> 重试
          </button>
        </div>
      )}
      {selectedPaperTitle && (
        <div className="mt-4 rounded-xl border border-indigo-200 bg-indigo-50 p-4 text-sm leading-6 text-indigo-950 dark:border-indigo-900/60 dark:bg-indigo-950/20 dark:text-indigo-100">
          <p className="font-semibold">当前论文分析节点：{selectedPaperTitle}</p>
          <p className="mt-1">{paperAnalysis ? `已接入 ${paperAnalysis.items.length} 条来源受限分析；${paperAnalysis.paper_reading ? `已读取论文正文 ${paperAnalysis.paper_reading.pages_read} 页。` : "当前依据为元数据与摘要。"}` : "请先生成来源受限的论文深度分析，导图不会补造论文全文事实。"}</p>
        </div>
      )}
      {mindmap ? (expanded ? <MindMapRendererBoundary fallback={<MindMapFallback mindmap={mindmap} />}><InteractiveMindMap mindmap={mindmap} onCollapse={() => setExpanded(false)} /></MindMapRendererBoundary> : <MindMapSummary mindmap={mindmap} onExpand={() => setExpanded(true)} />) : (
        <p className="mt-4 text-sm leading-6 text-slate-600 dark:text-zinc-300">尚未生成模型导图。点击上方按钮后，模型会根据已保存科研状态组织内容。</p>
      )}
      {mindmap && <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-zinc-300">{mindmap.provenance_note}</p>}
    </section>
  );
}
