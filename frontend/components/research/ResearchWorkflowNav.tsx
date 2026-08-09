"use client";

import { ListChecks } from "lucide-react";
import type { MouseEvent } from "react";

import type { RecommendedAction, ResearchConversationResponse } from "@/lib/api/research";

interface WorkflowStep {
  id: string;
  label: string;
  available: boolean;
  hasContent: boolean;
  current: boolean;
}

const CURRENT_ANCHOR_BY_ACTION: Record<RecommendedAction, string> = {
  continue_dialogue: "research-section-chat",
  review_profile: "research-section-profile",
  prepare_search: "research-section-search",
};

/**
 * Derives display-only workflow steps from the already-loaded conversation
 * response. This component never triggers requests, retrieval, or persistence.
 */
function deriveWorkflowSteps(conversation: ResearchConversationResponse): WorkflowStep[] {
  const hasPlan = Boolean(conversation.research_plan);
  const hasDesign = Boolean(conversation.experiment_design);
  const searchAvailable = hasPlan || conversation.next_skill === "academic-search";
  const currentAnchor = CURRENT_ANCHOR_BY_ACTION[conversation.recommended_action];
  const steps: Array<Omit<WorkflowStep, "current">> = [
    { id: "research-section-chat", label: "科研对话", available: true, hasContent: conversation.messages.length > 1 },
    { id: "research-section-profile", label: "画像与准备度", available: true, hasContent: Boolean(conversation.profile.topic) },
    { id: "research-section-plan", label: "规则研究计划", available: hasPlan, hasContent: hasPlan },
    { id: "research-section-search", label: "受限学术检索", available: searchAvailable, hasContent: false },
    { id: "research-section-difficulty", label: "方向难点分析", available: true, hasContent: conversation.topic_difficulty_analysis.items.length > 0 },
    { id: "research-section-experiment", label: "实验方案", available: hasDesign, hasContent: hasDesign },
    { id: "research-section-evidence", label: "实验证据包", available: hasPlan, hasContent: false },
    { id: "research-section-paper", label: "论文辅助", available: hasPlan, hasContent: false },
    { id: "research-section-mindmap", label: "研究思维导图", available: true, hasContent: conversation.research_mindmap.nodes.length > 0 },
  ];
  return steps.map((step) => ({ ...step, current: step.available && step.id === currentAnchor }));
}

/**
 * Display-only navigation: expands the target PanelSection when it is a
 * collapsible details element, then scrolls to it. No requests, no retrieval,
 * no persistence - this only adjusts local presentation state.
 */
function jumpToStep(event: MouseEvent<HTMLAnchorElement>, stepId: string) {
  const target = document.getElementById(stepId);
  if (!target) return;
  event.preventDefault();
  if (target instanceof HTMLDetailsElement) {
    target.open = true;
  }
  target.scrollIntoView({ behavior: "smooth", block: "start" });
}

export function ResearchWorkflowNav({ conversation }: { conversation: ResearchConversationResponse }) {
  const steps = deriveWorkflowSteps(conversation);
  return (
    <nav
      aria-label="科研流程步骤导航"
      className="mb-4 rounded-2xl border border-slate-200/80 bg-white/90 px-3 py-3 shadow-sm sm:px-4 dark:border-zinc-800 dark:bg-zinc-900/90"
    >
      <p className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-600 dark:text-zinc-400">
        <ListChecks className="h-3.5 w-3.5 shrink-0" />
        科研流程导航 · 仅根据已保存的会话数据展示，点击跳转到对应面板；不会触发检索或任何自动操作。
      </p>
      <ol className="mt-2 flex gap-2 overflow-x-auto pb-1 lg:flex-wrap lg:overflow-visible lg:pb-0">
        {steps.map((step, index) => {
          const content = (
            <>
              <span className="font-semibold">
                {index + 1}. {step.label}
              </span>
              {step.current && (
                <span className="rounded-full bg-indigo-100 px-1.5 py-0.5 text-[9px] font-bold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
                  当前建议
                </span>
              )}
              {step.hasContent && (
                <span className="rounded-full bg-emerald-100 px-1.5 py-0.5 text-[9px] font-bold text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300">
                  已有内容
                </span>
              )}
              {!step.available && (
                <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[9px] font-medium text-slate-500 dark:bg-zinc-800 dark:text-zinc-500">
                  未生成
                </span>
              )}
            </>
          );
          const className = step.available
            ? "inline-flex shrink-0 items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] text-slate-700 transition hover:border-indigo-300 hover:bg-indigo-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:border-indigo-800 dark:hover:bg-indigo-950/30"
            : "inline-flex shrink-0 cursor-not-allowed items-center gap-1.5 rounded-full border border-dashed border-slate-200 px-2.5 py-1.5 text-[11px] text-slate-400 dark:border-zinc-800 dark:text-zinc-600";
          return (
            <li key={step.id}>
              {step.available ? (
                <a
                  href={`#${step.id}`}
                  className={className}
                  onClick={(event) => jumpToStep(event, step.id)}
                >
                  {content}
                </a>
              ) : (
                <span className={className} aria-disabled="true">
                  {content}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}