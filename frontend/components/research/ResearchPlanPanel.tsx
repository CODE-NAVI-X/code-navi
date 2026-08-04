import { AlertTriangle, CalendarDays, CheckCircle2, FileText, Lightbulb } from "lucide-react";

import type { ConversationResearchPlan, ResearchPlanEntry } from "@/lib/api/research";

function PlanEntry({ entry }: { entry: ResearchPlanEntry }) {
  const pending = entry.classification === "to_verify";
  return (
    <li className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3 text-xs leading-5 dark:border-zinc-800 dark:bg-zinc-950/40">
      <span
        className={
          pending
            ? "rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800 dark:bg-amber-950/50 dark:text-amber-300"
            : "rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-semibold text-sky-800 dark:bg-sky-950/50 dark:text-sky-300"
        }
      >
        {pending ? "待确认" : "建议"}
      </span>
      <p className="mt-2 text-slate-800 dark:text-zinc-200">{entry.content}</p>
      <p className="mt-1 text-[10px] text-slate-500 dark:text-zinc-500">依据：{entry.basis}</p>
    </li>
  );
}

function Section({ title, entries }: { title: string; entries: ResearchPlanEntry[] }) {
  return (
    <section>
      <h3 className="text-[11px] font-bold text-slate-800 dark:text-zinc-200">{title}</h3>
      <ul className="mt-2 space-y-2">
        {entries.map((entry) => (
          <PlanEntry key={`${entry.classification}-${entry.content}`} entry={entry} />
        ))}
      </ul>
    </section>
  );
}

export function ResearchPlanPanel({ plan }: { plan: ConversationResearchPlan }) {
  return (
    <section className="rounded-2xl border border-indigo-200 bg-white p-4 shadow-sm dark:border-indigo-900/70 dark:bg-zinc-900/80">
      <div className="flex items-start gap-3">
        <span className="rounded-xl bg-indigo-100 p-2 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300">
          <FileText className="h-4 w-4" />
        </span>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-indigo-700 dark:text-indigo-300">Research plan</p>
          <h2 className="mt-1 text-sm font-bold text-slate-900 dark:text-zinc-100">规则研究计划</h2>
        </div>
      </div>

      <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50/70 p-3 text-[11px] leading-5 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-200">
        <AlertTriangle className="mr-1 inline h-3.5 w-3.5" /> 本计划只根据当前科研画像离线整理；内容是建议或待确认或待验证项，不是论文事实、实验结论，也没有触发联网检索。
      </p>

      <div className="mt-4 space-y-4">
        <Section title="研究题目" entries={[plan.research_title]} />
        <Section title="研究目标" entries={[plan.research_goal]} />
        <Section title="候选方法或基线" entries={plan.candidate_methods_or_baselines} />
        <Section title="可选数据集或评测指标" entries={plan.suggested_datasets_or_metrics} />
        <Section title="两周最小可行验证计划" entries={plan.two_week_mvp_plan} />

        <section>
          <h3 className="flex items-center gap-1.5 text-[11px] font-bold text-slate-800 dark:text-zinc-200">
            <CalendarDays className="h-3.5 w-3.5 text-indigo-500" /> 主要风险与规避建议
          </h3>
          <ul className="mt-2 space-y-2">
            {plan.risks_and_mitigations.map((item) => (
              <li key={item.risk.content} className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3 text-xs leading-5 dark:border-zinc-800 dark:bg-zinc-950/40">
                <p className="font-medium text-slate-800 dark:text-zinc-200">风险</p>
                <ul className="mt-2"><PlanEntry entry={item.risk} /></ul>
                <p className="mt-3 font-medium text-slate-800 dark:text-zinc-200">规避建议</p>
                <ul className="mt-2"><PlanEntry entry={item.mitigation} /></ul>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h3 className="flex items-center gap-1.5 text-[11px] font-bold text-slate-800 dark:text-zinc-200">
            <Lightbulb className="h-3.5 w-3.5 text-indigo-500" /> 建议检索关键词
          </h3>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {plan.suggested_search_keywords.map((keyword) => (
              <span key={keyword} className="rounded-full bg-indigo-50 px-2 py-1 text-[10px] font-medium text-indigo-800 dark:bg-indigo-950/40 dark:text-indigo-200">
                {keyword}
              </span>
            ))}
          </div>
        </section>

        {plan.pending_items.length > 0 && <Section title="待确认或待验证" entries={plan.pending_items} />}
      </div>

      <p className="mt-4 flex items-start gap-1.5 text-[10px] leading-5 text-slate-500 dark:text-zinc-500">
        <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {plan.provenance_note}
      </p>
    </section>
  );
}
