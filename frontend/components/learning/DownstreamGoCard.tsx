"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { setFlowPayload } from "@/lib/store/flow-store";
import { Target, Terminal, GraduationCap, X } from "lucide-react";

interface DownstreamGoCardProps {
  knowledgePoint: string;
  knowledgePointId?: string;
  sessionId?: string;
  onDismiss?: () => void;
}

export function DownstreamGoCard({
  knowledgePoint,
  knowledgePointId = "kp_dhcp_4stage",
  sessionId = "sess_demo_123",
  onDismiss,
}: DownstreamGoCardProps) {
  const router = useRouter();

  const handleGoToPractice = useCallback(() => {
    setFlowPayload({
      sessionId,
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
      `/student/practice?knowledge_id=${encodeURIComponent(knowledgePointId)}&session_id=${encodeURIComponent(sessionId)}`
    );
  }, [knowledgePoint, knowledgePointId, sessionId, router]);

  const handleGoToResearch = useCallback(() => {
    setFlowPayload({
      sessionId,
      masteredKnowledgePoint: {
        id: knowledgePointId,
        name: knowledgePoint,
      },
      studentPersona: "academic",
      targetModule: "research",
      payloadData: {
        recommendedTopic: `${knowledgePoint} 深度算法架构优化研究`,
      },
    });
    router.push(
      `/student/research?knowledge_id=${encodeURIComponent(knowledgePointId)}&session_id=${encodeURIComponent(sessionId)}`
    );
  }, [knowledgePoint, knowledgePointId, sessionId, setFlowPayload, router]);

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

      <div className="grid grid-cols-2 gap-2">
        <button
          onClick={handleGoToPractice}
          className="flex cursor-pointer items-center justify-center gap-1.5 rounded-xl bg-slate-900 px-3 py-2 text-xs font-medium text-white shadow-2xs transition hover:bg-slate-800 active:scale-98 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          <Terminal className="h-3.5 w-3.5" strokeWidth={1.5} />
          软件工程实践
        </button>
        <button
          onClick={handleGoToResearch}
          className="flex cursor-pointer items-center justify-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-800 shadow-2xs transition hover:bg-slate-50 active:scale-98 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
        >
          <GraduationCap className="h-3.5 w-3.5 text-slate-600 dark:text-zinc-400" strokeWidth={1.5} />
          学术科研路线
        </button>
      </div>
    </div>
  );
}

