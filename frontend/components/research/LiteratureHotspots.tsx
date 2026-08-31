"use client";

import type { ConversationEvidenceBundle } from "@/lib/api/research";

/**
 * Checkpoint-5 hotspot overview: aggregates ONLY the papers already saved in
 * this conversation's evidence bundles.  No model, no network: year and
 * source counts come straight from the retrieval metadata, and the header
 * always states the sample size, query terms, allowed sources and access
 * time so the numbers stay auditable.  Too few papers means no chart.
 */

const MIN_SAMPLE_FOR_CHART = 3;

export function LiteratureHotspots({ bundles }: { bundles: ConversationEvidenceBundle[] }) {
  const papers = bundles.flatMap((bundle) => bundle.papers);
  const sampleCount = papers.length;
  const queries = [...new Set(bundles.map((bundle) => bundle.query).filter(Boolean))];
  const allowedSources = [
    ...new Set(bundles.flatMap((bundle) => bundle.allowed_sources ?? [])),
  ];
  const searchedAt = bundles
    .map((bundle) => bundle.searched_at)
    .filter(Boolean)
    .sort()
    .at(-1);

  const byYear = new Map<number, number>();
  papers.forEach((paper) => {
    if (typeof paper.year === "number") {
      byYear.set(paper.year, (byYear.get(paper.year) ?? 0) + 1);
    }
  });
  const yearRows = [...byYear.entries()].sort((a, b) => b[0] - a[0]);
  const bySource = new Map<string, number>();
  papers.forEach((paper) => {
    bySource.set(paper.source_name, (bySource.get(paper.source_name) ?? 0) + 1);
  });
  const sourceRows = [...bySource.entries()].sort((a, b) => b[1] - a[1]);
  const maxYearCount = Math.max(1, ...yearRows.map(([, count]) => count));

  return (
    <div className="rounded-xl border border-slate-200 bg-white/60 p-4 dark:border-zinc-800 dark:bg-zinc-950/40">
      <p className="text-base font-semibold text-slate-900 dark:text-zinc-100">
        来源热点概览（仅聚合当前已保存的检索结果）
      </p>
      <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-zinc-400">
        样本数量：{sampleCount} 篇
        {queries.length > 0 && <> · 检索词：{queries.join("；")}</>}
        {allowedSources.length > 0 && <> · 允许来源：{allowedSources.join("、")}</>}
        {searchedAt && <> · 检索时间：{new Date(searchedAt).toLocaleString("zh-CN")}</>}
      </p>
      {sampleCount < MIN_SAMPLE_FOR_CHART ? (
        <p className="mt-3 text-sm leading-6 text-amber-800 dark:text-amber-200">
          样本不足（{sampleCount} 篇）：样本太少，不生成趋势图；保存更多检索结果后再看年份与来源分布。
        </p>
      ) : (
        <div className="mt-3 space-y-4">
          <div>
            <p className="text-sm font-semibold text-slate-700 dark:text-zinc-300">年份分布</p>
            <ul className="mt-2 space-y-1.5">
              {yearRows.map(([year, count]) => (
                <li key={year} className="flex items-center gap-2 text-sm leading-6 text-slate-700 dark:text-zinc-300">
                  <span className="w-12 shrink-0 text-right font-mono">{year}</span>
                  <span className="h-3 rounded bg-sky-500/70 dark:bg-sky-600/70" style={{ width: `${Math.round((count / maxYearCount) * 60) + 4}%` }} aria-hidden="true" />
                  <span>{count} 篇</span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-700 dark:text-zinc-300">来源分布</p>
            <p className="mt-1 text-sm leading-6 text-slate-700 dark:text-zinc-300">
              {sourceRows.map(([source, count]) => `${source}：${count} 篇`).join(" · ")}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
