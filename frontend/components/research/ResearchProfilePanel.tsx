import {
  AlertTriangle,
  BarChart3,
  Check,
  CircleDashed,
  Compass,
  Database,
  FileOutput,
  FlaskConical,
  Search,
  Target,
  Users,
} from "lucide-react";

import type { ResearchProfile, ResearchReadiness } from "@/lib/api/research";

interface ResearchProfilePanelProps {
  profile: ResearchProfile;
  readiness: ResearchReadiness;
  onSend: (message: string) => void;
  disabled: boolean;
}

const STAGE_LABELS = {
  exploring: "方向探索中",
  focusing: "正在聚焦",
  ready_for_plan: "可准备研究计划",
};

function ProfileItem({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | null;
}) {
  return (
    <div className="flex gap-3 rounded-xl border border-slate-200/80 bg-white/80 p-3 dark:border-zinc-800 dark:bg-zinc-900/70">
      <span className="mt-0.5 text-slate-400 dark:text-zinc-500">{icon}</span>
      <div className="min-w-0">
        <p className="text-[11px] font-medium text-slate-500 dark:text-zinc-500">{label}</p>
        <p className="mt-1 text-xs leading-5 text-slate-800 dark:text-zinc-200">
          {value || "尚未讨论"}
        </p>
      </div>
    </div>
  );
}

function joinValues(values: string[]): string | null {
  return values.length ? values.join("、") : null;
}

export function ResearchProfilePanel({
  profile,
  readiness,
  onSend,
  disabled,
}: ResearchProfilePanelProps) {
  return (
    <aside className="space-y-4 lg:sticky lg:top-5 lg:max-h-[calc(100vh-2.5rem)] lg:overflow-y-auto lg:pr-1">
      <section className="rounded-2xl border border-slate-200 bg-slate-50/90 p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-sky-700 dark:text-sky-300">
              Research profile
            </p>
            <h2 className="mt-1 text-sm font-bold text-slate-900 dark:text-zinc-100">科研画像</h2>
          </div>
          <span className="rounded-full bg-sky-100 px-2 py-1 text-[10px] font-semibold text-sky-700 dark:bg-sky-950 dark:text-sky-300">
            {STAGE_LABELS[readiness.stage]}
          </span>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-200 dark:bg-zinc-800">
            <div
              className="h-full rounded-full bg-gradient-to-r from-sky-500 to-indigo-500 transition-all duration-500"
              style={{ width: `${readiness.score}%` }}
            />
          </div>
          <span className="text-xs font-bold tabular-nums text-slate-700 dark:text-zinc-300">
            {readiness.score}%
          </span>
        </div>

        <div className="mt-4 space-y-2">
          <ProfileItem icon={<Compass className="h-4 w-4" />} label="研究主题" value={profile.topic} />
          <ProfileItem icon={<Target className="h-4 w-4" />} label="研究动机" value={profile.motivation} />
          <ProfileItem icon={<Users className="h-4 w-4" />} label="对象与场景" value={profile.context} />
          <ProfileItem icon={<FlaskConical className="h-4 w-4" />} label="方法路径" value={joinValues(profile.methods)} />
          <ProfileItem icon={<Database className="h-4 w-4" />} label="数据需求" value={profile.data_requirements} />
          <ProfileItem icon={<FileOutput className="h-4 w-4" />} label="预期产出" value={profile.expected_output} />
        </div>
      </section>

      {profile.candidate_questions.length > 0 && (
        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80">
          <h2 className="flex items-center gap-2 text-xs font-bold text-slate-900 dark:text-zinc-100">
            <BarChart3 className="h-4 w-4 text-indigo-500" /> 候选研究问题
          </h2>
          <div className="mt-3 space-y-2">
            {profile.candidate_questions.map((question) => (
              <button
                key={question}
                type="button"
                disabled={disabled}
                onClick={() => onSend(`我想优先讨论这个候选问题：${question}`)}
                className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-left text-xs leading-5 text-slate-700 transition hover:border-indigo-300 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-800 dark:text-zinc-300 dark:hover:border-indigo-800 dark:hover:bg-indigo-950/30"
              >
                {question}
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/80">
        <h2 className="flex items-center gap-2 text-xs font-bold text-slate-900 dark:text-zinc-100">
          {readiness.can_prepare_search ? (
            <Check className="h-4 w-4 text-emerald-500" />
          ) : (
            <CircleDashed className="h-4 w-4 text-amber-500" />
          )}
          下一步准备度
        </h2>
        {readiness.reasons.length > 0 ? (
          <ul className="mt-3 space-y-2 text-xs leading-5 text-slate-600 dark:text-zinc-400">
            {readiness.reasons.map((reason) => (
              <li key={reason} className="flex gap-2">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
                {reason}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-xs leading-5 text-emerald-700 dark:text-emerald-300">
            当前信息已经足够检查研究画像并准备下一步。
          </p>
        )}

        <div className="mt-4 rounded-xl border border-violet-200 bg-violet-50/60 p-3 text-[11px] leading-5 text-violet-800 dark:border-violet-900/60 dark:bg-violet-950/20 dark:text-violet-300">
          <p className="flex items-center gap-1.5 font-semibold">
            <Search className="h-3.5 w-3.5" /> 信息来源边界
          </p>
          <p className="mt-1">当前对话不会自动联网检索。受限学术来源检索将在下一阶段接入，并始终需要你明确触发。</p>
        </div>
      </section>
    </aside>
  );
}
