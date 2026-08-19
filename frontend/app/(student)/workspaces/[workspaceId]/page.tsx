"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { ArrowLeft, Loader2, Plus, RotateCw } from "lucide-react";

import {
  createTask,
  fetchWorkspace,
  listWorkspaceActivities,
  listWorkspaceTasks,
  type Workspace,
  type WorkspaceActivity,
  type WorkspaceTask,
} from "@/lib/api/workspaces";

export default function WorkspacePage() {
  const params = useParams<{ workspaceId: string }>();
  const router = useRouter();
  const workspaceId = params.workspaceId;
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [tasks, setTasks] = useState<WorkspaceTask[]>([]);
  const [activities, setActivities] = useState<WorkspaceActivity[]>([]);
  const [goal, setGoal] = useState("");
  const [loading, setLoading] = useState(true);
  const [creatingTask, setCreatingTask] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [workspaceData, taskData, activityData] = await Promise.all([
        fetchWorkspace(workspaceId),
        listWorkspaceTasks(workspaceId),
        listWorkspaceActivities(workspaceId),
      ]);
      setWorkspace(workspaceData);
      setTasks(taskData);
      setActivities(activityData);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : String(requestError));
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

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
      const task = await createTask({ goal: trimmedGoal, workspaceId });
      router.push(
        `/learning?workspace_id=${encodeURIComponent(workspaceId)}&task_id=${encodeURIComponent(task.id)}&return_to=${encodeURIComponent(`/workspaces/${workspaceId}`)}`,
      );
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : String(requestError));
    } finally {
      setCreatingTask(false);
    }
  }

  if (loading) {
    return <PageState icon={<Loader2 className="h-5 w-5 animate-spin" />} text="正在恢复工作区…" />;
  }

  if (error || !workspace) {
    return (
      <PageState
        icon={<RotateCw className="h-5 w-5" />}
        text={error ?? "工作区不可用。"}
        action={<button type="button" onClick={() => void load()} className="font-semibold underline">重试</button>}
      />
    );
  }

  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 sm:py-8">
      <Link href="/" className="inline-flex items-center gap-1 text-sm font-semibold text-slate-600 hover:text-slate-950 dark:text-zinc-300 dark:hover:text-white">
        <ArrowLeft className="h-4 w-4" /> 首页
      </Link>
      <header className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900 sm:p-7">
        <p className="text-xs font-semibold tracking-wide text-slate-500 uppercase dark:text-zinc-400">{workspace.kind} 工作区</p>
        <h1 className="mt-2 text-2xl font-bold text-slate-950 dark:text-zinc-50">{workspace.title}</h1>
        {workspace.description && <p className="mt-2 text-sm text-slate-600 dark:text-zinc-300">{workspace.description}</p>}
        <form onSubmit={handleCreateTask} className="mt-5 flex flex-col gap-2 sm:flex-row">
          <label className="sr-only" htmlFor="workspace-task-goal">新 Task 目标</label>
          <input
            id="workspace-task-goal"
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            placeholder="在此工作区创建一个目标"
            maxLength={2000}
            className="min-w-0 flex-1 rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm focus:border-slate-900 focus:ring-2 focus:ring-slate-900/15 focus:outline-none dark:border-zinc-700 dark:bg-zinc-950"
          />
          <button
            type="submit"
            disabled={creatingTask || !goal.trim()}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-50 dark:text-zinc-950"
          >
            {creatingTask ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            创建并进入 Learning
          </button>
        </form>
      </header>

      <section className="mt-6 grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
          <h2 className="text-base font-bold text-slate-950 dark:text-zinc-50">Tasks</h2>
          {tasks.length === 0 ? (
            <p className="mt-4 text-sm text-slate-600 dark:text-zinc-300">尚未创建 Task。可以从上方目标开始。</p>
          ) : (
            <div className="mt-4 space-y-2">
              {tasks.map((task) => (
                <Link key={task.id} href={`/tasks/${task.id}`} className="block rounded-xl border border-slate-200 p-3 hover:bg-slate-50 dark:border-zinc-800 dark:hover:bg-zinc-800">
                  <p className="font-semibold text-slate-950 dark:text-zinc-50">{task.title}</p>
                  <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-600 dark:text-zinc-300">{task.goal}</p>
                </Link>
              ))}
            </div>
          )}
        </div>
        <ActivityTimeline activities={activities} />
      </section>
    </main>
  );
}

function ActivityTimeline({ activities }: { activities: WorkspaceActivity[] }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-base font-bold text-slate-950 dark:text-zinc-50">最近活动</h2>
      {activities.length === 0 ? (
        <p className="mt-4 text-sm text-slate-600 dark:text-zinc-300">Learning 保存解析后，安全摘要会显示在这里。</p>
      ) : (
        <div className="mt-4 space-y-3">
          {activities.map((activity) => (
            <div key={activity.id} className="border-l-2 border-slate-300 pl-3 dark:border-zinc-600">
              <p className="font-semibold text-sm text-slate-900 dark:text-zinc-100">{activity.title}</p>
              <p className="mt-1 text-xs leading-5 text-slate-600 dark:text-zinc-300">{activity.summary}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function PageState({
  icon,
  text,
  action,
}: {
  icon: React.ReactNode;
  text: string;
  action?: React.ReactNode;
}) {
  return (
    <main className="mx-auto flex min-h-64 w-full max-w-5xl flex-col items-center justify-center gap-3 px-4 text-center text-sm text-slate-600 dark:text-zinc-300">
      {icon}
      <p>{text}</p>
      {action}
      <Link href="/" className="inline-flex items-center gap-1 font-semibold underline"><ArrowLeft className="h-4 w-4" /> 返回首页</Link>
    </main>
  );
}
