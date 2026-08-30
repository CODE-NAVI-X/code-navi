"use client";

import { AlertTriangle, BrainCircuit, Loader2, Sparkles } from "lucide-react";
import { useState } from "react";

import {
  generateTopicDifficultyAnalysis,
  type TopicDifficultyAnalysis,
} from "@/lib/api/research";
import { ClassificationBadge } from "./ClassificationBadge";
import { GenerationFailure, generationModeLabel, isGenerationFailure } from "./generationUi";

export function ResearchDifficultyPanel({
  analysis,
  conversationId,
}: {
  analysis: TopicDifficultyAnalysis | null;
  conversationId: string;
}) {
  const [generated, setGenerated] = useState<TopicDifficultyAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [failure, setFailure] = useState(false);
  const current = generated ?? analysis;

  async function personalize() {
    setLoading(true);
    setError(null);
    setFailure(false);
    try {
      setGenerated(await generateTopicDifficultyAnalysis(conversationId));
    } catch (value) {
      setFailure(isGenerationFailure(value));
      setError(value instanceof Error ? value.message : "难点分析生成失败。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="app-card rounded-2xl p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="rounded-xl bg-slate-100 p-2 text-slate-700 dark:bg-zinc-800 dark:text-zinc-200">
            <BrainCircuit className="h-5 w-5" />
          </span>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-zinc-400">Direction difficulty</p>
            <h2 className="mt-1 text-xl font-bold text-slate-900 dark:text-zinc-100">方向难点分析</h2>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void personalize()}
          disabled={loading}
          className="app-button-secondary inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-semibold disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {current ? "重新生成" : "生成难点分析"}
        </button>
      </div>
      {error &&
        (failure ? (
          <GenerationFailure error={error} busy={loading} hasLastSuccess={current !== null} onRetry={() => void personalize()} />
        ) : (
          <p role="alert" className="mt-3 text-sm text-rose-600">{error}</p>
        ))}
      {current === null && !error && (
        <p className="mt-4 rounded-xl border border-slate-200/80 bg-slate-50/70 p-4 text-sm leading-6 text-slate-600 dark:border-zinc-800 dark:bg-zinc-950/40 dark:text-zinc-400">
          尚未生成难点分析。点击“生成难点分析”后，模型会基于你的科研画像、研究计划和已保存证据生成带事实分类与来源边界的分析；失败时会明确提示，不会用通用模板替代。
        </p>
      )}
      {current && (
        <>
          <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50/70 p-3 text-sm leading-6 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-200">
            <AlertTriangle className="mr-1 inline h-4 w-4" />
            {generationModeLabel(current.generation_mode)}：这是研究设计的风险与缺口提示，不是论文精读或实验结论；当前范围：
            {current.information_scope === "metadata_and_abstract_only" ? "已有元数据/摘要" : "科研画像与规则计划"}。
          </p>
          <ul className="mt-4 space-y-3">
            {current.items.map((item) => (
              <li key={item.area} className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-4 text-base leading-7 dark:border-zinc-800 dark:bg-zinc-950/40">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold text-slate-800 dark:text-zinc-200">{item.area}</p>
                  <ClassificationBadge classification={item.classification} />
                </div>
                <p className="mt-2 text-slate-700 dark:text-zinc-300">{item.content}</p>
                <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-zinc-500">依据：{item.basis}</p>
                {item.evidence_refs.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {item.evidence_refs.map((reference) => (
                      <a key={`${reference.bundle_id}:${reference.paper_url}`} href={reference.paper_url} target="_blank" rel="noreferrer" className="rounded-full bg-sky-50 px-2.5 py-1 text-xs font-semibold text-sky-700 hover:underline dark:bg-sky-950/40 dark:text-sky-300">
                        Evidence：{reference.title}
                      </a>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
          <p className="mt-3 text-sm leading-6 text-slate-500 dark:text-zinc-500">
            {current.provenance_note}
            {current.run_id ? ` · 审计运行 ${current.run_id}` : ""}
          </p>
        </>
      )}
    </section>
  );
}
