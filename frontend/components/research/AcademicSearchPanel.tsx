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
  type ConversationEvidenceBundle,
  type PaperAnalysis,
  analyzeResearchPaper,
  getResearchSearchPlan,
  listResearchEvidence,
  ResearchApiError,
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

export function AcademicSearchPanel({ conversationId }: { conversationId: string }) {
  const [plan, setPlan] = useState<ResearchSearchPlan | null>(null);
  const [query, setQuery] = useState("");
  const [bundle, setBundle] = useState<ConversationEvidenceBundle | null>(null);
  const [selectedSources, setSelectedSources] = useState<AcademicSourceId[]>([]);
  const [phase, setPhase] = useState<"planning" | "ready" | "searching">("planning");
  const [error, setError] = useState<string | null>(null);
  const [paperAnalysis, setPaperAnalysis] = useState<PaperAnalysis | null>(null);
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
    } catch (requestError) {
      setError(searchErrorMessage(requestError));
    } finally {
      setSavingNote(false);
    }
  }

  async function analyzePaper(paperUrl: string) {
    setError(null);
    try {
      setPaperAnalysis(await analyzeResearchPaper(conversationId, paperUrl));
    } catch (requestError) {
      setError(searchErrorMessage(requestError));
    }
  }

  return (
    <section className="mx-4 mb-4 overflow-hidden rounded-2xl border border-emerald-200 bg-white shadow-sm dark:border-emerald-900/60 dark:bg-zinc-900 sm:mx-7">
      <div className="border-b border-emerald-100 bg-emerald-50 px-4 py-4 dark:border-emerald-900/50 dark:bg-emerald-950/20">
        <p className="flex items-center gap-2 text-sm font-bold text-emerald-900 dark:text-emerald-200">
          <BookOpenCheck className="h-4 w-4" /> 信息源检索 Skill
        </p>
        <p className="mt-1 text-xs leading-5 text-emerald-800/80 dark:text-emerald-300/80">
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
                className="mt-2 w-full resize-none rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-normal leading-6 outline-none focus:border-emerald-400 dark:border-zinc-700 dark:bg-zinc-950"
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
              className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-xs font-bold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
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
                    <a href={paper.url} target="_blank" rel="noreferrer" className="flex min-w-0 flex-1 items-start gap-2 text-sm font-bold leading-6 text-sky-700 hover:underline dark:text-sky-300">
                      <span className="min-w-0 flex-1">{paper.title}</span>
                      <ExternalLink className="mt-1 h-3.5 w-3.5 shrink-0" />
                    </a>
                  </div>
                  <p className="mt-1 text-xs text-slate-500 dark:text-zinc-400">
                    {[paper.authors.slice(0, 4).join("、"), paper.year, paper.source_name].filter(Boolean).join(" · ")}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] font-semibold">
                    <span className="rounded-full bg-sky-50 px-2 py-1 text-sky-700 dark:bg-sky-950/40 dark:text-sky-300">平台：{paper.source_name}</span>
                    <span className="rounded-full bg-violet-50 px-2 py-1 text-violet-700 dark:bg-violet-950/40 dark:text-violet-300">证据：{paper.abstract_excerpt ? "摘要级" : "元数据级"}</span>
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-slate-600 dark:bg-zinc-800 dark:text-zinc-300">摘要：{paper.abstract_excerpt ? "可用" : "不可用"}</span>
                    <span className="rounded-full bg-amber-50 px-2 py-1 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">全文：{paper.full_text_available ? "可用" : "不可用"}</span>
                    <span className="rounded-full bg-orange-50 px-2 py-1 text-orange-700 dark:bg-orange-950/40 dark:text-orange-300">相关性：{paper.relevance.classification === "inference" ? "规则推断，待人工核验" : paper.relevance.classification}</span>
                  </div>
                  {paper.abstract_excerpt && (
                    <p className="mt-2 line-clamp-4 text-xs leading-5 text-slate-600 dark:text-zinc-300">{paper.abstract_excerpt}</p>
                  )}
                  <p className="mt-2 text-[11px] leading-5 text-slate-500 dark:text-zinc-400">{paper.relevance.content}</p>
                  <button type="button" onClick={() => void analyzePaper(paper.url)} className="mt-3 rounded-lg border border-orange-200 px-2 py-1 text-[11px] font-semibold text-orange-800 hover:bg-orange-50 dark:border-orange-900 dark:text-orange-300 dark:hover:bg-orange-950/30">分析元数据/摘要难点</button>
                </article>
              ))
            ) : (
              <p className="rounded-xl bg-slate-50 p-3 text-xs text-slate-600 dark:bg-zinc-950 dark:text-zinc-400">
                本次没有可展示的论文。{bundle.failure_reasons.join("；") || "可以调整检索词后重试。"}
              </p>
            )}
            {bundle.papers.length > 0 && (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-3 dark:border-emerald-900/60 dark:bg-emerald-950/20">
                <button
                  type="button"
                  onClick={() => void saveSelectedEvidence()}
                  disabled={!selectedPaperUrls.length || savingNote}
                  className="inline-flex items-center gap-2 rounded-lg bg-emerald-700 px-3 py-2 text-xs font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {savingNote ? <Loader2 className="h-4 w-4 animate-spin" /> : savedNoteId ? <CheckCircle2 className="h-4 w-4" /> : <Save className="h-4 w-4" />}
                  {savedNoteId ? "已保存为研究笔记" : `保存所选证据到 Notebook（${selectedPaperUrls.length}）`}
                </button>
                <p className="mt-2 text-[11px] leading-5 text-emerald-800 dark:text-emerald-300">保存内容包括研究主题、问题、所选 Evidence 来源和下一步建议，并保留当前 Research Conversation。</p>
                {savedNoteId && (
                  <Link href="/learning#research-notes" className="mt-3 inline-flex items-center gap-2 rounded-lg border border-emerald-300 bg-white px-3 py-2 text-xs font-bold text-emerald-800 transition hover:bg-emerald-100 dark:border-emerald-800 dark:bg-zinc-900 dark:text-emerald-300 dark:hover:bg-emerald-950/40">
                    <BookOpenCheck className="h-4 w-4" /> 返回学习笔记查看
                  </Link>
                )}
              </div>
            )}
            {paperAnalysis && (
              <article className="rounded-xl border border-orange-200 bg-orange-50/40 p-3 text-xs leading-5 dark:border-orange-900/60 dark:bg-orange-950/20">
                <p className="font-bold text-orange-900 dark:text-orange-200">论文/方向难点分析：{paperAnalysis.title}</p>
                <p className="mt-1 text-[11px] text-orange-800 dark:text-orange-300">{paperAnalysis.generation_mode === "llm" ? "模型个性化建议" : paperAnalysis.generation_mode === "rules_fallback" ? "模型失败后的规则降级" : "基础规则"}；仅基于{paperAnalysis.abstract_available ? "来源摘要与元数据" : "来源元数据"}；未下载全文。</p>
                <ul className="mt-2 space-y-2">{paperAnalysis.items.map((item) => <li key={item.area}><span className="font-semibold">{item.area}：</span>{item.content}{item.evidence_refs.map((reference) => <a key={`${reference.bundle_id}:${reference.paper_url}`} href={reference.paper_url} target="_blank" rel="noreferrer" className="ml-2 font-semibold text-sky-700 underline dark:text-sky-300">查看所用 Evidence</a>)}</li>)}</ul>
              </article>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
