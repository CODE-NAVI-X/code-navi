"use client";

import { useEffect, useState } from "react";
import {
  createReproductionPipeline,
  listReproductionPipelines,
  listResearchEvidence,
  type ConversationEvidenceBundle,
  type ReproductionPipeline,
  type ReproductionPipelineItem,
} from "@/lib/api/research";
import { ClassificationBadge } from "./ClassificationBadge";

export function ReproductionPipelinePanel({ conversationId }: { conversationId: string }) {
  const [bundles, setBundles] = useState<ConversationEvidenceBundle[]>([]);
  const [selected, setSelected] = useState("");
  const [pipeline, setPipeline] = useState<ReproductionPipeline | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void Promise.all([listResearchEvidence(conversationId), listReproductionPipelines(conversationId)])
      .then(([savedBundles, savedPipelines]) => {
        setBundles(savedBundles);
        setPipeline(savedPipelines[0] ?? null);
      })
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "无法恢复复现方案。"));
  }, [conversationId]);

  const papers = bundles.flatMap((bundle) => bundle.papers.map((paper) => ({ ...paper, bundleId: bundle.bundle_id })));
  const generate = async () => {
    const paper = papers.find((item) => item.url === selected);
    if (!paper) return;
    setBusy(true); setError(null);
    try {
      setPipeline(await createReproductionPipeline(conversationId, { evidence_bundle_id: paper.bundleId, paper_url: paper.url }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "无法生成复现方案。");
    } finally { setBusy(false); }
  };

  return <div className="space-y-3 rounded-xl border border-violet-200 bg-violet-50/40 p-4 text-sm dark:border-violet-900 dark:bg-violet-950/20">
    <p className="font-semibold text-violet-950 dark:text-violet-100">复现方案</p>
    <p className="text-xs text-violet-900 dark:text-violet-200">仅使用你已保存并主动选择的受限论文来源。不会联网、下载全文、运行代码或写入学生项目。</p>
    <label className="block text-xs font-medium">选择已保存论文
      <select value={selected} onChange={(event) => setSelected(event.target.value)} className="mt-1 block w-full rounded border p-2" aria-label="选择已保存论文">
        <option value="">请选择</option>{papers.map((paper) => <option key={`${paper.bundleId}-${paper.url}`} value={paper.url}>{paper.title}</option>)}
      </select>
    </label>
    {!selected && <p className="text-xs text-amber-800 dark:text-amber-200">请先从已保存的受限来源中选择一篇论文，系统不会生成伪造方案。</p>}
    <button type="button" disabled={!selected || busy} onClick={() => void generate()} className="rounded bg-violet-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy ? "生成中…" : "生成复现方案"}</button>
    {error && <p role="alert" className="text-xs text-red-700">{error}</p>}
    {pipeline && <div className="space-y-3 border-t pt-3"><p className="font-medium">{pipeline.selected_paper.title}</p>
      {[["复现目标", pipeline.reproduction_goal], ["已知方法", pipeline.known_method], ["数据/样本条件", pipeline.data_and_sample_conditions[0]], ["指标", pipeline.metrics[0]], ["风险", pipeline.risks[0]]].map(([label, item]) => <div key={String(label)}><p className="font-medium">{label as string} <ClassificationBadge classification={(item as ReproductionPipelineItem).classification} /></p><p className="text-xs">{(item as ReproductionPipelineItem).content}</p><p className="text-xs text-slate-500">{(item as ReproductionPipelineItem).source_scope}</p></div>)}
      <div><p className="font-medium">Python 学习任务（不执行代码）</p>{pipeline.tasks.map((task) => <p key={task.task_id} className="text-xs">{task.title} · {task.status === "evidence_linked" ? "已关联用户实验记录" : "待用户记录"}</p>)}</div>
    </div>}
  </div>;
}
