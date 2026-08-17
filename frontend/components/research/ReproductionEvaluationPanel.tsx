"use client";

import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ClipboardList,
  FileWarning,
  Loader2,
  RotateCcw,
  ShieldCheck,
  SkipForward,
} from "lucide-react";
import { useEffect, useState } from "react";

import {
  createReproductionEvaluation,
  listReproductionEvaluations,
  type ReproductionEvaluationStatus,
  type ReproductionImprovementTask,
  type ReproductionProjectEvaluation,
  updateReproductionImprovementTask,
} from "@/lib/api/research";

import { ClassificationBadge } from "./ClassificationBadge";

const statusCopy: Record<
  ReproductionEvaluationStatus,
  { label: string; className: string }
> = {
  not_evaluable: {
    label: "不可评估",
    className: "bg-slate-100 text-slate-600 dark:bg-zinc-800 dark:text-zinc-300",
  },
  needs_revision: {
    label: "需要补充",
    className: "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300",
  },
  evidence_partial: {
    label: "证据部分完整",
    className: "bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300",
  },
  checklist_complete: {
    label: "清单项完整",
    className:
      "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300",
  },
};

const taskStatusCopy = {
  pending: "待处理",
  accepted: "已接受",
  skipped: "已跳过",
  completed: "用户已确认完成",
};

function DimensionCard({
  dimension,
}: {
  dimension: ReproductionProjectEvaluation["dimensions"][number];
}) {
  const status = statusCopy[dimension.status];
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-950/40">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-bold text-slate-900 dark:text-zinc-100">
            {dimension.label}
          </p>
          <p className="mt-1 text-[11px] font-semibold text-slate-500 dark:text-zinc-400">
            {dimension.score === null ? "未评分 / 20" : `${dimension.score} / 20`}
          </p>
        </div>
        <span className={`rounded-full px-2 py-1 text-[10px] font-bold ${status.className}`}>
          {status.label}
        </span>
      </div>

      {dimension.issues.length > 0 && (
        <ul className="mt-3 space-y-1 text-[11px] leading-5 text-rose-700 dark:text-rose-300">
          {dimension.issues.map((issue) => (
            <li key={issue} className="flex gap-1.5">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{issue}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3 rounded-xl bg-slate-50 p-2.5 text-[10px] leading-5 text-slate-600 dark:bg-zinc-900 dark:text-zinc-400">
        <p className="font-semibold text-slate-700 dark:text-zinc-300">事实边界</p>
        <p>{dimension.fact_boundary}</p>
      </div>

      <details className="mt-2 rounded-xl border border-slate-200 dark:border-zinc-800">
        <summary className="cursor-pointer px-2.5 py-2 text-[11px] font-semibold text-slate-700 dark:text-zinc-300">
          查看评分依据（{dimension.evidence.length} 条）
        </summary>
        <div className="space-y-2 border-t border-slate-200 p-2.5 dark:border-zinc-800">
          {dimension.evidence.length ? (
            dimension.evidence.map((item, index) => (
              <div
                key={`${item.source_type}-${item.source_id ?? index}-${index}`}
                className="rounded-lg bg-slate-50 p-2 text-[10px] leading-5 dark:bg-zinc-900"
              >
                <div className="flex flex-wrap items-center gap-1.5">
                  <ClassificationBadge classification={item.classification} />
                  <span className="font-semibold">{item.label}</span>
                </div>
                <p className="mt-1 text-slate-500 dark:text-zinc-400">
                  信息范围：{item.information_scope}
                </p>
                <p className="text-slate-500 dark:text-zinc-400">依据：{item.basis}</p>
              </div>
            ))
          ) : (
            <p className="text-[10px] text-slate-500">当前没有足以评分的保存证据。</p>
          )}
        </div>
      </details>
    </article>
  );
}
function TaskActions({
  task,
  busy,
  onUpdate,
}: {
  task: ReproductionImprovementTask;
  busy: boolean;
  onUpdate: (
    task: ReproductionImprovementTask,
    status: "accepted" | "skipped" | "completed",
  ) => void;
}) {
  if (task.status === "skipped" || task.status === "completed") return null;
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {task.status === "pending" ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => onUpdate(task, "accepted")}
          className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-2.5 py-1.5 text-[10px] font-bold text-white disabled:opacity-50"
        >
          <Check className="h-3.5 w-3.5" /> 接受任务
        </button>
      ) : (
        <button
          type="button"
          disabled={busy}
          onClick={() => onUpdate(task, "completed")}
          className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-2.5 py-1.5 text-[10px] font-bold text-white disabled:opacity-50"
        >
          <CheckCircle2 className="h-3.5 w-3.5" /> 标记为已完成
        </button>
      )}
      <button
        type="button"
        disabled={busy}
        onClick={() => onUpdate(task, "skipped")}
        className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[10px] font-semibold text-slate-600 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300"
      >
        <SkipForward className="h-3.5 w-3.5" /> 跳过
      </button>
    </div>
  );
}

export function ReproductionEvaluationPanel({ conversationId }: { conversationId: string }) {
  const [evaluations, setEvaluations] = useState<ReproductionProjectEvaluation[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void listReproductionEvaluations(conversationId)
      .then((items) => {
        if (active) setEvaluations(items);
      })
      .catch((value: unknown) => {
        if (active) {
          setError(value instanceof Error ? value.message : "无法恢复复现项目评估。请重试。");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [conversationId]);

  async function createEvaluation() {
    setCreating(true);
    setError(null);
    try {
      const created = await createReproductionEvaluation(conversationId);
      setEvaluations((current) => [created, ...current]);
    } catch (value) {
      setError(value instanceof Error ? value.message : "运行五维项目评估失败。请重试。");
    } finally {
      setCreating(false);
    }
  }

  async function updateTask(
    task: ReproductionImprovementTask,
    status: "accepted" | "skipped" | "completed",
  ) {
    setBusyTaskId(task.task_id);
    setError(null);
    try {
      const updated = await updateReproductionImprovementTask(task.task_id, status);
      setEvaluations((current) =>
        current.map((evaluation) => ({
          ...evaluation,
          improvement_tasks: evaluation.improvement_tasks.map((item) =>
            item.task_id === updated.task_id ? updated : item,
          ),
        })),
      );
    } catch (value) {
      setError(value instanceof Error ? value.message : "更新改进任务失败。请重试。");
    } finally {
      setBusyTaskId(null);
    }
  }

  const latest = evaluations[0] ?? null;
  const progress = latest?.score_summary.scored_maximum
    ? Math.round(
        (latest.score_summary.earned_score / latest.score_summary.scored_maximum) * 100,
      )
    : 0;

  return (
    <section className="rounded-2xl border border-indigo-200 bg-white p-4 shadow-sm dark:border-indigo-900/70 dark:bg-zinc-900/80">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="rounded-xl bg-indigo-100 p-2 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300">
            <ClipboardList className="h-4 w-4" />
          </span>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-indigo-700 dark:text-indigo-300">
              Reproduction evaluation
            </p>
            <h2 className="mt-1 text-sm font-bold">五维复现项目评估</h2>
          </div>
        </div>
        <button
          type="button"
          disabled={creating}
          onClick={() => void createEvaluation()}
          className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-3 py-2 text-xs font-bold text-white disabled:opacity-50"
        >
          {creating ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : latest ? (
            <RotateCcw className="h-3.5 w-3.5" />
          ) : (
            <ShieldCheck className="h-3.5 w-3.5" />
          )}
          {latest ? "基于当前记录重新评估" : "我确认运行五维项目评估"}
        </button>
      </div>

      <p className="mt-3 text-[11px] leading-5 text-slate-600 dark:text-zinc-400">
        只读取当前会话已经保存的画像、论文选择、复现 Pipeline 和实验文本。不会联网、读取全文、执行代码或修改论文；评分只表示记录与证据完整度。
      </p>
      {error && (
        <p role="alert" className="mt-3 rounded-xl bg-rose-50 p-2 text-xs text-rose-700 dark:bg-rose-950/30 dark:text-rose-300">
          {error}
        </p>
      )}
      {loading && (
        <p className="mt-3 flex items-center gap-2 text-xs text-slate-500">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> 正在恢复已保存评估…
        </p>
      )}

      {!loading && !latest && (
        <div className="mt-4 rounded-xl border border-dashed border-indigo-200 p-4 text-center text-xs text-slate-500 dark:border-indigo-900 dark:text-zinc-400">
          尚未运行评估。证据缺失的维度会显示“不可评估”，不会被猜测或强行打零分。
        </div>
      )}

      {latest && (
        <div className="mt-4 space-y-4">
          <div className="rounded-2xl bg-slate-950 p-4 text-white dark:bg-zinc-950">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-[10px] uppercase tracking-[0.18em] text-slate-400">
                  Evidence completeness
                </p>
                <p className="mt-1 text-2xl font-black">
                  {latest.score_summary.earned_score}
                  <span className="text-sm font-medium text-slate-400">
                    /{latest.score_summary.scored_maximum || "—"}
                  </span>
                </p>
              </div>
              <p className="max-w-xl text-[10px] leading-5 text-slate-300">
                {latest.score_summary.display}
              </p>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-800">
              <div
                className="h-full rounded-full bg-gradient-to-r from-sky-400 to-indigo-500"
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="mt-3 flex flex-wrap gap-2 text-[10px] text-slate-300">
              <span>已选论文 {latest.selected_paper_count}</span>
              <span>·</span>
              <span>实验记录 {latest.experiment_record_count}</span>
              <span>·</span>
              <span>
                Pipeline：{latest.pipeline_contract_status === "available" ? "已接入" : "尚未接入"}
              </span>
            </div>
          </div>

          {latest.pipeline_contract_status === "unavailable" && (
            <div className="flex gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-[11px] leading-5 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-200">
              <FileWarning className="mt-0.5 h-4 w-4 shrink-0" />
              <p>
                A 的 ReproductionPipeline 稳定合同尚未接入，因此“复现路径与可执行性”保持不可评估。B 模块不会用普通研究计划冒充 Pipeline。
              </p>
            </div>
          )}

          <div className="grid gap-3 lg:grid-cols-2">
            {latest.dimensions.map((dimension) => (
              <DimensionCard key={dimension.dimension} dimension={dimension} />
            ))}
          </div>

          <section className="rounded-2xl border border-indigo-200 p-3 dark:border-indigo-900/70">
            <h3 className="text-xs font-bold">复现改进任务</h3>
            <p className="mt-1 text-[10px] leading-5 text-slate-500 dark:text-zinc-400">
              任务来自本次评估的证据缺口；系统不会自动执行，也不会自动认定任务已经完成。
            </p>
            {latest.improvement_tasks.length ? (
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {latest.improvement_tasks.map((task) => (
                  <article
                    key={task.task_id}
                    className="rounded-xl bg-slate-50 p-3 dark:bg-zinc-950/60"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-[11px] font-bold">{task.title}</p>
                      <span className="shrink-0 rounded-full bg-white px-2 py-1 text-[9px] font-semibold text-slate-600 dark:bg-zinc-900 dark:text-zinc-300">
                        {taskStatusCopy[task.status]}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] leading-5 text-slate-600 dark:text-zinc-400">
                      {task.description}
                    </p>
                    <TaskActions
                      task={task}
                      busy={busyTaskId === task.task_id}
                      onUpdate={(item, status) => void updateTask(item, status)}
                    />
                  </article>
                ))}
              </div>
            ) : (
              <p className="mt-3 text-[11px] text-slate-500">本次评估没有生成改进任务。</p>
            )}
          </section>

          <p className="rounded-xl bg-slate-50 p-3 text-[10px] leading-5 text-slate-500 dark:bg-zinc-950/60 dark:text-zinc-400">
            {latest.boundary_note}
          </p>
        </div>
      )}
    </section>
  );
}
