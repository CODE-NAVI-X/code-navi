"use client";

import { FileText, ExternalLink, Bookmark, GitCompare, CheckCircle2, Loader2 } from "lucide-react";
import type { CurrentPaperCard, OrchestratorPaper, PaperUsage } from "@/lib/api/research";

interface CandidatePaperCardProps {
  currentPaper: CurrentPaperCard | null;
  paperHistory?: OrchestratorPaper[];
  onSelectPurpose: (paperUrl: string, title: string, purpose: PaperUsage) => Promise<void>;
  loading?: boolean;
}

export function CandidatePaperCard({
  currentPaper,
  paperHistory = [],
  onSelectPurpose,
  loading = false,
}: CandidatePaperCardProps) {
  if (!currentPaper && paperHistory.length === 0) return null;

  const displayPaper = currentPaper || paperHistory[paperHistory.length - 1];
  if (!displayPaper) return null;

  return (
    <div
      role="region"
      aria-label="候选论文卡片"
      className="my-4 rounded-2xl border border-blue-200/80 bg-gradient-to-b from-blue-50/60 to-slate-50/50 p-4 sm:p-5 shadow-sm dark:border-blue-900/60 dark:from-blue-950/20 dark:to-zinc-900/40 backdrop-blur-sm"
    >
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 text-blue-950 dark:text-blue-200">
          <FileText className="h-4 w-4 text-blue-600 dark:text-blue-400" />
          <h3 className="text-base font-bold">已选定/候选论文档案</h3>
        </div>
        <span className="text-xs px-2.5 py-0.5 rounded-full bg-blue-100 text-blue-800 dark:bg-blue-950/60 dark:text-blue-300 font-semibold">
          {displayPaper.purpose === "replace"
            ? "当前核心论文"
            : displayPaper.purpose === "compare"
            ? "对比阅读论文"
            : "参考引用论文"}
        </span>
      </div>

      <div className="rounded-xl border border-slate-200/80 bg-white/90 p-4 dark:border-zinc-800 dark:bg-zinc-900/90 shadow-xs">
        <div className="flex items-start justify-between gap-3">
          <h4 className="font-bold text-sm sm:text-base text-slate-900 dark:text-zinc-100 leading-snug">
            {displayPaper.title}
          </h4>
          <a
            href={displayPaper.paper_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-semibold text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-950/40 transition shrink-0"
          >
            <span>来源链接</span>
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        </div>

        <p className="mt-1.5 text-xs text-slate-500 dark:text-zinc-400 truncate">
          URL：{displayPaper.paper_url}
        </p>

        <div className="mt-4 pt-3 border-t border-slate-100 dark:border-zinc-800 flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs text-slate-500 dark:text-zinc-400">
            切换论文用途：
          </span>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={loading || displayPaper.purpose === "replace"}
              onClick={() => void onSelectPurpose(displayPaper.paper_url, displayPaper.title, "replace")}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                displayPaper.purpose === "replace"
                  ? "bg-emerald-600 text-white dark:bg-emerald-500 dark:text-zinc-950 shadow-xs"
                  : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
              } disabled:cursor-not-allowed disabled:opacity-50`}
            >
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
              设为当前论文 (replace)
            </button>
            <button
              type="button"
              disabled={loading || displayPaper.purpose === "compare"}
              onClick={() => void onSelectPurpose(displayPaper.paper_url, displayPaper.title, "compare")}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                displayPaper.purpose === "compare"
                  ? "bg-indigo-600 text-white dark:bg-indigo-500 dark:text-zinc-950 shadow-xs"
                  : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
              } disabled:cursor-not-allowed disabled:opacity-50`}
            >
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <GitCompare className="h-3.5 w-3.5" />}
              加入对比阅读 (compare)
            </button>
            <button
              type="button"
              disabled={loading || displayPaper.purpose === "cite"}
              onClick={() => void onSelectPurpose(displayPaper.paper_url, displayPaper.title, "cite")}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                displayPaper.purpose === "cite"
                  ? "bg-purple-600 text-white dark:bg-purple-500 dark:text-zinc-950 shadow-xs"
                  : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
              } disabled:cursor-not-allowed disabled:opacity-50`}
            >
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Bookmark className="h-3.5 w-3.5" />}
              标记为参考引用 (cite)
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
