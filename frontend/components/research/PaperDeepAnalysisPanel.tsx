"use client";

import { BookOpenCheck, RotateCcw, Sparkles } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useEffect, useState } from "react";

import {
  assessUnderstandingAnswer,
  createUnderstandingQuestion,
  listReadingReports,
  listUnderstandingChecks,
  openAccessLabel,
  type PaperAnalysis,
  type ReadingReport,
  type ResearchAnalysisItem,
  ResearchApiError,
  saveReadingReport,
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

function ReadingReportsCard({ conversationId, paper }: {
  conversationId: string;
  paper: SelectedResearchPaper;
}) {
  const [reports, setReports] = useState<ReadingReport[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void listReadingReports(conversationId)
      .then((saved) => { if (active) setReports(saved.filter((item) => item.paper_url === paper.url)); })
      .catch(() => { if (active) setReports([]); });
    return () => { active = false; };
  }, [conversationId, paper.url]);

  async function submit() {
    if (!draft.trim()) return;
    setBusy(true); setError(null);
    try {
      const saved = await saveReadingReport(conversationId, { paper_url: paper.url, title: paper.title, content: draft.trim() });
      setReports(saved.filter((item) => item.paper_url === paper.url));
      setDraft("");
    } catch (requestError) { setError(checkError(requestError)); }
    finally { setBusy(false); }
  }

  return (
    <details className="mt-4 rounded-xl border border-slate-200 bg-white/55 p-4 dark:border-zinc-800 dark:bg-zinc-950/40">
      <summary className="min-h-10 cursor-pointer text-base font-semibold text-slate-900 dark:text-zinc-100">我的阅读报告（用户来源，可展开）</summary>
      <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-zinc-400">你写的阅读记录单独保存，标记为用户提交、未核验；它不会当作论文原文事实，也不会改变分析边界。</p>
      <textarea
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        aria-label="阅读报告内容"
        rows={3}
        placeholder="用自己的话记录这一篇的要点、疑问和下一步……"
        className="app-input mt-3 min-h-20 w-full rounded-xl px-3 py-2 text-base leading-7"
      />
      <button
        type="button"
        disabled={busy || !draft.trim()}
        onClick={() => void submit()}
        className="app-button-secondary mt-2 inline-flex min-h-10 items-center rounded-xl px-4 py-2 text-sm font-semibold disabled:opacity-50"
      >
        {busy ? "保存中…" : "保存阅读报告"}
      </button>
      {error && <p role="alert" className="mt-2 text-sm leading-6 text-rose-700 dark:text-rose-300">{error}</p>}
      {reports.length > 0 && (
        <ul className="mt-3 space-y-2">
          {reports.map((report) => (
            <li key={report.report_id} className="rounded-lg bg-slate-50/80 px-3 py-2 text-base leading-7 text-slate-800 dark:bg-zinc-900/60 dark:text-zinc-200">
              <span className="text-sm font-semibold text-slate-500 dark:text-zinc-400">用户提交 · 未核验 · </span>
              {report.content}
            </li>
          ))}
        </ul>
      )}
    </details>
  );
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
  function followUpChapter() {
    const first = document.querySelector<HTMLDetailsElement>("#paper-deep-analysis [data-section-anchor]");
    if (!first) return;
    first.open = true;
    first.scrollIntoView({ behavior: "smooth", block: "start" });
    first.querySelector("summary")?.focus();
  }
  function followUpZone(anchorId: string) {
    document.getElementById(anchorId)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  return <section id="paper-deep-analysis" className="rounded-2xl border border-indigo-200 bg-indigo-50/50 p-5 dark:border-indigo-900/70 dark:bg-indigo-950/20 sm:p-6">
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
      {analysis.core_judgment && <div className="max-w-3xl space-y-2">
        <h3 className="text-xl font-bold text-slate-900 dark:text-zinc-100">核心判断</h3>
        <p className="text-base leading-7 text-slate-800 dark:text-zinc-200">{analysis.core_judgment}</p>
      </div>}
      {analysis.paper_reading && paperSections.length === 0 && <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-4 text-base leading-7 text-amber-950 dark:border-amber-900/70 dark:bg-amber-950/20 dark:text-amber-100">已读取正文，但未识别到标准章节标题；当前分析按主题展示，章节边界待核验。</div>}
      {(paperSections.length > 0 ? [...paperSections.map((section) => ({ key: section.key, title: section.title, items: chapterItems.get(section.key) ?? [] })), ...(chapterItems.has("other") ? [{ key: "other", title: "其他分析", items: chapterItems.get("other") ?? [] }] : [])] : [{ key: "all", title: "论文分析", items: analysis.items }]).map((chapter) => <section key={chapter.key} className="space-y-3"><h3 className="text-xl font-bold text-slate-900 dark:text-zinc-100">{chapter.title}</h3>{chapter.items.length === 0 ? <p className="rounded-xl border border-dashed border-slate-300 px-4 py-3 text-base leading-7 text-slate-600 dark:border-zinc-700 dark:text-zinc-300">尚未生成本章节的针对性分析，相关内容保持待核验。</p> : chapter.items.map((item, index) => <details key={`${chapter.key}-${item.section_key}-${index}`} id={`paper-analysis-section-${chapter.key}-${index}`} data-section-anchor={`paper-analysis-section-${item.section_key}`} className="scroll-mt-24 rounded-xl border border-slate-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-950/40"><summary className="cursor-pointer text-base font-semibold leading-7 text-slate-900 dark:text-zinc-100">{item.content}</summary><div className="mt-2 space-y-2 text-base leading-7 text-slate-700 dark:text-zinc-300"><p>分析主题：{item.area} · {item.classification === "to_verify" ? "待核验" : "建议推断"}</p><p>依据：{item.basis}</p>{item.relevance && <p>与当前研究问题的关系：{item.relevance}</p>}{item.suggested_action && <p>建议下一步：{item.suggested_action}</p>}</div><UnderstandingCheckCard check={checks.find((check) => check.section_key === item.section_key)} item={item} conversationId={conversationId} paper={selectedPaper} onChanged={updateCheck} /></details>)}</section>)}
      <article className="rounded-xl border border-slate-200 bg-slate-50/70 p-5 dark:border-zinc-800 dark:bg-zinc-950/30"><h3 className="text-xl font-bold text-slate-900 dark:text-zinc-100">待核验内容</h3><p className="mt-2 text-base leading-7 text-slate-700 dark:text-zinc-300">数据集划分、超参数、Accuracy、资源需求和复现结论只有在来源明确覆盖后才可确认。</p>{toVerify.length > 0 && <ul className="mt-3 space-y-2 text-base leading-7 text-slate-700 dark:text-zinc-300">{toVerify.map((item, index) => <li key={`${item.area}-${index}`}>• {item.area}：{item.content}</li>)}</ul>}</article>
      <ReadingReportsCard conversationId={conversationId} paper={selectedPaper} />
      <details className="rounded-xl border border-slate-200 bg-white/55 p-4 dark:border-zinc-800 dark:bg-zinc-950/40">
        <summary className="min-h-10 cursor-pointer text-base font-semibold text-slate-900 dark:text-zinc-100">PPT 汇报（设计草案，不阻塞主流程）</summary>
        <div className="mt-2 space-y-2 text-base leading-7 text-slate-700 dark:text-zinc-300">
          <p>规划中的 PPT 汇报将按当前论文分析的章节组织：问题与动机 → 方法结构 → 数据与指标 → 待核验项 → 对当前研究问题的启示；每页标注来源与事实分类，待核验内容进入附录页。</p>
          <p>当前版本仅提供此设计草案，不生成 PPT 文件；主流程（精读、理解检查、复现）不受影响。</p>
        </div>
      </details>
      {analysis.summary && <div className="max-w-3xl space-y-2">
        <h3 className="text-xl font-bold text-slate-900 dark:text-zinc-100">分析总结</h3>
        <p className="text-base leading-7 text-slate-800 dark:text-zinc-200">{analysis.summary}</p>
        {analysis.next_action && <p className="text-base leading-7 text-slate-800 dark:text-zinc-200">建议下一步：{analysis.next_action}</p>}
        <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="分析完成后的下一步选择">
          <button type="button" onClick={() => followUpChapter()} className="app-button-secondary inline-flex min-h-10 items-center rounded-xl px-4 py-2 text-sm font-semibold">继续追问本章</button>
          <button type="button" onClick={() => followUpZone("research-section-literature")} className="app-button-secondary inline-flex min-h-10 items-center rounded-xl px-4 py-2 text-sm font-semibold">精读另一篇</button>
          <button type="button" onClick={() => followUpZone("research-section-workbench")} className="app-button-secondary inline-flex min-h-10 items-center rounded-xl px-4 py-2 text-sm font-semibold">进入复现</button>
        </div>
      </div>}
      <p className="text-sm leading-6 text-slate-600 dark:text-zinc-400">{generationModeLabel(analysis.generation_mode)} · {analysis.provenance_note}</p>
    </div>}
    {!analysis && !loading && !error && <button type="button" onClick={() => onRetry(resolvedPaperPdfUrl)} className="app-button-primary mt-5 inline-flex min-h-10 items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold"><Sparkles className="h-4 w-4" /> 读取论文并生成分析</button>}{analysis && <button type="button" onClick={() => onRetry(resolvedPaperPdfUrl)} disabled={loading} className="app-button-secondary mt-5 inline-flex min-h-10 items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold disabled:opacity-50"><RotateCcw className="h-4 w-4" /> 重新读取并生成</button>}
  </section>;
}
