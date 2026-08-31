"use client";

import { BookOpenCheck, RotateCcw, Sparkles } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useEffect, useState } from "react";

import {
  assessUnderstandingAnswer,
  createUnderstandingQuestion,
  listUnderstandingChecks,
  openAccessLabel,
  type PaperAnalysis,
  type ResearchAnalysisItem,
  ResearchApiError,
  type UnderstandingCheck,
} from "@/lib/api/research";

import { GenerationFailure, generationModeLabel } from "./generationUi";

export interface SelectedResearchPaper {
  bundleId: string;
  title: string;
  url: string;
  authors: string[];
  year: number | null;
  sourceName: string;
  doi: string | null;
  arxivId: string | null;
  abstractExcerpt: string | null;
  paperKind: string | null;
  abstractAvailable: boolean;
}

function checkError(error: unknown): string {
  if (error instanceof ResearchApiError) return error.message;
  return error instanceof Error ? error.message : "理解检查请求失败，请重试。";
}

function arxivPdfUrl(arxivId: string | null): string | undefined {
  const normalized = (arxivId ?? "").replace(/^arxiv:/i, "").replace(/v\d+$/i, "");
  return /^\d{4}\.\d{4,5}$/.test(normalized)
    ? `https://arxiv.org/pdf/${normalized}.pdf`
    : undefined;
}

function statusLabel(status: UnderstandingCheck["status"]): string {
  return {
    not_started: "未开始", question_ready: "等待你的回答", answer_submitted: "答案已提交",
    needs_explanation: "需要补充说明", partially_understood: "部分理解", understood: "已理解本段内容",
    generation_failed: "本次评估未生成",
  }[status];
}

function UnderstandingCheckCard({ check, item, conversationId, paper, onChanged }: {
  check: UnderstandingCheck | undefined;
  item: ResearchAnalysisItem;
  conversationId: string;
  paper: SelectedResearchPaper;
  onChanged: (updated: UnderstandingCheck) => void;
}) {
  const [answer, setAnswer] = useState(check?.answer ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function createQuestion() {
    setBusy(true); setError(null);
    try { onChanged(await createUnderstandingQuestion(conversationId, { paper_url: paper.url, bundle_id: paper.bundleId, section_key: item.section_key })); }
    catch (requestError) { setError(checkError(requestError)); }
    finally { setBusy(false); }
  }
  async function submitAnswer() {
    if (!check || !answer.trim()) return;
    setBusy(true); setError(null);
    try { onChanged(await assessUnderstandingAnswer(conversationId, { check_id: check.check_id, paper_url: paper.url, bundle_id: paper.bundleId, section_key: item.section_key, answer: answer.trim() })); }
    catch (requestError) { setError(checkError(requestError)); }
    finally { setBusy(false); }
  }
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); void submitAnswer(); }
  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); void submitAnswer(); }
  }
  return <div className="mt-4 rounded-xl border border-indigo-200 bg-indigo-50/70 p-4 dark:border-indigo-900/70 dark:bg-indigo-950/20">
    <p className="text-sm font-semibold text-indigo-950 dark:text-indigo-100">理解检查（仅本段，需你主动触发）</p>
    {!check ? <button type="button" onClick={() => void createQuestion()} disabled={busy} className="app-button-secondary mt-3 min-h-10 rounded-xl px-3 py-2 text-sm font-semibold disabled:opacity-50">{busy ? "正在生成问题…" : "生成一题理解检查"}</button> : <form className="mt-3 space-y-3" onSubmit={submit}>
      <p className="text-base leading-7 text-slate-800 dark:text-zinc-200">{check.question}</p>
      <p className="text-sm leading-6 text-slate-600 dark:text-zinc-300">依据：{check.question_basis} · 来源范围：{check.source_scope === "metadata_only" ? "仅元数据" : "元数据与摘要"}</p>
      <textarea value={answer} onChange={(event) => setAnswer(event.target.value)} onKeyDown={onKeyDown} placeholder="写下你的理解；Ctrl/Cmd + Enter 提交" className="app-input min-h-24 w-full rounded-xl px-3 py-2 text-base leading-7" />
      <button type="submit" disabled={busy || !answer.trim()} className="app-button-primary min-h-10 rounded-xl px-3 py-2 text-sm font-semibold disabled:opacity-50">{busy ? "正在评估…" : "提交理解"}</button>
      <p className="text-sm font-semibold text-indigo-900 dark:text-indigo-200">状态：{statusLabel(check.status)}</p>
      {check.assessment && <p className="text-base leading-7 text-slate-800 dark:text-zinc-200">{check.assessment}</p>}
      {check.correct_points.length > 0 && <p className="text-sm leading-6 text-slate-700 dark:text-zinc-300">已理解：{check.correct_points.join("；")}</p>}
      {check.missing_points.length > 0 && <p className="text-sm leading-6 text-amber-900 dark:text-amber-200">待补充：{check.missing_points.join("；")}</p>}
      {check.explanation && <p className="text-sm leading-6 text-slate-700 dark:text-zinc-300">说明：{check.explanation}</p>}
      {check.example && <p className="text-sm leading-6 text-slate-700 dark:text-zinc-300">示例：{check.example}</p>}
      {check.recommended_next_action && <p className="text-sm leading-6 text-indigo-900 dark:text-indigo-200">下一步：{check.recommended_next_action}</p>}
    </form>}
    {error && <GenerationFailure error={error} busy={busy} hasLastSuccess={Boolean(check?.assessment)} onRetry={() => check ? void submitAnswer() : void createQuestion()} />}
  </div>;
}

export function PaperDeepAnalysisPanel({ conversationId, selectedPaper, analysis, loading, error, onRetry, onUpload }: {
  conversationId: string; selectedPaper: SelectedResearchPaper | null; analysis: PaperAnalysis | null; loading: boolean; error: string | null; onRetry: (paperPdfUrl?: string) => void; onUpload: (file: File) => void;
}) {
  const [checks, setChecks] = useState<UnderstandingCheck[]>([]);
  const [paperFile, setPaperFile] = useState<File | null>(null);
  useEffect(() => {
    let active = true;
    if (!selectedPaper) return;
    void listUnderstandingChecks(conversationId, selectedPaper.url).then((restored) => { if (active) setChecks(restored); }).catch(() => { if (active) setChecks([]); });
    return () => { active = false; };
  }, [conversationId, selectedPaper]);
  if (!selectedPaper) return <section className="rounded-2xl border border-slate-200 bg-slate-50/70 p-6 dark:border-zinc-800 dark:bg-zinc-950/30"><h2 className="text-2xl font-bold text-slate-950 dark:text-zinc-100">论文深度分析</h2><p className="mt-3 max-w-3xl text-base leading-7 text-slate-600 dark:text-zinc-300">准入条件：先在“方向与文献”中保存当前会话的论文，并点击“选择并分析元数据/摘要”。系统不会下载全文或把标题推测成论文结论。</p></section>;
  const toVerify = analysis?.items.filter((item) => item.classification === "to_verify") ?? [];
  const paperSections = analysis?.paper_reading?.sections ?? [];
  const chapterItems = new Map<string, ResearchAnalysisItem[]>();
  analysis?.items.forEach((item) => {
    const key = item.chapter_key ?? "other";
    chapterItems.set(key, [...(chapterItems.get(key) ?? []), item]);
  });
  const persistedPdfUrl = analysis?.paper_reading?.source_url?.startsWith("https://")
    ? analysis.paper_reading.source_url
    : undefined;
  const resolvedPaperPdfUrl = persistedPdfUrl || arxivPdfUrl(selectedPaper.arxivId);
  const access = openAccessLabel({ arxiv_id: selectedPaper.arxivId, doi: selectedPaper.doi });
  const updateCheck = (updated: UnderstandingCheck) => setChecks((current) => [...current.filter((item) => item.check_id !== updated.check_id), updated]);
  return <section className="rounded-2xl border border-indigo-200 bg-indigo-50/50 p-5 dark:border-indigo-900/70 dark:bg-indigo-950/20 sm:p-6">
    <div className="flex flex-wrap items-start justify-between gap-4"><div className="max-w-3xl"><p className="text-sm font-semibold uppercase tracking-[0.14em] text-indigo-700 dark:text-indigo-300">Selected paper</p><h2 className="mt-2 text-2xl font-bold text-slate-950 dark:text-zinc-100">{selectedPaper.title}</h2><p className="mt-2 text-sm leading-6 text-slate-600 dark:text-zinc-300">{[selectedPaper.authors.slice(0, 4).join("、"), selectedPaper.year, selectedPaper.sourceName].filter(Boolean).join(" · ")}</p></div><a href={selectedPaper.url} target="_blank" rel="noreferrer" className="app-button-secondary inline-flex min-h-10 items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold"><BookOpenCheck className="h-4 w-4" /> 查看已保存来源</a></div>
    <dl className="mt-5 grid gap-2 text-sm leading-6 text-slate-700 dark:text-zinc-300 sm:grid-cols-2"><div><dt className="font-semibold">DOI</dt><dd>{selectedPaper.doi ?? "未提供"}</dd></div><div><dt className="font-semibold">arXiv</dt><dd>{selectedPaper.arxivId ?? "未提供"}</dd></div><div><dt className="font-semibold">论文类别</dt><dd>{selectedPaper.paperKind ?? "待核验"}</dd></div><div><dt className="font-semibold">开放获取</dt><dd>{access.label}：{access.note}</dd></div></dl>
    <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50/70 p-4 text-base leading-7 text-slate-700 dark:border-zinc-800 dark:bg-zinc-950/30 dark:text-zinc-300">
      <p>{analysis?.paper_reading ? `已读取论文正文 ${analysis.paper_reading.pages_read} 页，建议基于正文生成。` : "点击生成时，系统会按标题、作者和 DOI 自动寻找公开论文；找不到公开版本时，可上传本地 PDF。"}</p>
      {!analysis?.paper_reading && <div className="mt-3 flex flex-wrap items-center gap-3">
        <input type="file" accept="application/pdf,.pdf" aria-label="上传本地 PDF" onChange={(event) => setPaperFile(event.target.files?.[0] ?? null)} className="app-input min-h-10 max-w-full rounded-xl px-3 py-2 text-sm" />
        {paperFile && <button type="button" onClick={() => { onUpload(paperFile); setPaperFile(null); }} className="app-button-secondary min-h-10 rounded-xl px-4 py-2 text-sm font-semibold">上传本地 PDF 并生成</button>}
      </div>}
    </div>
    {error && <GenerationFailure error={error} busy={loading} hasLastSuccess={analysis !== null} onRetry={() => onRetry(resolvedPaperPdfUrl)} />}{loading && <p className="mt-5 text-base leading-7 text-slate-600 dark:text-zinc-300">正在读取论文并生成来源受限分析…</p>}
    {analysis && <div className="mt-6 space-y-5">
      {analysis.paper_reading && paperSections.length === 0 && <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-4 text-base leading-7 text-amber-950 dark:border-amber-900/70 dark:bg-amber-950/20 dark:text-amber-100">已读取正文，但未识别到标准章节标题；当前分析按主题展示，章节边界待核验。</div>}
      {(paperSections.length > 0 ? [...paperSections.map((section) => ({ key: section.key, title: section.title, items: chapterItems.get(section.key) ?? [] })), ...(chapterItems.has("other") ? [{ key: "other", title: "其他分析", items: chapterItems.get("other") ?? [] }] : [])] : [{ key: "all", title: "论文分析", items: analysis.items }]).map((chapter) => <section key={chapter.key} className="space-y-3"><h3 className="text-xl font-bold text-slate-900 dark:text-zinc-100">{chapter.title}</h3>{chapter.items.length === 0 ? <p className="rounded-xl border border-dashed border-slate-300 px-4 py-3 text-base leading-7 text-slate-600 dark:border-zinc-700 dark:text-zinc-300">尚未生成本章节的针对性分析，相关内容保持待核验。</p> : chapter.items.map((item, index) => <details key={`${chapter.key}-${item.section_key}-${index}`} id={`paper-analysis-section-${chapter.key}-${index}`} data-section-anchor={`paper-analysis-section-${item.section_key}`} className="scroll-mt-24 rounded-xl border border-slate-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-950/40"><summary className="cursor-pointer text-base font-semibold leading-7 text-slate-900 dark:text-zinc-100">{item.content}</summary><div className="mt-2 space-y-2 text-base leading-7 text-slate-700 dark:text-zinc-300"><p>分析主题：{item.area} · {item.classification === "to_verify" ? "待核验" : "建议推断"}</p><p>依据：{item.basis}</p></div><UnderstandingCheckCard check={checks.find((check) => check.section_key === item.section_key)} item={item} conversationId={conversationId} paper={selectedPaper} onChanged={updateCheck} /></details>)}</section>)}
      <article className="rounded-xl border border-slate-200 bg-slate-50/70 p-5 dark:border-zinc-800 dark:bg-zinc-950/30"><h3 className="text-xl font-bold text-slate-900 dark:text-zinc-100">待核验内容</h3><p className="mt-2 text-base leading-7 text-slate-700 dark:text-zinc-300">数据集划分、超参数、Accuracy、资源需求和复现结论只有在来源明确覆盖后才可确认。</p>{toVerify.length > 0 && <ul className="mt-3 space-y-2 text-base leading-7 text-slate-700 dark:text-zinc-300">{toVerify.map((item, index) => <li key={`${item.area}-${index}`}>• {item.area}：{item.content}</li>)}</ul>}</article><p className="text-sm leading-6 text-slate-600 dark:text-zinc-400">{generationModeLabel(analysis.generation_mode)} · {analysis.provenance_note}</p>
    </div>}
    {!analysis && !loading && !error && <button type="button" onClick={() => onRetry(resolvedPaperPdfUrl)} className="app-button-primary mt-5 inline-flex min-h-10 items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold"><Sparkles className="h-4 w-4" /> 读取论文并生成分析</button>}{analysis && <button type="button" onClick={() => onRetry(resolvedPaperPdfUrl)} disabled={loading} className="app-button-secondary mt-5 inline-flex min-h-10 items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold disabled:opacity-50"><RotateCcw className="h-4 w-4" /> 重新读取并生成</button>}
  </section>;
}
