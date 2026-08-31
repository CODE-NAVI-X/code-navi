"use client";

import { FlaskConical, Loader2, Sparkles } from "lucide-react";
import { useState } from "react";

import {
  createExperimentCodeDraft,
  generateExperimentDesign,
  type ExperimentCodeDraft,
  type ExperimentDesign,
  type ResearchPlanEntry,
} from "@/lib/api/research";
import { GenerationFailure, generationModeLabel, isGenerationFailure } from "./generationUi";

function Entries({ title, entries }: { title: string; entries: ResearchPlanEntry[] }) {
  return (
    <section>
      <p className="text-base font-bold text-slate-800 dark:text-zinc-200">{title}</p>
      <p className="mt-2 max-w-4xl whitespace-pre-line text-base leading-7 text-slate-700 dark:text-zinc-300">
        {entries.map((item) => item.content).join(" ")}
      </p>
    </section>
  );
}

function draftText(draft: ExperimentCodeDraft) {
  return [draft.title, draft.provenance_note, ...draft.files.map((item) => `# ${item.path}\n${item.content}`)].join("\n\n");
}

export function ExperimentDesignPanel({
  design,
  conversationId,
}: {
  design: ExperimentDesign | null;
  conversationId: string;
}) {
  const [generated, setGenerated] = useState<ExperimentDesign | null>(null);
  const [personalizing, setPersonalizing] = useState(false);
  const [draft, setDraft] = useState<ExperimentCodeDraft | null>(null);
  const [loadingDraft, setLoadingDraft] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [failure, setFailure] = useState(false);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [draftFailure, setDraftFailure] = useState(false);
  const [copyNotice, setCopyNotice] = useState<string | null>(null);

  const current = generated ?? design;

  async function personalize() {
    setPersonalizing(true);
    setError(null);
    setFailure(false);
    try {
      setGenerated(await generateExperimentDesign(conversationId));
    } catch (value) {
      setFailure(isGenerationFailure(value));
      setError(value instanceof Error ? value.message : "实验方案生成失败。");
    } finally {
      setPersonalizing(false);
    }
  }

  async function previewDraft() {
    setLoadingDraft(true);
    setDraftError(null);
    setDraftFailure(false);
    try {
      setDraft(await createExperimentCodeDraft(conversationId));
    } catch (value) {
      setDraftFailure(isGenerationFailure(value));
      setDraftError(value instanceof Error ? value.message : "代码草案预览失败。");
    } finally {
      setLoadingDraft(false);
    }
  }

  async function copyDraft() {
    if (!draft) return;
    try {
      await navigator.clipboard.writeText(draftText(draft));
      setCopyNotice("已复制浏览器内的草案文本。");
    } catch {
      setCopyNotice("复制失败，请手动从预览区复制。");
    }
  }

  function downloadDraft() {
    if (!draft) return;
    const url = URL.createObjectURL(new Blob([draftText(draft)], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "experiment-code-draft.txt";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="app-card rounded-2xl p-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="rounded-xl bg-slate-100 p-2 text-slate-700 dark:bg-zinc-800 dark:text-zinc-300"><FlaskConical className="h-5 w-5" /></span>
          <div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-zinc-400">Experiment design</p><h2 className="mt-1 text-xl font-bold">实验方案（建议）</h2></div>
        </div>
        <button type="button" onClick={() => void personalize()} disabled={personalizing} className="app-button-secondary inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-semibold disabled:opacity-50">
          {personalizing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {current ? "重新生成" : "生成实验方案"}
        </button>
      </div>
      {error &&
        (failure ? (
          <GenerationFailure error={error} busy={personalizing} hasLastSuccess={current !== null} onRetry={() => void personalize()} />
        ) : (
          <p role="alert" className="mt-3 text-sm text-rose-600">{error}</p>
        ))}
      {current === null && !error && (
        <p className="mt-4 rounded-xl border border-slate-200/80 bg-slate-50/70 p-4 text-sm leading-6 text-slate-600 dark:border-zinc-800 dark:bg-zinc-950/40 dark:text-zinc-400">
          尚未生成实验方案。点击“生成实验方案”后，模型会基于你的科研画像与研究计划生成建议性设计；失败时会明确提示，不会用通用模板替代。
        </p>
      )}
      {current && (
        <>
          <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-zinc-400">{generationModeLabel(current.generation_mode)}：{current.provenance_note}{current.run_id ? ` · 审计运行 ${current.run_id}` : ""}</p>
          <div className="mt-4 space-y-3">
            <Entries title="假设" entries={[current.hypothesis]} />
            <Entries title="变量与对照" entries={current.variables} />
            <Entries title="数据来源与基线" entries={[...current.data_sources, ...current.baselines]} />
            <Entries title="指标与步骤" entries={[...current.metrics, ...current.steps]} />
            <Entries title="资源、风险与导师确认" entries={[...current.resources, ...current.risks, ...current.advisor_confirmation_items]} />
          </div>
        </>
      )}
      <button type="button" onClick={() => void previewDraft()} disabled={loadingDraft} className="app-button-secondary mt-4 inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-bold disabled:opacity-50">
        {loadingDraft && <Loader2 className="h-4 w-4 animate-spin" />}
        我确认仅预览代码草案
      </button>
      {draftError &&
        (draftFailure ? (
          <GenerationFailure error={draftError} busy={loadingDraft} hasLastSuccess={draft !== null} onRetry={() => void previewDraft()} />
        ) : (
          <p role="alert" className="mt-2 text-sm text-rose-600">{draftError}</p>
        ))}
      {draft && (
        <div className="app-card-subtle mt-3 rounded-xl p-4 text-sm">
          <p className="text-base font-bold">{draft.title}</p>
          <p className="mt-1 leading-6">{generationModeLabel(draft.generation_mode)}：{draft.provenance_note}</p>
          <p className="mt-1 text-sm text-slate-500 dark:text-zinc-500">建议/待验证，不是已验证实验结论；仅导出当前浏览器内文本，不写入项目。</p>
          <div className="mt-2 flex flex-wrap gap-2"><button type="button" onClick={() => void copyDraft()} className="app-button-secondary rounded px-2.5 py-1.5 text-sm">复制代码</button><button type="button" onClick={downloadDraft} className="app-button-secondary rounded px-2.5 py-1.5 text-sm">下载草案文本</button></div>
          {copyNotice && <p className="mt-1 text-sm text-slate-500">{copyNotice}</p>}
          <pre className="mt-2 overflow-auto rounded bg-slate-950 p-3 text-xs leading-5 text-slate-100">{draftText(draft)}</pre>
        </div>
      )}
    </section>
  );
}
