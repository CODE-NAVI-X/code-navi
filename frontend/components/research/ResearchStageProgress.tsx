"use client";

import { Check, Compass, FileCode2, FlaskConical, LineChart } from "lucide-react";
import type { OrchestratorStage } from "@/lib/api/research";

interface ResearchStageProgressProps {
  currentStage: OrchestratorStage;
  completedStages: OrchestratorStage[];
}

interface StageConfig {
  key: OrchestratorStage;
  label: string;
  stepNumber: string;
  icon: typeof Compass;
  description: string;
}

const STAGES: StageConfig[] = [
  {
    key: "research_need",
    label: "研究需求确定",
    stepNumber: "01",
    icon: Compass,
    description: "明确研究主题与核心问题",
  },
  {
    key: "research_plan",
    label: "研究计划生成",
    stepNumber: "02",
    icon: FileCode2,
    description: "构建画像并生成可执行计划",
  },
  {
    key: "research_execution",
    label: "研究开展",
    stepNumber: "03",
    icon: FlaskConical,
    description: "文献精读与实验方案设计",
  },
  {
    key: "research_analysis",
    label: "研究结果分析",
    stepNumber: "04",
    icon: LineChart,
    description: "实验指标归因与结论梳理",
  },
];

export function ResearchStageProgress({
  currentStage,
  completedStages,
}: ResearchStageProgressProps) {
  const completedSet = new Set(completedStages);

  return (
    <div
      role="region"
      aria-label="四阶段研究进度"
      className="app-card rounded-2xl p-3 sm:p-4 shadow-sm border border-slate-200/80 dark:border-zinc-800 bg-white/80 dark:bg-zinc-900/80 backdrop-blur-md select-none"
    >
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 sm:gap-3">
        {STAGES.map((stage) => {
          const isCompleted = completedSet.has(stage.key);
          const isCurrent = stage.key === currentStage && !isCompleted;
          const IconComponent = stage.icon;

          let containerStyle = "";
          let badgeStyle = "";
          let titleStyle = "";
          let descStyle = "";

          if (isCompleted) {
            // Completed: High contrast highlighted state with emerald accent
            containerStyle =
              "bg-emerald-500/10 border-emerald-500/30 text-emerald-950 dark:text-emerald-100 ring-1 ring-emerald-500/20";
            badgeStyle =
              "bg-emerald-600 text-white dark:bg-emerald-500 dark:text-zinc-950";
            titleStyle = "text-emerald-900 dark:text-emerald-200 font-bold";
            descStyle = "text-emerald-700/80 dark:text-emerald-300/80";
          } else if (isCurrent) {
            // Current: Neutral active focus state
            containerStyle =
              "bg-slate-900 text-white dark:bg-zinc-100 dark:text-zinc-900 shadow-md ring-2 ring-slate-900/10 dark:ring-zinc-100/20";
            badgeStyle =
              "bg-white/20 text-white dark:bg-zinc-900/20 dark:text-zinc-900 font-semibold";
            titleStyle = "text-white dark:text-zinc-950 font-bold";
            descStyle = "text-slate-300 dark:text-zinc-600";
          } else {
            // Unstarted: Weakened / dimmed state
            containerStyle =
              "bg-slate-50/60 dark:bg-zinc-900/40 border-slate-200/60 dark:border-zinc-800/60 opacity-50";
            badgeStyle =
              "bg-slate-200 text-slate-500 dark:bg-zinc-800 dark:text-zinc-500";
            titleStyle = "text-slate-500 dark:text-zinc-400 font-medium";
            descStyle = "text-slate-400 dark:text-zinc-500";
          }

          return (
            <div
              key={stage.key}
              aria-disabled="true"
              className={`cursor-default rounded-xl p-3 border transition-all duration-200 ${containerStyle}`}
            >
              <div className="flex items-center gap-2.5">
                <div
                  className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-lg text-xs font-semibold ${badgeStyle}`}
                >
                  {isCompleted ? (
                    <Check className="h-3.5 w-3.5 stroke-[2.5]" />
                  ) : (
                    <span>{stage.stepNumber}</span>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <IconComponent className="h-3.5 w-3.5 shrink-0 opacity-80" />
                    <span className={`truncate text-sm sm:text-base ${titleStyle}`}>
                      {stage.label}
                    </span>
                  </div>
                  <p className={`mt-0.5 truncate text-xs ${descStyle}`}>
                    {stage.description}
                  </p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
