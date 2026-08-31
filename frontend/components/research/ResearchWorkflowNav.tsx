"use client";

import { ListChecks } from "lucide-react";
import type { MouseEvent } from "react";

import type { RecommendedAction, ResearchConversationResponse } from "@/lib/api/research";

interface WorkflowZone {
  anchorId: string;
  label: string;
  admission: string;
}

const DEFAULT_ZONE_BY_ACTION: Record<RecommendedAction, number> = {
  continue_dialogue: 0,
  review_profile: 0,
  prepare_search: 1,
};

const PRIMARY_ZONES: WorkflowZone[] = [
  { anchorId: "research-section-start", label: "研究起点", admission: "确认研究主题与候选问题" },
  { anchorId: "research-section-literature", label: "方向与文献", admission: "画像达到检索准备度，并由用户主动检索" },
  { anchorId: "research-section-paper-analysis", label: "论文深度分析", admission: "选择当前会话中已保存的论文" },
  { anchorId: "research-section-workbench", label: "复现工作台", admission: "已确认论文分析范围和待核验条件" },
  { anchorId: "research-section-evidence", label: "证据与成果", admission: "已有复现任务或用户实验记录" },
];

function zoneDetails(conversation: ResearchConversationResponse, zone: number) {
  if (zone === 0) return { missing: conversation.readiness.reasons[0] ?? "请确认研究范围。", next: "补充或确认研究需求。" };
  if (zone === 1) return { missing: "请确认检索词与允许来源。", next: "主动启动受限检索。" };
  if (zone === 2) return { missing: "请选择一篇已保存论文并核对摘要范围。", next: "生成论文深度分析。" };
  if (zone === 3) return { missing: "请核对待验证的复现条件。", next: "生成并核对复现方案。" };
  return { missing: "请补充用户实验记录或待核验证据。", next: "主动运行证据完整度评估。" };
}

function jumpToZone(event: MouseEvent<HTMLAnchorElement>, anchorId: string) {
  const target = document.getElementById(anchorId);
  if (!target) return;
  event.preventDefault();
  if (target instanceof HTMLDetailsElement) target.open = true;
  target.scrollIntoView({ behavior: "smooth", block: "start" });
}

export function ResearchWorkflowNav({
  conversation,
  currentStage,
  selectedPaperTitle,
}: {
  conversation: ResearchConversationResponse;
  currentStage?: number;
  selectedPaperTitle?: string | null;
}) {
  const zone = Math.min(Math.max(currentStage ?? DEFAULT_ZONE_BY_ACTION[conversation.recommended_action], 0), PRIMARY_ZONES.length - 1);
  const details = zoneDetails(conversation, zone);

  return (
    <nav aria-label="科研五区主流程" className="app-card mb-8 rounded-2xl px-5 py-6 sm:px-7">
      <div className="grid gap-3 text-base leading-7 text-slate-700 dark:text-zinc-300 lg:grid-cols-2">
        <p><span className="font-semibold text-slate-950 dark:text-zinc-100">当前研究主题：</span>{conversation.profile.topic ?? "尚未确认"}</p>
        <p><span className="font-semibold text-slate-950 dark:text-zinc-100">当前阶段：</span>{PRIMARY_ZONES[zone].label}</p>
        <p><span className="font-semibold text-slate-950 dark:text-zinc-100">当前缺失信息：</span>{details.missing}</p>
        <p><span className="font-semibold text-slate-950 dark:text-zinc-100">当前选择论文：</span>{selectedPaperTitle ?? "尚未选择"}</p>
        <p className="lg:col-span-2"><span className="font-semibold text-slate-950 dark:text-zinc-100">唯一下一步：</span>{details.next}</p>
      </div>
      <ol className="mt-6 grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
        {PRIMARY_ZONES.map((item, index) => {
          const status = index < zone ? "已完成摘要" : index === zone ? "当前区域" : "尚未开始";
          return (
            <li key={item.label}>
              <a href={`#${item.anchorId}`} onClick={(event) => jumpToZone(event, item.anchorId)} className="app-button-secondary flex min-h-12 h-full rounded-xl px-3 py-3 text-sm transition hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 dark:hover:bg-zinc-800">
                <ListChecks className="mt-0.5 h-4 w-4 shrink-0" />
                <span className="ml-2 min-w-0"><span className="block font-semibold">{index + 1}. {item.label}</span><span className="mt-1 block leading-5 text-slate-600 dark:text-zinc-400">{status} · {index > zone ? item.admission : "可展开查看"}</span></span>
              </a>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
