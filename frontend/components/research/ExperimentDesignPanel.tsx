"use client";

import { FlaskConical } from "lucide-react";
import { useState } from "react";

import { createExperimentCodeDraft, type ExperimentDesign, type ExperimentCodeDraft, type ResearchPlanEntry } from "@/lib/api/research";

function Entries({ title, entries }: { title: string; entries: ResearchPlanEntry[] }) {
  return <section><p className="text-[11px] font-bold text-slate-800 dark:text-zinc-200">{title}</p><ul className="mt-1 space-y-1">{entries.map((item) => <li key={item.content} className="rounded-lg bg-slate-50 p-2 text-[11px] leading-5 text-slate-700 dark:bg-zinc-950/50 dark:text-zinc-300"><span className="mr-1 font-semibold">{item.classification === "inference" ? "建议" : "待确认"}</span>{item.content}</li>)}</ul></section>;
}

export function ExperimentDesignPanel({ design, conversationId }: { design: ExperimentDesign; conversationId: string }) {
  const [draft, setDraft] = useState<ExperimentCodeDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function previewDraft() { setError(null); try { setDraft(await createExperimentCodeDraft(conversationId)); } catch (value) { setError(value instanceof Error ? value.message : "代码草案预览失败。"); } }
  const mode = design.generation_mode === "llm" ? "模型个性化建议" : design.generation_mode === "rules_fallback" ? "模型失败后的规则降级" : "基础规则";
  return <section className="rounded-2xl border border-fuchsia-200 bg-white p-4 shadow-sm dark:border-fuchsia-900/70 dark:bg-zinc-900/80"><div className="flex items-center gap-3"><span className="rounded-xl bg-fuchsia-100 p-2 text-fuchsia-700 dark:bg-fuchsia-950/50 dark:text-fuchsia-300"><FlaskConical className="h-4 w-4" /></span><div><p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-fuchsia-700 dark:text-fuchsia-300">Experiment design</p><h2 className="mt-1 text-sm font-bold">实验方案（建议）</h2></div></div><p className="mt-3 text-[11px] leading-5 text-slate-600 dark:text-zinc-400">{mode}：{design.provenance_note}</p><div className="mt-4 space-y-3"><Entries title="假设" entries={[design.hypothesis]} /><Entries title="变量与对照" entries={design.variables} /><Entries title="数据来源与基线" entries={[...design.data_sources, ...design.baselines]} /><Entries title="指标与步骤" entries={[...design.metrics, ...design.steps]} /><Entries title="资源、风险与导师确认" entries={[...design.resources, ...design.risks, ...design.advisor_confirmation_items]} /></div><button type="button" onClick={() => void previewDraft()} className="mt-4 rounded-xl border border-fuchsia-200 px-3 py-2 text-xs font-bold text-fuchsia-800 dark:border-fuchsia-900 dark:text-fuchsia-300">我确认仅预览代码草案</button>{error && <p role="alert" className="mt-2 text-xs text-rose-600">{error}</p>}{draft && <div className="mt-3 rounded-xl border border-fuchsia-200 p-3 text-xs"><p className="font-bold">{draft.title}</p><p className="mt-1">{draft.provenance_note}</p><pre className="mt-2 overflow-auto rounded bg-slate-950 p-2 text-[10px] text-slate-100">{draft.files.map((item) => `# ${item.path}\n${item.content}`).join("\n\n")}</pre></div>}</section>;
}
