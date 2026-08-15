"use client";

/**
 * Companion-exercise view (配套练习题) — the third view of the unified learning
 * result area. The parent holds all quiz state (params / response / loading /
 * error / exporting) so the view survives tab switches; this component stays
 * presentational except for the transient answer set and grading state.
 *
 * Answering submits every answered item to ``POST /quiz/grade``: ``single`` is
 * judged deterministically server-side against the archived answer
 * (``graded_by=rules``), ``fill_blank`` / ``short_answer`` through the LLM
 * (tolerating equivalent math / rewording) with a Chinese analysis comment. In
 * offline mode the backend degrades honestly — exact match for fill blanks
 * (labeled 离线 Mock 判分), and short answers come back ``graded=false``
 * prompting self-grading — never a faked verdict. Every scored answer is
 * persisted as a ``quiz_attempts`` row keyed by the client-minted
 * ``attempt_id``, aggregated into the learning portrait via ``profile_id``.
 */

import { useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  Eraser,
  FileQuestion,
  FileText,
  Loader2,
  RefreshCw,
  Sparkles,
  UserRound,
  XCircle,
} from "lucide-react";
import katex from "katex";
import type {
  QuizDifficulty,
  QuizGenerateParams,
  QuizGenerateResponse,
  QuizQuestion,
  QuizQuestionGradeResult,
  QuizQuestionType,
} from "@/lib/api/quiz";
import { gradeQuizAnswers } from "@/lib/api/learning";
import { markSourceRef } from "@/lib/api/profile";
import { getOrCreateLearnerId, newUuidV4 } from "@/lib/learner";
import { MarkButton } from "@/components/learning/MarkButton";

// ── Inline LaTeX ($...$) ───────────────────────────────────────────────────────

interface LatexSegment {
  math: boolean;
  text?: string;
  html?: string;
}

/**
 * Split text on ``$...$`` pairs and render each math segment with KaTeX (the
 * same library the PPT ``SlideRenderer`` uses). Unbalanced or unparseable
 * segments stay as literal text — the docx exporter converts the same syntax
 * to native Word equations.
 */
function splitLatex(text: string): LatexSegment[] {
  const parts = text.split(/(\$[^$]+\$)/g);
  return parts.map((part) => {
    const match = part.match(/^\$([^$]+)\$$/);
    if (match) {
      let html = part;
      try {
        html = katex.renderToString(match[1], {
          throwOnError: false,
          strict: false,
          displayMode: false,
        });
      } catch {
        // keep the raw $...$ text on a KaTeX failure
      }
      return { math: true, html };
    }
    return { math: false, text: part };
  });
}

function InlineLatex({ text }: { text: string }) {
  const segments = useMemo(() => splitLatex(text), [text]);
  return (
    <span>
      {segments.map((segment, index) =>
        segment.math ? (
          <span
            key={index}
            dangerouslySetInnerHTML={{ __html: segment.html ?? "" }}
          />
        ) : (
          <span key={index}>{segment.text}</span>
        ),
      )}
    </span>
  );
}

// ── Type / difficulty labels ───────────────────────────────────────────────────

const TYPE_LABELS: Record<QuizQuestionType, string> = {
  single: "单选题",
  fill_blank: "填空题",
  short_answer: "简答题",
};

const TYPE_BADGE_CLASSES: Record<QuizQuestionType, string> = {
  single: "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300",
  fill_blank: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
  short_answer: "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300",
};

const DIFFICULTIES: { value: QuizDifficulty; label: string }[] = [
  { value: "easy", label: "易" },
  { value: "medium", label: "中" },
  { value: "hard", label: "难" },
];

const ALL_TYPES: QuizQuestionType[] = ["single", "fill_blank", "short_answer"];

/** Count ``______`` blanks inside a fill-blank stem (backend convention). */
function countBlanks(question: string, questionItem: QuizQuestion): number {
  const fromStem = (question.match(/_{4,}/g) ?? []).length;
  if (fromStem > 0) return fromStem;
  return questionItem.answer?.length ?? 0;
}

// ── Skeleton ───────────────────────────────────────────────────────────────────

function SkeletonLine({ width = "w-full" }: { width?: string }) {
  return (
    <div
      className={`h-4 ${width} animate-pulse rounded-md bg-slate-100 dark:bg-zinc-800`}
    />
  );
}

// ── Props ──────────────────────────────────────────────────────────────────────

interface QuizViewProps {
  knowledgePoint: string;
  sessionId: string;
  params: QuizGenerateParams;
  onParamsChange: (params: QuizGenerateParams) => void;
  response: QuizGenerateResponse | null;
  loading: boolean;
  error: string | null;
  onGenerate: () => void;
  onExport: (withAnswer: boolean) => void;
  exporting?: boolean;
}

// ── Component ──────────────────────────────────────────────────────────────────

export function QuizView({
  knowledgePoint,
  sessionId,
  params,
  onParamsChange,
  response,
  loading,
  error,
  onGenerate,
  onExport,
  exporting,
}: QuizViewProps) {
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [submitted, setSubmitted] = useState(false);
  const [grading, setGrading] = useState(false);
  const [gradeResults, setGradeResults] = useState<
    Record<string, QuizQuestionGradeResult>
  >({});
  const [gradeError, setGradeError] = useState<string | null>(null);
  const [withAnswer, setWithAnswer] = useState(false);
  const [showProfile, setShowProfile] = useState(false);

  // A fresh quiz resets answer / grading state via the parent's ``key`` on this
  // component (remount), so no ``setState``-in-effect is needed here.

  const questions = response?.questions ?? [];
  const controlsDisabled = loading;

  function setQuestionTypes(types: QuizQuestionType[]) {
    onParamsChange({
      ...params,
      question_types: types.length === ALL_TYPES.length || types.length === 0 ? null : types,
    });
  }

  function setAnswer(questionId: string, values: string[]) {
    setAnswers((current) => ({ ...current, [questionId]: values }));
  }

  function isCorrect(question: QuizQuestion): boolean {
    const given = answers[question.id] ?? [];
    if (question.type === "single") {
      return given[0] !== undefined && given[0] === question.answer?.[0];
    }
    if (question.type === "fill_blank") {
      const expected = question.answer ?? [];
      if (given.length !== expected.length) return false;
      return expected.every((want, index) => (given[index] ?? "").trim() === (want ?? "").trim());
    }
    // short_answer is graded by the LLM (or self-graded offline).
    return false;
  }

  async function submitAnswers() {
    if (!response) return;
    const answered = response.questions
      .filter((q) => (answers[q.id] ?? []).some((value) => value.trim() !== ""));
    if (answered.length === 0) {
      setGradeError("尚未作答任何题目，请先作答后提交判分。");
      return;
    }
    setGrading(true);
    setGradeError(null);
    try {
      // Fresh client-minted idempotency key per submission: a network retry of
      // the same request re-uses it so the server upserts, never double-inserts.
      const attemptId = newUuidV4();
      const grade = await gradeQuizAnswers({
        session_id: sessionId,
        quiz_id: response.quiz_id,
        attempt_id: attemptId,
        profile_id: getOrCreateLearnerId(),
        student_answers: answered.map((q) => ({
          question_id: q.id,
          answer: answers[q.id] ?? [],
        })),
      });
      const byQuestion: Record<string, QuizQuestionGradeResult> = {};
      for (const result of grade.results) byQuestion[result.question_id] = result;
      setGradeResults(byQuestion);
      setSubmitted(true);
    } catch (err) {
      setGradeError(err instanceof Error ? err.message : String(err));
    } finally {
      setGrading(false);
    }
  }

  function resetAnswers() {
    setAnswers({});
    setSubmitted(false);
    setGradeResults({});
    setGradeError(null);
  }

  // Auto-graded score: every server-graded result first (single → rules,
  // fill_blank → mock/model, short_answer → model), with a local exact-match
  // fallback only where no server result exists. Ungraded short answers stay
  // out of the auto total so they never drag the objective score down.
  const earned = questions.reduce((sum, q) => {
    const grade = gradeResults[q.id];
    if (grade?.graded) return sum + grade.score;
    if (q.type === "single") return sum + (isCorrect(q) ? q.points : 0);
    if (q.type === "fill_blank") return sum + (isCorrect(q) ? q.points : 0);
    return sum;
  }, 0);
  const autoTotal = questions.reduce((sum, q) => {
    if (q.type === "single") return sum + q.points;
    const grade = gradeResults[q.id];
    if (grade?.graded) return sum + grade.max_score;
    if (q.type === "fill_blank") return sum + q.points;
    return sum;
  }, 0);
  const selfCount = questions.filter(
    (q) => q.type === "short_answer" && !gradeResults[q.id]?.graded,
  ).length;

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-7 shadow-xs dark:border-zinc-800 dark:bg-zinc-900/90 transition-all">
      {/* Header + generation controls */}
      <div className="mb-6 border-b border-slate-100 pb-5 dark:border-zinc-800/70">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-md bg-violet-100/80 px-2 py-0.5 text-[11px] font-semibold tracking-wider text-violet-700 dark:bg-violet-950/40 dark:text-violet-300">
                <Sparkles className="h-3 w-3" strokeWidth={1.5} />
                配套练习题 · 组卷
              </span>
            </div>
            <h3 className="mt-2 truncate text-xl font-bold tracking-tight text-slate-900 dark:text-zinc-100">
              {knowledgePoint}
            </h3>
          </div>
          <button
            type="button"
            onClick={onGenerate}
            disabled={controlsDisabled}
            className="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-gradient-to-r from-violet-600 to-purple-600 px-4 py-2.5 text-xs font-semibold text-white shadow-md shadow-violet-500/20 transition hover:from-violet-500 hover:to-purple-500 focus:ring-2 focus:ring-violet-400/40 focus:outline-none active:scale-98 disabled:cursor-not-allowed disabled:opacity-50 dark:from-violet-500 dark:to-purple-500 dark:shadow-violet-950/40"
          >
            {loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />
            ) : response ? (
              <RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} />
            ) : (
              <FileQuestion className="h-3.5 w-3.5" strokeWidth={1.5} />
            )}
            {loading ? "正在生成练习题…" : response ? "重新组卷" : "生成组卷"}
          </button>
        </div>

        {/* Generation option bar */}
        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-xs font-medium text-slate-600 dark:text-zinc-400">
            题目数量
            <select
              value={params.question_count ?? 5}
              disabled={controlsDisabled}
              onChange={(event) =>
                onParamsChange({ ...params, question_count: Number(event.target.value) })
              }
              className="cursor-pointer rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 outline-none focus:border-violet-400 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
            >
              {Array.from({ length: 30 }, (_, index) => index + 1).map((count) => (
                <option key={count} value={count}>
                  {count} 题
                </option>
              ))}
            </select>
          </label>

          <div className="flex items-center gap-2 text-xs font-medium text-slate-600 dark:text-zinc-400">
            难度
            <div className="inline-flex rounded-lg bg-slate-100/90 p-1 dark:bg-zinc-800/80">
              {DIFFICULTIES.map((difficulty) => {
                const active = (params.difficulty ?? "medium") === difficulty.value;
                return (
                  <button
                    key={difficulty.value}
                    type="button"
                    disabled={controlsDisabled}
                    onClick={() => onParamsChange({ ...params, difficulty: difficulty.value })}
                    className={`cursor-pointer rounded-md px-2.5 py-1 text-[11px] font-medium transition-all ${
                      active
                        ? "bg-white text-slate-900 shadow-2xs dark:bg-zinc-900 dark:text-zinc-100"
                        : "text-slate-500 hover:text-slate-700 dark:text-zinc-400 dark:hover:text-zinc-200"
                    } disabled:cursor-not-allowed disabled:opacity-50`}
                  >
                    {difficulty.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-slate-600 dark:text-zinc-400">
            题型
            {ALL_TYPES.map((type) => {
              const selected = params.question_types === undefined || (params.question_types ?? null)?.includes(type);
              return (
                <button
                  key={type}
                  type="button"
                  disabled={controlsDisabled}
                  onClick={() => {
                    const current = params.question_types ?? null;
                    const next = current === null ? ALL_TYPES.filter((t) => t !== type) : current.includes(type)
                      ? current.filter((t) => t !== type)
                      : [...current, type];
                    setQuestionTypes(next);
                  }}
                  aria-pressed={selected}
                  className={`cursor-pointer rounded-lg border px-2.5 py-1.5 text-[11px] font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${
                    selected
                      ? "border-violet-300 bg-violet-50 text-violet-700 dark:border-violet-700 dark:bg-violet-950/40 dark:text-violet-300"
                      : "border-slate-200 bg-white text-slate-500 hover:border-slate-300 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400"
                  }`}
                >
                  {TYPE_LABELS[type]}
                </button>
              );
            })}
            <span className="text-[11px] text-slate-400 dark:text-zinc-500">
              {params.question_types === undefined || params.question_types === null ? "（默认全部）" : ""}
            </span>
          </div>
        </div>

        {/* 学情画像（可选）— 随组卷请求写入，LLM 据此适配难度与内容 */}
        <div className="mt-3 rounded-xl border border-dashed border-slate-200 bg-slate-50/60 dark:border-zinc-700 dark:bg-zinc-800/40">
          <button
            type="button"
            onClick={() => setShowProfile((current) => !current)}
            className="flex w-full cursor-pointer items-center gap-2 px-3 py-2.5 text-left text-xs font-medium text-slate-600 dark:text-zinc-400"
          >
            <UserRound className="h-3.5 w-3.5 text-violet-500 dark:text-violet-400" strokeWidth={1.5} />
            学情画像（可选）
            {params.student_profile?.trim() ? (
              <span className="rounded-md bg-violet-100 px-1.5 py-0.5 text-[10px] font-semibold text-violet-700 dark:bg-violet-950/40 dark:text-violet-300">
                已填写
              </span>
            ) : (
              <span className="text-[10px] text-slate-400 dark:text-zinc-500">未填写</span>
            )}
            <span className="ml-auto text-[10px] text-slate-400 dark:text-zinc-500">
              {showProfile ? "收起" : "展开"}
            </span>
          </button>
          {showProfile && (
            <div className="px-3 pb-3">
              <textarea
                value={params.student_profile ?? ""}
                disabled={controlsDisabled}
                rows={3}
                placeholder="例如：已掌握集合列举法，但对交集/并集运算和证明题薄弱；希望多出基础题，难度适中。"
                onChange={(event) =>
                  onParamsChange({
                    ...params,
                    student_profile: event.target.value.trim() ? event.target.value : null,
                  })
                }
                className="w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs leading-5 text-slate-700 outline-none placeholder:text-slate-400 focus:border-violet-400 focus:ring-4 focus:ring-violet-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:focus:ring-violet-950/40"
              />
              <p className="mt-1 text-[10px] text-slate-400 dark:text-zinc-500">
                填写后，组卷时会把你的薄弱点与掌握情况交给模型，用于调整题目难度与内容。
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Loading */}
      {loading && (
        <div className="space-y-4">
          <SkeletonLine width="w-2/5" />
          <SkeletonLine />
          <SkeletonLine width="w-4/5" />
          <SkeletonLine width="w-3/5" />
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50/70 p-4 text-xs text-red-800 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-300">
          <AlertCircle className="h-4 w-4 shrink-0 text-red-600 dark:text-red-400" strokeWidth={1.5} />
          <div>
            <p className="font-semibold">练习题生成异常</p>
            <p className="mt-0.5 text-slate-600 dark:text-red-200/80">{error}</p>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!response && !loading && !error && (
        <div className="flex flex-col items-center justify-center py-14 text-center">
          <FileQuestion className="mb-3 h-10 w-10 text-slate-300 dark:text-zinc-600" strokeWidth={1.5} />
          <p className="text-xs font-medium text-slate-500 dark:text-zinc-400">
            尚未生成练习题。点击右上角「生成组卷」，将基于当前知识点自动编制一套配套练习。
          </p>
        </div>
      )}

      {/* Generated quiz */}
      {response && !loading && (
        <div>
          {/* Quiz meta + export bar */}
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2 text-[11px]">
              <span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[11px] text-slate-600 dark:bg-zinc-800 dark:text-zinc-400">
                {response.questions.length} 题
              </span>
              <span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[11px] text-slate-600 dark:bg-zinc-800 dark:text-zinc-400">
                满分 {response.total_points} 分
              </span>
              <span className="rounded-md bg-violet-50 px-2 py-0.5 font-semibold text-violet-700 dark:bg-violet-950/40 dark:text-violet-300">
                {response.generation_mode === "model"
                  ? `模型生成 · ${response.provider_name ?? "provider"}`
                  : response.generation_mode === "rules_fallback"
                    ? "模型失败 · 规则降级"
                    : "离线规则生成"}
              </span>
              {response.audit && (
                <span className="rounded-md bg-slate-100 px-2 py-0.5 font-medium text-slate-500 dark:bg-zinc-800 dark:text-zinc-400">
                  质检 {response.audit.verdict === "pass" ? "通过" : "已调整"}
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex cursor-pointer items-center gap-1.5 text-xs font-medium text-slate-600 dark:text-zinc-400">
                <input
                  type="checkbox"
                  checked={withAnswer}
                  onChange={(event) => setWithAnswer(event.target.checked)}
                  className="h-3.5 w-3.5 cursor-pointer accent-violet-600"
                />
                含答案
              </label>
              <button
                type="button"
                onClick={() => onExport(withAnswer)}
                disabled={exporting}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
              >
                {exporting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />
                ) : (
                  <Download className="h-3.5 w-3.5" strokeWidth={1.5} />
                )}
                导出 Word 试卷 (.docx)
              </button>
            </div>
          </div>

          {/* Questions */}
          <ol className="space-y-5">
            {response.questions.map((question, index) => {
              const grade = gradeResults[question.id];
              return (
                <li
                  key={question.id}
                  className="rounded-2xl border border-slate-200/70 bg-slate-50/50 p-5 dark:border-zinc-800 dark:bg-zinc-800/30"
                >
                  <div className="mb-3 flex items-start justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-2.5">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-[11px] font-bold text-white dark:bg-zinc-100 dark:text-zinc-900">
                        {index + 1}
                      </span>
                      <span className={`shrink-0 rounded-md px-2 py-0.5 text-[10px] font-semibold ${TYPE_BADGE_CLASSES[question.type]}`}>
                        {TYPE_LABELS[question.type]}
                      </span>
                      {submitted && question.type === "single" && (() => {
                        // Server-side rules grade is authoritative; fall back to
                        // the local exact match only if the result is missing.
                        const server = grade?.graded ? grade : null;
                        const correct = server ? server.is_correct : isCorrect(question);
                        const score = server ? server.score : correct ? question.points : 0;
                        return (
                          <span className={`flex shrink-0 items-center gap-1 text-[11px] font-semibold ${correct ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
                            {correct ? (
                              <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={1.5} />
                            ) : (
                              <XCircle className="h-3.5 w-3.5" strokeWidth={1.5} />
                            )}
                            {correct ? `正确 · ${score}/${question.points} 分` : `错误 · ${score}/${question.points} 分`}
                          </span>
                        );
                      })()}
                      {submitted && question.type !== "single" && grade?.graded && (
                        <>
                          <span className={`flex shrink-0 items-center gap-1 text-[11px] font-semibold ${grade.is_correct ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
                            {grade.is_correct ? (
                              <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={1.5} />
                            ) : (
                              <XCircle className="h-3.5 w-3.5" strokeWidth={1.5} />
                            )}
                            {grade.score}/{grade.max_score} 分
                          </span>
                          <span className={`shrink-0 rounded-md px-2 py-0.5 text-[10px] font-semibold ${grade.is_mock ? "bg-slate-100 text-slate-600 dark:bg-zinc-800 dark:text-zinc-400" : "bg-violet-50 text-violet-700 dark:bg-violet-950/40 dark:text-violet-300"}`}>
                            {grade.is_mock ? "离线 Mock 判分" : "LLM 智能判分"}
                          </span>
                        </>
                      )}
                      {submitted && question.type !== "single" && grade && !grade.graded && (
                        <span className="shrink-0 rounded-md bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                          离线模式，请对照参考答案自评
                        </span>
                      )}
                      {submitted && question.type === "fill_blank" && !grade && (
                        isCorrect(question) ? (
                          <span className="flex shrink-0 items-center gap-1 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">
                            <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={1.5} />
                            正确 · {question.points}/{question.points} 分
                          </span>
                        ) : (
                          <span className="flex shrink-0 items-center gap-1 text-[11px] font-semibold text-rose-600 dark:text-rose-400">
                            <XCircle className="h-3.5 w-3.5" strokeWidth={1.5} />
                            错误 · 0/{question.points} 分
                          </span>
                        )
                      )}
                      {submitted && question.type === "short_answer" && !grade && (
                        <span className="shrink-0 rounded-md bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                          请对照参考答案自评
                        </span>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <MarkButton
                        knowledgePoint={knowledgePoint}
                        sourceType="quiz_question"
                        sourceRef={markSourceRef(
                          "quiz_question",
                          knowledgePoint,
                          question.id,
                        )}
                      />
                      <span className="font-mono text-[11px] text-slate-400 dark:text-zinc-500">
                        {question.points} 分
                      </span>
                    </div>
                  </div>

                  <p className="mb-3 text-sm leading-relaxed whitespace-pre-wrap text-slate-800 dark:text-zinc-200">
                    <InlineLatex text={question.question} />
                  </p>

                  {question.source && (
                    <p className="mb-3 flex items-center gap-1 text-[10px] text-slate-400 dark:text-zinc-500">
                      <FileText className="h-3 w-3" strokeWidth={1.5} />
                      来源：{question.source.label}
                    </p>
                  )}

                  {/* Answer widgets */}
                  {question.type === "single" && question.options && (
                    <div className="space-y-2">
                      {question.options.map((option) => {
                        const selected = (answers[question.id] ?? [])[0] === option.value;
                        const correctValue = question.answer?.[0];
                        const isCorrectOption = option.value === correctValue;
                        const isWrongPick = submitted && selected && !isCorrectOption;
                        const isRevealedCorrect = submitted && isCorrectOption;
                        let rowClass =
                          "border-slate-200 bg-white text-slate-700 hover:border-slate-300 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300";
                        let dotClass =
                          "border-slate-300 text-slate-500 dark:border-zinc-600 dark:text-zinc-400";
                        if (isWrongPick) {
                          rowClass =
                            "border-rose-400 bg-rose-50 text-slate-900 dark:border-rose-600 dark:bg-rose-950/30 dark:text-zinc-100";
                          dotClass = "border-rose-500 bg-rose-600 text-white";
                        } else if (isRevealedCorrect) {
                          rowClass =
                            "border-emerald-400 bg-emerald-50 text-slate-900 dark:border-emerald-600 dark:bg-emerald-950/30 dark:text-zinc-100";
                          dotClass = "border-emerald-500 bg-emerald-600 text-white";
                        } else if (selected) {
                          rowClass =
                            "border-violet-400 bg-violet-50 text-slate-900 dark:border-violet-600 dark:bg-violet-950/30 dark:text-zinc-100";
                          dotClass = "border-violet-500 bg-violet-600 text-white";
                        }
                        return (
                          <button
                            key={option.value}
                            type="button"
                            disabled={submitted || grading}
                            onClick={() => setAnswer(question.id, [option.value])}
                            className={`flex w-full cursor-pointer items-center gap-3 rounded-xl border px-3.5 py-2.5 text-left text-sm transition disabled:cursor-not-allowed ${rowClass}`}
                          >
                            <span
                              className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-bold ${dotClass}`}
                            >
                              {option.value}
                            </span>
                            <span className="min-w-0 flex-1">
                              <InlineLatex text={option.label} />
                            </span>
                            {isWrongPick && (
                              <XCircle className="h-4 w-4 shrink-0 text-rose-600 dark:text-rose-400" strokeWidth={1.5} />
                            )}
                            {isRevealedCorrect && (
                              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" strokeWidth={1.5} />
                            )}
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {question.type === "fill_blank" && (() => {
                    const blankCount = countBlanks(question.question, question);
                    const values = answers[question.id] ?? [];
                    return (
                      <div className="grid gap-2.5 sm:grid-cols-2">
                        {Array.from({ length: blankCount }, (_, blankIndex) => (
                          <input
                            key={blankIndex}
                            type="text"
                            value={values[blankIndex] ?? ""}
                            disabled={submitted || grading}
                            placeholder={`第 ${blankIndex + 1} 个空`}
                            onChange={(event) => {
                              const next = [...values];
                              next[blankIndex] = event.target.value;
                              setAnswer(question.id, next);
                            }}
                            className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-violet-400 focus:ring-4 focus:ring-violet-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:focus:ring-violet-950/40"
                          />
                        ))}
                      </div>
                    );
                  })()}

                  {question.type === "short_answer" && (
                    <textarea
                      value={(answers[question.id] ?? [])[0] ?? ""}
                      disabled={submitted || grading}
                      rows={3}
                      placeholder="写下你的作答要点…"
                      onChange={(event) => setAnswer(question.id, [event.target.value])}
                      className="w-full resize-y rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm leading-6 text-slate-900 outline-none placeholder:text-slate-400 focus:border-violet-400 focus:ring-4 focus:ring-violet-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:focus:ring-violet-950/40"
                    />
                  )}

                  {/* LLM 评语 card (fill_blank / short_answer) */}
                  {submitted && grade?.graded && grade.comment && (
                    <div className="mt-4 rounded-xl border-l-2 border-violet-400 bg-violet-50/60 p-4 text-xs leading-relaxed text-slate-700 dark:border-violet-600 dark:bg-violet-950/20 dark:text-zinc-300">
                      <p className="mb-1.5 font-semibold text-violet-700 dark:text-violet-300">
                        {grade.is_mock ? "离线判分说明" : "AI 评分解析"}
                      </p>
                      <p className="whitespace-pre-wrap">
                        <InlineLatex text={grade.comment} />
                      </p>
                    </div>
                  )}

                  {/* Standard answer / analysis reveal after submission */}
                  {submitted && question.analysis && (
                    <div className="mt-4 rounded-xl border-l-2 border-violet-400 bg-white p-4 text-xs leading-relaxed text-slate-700 dark:border-violet-600 dark:bg-zinc-900 dark:text-zinc-300">
                      <p className="mb-1.5 font-semibold text-violet-700 dark:text-violet-300">
                        {question.type === "short_answer" ? "参考答案与解析" : "答案解析"}
                      </p>
                      <p className="whitespace-pre-wrap">
                        <InlineLatex text={question.analysis} />
                      </p>
                    </div>
                  )}
                  {submitted && question.type === "short_answer" && !question.analysis && (
                    <p className="mt-4 text-[11px] text-slate-400 dark:text-zinc-500">
                      本题为开放作答，请结合已学内容自行判断要点是否完整。
                    </p>
                  )}
                </li>
              );
            })}
          </ol>

          {/* Grading failure banner */}
          {gradeError && (
            <div className="mt-4 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50/70 p-4 text-xs text-red-800 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-300">
              <AlertCircle className="h-4 w-4 shrink-0 text-red-600 dark:text-red-400" strokeWidth={1.5} />
              <div>
                <p className="font-semibold">智能判分失败</p>
                <p className="mt-0.5 text-slate-600 dark:text-red-200/80">{gradeError}</p>
              </div>
            </div>
          )}

          {/* Action bar: grading + reset */}
          <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-5 dark:border-zinc-800/70">
            {submitted ? (
              <p className="flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-zinc-200">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" strokeWidth={1.5} />
                自动判分 {earned} / {autoTotal}
                {selfCount > 0 && (
                  <span className="text-xs font-normal text-slate-400 dark:text-zinc-500">
                    · {selfCount} 道简答题请对照参考答案自评
                  </span>
                )}
              </p>
            ) : (
              <p className="text-xs text-slate-400 dark:text-zinc-500">
                提交后：单选本地判分，填空与解答题由大模型判分并给出解析。
              </p>
            )}
            <div className="flex gap-2">
              {submitted && (
                <button
                  type="button"
                  onClick={resetAnswers}
                  className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
                >
                  <Eraser className="h-3.5 w-3.5" strokeWidth={1.5} />
                  重新作答
                </button>
              )}
              <button
                type="button"
                onClick={() => void submitAnswers()}
                disabled={submitted || grading}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-1.5 text-xs font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
              >
                {submitted ? (
                  <>
                    <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={1.5} />
                    已对照答案
                  </>
                ) : grading ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />
                    正在批改…
                  </>
                ) : (
                  "提交并对照答案"
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
