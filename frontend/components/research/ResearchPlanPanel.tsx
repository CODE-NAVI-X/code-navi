import { AlertTriangle, CalendarDays, CheckCircle2, FileText, Lightbulb } from "lucide-react";

import type { ConversationResearchPlan, ResearchPlanEntry } from "@/lib/api/research";
import { ClassificationBadge } from "./ClassificationBadge";

function PlanEntry({ entry }: { entry: ResearchPlanEntry }) {
  return (
    <li className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3 text-base leading-7 dark:border-zinc-800 dark:bg-zinc-950/40">
      <ClassificationBadge classification={entry.classification} />
      <p className="mt-2 text-slate-800 dark:text-zinc-200">{entry.content}</p>
      <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-zinc-500">依据：{entry.basis}</p>
      {entry.relevance && <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-zinc-400">与当前研究问题的关系：{entry.relevance}</p>}
      {entry.suggested_action && <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-zinc-400">建议下一步：{entry.suggested_action}</p>}
    </li>
  );
}

function Section({ title, entries }: { title: string; entries: ResearchPlanEntry[] }) {
  return (
    <section>
      <h3 className="text-base font-bold text-slate-800 dark:text-zinc-200">{title}</h3>
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
    <section className="app-card rounded-2xl p-4">
      <div className="flex items-start gap-3">
        <span className="rounded-xl bg-slate-100 p-2 text-slate-700 dark:bg-zinc-800 dark:text-zinc-200">
          <FileText className="h-4 w-4" />
        </span>
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-zinc-400">Research plan</p>
          <h2 className="mt-1 text-lg font-bold text-slate-900 dark:text-zinc-100">模型研究计划</h2>
        </div>
      </div>

      <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-zinc-400">
        <AlertTriangle className="mr-1 inline h-3.5 w-3.5" /> 模型已结合当前科研画像生成研究建议；实验结论需在你完成实验并保存证据后确认，联网检索仍由你主动触发。
      </p>

      {plan.core_judgment && (
        <p className="mt-3 text-base leading-7 font-semibold text-slate-900 dark:text-zinc-100">核心判断：{plan.core_judgment}</p>
      )}

      <div className="mt-4 space-y-4">
        <Section title="研究题目" entries={[plan.research_title]} />
        <Section title="研究目标" entries={[plan.research_goal]} />
        <Section title="候选方法或基线" entries={plan.candidate_methods_or_baselines} />
        <Section title="可选数据集或评测指标" entries={plan.suggested_datasets_or_metrics} />
        <Section title="两周最小可行验证计划" entries={plan.two_week_mvp_plan} />

        <section>
          <h3 className="flex items-center gap-1.5 text-base font-bold text-slate-800 dark:text-zinc-200">
            <CalendarDays className="h-3.5 w-3.5 text-slate-500 dark:text-zinc-400" /> 主要风险与规避建议
          </h3>
          <ul className="mt-2 space-y-2">
            {plan.risks_and_mitigations.map((item) => (
              <li key={item.risk.content} className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3 text-base leading-7 dark:border-zinc-800 dark:bg-zinc-950/40">
                <p className="font-medium text-slate-800 dark:text-zinc-200">风险</p>
                <ul className="mt-2"><PlanEntry entry={item.risk} /></ul>
                <p className="mt-3 font-medium text-slate-800 dark:text-zinc-200">规避建议</p>
                <ul className="mt-2"><PlanEntry entry={item.mitigation} /></ul>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h3 className="flex items-center gap-1.5 text-base font-bold text-slate-800 dark:text-zinc-200">
            <Lightbulb className="h-3.5 w-3.5 text-slate-500 dark:text-zinc-400" /> 建议检索关键词
          </h3>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {plan.suggested_search_keywords.map((keyword) => (
              <span key={keyword} className="rounded-full bg-slate-100 px-2 py-1 text-sm font-medium text-slate-700 dark:bg-zinc-800 dark:text-zinc-200">
                {keyword}
              </span>
            ))}
          </div>
        </section>

        {plan.pending_items.length > 0 && <Section title="待确认或待验证" entries={plan.pending_items} />}
      </div>

      {plan.next_action && (
        <p className="mt-4 text-base leading-7 font-semibold text-slate-900 dark:text-zinc-100">唯一下一步：{plan.next_action}</p>
      )}

      <p className="mt-4 flex items-start gap-1.5 text-sm leading-6 text-slate-500 dark:text-zinc-500">
        <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {plan.provenance_note}
        {plan.run_id && <span className="break-all"> · Run ID: {plan.run_id}</span>}
      </p>
    </section>
  );
}
