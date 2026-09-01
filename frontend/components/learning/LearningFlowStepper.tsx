"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  BarChart3,
  BookOpen,
  ChevronRight,
  ClipboardList,
  Code2,
  FileQuestion,
  Microscope,
} from "lucide-react";
import { buildKnowledgeId, buildPracticeHref } from "@/lib/learning-context";

export type LearningStepId =
  | "understand"
  | "check"
  | "practice"
  | "portrait"
  | "notebook"
  | "research";

export interface LearningStepConfig {
  id: LearningStepId;
  stepNumber: number;
  label: string;
  shortLabel: string;
  icon: typeof BookOpen;
  defaultHref: string;
}

export const LEARNING_STEPS: LearningStepConfig[] = [
  {
    id: "understand",
    stepNumber: 1,
    label: "理解",
    shortLabel: "理解",
    icon: BookOpen,
    defaultHref: "/learning",
  },
  {
    id: "check",
    stepNumber: 2,
    label: "检查",
    shortLabel: "检查",
    icon: FileQuestion,
    defaultHref: "/learning?view=quiz",
  },
  {
    id: "practice",
    stepNumber: 3,
    label: "动手实践",
    shortLabel: "实践",
    icon: Code2,
    defaultHref: "/learning/practice",
  },
  {
    id: "portrait",
    stepNumber: 4,
    label: "复盘",
    shortLabel: "复盘",
    icon: BarChart3,
    defaultHref: "/learning/portrait",
  },
  {
    id: "notebook",
    stepNumber: 5,
    label: "笔记",
    shortLabel: "笔记",
    icon: ClipboardList,
    defaultHref: "/learning/notebook",
  },
  {
    id: "research",
    stepNumber: 6,
    label: "科研引导",
    shortLabel: "科研",
    icon: Microscope,
    defaultHref: "/research",
  },
];

interface LearningFlowStepperProps {
  currentStep: LearningStepId;
  knowledgePoint?: string;
  sessionId?: string;
  onStepClick?: (stepId: LearningStepId) => boolean | void;
  className?: string;
}

export function LearningFlowStepper({
  currentStep,
  knowledgePoint,
  sessionId,
  onStepClick,
  className = "",
}: LearningFlowStepperProps) {
  const searchParams = useSearchParams();

  function getStepHref(step: LearningStepConfig): string {
    const topic = knowledgePoint?.trim();
    if (step.id === "practice" && topic) {
      return buildPracticeHref({
        knowledgePoint: topic,
        knowledgePointId: buildKnowledgeId(topic),
        sessionId: sessionId ?? undefined,
        currentSearchParams: searchParams,
      });
    }
    if (step.id === "check" && topic) {
      const params = new URLSearchParams(searchParams.toString());
      params.set("view", "quiz");
      return `/learning?${params.toString()}`;
    }
    if (step.id === "understand" && topic) {
      const params = new URLSearchParams(searchParams.toString());
      params.delete("view");
      const query = params.toString();
      return query ? `/learning?${query}` : "/learning";
    }
    return step.defaultHref;
  }

  return (
    <nav
      aria-label="学习闭环六步流程导航"
      className={`app-card mb-6 rounded-2xl p-2 sm:p-2.5 shadow-sm overflow-x-auto ${className}`}
    >
      <ol className="flex min-w-max items-center justify-between gap-1 sm:gap-2">
        {LEARNING_STEPS.map((step, index) => {
          const isCurrent = step.id === currentStep;
          const Icon = step.icon;
          const href = getStepHref(step);

          const stepContent = (
            <div
              className={`flex items-center gap-2 rounded-xl px-2.5 py-1.5 sm:px-3 sm:py-2 text-xs font-semibold transition select-none ${
                isCurrent
                  ? "bg-slate-950 text-white shadow-sm dark:bg-white dark:text-zinc-950"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-white"
              }`}
            >
              <span
                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-[11px] font-bold ${
                  isCurrent
                    ? "bg-white/20 text-white dark:bg-zinc-950/20 dark:text-zinc-950"
                    : "bg-slate-100 text-slate-500 dark:bg-zinc-800 dark:text-zinc-400"
                }`}
              >
                {step.stepNumber}
              </span>
              <Icon className="h-3.5 w-3.5 shrink-0" strokeWidth={1.8} />
              <span>{step.label}</span>
            </div>
          );

          return (
            <li key={step.id} className="flex items-center">
              {onStepClick ? (
                <button
                  type="button"
                  onClick={() => {
                    const handled = onStepClick(step.id);
                    if (!handled && !isCurrent) {
                      window.location.href = href;
                    }
                  }}
                  aria-current={isCurrent ? "step" : undefined}
                  className="cursor-pointer focus:outline-none focus:ring-2 focus:ring-slate-900/20 rounded-xl"
                >
                  {stepContent}
                </button>
              ) : (
                <Link
                  href={href}
                  aria-current={isCurrent ? "step" : undefined}
                  className="focus:outline-none focus:ring-2 focus:ring-slate-900/20 rounded-xl"
                >
                  {stepContent}
                </Link>
              )}

              {index < LEARNING_STEPS.length - 1 && (
                <ChevronRight
                  className="mx-1 h-3.5 w-3.5 shrink-0 text-slate-300 dark:text-zinc-600"
                  aria-hidden="true"
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
