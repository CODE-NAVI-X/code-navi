"use client";

import { AlertTriangle, BrainCircuit, Loader2, Sparkles } from "lucide-react";
import { useState } from "react";

import {
  generateTopicDifficultyAnalysis,
  type TopicDifficultyAnalysis,
} from "@/lib/api/research";
import { ClassificationBadge } from "./ClassificationBadge";
const MODE = {
  llm: "模型个性化建议",
  rules: "基础规则",
  rules_fallback: "模型失败后的规则降级",
} as const;

export function ResearchDifficultyPanel({
  analysis,
  conversationId,
}: {
  analysis: TopicDifficultyAnalysis;
  conversationId: string;
}) {
  const [override, setOverride] = useState<{
    base: TopicDifficultyAnalysis;
    value: TopicDifficultyAnalysis;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const current = override?.base === analysis ? override.value : analysis;

  async function personalize() {
    setLoading(true);
    setError(null);
    try {
      setOverride({
        base: analysis,
        value: await generateTopicDifficultyAnalysis(conversationId),
      });
    } catch (value) {
      setError(value instanceof Error ? value.message : "个性化难点分析失败。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-2xl border border-orange-200 bg-white p-4 shadow-sm dark:border-orange-900/70 dark:bg-zinc-900/80">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="rounded-xl bg-orange-100 p-2 text-orange-700 dark:bg-orange-950/50 dark:text-orange-300">
            <BrainCircuit className="h-4 w-4" />
          </span>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-orange-700 dark:text-orange-300">Direction difficulty</p>
            <h2 className="mt-1 text-sm font-bold text-slate-900 dark:text-zinc-100">方向难点分析</h2>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void personalize()}
          disabled={loading}
          className="inline-flex items-center gap-1 rounded-lg border border-orange-200 px-2.5 py-1.5 text-[11px] font-semibold text-orange-800 disabled:opacity-50 dark:border-orange-900 dark:text-orange-300"
        >
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
          用户确认后个性化
        </button>
      </div>
      <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50/70 p-3 text-[11px] leading-5 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-200">
        <AlertTriangle className="mr-1 inline h-3.5 w-3.5" />
        {MODE[current.generation_mode]}：这是研究设计的风险与缺口提示，不是论文精读或实验结论；当前范围：
        {current.information_scope === "metadata_and_abstract_only" ? "已有元数据/摘要" : "科研画像与规则计划"}。
      </p>
      {error && <p role="alert" className="mt-2 text-xs text-rose-600">{error}</p>}
      <ul className="mt-4 space-y-2">
        {current.items.map((item) => (
          <li key={item.area} className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3 text-xs leading-5 dark:border-zinc-800 dark:bg-zinc-950/40">
            <div className="flex items-center justify-between gap-2">
              <p className="font-semibold text-slate-800 dark:text-zinc-200">{item.area}</p>
              <ClassificationBadge classification={item.classification} />
            </div>
            <p className="mt-2 text-slate-700 dark:text-zinc-300">{item.content}</p>
            <p className="mt-1 text-[10px] text-slate-500">依据：{item.basis}</p>
            {item.evidence_refs.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {item.evidence_refs.map((reference) => (
                  <a key={`${reference.bundle_id}:${reference.paper_url}`} href={reference.paper_url} target="_blank" rel="noreferrer" className="rounded-full bg-sky-50 px-2 py-1 text-[10px] font-semibold text-sky-700 hover:underline dark:bg-sky-950/40 dark:text-sky-300">
                    Evidence：{reference.title}
                  </a>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[10px] leading-5 text-slate-500 dark:text-zinc-500">
        {current.provenance_note}
        {current.run_id ? ` · 审计运行 ${current.run_id}` : ""}
      </p>
    </section>
  );
}
