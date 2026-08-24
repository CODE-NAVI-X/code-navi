"use client";

/**
 * 学情画像 (learning portrait) — the anonymous, cross-session snapshot of one
 * browser's learning activity.
 *
 * Data comes exclusively from real persisted facts: graded ``quiz_attempts``
 * (single → rules, fill_blank → mock/model, short_answer → model) and
 * self-reported 不懂/懂了 ``confusion_marks``. It never invents a number:
 * below the minimum sample size (3 graded attempts) a knowledge point shows
 * 样本不足 instead of a fake percentage.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertCircle,
  ArrowLeft,
  BarChart3,
  BookOpen,
  BookOpenCheck,
  Check,
  ChevronDown,
  Code2,
  FileQuestion,
  HelpCircle,
  Inbox,
  Loader2,
  Presentation,
  RefreshCw,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import type {
  ConfusionItem,
  ConfusionMarkItem,
  KnowledgeGapItem,
  MarkSourceType,
  ProfileMastery,
  ProfileResponse,
} from "@/lib/api/profile";
import { fetchKnowledgeGaps, fetchProfile, setConfusionMark } from "@/lib/api/profile";
import { getLearningSessionId } from "@/lib/api/learning";
import { getOrCreateLearnerId } from "@/lib/learner";

// ── Thresholds mirror the backend service (learning_profile/service.py) ────────

const STRENGTH_THRESHOLD = 0.75;
const WEAKNESS_THRESHOLD = 0.6;
const MIN_MASTERY_SAMPLE = 3;

function formatRate(rate: number | null): string {
  if (rate === null) return "—";
  return `${Math.round(rate * 100)}%`;
}

/** Color the mastery bar by the same thresholds the backend uses. */
function barColor(rate: number): string {
  if (rate >= STRENGTH_THRESHOLD) return "bg-emerald-500";
  if (rate >= WEAKNESS_THRESHOLD) return "bg-amber-500";
  return "bg-rose-500";
}

function masteryBadge(m: ProfileMastery) {
  if (m.status !== "sufficient" || m.mastery === null) {
    return (
      <span className="shrink-0 rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500 dark:bg-zinc-800 dark:text-zinc-400">
        样本不足
      </span>
    );
  }
  const cls =
    m.mastery >= STRENGTH_THRESHOLD
      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
      : m.mastery >= WEAKNESS_THRESHOLD
        ? "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300"
        : "bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300";
  return (
    <span className={`shrink-0 rounded-md px-2 py-0.5 text-[10px] font-semibold ${cls}`}>
      {formatRate(m.mastery)}
    </span>
  );
}

function MasteryRow({ m }: { m: ProfileMastery }) {
  const sufficient = m.status === "sufficient" && m.mastery !== null;
  const rate = m.quiz_rate ?? 0;
  const widthPct = sufficient ? `${Math.max(2, Math.round(rate * 100))}%` : "0%";
  return (
    <li className="rounded-xl border border-slate-200/70 bg-slate-50/50 p-4 dark:border-zinc-800 dark:bg-zinc-800/30">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="min-w-0 flex-1 truncate text-sm font-semibold text-slate-800 dark:text-zinc-200">
          {m.knowledge_point}
        </p>
        {masteryBadge(m)}
      </div>
      <div className="mt-2.5 h-2 w-full overflow-hidden rounded-full bg-slate-200/80 dark:bg-zinc-800">
        <div
          className={`h-full rounded-full transition-all ${sufficient ? barColor(rate) : "bg-transparent"}`}
          style={{ width: widthPct }}
        />
      </div>
      <p className="mt-1.5 text-[11px] text-slate-400 dark:text-zinc-500">
        {sufficient
          ? `已作答 ${m.sample_size} 次 · 得分率 ${formatRate(m.quiz_rate)}`
          : `已作答 ${m.sample_size}/${MIN_MASTERY_SAMPLE} 次，达 ${MIN_MASTERY_SAMPLE} 次后展示掌握度`}
      </p>
    </li>
  );
}

const SOURCE_LABELS: Record<MarkSourceType, string> = {
  ppt_page: "PPT 页",
  explain: "名词解析",
  quiz_question: "练习题",
};

const GAP_SOURCE_LABELS: Record<KnowledgeGapItem["sourceType"], string> = {
  quiz_attempt: "理解检查",
  confusion_mark: "不懂标记",
  practice_outcome: "动手实践",
};

const GAP_KIND_LABELS: Record<string, string> = {
  quiz_incorrect: "答题错误",
  quiz_partial_score: "部分得分",
  self_reported_confusion: "主动标记不懂",
  syntax_error: "语法错误",
  runtime_error: "运行错误",
  time_limit: "运行超时",
  output_limit: "输出超限",
  wrong_answer: "答案错误",
};

//: Fixed column order (名词解析 → PPT 页 → 练习题) with per-surface icons.
const SURFACE_COLUMNS: {
  type: MarkSourceType;
  icon: React.ReactNode;
}[] = [
  { type: "explain", icon: <BookOpen className="h-3 w-3" strokeWidth={1.5} /> },
  { type: "ppt_page", icon: <Presentation className="h-3 w-3" strokeWidth={1.5} /> },
  { type: "quiz_question", icon: <FileQuestion className="h-3 w-3" strokeWidth={1.5} /> },
];

function formatMarkedAt(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatOccurredAt(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** "名词解析 2 · PPT 页 1" — per-surface count summary for the row header. */
function sourceSummary(item: ConfusionItem): string {
  return SURFACE_COLUMNS.flatMap(({ type }) => {
    const count = (item.by_type[type] ?? []).length;
    return count > 0 ? [`${SOURCE_LABELS[type]} ${count}`] : [];
  }).join(" · ");
}

function ConfusionRow({
  item,
  onMarkCleared,
}: {
  item: ConfusionItem;
  onMarkCleared: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [clearing, setClearing] = useState<string | null>(null);
  const [clearError, setClearError] = useState<string | null>(null);

  /** 已懂 — clear every 不懂 mark on this surface, then refresh the portrait. */
  async function handleClear(sourceType: MarkSourceType, sourceRef: string) {
    if (clearing) return;
    setClearing(sourceRef);
    setClearError(null);
    try {
      await setConfusionMark({
        session_id: getLearningSessionId(),
        profile_id: getOrCreateLearnerId(),
        knowledge_point: item.knowledge_point,
        source_type: sourceType,
        source_ref: sourceRef,
        mark: false,
      });
      onMarkCleared();
    } catch (err) {
      setClearError(err instanceof Error ? err.message : String(err));
    } finally {
      setClearing(null);
    }
  }

  return (
    <li className="rounded-xl border border-amber-200/70 bg-amber-50/40 dark:border-amber-900/40 dark:bg-amber-950/20">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        className="flex w-full cursor-pointer items-center justify-between gap-3 p-4 text-left"
      >
        <div className="flex min-w-0 items-center gap-2">
          <HelpCircle className="h-4 w-4 shrink-0 text-amber-500" strokeWidth={1.5} />
          <p className="min-w-0 flex-1 truncate text-sm font-semibold text-slate-800 dark:text-zinc-200">
            {item.knowledge_point}
          </p>
          <span className="shrink-0 rounded-md bg-amber-100/80 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-900/50 dark:text-amber-300">
            {item.mark_count} 处标记
          </span>
        </div>
        <span className="flex shrink-0 items-center gap-1.5 text-[11px] text-amber-600/90 dark:text-amber-300/80">
          {sourceSummary(item)}
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`}
            strokeWidth={1.5}
          />
        </span>
      </button>

      {open && (
        <div className="border-t border-amber-100 px-4 pb-4 pt-3 dark:border-amber-900/30">
          {clearError && (
            <p className="mb-3 rounded-lg bg-red-50 px-3 py-1.5 text-[11px] text-red-700 dark:bg-red-950/30 dark:text-red-300">
              {clearError}
            </p>
          )}
          <div className="grid gap-4 md:grid-cols-3">
            {SURFACE_COLUMNS.map(({ type, icon }) => {
              const marks: ConfusionMarkItem[] = item.by_type[type] ?? [];
              if (marks.length === 0) return null;
              return (
                <div key={type} className="min-w-0">
                  <div className="mb-2 flex items-center gap-1.5 text-[10px] font-bold tracking-wide text-slate-500 uppercase dark:text-zinc-400">
                    {icon}
                    {SOURCE_LABELS[type]}
                    <span className="rounded bg-amber-100/80 px-1 py-px font-semibold text-amber-700 dark:bg-amber-900/50 dark:text-amber-300">
                      {marks.length}
                    </span>
                  </div>
                  <ul className="space-y-1.5">
                    {marks.map((mark) => (
                      <li
                        key={mark.source_ref}
                        className="flex items-start justify-between gap-2 rounded-lg bg-white/80 px-2.5 py-2 text-[11px] leading-relaxed text-slate-700 dark:bg-zinc-900/80 dark:text-zinc-300"
                      >
                        <span className="min-w-0 flex-1 break-words">{mark.label}</span>
                        <div className="flex shrink-0 flex-col items-end gap-1">
                          <button
                            type="button"
                            disabled={clearing !== null}
                            onClick={() => void handleClear(type, mark.source_ref)}
                            className="inline-flex cursor-pointer items-center gap-1 rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-emerald-950/40 dark:text-emerald-300"
                          >
                            {clearing === mark.source_ref ? (
                              <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.5} />
                            ) : (
                              <Check className="h-3 w-3" strokeWidth={1.5} />
                            )}
                            已懂
                          </button>
                          <span className="text-[10px] text-slate-400 dark:text-zinc-500">
                            {formatMarkedAt(mark.marked_at)}
                          </span>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </li>
  );
}

function KnowledgeGapRow({ item }: { item: KnowledgeGapItem }) {
  const sourceLabel = GAP_SOURCE_LABELS[item.sourceType];
  const kindLabel = GAP_KIND_LABELS[item.gapKind] ?? item.gapKind;
  return (
    <li className="rounded-xl border border-slate-200/70 bg-slate-50/60 p-4 dark:border-zinc-800 dark:bg-zinc-800/30">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600 dark:bg-zinc-800 dark:text-zinc-300">
              {sourceLabel}
            </span>
            <span className="rounded-md bg-rose-50 px-1.5 py-0.5 text-[10px] font-semibold text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
              {kindLabel}
            </span>
          </div>
          <p className="mt-2 truncate text-sm font-semibold text-slate-900 dark:text-zinc-100">
            {item.topic}
          </p>
          <p className="mt-1 break-words text-xs leading-relaxed text-slate-600 dark:text-zinc-300">
            {item.summary || item.label}
          </p>
        </div>
        <span className="shrink-0 text-[10px] text-slate-400 dark:text-zinc-500">
          {formatOccurredAt(item.occurredAt)}
        </span>
      </div>
      <p className="mt-2 truncate text-[10px] text-slate-400 dark:text-zinc-500">
        {item.sourceType}:{item.sourceId}
      </p>
    </li>
  );
}

function SkeletonBlock() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="h-4 w-1/4 rounded-md bg-slate-100 dark:bg-zinc-800" />
      <div className="h-16 rounded-xl bg-slate-100 dark:bg-zinc-800" />
      <div className="h-16 rounded-xl bg-slate-100 dark:bg-zinc-800" />
    </div>
  );
}

function SectionCard({
  icon,
  title,
  hint,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-xs dark:border-zinc-800 dark:bg-zinc-900/90">
      <div className="mb-4 flex items-center gap-2">
        {icon}
        <h2 className="text-sm font-bold tracking-tight text-slate-900 dark:text-zinc-100">
          {title}
        </h2>
        {hint && (
          <span className="ml-1 text-[10px] font-normal text-slate-400 dark:text-zinc-500">
            {hint}
          </span>
        )}
      </div>
      {children}
    </section>
  );
}

export default function PortraitPage() {
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [knowledgeGaps, setKnowledgeGaps] = useState<KnowledgeGapItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // Fetch the anonymous portrait on mount and on manual refresh. ``loading``
  // starts ``true`` so the first render is the skeleton; all setState happens
  // in async callbacks, never synchronously in the effect body.
  useEffect(() => {
    let cancelled = false;
    const profileId = getOrCreateLearnerId();
    Promise.all([fetchProfile(profileId), fetchKnowledgeGaps(profileId)])
      .then(([profileData, gapData]) => {
        if (!cancelled) {
          setProfile(profileData);
          setKnowledgeGaps(gapData.items);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  function handleRefresh() {
    // Reset state from the event handler (never inside the effect body).
    setError(null);
    setLoading(true);
    setRefreshKey((key) => key + 1);
  }

  /** Refetch after a 已懂 clear — without flashing the skeleton. */
  function handleMarkCleared() {
    setError(null);
    setRefreshKey((key) => key + 1);
  }

  const isEmpty = profile && profile.mastery.length === 0 && profile.confusion.length === 0;
  const hasKnowledgeGaps = knowledgeGaps.length > 0;
  const hasMastery = (profile?.mastery.length ?? 0) > 0;

  return (
    <div className="mx-auto max-w-[1100px] px-4 py-8 sm:py-10">
      {/* Header */}
      <header className="mb-8">
        <Link
          href="/learning"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 transition hover:text-slate-800 dark:text-zinc-400 dark:hover:text-zinc-200"
        >
          <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
          返回知识学习
        </Link>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="mb-1.5 inline-flex items-center gap-1.5 rounded-md bg-violet-100/80 px-2 py-0.5 text-[11px] font-semibold tracking-wider text-violet-700 dark:bg-violet-950/40 dark:text-violet-300">
              <Sparkles className="h-3 w-3" strokeWidth={1.5} />
              学情画像
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl dark:text-zinc-100">
              我的学习掌握情况
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-500 dark:text-zinc-400">
              基于理解检查、动手实践结果与「不懂」标记，按本地资料与匿名 profile_id 聚合。它不是账号权限或跨设备身份。
            </p>
          </div>
          <button
            type="button"
            onClick={handleRefresh}
            disabled={loading}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} strokeWidth={1.5} />
            刷新
          </button>
        </div>
      </header>

      {/* Loading */}
      {loading && (
        <div className="space-y-6">
          <SkeletonBlock />
          <SkeletonBlock />
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50/70 p-4 text-xs text-red-800 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-300">
          <AlertCircle className="h-4 w-4 shrink-0 text-red-600 dark:text-red-400" strokeWidth={1.5} />
          <div>
            <p className="font-semibold">画像加载失败</p>
            <p className="mt-0.5 text-slate-600 dark:text-red-200/80">{error}</p>
          </div>
        </div>
      )}

      {/* Empty state — never a fake score */}
      {!loading && !error && isEmpty && !hasKnowledgeGaps && (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 py-20 text-center dark:border-zinc-800">
          <Inbox className="mb-3 h-10 w-10 text-slate-300 dark:text-zinc-600" strokeWidth={1.5} />
          <p className="text-sm font-semibold text-slate-600 dark:text-zinc-300">
            还没有学习记录
          </p>
          <p className="mt-2 max-w-md text-xs leading-relaxed text-slate-400 dark:text-zinc-500">
            完成一次理解检查、动手实践，或点击学习页面的「标记不懂」，这里就会生成可追溯复盘项。
          </p>
        </div>
      )}

      {!loading && !error && profile && (!isEmpty || hasKnowledgeGaps) && (
        <div className="space-y-6">
          <SectionCard
            icon={<Code2 className="h-4 w-4 text-cyan-600" strokeWidth={1.5} />}
            title="复盘知识缺口"
            hint="按来源可追溯"
          >
            {hasKnowledgeGaps ? (
              <ul className="space-y-2.5">
                {knowledgeGaps.map((item) => (
                  <KnowledgeGapRow key={`${item.sourceType}:${item.sourceId}`} item={item} />
                ))}
              </ul>
            ) : (
              <div className="flex items-center gap-2 text-xs text-slate-400 dark:text-zinc-500">
                <Target className="h-4 w-4" strokeWidth={1.5} />
                暂无可追溯复盘项。
              </div>
            )}
          </SectionCard>

          {/* Mastery bars */}
          {hasMastery && (
            <SectionCard
              icon={<BarChart3 className="h-4 w-4 text-violet-500" strokeWidth={1.5} />}
              title="知识点掌握度"
              hint="按判分结果聚合"
            >
              {profile.mastery.length > 0 ? (
                <ul className="space-y-3">
                  {profile.mastery.map((m) => (
                    <MasteryRow key={m.knowledge_point} m={m} />
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-slate-400 dark:text-zinc-500">
                  暂无判分数据，完成练习题后展示。
                </p>
              )}
            </SectionCard>
          )}

          {/* Strengths / Weaknesses */}
          {(profile.strengths.length > 0 || profile.weaknesses.length > 0) && (
            <div className="grid gap-6 md:grid-cols-2">
              <SectionCard
                icon={<TrendingUp className="h-4 w-4 text-emerald-500" strokeWidth={1.5} />}
                title="掌握较好"
                hint="得分率 ≥ 75%"
              >
                {profile.strengths.length > 0 ? (
                  <ul className="flex flex-wrap gap-2">
                    {profile.strengths.map((name) => (
                      <li
                        key={name}
                        className="rounded-lg bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
                      >
                        {name}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-slate-400 dark:text-zinc-500">暂无</p>
                )}
              </SectionCard>
              <SectionCard
                icon={<TrendingDown className="h-4 w-4 text-rose-500" strokeWidth={1.5} />}
                title="需要加强"
                hint="得分率 < 60%"
              >
                {profile.weaknesses.length > 0 ? (
                  <ul className="flex flex-wrap gap-2">
                    {profile.weaknesses.map((name) => (
                      <li
                        key={name}
                        className="rounded-lg bg-rose-50 px-2.5 py-1 text-xs font-medium text-rose-700 dark:bg-rose-950/40 dark:text-rose-300"
                      >
                        {name}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-slate-400 dark:text-zinc-500">暂无</p>
                )}
              </SectionCard>
            </div>
          )}

          {/* Confusion / 待复习 */}
          <SectionCard
            icon={<BookOpenCheck className="h-4 w-4 text-amber-500" strokeWidth={1.5} />}
            title="待复习知识点"
            hint="标记过「不懂」"
          >
            {profile.confusion.length > 0 ? (
              <ul className="space-y-2.5">
                {profile.confusion.map((item) => (
                  <ConfusionRow
                    key={item.knowledge_point}
                    item={item}
                    onMarkCleared={handleMarkCleared}
                  />
                ))}
              </ul>
            ) : (
              <div className="flex items-center gap-2 text-xs text-slate-400 dark:text-zinc-500">
                <Target className="h-4 w-4" strokeWidth={1.5} />
                暂无待复习项。学习时点击「标记不懂」即可把知识点加入这里。
              </div>
            )}
          </SectionCard>
        </div>
      )}

      {/* Footnote */}
      {!loading && profile && (
        <p className="mt-8 flex items-center justify-center gap-1.5 text-center text-[11px] text-slate-400 dark:text-zinc-600">
          <Activity className="h-3.5 w-3.5" strokeWidth={1.5} />
          画像与复盘只读取已有事实；Practice 复盘不展示源码、stdin、隐藏测试或 raw 输出。
        </p>
      )}
    </div>
  );
}
