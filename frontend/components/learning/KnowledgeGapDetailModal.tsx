"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Code2,
  Compass,
  FlaskConical,
  Sparkles,
  Target,
  Trash2,
  X,
} from "lucide-react";
import type { LearningKnowledgeGapOverview } from "@/lib/api/profile";

interface KnowledgeGapDetailModalProps {
  item: LearningKnowledgeGapOverview | null;
  isOpen: boolean;
  onClose: () => void;
  onDeleteRecord?: (recordId: string, item: LearningKnowledgeGapOverview) => Promise<void> | void;
}

function formatSourceType(sourceType: string): string {
  switch (sourceType) {
    case "quiz_attempt":
      return "随堂理解检查判分 (Quiz Attempt)";
    case "confusion_mark":
      return "自主标记不懂 (Confusion Mark)";
    case "practice_outcome":
      return "沙盒代码实操评测 (Practice Outcome)";
    case "code_fill_attempt":
      return "代码填空实操评测 (Code Fill Attempt)";
    default:
      return sourceType || "诊断记录";
  }
}

export function KnowledgeGapDetailModal({
  item,
  isOpen,
  onClose,
  onDeleteRecord,
}: KnowledgeGapDetailModalProps) {
  const router = useRouter();
  const [isDeleting, setIsDeleting] = useState(false);

  // Close on Escape key
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !item) return null;

  async function handleDelete() {
    if (!item) return;
    const recordId = item.source_id || item.knowledge_point;
    if (
      confirm(
        `确认要从学情画像中移除「${item.knowledge_point}」的这条历史薄弱记录吗？移除后系统将重新聚合您的最新掌握度。`
      )
    ) {
      setIsDeleting(true);
      try {
        await onDeleteRecord?.(recordId, item);
        onClose();
      } finally {
        setIsDeleting(false);
      }
    }
  }

  // Handle Jump & Auto-inject prompt for reviewing this specific weak point
  function handleReviewWeakPoint() {
    if (!item) return;
    const targetPrompt = `针对薄弱知识点「${item.knowledge_point}」开展专项巩固复习。学情事实依据：${item.summary}。请围绕此单一知识点进行针对性出题。`;
    onClose();
    router.push(
      `/learning?mode=quiz&knowledgePoint=${encodeURIComponent(item.knowledge_point)}&targetProfile=${encodeURIComponent(targetPrompt)}&autoStart=1`
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-950/70 backdrop-blur-md animate-in fade-in duration-200"
    >
      {/* Click outside backdrop to close */}
      <div className="absolute inset-0" onClick={onClose} />

      {/* Main Glassmorphic Modal Window */}
      <div className="relative z-10 flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-3xl border border-slate-200/80 bg-white/95 shadow-2xl backdrop-blur-xl dark:border-zinc-800 dark:bg-zinc-900/95">
        {/* Top Header Bar */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4 dark:border-zinc-800">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-violet-100 text-violet-700 dark:bg-violet-950/50 dark:text-violet-300">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <h2 id="modal-title" className="text-base font-bold text-slate-900 dark:text-zinc-100">
                {item.knowledge_point} · 薄弱待巩固
              </h2>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭弹窗"
            className="rounded-xl p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-200 transition cursor-pointer"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Scrollable Modal Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {/* Summary Banner */}
          <div className="rounded-2xl border border-rose-200/70 bg-rose-50/50 p-4 dark:border-rose-900/30 dark:bg-rose-950/20">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-4 w-4 text-rose-600 dark:text-rose-400 shrink-0 mt-0.5" />
              <div className="min-w-0 flex-1 space-y-1.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-bold text-rose-900 dark:text-rose-200">
                    诊断事实与依据
                  </span>
                  <span className="rounded-full bg-rose-200/60 px-2 py-0.5 text-[11px] font-medium text-rose-800 dark:bg-rose-900/50 dark:text-rose-300">
                    {formatSourceType(item.source_type)}
                  </span>
                  {item.source_id && (
                    <span className="text-[10px] text-rose-600/70 dark:text-rose-400/60">
                      ID: {item.source_id.slice(0, 8)}...
                    </span>
                  )}
                </div>
                <p className="text-xs font-medium text-rose-800 dark:text-rose-300 leading-relaxed">
                  {item.summary}
                </p>
              </div>
            </div>
          </div>

          {/* Authentic Fact Perspective & Learning Status */}
          <div className="rounded-2xl border border-slate-200/80 bg-slate-50/70 p-4 dark:border-zinc-800 dark:bg-zinc-800/40 space-y-3">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-800 dark:text-zinc-200 border-b border-slate-200/60 dark:border-zinc-700/60 pb-2">
              <BookOpen className="h-4 w-4 text-indigo-500" />
              <span>考点透视与学情分析</span>
            </div>
            <div className="text-xs text-slate-600 dark:text-zinc-300 leading-relaxed space-y-2">
              <p>
                考点「<strong className="text-slate-900 dark:text-zinc-100">{item.knowledge_point}</strong>」在近期学习与评测中产生了薄弱信号。系统学情画像已将该知识点纳入定向突破队列，后续出题组卷将针对性强化其概念辨析与实操考察。
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1 text-[11px]">
                <div className="rounded-xl border border-slate-200/60 bg-white p-2.5 dark:border-zinc-700/60 dark:bg-zinc-900/60">
                  <span className="font-semibold text-slate-700 dark:text-zinc-300 block mb-0.5">
                    考点归属
                  </span>
                  <span className="text-slate-500 dark:text-zinc-400">{item.knowledge_point}</span>
                </div>
                <div className="rounded-xl border border-slate-200/60 bg-white p-2.5 dark:border-zinc-700/60 dark:bg-zinc-900/60">
                  <span className="font-semibold text-slate-700 dark:text-zinc-300 block mb-0.5">
                    诊断来源
                  </span>
                  <span className="text-slate-500 dark:text-zinc-400">{formatSourceType(item.source_type)}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Action Pathways Guidance */}
          <div className="rounded-2xl border border-violet-200/70 bg-violet-50/40 p-4 dark:border-violet-900/30 dark:bg-violet-950/20 space-y-2.5">
            <div className="flex items-center gap-1.5 text-xs font-bold text-violet-800 dark:text-violet-300">
              <Compass className="h-4 w-4 text-violet-600 dark:text-violet-400" />
              专项突破路径指引
            </div>
            <ul className="text-xs leading-relaxed text-slate-600 dark:text-zinc-300 space-y-1.5 list-disc list-inside">
              <li>
                <strong className="text-violet-700 dark:text-violet-300">复习薄弱知识点</strong>：点击下方专属复习按钮，将仅注入本考点的诊断事实，由 AI 生成针对性测验进行单点查漏补缺；
              </li>
              <li>
                <strong className="text-cyan-700 dark:text-cyan-300">动手实践</strong>：前往编译器沙盒，围绕「{item.knowledge_point}」编写与调试代码；
              </li>
              <li>
                <strong className="text-indigo-700 dark:text-indigo-300">带入科研</strong>：将该考点引入前沿科研研讨，探索其学术前沿与工程落地。
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom Action Footer */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 bg-slate-50/80 px-6 py-4 dark:border-zinc-800 dark:bg-zinc-900/80">
          {/* Active Record Management (Delete / Reset) */}
          <button
            type="button"
            onClick={handleDelete}
            disabled={isDeleting}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-600 transition hover:bg-red-50 dark:border-red-900/50 dark:bg-zinc-800 dark:text-red-400 dark:hover:bg-red-950/30 disabled:opacity-50"
          >
            <Trash2 className="h-3.5 w-3.5" />
            {isDeleting ? "正在移除..." : "移除此记录 (纠偏画像)"}
          </button>

          {/* Action Pathways: [复习薄弱知识点] on the left of 动手实践 and 带入科研 */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleReviewWeakPoint}
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:from-violet-500 hover:to-indigo-500 cursor-pointer"
            >
              <Target className="h-3.5 w-3.5" />
              复习薄弱知识点
            </button>
            <Link
              href={`/learning/practice?knowledgePoint=${encodeURIComponent(item.knowledge_point)}`}
              onClick={onClose}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs transition hover:bg-slate-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
            >
              <Code2 className="h-3.5 w-3.5 text-cyan-600" />
              动手实践
            </Link>
            <Link
              href={`/research?topic=${encodeURIComponent(item.knowledge_point)}`}
              onClick={onClose}
              className="inline-flex items-center gap-1.5 rounded-xl border border-violet-200 bg-violet-50/80 px-3.5 py-1.5 text-xs font-semibold text-violet-700 shadow-2xs transition hover:bg-violet-100 dark:border-violet-800/50 dark:bg-violet-950/40 dark:text-violet-300"
            >
              <FlaskConical className="h-3.5 w-3.5" />
              带入科研
              <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
