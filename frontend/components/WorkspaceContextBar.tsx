"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { ArrowLeft, BookOpen, BriefcaseBusiness, Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { getLearningSessionId } from "@/lib/api/learning";
import {
  LEARNING_NOTEBOOK_OPEN_EVENT,
  StructuredNotebook,
  type NotebookTab,
} from "@/components/learning/StructuredNotebook";
import {
  fetchTask,
  fetchWorkspace,
  type Workspace,
  type WorkspaceTask,
} from "@/lib/api/workspaces";
import { useLearningSessionId } from "@/lib/store/learning-store";

type ContextState =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "ready"; workspace: Workspace; task: WorkspaceTask | null }
  | { state: "error" };

function safeReturnTo(value: string | null): string | null {
  if (
    typeof window === "undefined" ||
    !value ||
    !value.startsWith("/") ||
    value.startsWith("//") ||
    value.includes("\\")
  ) {
    return null;
  }

  try {
    const destination = new URL(value, window.location.origin);
    if (destination.origin !== window.location.origin) return null;
    return `${destination.pathname}${destination.search}${destination.hash}`;
  } catch {
    return null;
  }
}

function returnLabel(destination: string): string {
  if (destination.startsWith("/workspaces/")) return "返回工作区";
  if (destination.startsWith("/tasks/")) return "返回任务";
  return "返回上一步";
}

function isLearningRoute(pathname: string): boolean {
  return (
    pathname === "/learning" ||
    pathname.startsWith("/learning/") ||
    pathname === "/student/learning" ||
    pathname.startsWith("/student/learning/")
  );
}

function isNotebookTab(value: unknown): value is NotebookTab {
  return (
    value === "summary" ||
    value === "note" ||
    value === "research_note" ||
    value === "wrong_answer" ||
    value === "presentation"
  );
}

function LearningNotebookHost() {
  const [notebookOpen, setNotebookOpen] = useState(false);
  const [notebookInitialTab, setNotebookInitialTab] = useState<NotebookTab>("summary");
  const browserSessionId = useLearningSessionId();
  const [sessionIdOverride, setSessionIdOverride] = useState<string | null>(null);
  const sessionId = sessionIdOverride ?? browserSessionId;

  useEffect(() => {
    function handleOpen(event: Event) {
      const detail = (event as CustomEvent<{ tab?: unknown }>).detail;
      const tab = isNotebookTab(detail?.tab) ? detail.tab : "summary";
      setSessionIdOverride(getLearningSessionId());
      setNotebookInitialTab(tab);
      setNotebookOpen(true);
    }

    window.addEventListener(LEARNING_NOTEBOOK_OPEN_EVENT, handleOpen);
    return () => window.removeEventListener(LEARNING_NOTEBOOK_OPEN_EVENT, handleOpen);
  }, []);

  function showNotebook(tab: NotebookTab) {
    setSessionIdOverride(getLearningSessionId());
    setNotebookInitialTab(tab);
    setNotebookOpen(true);
  }

  return (
    <>
      <button
        type="button"
        onClick={() => showNotebook("summary")}
        aria-label="展开学习笔记"
        className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-slate-200/80 bg-white/80 px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs backdrop-blur-md transition hover:border-slate-300 hover:bg-white active:scale-95 cursor-pointer dark:border-white/15 dark:bg-white/10 dark:text-zinc-200 dark:hover:bg-white/15 dark:hover:text-white"
      >
        <BookOpen className="h-3.5 w-3.5 text-indigo-500 dark:text-purple-300" strokeWidth={1.8} />
        <span>展开学习笔记</span>
      </button>
      <StructuredNotebook
        key={`${sessionId}:${notebookInitialTab}`}
        open={notebookOpen}
        onDismiss={() => setNotebookOpen(false)}
        sessionId={sessionId || undefined}
        initialTab={notebookInitialTab}
      />
    </>
  );
}

/**
 * 统一顶栏中段的「我在哪」面包屑（DESIGN.md §6.6 / D5 Q3）。
 * 原 WorkspaceContextBar 独立条已内聚于此：展示 Workspace / Task 上下文
 * 与返回入口；Learning 页面同时提供常驻学习笔记入口。
 */
export function WorkspaceContextBar() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const workspaceId = searchParams.get("workspace_id");
  const taskId = searchParams.get("task_id");
  const returnTo = useMemo(() => safeReturnTo(searchParams.get("return_to")), [searchParams]);
  const [context, setContext] = useState<ContextState>({ state: "idle" });
  const [retryVersion, setRetryVersion] = useState(0);
  const hasExplicitContext = Boolean(workspaceId || taskId);
  const showLearningNotebook = isLearningRoute(pathname) && pathname !== "/learning/notebook";

  useEffect(() => {
    let active = true;
    if (!hasExplicitContext) {
      return () => {
        active = false;
      };
    }

    const timeoutId = window.setTimeout(() => {
      setContext({ state: "loading" });
      void (async () => {
        try {
          if (taskId) {
            const task = await fetchTask(taskId);
            if (workspaceId && task.workspace_id !== workspaceId) {
              throw new Error("Task 与指定工作区不匹配。");
            }
            const workspace = await fetchWorkspace(task.workspace_id);
            if (active) setContext({ state: "ready", workspace, task });
            return;
          }
          const workspace = await fetchWorkspace(workspaceId!);
          if (active) setContext({ state: "ready", workspace, task: null });
        } catch {
          if (active) setContext({ state: "error" });
        }
      })();
    }, 0);

    return () => {
      active = false;
      window.clearTimeout(timeoutId);
    };
  }, [hasExplicitContext, retryVersion, taskId, workspaceId]);

  if (!hasExplicitContext) {
    if (!isLearningRoute(pathname)) return null;
    return showLearningNotebook ? <LearningNotebookHost /> : null;
  }

  if (context.state === "idle") {
    return showLearningNotebook ? <LearningNotebookHost /> : null;
  }

  if (context.state === "loading") {
    return (
      <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
        <div
          role="status"
          aria-live="polite"
          className="flex min-w-0 items-center gap-1.5 text-xs text-[var(--app-muted)]"
        >
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
          <span className="truncate">正在恢复工作上下文…</span>
        </div>
        {showLearningNotebook && <LearningNotebookHost />}
      </div>
    );
  }

  if (context.state === "error") {
    return (
      <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
        <div
          role="alert"
          className="flex min-w-0 items-center gap-2 truncate text-xs text-amber-700 dark:text-amber-300"
        >
          <span className="truncate">工作上下文不可用</span>
          <button
            type="button"
            onClick={() => setRetryVersion((version) => version + 1)}
            className="shrink-0 font-semibold underline"
          >
            重试
          </button>
          <Link href="/" className="shrink-0 font-semibold underline">
            返回首页
          </Link>
        </div>
        {showLearningNotebook && <LearningNotebookHost />}
      </div>
    );
  }

  const fallback = context.task
    ? `/tasks/${context.task.id}`
    : `/workspaces/${context.workspace.id}`;
  const destination = returnTo ?? fallback;
  const currentIsDestination = pathname === destination;

  return (
    <div className="flex min-w-0 flex-1 items-center gap-2 text-xs text-slate-700 dark:text-zinc-200">
      <div className="flex min-w-0 items-center gap-1.5">
        <BriefcaseBusiness className="h-3.5 w-3.5 shrink-0 text-slate-400 dark:text-zinc-500" />
        <span className="truncate font-semibold">{context.workspace.title}</span>
        {context.task && (
          <>
            <span className="shrink-0 text-slate-400 dark:text-zinc-500">/</span>
            <span className="truncate">{context.task.title}</span>
          </>
        )}
      </div>
      {!currentIsDestination && (
        <Link
          href={destination}
          className="app-button-secondary inline-flex shrink-0 items-center gap-1 rounded-control px-2 py-1 font-semibold hover:bg-slate-50 dark:hover:bg-zinc-800"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">{returnLabel(destination)}</span>
        </Link>
      )}
      {showLearningNotebook && <LearningNotebookHost />}
    </div>
  );
}
