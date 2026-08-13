"use client";

/**
 * Knowledge-PPT viewer: a thumbnail rail on the left plus a large slide
 * canvas. Pages appear incrementally as the backend finishes generating them —
 * the user can flip back to any already-finished page while later pages are
 * still streaming in (rendered as a shimmer placeholder until their event
 * arrives).
 */

import { useEffect, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Loader2,
  Presentation as PresentationIcon,
  Download,
  FileQuestion,
} from "lucide-react";
import type {
  PresentationGenerationMode,
  SceneOutline,
  Slide,
} from "@/lib/api/learning";
import { SlideRenderer } from "./SlideRenderer";

interface SlideViewerProps {
  knowledgePoint: string;
  outlines: SceneOutline[];
  slides: Slide[];
  generating: boolean;
  currentIndex: number;
  onNavigate: (index: number) => void;
  onExport?: () => void;
  exporting?: boolean;
  generationMode?: PresentationGenerationMode;
  providerName?: string;
  /**
   * When provided, a "generate companion exercises" action is rendered in the
   * top bar. Optional so the read-only preview in the notebook drawer stays
   * without it.
   */
  onGenerateQuiz?: () => void;
}

function ThumbPlaceholder() {
  return (
    <div className="flex aspect-video w-full animate-pulse items-center justify-center rounded-md bg-slate-100 dark:bg-zinc-800">
      <Loader2 className="h-4 w-4 animate-spin text-slate-400" strokeWidth={1.5} />
    </div>
  );
}

export function SlideViewer({
  knowledgePoint,
  outlines,
  slides,
  generating,
  currentIndex,
  onNavigate,
  onExport,
  exporting,
  generationMode,
  providerName,
  onGenerateQuiz,
}: SlideViewerProps) {
  const mainRef = useRef<HTMLDivElement>(null);
  const [mainWidth, setMainWidth] = useState(800);

  // Fit the large canvas to the available container width.
  useEffect(() => {
    const el = mainRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (width > 0) setMainWidth(Math.round(width));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const total = outlines.length;
  const hasCurrent = currentIndex < slides.length;
  const isGeneratingCurrent = generating && !hasCurrent && currentIndex === slides.length;

  const currentSlide = hasCurrent ? slides[currentIndex] : null;

  return (
    <div className="flex gap-5">
      {/* Thumbnail rail */}
      <div className="w-40 shrink-0 space-y-3">
        {outlines.map((outline, idx) => {
          const slide = slides[idx];
          const isActive = idx === currentIndex;
          const pending = !slide;
          return (
            <button
              key={outline.id}
              type="button"
              onClick={() => onNavigate(idx)}
              disabled={pending}
              className={`group w-full rounded-xl border p-1.5 text-left transition-all cursor-pointer ${
                isActive
                  ? "border-indigo-400 bg-indigo-50/60 dark:border-indigo-500 dark:bg-indigo-950/30"
                  : "border-slate-200/70 bg-white hover:border-slate-300 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-zinc-700"
              } ${pending ? "opacity-70" : ""}`}
            >
              {slide ? (
                <div className="pointer-events-none">
                  <SlideRenderer slide={slide} width={150} />
                </div>
              ) : (
                <ThumbPlaceholder />
              )}
              <p
                className={`mt-1.5 truncate px-0.5 text-[11px] font-medium ${
                  isActive
                    ? "text-indigo-700 dark:text-indigo-300"
                    : "text-slate-600 dark:text-zinc-400"
                }`}
              >
                {idx + 1}. {outline.title}
              </p>
              {pending && (
                <p className="px-0.5 pb-0.5 text-[10px] text-slate-400 dark:text-zinc-500">
                  {generating ? "生成中…" : "待生成"}
                </p>
              )}
            </button>
          );
        })}
      </div>

      {/* Main canvas */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-500 dark:text-zinc-400">
            <PresentationIcon className="h-4 w-4" strokeWidth={1.5} />
            <span className="truncate">{knowledgePoint}</span>
            <span className="shrink-0 rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[11px] dark:bg-zinc-800">
              {hasCurrent ? currentIndex + 1 : "·"} / {total}
            </span>
            {generationMode && (
              <span className="shrink-0 rounded-md bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
                {generationMode === "model"
                  ? `模型生成 · ${providerName ?? "provider"}`
                  : generationMode === "rules"
                    ? "离线规则生成"
                    : generationMode === "rules_fallback"
                      ? "模型失败 · 规则降级"
                      : `混合生成 · ${providerName ?? "provider"}`}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onNavigate(currentIndex - 1)}
              disabled={currentIndex <= 0}
              className="flex cursor-pointer items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
            >
              <ChevronLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
              上一页
            </button>
            <button
              type="button"
              onClick={() => onNavigate(currentIndex + 1)}
              disabled={!hasCurrent || currentIndex >= slides.length - 1}
              className="flex cursor-pointer items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
            >
              下一页
              <ChevronRight className="h-3.5 w-3.5" strokeWidth={1.5} />
            </button>
            {onGenerateQuiz && (
              <button
                type="button"
                onClick={onGenerateQuiz}
                className="flex cursor-pointer items-center gap-1.5 rounded-lg bg-gradient-to-r from-violet-600 to-purple-600 px-3 py-1.5 text-xs font-medium text-white transition hover:from-violet-500 hover:to-purple-500 dark:from-violet-500 dark:to-purple-500"
              >
                <FileQuestion className="h-3.5 w-3.5" strokeWidth={1.5} />
                根据 PPT 生成配套练习题
              </button>
            )}
            {onExport && (
              <button
                type="button"
                onClick={onExport}
                disabled={exporting || slides.length === 0}
                className="flex cursor-pointer items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
              >
                {exporting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={1.5} />
                ) : (
                  <Download className="h-3.5 w-3.5" strokeWidth={1.5} />
                )}
                导出 PPTX
              </button>
            )}
          </div>
        </div>

        <div className="mt-4 w-full" ref={mainRef}>
          {currentSlide ? (
            <SlideRenderer
              slide={currentSlide}
              width={mainWidth}
              className="shadow-xl"
            />
          ) : (
            <div className="flex aspect-video w-full flex-col items-center justify-center gap-3 rounded-xl border border-slate-200/80 bg-slate-50 text-slate-400 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-500">
              {isGeneratingCurrent ? (
                <>
                  <Loader2 className="h-8 w-8 animate-spin text-indigo-500" strokeWidth={1.5} />
                  <p className="text-xs font-medium">
                    正在生成第 {currentIndex + 1} / {total} 页…
                  </p>
                  <p className="text-[11px]">您可以先翻看已生成页面，后续页面到达后会自动就绪</p>
                </>
              ) : (
                <p className="text-xs font-medium">此页尚未生成</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
