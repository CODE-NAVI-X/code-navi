"use client";

import { useEffect, useState } from "react";
import {
  createReproductionPipeline,
  listExperimentEvidenceBundles,
  listReproductionPipelines,
  listResearchEvidence,
  type ConversationEvidenceBundle,
  type ReproductionPipeline,
  type ReproductionPipelineItem,
} from "@/lib/api/research";
import { ClassificationBadge } from "./ClassificationBadge";
import { GenerationFailure, isGenerationFailure } from "./generationUi";

type SavedPaper = ConversationEvidenceBundle["papers"][number] & {
  bundleId: string;
  selectionKey: string;
};

export function ReproductionPipelinePanel({
  conversationId,
  evidenceVersion,
  onPipelineSaved,
}: {
  conversationId: string;
  evidenceVersion: number;
  onPipelineSaved?: (pipeline: ReproductionPipeline) => void;
}) {
  const [bundles, setBundles] = useState<ConversationEvidenceBundle[]>([]);
  const [selected, setSelected] = useState("");
  const [pipeline, setPipeline] = useState<ReproductionPipeline | null>(null);
  const [linkedTaskIds, setLinkedTaskIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [failure, setFailure] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void Promise.all([
      listResearchEvidence(conversationId),
      listReproductionPipelines(conversationId),
      listExperimentEvidenceBundles(conversationId),
    ])
      .then(([savedBundles, savedPipelines, experimentBundles]) => {
        setBundles(savedBundles);
        setPipeline(savedPipelines[0] ?? null);
        setLinkedTaskIds(
          [...new Set(
            experimentBundles.flatMap((bundle) => [
              bundle.experiment_name,
              bundle.goal,
              ...bundle.items,
            ].flatMap((item) => item.related_plan_item ? [item.related_plan_item] : [])),
          )],
        );
      })
      .catch((cause: unknown) =>
        setError(cause instanceof Error ? cause.message : "无法恢复复现方案。"),
      );
  }, [conversationId, evidenceVersion]);

  const papers: SavedPaper[] = bundles.flatMap((bundle) =>
    bundle.papers.map((paper, index) => ({
      ...paper,
      bundleId: bundle.bundle_id,
      selectionKey: `${bundle.bundle_id}:${paper.paper_id ?? paper.url ?? index}`,
    })),
  );
  const generate = async () => {
    const paper = papers.find((item) => item.selectionKey === selected);
    if (!paper) return;
    setBusy(true);
    setError(null);
    setFailure(false);
    try {
      const savedPipeline = await createReproductionPipeline(conversationId, {
          evidence_bundle_id: paper.bundleId,
          paper_url: paper.url,
        });
      setPipeline(savedPipeline);
      onPipelineSaved?.(savedPipeline);
    } catch (cause) {
      setFailure(isGenerationFailure(cause));
      setError(cause instanceof Error ? cause.message : "无法生成复现方案。");
    } finally {
      setBusy(false);
    }
  };

  const sections: Array<[string, ReproductionPipelineItem | ReproductionPipelineItem[]]> = pipeline
    ? [
        ["复现目标", pipeline.reproduction_goal],
        ["研究问题", pipeline.research_question],
        ["已知方法", pipeline.known_method],
        ["数据/样本条件", pipeline.data_and_sample_conditions],
        ["候选基线", pipeline.candidate_baselines],
        ["指标", pipeline.metrics],
        ["实验步骤", pipeline.experiment_steps],
        ["资源", pipeline.resources],
        ["风险", pipeline.risks],
        ["伦理", pipeline.ethics],
        ["待确认项", pipeline.confirmation_items],
        ["两周 MVP", pipeline.two_week_mvp],
      ]
    : [];

  return (
    <div className="space-y-3 rounded-xl border border-violet-200 bg-violet-50/40 p-4 text-sm dark:border-violet-900 dark:bg-violet-950/20">
      <p className="font-semibold text-violet-950 dark:text-violet-100">复现方案</p>
      <p className="text-xs text-violet-900 dark:text-violet-200">
        仅使用你已保存并主动选择的受限论文来源。不会联网、下载全文、运行代码或写入学生项目。
      </p>
      <label className="block text-xs font-medium">
        选择已保存论文
        <select
          value={selected}
          onChange={(event) => setSelected(event.target.value)}
          className="mt-1 block w-full rounded border p-2"
          aria-label="选择已保存论文"
        >
          <option value="">请选择</option>
          {papers.map((paper) => (
            <option key={paper.selectionKey} value={paper.selectionKey}>
              {paper.title}
            </option>
          ))}
        </select>
      </label>
      {!selected && (
        <p className="text-xs text-amber-800 dark:text-amber-200">
          请先从已保存的受限来源中选择一篇论文，系统不会生成伪造方案。
        </p>
      )}
      <button
        type="button"
        disabled={!selected || busy}
        onClick={() => void generate()}
        className="rounded bg-violet-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
      >
        {busy ? "生成中…" : "生成复现方案"}
      </button>
      {error &&
        (failure ? (
          <GenerationFailure
            error={error}
            busy={busy}
            hasLastSuccess={pipeline !== null}
            onRetry={() => void generate()}
          />
        ) : (
          <p role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</p>
        ))}
      {pipeline && (
        <div className="space-y-3 border-t pt-3">
          <p className="font-medium">{pipeline.selected_paper.title}</p>
          <p className="text-xs text-slate-500">
            信息范围：
            {pipeline.selected_paper.abstract_scope === "metadata_only"
              ? "仅元数据"
              : "元数据与摘要"}
          </p>
          {sections.map(([label, section]) => {
            const items = Array.isArray(section) ? section : [section];
            return (
              <div key={label}>
                <p className="font-medium">{label}</p>
                {items.map((item, index) => (
                  <div key={`${label}-${index}`} className="mt-1">
                    <p className="text-xs">
                      <ClassificationBadge classification={item.classification} /> {item.content}
                    </p>
                    <p className="text-xs text-slate-500">{item.source_scope}</p>
                  </div>
                ))}
              </div>
            );
          })}
          <div>
            <p className="font-medium">Python 学习任务（不执行代码）</p>
            {pipeline.tasks.map((task) => (
              <p key={task.task_id} className="text-xs">
                {task.title} · {linkedTaskIds.includes(task.task_id) || task.status === "evidence_linked"
                  ? "已关联用户实验记录（未核验）"
                  : "待用户记录"}
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
