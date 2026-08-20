"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { getLearningSessionId } from "@/lib/api/learning";
import {
  navigateToPractice,
  navigateToResearch,
} from "@/lib/learning-context";
import {
  BookOpenCheck,
  GraduationCap,
  Loader2,
  Microscope,
  Target,
  Terminal,
} from "lucide-react";

interface DownstreamGoCardProps {
  knowledgePoint: string;
  knowledgePointId?: string;
  sessionId?: string;
  /** Id of the archived summary backing this card, used for research transfer. */
  notebookItemId?: string;
  onOpenResearch?: () => void;
}

export function DownstreamGoCard({
  knowledgePoint,
  knowledgePointId = "kp_dhcp_4stage",
  sessionId = "",
  notebookItemId,
  onOpenResearch,
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
    <section className="app-card mt-5 rounded-2xl p-5">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-slate-100 text-slate-700 dark:bg-zinc-800 dark:text-zinc-300">
            <Target className="h-3.5 w-3.5" strokeWidth={1.5} />
          </div>
          <h4 className="text-xs font-bold tracking-tight text-slate-900 dark:text-zinc-100">
            教学节点闭环接力
          </h4>
        </div>
        <BookOpenCheck className="h-4 w-4 text-slate-400" />
      </div>

      <p className="mb-3.5 text-xs leading-relaxed text-slate-600 dark:text-zinc-400">
        当前主题：<span className="font-semibold text-slate-900 dark:text-zinc-100">{knowledgePoint}</span>。你可以自由选择下一步，模块之间不强制顺序。
      </p>

      <div className="flex flex-wrap gap-2">
        <button
          onClick={handleGoToPractice}
          disabled={researching}
            className="app-button-primary flex cursor-pointer items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-xs font-medium transition hover:bg-slate-800 active:scale-98 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-zinc-200"
        >
          <Terminal className="h-3.5 w-3.5" strokeWidth={1.5} />
          继续练习
        </button>
        {onOpenResearch && (
          <button
            type="button"
            onClick={onOpenResearch}
            disabled={researching}
            className="app-button-secondary flex cursor-pointer items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-xs font-medium transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-zinc-800"
          >
            <Microscope className="h-3.5 w-3.5" strokeWidth={1.5} />
            查看已保存摘要
          </button>
        )}
        <button
          onClick={() => void handleGoToResearch()}
          disabled={researching}
          className="app-button-secondary flex cursor-pointer items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-xs font-medium transition hover:bg-slate-50 active:scale-98 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-zinc-800"
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
        <p role="alert" className="mt-2 text-[11px] leading-relaxed text-rose-600 dark:text-rose-400">
          {researchError}
        </p>
      )}
    </section>
  );
}
