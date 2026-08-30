"use client";

import { ClipboardCheck, FileText, Loader2, Plus } from "lucide-react";
import { useEffect, useState } from "react";

import {
  createExperimentEvidenceBundle,
  generatePaperBlueprint,
  listExperimentEvidenceBundles,
  listReproductionPipelines,
  type AnalysisClassification,
  type ExperimentEvidenceBundle,
  type ExperimentEvidenceCategory,
  type PaperBlueprint,
  type ReproductionPipeline,
} from "@/lib/api/research";
import { ClassificationBadge } from "./ClassificationBadge";

const categoryLabels: Array<{ value: ExperimentEvidenceCategory; label: string }> = [
  { value: "data_or_sample", label: "数据或样本实际情况" },
  { value: "setup", label: "实验设置" },
  { value: "baseline_or_control", label: "对照组或基线" },
  { value: "random_seed_or_reason", label: "随机种子或不可得原因" },
  { value: "metric_or_result", label: "指标或结果数值" },
  { value: "result_table", label: "结果表格文本" },
  { value: "chart_description", label: "图表说明" },
  { value: "failure_or_limitation", label: "失败、异常或局限" },
  { value: "ethics_or_data_governance", label: "伦理、匿名化或数据许可" },
  { value: "pending_item", label: "待确认项" },
];

const classificationLabels: Record<AnalysisClassification, string> = {
  fact: "用户提交事实（未复核）",
  inference: "建议/推断",
  to_verify: "待验证",
};

function EntryLabel({ classification }: { classification: AnalysisClassification }) {
  return <ClassificationBadge classification={classification} />;
}

export function ExperimentEvidencePanel({
  conversationId,
  evidenceVersion,
  onEvidenceSaved,
}: {
  conversationId: string;
  evidenceVersion: number;
  onEvidenceSaved?: () => void;
}) {
  const [bundles, setBundles] = useState<ExperimentEvidenceBundle[]>([]);
  const [pipeline, setPipeline] = useState<ReproductionPipeline | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [experimentName, setExperimentName] = useState("");
  const [goal, setGoal] = useState("");
  const [category, setCategory] = useState<ExperimentEvidenceCategory>("metric_or_result");
  const [classification, setClassification] = useState<AnalysisClassification>("fact");
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [blueprint, setBlueprint] = useState<PaperBlueprint | null>(null);
  const [buildingBlueprint, setBuildingBlueprint] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void Promise.all([
      listExperimentEvidenceBundles(conversationId),
      listReproductionPipelines(conversationId),
    ])
      .then(([savedBundles, savedPipelines]) => {
        if (!active) return;
        setBundles(savedBundles);
        setPipeline(savedPipelines[0] ?? null);
      })
      .catch((value: unknown) => { if (active) setError(value instanceof Error ? value.message : "无法恢复实验结果记录。"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [conversationId, evidenceVersion]);

  async function saveEvidence() {
    if (!experimentName.trim() || !goal.trim() || !content.trim()) {
      setError("请填写实验名称、目标和至少一条结果/记录。\n");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await createExperimentEvidenceBundle(conversationId, {
        experiment_name: experimentName,
        goal,
        items: [{
          category,
          classification,
          content,
          related_plan_item: selectedTaskId || null,
        }],
      });
      setBundles((current) => [saved, ...current]);
      setContent("");
      onEvidenceSaved?.();
    } catch (value) {
      setError(value instanceof Error ? value.message : "保存实验结果失败。请重试。");
    } finally {
      setSaving(false);
    }
  }

  async function buildBlueprint() {
    setBuildingBlueprint(true);
    setError(null);
    try {
      setBlueprint(await generatePaperBlueprint(conversationId));
    } catch (value) {
      setError(value instanceof Error ? value.message : "生成论文蓝图失败。请重试。");
    } finally {
      setBuildingBlueprint(false);
    }
  }

  return (
    <section className="app-card rounded-2xl p-4">
      <div className="flex items-center gap-3">
        <span className="rounded-xl bg-slate-100 p-2 text-slate-700 dark:bg-zinc-800 dark:text-zinc-300"><ClipboardCheck className="h-4 w-4" /></span>
        <div><p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-zinc-400">Experiment evidence</p><h2 className="mt-1 text-sm font-bold">实验结果证据包</h2></div>
      </div>
      <p className="mt-3 text-[11px] leading-5 text-slate-600 dark:text-zinc-400">仅保存你主动粘贴的文本、表格文本或图表说明。不会读取文件、运行代码或联网；“事实”表示你的报告，系统不会将其当作已独立复核结论。</p>
      <div className="mt-3 grid gap-2">
        <input value={experimentName} onChange={(event) => setExperimentName(event.target.value)} maxLength={500} placeholder="实验名称" aria-label="实验名称" className="app-input rounded-lg px-2 py-1.5 text-xs" />
        <input value={goal} onChange={(event) => setGoal(event.target.value)} maxLength={1000} placeholder="实验目标" aria-label="实验目标" className="app-input rounded-lg px-2 py-1.5 text-xs" />
        <div className="grid grid-cols-2 gap-2">
          <select value={category} onChange={(event) => setCategory(event.target.value as ExperimentEvidenceCategory)} aria-label="证据类别" className="app-input rounded-lg px-2 py-1.5 text-[11px]">{categoryLabels.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select>
          <select value={classification} onChange={(event) => setClassification(event.target.value as AnalysisClassification)} aria-label="证据分类" className="app-input rounded-lg px-2 py-1.5 text-[11px]">{Object.entries(classificationLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
        </div>
        <label className="text-[11px] text-slate-600 dark:text-zinc-400">
          关联复现任务（可选）
          <select value={selectedTaskId} onChange={(event) => setSelectedTaskId(event.target.value)} aria-label="关联复现任务" className="app-input mt-1 w-full rounded-lg px-2 py-1.5 text-[11px]">
            <option value="">不关联任务</option>
            {pipeline?.tasks.map((task) => <option key={task.task_id} value={task.task_id}>{task.title}</option>)}
          </select>
        </label>
        <p className="text-[10px] leading-5 text-slate-500 dark:text-zinc-400">
          {pipeline
            ? "关联只表示存在相关用户实验记录，不代表实验正确、完成或复现成功。"
            : "请先从已保存论文主动生成复现方案；系统不会用普通研究计划补造关联任务。"}
        </p>
        <textarea value={content} onChange={(event) => setContent(event.target.value)} maxLength={4000} rows={4} placeholder="例如：指标、数值、失败原因、表格文本或待确认条件…" aria-label="实验结果或证据内容" className="app-input resize-y rounded-lg px-2 py-1.5 text-xs leading-5" />
      </div>
      <button type="button" onClick={() => void saveEvidence()} disabled={saving} className="app-button-secondary mt-2 inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] font-semibold disabled:opacity-50">{saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}保存结果记录</button>
      {error && <p role="alert" className="mt-2 whitespace-pre-wrap text-xs text-rose-600">{error}</p>}
      {loading ? <p role="status" aria-live="polite" className="mt-3 text-[11px] text-slate-500">正在恢复已保存的实验结果…</p> : bundles.length ? <div className="mt-3 space-y-2">{bundles.map((bundle) => <details key={bundle.bundle_id} className="app-card-subtle rounded-lg p-2"><summary className="cursor-pointer text-xs font-semibold">{bundle.experiment_name.content} · {new Date(bundle.submitted_at).toLocaleString()}</summary><p className="mt-2 text-[11px]"><EntryLabel classification={bundle.goal.classification} />：{bundle.goal.content}</p>{bundle.items.map((item, index) => <div key={`${item.category}-${index}`} className="mt-1"><p className="text-[11px]"><EntryLabel classification={item.classification} />：{item.content}</p><p className="text-[10px] text-slate-500">来源范围：{item.source_scope} · 依据：{item.basis}</p></div>)}<p className="mt-2 text-[10px] text-slate-500">证据范围：{bundle.provenance_note}</p></details>)}</div> : <p className="mt-3 text-[11px] text-slate-500">尚未保存实验结果。没有结果时仍可生成“待补充”的论文蓝图。</p>}
      <button type="button" onClick={() => void buildBlueprint()} disabled={buildingBlueprint} className="app-button-primary mt-4 inline-flex items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold disabled:opacity-50">{buildingBlueprint ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileText className="h-3.5 w-3.5" />}我确认生成论文蓝图</button>
      {blueprint && <div className="app-card-subtle mt-3 rounded-xl p-3 text-xs"><p className="font-bold">{blueprint.candidate_titles[0]?.content}</p><p className="mt-1 text-[11px]">投稿就绪度：<EntryLabel classification={blueprint.submission_readiness.classification} /> · {blueprint.submission_readiness.content}</p>{blueprint.sections.map((section) => <details key={section.section} className="mt-2 rounded-lg bg-slate-50 p-2 dark:bg-zinc-950/50"><summary className="cursor-pointer font-semibold">{section.section}：{section.writing_goal.content}</summary><p className="mt-1 text-[11px]">可用证据：{section.evidence_references.length ? section.evidence_references.map((reference) => reference.label).join("；") : "暂无"}</p><p className="mt-1 text-[11px]">待补充：{section.missing_evidence.map((item) => item.content).join("；") || "无"}</p></details>)}<p className="mt-2 text-[10px] text-slate-500">{blueprint.provenance_note}</p></div>}
    </section>
  );
}
