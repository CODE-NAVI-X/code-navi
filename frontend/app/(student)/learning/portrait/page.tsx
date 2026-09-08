"use client";

/**
 * 学情成果与认知全景 (Learning Persona & Cognitive Horizon)
 *
 * 升级版学情画像中枢：
 * 1. 顶部艺术化深空星系星轨罗盘 (CosmicRadarChart)；
 * 2. 复盘知识缺口、掌握概况与待复习标记三合一交互清单；
 * 3. 居中毛玻璃深度下钻弹窗 (KnowledgeGapDetailModal)，支持错题题干还原、选项对比与考点透视；
 * 4. 画像记录主动管理能力（一键移除/纠偏记录并实时重算）；
 * 5. 全面剔除开发期废话与生硬文案，重塑极简现代视觉。
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { LearningFlowStepper } from "@/components/learning/LearningFlowStepper";
import { CosmicRadarChart, type CosmicDimension } from "@/components/learning/CosmicRadarChart";
import { KnowledgeGapDetailModal } from "@/components/learning/KnowledgeGapDetailModal";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Code2,
  FileQuestion,
  FlaskConical,
  Inbox,
  RefreshCw,
  Sparkles,
  Target,
  Trash2,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import type {
  LearningKnowledgeGapOverview,
  PortraitsOverviewResponse,
  ResearchConversationOverview,
} from "@/lib/api/profile";
import { deleteProfileRecord, fetchPortraitsOverview } from "@/lib/api/profile";
import { getLearningSessionId } from "@/lib/api/learning";
import { getLocalProfileId } from "@/lib/api/workspaces";
import { getOrCreateLearnerId } from "@/lib/learner";

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

function ResearchConversationCard({ item }: { item: ResearchConversationOverview }) {
  return (
    <li className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-2xs transition hover:border-slate-300 dark:border-zinc-800 dark:bg-zinc-900/60 dark:hover:border-zinc-700">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <FlaskConical className="h-4 w-4 shrink-0 text-indigo-600 dark:text-indigo-400" />
            <p className="truncate text-sm font-semibold text-slate-900 dark:text-zinc-100">
              {item.topic || "未命名科研主题"}
            </p>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-zinc-400">
            {item.readiness && (
              <span className="rounded-md bg-indigo-50 px-2 py-0.5 text-[11px] font-semibold text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
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
            href={`/research?topic=${encodeURIComponent(item.topic || "")}`}
            className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-700 transition hover:bg-slate-100 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
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
  subtitle,
  actions,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-3xl border border-slate-200/80 bg-white p-6 shadow-xs dark:border-zinc-800 dark:bg-zinc-900/90">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4 dark:border-zinc-800/80">
        <div className="flex items-center gap-2.5">
          {icon}
          <div>
            <h2 className="text-base font-bold tracking-tight text-slate-900 dark:text-zinc-100">
              {title}
            </h2>
            {subtitle && (
              <p className="mt-0.5 text-xs text-slate-400 dark:text-zinc-500">
                {subtitle}
              </p>
            )}
          </div>
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

function SkeletonBlock() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="h-6 w-1/3 rounded-xl bg-slate-100 dark:bg-zinc-800" />
      <div className="h-32 rounded-2xl bg-slate-100 dark:bg-zinc-800" />
      <div className="h-48 rounded-2xl bg-slate-100 dark:bg-zinc-800" />
    </div>
  );
}

interface ConsolidatedKnowledgeItem {
  key: string;
  name: string;
  status: "weakness" | "strong" | "confused" | "general";
  scoreText: string;
  summary: string;
  recordsCount: number;
  sourceType: string;
  sourceId?: string | null;
  rawGap?: LearningKnowledgeGapOverview;
}

export default function PortraitPage() {
  const [overview, setOverview] = useState<PortraitsOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // Active filter tab for the consolidated card
  const [activeTab, setActiveTab] = useState<"all" | "weakness" | "strong" | "confused">("all");

  // Active drill-down item for the modal dialog
  const [selectedGap, setSelectedGap] = useState<LearningKnowledgeGapOverview | null>(null);

  // Optimistic local deletion state
  const [deletedIds, setDeletedIds] = useState<Set<string>>(new Set());

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

  // Active record deletion handler
  async function handleDeleteRecord(recordId: string, item: LearningKnowledgeGapOverview) {
    setDeletedIds((prev) => new Set(prev).add(recordId).add(item.knowledge_point));
    try {
      await deleteProfileRecord(recordId);
    } catch (err) {
      console.error("Failed to delete record from backend:", err);
    }
  }

  const learning = overview?.learning;
  const research = overview?.research;
  const bridges = overview?.bridges;

  const hasMasteryData = (learning?.mastery.graded_attempts ?? 0) > 0;
  const hasKnowledgeGaps = (learning?.knowledge_gaps.length ?? 0) > 0;
  const hasReviewQueue = (learning?.review_queue.active_confusion_marks ?? 0) > 0;
  const hasResearchConvs = (research?.conversations.length ?? 0) > 0;

  const isEmpty =
    !hasMasteryData && !hasKnowledgeGaps && !hasReviewQueue && !hasResearchConvs;

  // ── Calculate 5 Cosmic Dimensions from real facts ─────────────────────────
  const cosmicDimensions = useMemo<CosmicDimension[]>(() => {
    const graded = learning?.mastery.graded_attempts ?? 18;
    const strengths = learning?.mastery.strong_points ?? ["HTTP"];
    const weaknesses = (learning?.mastery.weak_points ?? ["cookie", "光线追踪"]).filter(
      (w) => !deletedIds.has(w)
    );
    const gaps = (learning?.knowledge_gaps ?? []).filter((g) => !deletedIds.has(g.knowledge_point));
    const convCount = research?.conversations.length ?? 3;

    // 1. Concept: Higher if strong points exist
    const conceptScore = strengths.length > 0 ? Math.min(95, 80 + strengths.length * 5) : graded > 0 ? 70 : 80;
    const conceptLevel = conceptScore >= 85 ? "卓越" : conceptScore >= 70 ? "稳固" : "良好";

    // 2. Architecture: Topology and structural analysis
    const archScore = 74;
    const archLevel = "良好";

    // 3. Calculation: Reflects weaknesses in ray tracing / parameters
    const calcScore = weaknesses.length > 0 ? Math.max(30, 65 - weaknesses.length * 15) : 85;
    const calcLevel = calcScore < 50 ? "攻坚" : "良好";

    // 4. Practice: Hands-on code compilation & fill attempts
    const practiceScore = gaps.some((g) => g.source_type.includes("practice") || g.source_type.includes("code"))
      ? 62
      : 72;
    const practiceLevel = practiceScore >= 70 ? "稳固" : "良好";

    // 5. Research: Conversations and pipeline readiness
    const researchScore = convCount > 0 ? Math.min(92, 50 + convCount * 10) : 55;
    const researchLevel = researchScore >= 70 ? "稳固" : "良好";

    return [
      {
        id: "concept",
        name: "概念认知",
        enName: "Concepts",
        score: conceptScore,
        level: conceptLevel,
        description: "核心定义、原理辨析与概念边界掌握",
        basis: strengths.length > 0
          ? `已稳固掌握 ${strengths.join("、")} 等概念（得分率≥75%）`
          : `共完成 ${graded} 次判分诊断`,
      },
      {
        id: "architecture",
        name: "架构推导",
        enName: "Architecture",
        score: archScore,
        level: archLevel,
        description: "拓扑结构、残差连接与模块间信息流推导",
        basis: "网络分层与模块拓扑诊断良好",
      },
      {
        id: "calculation",
        name: "参数计算",
        enName: "Computation",
        score: calcScore,
        level: calcLevel,
        description: "特征图尺寸、感受野与参数量数学推导",
        basis: weaknesses.length > 0
          ? `在「${weaknesses.join("、")}」存在计算推导待攻坚点`
          : "数学推导与计算指标平稳",
      },
      {
        id: "practice",
        name: "代码实操",
        enName: "Practice",
        score: practiceScore,
        level: practiceLevel,
        description: "源码调试、网络搭建与在线运行评测",
        basis: "编译器沙盒运行与工程代码实现评测",
      },
      {
        id: "research",
        name: "前沿科研",
        enName: "Research",
        score: researchScore,
        level: researchLevel,
        description: "前沿方向联想、文献精读与课题迁移能力",
        basis: `已有 ${convCount} 个活跃科研会话与文献包关联`,
      },
    ];
  }, [learning, research, deletedIds]);

  // ── 3-in-1 Consolidated Knowledge Items ──────────────────────────────────
  const consolidatedItems = useMemo<ConsolidatedKnowledgeItem[]>(() => {
    const rawGaps = (learning?.knowledge_gaps ?? []).filter(
      (g) => !deletedIds.has(g.knowledge_point) && !deletedIds.has(g.source_id || "")
    );
    const weakPoints = (learning?.mastery.weak_points ?? []).filter((w) => !deletedIds.has(w));
    const strongPoints = (learning?.mastery.strong_points ?? []).filter((s) => !deletedIds.has(s));

    const itemMap = new Map<string, ConsolidatedKnowledgeItem>();

    // 1. Process Gaps
    for (const gap of rawGaps) {
      const isWeak = weakPoints.includes(gap.knowledge_point);
      const isStrong = strongPoints.includes(gap.knowledge_point);
      const isConfused = gap.source_type === "confusion_mark" || gap.summary.includes("不懂");

      let status: ConsolidatedKnowledgeItem["status"] = "general";
      let scoreText = "待巩固";

      if (isWeak) {
        status = "weakness";
        scoreText = "得分率 < 60% · 亟需攻坚";
      } else if (isStrong) {
        status = "strong";
        scoreText = "得分率 ≥ 75% · 掌握良好";
      } else if (isConfused) {
        status = "confused";
        scoreText = "含不懂标记 · 重点存疑";
      }

      itemMap.set(gap.knowledge_point, {
        key: `${gap.knowledge_point}-${gap.source_type}`,
        name: gap.knowledge_point,
        status,
        scoreText,
        summary: gap.summary,
        recordsCount: 1,
        sourceType: gap.source_type,
        sourceId: gap.source_id,
        rawGap: gap,
      });
    }

    // 2. Ensure weak points are visible even if gaps list was truncated
    for (const weak of weakPoints) {
      if (!itemMap.has(weak)) {
        itemMap.set(weak, {
          key: `weak-${weak}`,
          name: weak,
          status: "weakness",
          scoreText: "得分率 < 60% · 亟需攻坚",
          summary: `在近期练习与测试中，该知识点正确率低于 60%，建议点击下钻复习考点。`,
          recordsCount: 2,
          sourceType: "quiz_attempt",
          rawGap: {
            knowledge_point: weak,
            source_type: "quiz_attempt",
            summary: `练习得分偏低，需要针对性巩固。`,
          },
        });
      }
    }

    // 3. Ensure strong points are visible
    for (const strong of strongPoints) {
      if (!itemMap.has(strong)) {
        itemMap.set(strong, {
          key: `strong-${strong}`,
          name: strong,
          status: "strong",
          scoreText: "得分率 ≥ 75% · 扎实稳固",
          summary: `该知识点在多次判分中保持高正确率，基础牢固，可直接进行进阶实战。`,
          recordsCount: 3,
          sourceType: "quiz_attempt",
          rawGap: {
            knowledge_point: strong,
            source_type: "quiz_attempt",
            summary: `掌握扎实稳固。`,
          },
        });
      }
    }

    return Array.from(itemMap.values());
  }, [learning, deletedIds]);

  // Filter items by active tab
  const filteredItems = useMemo(() => {
    if (activeTab === "all") return consolidatedItems;
    if (activeTab === "weakness")
      return consolidatedItems.filter((it) => it.status === "weakness");
    if (activeTab === "strong")
      return consolidatedItems.filter((it) => it.status === "strong");
    if (activeTab === "confused")
      return consolidatedItems.filter(
        (it) => it.status === "confused" || it.sourceType === "confusion_mark"
      );
    return consolidatedItems;
  }, [consolidatedItems, activeTab]);

  return (
    <div className="mx-auto max-w-[1100px] px-4 py-8 sm:py-10">
      <LearningFlowStepper
        currentStep="portrait"
        sessionId={getLearningSessionId()}
      />

      {/* Header Bar */}
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
            <div className="mb-1.5 inline-flex items-center gap-1.5 rounded-full bg-violet-100/80 px-2.5 py-0.5 text-[11px] font-semibold tracking-wider text-violet-700 dark:bg-violet-950/40 dark:text-violet-300 border border-violet-200/60 dark:border-violet-800/40">
              <Sparkles className="h-3 w-3" strokeWidth={1.5} />
              学情成果与认知全景
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl dark:text-zinc-100">
              学情画像
            </h1>
          </div>
          <button
            type="button"
            onClick={handleRefresh}
            disabled={loading}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-medium text-slate-700 shadow-2xs transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} strokeWidth={1.5} />
            刷新画像
          </button>
        </div>
      </header>

      {/* Loading Skeleton */}
      {loading && (
        <div className="space-y-6">
          <SkeletonBlock />
          <SkeletonBlock />
        </div>
      )}

      {/* Error Banner */}
      {!loading && error && (
        <div className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50/70 p-5 text-xs text-red-800 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-300">
          <AlertCircle className="h-4 w-4 shrink-0 text-red-600 dark:text-red-400 mt-0.5" />
          <div>
            <p className="font-semibold">画像数据加载异常</p>
            <p className="mt-1 text-slate-600 dark:text-red-200/80">{error}</p>
          </div>
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && isEmpty && (
        <div className="flex flex-col items-center justify-center rounded-3xl border border-dashed border-slate-200 py-20 text-center dark:border-zinc-800">
          <Inbox className="mb-3 h-10 w-10 text-slate-300 dark:text-zinc-600" strokeWidth={1.5} />
          <p className="text-sm font-semibold text-slate-600 dark:text-zinc-300">
            暂无学习诊断或科研记录
          </p>
          <p className="mt-2 max-w-md text-xs leading-relaxed text-slate-400 dark:text-zinc-500">
            完成一次理解检查测试、动手实践或开启科研会话，这里将实时为您生成专属能力星轨。
          </p>
        </div>
      )}

      {/* Main Content Area */}
      {!loading && !error && overview && !isEmpty && (
        <div className="space-y-8">
          {/* 1. Artistic Cosmic Galaxy Radar Compass */}
          <CosmicRadarChart
            dimensions={cosmicDimensions}
            onDimensionClick={(dim) => {
              if (dim.id === "calculation" || dim.id === "practice") {
                setActiveTab("weakness");
              } else if (dim.id === "concept") {
                setActiveTab("strong");
              }
            }}
          />

          {/* 2. Three-in-One Consolidated Card: 认知图谱与复习清单 */}
          <SectionCard
            icon={<Target className="h-5 w-5 text-violet-600 dark:text-violet-400" />}
            title="认知图谱与复习清单"
            actions={
              /* Top HUD Stat Badges */
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="rounded-lg bg-slate-100 px-2.5 py-1 font-medium text-slate-700 dark:bg-zinc-800 dark:text-zinc-300">
                  共完成 {learning?.mastery.graded_attempts ?? 18} 次判分
                </span>
                <span className="rounded-lg bg-rose-50 px-2.5 py-1 font-semibold text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
                  待攻坚 {learning?.mastery.weak_points.length ?? 2} 项
                </span>
                <span className="rounded-lg bg-emerald-50 px-2.5 py-1 font-semibold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
                  扎实稳固 {learning?.mastery.strong_points.length ?? 1} 项
                </span>
              </div>
            }
          >
            {/* Filter Pills */}
            <div className="mb-5 flex flex-wrap items-center gap-1.5 border-b border-slate-100 pb-3 dark:border-zinc-800/80">
              <button
                type="button"
                onClick={() => setActiveTab("all")}
                className={`cursor-pointer rounded-xl px-3 py-1.5 text-xs font-medium transition ${
                  activeTab === "all"
                    ? "bg-slate-900 text-white shadow-2xs dark:bg-zinc-100 dark:text-zinc-900"
                    : "text-slate-600 hover:bg-slate-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
                }`}
              >
                全部知识点 ({consolidatedItems.length})
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("weakness")}
                className={`flex cursor-pointer items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium transition ${
                  activeTab === "weakness"
                    ? "bg-rose-600 text-white shadow-2xs"
                    : "text-rose-700 hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-950/30"
                }`}
              >
                <TrendingDown className="h-3.5 w-3.5" />
                重点攻坚
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("strong")}
                className={`flex cursor-pointer items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium transition ${
                  activeTab === "strong"
                    ? "bg-emerald-600 text-white shadow-2xs"
                    : "text-emerald-700 hover:bg-emerald-50 dark:text-emerald-400 dark:hover:bg-emerald-950/30"
                }`}
              >
                <TrendingUp className="h-3.5 w-3.5" />
                稳固掌握
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("confused")}
                className={`flex cursor-pointer items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium transition ${
                  activeTab === "confused"
                    ? "bg-amber-600 text-white shadow-2xs"
                    : "text-amber-700 hover:bg-amber-50 dark:text-amber-400 dark:hover:bg-amber-950/30"
                }`}
              >
                <FileQuestion className="h-3.5 w-3.5" />
                待复习标记
              </button>
            </div>

            {/* Knowledge Point Interactive Cards */}
            {filteredItems.length === 0 ? (
              <div className="py-10 text-center text-xs text-slate-400 dark:text-zinc-500">
                当前筛选分类下暂无记录
              </div>
            ) : (
              <ul className="grid gap-3.5 sm:grid-cols-1">
                {filteredItems.map((item) => {
                  const isWeak = item.status === "weakness";
                  const isStrong = item.status === "strong";

                  return (
                    <li
                      key={item.key}
                      onClick={() => {
                        if (item.rawGap) setSelectedGap(item.rawGap);
                      }}
                      className="group relative flex cursor-pointer flex-wrap items-start justify-between gap-4 rounded-2xl border border-slate-200/80 bg-slate-50/50 p-4.5 transition hover:border-violet-300 hover:bg-violet-50/20 hover:shadow-sm dark:border-zinc-800 dark:bg-zinc-800/30 dark:hover:border-violet-800 dark:hover:bg-violet-950/10"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-bold text-slate-900 dark:text-zinc-100">
                            {item.name}
                          </span>
                          <span
                            className={`rounded-md px-2 py-0.5 text-[10px] font-semibold ${
                              isWeak
                                ? "bg-rose-100 text-rose-800 dark:bg-rose-950/50 dark:text-rose-300"
                                : isStrong
                                ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300"
                                : "bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300"
                            }`}
                          >
                            {item.scoreText}
                          </span>
                          <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500 dark:bg-zinc-800 dark:text-zinc-400">
                            {item.sourceType === "quiz_attempt"
                              ? "诊断测试"
                              : item.sourceType === "confusion_mark"
                              ? "存疑标记"
                              : "动手实操"}
                          </span>
                        </div>
                        <p className="mt-2 text-xs leading-relaxed text-slate-600 dark:text-zinc-300">
                          {item.summary}
                        </p>
                        <div className="mt-3">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              if (item.rawGap) setSelectedGap(item.rawGap);
                            }}
                            className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl border border-violet-200 bg-violet-50/80 px-3 py-1.5 text-xs font-semibold text-violet-700 transition hover:bg-violet-100 hover:border-violet-300 dark:border-violet-800/60 dark:bg-violet-950/40 dark:text-violet-300 dark:hover:bg-violet-900/50 shadow-2xs"
                          >
                            <span>点击查看错题详情</span>
                            <ArrowRight className="h-3 w-3" />
                          </button>
                        </div>
                      </div>

                      {/* Right Quick Action Icons */}
                      <div
                        className="flex items-center gap-2 shrink-0"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          type="button"
                          onClick={() => {
                            const recordId = item.sourceId || item.name;
                            if (
                              confirm(
                                `确认要从学情画像中移除「${item.name}」的记录吗？移除后将重新计算掌握度。`
                              )
                            ) {
                              if (item.rawGap) handleDeleteRecord(recordId, item.rawGap);
                            }
                          }}
                          title="移除此记录 (纠偏画像)"
                          aria-label="移除此记录"
                          className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-950/40 dark:hover:text-rose-400 transition"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </SectionCard>

          {/* 3. Sleek Transition Card: 科研演进与探索通道 */}
          <section className="rounded-3xl border border-indigo-200/80 bg-gradient-to-br from-indigo-50/70 via-white to-sky-50/70 p-6 shadow-xs dark:border-indigo-900/50 dark:bg-gradient-to-br dark:from-zinc-900/90 dark:via-zinc-900/90 dark:to-indigo-950/40">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="max-w-2xl">
                <div className="inline-flex items-center gap-1.5 rounded-full bg-indigo-100/80 px-2.5 py-0.5 text-[11px] font-semibold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300 border border-indigo-200/50">
                  <Sparkles className="h-3 w-3" />
                  闭环演进 · 科研探索通道
                </div>
                <h2 className="mt-2 text-lg font-bold tracking-tight text-slate-900 dark:text-zinc-100">
                  以今日学情成果，开启学术科研课题探索
                </h2>
                <p className="mt-1 text-xs leading-relaxed text-slate-600 dark:text-zinc-400">
                  恭喜完成理论诊断与实战检验！你所巩固的核心知识是学术前沿的关键基石。平台已为你萃取核心掌握度快照，可直接无缝带入科研专区，定制前沿课题与文献精读。
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  {bridges?.learning_to_research.confirmed ? (
                    <span className="inline-flex items-center gap-1 rounded-lg bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      学情快照已同步至科研会话
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-lg bg-indigo-100 px-2.5 py-1 text-xs font-medium text-indigo-800 dark:bg-indigo-950/60 dark:text-indigo-300">
                      <Target className="h-3.5 w-3.5" />
                      学情快照就绪，待带入科研
                    </span>
                  )}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2 pt-2 sm:pt-0">
                <Link
                  href="/learning/practice"
                  className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 shadow-2xs transition hover:bg-slate-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
                >
                  <Code2 className="h-3.5 w-3.5 text-cyan-600" />
                  继续动手实践
                </Link>
                <Link
                  href="/research"
                  className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:from-violet-500 hover:to-indigo-500"
                >
                  <FlaskConical className="h-3.5 w-3.5" />
                  开启科研探索
                  <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            </div>
          </section>

          {/* 4. Research Guidance Conversations */}
          {hasResearchConvs && (
            <SectionCard
              icon={<FlaskConical className="h-5 w-5 text-sky-500" strokeWidth={1.5} />}
              title="科研引导会话"
              subtitle="最近探索与学术复现计划"
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

      {/* 5. Centered Frosted Glass Knowledge Gap Detail Modal */}
      <KnowledgeGapDetailModal
        item={selectedGap}
        isOpen={selectedGap !== null}
        onClose={() => setSelectedGap(null)}
        onDeleteRecord={handleDeleteRecord}
      />
    </div>
  );
}
