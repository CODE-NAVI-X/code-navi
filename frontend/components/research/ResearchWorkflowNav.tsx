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
  prepare_search: 3,
};

const PRIMARY_STEPS: Array<{ anchorId: string; label: string }> = [
  { anchorId: "research-section-chat", label: "总结已学习知识" },
  { anchorId: "research-section-search", label: "了解热门研究方向" },
  { anchorId: "research-section-search", label: "选择感兴趣的方向" },
  { anchorId: "research-section-search", label: "检索并保存相关论文" },
  { anchorId: "research-section-analysis", label: "选择论文并按章节分析" },
  { anchorId: "research-section-analysis", label: "检查用户理解程度" },
  { anchorId: "research-section-reproduction", label: "生成复现方案并记录实验" },
  { anchorId: "research-section-evidence", label: "汇总证据边界与后续任务" },
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
  if (stage < 3) return { missing: "请确认感兴趣的方向与检索范围。", next: "查看并选择一个方向。" };
  if (stage === 3) return { missing: "请确认检索词与允许来源。", next: "主动启动受限检索。" };
  if (stage < 6) return { missing: "请从已保存结果中选择论文并核对摘要边界。", next: "生成论文分析。" };
  if (stage === 6) return { missing: "请核对待验证的复现条件。", next: "生成并核对复现方案。" };
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
  selectedPaperTitle,
}: {
  conversation: ResearchConversationResponse;
  currentStage?: number;
  selectedPaperTitle?: string | null;
}) {
  const steps = deriveWorkflowSteps(conversation, currentStage);
  const stage = steps.findIndex((step) => step.current);
  const details = stageDetails(conversation, stage);

  return (
    <nav aria-label="科研八步主流程" className="app-card mb-6 rounded-2xl px-5 py-5 sm:px-7">
      <div className="grid gap-3 text-sm leading-6 text-slate-700 dark:text-zinc-300 lg:grid-cols-2">
        <p><span className="font-semibold text-slate-950 dark:text-zinc-100">当前阶段：</span>{steps[stage]?.label}</p>
        <p><span className="font-semibold text-slate-950 dark:text-zinc-100">当前研究主题：</span>{conversation.profile.topic ?? "尚未确认"}</p>
        <p><span className="font-semibold text-slate-950 dark:text-zinc-100">当前选择论文：</span>{selectedPaperTitle ?? "尚未选择"}</p>
        <p><span className="font-semibold text-slate-950 dark:text-zinc-100">当前缺失信息：</span>{details.missing}</p>
        <p className="lg:col-span-2"><span className="font-semibold text-slate-950 dark:text-zinc-100">唯一下一步：</span>{details.next}</p>
      </div>
      <ol className="mt-5 flex snap-x snap-mandatory gap-2 overflow-x-auto pb-1 whitespace-nowrap [scrollbar-width:thin]">
        {steps.map((step, index) => (
          <li key={`${step.label}-${index}`} className="min-w-max snap-start">
            <a
              href={`#${step.anchorId}`}
              onClick={(event) => jumpToStep(event, step.anchorId)}
              className="app-button-secondary inline-flex min-h-10 shrink-0 items-center gap-2 rounded-full px-3 py-2 text-sm transition hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 dark:hover:bg-zinc-800"
            >
              <ListChecks className="h-4 w-4" />
              <span className="font-semibold">{index + 1}. {step.label}</span>
              {step.current && <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-bold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">当前</span>}
              {step.completed && <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-bold text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300">摘要</span>}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
