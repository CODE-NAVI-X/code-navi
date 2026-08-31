"use client";

import {
  BookOpenCheck,
  CheckCircle2,
  CircleAlert,
  ExternalLink,
  Loader2,
  Search,
  Save,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useState } from "react";
import Link from "next/link";

import {
  type AcademicSourceId,
  type AcademicPaperResult,
  type ConversationEvidenceBundle,
  getResearchSearchPlan,
  listResearchEvidence,
  ResearchApiError,
  openAccessLabel,
  researchPaperLinks,
  type ResearchSearchPlan,
  searchResearchEvidence,
  saveResearchNotebookNote,
} from "@/lib/api/research";
import { getLearningSessionId } from "@/lib/api/learning";

function searchErrorMessage(error: unknown): string {
  if (error instanceof ResearchApiError) {
    if (error.status === 409) return error.message;
    if (error.status === 0) return error.message;
    return `检索服务返回 HTTP ${error.status}：${error.message}`;
  }
  return error instanceof Error ? error.message : "检索过程中发生未知错误。";
}

function PaperSourceLinks({ paper }: { paper: AcademicPaperResult }) {
  const links = researchPaperLinks(paper);
  const access = openAccessLabel(paper);
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
      <a
        href={links.sourceUrl}
        target="_blank"
        rel="noreferrer"
        className="inline-flex min-h-10 items-center gap-1.5 rounded-xl border border-sky-200 px-3 font-semibold text-sky-800 hover:bg-sky-50 dark:border-sky-900 dark:text-sky-200 dark:hover:bg-sky-950/30"
      >
        <ExternalLink className="h-4 w-4" /> 打开原始来源
      </a>
      {links.arxivPdfUrl && (
        <a
          href={links.arxivPdfUrl}
          target="_blank"
          rel="noreferrer"
          className="inline-flex min-h-10 items-center gap-1.5 rounded-xl border border-slate-200 px-3 font-semibold text-slate-700 hover:bg-slate-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
        >
          <ExternalLink className="h-4 w-4" /> 在新窗口打开 arXiv PDF
        </a>
      )}
      <span className="text-sm text-slate-600 dark:text-zinc-300">开放获取：{access.label}（{access.note}）</span>
      <span className="w-full text-sm leading-6 text-slate-600 dark:text-zinc-300">打开来源不等于系统已阅读全文；不会自动下载或缓存 PDF。</span>
    </div>
  );
}

export function AcademicSearchPanel({
  conversationId,
  onEvidenceSaved,
  onPaperSelected,
}: {
  conversationId: string;
  onEvidenceSaved?: () => void;
  onPaperSelected?: (paper: {
    title: string;
    url: string;
    authors: string[];
    year: number | null;
    sourceName: string;
    bundleId: string;
    doi: string | null;
    arxivId: string | null;
    abstractExcerpt: string | null;
    paperKind: string | null;
    abstractAvailable: boolean;
  }) => void;
}) {
  const [plan, setPlan] = useState<ResearchSearchPlan | null>(null);
  const [query, setQuery] = useState("");
  const [bundle, setBundle] = useState<ConversationEvidenceBundle | null>(null);
  const [selectedSources, setSelectedSources] = useState<AcademicSourceId[]>([]);
  const [phase, setPhase] = useState<"planning" | "ready" | "searching">("planning");
  const [error, setError] = useState<string | null>(null);
  const [selectedPaperUrls, setSelectedPaperUrls] = useState<string[]>([]);
  const [savingNote, setSavingNote] = useState(false);
  const [savedNoteId, setSavedNoteId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void getResearchSearchPlan(conversationId)
      .then((result) => {
        if (!active) return;
        setPlan(result);
        setQuery(result.query);
        setSelectedSources(result.sources.filter((source) => source.enabled).map((source) => source.id));
        setPhase("ready");
        return listResearchEvidence(conversationId);
      })
      .then((saved) => {
        if (active && saved?.length) setBundle(saved[0]);
      })
      .catch((requestError) => {
        if (!active) return;
        setError(searchErrorMessage(requestError));
        setPhase("ready");
      });
    return () => {
      active = false;
    };
  }, [conversationId]);

  async function runSearch() {
    if (!query.trim() || !selectedSources.length || phase !== "ready") return;
    setPhase("searching");
    setError(null);
    setBundle(null);
    try {
      setBundle(await searchResearchEvidence(conversationId, query.trim(), selectedSources));
      setSelectedPaperUrls([]);
      setSavedNoteId(null);
      onEvidenceSaved?.();
    } catch (requestError) {
      setError(searchErrorMessage(requestError));
    } finally {
      setPhase("ready");
    }
  }

  async function saveSelectedEvidence() {
    if (!bundle || !selectedPaperUrls.length || savingNote) return;
    setSavingNote(true);
    setError(null);
    try {
      const saved = await saveResearchNotebookNote(
        conversationId,
        bundle.bundle_id,
        getLearningSessionId(),
        selectedPaperUrls,
      );
      setSavedNoteId(saved.notebook_item_id);
      onEvidenceSaved?.();
    } catch (requestError) {
      setError(searchErrorMessage(requestError));
    } finally {
      setSavingNote(false);
    }
  }

  return (
    <section className="app-card mx-4 mb-4 overflow-hidden rounded-2xl sm:mx-7">
      <div className="border-b border-slate-200 bg-slate-50 px-4 py-4 dark:border-zinc-800 dark:bg-zinc-950/60">
        <p className="flex items-center gap-2 text-sm font-bold text-slate-900 dark:text-zinc-100">
          <BookOpenCheck className="h-4 w-4 text-emerald-600 dark:text-emerald-400" /> 信息源检索 Skill
        </p>
        <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-zinc-400">
          先检查检索词和允许来源；只有点击“开始受限检索”后才会访问网络。
        </p>
      </div>

      <div className="space-y-4 p-4">
        {phase === "planning" ? (
          <p className="flex items-center gap-2 text-xs text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin text-emerald-500" />
            正在根据科研画像生成检索计划（此步骤不联网）…
          </p>
        ) : plan ? (
          <>
            <label className="block text-xs font-semibold text-slate-700 dark:text-zinc-300">
              检索词
              <textarea
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                rows={2}
                maxLength={300}
                className="app-input mt-2 w-full resize-none rounded-xl px-3 py-2 text-sm font-normal leading-6 outline-none focus:border-slate-500"
              />
            </label>

            <div>
              <p className="text-xs font-semibold text-slate-700 dark:text-zinc-300">允许的信息源</p>
              {plan.sources.map((source) => (
                <label key={source.id} className="mt-2 flex cursor-pointer gap-3 rounded-xl border border-slate-200 p-3 dark:border-zinc-700">
                  <input
                    type="checkbox"
                    checked={selectedSources.includes(source.id)}
                    disabled={!source.enabled || phase === "searching"}
                    onChange={(event) =>
                      setSelectedSources((current) =>
                        event.target.checked
                          ? [...current, source.id]
                          : current.filter((item) => item !== source.id),
                      )
                    }
                    className="mt-1 h-4 w-4 accent-emerald-600"
                  />
                  <span className="min-w-0">
                    <span className="flex items-center gap-2 text-sm font-semibold">
                      <ShieldCheck className="h-4 w-4 text-emerald-500" /> {source.display_name}
                    </span>
                    <span className="mt-1 block text-xs leading-5 text-slate-500 dark:text-zinc-400">{source.scope}</span>
                  </span>
                </label>
              ))}
            </div>

            <button
              type="button"
              onClick={() => void runSearch()}
              disabled={!query.trim() || !selectedSources.length || phase === "searching"}
                className="app-button-primary inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-bold transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-zinc-200"
            >
              {phase === "searching" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              {phase === "searching"
                ? `正在并行访问 ${selectedSources.length} 个学术来源…`
                : `开始受限检索（${selectedSources.length} 个来源）`}
            </button>
          </>
        ) : null}

        {error && (
          <div role="alert" className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs leading-5 text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/20 dark:text-rose-300">
            <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" /> {error}
          </div>
        )}

        {bundle && (
          <div className="space-y-3 border-t border-slate-200 pt-4 dark:border-zinc-800">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500 dark:text-zinc-400">
              <span>
                找到 {bundle.papers.length} 条论文元数据
                {bundle.cache_hit ? " · 来自本地缓存" : ""}
              </span>
              <span>范围：题录与摘要，不代表已阅读全文</span>
            </div>
            <div className="grid gap-2 sm:grid-cols-3">
              {bundle.source_statuses.map((status) => (
                <div key={status.source} className="rounded-xl border border-slate-200 p-2.5 text-xs dark:border-zinc-700">
                  <p className="flex items-center justify-between gap-2 font-semibold">
                    <span>{status.source}</span>
                    <span className={status.status === "success" ? "text-emerald-600" : "text-amber-600"}>
                      {status.status}
                    </span>
                  </p>
                  <p className="mt-1 text-[11px] text-slate-500 dark:text-zinc-400">
                    {status.duration_ms} ms{status.reason ? ` · ${status.reason}` : ""}
                  </p>
                </div>
              ))}
            </div>
            {bundle.papers.length ? (
              bundle.papers.map((paper) => (
                <article key={paper.url} className="rounded-xl border border-slate-200 p-3 dark:border-zinc-700">
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      aria-label={`选择证据：${paper.title}`}
                      checked={selectedPaperUrls.includes(paper.url)}
                      onChange={(event) => setSelectedPaperUrls((current) => event.target.checked ? [...current, paper.url] : current.filter((url) => url !== paper.url))}
                      className="mt-1.5 h-4 w-4 shrink-0 accent-emerald-600"
                    />
                    <span className="flex min-w-0 flex-1 items-start gap-2 text-base font-bold leading-7 text-slate-900 dark:text-zinc-100">
                      <span className="min-w-0 flex-1">{paper.title}</span>
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-slate-600 dark:text-zinc-300">
                    {[paper.authors.slice(0, 4).join("、"), paper.year, paper.source_name].filter(Boolean).join(" · ")}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5 text-xs font-semibold">
                    <span className="rounded-full bg-sky-50 px-2 py-1 text-sky-700 dark:bg-sky-950/40 dark:text-sky-300">平台：{paper.source_name}</span>
                    <span className="rounded-full bg-violet-50 px-2 py-1 text-violet-700 dark:bg-violet-950/40 dark:text-violet-300">证据：{paper.abstract_excerpt ? "摘要级" : "元数据级"}</span>
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-slate-600 dark:bg-zinc-800 dark:text-zinc-300">摘要：{paper.abstract_excerpt ? "可用" : "不可用"}</span>
                    <span className="rounded-full bg-amber-50 px-2 py-1 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">全文：{paper.full_text_available ? "可用" : "不可用"}</span>
                    <span className="rounded-full bg-orange-50 px-2 py-1 text-orange-700 dark:bg-orange-950/40 dark:text-orange-300">相关性：{paper.relevance.classification === "inference" ? "规则推断，待人工核验" : paper.relevance.classification}</span>
                  </div>
                  {paper.abstract_excerpt && (
                    <p className="mt-2 line-clamp-4 text-base leading-7 text-slate-700 dark:text-zinc-200">{paper.abstract_excerpt}</p>
                  )}
                  <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-zinc-300">{paper.relevance.content}</p>
                  <PaperSourceLinks paper={paper} />
                  <button type="button" onClick={() => onPaperSelected?.({ title: paper.title, url: paper.url, authors: paper.authors, year: paper.year, sourceName: paper.source_name, bundleId: bundle.bundle_id, doi: paper.doi, arxivId: paper.arxiv_id, abstractExcerpt: paper.abstract_excerpt, paperKind: paper.paper_kind?.content ?? null, abstractAvailable: Boolean(paper.abstract_excerpt) })} className="app-button-secondary mt-3 inline-flex min-h-10 items-center rounded-xl px-3 py-2 text-sm font-semibold">选择并分析元数据/摘要难点</button>
                </article>
              ))
            ) : (
              <p className="rounded-xl bg-slate-50 p-3 text-xs text-slate-600 dark:bg-zinc-950 dark:text-zinc-400">
                本次没有可展示的论文。{bundle.failure_reasons.join("；") || "可以调整检索词后重试。"}
              </p>
            )}
            {bundle.papers.length > 0 && (
              <div className="app-card-subtle rounded-xl p-3">
                <button
                  type="button"
                  onClick={() => void saveSelectedEvidence()}
                  disabled={!selectedPaperUrls.length || savingNote}
                  className="app-button-primary inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-bold disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {savingNote ? <Loader2 className="h-4 w-4 animate-spin" /> : savedNoteId ? <CheckCircle2 className="h-4 w-4" /> : <Save className="h-4 w-4" />}
                  {savedNoteId ? "已保存为研究笔记" : `保存所选证据到 Notebook（${selectedPaperUrls.length}）`}
                </button>
                <p className="mt-2 text-[11px] leading-5 text-slate-500 dark:text-zinc-400">保存内容包括研究主题、问题、所选 Evidence 来源和下一步建议，并保留当前 Research Conversation。</p>
                {savedNoteId && (
                  <Link href="/learning#research-notes" className="app-button-secondary mt-3 inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-bold transition hover:bg-slate-50 dark:hover:bg-zinc-800">
                    <BookOpenCheck className="h-4 w-4" /> 返回学习笔记查看
                  </Link>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
