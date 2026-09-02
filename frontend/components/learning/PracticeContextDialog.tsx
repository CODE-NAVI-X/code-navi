"use client";

/**
 * Pre-jump review for the §3.1 practice-context.v1 hand-off (查看/修改/清除).
 *
 * Deliberately minimal: the student can read what will be handed over, edit
 * the goal wording and notes summary (and drop knowledge points), or clear the
 * context entirely and jump into free practice. The structured fields stay
 * server-shaped — no extra form fields beyond the contract's four.
 */

import { useState } from "react";
import { Eraser, Sparkles } from "lucide-react";
import {
  PRACTICE_CONTEXT_LIMITS,
  type PracticeContextV1,
} from "@/lib/practice-context";

interface PracticeContextDialogProps {
  context: PracticeContextV1;
  busy?: boolean;
  error?: string | null;
  onConfirm: (context: PracticeContextV1) => void;
  onClear: () => void;
  onCancel: () => void;
}

function formatMastery(mastery: number | null): string {
  if (mastery === null) return "画像暂无掌握度";
  return `掌握度 ${Math.round(mastery * 100)}%`;
}

export function PracticeContextDialog({
  context,
  busy = false,
  error = null,
  onConfirm,
  onClear,
  onCancel,
}: PracticeContextDialogProps) {
  const [draft, setDraft] = useState<PracticeContextV1>(context);

  function removeKnowledgePoint(index: number) {
    setDraft((current) => ({
      ...current,
      knowledge_points: current.knowledge_points.filter(
        (_, position) => position !== index,
      ),
    }));
  }

  const canConfirm =
    draft.objective.trim().length > 0 && draft.knowledge_points.length >= 1;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="确认带入动手实践的上下文"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4"
    >
      <div className="app-card max-h-[85vh] w-full max-w-xl overflow-y-auto rounded-2xl p-5">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-slate-500" strokeWidth={1.5} />
          <h2 className="text-lg font-bold text-slate-950 dark:text-zinc-50">
            带上下文进入动手实践
          </h2>
        </div>
        <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-zinc-400">
          跳转前请确认将交接的内容：可查看、修改，也可以清除后自由练习。正文仅经服务端提交，URL 不携带。
        </p>

        <dl className="mt-4 space-y-3 text-sm">
          <div className="rounded-xl bg-slate-50 p-3 dark:bg-zinc-950/60">
            <dt className="text-xs font-semibold text-slate-700 dark:text-zinc-200">
              来源学习会话
            </dt>
            <dd className="mt-1 break-all font-mono text-xs text-slate-500 dark:text-zinc-400">
              {draft.source_session_id}
            </dd>
          </div>
          <div className="rounded-xl bg-slate-50 p-3 dark:bg-zinc-950/60">
            <dt className="text-xs font-semibold text-slate-700 dark:text-zinc-200">
              知识点（{draft.knowledge_points.length}/{PRACTICE_CONTEXT_LIMITS.knowledgePointsMax}）
            </dt>
            <dd className="mt-2 space-y-2">
              {draft.knowledge_points.map((point, index) => (
                <label
                  key={`${point.source_ref}-${index}`}
                  className="flex items-center gap-2 text-xs text-slate-700 dark:text-zinc-200"
                >
                  <input
                    type="checkbox"
                    checked
                    onChange={() => removeKnowledgePoint(index)}
                    className="h-4 w-4 accent-slate-900 dark:accent-zinc-100"
                    aria-label={`取消带入知识点 ${point.name}`}
                  />
                  <span className="min-w-0 flex-1 truncate">{point.name}</span>
                  <span className="flex-none text-slate-500 dark:text-zinc-400">
                    {formatMastery(point.mastery)}
                  </span>
                </label>
              ))}
            </dd>
          </div>
          <div className="rounded-xl bg-slate-50 p-3 dark:bg-zinc-950/60">
            <dt>
              <label
                htmlFor="practice-context-objective"
                className="text-xs font-semibold text-slate-700 dark:text-zinc-200"
              >
                学习目标（原文）
              </label>
            </dt>
            <dd>
              <textarea
                id="practice-context-objective"
                value={draft.objective}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    objective: event.target.value.slice(
                      0,
                      PRACTICE_CONTEXT_LIMITS.objective,
                    ),
                  }))
                }
                rows={2}
                className="app-input mt-2 min-h-16 w-full resize-y rounded-xl p-2.5 text-xs leading-5"
              />
            </dd>
          </div>
          <div className="rounded-xl bg-slate-50 p-3 dark:bg-zinc-950/60">
            <dt>
              <label
                htmlFor="practice-context-notes"
                className="text-xs font-semibold text-slate-700 dark:text-zinc-200"
              >
                勾选的笔记摘要（可清空）
              </label>
            </dt>
            <dd>
              <textarea
                id="practice-context-notes"
                value={draft.notes_summary ?? ""}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    notes_summary:
                      event.target.value.slice(0, PRACTICE_CONTEXT_LIMITS.notesSummary) || null,
                  }))
                }
                rows={2}
                placeholder="未勾选笔记时留空"
                className="app-input mt-2 min-h-16 w-full resize-y rounded-xl p-2.5 text-xs leading-5"
              />
            </dd>
          </div>
        </dl>

        {error ? (
          <p role="alert" className="mt-3 text-xs text-red-600">
            {error}
          </p>
        ) : null}

        <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="app-button-secondary rounded-xl px-4 py-2 text-xs font-semibold transition hover:bg-slate-50 dark:hover:bg-zinc-800"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onClear}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-500 transition hover:bg-slate-50 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            <Eraser className="h-3.5 w-3.5" strokeWidth={1.5} />
            清除上下文，自由练习
          </button>
          <button
            type="button"
            onClick={() => onConfirm(draft)}
            disabled={busy || !canConfirm}
            className="app-button-primary rounded-xl px-4 py-2 text-xs font-bold transition hover:bg-slate-800 disabled:opacity-50 dark:hover:bg-zinc-200"
          >
            确认并跳转
          </button>
        </div>
      </div>
    </div>
  );
}
