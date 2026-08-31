"use client";

import { AlertTriangle, BrainCircuit, Loader2, Sparkles } from "lucide-react";
import { useState } from "react";

import {
  generateTopicDifficultyAnalysis,
  type TopicDifficultyAnalysis,
} from "@/lib/api/research";
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
          <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-zinc-400">
            <AlertTriangle className="mr-1 inline h-4 w-4" />
            {generationModeLabel(current.generation_mode)}：这是研究设计的风险与缺口提示，不是论文精读或实验结论；当前范围：
            {current.information_scope === "metadata_and_abstract_only" ? "已有元数据/摘要" : "科研画像与规则计划"}。
          </p>
          <div className="mt-4 rounded-xl border border-slate-200/80 bg-slate-50/70 p-5 text-base leading-8 dark:border-zinc-800 dark:bg-zinc-950/40" aria-label="方向难点分析正文">
            {current.core_judgment && (
              <p className="mb-3 font-semibold text-slate-900 dark:text-zinc-100">核心判断：{current.core_judgment}</p>
            )}
            {current.items.map((item) => (
              <div key={`${item.area}:${item.content}`} className="mb-3 last:mb-0">
                <p className="whitespace-pre-wrap text-slate-700 dark:text-zinc-300">
                  <span className="font-semibold text-slate-900 dark:text-zinc-100">{item.area}：</span>
                  {item.content}
                </p>
                {item.relevance && <p className="mt-1 text-slate-700 dark:text-zinc-300">与当前研究问题的关系：{item.relevance}</p>}
                {item.suggested_action && <p className="mt-1 text-slate-700 dark:text-zinc-300">建议下一步：{item.suggested_action}</p>}
              </div>
            ))}
            {current.next_action && (
              <p className="mt-3 font-semibold text-slate-900 dark:text-zinc-100">唯一下一步：{current.next_action}</p>
            )}
          </div>
          <div className="mt-4 space-y-3 text-sm leading-6 text-slate-600 dark:text-zinc-400">
            {current.items.map((item) => (
              <div key={`basis:${item.area}:${item.content}`}>
                <p>依据：{item.basis}</p>
                {item.evidence_refs.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-2">
                    {item.evidence_refs.map((reference) => (
                      <a key={`${reference.bundle_id}:${reference.paper_url}`} href={reference.paper_url} target="_blank" rel="noreferrer" className="text-sm font-semibold text-sky-700 hover:underline dark:text-sky-300">
                        来源：{reference.title}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-500 dark:text-zinc-500">
            {current.provenance_note}
            {current.run_id ? ` · 审计运行 ${current.run_id}` : ""}
          </p>
        </>
      )}
    </section>
  );
}
