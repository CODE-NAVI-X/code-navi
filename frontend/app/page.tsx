"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment, type FormEvent, useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  BarChart3,
  BookOpen,
  BriefcaseBusiness,
  Code2,
  Loader2,
  Microscope,
  Plus,
  Target,
  Zap,
} from "lucide-react";

import { AppShell } from "@/components/AppShell";
import {
  createTask,
  createWorkspace,
  getLocalProfileId,
  listRecentTasks,
  listWorkspaces,
  type Workspace,
  type WorkspaceTask,
} from "@/lib/api/workspaces";
import {
  fetchPortraitsOverview,
  type PortraitsOverviewResponse,
} from "@/lib/api/profile";
import { getPersistedFlowPayload, type FlowPayload } from "@/lib/store/flow-store";
import { getOrCreateLearnerId } from "@/lib/learner";

import { useAuth } from "@/lib/context/auth-context";

type OverviewState = "loading" | "ready" | "error";

const GAP_SOURCE_LABELS: Record<string, string> = {
  quiz_attempt: "测验",
  confusion_mark: "标记",
  practice_outcome: "练习",
  code_fill_attempt: "填空",
};

const capabilityCards = [
  {
    index: "01",
    label: "EXPLORE",
    title: "理解与探索",
    description: "概念解析 / 代码问答",
    href: "/learning",
    cta: "进入学习",
    icon: BookOpen,
    featured: false,
  },
  {
    index: "02",
    label: "PRACTICE",
    title: "动手实践",
    description: "填空判题 / 实操验证",
    href: "/learning/practice",
    cta: "进入实践",
    icon: Code2,
    featured: false,
  },
  {
    index: "03",
    label: "REVIEW",
    title: "知识复盘",
    description: "技能雷达 / 薄弱分析",
    href: "/learning/portrait",
    cta: "查看画像",
    icon: BarChart3,
    featured: false,
  },
  {
    index: "04",
    label: "RESEARCH",
    title: "科研引导",
    description: "论文研读 / 四阶段引导",
    href: "/research",
    cta: "进入科研",
    icon: Microscope,
    featured: true,
  },
];

export default function HomePage() {
  const router = useRouter();
  const { mode, loading: authLoading } = useAuth();
  const [goal, setGoal] = useState("");
  const [workspaceTitle, setWorkspaceTitle] = useState("");
  const [recentTasks, setRecentTasks] = useState<WorkspaceTask[]>([]);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [creatingTask, setCreatingTask] = useState(false);
  const [creatingWorkspace, setCreatingWorkspace] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [flowPayload, setFlowPayload] = useState<FlowPayload | null>(null);
  const [overview, setOverview] = useState<PortraitsOverviewResponse | null>(null);
  const [overviewState, setOverviewState] = useState<OverviewState>("loading");
  const [overviewRetry, setOverviewRetry] = useState(0);

  useEffect(() => {
    if (!authLoading && mode !== "authenticated") {
      router.replace("/login");
    }
  }, [authLoading, mode, router]);

  const load = useCallback(async () => {
    if (mode !== "authenticated") return;
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
  }, [mode]);

  useEffect(() => {
    if (mode === "authenticated") {
      const timeoutId = window.setTimeout(() => {
        void load();
      }, 0);
      return () => window.clearTimeout(timeoutId);
    }
  }, [load, mode]);

  useEffect(() => {
    // flow-store is a localStorage-backed resume cache; read it after mount.
    const timeoutId = window.setTimeout(() => {
      setFlowPayload(getPersistedFlowPayload());
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, []);

  useEffect(() => {
    if (mode !== "authenticated") return;
    let active = true;
    const timeoutId = window.setTimeout(() => {
      setOverviewState("loading");
      void (async () => {
        try {
          const response = await fetchPortraitsOverview(getOrCreateLearnerId(), {
            localProfileId: getLocalProfileId(),
            conversationLimit: 5,
          });
          if (active) {
            setOverview(response);
            setOverviewState("ready");
          }
        } catch {
          if (active) setOverviewState("error");
        }
      })();
    }, 0);
    return () => {
      active = false;
      window.clearTimeout(timeoutId);
    };
  }, [mode, overviewRetry]);

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

  const practiceTopic = flowPayload
    ? flowPayload.practiceContext?.objective?.trim() ||
      flowPayload.masteredKnowledgePoint.name
    : null;
  const latestTask = recentTasks[0] ?? null;
  const latestConversation = overview?.research.conversations[0] ?? null;
  const hasResumeEntry = Boolean(practiceTopic || latestTask || latestConversation);
  const knowledgeGaps = overview?.learning.knowledge_gaps.slice(0, 3) ?? [];

  return (
    <AppShell>
      <main className="bg-grid-pattern-light min-h-[calc(100vh-3rem)] dark:bg-grid-pattern">
        <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 md:py-10 lg:px-8">
          {/* ── 第一区：继续上次（Resume Hero） ─────────────────────────── */}
          <section aria-labelledby="resume-hero-title">
            <div className="flex items-baseline justify-between gap-3">
              <h1 id="resume-hero-title" className="text-xl font-bold tracking-tight text-slate-950 dark:text-zinc-50">
                继续上次
              </h1>
              <span className="font-mono text-xs tracking-wider text-blue-600 dark:text-blue-500 uppercase">
                Resume
              </span>
            </div>

            <div className="tech-border-glow app-card mt-3 rounded-card border p-5 sm:p-6">
              {loading && overviewState === "loading" ? (
                <div className="space-y-3" role="status" aria-live="polite" aria-label="正在恢复最近记录">
                  <div className="h-4 w-2/3 animate-pulse rounded bg-[var(--app-card-subtle)]" />
                  <div className="h-4 w-1/2 animate-pulse rounded bg-[var(--app-card-subtle)]" />
                </div>
              ) : hasResumeEntry ? (
                <ul className="space-y-3">
                  {practiceTopic && (
                    <ResumeRow
                      icon={<Zap className="h-4 w-4 shrink-0 text-blue-600 dark:text-blue-500" />}
                      label="上次停留在 · 动手实践"
                      value={practiceTopic}
                      href="/learning/practice"
                      action="继续练习"
                    />
                  )}
                  {latestTask && (
                    <ResumeRow
                      icon={<BriefcaseBusiness className="h-4 w-4 shrink-0 text-blue-600 dark:text-blue-500" />}
                      label="最近 Task"
                      value={latestTask.title}
                      href={`/tasks/${latestTask.id}`}
                      action="打开任务"
                    />
                  )}
                  {latestConversation && (
                    <ResumeRow
                      icon={<Microscope className="h-4 w-4 shrink-0 text-blue-600 dark:text-blue-500" />}
                      label="最近科研"
                      value={latestConversation.topic ?? "未命名科研对话"}
                      href="/research"
                      action="进入科研"
                    />
                  )}
                </ul>
              ) : (
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="font-mono text-xs tracking-wider text-blue-600 dark:text-blue-500 uppercase">
                      Quick Start
                    </p>
                    <p className="mt-1 text-base font-semibold text-slate-950 dark:text-zinc-50">
                      快速启航：完成你的第一次概念测验
                    </p>
                    <p className="mt-1 text-base text-[var(--app-muted)]">
                      从一个概念或问题进入学习，系统会随学习进展自动生成复盘与练习建议。
                    </p>
                  </div>
                  <Link
                    href="/learning"
                    className="app-button-primary inline-flex shrink-0 items-center gap-2 rounded-control px-4 py-2 text-sm font-semibold transition hover:opacity-90"
                  >
                    进入学习
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </div>
              )}
            </div>
          </section>

          {/* ── 第二区：学习闭环与科研衔接（Learning loop and research handoff） ── */}
          <section aria-labelledby="capability-loop-title" className="mt-6">
            <div className="flex items-baseline justify-between gap-3">
              <h2 id="capability-loop-title" className="text-xl font-bold tracking-tight text-slate-950 dark:text-zinc-50">
                学习闭环与科研衔接
              </h2>
              <span className="font-mono text-xs tracking-wider text-blue-600 dark:text-blue-500 uppercase">
                Learning Loop → Research
              </span>
            </div>

            <div className="mt-3 flex flex-col gap-4 md:grid md:grid-cols-2 xl:flex xl:flex-row xl:items-stretch">
              {capabilityCards.map((card, index) => {
                const Icon = card.icon;
                return (
                  <Fragment key={card.href}>
                    <Link
                      href={card.href}
                      className={`app-card group flex flex-1 flex-col rounded-card p-5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[var(--app-shadow-lift)] ${
                        card.featured ? "tech-border-glow border" : ""
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-xs tracking-wider text-blue-600 dark:text-blue-500">
                          {`${card.index} // ${card.label}`}
                        </span>
                        <Icon className="h-4 w-4 text-slate-400 dark:text-zinc-500" strokeWidth={1.8} />
                      </div>
                      <p className="mt-4 text-base font-semibold text-slate-950 dark:text-zinc-50">
                        {card.title}
                      </p>
                      <p className="mt-1 flex-1 text-base text-[var(--app-muted)]">{card.description}</p>
                      <span className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-blue-600 dark:text-blue-400">
                        {card.cta}
                        <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
                      </span>
                    </Link>
                    {index < capabilityCards.length - 1 && (
                      <div
                        className="hidden items-center text-slate-300 dark:text-zinc-600 xl:flex"
                        aria-hidden="true"
                      >
                        <ArrowRight className="h-4 w-4" />
                      </div>
                    )}
                  </Fragment>
                );
              })}
            </div>
          </section>

          {/* ── 第三区：待办与智能推荐（Action Hub） ─────────────────────── */}
          <section aria-labelledby="action-hub-title" className="mt-6 grid gap-4 lg:grid-cols-2">
            <h2 id="action-hub-title" className="sr-only">
              待办与智能推荐
            </h2>

            {/* 左：薄弱项诊断与一键组卷 */}
            <article className="app-card flex flex-col rounded-card p-5">
              <div className="flex items-baseline justify-between gap-3">
                <h3 className="flex items-center gap-2 text-base font-bold text-slate-950 dark:text-zinc-50">
                  <Target className="h-4 w-4 text-blue-600 dark:text-blue-500" />
                  薄弱项诊断与组卷
                </h3>
                <span className="font-mono text-xs tracking-wider text-blue-600 dark:text-blue-500 uppercase">Action Hub</span>
              </div>

              {overviewState === "loading" ? (
                <div className="mt-4 flex gap-2" role="status" aria-label="正在加载薄弱项诊断">
                  <div className="h-6 w-24 animate-pulse rounded-full bg-[var(--app-card-subtle)]" />
                  <div className="h-6 w-28 animate-pulse rounded-full bg-[var(--app-card-subtle)]" />
                </div>
              ) : overviewState === "error" ? (
                <div className="app-status-error mt-4 rounded-control p-3 text-base" role="alert">
                  薄弱项诊断加载失败。
                  <button
                    type="button"
                    onClick={() => setOverviewRetry((version) => version + 1)}
                    className="ml-2 font-semibold underline"
                  >
                    重试
                  </button>
                </div>
              ) : knowledgeGaps.length > 0 ? (
                <ul className="mt-4 flex flex-wrap gap-2">
                  {knowledgeGaps.map((gap) => (
                    <li
                      key={`${gap.source_type}-${gap.knowledge_point}`}
                      className="app-card-subtle inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium text-slate-700 dark:text-zinc-200"
                    >
                      {gap.knowledge_point}
                      <span className="text-[var(--app-muted)]">
                        · {GAP_SOURCE_LABELS[gap.source_type] ?? "诊断"}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-4 text-base text-[var(--app-muted)]">
                  暂无薄弱项诊断——完成概念测验或练习后，这里会给出针对性建议。
                </p>
              )}

              <div className="mt-auto pt-4">
                <button
                  type="button"
                  onClick={() => router.push("/learning/practice?source=learning")}
                  className="app-button-primary inline-flex w-full items-center justify-center gap-2 rounded-control px-4 py-2.5 text-sm font-semibold transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Zap className="h-4 w-4" />
                  针对薄弱项一键组卷练习
                </button>
                <p className="mt-2 text-xs text-[var(--app-muted)]">
                  进入动手实践并预选「从学习数据生成」，由你确认后调用练习网关出题。
                </p>
              </div>
            </article>

            {/* 右：活跃工作区与任务快速直达 */}
            <article className="app-card flex flex-col rounded-card p-5">
              <div className="flex items-baseline justify-between gap-3">
                <h3 className="flex items-center gap-2 text-base font-bold text-slate-950 dark:text-zinc-50">
                  <BriefcaseBusiness className="h-4 w-4 text-blue-600 dark:text-blue-500" />
                  活跃工作区与任务
                </h3>
                {loading && <Loader2 className="h-4 w-4 animate-spin text-slate-500" />}
              </div>

              {!loading && workspaces.length === 0 && recentTasks.length === 0 && (
                <p className="mt-4 text-base text-[var(--app-muted)]">
                  还没有工作区或 Task。展开「快速新建」即可从目标开始，也可直接使用任一能力。
                </p>
              )}

              {workspaces.length > 0 && (
                <ul className="mt-4 space-y-2">
                  {workspaces.slice(0, 3).map((workspace) => {
                    const taskCount = recentTasks.filter(
                      (task) => task.workspace_id === workspace.id,
                    ).length;
                    return (
                      <li key={workspace.id}>
                        <Link
                          href={`/workspaces/${workspace.id}`}
                          className="app-card-subtle flex items-center justify-between gap-3 rounded-control p-3 transition hover:-translate-y-0.5"
                        >
                          <span className="truncate text-base font-semibold text-slate-950 dark:text-zinc-50">
                            {workspace.title}
                          </span>
                          <span className="shrink-0 font-mono text-xs text-[var(--app-muted)]">
                            {taskCount > 0 ? `${taskCount} 个最近任务` : workspace.kind}
                          </span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}

              {recentTasks.length > 0 && (
                <div className="mt-4">
                  <p className="text-xs font-bold tracking-wider text-slate-500 uppercase dark:text-zinc-400">
                    最近 Task
                  </p>
                  <ul className="mt-2 space-y-1.5">
                    {recentTasks.slice(0, 3).map((task) => (
                      <li key={task.id}>
                        <Link
                          href={`/tasks/${task.id}`}
                          className="block truncate rounded-control px-2 py-1.5 text-base text-slate-700 transition hover:bg-[var(--app-card-subtle)] dark:text-zinc-200"
                        >
                          {task.title}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <details className="mt-auto pt-4">
                <summary className="cursor-pointer text-sm font-semibold text-blue-600 dark:text-blue-400">
                  ＋ 快速新建（Task / 工作区）
                </summary>
                <form onSubmit={handleCreateTask} className="mt-3 flex flex-col gap-2">
                  <label className="sr-only" htmlFor="task-goal">当前目标</label>
                  <input
                    id="task-goal"
                    value={goal}
                    onChange={(event) => setGoal(event.target.value)}
                    maxLength={2000}
                    placeholder="例如：理解 Q-learning 更新过程"
                    className="app-input w-full rounded-control px-3 py-2 text-sm"
                  />
                  <button
                    type="submit"
                    disabled={creatingTask || !goal.trim()}
                    className="app-button-primary inline-flex items-center justify-center gap-2 rounded-control px-4 py-2 text-sm font-semibold transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {creatingTask ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                    创建目标并进入 Learning
                  </button>
                </form>
                <form onSubmit={handleCreateWorkspace} className="mt-2 flex flex-col gap-2">
                  <label className="sr-only" htmlFor="workspace-title">工作区名称</label>
                  <input
                    id="workspace-title"
                    value={workspaceTitle}
                    onChange={(event) => setWorkspaceTitle(event.target.value)}
                    maxLength={200}
                    placeholder="新建课程、项目或研究工作区"
                    className="app-input w-full rounded-control px-3 py-2 text-sm"
                  />
                  <button
                    type="submit"
                    disabled={creatingWorkspace || !workspaceTitle.trim()}
                    className="app-button-secondary inline-flex items-center justify-center gap-2 rounded-control px-4 py-2 text-sm font-semibold transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-zinc-800"
                  >
                    {creatingWorkspace ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                    新建工作区
                  </button>
                </form>
              </details>
            </article>
          </section>

          {error && (
            <section
              role="alert"
              className="app-status-error mt-6 rounded-card p-4 text-base"
            >
              <p>{error}</p>
              <button type="button" onClick={() => void load()} className="mt-2 font-semibold underline">
                重试加载
              </button>
            </section>
          )}
        </div>
      </main>
    </AppShell>
  );
}

function ResumeRow({
  icon,
  label,
  value,
  href,
  action,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  href: string;
  action: string;
}) {
  return (
    <li className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-center gap-2.5">
        {icon}
        <div className="min-w-0">
          <p className="text-xs font-medium text-[var(--app-muted)]">{label}</p>
          <p className="truncate text-base font-semibold text-slate-950 dark:text-zinc-50">
            {value}
          </p>
        </div>
      </div>
      <Link
        href={href}
        className="app-button-secondary inline-flex shrink-0 items-center gap-1.5 self-start rounded-control px-3 py-1.5 text-sm font-semibold transition hover:bg-slate-50 dark:hover:bg-zinc-800 sm:self-auto"
      >
        {action}
        <ArrowRight className="h-3.5 w-3.5" />
      </Link>
    </li>
  );
}
