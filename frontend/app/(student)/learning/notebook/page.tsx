"use client";

import { useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { StructuredNotebook } from "@/components/learning/StructuredNotebook";
import { LearningFlowStepper } from "@/components/learning/LearningFlowStepper";
import { useLearningSessionId } from "@/lib/store/learning-store";

type NotebookTab = "summary" | "note" | "research_note" | "wrong_answer" | "presentation";

const NOTEBOOK_TABS: NotebookTab[] = [
  "summary",
  "note",
  "research_note",
  "wrong_answer",
  "presentation",
];

function notebookTab(value: string | null): NotebookTab {
  return NOTEBOOK_TABS.includes(value as NotebookTab) ? (value as NotebookTab) : "summary";
}

export default function LearningNotebookPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const sessionId = useLearningSessionId();
  const initialTab = notebookTab(searchParams.get("tab"));
  const learningHref = useMemo(() => {
    const params = new URLSearchParams(searchParams.toString());
    params.delete("tab");
    const query = params.toString();
    return query ? `/learning?${query}` : "/learning";
  }, [searchParams]);

  return (
    <main className="min-h-[calc(100vh-4rem)] bg-[var(--app-surface)] text-slate-950 dark:text-zinc-50">
      <div className="mx-auto max-w-7xl px-4 pt-4 sm:px-6">
        <LearningFlowStepper
          currentStep="notebook"
          sessionId={sessionId}
        />
      </div>
      <StructuredNotebook
        open
        onDismiss={() => router.push(learningHref)}
        sessionId={sessionId}
        initialTab={initialTab}
      />
    </main>
  );
}
