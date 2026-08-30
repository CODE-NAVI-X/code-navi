"use client";

import { ListChecks } from "lucide-react";
import type { MouseEvent } from "react";

import type { RecommendedAction, ResearchConversationResponse } from "@/lib/api/research";

interface WorkflowStep {
  anchorId: string;
  label: string;
  current: boolean;
  completed: boolean;
}

const DEFAULT_STAGE_BY_ACTION: Record<RecommendedAction, number> = {
  continue_dialogue: 0,
  review_profile: 0,
  prepare_search: 1,
};

const PRIMARY_STEPS: Array<{ anchorId: string; label: string }> = [
  { anchorId: "research-section-chat", label: "研究需求" },
  { anchorId: "research-section-search", label: "检索计划" },
  { anchorId: "research-section-search", label: "保存原始论文" },
  { anchorId: "research-section-reproduction", label: "复现方案" },
  { anchorId: "research-section-reproduction-evaluation", label: "证据边界与下一步任务" },
];

function deriveWorkflowSteps(
  conversation: ResearchConversationResponse,
  requestedStage?: number,
): WorkflowStep[] {
  const stage = Math.min(
    Math.max(requestedStage ?? DEFAULT_STAGE_BY_ACTION[conversation.recommended_action], 0),
    PRIMARY_STEPS.length - 1,
  );
  return PRIMARY_STEPS.map((step, index) => ({
    ...step,
    current: index === stage,
    completed: index < stage,
  }));
}

function stageDetails(conversation: ResearchConversationResponse, stage: number) {
  if (stage === 0) {
    return {
      missing: conversation.readiness.reasons[0] ?? "请补齐科研画像中的关键信息。",
      next: "补充或确认研究需求。",
    };
  }
  if (stage === 1) return { missing: "请确认检索词与允许来源。", next: "主动启动受限检索。" };
  if (stage === 2) return { missing: "请从已保存结果中选择原始论文。", next: "保存并选择一篇原始论文。" };
  if (stage === 3) return { missing: "请核对待验证的复现条件。", next: "生成并核对复现方案。" };
  return { missing: "请补充实验记录或待核验证据。", next: "主动运行证据完整度评估。" };
}

function jumpToStep(event: MouseEvent<HTMLAnchorElement>, anchorId: string) {
  const target = document.getElementById(anchorId);
  if (!target) return;
  event.preventDefault();
  if (target instanceof HTMLDetailsElement) target.open = true;
  target.scrollIntoView({ behavior: "smooth", block: "start" });
}

export function ResearchWorkflowNav({
  conversation,
  currentStage,
}: {
  conversation: ResearchConversationResponse;
  currentStage?: number;
}) {
  const steps = deriveWorkflowSteps(conversation, currentStage);
  const stage = steps.findIndex((step) => step.current);
  const details = stageDetails(conversation, stage);

  return (
    <nav aria-label="科研五步主流程" className="app-card mb-2 rounded-xl px-3 py-2">
      <div className="grid gap-1 text-[11px] text-slate-600 dark:text-zinc-400 sm:grid-cols-3 sm:gap-3">
        <p><span className="font-semibold">当前阶段：</span>{steps[stage]?.label}</p>
        <p><span className="font-semibold">当前缺失信息：</span>{details.missing}</p>
        <p><span className="font-semibold">唯一下一步：</span>{details.next}</p>
      </div>
      <ol className="mt-2 flex snap-x snap-mandatory gap-2 overflow-x-auto pb-1 whitespace-nowrap [scrollbar-width:thin]">
        {steps.map((step, index) => (
          <li key={`${step.label}-${index}`} className="min-w-max snap-start">
            <a
              href={`#${step.anchorId}`}
              onClick={(event) => jumpToStep(event, step.anchorId)}
              className="app-button-secondary inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1.5 text-[11px] transition hover:bg-slate-50 dark:hover:bg-zinc-800"
            >
              <ListChecks className="h-3.5 w-3.5" />
              <span className="font-semibold">{index + 1}. {step.label}</span>
              {step.current && <span className="rounded-full bg-indigo-100 px-1.5 py-0.5 text-[9px] font-bold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">当前</span>}
              {step.completed && <span className="rounded-full bg-emerald-100 px-1.5 py-0.5 text-[9px] font-bold text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300">摘要</span>}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
