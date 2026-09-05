"use client";

import { ExternalLink, FileSearch, Loader2 } from "lucide-react";

import type { AcademicPaperResult } from "@/lib/api/research";

interface SearchCandidateCardsProps {
  papers: AcademicPaperResult[];
  disabled: boolean;
  onSelect: (paper: AcademicPaperResult) => void;
  loading?: boolean;
}

/**
 * 候选论文卡片（正式检索后的可点击例外之二）。
 *
 * 卡片只展示真实检索结果的元数据（标题 / 来源 / 年份 / 链接 / 摘要摘录，
 * `metadata_and_abstract_only`，不下载全文）；中文一句话说明、核心创新点
 * 与与当前目标的关系由点击后的姜姜精读式介绍给出。点击只会把该论文作为
 * 待确认候选发进聊天流，确定前不会设为当前论文。
 */
export function SearchCandidateCards({
  papers,
  disabled,
  onSelect,
  loading = false,
}: SearchCandidateCardsProps) {
  if (papers.length === 0) return null;

  return (
    <div
      role="region"
      aria-label="检索候选论文卡片"
      className="my-4 rounded-2xl border border-cyan-200/80 bg-gradient-to-b from-cyan-50/60 to-slate-50/50 p-4 sm:p-5 shadow-sm dark:border-cyan-900/60 dark:from-cyan-950/20 dark:to-zinc-900/40 backdrop-blur-sm"
    >
      <div className="mb-3 flex items-center gap-2 text-cyan-950 dark:text-cyan-200">
        <FileSearch className="h-4 w-4 text-cyan-600 dark:text-cyan-400" />
        <h3 className="text-base font-bold">检索候选论文</h3>
        <span className="rounded-full bg-cyan-100 px-2.5 py-0.5 text-xs font-semibold text-cyan-800 dark:bg-cyan-950/60 dark:text-cyan-300">
          真实检索结果 · 仅元数据与摘要
        </span>
      </div>
      <div className="space-y-3">
        {papers.map((paper) => (
          <div
            key={paper.url}
            className="rounded-xl border border-slate-200/80 bg-white/90 p-4 shadow-xs dark:border-zinc-800 dark:bg-zinc-900/90"
          >
            <div className="flex items-start justify-between gap-3">
              <h4 className="text-sm font-bold leading-snug text-slate-900 sm:text-base dark:text-zinc-100">
                {paper.title}
              </h4>
              <a
                href={paper.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex shrink-0 items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-semibold text-cyan-600 transition hover:bg-cyan-50 dark:text-cyan-400 dark:hover:bg-cyan-950/40"
              >
                <span>来源链接</span>
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </div>
            <p className="mt-1.5 text-xs text-slate-500 dark:text-zinc-400">
              {paper.source_name}
              {paper.year ? ` · ${paper.year}` : ""}
            </p>
            {paper.abstract_excerpt && (
              <p className="mt-2 line-clamp-3 text-xs leading-5 text-slate-600 dark:text-zinc-300">
                {paper.abstract_excerpt}
              </p>
            )}
            <button
              type="button"
              disabled={disabled || loading}
              onClick={() => onSelect(paper)}
              className="app-button-secondary mt-3 inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileSearch className="h-3.5 w-3.5" />}
              请姜姜精读介绍这篇
            </button>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-slate-400 dark:text-zinc-500">
        点击只会把论文作为待确认候选发给姜姜；确认后才会设为当前论文。
      </p>
    </div>
  );
}
