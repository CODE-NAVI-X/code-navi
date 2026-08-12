"use client";

import { useCallback } from "react";
import { useRouter } from "next/navigation";
import { setFlowPayload } from "@/lib/store/flow-store";
import { getLearningSessionId } from "@/lib/api/learning";
import { BookOpenCheck, Microscope, Target, Terminal } from "lucide-react";

interface DownstreamGoCardProps {
  knowledgePoint: string;
  knowledgePointId?: string;
  sessionId?: string;
  onOpenResearch: () => void;
}

export function DownstreamGoCard({
  knowledgePoint,
  knowledgePointId = "kp_dhcp_4stage",
  sessionId = "",
  onOpenResearch,
}: DownstreamGoCardProps) {
  const router = useRouter();

  const handleGoToPractice = useCallback(() => {
    // Resolved on click, so an unmounted-yet parent never forwards an empty id.
    const effectiveSessionId = sessionId || getLearningSessionId();
    setFlowPayload({
      sessionId: effectiveSessionId,
      masteredKnowledgePoint: {
        id: knowledgePointId,
        name: knowledgePoint,
      },
      studentPersona: "software_coursework",
      targetModule: "practice",
      payloadData: {
        exerciseIds: ["ex_practice_01", "ex_practice_02"],
      },
    });
    router.push(
      `/practice?knowledge_id=${encodeURIComponent(knowledgePointId)}&knowledge_name=${encodeURIComponent(knowledgePoint)}&session_id=${encodeURIComponent(effectiveSessionId)}`
    );
  }, [knowledgePoint, knowledgePointId, sessionId, router]);

  return (
    <section className="mt-5 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/95">
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
          className="flex cursor-pointer items-center justify-center gap-1.5 rounded-xl bg-slate-900 px-3 py-2 text-xs font-medium text-white shadow-2xs transition hover:bg-slate-800 active:scale-98 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          <Terminal className="h-3.5 w-3.5" strokeWidth={1.5} />
          继续练习
        </button>
        <button
          type="button"
          onClick={onOpenResearch}
          className="flex cursor-pointer items-center justify-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 transition hover:bg-slate-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
        >
          <Microscope className="h-3.5 w-3.5" strokeWidth={1.5} />
          从已保存摘要继续研究
        </button>
      </div>
    </section>
  );
}

