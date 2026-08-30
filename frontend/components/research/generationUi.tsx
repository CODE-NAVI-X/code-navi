"use client";

import { CircleAlert, Loader2, RotateCcw } from "lucide-react";

import { ResearchApiError } from "@/lib/api/research";

export const GENERATION_MODE_LABELS: Record<string, string> = {
  llm: "模型生成",
  rules: "基础规则",
};

export function generationModeLabel(mode: string): string {
  return GENERATION_MODE_LABELS[mode] ?? "基础规则";
}

export function isGenerationFailure(error: unknown): boolean {
  return error instanceof ResearchApiError && error.isGenerationFailure;
}

export function GenerationFailure({
  error,
  busy,
  hasLastSuccess,
  onRetry,
}: {
  error: string;
  busy: boolean;
  hasLastSuccess: boolean;
  onRetry: () => void;
}) {
  return (
    <div
      role="alert"
      className="mt-3 rounded-xl border border-rose-200 bg-rose-50/70 p-4 text-sm leading-6 text-rose-900 dark:border-rose-900/60 dark:bg-rose-950/20 dark:text-rose-200"
    >
      <p className="flex items-center gap-2 font-semibold">
        <CircleAlert className="h-4 w-4" /> 本次模型生成失败
      </p>
      <p className="mt-1">{error}</p>
      <p className="mt-1 text-rose-800/90 dark:text-rose-200/80">
        {hasLastSuccess
          ? "已保留并继续展示上一次成功生成的结果；可重试生成最新内容。"
          : "本次未生成科研建议，请重试。"}
      </p>
      <button
        type="button"
        onClick={onRetry}
        disabled={busy}
        className="app-button-secondary mt-3 inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-semibold disabled:opacity-50"
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
        重试生成
      </button>
    </div>
  );
}
