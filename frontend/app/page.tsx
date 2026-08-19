"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  BookOpen,
  BriefcaseBusiness,
  Code2,
  Loader2,
  Microscope,
  Plus,
} from "lucide-react";

import { AppShell } from "@/components/AppShell";
import {
  createTask,
  createWorkspace,
  listRecentTasks,
  listWorkspaces,
  type Workspace,
  type WorkspaceTask,
} from "@/lib/api/workspaces";

export default function HomePage() {
  const router = useRouter();
  const [goal, setGoal] = useState("");
  const [workspaceTitle, setWorkspaceTitle] = useState("");
  const [recentTasks, setRecentTasks] = useState<WorkspaceTask[]>([]);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [creatingTask, setCreatingTask] = useState(false);
  const [creatingWorkspace, setCreatingWorkspace] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [tasks, savedWorkspaces] = await Promise.all([listRecentTasks(), listWorkspaces()]);
      setRecentTasks(tasks);
      setWorkspaces(savedWorkspaces);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : String(requestError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [load]);

  async function handleCreateTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedGoal = goal.trim();
    if (!trimmedGoal) return;

    setCreatingTask(true);
    setError(null);
    try {
      const task = await createTask({ goal: trimmedGoal });
      router.push(
        `/learning?workspace_id=${encodeURIComponent(task.workspace_id)}&task_id=${encodeURIComponent(task.id)}&return_to=${encodeURIComponent(`/tasks/${task.id}`)}`,
      );
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : String(requestError));
    } finally {
      setCreatingTask(false);
    }
  }

  async function handleCreateWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedTitle = workspaceTitle.trim();
    if (!trimmedTitle) return;

    setCreatingWorkspace(true);
    setError(null);
    try {
      const workspace = await createWorkspace({ title: trimmedTitle });
      router.push(`/workspaces/${workspace.id}`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : String(requestError));
    } finally {
      setCreatingWorkspace(false);
    }
  }

  return (
    <AppShell>
      <main className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 sm:py-12">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-8 dark:border-zinc-800 dark:bg-zinc-900">
          <p className="text-xs font-semibold tracking-wide text-slate-500 uppercase dark:text-zinc-400">
            Persistent Workspace Foundation
          </p>
          <h1 className="mt-3 max-w-3xl text-2xl font-bold tracking-tight text-slate-950 sm:text-4xl dark:text-zinc-50">
            从当前目标、已有工作区或任一能力开始。
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600 dark:text-zinc-300">
            工作区保存长期组织关系；Task 聚焦目标与成功标准。Learning、Practice 与 Research 仍可独立使用。
          </p>

          <form onSubmit={handleCreateTask} className="mt-6 flex flex-col gap-2 sm:flex-row">
            <label className="sr-only" htmlFor="task-goal">当前目标</label>
            <input
              id="task-goal"
              value={goal}
              onChange={(event) => setGoal(event.target.value)}
              maxLength={2000}
              placeholder="例如：理解 Q-learning 更新过程"
              className="min-w-0 flex-1 rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-950 placeholder:text-slate-400 focus:border-slate-900 focus:ring-2 focus:ring-slate-900/15 focus:outline-none dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-50"
            />
            <button
              type="submit"
              disabled={creatingTask || !goal.trim()}
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-50 dark:text-zinc-950 dark:hover:bg-zinc-200"
            >
              {creatingTask ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
              创建目标并进入 Learning
            </button>
          </form>
        </section>

        {error && (
          <section className="mt-5 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-200">
            <p>{error}</p>
            <button type="button" onClick={() => void load()} className="mt-2 font-semibold underline">
              重试加载
            </button>
          </section>
        )}

        <section className="mt-8 grid gap-5 lg:grid-cols-2">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
            <div className="flex items-center justify-between gap-3">
              <h2 className="flex items-center gap-2 text-base font-bold text-slate-950 dark:text-zinc-50">
                <BriefcaseBusiness className="h-4 w-4" /> 继续最近 Task
              </h2>
              {loading && <Loader2 className="h-4 w-4 animate-spin text-slate-500" />}
            </div>
            {!loading && recentTasks.length === 0 && (
              <p className="mt-4 text-sm text-slate-600 dark:text-zinc-300">还没有 Task。输入上方目标即可开始。</p>
            )}
            <div className="mt-4 space-y-2">
              {recentTasks.map((task) => (
                <Link
                  key={task.id}
                  href={`/tasks/${task.id}`}
                  className="block rounded-xl border border-slate-200 p-3 transition hover:border-slate-400 hover:bg-slate-50 dark:border-zinc-800 dark:hover:border-zinc-600 dark:hover:bg-zinc-800"
                >
                  <p className="font-semibold text-slate-900 dark:text-zinc-100">{task.title}</p>
                  <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-600 dark:text-zinc-300">{task.goal}</p>
                </Link>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
            <h2 className="flex items-center gap-2 text-base font-bold text-slate-950 dark:text-zinc-50">
              <BriefcaseBusiness className="h-4 w-4" /> 进入工作区
            </h2>
            <form onSubmit={handleCreateWorkspace} className="mt-4 flex gap-2">
              <label className="sr-only" htmlFor="workspace-title">工作区名称</label>
              <input
                id="workspace-title"
                value={workspaceTitle}
                onChange={(event) => setWorkspaceTitle(event.target.value)}
                maxLength={200}
                placeholder="新建课程、项目或研究工作区"
                className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-900 focus:ring-2 focus:ring-slate-900/15 focus:outline-none dark:border-zinc-700 dark:bg-zinc-950"
              />
              <button
                type="submit"
                disabled={creatingWorkspace || !workspaceTitle.trim()}
                className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-50 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
              >
                {creatingWorkspace ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                新建
              </button>
            </form>
            {!loading && workspaces.length === 0 && (
              <p className="mt-4 text-sm text-slate-600 dark:text-zinc-300">先新建一个工作区，再在其中创建 Task。</p>
            )}
            <div className="mt-4 space-y-2">
              {workspaces.map((workspace) => (
                <Link
                  key={workspace.id}
                  href={`/workspaces/${workspace.id}`}
                  className="block rounded-xl border border-slate-200 p-3 transition hover:border-slate-400 hover:bg-slate-50 dark:border-zinc-800 dark:hover:border-zinc-600 dark:hover:bg-zinc-800"
                >
                  <p className="font-semibold text-slate-900 dark:text-zinc-100">{workspace.title}</p>
                  <p className="mt-1 text-xs text-slate-500 dark:text-zinc-400">{workspace.kind}</p>
                </Link>
              ))}
            </div>
          </div>
        </section>

        <section className="mt-8">
          <h2 className="text-base font-bold text-slate-950 dark:text-zinc-50">直接使用能力</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <CapabilityLink href="/learning" icon={<BookOpen className="h-5 w-5" />} title="Learning" description="独立学习，结果归入个人工作区。" />
            <CapabilityLink href="/practice" icon={<Code2 className="h-5 w-5" />} title="Practice" description="独立练习；本切片不写入工作区时间线。" />
            <CapabilityLink href="/research" icon={<Microscope className="h-5 w-5" />} title="Research" description="独立科研流程；本切片不改造其持久化。" />
          </div>
        </section>
      </main>
    </AppShell>
  );
}

function CapabilityLink({
  href,
  icon,
  title,
  description,
}: {
  href: string;
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <Link
      href={href}
      className="rounded-2xl border border-slate-200 bg-white p-4 transition hover:border-slate-400 hover:bg-slate-50 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-zinc-600 dark:hover:bg-zinc-800"
    >
      <div className="text-slate-700 dark:text-zinc-200">{icon}</div>
      <h3 className="mt-3 font-bold text-slate-950 dark:text-zinc-50">{title}</h3>
      <p className="mt-1 text-sm leading-5 text-slate-600 dark:text-zinc-300">{description}</p>
    </Link>
  );
}
