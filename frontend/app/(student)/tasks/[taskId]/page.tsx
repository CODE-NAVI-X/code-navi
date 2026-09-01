"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, BookOpen, Loader2, RotateCw } from "lucide-react";

import {
  fetchTask,
  listTaskActivities,
  type WorkspaceActivity,
  type WorkspaceTask,
} from "@/lib/api/workspaces";

export default function TaskPage() {
  const params = useParams<{ taskId: string }>();
  const taskId = params.taskId;
  const [task, setTask] = useState<WorkspaceTask | null>(null);
  const [activities, setActivities] = useState<WorkspaceActivity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [taskData, activityData] = await Promise.all([fetchTask(taskId), listTaskActivities(taskId)]);
      setTask(taskData);
      setActivities(activityData);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : String(requestError));
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [load]);

  if (loading) {
    return <TaskState icon={<Loader2 className="h-5 w-5 animate-spin" />} text="正在恢复 Task…" />;
  }
  if (error || !task) {
    return (
      <TaskState
        icon={<RotateCw className="h-5 w-5" />}
        text={error ?? "Task 不可用。"}
        action={<button type="button" onClick={() => void load()} className="font-semibold underline">重试</button>}
      />
    );
  }

  const learningHref = `/learning?workspace_id=${encodeURIComponent(task.workspace_id)}&task_id=${encodeURIComponent(task.id)}&return_to=${encodeURIComponent(`/tasks/${task.id}`)}`;
  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-6 sm:px-6 sm:py-8">
      <nav aria-label="面包屑导航" className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 dark:text-zinc-400">
        <Link href="/" className="hover:text-slate-900 dark:hover:text-zinc-100 transition">工作台</Link>
        <span>&rarr;</span>
        <Link href={`/workspaces/${task.workspace_id}`} className="hover:text-slate-900 dark:hover:text-zinc-100 transition">工作区</Link>
        <span>&rarr;</span>
        <span className="text-slate-900 dark:text-zinc-100 font-bold">任务详情</span>
      </nav>
      <header className="app-card mt-5 rounded-2xl p-5 sm:p-7">
        <p className="text-xs font-semibold tracking-wide text-slate-500 uppercase dark:text-zinc-400">当前 Task · {task.status}</p>
        <h1 className="mt-2 break-words text-2xl font-bold text-slate-950 dark:text-zinc-50">{task.title}</h1>
        <p className="mt-3 break-words whitespace-pre-wrap text-sm leading-6 text-slate-700 dark:text-zinc-200">{task.goal}</p>
        <Link href={learningHref} className="app-button-primary mt-5 inline-flex min-h-11 items-center gap-2 rounded-xl px-4 py-3 text-sm font-semibold hover:bg-slate-800 dark:hover:bg-zinc-200">
          <BookOpen className="h-4 w-4" /> 进入 Learning
          <ArrowRight className="h-4 w-4" />
        </Link>
      </header>

      <section className="app-card mt-6 rounded-2xl p-5">
        <h2 className="text-base font-bold text-slate-950 dark:text-zinc-50">Task 时间线</h2>
        {activities.length === 0 ? (
          <p className="mt-4 text-sm text-slate-600 dark:text-zinc-300">尚无活动。进入 Learning 并成功保存解析后，这里会显示来源摘要。</p>
        ) : (
          <div className="mt-4 space-y-3">
            {activities.map((activity) => (
              <article key={activity.id} className="app-card-subtle rounded-xl p-4">
                <p className="break-words font-semibold text-slate-950 dark:text-zinc-50">{activity.title}</p>
                <p className="mt-1 break-words text-sm text-slate-600 dark:text-zinc-300">{activity.summary}</p>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

function TaskState({
  icon,
  text,
  action,
}: {
  icon: React.ReactNode;
  text: string;
  action?: React.ReactNode;
}) {
  return (
    <main
      role={action ? "alert" : "status"}
      aria-live={action ? "assertive" : "polite"}
      className="mx-auto flex min-h-64 w-full max-w-4xl flex-col items-center justify-center gap-3 px-4 text-center text-sm text-slate-600 dark:text-zinc-300"
    >
      {icon}
      <p>{text}</p>
      {action}
      <Link href="/" className="inline-flex items-center gap-1 font-semibold underline"><ArrowLeft className="h-4 w-4" /> 返回首页</Link>
    </main>
  );
}
