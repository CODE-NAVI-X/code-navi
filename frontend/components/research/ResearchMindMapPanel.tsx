"use client";

import { Download, GitBranch, Link as LinkIcon, Network } from "lucide-react";

import type { ResearchMindMap, ResearchMindMapNodeStatus } from "@/lib/api/research";

const STATUS_LABEL: Record<ResearchMindMapNodeStatus, string> = {
  confirmed: "已确认",
  inference: "建议",
  to_verify: "待验证",
  evidence: "来源证据",
  risk: "风险",
};

const STATUS_STYLE: Record<ResearchMindMapNodeStatus, string> = {
  confirmed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300",
  inference: "bg-sky-100 text-sky-800 dark:bg-sky-950/50 dark:text-sky-300",
  to_verify: "bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300",
  evidence: "bg-violet-100 text-violet-800 dark:bg-violet-950/50 dark:text-violet-300",
  risk: "bg-rose-100 text-rose-800 dark:bg-rose-950/50 dark:text-rose-300",
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

function downloadSvg(mindmap: ResearchMindMap) {
  const labels = mindmap.nodes.map((node, index) => `<text x="24" y="${36 + index * 28}" font-size="14">${escapeXml(node.label)}（${escapeXml(STATUS_LABEL[node.status])}）</text>`).join("");
  const height = Math.max(120, 64 + mindmap.nodes.length * 28);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="900" height="${height}" viewBox="0 0 900 ${height}"><rect width="100%" height="100%" fill="#ffffff"/><text x="24" y="20" font-size="16" font-weight="700">研究思维导图（结构化节点清单）</text>${labels}</svg>`;
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "research-mindmap.svg";
  anchor.click();
  URL.revokeObjectURL(url);
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
        此导图只整理已保存画像、规则计划与已有证据包；不联网、不调用模型。展开节点可查看来源链接与访问时间。
      </p>
      <ul className="mt-4 space-y-2">
        {mindmap.nodes.map((node) => (
          <li key={node.id} className="rounded-xl border border-slate-200/80 bg-slate-50/70 dark:border-zinc-800 dark:bg-zinc-950/40">
            <details>
              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-3 text-xs">
                <span className="flex min-w-0 items-center gap-2 font-medium text-slate-800 dark:text-zinc-200"><GitBranch className="h-3.5 w-3.5 shrink-0 text-teal-600" />{node.label}</span>
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${STATUS_STYLE[node.status]}`}>{STATUS_LABEL[node.status]}</span>
              </summary>
              <div className="border-t border-slate-200 px-3 py-2 text-[11px] leading-5 text-slate-600 dark:border-zinc-800 dark:text-zinc-400">
                <p>{node.detail}</p>
                {node.sources.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer" className="mt-2 flex items-center gap-1 text-teal-700 underline dark:text-teal-300"><LinkIcon className="h-3 w-3" />{source.label} · {new Date(source.accessed_at).toLocaleString()}</a>)}
              </div>
            </details>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[10px] leading-5 text-slate-500 dark:text-zinc-500">{mindmap.provenance_note}</p>
    </section>
  );
}
