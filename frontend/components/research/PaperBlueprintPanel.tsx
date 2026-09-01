"use client";

import { FileText, Loader2 } from "lucide-react";
import { useState } from "react";

import {
  generatePaperBlueprint,
  type AnalysisClassification,
  type PaperBlueprint,
} from "@/lib/api/research";
import { ClassificationBadge } from "./ClassificationBadge";
import { GenerationFailure, isGenerationFailure } from "./generationUi";

function EntryLabel({ classification }: { classification: AnalysisClassification }) {
  return <ClassificationBadge classification={classification} />;
}

export function PaperBlueprintPanel({
  conversationId,
}: {
  conversationId: string;
}) {
  const [blueprint, setBlueprint] = useState<PaperBlueprint | null>(null);
  const [buildingBlueprint, setBuildingBlueprint] = useState(false);
  const [blueprintError, setBlueprintError] = useState<string | null>(null);
  const [blueprintFailure, setBlueprintFailure] = useState(false);

  async function buildBlueprint() {
    setBuildingBlueprint(true);
    setBlueprintError(null);
    setBlueprintFailure(false);
    try {
      setBlueprint(await generatePaperBlueprint(conversationId));
    } catch (value) {
      setBlueprintFailure(isGenerationFailure(value));
      setBlueprintError(
        value instanceof Error ? value.message : "生成论文蓝图失败。请重试。",
      );
    } finally {
      setBuildingBlueprint(false);
    }
  }

  return (
    <section className="app-card rounded-2xl p-4">
      <div className="flex items-center gap-3">
        <span className="rounded-xl bg-slate-100 p-2 text-slate-700 dark:bg-zinc-800 dark:text-zinc-300">
          <FileText className="h-4 w-4" />
        </span>
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-zinc-400">
            Paper blueprint
          </p>
          <h2 className="mt-1 text-lg font-bold">论文蓝图（五段标准学术结构）</h2>
        </div>
      </div>
      <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-zinc-400">
        基于已保存的科研画像、受限文献与实验记录生成固定五段结构（摘要、介绍、文献综述、方法、实验）。不会联网、不下载论文全文、不生成或投稿论文正文。
      </p>
      <button
        type="button"
        onClick={() => void buildBlueprint()}
        disabled={buildingBlueprint}
        className="app-button-primary mt-4 inline-flex min-h-10 items-center gap-1 rounded-xl px-3 py-2 text-sm font-bold disabled:opacity-50"
      >
        {buildingBlueprint ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <FileText className="h-3.5 w-3.5" />
        )}
        我确认生成论文蓝图
      </button>
      {blueprintError &&
        (blueprintFailure ? (
          <GenerationFailure
            error={blueprintError}
            busy={buildingBlueprint}
            hasLastSuccess={blueprint !== null}
            onRetry={() => void buildBlueprint()}
          />
        ) : (
          <p role="alert" className="mt-2 text-sm text-rose-600">
            {blueprintError}
          </p>
        ))}
      {blueprint && (
        <div className="app-card-subtle mt-3 rounded-xl p-3 text-base leading-7">
          <p className="font-bold">{blueprint.candidate_titles[0]?.content}</p>
          <p className="mt-1 text-sm">
            投稿就绪度：
            <EntryLabel classification={blueprint.submission_readiness.classification} /> ·{" "}
            {blueprint.submission_readiness.content}
          </p>
          {blueprint.sections.map((section) => (
            <details
              key={section.section}
              className="mt-2 rounded-lg bg-slate-50 p-2 dark:bg-zinc-950/50"
            >
              <summary className="min-h-10 cursor-pointer py-2 font-semibold">
                {section.section}：{section.writing_goal.content}
              </summary>
              <p className="mt-1 text-sm">
                可用证据：
                {section.evidence_references.length
                  ? section.evidence_references
                      .map((reference) => reference.label)
                      .join("；")
                  : "暂无"}
              </p>
              <p className="mt-1 text-sm">
                待补充：
                {section.missing_evidence.map((item) => item.content).join("；") || "无"}
              </p>
            </details>
          ))}
          <p className="mt-2 text-sm text-slate-500">{blueprint.provenance_note}</p>
        </div>
      )}
    </section>
  );
}
