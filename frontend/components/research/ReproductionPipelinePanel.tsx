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
import { GenerationFailure, isGenerationFailure } from "./generationUi";

type SavedPaper = ConversationEvidenceBundle["papers"][number] & {
  bundleId: string;
  selectionKey: string;
};

function arxivPdfUrl(arxivId: string | null | undefined): string | undefined {
  const normalized = (arxivId ?? "").replace(/^arxiv:/i, "").replace(/v\d+$/i, "");
  return /^\d{4}\.\d{4,5}$/.test(normalized)
    ? `https://arxiv.org/pdf/${normalized}.pdf`
    : undefined;
}

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
  const [paperPdfUrl, setPaperPdfUrl] = useState("");
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
          paper_pdf_url: paperPdfUrl || arxivPdfUrl(paper.arxiv_id) || null,
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
    <div className="space-y-5 rounded-xl border border-violet-200 bg-violet-50/40 p-5 text-base dark:border-violet-900 dark:bg-violet-950/20">
      <p className="text-xl font-semibold text-violet-950 dark:text-violet-100">复现方案</p>
      <p className="text-sm leading-6 text-violet-900 dark:text-violet-200">
        仅使用你已保存并主动选择的受限论文来源。不会联网、下载全文、运行代码或写入学生项目。
      </p>
      <label className="block text-base font-medium">
        选择已保存论文
        <select
          value={selected}
          onChange={(event) => setSelected(event.target.value)}
          className="mt-2 block min-h-10 w-full rounded border p-2 text-base"
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
        <p className="text-sm leading-6 text-amber-800 dark:text-amber-200">
          请先从已保存的受限来源中选择一篇论文，系统不会生成伪造方案。
        </p>
      )}
      <button
        type="button"
        disabled={!selected || busy}
        onClick={() => void generate()}
        className="min-h-10 rounded bg-violet-700 px-4 py-2 text-base font-semibold text-white disabled:opacity-50"
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
        <div className="space-y-5 border-t pt-5">
          <div>
            <p className="text-xl font-semibold">{pipeline.selected_paper.title}</p>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              信息范围：
              {pipeline.selected_paper.abstract_scope === "metadata_only"
                ? "仅元数据"
                : "元数据与摘要"}
            </p>
            {pipeline.paper_reading && <p className="mt-2 text-base leading-7 text-emerald-700 dark:text-emerald-300">已读取论文正文：{pipeline.paper_reading.pages_read} 页（{pipeline.paper_reading.source_url}）</p>}
          </div>
          <div className="space-y-4 rounded-lg border border-violet-200/80 bg-white/55 p-4 dark:border-violet-800/70 dark:bg-violet-950/25">
            <div>
              <p className="text-lg font-semibold">核心复现目标</p>
              <div className="mt-2 space-y-2 text-base leading-7">
                {[pipeline.reproduction_goal, pipeline.research_question, pipeline.known_method].map((item, index) => (
                  <p key={`goal-${index}`} className="whitespace-pre-line">
                    {item.content}
                  </p>
                ))}
              </div>
            </div>
            <div>
              <p className="text-lg font-semibold">数据、基线与指标</p>
              <div className="mt-2 space-y-2 text-base leading-7">
                {[...pipeline.data_and_sample_conditions, ...pipeline.candidate_baselines, ...pipeline.metrics].map((item, index) => (
                  <p key={`scope-${index}`} className="whitespace-pre-line">
                    {item.content}
                  </p>
                ))}
              </div>
            </div>
            <div>
              <p className="text-lg font-semibold">完整实验路径</p>
              <ol className="mt-2 list-decimal space-y-3 pl-6 text-base leading-7">
                {[...pipeline.experiment_steps, ...pipeline.two_week_mvp].map((item, index) => (
                  <li key={`path-${index}`}>
                    <span className="whitespace-pre-line">{item.content}</span>
                  </li>
                ))}
              </ol>
            </div>
          </div>
          <details className="rounded-lg border border-slate-200 bg-white/45 p-4 dark:border-slate-700 dark:bg-slate-950/20">
            <summary className="cursor-pointer text-base font-semibold">查看完整依据与待核对项</summary>
            <div className="mt-4 space-y-4">
              {sections.map(([label, section]) => {
                const items = Array.isArray(section) ? section : [section];
                return (
                  <div key={label}>
                    <p className="text-lg font-semibold">{label}</p>
                    {items.map((item, index) => (
                      <div key={`${label}-${index}`} className="mt-2">
                        <p className="text-base leading-7">
                          <span className="whitespace-pre-line">{item.content}</span>
                        </p>
                        <p className="text-sm text-slate-600 dark:text-slate-300">来源范围：{item.source_scope}</p>
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </details>
          <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-700">
            <p className="text-lg font-semibold">Python 学习任务（不执行代码）</p>
            <div className="mt-2 space-y-2 text-base leading-7">
              {pipeline.tasks.map((task) => (
                <p key={task.task_id}>
                  {task.title} · {linkedTaskIds.includes(task.task_id) || task.status === "evidence_linked"
                    ? "已关联用户实验记录（未核验）"
                    : "待用户记录"}
                </p>
              ))}
            </div>
          </div>
        </div>
      )}
      {selected && <input value={paperPdfUrl} onChange={(event) => setPaperPdfUrl(event.target.value)} placeholder="可选：公开 arXiv PDF 地址（提供后会先读正文）" aria-label="论文公开 PDF 地址" className="app-input min-h-10 w-full rounded px-3 py-2 text-base" />}
    </div>
  );
}
