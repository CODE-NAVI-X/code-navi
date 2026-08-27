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
import { ClassificationBadge } from "./ClassificationBadge";

function Entries({ title, entries }: { title: string; entries: ResearchPlanEntry[] }) {
  return (
    <section>
      <p className="text-[11px] font-bold text-slate-800 dark:text-zinc-200">{title}</p>
      <ul className="mt-1 space-y-1">
        {entries.map((item) => (
          <li key={item.content} className="app-card-subtle rounded-lg p-2 text-[11px] leading-5 text-slate-700 dark:text-zinc-300">
            <ClassificationBadge classification={item.classification} />{" "}
            {item.content}
          </li>
        ))}
      </ul>
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
  design: ExperimentDesign;
  conversationId: string;
}) {
  const [override, setOverride] = useState<{
    base: ExperimentDesign;
    value: ExperimentDesign;
  } | null>(null);
  const [personalizing, setPersonalizing] = useState(false);
  const [draft, setDraft] = useState<ExperimentCodeDraft | null>(null);
  const [loadingDraft, setLoadingDraft] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copyNotice, setCopyNotice] = useState<string | null>(null);

  const current = override?.base === design ? override.value : design;

  async function personalize() {
    setPersonalizing(true);
    setError(null);
    try {
      setOverride({
        base: design,
        value: await generateExperimentDesign(conversationId),
      });
    } catch (value) {
      setError(value instanceof Error ? value.message : "个性化实验方案失败。");
    } finally {
      setPersonalizing(false);
    }
  }

  async function previewDraft() {
    setLoadingDraft(true);
    setError(null);
    try {
      setDraft(await createExperimentCodeDraft(conversationId));
    } catch (value) {
      setError(value instanceof Error ? value.message : "代码草案预览失败。");
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

  const mode = current.generation_mode === "llm"
    ? "模型个性化建议"
    : current.generation_mode === "rules_fallback"
      ? "模型失败后的规则降级"
      : "基础规则";

  return (
    <section className="app-card rounded-2xl p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="rounded-xl bg-slate-100 p-2 text-slate-700 dark:bg-zinc-800 dark:text-zinc-300"><FlaskConical className="h-4 w-4" /></span>
          <div><p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-zinc-400">Experiment design</p><h2 className="mt-1 text-sm font-bold">实验方案（建议）</h2></div>
        </div>
        <button type="button" onClick={() => void personalize()} disabled={personalizing} className="app-button-secondary inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-semibold disabled:opacity-50">
          {personalizing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
          用户确认后个性化
        </button>
      </div>
      <p className="mt-3 text-[11px] leading-5 text-slate-600 dark:text-zinc-400">{mode}：{current.provenance_note}{current.run_id ? ` · 审计运行 ${current.run_id}` : ""}</p>
      <div className="mt-4 space-y-3">
        <Entries title="假设" entries={[current.hypothesis]} />
        <Entries title="变量与对照" entries={current.variables} />
        <Entries title="数据来源与基线" entries={[...current.data_sources, ...current.baselines]} />
        <Entries title="指标与步骤" entries={[...current.metrics, ...current.steps]} />
        <Entries title="资源、风险与导师确认" entries={[...current.resources, ...current.risks, ...current.advisor_confirmation_items]} />
      </div>
      <button type="button" onClick={() => void previewDraft()} disabled={loadingDraft} className="app-button-secondary mt-4 inline-flex items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold disabled:opacity-50">
        {loadingDraft && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
        我确认仅预览代码草案
      </button>
      {error && <p role="alert" className="mt-2 text-xs text-rose-600">{error}</p>}
      {draft && (
        <div className="app-card-subtle mt-3 rounded-xl p-3 text-xs">
          <p className="font-bold">{draft.title}</p>
          <p className="mt-1">{draft.generation_mode === "llm" ? "模型个性化建议" : draft.generation_mode === "rules_fallback" ? "模型失败后的规则降级" : "基础规则"}：{draft.provenance_note}</p>
          <p className="mt-1 text-[10px] text-slate-500">建议/待验证，不是已验证实验结论；仅导出当前浏览器内文本，不写入项目。</p>
          <div className="mt-2 flex flex-wrap gap-2"><button type="button" onClick={() => void copyDraft()} className="app-button-secondary rounded px-2 py-1">复制代码</button><button type="button" onClick={downloadDraft} className="app-button-secondary rounded px-2 py-1">下载草案文本</button></div>
          {copyNotice && <p className="mt-1 text-[10px] text-slate-500">{copyNotice}</p>}
          <pre className="mt-2 overflow-auto rounded bg-slate-950 p-2 text-[10px] text-slate-100">{draftText(draft)}</pre>
        </div>
      )}
    </section>
  );
}
