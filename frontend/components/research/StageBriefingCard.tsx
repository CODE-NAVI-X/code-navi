"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  GraduationCap,
  Layers,
  Lightbulb,
  Loader2,
  RefreshCw,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import {
  fetchStageBriefing,
  fetchStudyRecommendations,
  type StageBriefingResponse,
  type StudyRecommendation,
} from "@/lib/api/research";

interface StageBriefingCardProps {
  conversationId: string;
}

export function StageBriefingCard({ conversationId }: StageBriefingCardProps) {
  const [briefing, setBriefing] = useState<StageBriefingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const [recommendations, setRecommendations] = useState<StudyRecommendation[] | null>(null);
  const [loadingRecs, setLoadingRecs] = useState(false);
  const [recError, setRecError] = useState<string | null>(null);
  const [showRecs, setShowRecs] = useState(false);

  useEffect(() => {
    let cancelled = false;

    fetchStageBriefing(conversationId, true)
      .then((data) => {
        if (!cancelled) {
          setBriefing(data);
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
  }, [conversationId, refreshKey]);

  async function handleLoadRecommendations() {
    if (recommendations) {
      setShowRecs((v) => !v);
      return;
    }
    setLoadingRecs(true);
    setRecError(null);
    try {
      const res = await fetchStudyRecommendations(conversationId, true);
      setRecommendations(res.recommendations);
      setShowRecs(true);
    } catch (err) {
      setRecError(err instanceof Error ? err.message : "获取为科研而学知识点建议失败");
    } finally {
      setLoadingRecs(false);
    }
  }

  if (loading) {
    return (
      <div className="app-card mb-6 rounded-2xl p-4 sm:p-5">
        <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-zinc-400">
          <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
          <span>正在加载阶段简报与学习背景…</span>
        </div>
      </div>
    );
  }

  if (error || !briefing) {
    return null; // Silently degrade or return null if not available
  }

  return (
    <section
      aria-labelledby="stage-briefing-title"
      className="app-card mb-6 rounded-2xl p-5 sm:p-6 shadow-xs border-indigo-100 dark:border-indigo-950/60 bg-gradient-to-br from-white via-indigo-50/10 to-slate-50/30 dark:from-zinc-900 dark:via-indigo-950/10 dark:to-zinc-900/50"
    >
      {/* 标题栏 */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3.5 dark:border-zinc-800">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-100 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-400">
            <Sparkles className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 id="stage-briefing-title" className="text-sm font-bold text-slate-900 dark:text-zinc-100">
                科研阶段简报 (Stage Briefing)
              </h2>
              <span className="rounded-md bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300 border border-indigo-200/60 dark:border-indigo-800/40">
                纯规则衔接
              </span>
            </div>
            <p className="text-xs text-slate-500 dark:text-zinc-400">
              六步闭环第 5&rarr;6 步：笔记与学情画像向科研引导的无缝衔接
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => {
            setError(null);
            setLoading(true);
            setRefreshKey((k) => k + 1);
          }}
          className="inline-flex cursor-pointer items-center gap-1 text-xs text-slate-400 hover:text-slate-700 dark:hover:text-zinc-200 transition"
          title="刷新简报"
        >
          <RefreshCw className="h-3 w-3" />
          <span>刷新</span>
        </button>
      </div>

      {/* 学习背景摘要 */}
      {briefing.has_learning_context ? (
        <div className="mt-4 space-y-3.5">
          <div className="rounded-xl bg-white/80 p-3.5 border border-slate-200/70 dark:bg-zinc-800/40 dark:border-zinc-800">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-700 dark:text-zinc-300">
              <BookOpen className="h-3.5 w-3.5 text-indigo-500" />
              <span>已确认学习主题：</span>
              <strong className="text-slate-900 dark:text-zinc-100">{briefing.stage_summary.topic || "无特定主题"}</strong>
            </div>
            {briefing.stage_summary.digest && (
              <p className="mt-2 text-xs leading-relaxed text-slate-600 dark:text-zinc-300 whitespace-pre-wrap">
                {briefing.stage_summary.digest}
              </p>
            )}

            {/* 掌握度快照 */}
            {briefing.stage_summary.knowledge_points && briefing.stage_summary.knowledge_points.length > 0 && (
              <div className="mt-3 pt-2.5 border-t border-slate-100 dark:border-zinc-800">
                <p className="text-xs font-semibold text-slate-500 dark:text-zinc-400 mb-1.5">
                  学习掌握度快照：
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {briefing.stage_summary.knowledge_points.map((kp) => (
                    <span
                      key={kp.name}
                      className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-700 dark:bg-zinc-800 dark:text-zinc-300 border border-slate-200/50 dark:border-zinc-700/50"
                    >
                      <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                      <span>{kp.name}</span>
                      {kp.mastery !== null && (
                        <span className="font-semibold text-emerald-600 dark:text-emerald-400 text-xs">
                          {Math.round(kp.mastery * 100)}%
                        </span>
                      )}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* 论文复现路径与已存证据 */}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl bg-white/80 p-3 border border-slate-200/70 dark:bg-zinc-800/40 dark:border-zinc-800">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 dark:text-zinc-300">
                <Layers className="h-3.5 w-3.5 text-blue-500" />
                <span>论文复现路径</span>
              </div>
              <div className="mt-2 text-xs text-slate-600 dark:text-zinc-400">
                <span>已收录文献包：<strong className="text-slate-900 dark:text-zinc-100">{briefing.reproduction_entry.bundle_count}</strong> 篇</span>
                {briefing.reproduction_entry.pipeline_status && (
                  <span className="ml-2">· 状态：{briefing.reproduction_entry.pipeline_status}</span>
                )}
              </div>
            </div>

            {briefing.evidence_trends.length > 0 && (
              <div className="rounded-xl bg-white/80 p-3 border border-slate-200/70 dark:bg-zinc-800/40 dark:border-zinc-800">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 dark:text-zinc-300">
                  <TrendingUp className="h-3.5 w-3.5 text-indigo-500" />
                  <span>已存证据方向推荐</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {briefing.evidence_trends.map((trend) => (
                    <span
                      key={trend.keyword}
                      className="rounded-md bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300"
                    >
                      {trend.keyword} ({trend.paper_count} 篇)
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="mt-4 rounded-xl bg-white/80 p-3.5 border border-slate-200/70 dark:bg-zinc-800/40 dark:border-zinc-800">
          <p className="text-xs text-slate-600 dark:text-zinc-400 leading-relaxed">
            当前科研会话为独立发起。完成知识学习后，可在学习笔记中一键将已确认背景传递至科研引导。
          </p>
          <div className="mt-2 text-xs text-slate-500 dark:text-zinc-400">
            <span>已收录文献包：<strong className="text-slate-900 dark:text-zinc-100">{briefing.reproduction_entry.bundle_count}</strong> 篇</span>
          </div>
        </div>
      )}

      {/* 为科研而学触发按钮 */}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 pt-3 border-t border-slate-100 dark:border-zinc-800">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void handleLoadRecommendations()}
            disabled={loadingRecs}
            className="app-button-secondary inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold hover:bg-slate-50 dark:hover:bg-zinc-800 transition"
          >
            {loadingRecs ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Lightbulb className="h-3.5 w-3.5 text-amber-500" />
            )}
            <span>为科研而学知识点建议</span>
            {showRecs ? <ChevronUp className="h-3.5 w-3.5 ml-0.5" /> : <ChevronDown className="h-3.5 w-3.5 ml-0.5" />}
          </button>
        </div>

        <Link
          href="/learning"
          className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 transition"
        >
          <GraduationCap className="h-3.5 w-3.5" />
          <span>返回学习闭环</span>
        </Link>
      </div>

      {/* 建议列表展开区域 */}
      {recError && (
        <p className="mt-2 text-xs text-red-600 dark:text-red-400">{recError}</p>
      )}

      {showRecs && recommendations && recommendations.length > 0 && (
        <div className="mt-3.5 space-y-2 rounded-xl bg-white p-3 border border-slate-200/80 dark:bg-zinc-900/60 dark:border-zinc-800 animate-in fade-in duration-200">
          <p className="text-xs font-bold text-slate-900 dark:text-zinc-100">
            建议掌握的前置/补充知识点：
          </p>
          <ul className="space-y-2">
            {recommendations.map((rec) => (
              <li
                key={rec.knowledge_point}
                className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 rounded-lg bg-slate-50 p-2.5 dark:bg-zinc-800/50"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-slate-900 dark:text-zinc-100">
                      {rec.knowledge_point}
                    </span>
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                        rec.mastery_status === "mastered"
                          ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300"
                          : rec.mastery_status === "weak"
                            ? "bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300"
                            : "bg-slate-100 text-slate-600 dark:bg-zinc-700 dark:text-zinc-300"
                      }`}
                    >
                      {rec.mastery_status === "mastered"
                        ? "已掌握"
                        : rec.mastery_status === "weak"
                          ? "需巩固"
                          : "未学习"}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 dark:text-zinc-400 mt-0.5">
                    {rec.reason}
                  </p>
                </div>

                <Link
                  href={`/learning?query=${encodeURIComponent(rec.knowledge_point)}`}
                  className="app-button-primary inline-flex shrink-0 items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-medium self-start sm:self-center"
                >
                  <BookOpen className="h-3 w-3" />
                  <span>去学习</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
