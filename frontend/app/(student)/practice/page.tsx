"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Loader2,
  Play,
  RotateCcw,
  Save,
  Terminal,
} from "lucide-react";
import {
  CompilerAiFeedback,
  CompilerExecutionResult,
  CompilerRecord,
  CompilerRuntimeStatus,
  evaluatePythonRun,
  executePython,
  fetchCompilerRecords,
  fetchCompilerRuntime,
} from "@/lib/api/compiler";
import { useFlowStore } from "@/lib/store/flow-store";

const DEFAULT_SOURCE = `text = input().strip()

is_palindrome = text == text[::-1]
print("YES" if is_palindrome else "NO")
`;

const DEFAULT_STDIN = "level\n";

function PracticeContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const payload = useFlowStore((s) => s.payload);
  const knowledgeName =
    payload?.masteredKnowledgePoint.name ??
    searchParams.get("knowledge_name") ??
    "DHCP 四阶段报文交互";
  const exerciseIds = payload?.payloadData.exerciseIds ?? [
    "ex_python_string_palindrome",
    "ex_python_input_loop",
  ];

  const [runtime, setRuntime] = useState<CompilerRuntimeStatus | null>(null);
  const [source, setSource] = useState(DEFAULT_SOURCE);
  const [stdin, setStdin] = useState(DEFAULT_STDIN);
  const [enableAi, setEnableAi] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<CompilerExecutionResult | null>(null);
  const [aiFeedback, setAiFeedback] = useState<CompilerAiFeedback | null>(null);
  const [records, setRecords] = useState<CompilerRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [learnerId] = useState(() => getLearnerId());

  useEffect(() => {
    let active = true;
    void fetchCompilerRuntime()
      .then((status) => {
        if (!active) return;
        setRuntime(status);
        setEnableAi(status.ai.status === "ready");
      })
      .catch((runtimeError: Error) => {
        if (active) setError(runtimeError.message);
      });
    void fetchCompilerRecords(learnerId)
      .then((items) => {
        if (active) setRecords(items);
      })
      .catch(() => {
        if (active) setRecords([]);
      });
    return () => {
      active = false;
    };
  }, [learnerId]);

  async function runCode() {
    setRunning(true);
    setError(null);
    setAiFeedback(null);
    try {
      const executed = await executePython({ source, stdin, learnerId, enableAi });
      setResult(executed);
      setAiFeedback(executed.ai);
      void refreshRecords();
      if (executed.ai.evaluationId) {
        const evaluated = await evaluatePythonRun({
          evaluationId: executed.ai.evaluationId,
          learnerId,
        });
        setAiFeedback(evaluated.ai);
        void refreshRecords();
      }
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "代码运行失败。");
    } finally {
      setRunning(false);
    }
  }

  async function refreshRecords() {
    try {
      setRecords(await fetchCompilerRecords(learnerId));
    } catch {
      setRecords([]);
    }
  }

  return (
    <main className="min-h-screen bg-zinc-950 bg-grid-pattern text-zinc-100">
      <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-5 px-4 py-5 sm:px-6 lg:px-8">
        <header className="flex flex-col gap-4 border-b border-zinc-800/80 pb-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-3">
            <button
              type="button"
              onClick={() => router.push("/student/learning")}
              className="inline-flex items-center gap-2 text-xs font-medium text-zinc-400 transition-colors hover:text-zinc-100"
            >
              <ArrowLeft className="h-4 w-4" strokeWidth={1.5} />
              返回知识点学习
            </button>
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-zinc-700/70 bg-zinc-900 text-emerald-300">
                <Terminal className="h-5 w-5" strokeWidth={1.5} />
              </div>
              <div>
                <h1 className="text-xl font-bold tracking-normal text-zinc-50">
                  代码测试练习模块
                </h1>
                <p className="text-xs text-zinc-400">
                  当前知识点：{knowledgeName}
                </p>
              </div>
            </div>
          </div>
          <RuntimeBadge runtime={runtime} error={error} />
        </header>

        <section className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              {exerciseIds.slice(0, 2).map((exerciseId, index) => (
                <div
                  key={exerciseId}
                  className="rounded-2xl border border-zinc-800 bg-zinc-900/70 p-4"
                >
                  <span className="text-[11px] text-zinc-500">
                    推荐题目 {String(index + 1).padStart(2, "0")}
                  </span>
                  <p className="mt-1 font-mono text-xs text-zinc-200">{exerciseId}</p>
                </div>
              ))}
            </div>

            <div className="overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl">
              <div className="flex items-center justify-between border-b border-zinc-800 bg-zinc-900/80 px-4 py-3">
                <div>
                  <p className="text-sm font-semibold text-zinc-100">main.py</p>
                  <p className="text-[11px] text-zinc-500">
                    Python 单文件运行，资源限制由服务端控制
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setSource(DEFAULT_SOURCE)}
                  className="inline-flex items-center gap-2 rounded-xl border border-zinc-700 px-3 py-2 text-xs text-zinc-300 transition-colors hover:border-zinc-500 hover:text-zinc-100"
                >
                  <RotateCcw className="h-3.5 w-3.5" strokeWidth={1.5} />
                  重置
                </button>
              </div>
              <textarea
                value={source}
                onChange={(event) => setSource(event.target.value)}
                spellCheck={false}
                className="min-h-[420px] w-full resize-y bg-zinc-950 p-5 font-mono text-sm leading-6 text-zinc-100 outline-none"
              />
            </div>

            <div className="grid gap-4 md:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
              <div className="rounded-2xl border border-zinc-800 bg-zinc-900/70 p-4">
                <label className="text-xs font-semibold text-zinc-300">
                  标准输入
                </label>
                <textarea
                  value={stdin}
                  onChange={(event) => setStdin(event.target.value)}
                  spellCheck={false}
                  className="mt-3 min-h-32 w-full resize-y rounded-xl border border-zinc-800 bg-zinc-950 p-3 font-mono text-xs text-zinc-100 outline-none focus:border-emerald-500/70"
                />
              </div>
              <ResultPanel result={result} error={error} />
            </div>
          </div>

          <aside className="space-y-4">
            <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold text-zinc-100">运行控制</h2>
                  <p className="mt-1 text-xs text-zinc-500">
                    运行结果不代表题目测试用例判分
                  </p>
                </div>
                <label className="flex items-center gap-2 text-xs text-zinc-300">
                  <input
                    type="checkbox"
                    checked={enableAi}
                    disabled={runtime?.ai.status !== "ready"}
                    onChange={(event) => setEnableAi(event.target.checked)}
                    className="h-4 w-4 accent-emerald-500"
                  />
                  AI 评析
                </label>
              </div>
              <button
                type="button"
                disabled={running || !runtime?.ready}
                onClick={() => void runCode()}
                className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-400 px-4 py-3 text-sm font-bold text-zinc-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-400"
              >
                {running ? (
                  <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.5} />
                ) : (
                  <Play className="h-4 w-4" strokeWidth={1.5} />
                )}
                {running ? "运行中" : "运行代码"}
              </button>
            </div>

            <AssessmentPanel result={result} aiFeedback={aiFeedback} />
            <HistoryPanel records={records} />
          </aside>
        </section>
      </div>
    </main>
  );
}

function RuntimeBadge({
  runtime,
  error,
}: {
  runtime: CompilerRuntimeStatus | null;
  error: string | null;
}) {
  const ready = runtime?.ready === true;
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900/70 px-4 py-3 text-xs">
      <div className="flex items-center gap-2">
        <span
          className={`h-2 w-2 rounded-full ${
            ready ? "bg-emerald-400" : error ? "bg-red-400" : "bg-amber-300"
          }`}
        />
        <span className="font-semibold text-zinc-200">
          {ready ? `${runtime.language} ${runtime.version}` : error ?? "连接运行环境"}
        </span>
      </div>
      {runtime ? (
        <p className="mt-1 text-zinc-500">
          {formatDuration(runtime.limits.wallTimeMs)} /{" "}
          {formatBytes(runtime.limits.memoryBytes)}
        </p>
      ) : null}
    </div>
  );
}

function ResultPanel({
  result,
  error,
}: {
  result: CompilerExecutionResult | null;
  error: string | null;
}) {
  const output = error ?? result?.stderr ?? result?.stdout ?? "等待运行结果";
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900/70 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-xs font-semibold text-zinc-300">控制台输出</h2>
        <span className="rounded-lg border border-zinc-800 px-2 py-1 text-[11px] text-zinc-500">
          {result?.outcome ?? "idle"}
        </span>
      </div>
      <pre
        className={`min-h-32 overflow-auto whitespace-pre-wrap rounded-xl border p-3 font-mono text-xs ${
          error || result?.stderr
            ? "border-red-900/70 bg-red-950/20 text-red-100"
            : "border-zinc-800 bg-zinc-950 text-zinc-100"
        }`}
      >
        {output}
      </pre>
      {result ? (
        <div className="mt-3 grid grid-cols-3 gap-2 text-[11px] text-zinc-400">
          <span>耗时 {formatDuration(result.metrics.wallTimeMs)}</span>
          <span>内存 {formatBytes(result.metrics.memoryBytes)}</span>
          <span>退出码 {result.exitCode ?? "-"}</span>
        </div>
      ) : null}
    </div>
  );
}

function AssessmentPanel({
  result,
  aiFeedback,
}: {
  result: CompilerExecutionResult | null;
  aiFeedback: CompilerAiFeedback | null;
}) {
  const assessment = result?.assessment;
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-4">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
        <CheckCircle2 className="h-4 w-4 text-emerald-300" strokeWidth={1.5} />
        规则结论
      </h2>
      <p className="mt-3 text-sm font-semibold text-zinc-200">
        {assessment?.title ?? "尚未运行"}
      </p>
      <p className="mt-2 text-xs leading-5 text-zinc-400">
        {assessment?.summary ?? "运行后会展示确定性规则结论。"}
      </p>
      {assessment?.errorType ? (
        <p className="mt-2 font-mono text-[11px] text-amber-200">
          {assessment.errorType}
          {assessment.line ? ` / 第 ${assessment.line} 行` : ""}
        </p>
      ) : null}

      <div className="mt-5 border-t border-zinc-800 pt-4">
        <h3 className="flex items-center gap-2 text-xs font-semibold text-zinc-300">
          <BrainCircuit className="h-4 w-4 text-zinc-400" strokeWidth={1.5} />
          AI 评析
        </h3>
        <p className="mt-2 text-xs leading-5 text-zinc-400">
          {aiFeedback?.explanation ?? aiFeedback?.message ?? "未启用或尚无 AI 反馈。"}
        </p>
        {aiFeedback?.quality ? (
          <div className="mt-3 rounded-xl border border-zinc-800 bg-zinc-950 p-3">
            <p className="text-[11px] text-zinc-500">代码质量参考分</p>
            <p className="mt-1 text-2xl font-bold text-emerald-300">
              {aiFeedback.quality.overall}
            </p>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function HistoryPanel({ records }: { records: CompilerRecord[] }) {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900/80 p-4">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
        <Save className="h-4 w-4 text-zinc-400" strokeWidth={1.5} />
        最近记录
      </h2>
      <div className="mt-3 space-y-2">
        {records.length === 0 ? (
          <p className="text-xs text-zinc-500">暂无运行记录</p>
        ) : (
          records.slice(0, 5).map((record) => (
            <article
              key={record.id}
              className="rounded-xl border border-zinc-800 bg-zinc-950 p-3"
            >
              <div className="flex items-center justify-between gap-2">
                <strong className="text-xs text-zinc-200">{record.title}</strong>
                <span className="flex items-center gap-1 text-[11px] text-zinc-500">
                  <Clock3 className="h-3 w-3" strokeWidth={1.5} />
                  {formatRecordTime(record.createdAt)}
                </span>
              </div>
              <p className="mt-1 line-clamp-2 text-[11px] leading-4 text-zinc-500">
                {record.aiExplanation ?? record.summary}
              </p>
            </article>
          ))
        )}
      </div>
    </div>
  );
}

function getLearnerId(): string {
  const storageKey = "code-navi-compiler-learner-id";
  if (typeof window === "undefined") return "00000000-0000-4000-8000-000000000000";
  const existing = window.localStorage.getItem(storageKey);
  if (existing) return existing;
  const generated = crypto.randomUUID();
  window.localStorage.setItem(storageKey, generated);
  return generated;
}

function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / 1024 / 1024).toFixed(1)} MiB`;
}

function formatDuration(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(1)} s`;
}

function formatRecordTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "刚刚";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export default function PracticePage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center bg-zinc-950 text-zinc-400">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" strokeWidth={1.5} />
          页面加载中...
        </main>
      }
    >
      <PracticeContent />
    </Suspense>
  );
}
