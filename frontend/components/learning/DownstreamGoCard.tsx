"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { getLearningSessionId } from "@/lib/api/learning";
import {
  navigateToPractice,
  navigateToResearch,
} from "@/lib/learning-context";
import { Target, Terminal, GraduationCap, Loader2, X } from "lucide-react";

interface DownstreamGoCardProps {
  knowledgePoint: string;
  knowledgePointId?: string;
  sessionId?: string;
  /** Id of the archived summary backing this card, used for research transfer. */
  notebookItemId?: string;
  onDismiss?: () => void;
}

export function DownstreamGoCard({
  knowledgePoint,
  knowledgePointId = "kp_dhcp_4stage",
  sessionId = "",
  notebookItemId,
  onDismiss,
}: DownstreamGoCardProps) {
  const router = useRouter();
  const [researching, setResearching] = useState(false);
  const [researchError, setResearchError] = useState<string | null>(null);

  const handleGoToPractice = useCallback(() => {
    // Resolved on click, so an unmounted-yet parent never forwards an empty id.
    const effectiveSessionId = sessionId || getLearningSessionId();
    navigateToPractice(router, {
      knowledgePoint,
      knowledgePointId,
      sessionId: effectiveSessionId,
      exerciseIds: ["ex_practice_01", "ex_practice_02"],
    });
  }, [knowledgePoint, knowledgePointId, sessionId, router]);

  const handleGoToResearch = useCallback(async () => {
    const effectiveSessionId = sessionId || getLearningSessionId();
    if (!notebookItemId) {
      setResearchError("当前学习摘要尚未归档，无法发起科研会话。");
      return;
    }
    setResearching(true);
    setResearchError(null);
    try {
      await navigateToResearch(router, {
        notebookItemId,
        sessionId: effectiveSessionId,
      });
    } catch (err) {
      setResearchError(
        err instanceof Error ? err.message : "发起科研会话失败，请重试。",
      );
      setResearching(false);
    }
  }, [notebookItemId, sessionId, router]);

  return (
    <div className="fixed bottom-6 right-6 z-50 w-84 rounded-2xl border border-slate-200/80 bg-white/95 p-4.5 shadow-2xl backdrop-blur-md dark:border-zinc-800 dark:bg-zinc-900/95 animate-in slide-in-from-bottom-5 duration-300">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-slate-100 text-slate-700 dark:bg-zinc-800 dark:text-zinc-300">
            <Target className="h-3.5 w-3.5" strokeWidth={1.5} />
          </div>
          <h4 className="text-xs font-bold tracking-tight text-slate-900 dark:text-zinc-100">
            教学节点闭环接力
          </h4>
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            aria-label="关闭"
            className="flex h-6 w-6 cursor-pointer items-center justify-center rounded text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200 transition-colors"
          >
            <X className="h-3.5 w-3.5" strokeWidth={1.5} />
          </button>
        )}
      </div>

      <p className="mb-3.5 text-xs leading-relaxed text-slate-600 dark:text-zinc-400">
        已掌握知识点：<span className="font-semibold text-slate-900 dark:text-zinc-100">{knowledgePoint}</span>
      </p>

      <div className="grid grid-cols-1 gap-2">
        <button
          onClick={handleGoToPractice}
          disabled={researching}
          className="flex cursor-pointer items-center justify-center gap-1.5 rounded-xl bg-slate-900 px-3 py-2 text-xs font-medium text-white shadow-2xs transition hover:bg-slate-800 active:scale-98 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          <Terminal className="h-3.5 w-3.5" strokeWidth={1.5} />
          软件工程实践
        </button>
        <button
          onClick={() => void handleGoToResearch()}
          disabled={researching}
          className="flex cursor-pointer items-center justify-center gap-1.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-3 py-2 text-xs font-medium text-white shadow-2xs transition hover:from-indigo-500 hover:to-violet-500 active:scale-98 disabled:cursor-not-allowed disabled:opacity-50 dark:from-indigo-500 dark:to-violet-500"
        >
          {researching ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />
          ) : (
            <GraduationCap className="h-3.5 w-3.5" strokeWidth={1.5} />
          )}
          {researching ? "正在创建科研会话…" : "学术科研路线"}
        </button>
      </div>

      {researchError && (
        <p className="mt-2 text-[11px] leading-relaxed text-rose-600 dark:text-rose-400">
          {researchError}
        </p>
      )}
    </div>
  );
}
