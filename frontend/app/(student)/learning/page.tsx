"use client";

import {
  type ExplainResponse,
  explainKnowledgePoint,
  LearningApiError,
} from "@/lib/api/learning";
import TextSelectionPopover from "@/components/learning/TextSelectionPopover";
import { StructuredNotebook } from "@/components/learning/StructuredNotebook";
import { DownstreamGoCard } from "@/components/learning/DownstreamGoCard";
import { type JSX, useState, useEffect } from "react";
import {
  setLearningSnapshot,
  useLearningStore,
} from "@/lib/store/learning-store";
import {
  BookOpen,
  Sparkles,
  Compass,
  ExternalLink,
  Layers,
  GraduationCap,
  Search,
  Loader2,
  AlertCircle,
} from "lucide-react";

// ── UI helpers ─────────────────────────────────────────────────────────────────

/** Trivial skeleton shimmer while a request is in-flight. */
function SkeletonLine({ width = "w-full" }: { width?: string }) {
  return (
    <div className={`h-4 ${width} animate-pulse rounded-md bg-slate-100 dark:bg-zinc-800`} />
  );
}

function ExplanationCard({ data }: { data: ExplainResponse }) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-7 shadow-xs dark:border-zinc-800 dark:bg-zinc-900/90 transition-all">
      <h2 className="mb-5 text-2xl font-bold tracking-tight text-slate-900 dark:text-zinc-100">
        {data.knowledge_point}
      </h2>

      {/* Summary block */}
      <div className="mb-5 rounded-r-xl border-l-2 border-indigo-500 bg-indigo-50/40 p-5 dark:bg-indigo-950/20">
        <div className="mb-2 flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-md bg-indigo-100/80 px-2 py-0.5 text-[11px] font-semibold tracking-wider text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-300">
            <Sparkles className="h-3 w-3" strokeWidth={1.5} />
            核心概念提炼
          </span>
        </div>
        <p className="text-sm leading-relaxed text-slate-800 dark:text-zinc-200">{data.summary}</p>
      </div>

      {/* Detail block (optional) */}
      {data.detail && (
        <div className="mb-5 rounded-r-xl border-l-2 border-emerald-500 bg-emerald-50/40 p-5 dark:bg-emerald-950/20">
          <div className="mb-2 flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-md bg-emerald-100/80 px-2 py-0.5 text-[11px] font-semibold tracking-wider text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300">
              <GraduationCap className="h-3 w-3" strokeWidth={1.5} />
              原理解析与应用场景
            </span>
          </div>
          <p className="text-sm leading-relaxed whitespace-pre-wrap text-slate-800 dark:text-zinc-200">
            {data.detail}
          </p>
        </div>
      )}

      {/* Citations */}
      {data.citations.length > 0 && (
        <div className="mt-7 pt-4 border-t border-slate-100 dark:border-zinc-800/60">
          <div className="mb-3.5 flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-slate-400" strokeWidth={1.5} />
            <h3 className="text-xs font-semibold tracking-wider text-slate-500 uppercase dark:text-zinc-400">
              权威文献与引用来源
            </h3>
          </div>
          <ul className="space-y-2.5">
            {data.citations.map((cit, i) => (
              <li
                key={`${cit.source_title}-${i}`}
                className="rounded-xl border border-slate-200/60 bg-slate-50/60 p-4 text-xs dark:border-zinc-800/80 dark:bg-zinc-800/40"
              >
                <p className="font-semibold text-slate-900 dark:text-zinc-200">{cit.source_title}</p>
                {cit.snippet && (
                  <blockquote className="mt-2 border-l-2 border-slate-300 pl-3 italic text-slate-600 dark:border-zinc-700 dark:text-zinc-400">
                    &ldquo;{cit.snippet}&rdquo;
                  </blockquote>
                )}
                {cit.uri && (
                  <a
                    href={cit.uri}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2.5 inline-flex items-center gap-1.5 text-xs font-medium text-slate-700 transition hover:text-slate-900 underline decoration-slate-300 hover:decoration-slate-600 dark:text-zinc-300 dark:hover:text-white dark:decoration-zinc-700"
                  >
                    <ExternalLink className="h-3 w-3 shrink-0 text-slate-400" strokeWidth={1.5} />
                    <span className="truncate">{cit.uri}</span>
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

// ── Page component ─────────────────────────────────────────────────────────────

export default function LearningPage(): JSX.Element {
  const savedSnapshot = useLearningStore((s) => s);

  const [query, setQuery] = useState(savedSnapshot?.query ?? "");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ExplainResponse | null>(
    (savedSnapshot?.result as ExplainResponse) ?? null,
  );
  const [error, setError] = useState<string | null>(null);

  // Persist snapshot whenever query or result changes
  useEffect(() => {
    if (result || query) {
      setLearningSnapshot({ query, result });
    }
  }, [query, result]);

  const [notebookOpen, setNotebookOpen] = useState(false);
  const [goCardVisible, setGoCardVisible] = useState(true);

  async function handleSubmit(formEvent: React.FormEvent) {
    formEvent.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await explainKnowledgePoint({ knowledge_point: trimmed });
      setResult(data);
    } catch (err) {
      setError(
        err instanceof LearningApiError ? err.message : String(err),
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:py-12">
      {/* Top Floating Control Bar - Swiss Light Gray Minimalist */}
      <div className="mb-8 flex items-center justify-between rounded-xl border border-slate-200/70 bg-slate-100/70 p-3 backdrop-blur-md dark:border-zinc-800/70 dark:bg-zinc-900/70">
        <div className="flex items-center gap-2">
          <Compass className="h-4 w-4 text-slate-500 dark:text-zinc-400" strokeWidth={1.5} />
          <span className="text-xs font-medium text-slate-700 dark:text-zinc-300">
            知识探索与学术辅助工具栏
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setNotebookOpen(true)}
            className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-2xs transition hover:bg-slate-50 hover:text-slate-900 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700/80 dark:hover:text-white"
          >
            <BookOpen className="h-3.5 w-3.5 text-slate-500 dark:text-zinc-400" strokeWidth={1.5} />
            学习笔记
          </button>
          <button
            type="button"
            onClick={() => setGoCardVisible((prev) => !prev)}
            className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-2xs transition hover:bg-slate-50 hover:text-slate-900 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700/80 dark:hover:text-white"
          >
            <Layers className="h-3.5 w-3.5 text-slate-500 dark:text-zinc-400" strokeWidth={1.5} />
            节点流转看板 {goCardVisible ? "已开启" : "已隐藏"}
          </button>
        </div>
      </div>

      {/* Header */}
      <header className="mb-8 text-center">
        <div className="mb-3 inline-flex items-center justify-center rounded-full bg-slate-100 p-2.5 text-slate-700 dark:bg-zinc-800 dark:text-zinc-300">
          <Sparkles className="h-6 w-6" strokeWidth={1.5} />
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl dark:text-zinc-100">
          知识探索与学术深度解析
        </h1>
        <p className="mt-2.5 text-sm text-slate-500 dark:text-zinc-400">
          输入专业概念、协议原理或学术难题，获取带权威引用的结构化解答
        </p>
      </header>

      {/* Search form */}
      <form onSubmit={handleSubmit} className="mb-8 flex gap-2.5">
        <div className="relative flex-1">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder='例如 "Monad"、"DHCP 4阶段报文交互"、"TCP 拥塞控制"…'
            maxLength={512}
            disabled={loading}
            className="w-full rounded-xl border border-slate-200 bg-white px-4.5 py-3.5 text-sm text-slate-900 shadow-2xs placeholder:text-slate-400 focus:border-slate-400 focus:ring-4 focus:ring-slate-100 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-100 dark:placeholder:text-zinc-500 dark:focus:ring-zinc-800"
          />
        </div>
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="flex cursor-pointer items-center gap-2 rounded-xl bg-slate-900 px-6 py-3.5 text-sm font-medium text-white shadow-2xs transition hover:bg-slate-800 focus:ring-2 focus:ring-slate-900/20 focus:outline-none active:scale-98 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.5} />
              深度思考中…
            </>
          ) : (
            <>
              <Search className="h-4 w-4" strokeWidth={1.5} />
              深度解析
            </>
          )}
        </button>
      </form>

      {/* Loading */}
      {loading && (
        <div className="space-y-4 rounded-2xl border border-slate-200/80 bg-white p-7 shadow-2xs dark:border-zinc-800 dark:bg-zinc-900">
          <SkeletonLine width="w-2/5" />
          <SkeletonLine />
          <SkeletonLine width="w-4/5" />
          <SkeletonLine width="w-3/5" />
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50/70 p-4 text-xs text-red-800 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-300">
          <AlertCircle className="h-4 w-4 shrink-0 text-red-600 dark:text-red-400" strokeWidth={1.5} />
          <div>
            <p className="font-semibold">请求响应异常</p>
            <p className="mt-0.5 text-slate-600 dark:text-red-200/80">{error}</p>
          </div>
        </div>
      )}

      {/* Result */}
      {result && <ExplanationCard data={result} />}

      {/* Empty state */}
      {!loading && !error && !result && (
        <div className="rounded-2xl border border-dashed border-slate-200 py-16 text-center text-slate-400 dark:border-zinc-800 dark:text-zinc-500">
          <BookOpen className="mx-auto mb-3 h-8 w-8 text-slate-300 dark:text-zinc-600" strokeWidth={1.5} />
          <p className="text-xs font-medium">在上方输入专业概念或学术词条以开启深度解析</p>
        </div>
      )}

      {/* Floating text-selection popover — works on the whole page */}
      <TextSelectionPopover />

      {/* Side-Drawer Notebook */}
      <StructuredNotebook
        open={notebookOpen}
        onDismiss={() => setNotebookOpen(false)}
        sessionId="sess_demo_123"
      />

      {/* Downstream Flow Go Card */}
      {goCardVisible && (
        <DownstreamGoCard
          knowledgePoint={result?.knowledge_point || query || "DHCP 四阶段报文交互"}
          knowledgePointId="kp_dhcp_4stage"
          sessionId="sess_demo_123"
          onDismiss={() => setGoCardVisible(false)}
        />
      )}
    </div>
  );
}