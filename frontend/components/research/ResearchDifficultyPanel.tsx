import { AlertTriangle, BrainCircuit } from "lucide-react";

import type { TopicDifficultyAnalysis } from "@/lib/api/research";

const LABEL = { fact: "已知输入", inference: "分析建议", to_verify: "待核验" } as const;

export function ResearchDifficultyPanel({ analysis }: { analysis: TopicDifficultyAnalysis }) {
  return (
    <section className="rounded-2xl border border-orange-200 bg-white p-4 shadow-sm dark:border-orange-900/70 dark:bg-zinc-900/80">
      <div className="flex items-start gap-3"><span className="rounded-xl bg-orange-100 p-2 text-orange-700 dark:bg-orange-950/50 dark:text-orange-300"><BrainCircuit className="h-4 w-4" /></span><div><p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-orange-700 dark:text-orange-300">Direction difficulty</p><h2 className="mt-1 text-sm font-bold text-slate-900 dark:text-zinc-100">方向难点分析</h2></div></div>
      <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50/70 p-3 text-[11px] leading-5 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-200"><AlertTriangle className="mr-1 inline h-3.5 w-3.5" /> 这是研究设计的风险与缺口提示，不是论文精读或实验结论；当前范围：{analysis.information_scope === "metadata_and_abstract_only" ? "已有元数据/摘要" : "科研画像与规则计划"}。</p>
      <ul className="mt-4 space-y-2">{analysis.items.map((item) => <li key={item.area} className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3 text-xs leading-5 dark:border-zinc-800 dark:bg-zinc-950/40"><div className="flex items-center justify-between gap-2"><p className="font-semibold text-slate-800 dark:text-zinc-200">{item.area}</p><span className="rounded-full bg-orange-100 px-2 py-0.5 text-[10px] font-semibold text-orange-800 dark:bg-orange-950/50 dark:text-orange-300">{LABEL[item.classification]}</span></div><p className="mt-2 text-slate-700 dark:text-zinc-300">{item.content}</p><p className="mt-1 text-[10px] text-slate-500">依据：{item.basis}</p></li>)}</ul>
      <p className="mt-3 text-[10px] leading-5 text-slate-500 dark:text-zinc-500">{analysis.provenance_note}</p>
    </section>
  );
}
