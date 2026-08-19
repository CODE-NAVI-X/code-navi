"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { ArrowLeft, BriefcaseBusiness, Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  fetchTask,
  fetchWorkspace,
  type Workspace,
  type WorkspaceTask,
} from "@/lib/api/workspaces";

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

export function WorkspaceContextBar() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const workspaceId = searchParams.get("workspace_id");
  const taskId = searchParams.get("task_id");
  const returnTo = useMemo(() => safeReturnTo(searchParams.get("return_to")), [searchParams]);
  const [context, setContext] = useState<ContextState>({ state: "idle" });
  const [retryVersion, setRetryVersion] = useState(0);
  const hasExplicitContext = Boolean(workspaceId || taskId);

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
    const isLearningRoute =
      pathname === "/learning" ||
      pathname.startsWith("/learning/") ||
      pathname === "/student/learning" ||
      pathname.startsWith("/student/learning/");
    if (!isLearningRoute) return null;
    return (
      <div className="border-t border-[var(--app-border)] bg-white/80 px-3 py-2 dark:bg-zinc-950/80">
        <div className="mx-auto max-w-[1920px] text-xs text-slate-600 dark:text-zinc-300">
          独立 Learning：解析会保存至个人工作区，但不关联 Task。
        </div>
      </div>
    );
  }

  if (context.state === "idle") return null;

  if (context.state === "loading") {
    return (
      <div className="border-t border-[var(--app-border)] bg-white/80 px-3 py-2 dark:bg-zinc-950/80">
        <div className="mx-auto flex max-w-[1920px] items-center gap-2 text-xs text-slate-600 dark:text-zinc-300">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          正在恢复工作上下文…
        </div>
      </div>
    );
  }

  if (context.state === "error") {
    return (
      <div className="border-t border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-900/50 dark:bg-amber-950/30">
        <div className="mx-auto flex max-w-[1920px] flex-wrap items-center justify-between gap-2 text-xs text-amber-900 dark:text-amber-200">
          <span>工作上下文不可用；请从有效的工作区或任务入口重新进入。</span>
          <div className="flex items-center gap-3">
            <button type="button" onClick={() => setRetryVersion((version) => version + 1)} className="font-semibold underline">
              重试
            </button>
            <Link className="font-semibold underline" href="/">返回首页</Link>
          </div>
        </div>
      </div>
    );
  }

  const fallback = context.task
    ? `/tasks/${context.task.id}`
    : `/workspaces/${context.workspace.id}`;
  const destination = returnTo ?? fallback;
  const currentIsDestination = pathname === destination;

  return (
    <div className="border-t border-[var(--app-border)] bg-white/80 px-3 py-2 dark:bg-zinc-950/80">
      <div className="mx-auto flex max-w-[1920px] flex-wrap items-center justify-between gap-2 text-xs text-slate-700 dark:text-zinc-200">
        <div className="flex min-w-0 items-center gap-2">
          <BriefcaseBusiness className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate font-semibold">{context.workspace.title}</span>
          {context.task && (
            <>
              <span className="text-slate-400 dark:text-zinc-500">/</span>
              <span className="truncate">{context.task.title}</span>
            </>
          )}
        </div>
        {!currentIsDestination && (
          <Link
            href={destination}
            className="inline-flex shrink-0 items-center gap-1 rounded-md border border-slate-200 px-2 py-1 font-semibold hover:bg-slate-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            {returnLabel(destination)}
          </Link>
        )}
      </div>
    </div>
  );
}
