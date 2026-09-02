"use client";

import {
  AlertTriangle,
  BookOpen,
  Clock3,
  Database,
  FlaskConical,
  Lightbulb,
  Search,
  Target,
} from "lucide-react";

import type { ResearchProfile, ResearchReadiness } from "@/lib/api/research";

interface ResearchProfilePanelProps {
  profile: ResearchProfile;
  readiness: ResearchReadiness;
  learningBackground?: string | null;
  selectedPaperTitle?: string | null;
  onSend: (message: string) => void;
  disabled: boolean;
}

function displayValues(values: string[]): string {
  return values.length ? values.join("、") : "尚未确认";
}

function SummaryItem({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="min-w-0 rounded-xl border border-slate-200/80 bg-white/70 p-4 dark:border-zinc-800 dark:bg-zinc-950/30">
      <p className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-zinc-100">
        {icon} {label}
      </p>
      <p className="mt-2 text-base leading-7 text-slate-700 dark:text-zinc-300">{value}</p>
    </div>
  );
}

export function ResearchProfilePanel({
  profile,
  readiness,
  learningBackground,
  selectedPaperTitle,
  onSend,
  disabled,
}: ResearchProfilePanelProps) {
  const missing = readiness.reasons.length
    ? readiness.reasons
    : ["关键信息已足够进入下一步；仍请人工核对研究边界。"];

  return (
    <section className="rounded-2xl border border-slate-200 bg-slate-50/70 p-5 dark:border-zinc-800 dark:bg-zinc-950/40 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <p className="text-sm font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-zinc-400">
            Research starting point
          </p>
          <h2 className="mt-2 text-2xl font-bold tracking-tight text-slate-950 dark:text-zinc-100">
            科研画像摘要
          </h2>
          <p className="mt-2 text-base leading-7 text-slate-600 dark:text-zinc-300">
            只保留会影响方向、检索和复现安排的信息；旧会话中的其他字段仍在服务端保留以便兼容恢复。
          </p>
        </div>
        <span className="rounded-full border border-sky-200 bg-sky-50 px-3 py-2 text-sm font-semibold text-sky-800 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-200">
          {readiness.stage === "ready_for_plan" ? "可进入方向与文献" : "仍需补齐研究信息"}
        </span>
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <SummaryItem icon={<BookOpen className="h-4 w-4" />} label="学习知识背景" value={learningBackground || "尚未从 Learning 上下文确认背景"} />
        <SummaryItem icon={<Target className="h-4 w-4" />} label="研究主题" value={profile.topic || "尚未确认"} />
        <SummaryItem icon={<Lightbulb className="h-4 w-4" />} label="研究动机" value={profile.motivation || "尚未确认"} />
        <SummaryItem icon={<FlaskConical className="h-4 w-4" />} label="方法路径" value={displayValues(profile.methods)} />
        <SummaryItem icon={<Database className="h-4 w-4" />} label="数据需求" value={profile.data_requirements || "尚未确认"} />
        <SummaryItem icon={<Target className="h-4 w-4" />} label="预期产出" value={profile.expected_output || "尚未确认"} />
        <SummaryItem icon={<Clock3 className="h-4 w-4" />} label="时间和设备限制" value={[profile.time_scope, displayValues(profile.constraints)].filter((item) => item && item !== "尚未确认").join("；") || "尚未确认"} />
        <SummaryItem icon={<Search className="h-4 w-4" />} label="感兴趣的研究方向" value={displayValues(profile.candidate_questions)} />
        {selectedPaperTitle && (
          <SummaryItem icon={<Database className="h-4 w-4" />} label="当前选择论文" value={selectedPaperTitle} />
        )}
      </div>

      <div className="mt-5 px-1">
        <p className="flex items-center gap-2 text-base font-semibold text-slate-800 dark:text-zinc-200">
          <AlertTriangle className="h-4 w-4" /> 当前缺失信息
        </p>
        <ul className="mt-2 space-y-2 text-sm leading-6 text-slate-600 dark:text-zinc-400">
          {missing.map((reason) => <li key={reason}>• {reason}</li>)}
        </ul>
      </div>

      <details className="mt-5 rounded-xl border border-slate-200 bg-white/80 dark:border-zinc-800 dark:bg-zinc-950/30">
        <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-slate-800 dark:text-zinc-200">
          查看并讨论候选研究问题（{profile.candidate_questions.length}）
        </summary>
        <div className="border-t border-slate-200 p-4 dark:border-zinc-800">
          {profile.candidate_questions.length ? (
            <div className="space-y-2">
              {profile.candidate_questions.map((question) => (
                <button
                  key={question}
                  type="button"
                  disabled={disabled}
                  onClick={() => onSend(`我想优先讨论这个候选问题：${question}`)}
                  className="app-button-secondary min-h-10 w-full rounded-xl px-4 py-2 text-left text-sm leading-6 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {question}
                </button>
              ))}
            </div>
          ) : (
            <p className="text-sm leading-6 text-slate-600 dark:text-zinc-400">尚未形成候选问题，可先在上方对话中补充。</p>
          )}
        </div>
      </details>

      <p className="mt-4 text-sm leading-6 text-slate-600 dark:text-zinc-400">
        当前对话不会自动联网检索。受限学术来源检索只有你明确触发后才会执行。
      </p>
    </section>
  );
}
