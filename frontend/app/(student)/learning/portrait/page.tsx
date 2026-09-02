"use client";

/**
 * 学情与科研画像中枢 (Portraits Overview) — unified read-only aggregation page.
 *
 * Replaces dual frontend queries with a single call to GET /api/v1/portraits/overview (contract §4.1).
 * Displays learning mastery, review queue, traceable knowledge gaps, research conversations,
 * and cross-module bridges.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { LearningFlowStepper } from "@/components/learning/LearningFlowStepper";
import {
  Activity,
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  BookOpen,
  BookOpenCheck,
  CheckCircle2,
  Code2,
  FileQuestion,
  FlaskConical,
  Inbox,
  Link2,
  Presentation,
  RefreshCw,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import type {
  LearningKnowledgeGapOverview,
  PortraitsOverviewResponse,
  ResearchConversationOverview,
} from "@/lib/api/profile";
import { fetchPortraitsOverview } from "@/lib/api/profile";
import { getLearningSessionId } from "@/lib/api/learning";
import { getLocalProfileId } from "@/lib/api/workspaces";
import { getOrCreateLearnerId } from "@/lib/learner";

const GAP_SOURCE_LABELS: Record<string, string> = {
  quiz_attempt: "理解检查",
  confusion_mark: "不懂标记",
  practice_outcome: "动手实践",
  code_fill_attempt: "代码填空",
};

const SURFACE_LABELS: Record<string, string> = {
  ppt_page: "PPT 讲义页",
  explain: "名词解析",
  quiz_question: "练习题",
};

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

function KnowledgeGapRow({ item }: { item: LearningKnowledgeGapOverview }) {
  const sourceLabel = GAP_SOURCE_LABELS[item.source_type] || item.source_type;
  return (
    <li className="rounded-xl border border-slate-200/70 bg-slate-50/60 p-4 dark:border-zinc-800 dark:bg-zinc-800/30">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600 dark:bg-zinc-800 dark:text-zinc-300">
              {sourceLabel}
            </span>
            <span className="rounded-md bg-rose-50 px-1.5 py-0.5 text-[10px] font-semibold text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
              复盘缺口
            </span>
          </div>
          <p className="mt-2 truncate text-sm font-semibold text-slate-900 dark:text-zinc-100">
            {item.knowledge_point}
          </p>
          <p className="mt-1 break-words text-xs leading-relaxed text-slate-600 dark:text-zinc-300">
            {item.summary}
          </p>
        </div>
      </div>
    </li>
  );
}

function ResearchConversationCard({ item }: { item: ResearchConversationOverview }) {
  return (
    <li className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-2xs dark:border-zinc-800 dark:bg-zinc-900/60">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <FlaskConical className="h-4 w-4 shrink-0 text-sky-600 dark:text-sky-400" />
            <p className="truncate text-sm font-semibold text-slate-900 dark:text-zinc-100">
              {item.topic || "未命名科研主题"}
            </p>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-zinc-400">
            {item.readiness && (
              <span className="rounded-md bg-sky-50 px-2 py-0.5 text-[11px] font-semibold text-sky-700 dark:bg-sky-950/40 dark:text-sky-300">
                准备度 {item.readiness}
              </span>
            )}
            <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600 dark:bg-zinc-800 dark:text-zinc-300">
              文献包: {item.evidence_bundle_count}
            </span>
            {item.reproduction_pipeline_status && (
              <span className="rounded-md bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
                复现: {item.reproduction_pipeline_status === "evidence_linked" ? "已关联证据" : item.reproduction_pipeline_status}
              </span>
            )}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1.5 shrink-0">
          <Link
            href={`/research`}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-700 transition hover:bg-slate-100 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
          >
            进入会话
            <ArrowRight className="h-3 w-3" />
          </Link>
          <span className="text-[10px] text-slate-400 dark:text-zinc-500">
            {formatOccurredAt(item.updated_at)}
          </span>
        </div>
      </div>
    </li>
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

function SkeletonBlock() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="h-4 w-1/4 rounded-md bg-slate-100 dark:bg-zinc-800" />
      <div className="h-16 rounded-xl bg-slate-100 dark:bg-zinc-800" />
      <div className="h-16 rounded-xl bg-slate-100 dark:bg-zinc-800" />
    </div>
  );
}

export default function PortraitPage() {
  const [overview, setOverview] = useState<PortraitsOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const profileId = getOrCreateLearnerId();
    const localProfileId = getLocalProfileId();
    fetchPortraitsOverview(profileId, { localProfileId })
      .then((data) => {
        if (!cancelled) {
          setOverview(data);
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
    setError(null);
    setLoading(true);
    setRefreshKey((key) => key + 1);
  }

  const learning = overview?.learning;
  const research = overview?.research;
  const bridges = overview?.bridges;

  const hasMasteryData = (learning?.mastery.graded_attempts ?? 0) > 0;
  const hasStrengths = (learning?.mastery.strong_points.length ?? 0) > 0;
  const hasWeaknesses = (learning?.mastery.weak_points.length ?? 0) > 0;
  const hasKnowledgeGaps = (learning?.knowledge_gaps.length ?? 0) > 0;
  const hasReviewQueue = (learning?.review_queue.active_confusion_marks ?? 0) > 0;
  const hasResearchConvs = (research?.conversations.length ?? 0) > 0;

  const isEmpty =
    !hasMasteryData && !hasKnowledgeGaps && !hasReviewQueue && !hasResearchConvs;

  return (
    <div className="mx-auto max-w-[1100px] px-4 py-8 sm:py-10">
      <LearningFlowStepper
        currentStep="portrait"
        sessionId={getLearningSessionId()}
      />

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
              画像统一中枢
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl dark:text-zinc-100">
              学习与科研画像总览
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-500 dark:text-zinc-400">
              基于练习判分、代码挖空、不懂标记与科研会话记录聚合，两套画像与跨板块桥接一次呈现。
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

      {/* Empty state */}
      {!loading && !error && isEmpty && (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 py-20 text-center dark:border-zinc-800">
          <Inbox className="mb-3 h-10 w-10 text-slate-300 dark:text-zinc-600" strokeWidth={1.5} />
          <p className="text-sm font-semibold text-slate-600 dark:text-zinc-300">
            还没有学习或科研记录
          </p>
          <p className="mt-2 max-w-md text-xs leading-relaxed text-slate-400 dark:text-zinc-500">
            完成一次理解检查、动手实践，或开启科研会话，这里就会实时生成聚合画像。
          </p>
        </div>
      )}

      {!loading && !error && overview && !isEmpty && (
        <div className="space-y-6">
          {/* Bridges block */}
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl border border-indigo-200/80 bg-indigo-50/40 p-5 dark:border-indigo-900/40 dark:bg-indigo-950/20">
              <div className="flex items-center gap-2">
                <Link2 className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
                <h3 className="text-sm font-bold text-slate-900 dark:text-zinc-100">
                  学习 → 科研衔接
                </h3>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {bridges?.learning_to_research.confirmed ? (
                  <span className="inline-flex items-center gap-1 rounded-md bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300">
                    <CheckCircle2 className="h-3 w-3" />
                    已确认带入科研
                  </span>
                ) : bridges?.learning_to_research.latest_transfer_id ? (
                  <span className="rounded-md bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950/50 dark:text-amber-300">
                    待确认草稿
                  </span>
                ) : (
                  <span className="text-xs text-slate-500 dark:text-zinc-400">暂无迁移上下文</span>
                )}
                {bridges?.learning_to_research.has_mastery_snapshot && (
                  <span className="rounded-md bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-800 dark:bg-indigo-950/50 dark:text-indigo-300">
                    含掌握度快照
                  </span>
                )}
              </div>
            </div>

            <div className="rounded-2xl border border-sky-200/80 bg-sky-50/40 p-5 dark:border-sky-900/40 dark:bg-sky-950/20">
              <div className="flex items-center gap-2">
                <Target className="h-4 w-4 text-sky-600 dark:text-sky-400" />
                <h3 className="text-sm font-bold text-slate-900 dark:text-zinc-100">
                  科研 → 学习建议
                </h3>
              </div>
              <p className="mt-3 text-xs leading-relaxed text-slate-600 dark:text-zinc-300">
                {(bridges?.research_to_learning.pending_study_recommendations ?? 0) > 0 ? (
                  <span className="font-semibold text-sky-700 dark:text-sky-300">
                    最近科研会话有 {bridges?.research_to_learning.pending_study_recommendations} 条为科研而学的知识建议待消化
                  </span>
                ) : (
                  "当前会话暂无待学习建议"
                )}
              </p>
            </div>
          </div>

          {/* Knowledge Gaps */}
          {hasKnowledgeGaps && (
            <SectionCard
              icon={<Code2 className="h-4 w-4 text-cyan-600" strokeWidth={1.5} />}
              title="复盘知识缺口"
              hint="包含单选、填空、挖空与动手实践"
            >
              <ul className="space-y-2.5">
                {learning?.knowledge_gaps.map((item, idx) => (
                  <KnowledgeGapRow key={`${item.source_type}:${item.knowledge_point}:${idx}`} item={item} />
                ))}
              </ul>
            </SectionCard>
          )}

          {/* Mastery */}
          {hasMasteryData && (
            <SectionCard
              icon={<BarChart3 className="h-4 w-4 text-violet-500" strokeWidth={1.5} />}
              title="知识点掌握概况"
              hint={`共完成 ${learning?.mastery.graded_attempts} 次判分`}
            >
              {learning?.mastery.insufficient_sample && (
                <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50/60 p-3 text-xs text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-300">
                  <p className="font-semibold">部分知识点样本不足</p>
                  <p className="mt-0.5 text-slate-600 dark:text-amber-200/80">
                    达到 3 次判分后将展示确定掌握度，不编造虚假百分比。
                  </p>
                </div>
              )}

              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-xl border border-slate-100 bg-slate-50/50 p-4 dark:border-zinc-800 dark:bg-zinc-800/30">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-700 dark:text-emerald-300">
                    <TrendingUp className="h-3.5 w-3.5" />
                    掌握较好 (得分率 ≥ 75%)
                  </div>
                  {hasStrengths ? (
                    <ul className="mt-2.5 flex flex-wrap gap-1.5">
                      {learning?.mastery.strong_points.map((point) => (
                        <li
                          key={point}
                          className="rounded-lg bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
                        >
                          {point}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-2 text-xs text-slate-400 dark:text-zinc-500">暂无</p>
                  )}
                </div>

                <div className="rounded-xl border border-slate-100 bg-slate-50/50 p-4 dark:border-zinc-800 dark:bg-zinc-800/30">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-rose-700 dark:text-rose-300">
                    <TrendingDown className="h-3.5 w-3.5" />
                    需要加强 (得分率 &lt; 60%)
                  </div>
                  {hasWeaknesses ? (
                    <ul className="mt-2.5 flex flex-wrap gap-1.5">
                      {learning?.mastery.weak_points.map((point) => (
                        <li
                          key={point}
                          className="rounded-lg bg-rose-50 px-2.5 py-1 text-xs font-medium text-rose-800 dark:bg-rose-950/40 dark:text-rose-300"
                        >
                          {point}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-2 text-xs text-slate-400 dark:text-zinc-500">暂无</p>
                  )}
                </div>
              </div>
            </SectionCard>
          )}

          {/* Review queue */}
          {hasReviewQueue && (
            <SectionCard
              icon={<BookOpenCheck className="h-4 w-4 text-amber-500" strokeWidth={1.5} />}
              title="待复习标记队列"
              hint={`共 ${learning?.review_queue.active_confusion_marks} 处主动标记`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs text-slate-500 dark:text-zinc-400">主要分布载体：</span>
                {learning?.review_queue.top_surfaces.map((surface) => (
                  <span
                    key={surface}
                    className="inline-flex items-center gap-1 rounded-md bg-amber-50 px-2 py-1 text-xs font-medium text-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
                  >
                    {surface === "ppt_page" ? (
                      <Presentation className="h-3 w-3" />
                    ) : surface === "explain" ? (
                      <BookOpen className="h-3 w-3" />
                    ) : (
                      <FileQuestion className="h-3 w-3" />
                    )}
                    {SURFACE_LABELS[surface] || surface}
                  </span>
                ))}
              </div>
            </SectionCard>
          )}

          {/* Research conversations */}
          {hasResearchConvs && (
            <SectionCard
              icon={<FlaskConical className="h-4 w-4 text-sky-500" strokeWidth={1.5} />}
              title="科研引导会话"
              hint="最近探索与复现计划"
            >
              <ul className="space-y-3">
                {research?.conversations.map((conv) => (
                  <ResearchConversationCard key={conv.conversation_id} item={conv} />
                ))}
              </ul>
            </SectionCard>
          )}
        </div>
      )}

      {/* Footnote */}
      {!loading && overview && (
        <p className="mt-8 flex items-center justify-center gap-1.5 text-center text-[11px] text-slate-400 dark:text-zinc-600">
          <Activity className="h-3.5 w-3.5" strokeWidth={1.5} />
          画像统一读口由规则聚合生成，不调用模型、不联网；Practice 复盘不外泄源码与测试数据。
        </p>
      )}
    </div>
  );
}
