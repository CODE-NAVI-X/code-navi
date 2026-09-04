"use client";

import { Sparkles, ArrowUpRight, AlertCircle } from "lucide-react";
import type { DirectionCard } from "@/lib/api/research";

interface DirectionCardsBoxProps {
  cards: DirectionCard[];
  onSelectDirection: (text: string) => void;
  disabled?: boolean;
}

export function DirectionCardsBox({
  cards,
  onSelectDirection,
  disabled = false,
}: DirectionCardsBoxProps) {
  if (!cards || cards.length === 0) return null;

  return (
    <div
      role="region"
      aria-label="推荐探索方向卡片"
      className="my-4 rounded-2xl border border-indigo-200/80 bg-gradient-to-b from-indigo-50/70 to-slate-50/50 p-4 sm:p-5 shadow-sm dark:border-indigo-900/60 dark:from-indigo-950/20 dark:to-zinc-900/40 backdrop-blur-sm"
    >
      <div className="flex items-center gap-2 text-indigo-950 dark:text-indigo-200 mb-3">
        <Sparkles className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
        <h3 className="text-base font-bold">姜姜为你整理的动态探索方向</h3>
        <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-300 font-medium ml-auto">
          可点击直接选择
        </span>
      </div>

      <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((card) => (
          <button
            key={card.id}
            type="button"
            disabled={disabled}
            onClick={() => onSelectDirection(card.title)}
            className="group relative flex flex-col justify-between rounded-xl border border-slate-200/80 bg-white/90 p-3.5 text-left shadow-xs transition hover:-translate-y-0.5 hover:border-indigo-400 hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-800 dark:bg-zinc-900/90 dark:hover:border-indigo-600"
          >
            <div>
              <div className="flex items-start justify-between gap-2">
                <h4 className="font-bold text-sm text-slate-900 dark:text-zinc-100 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
                  {card.title}
                </h4>
                <ArrowUpRight className="h-4 w-4 shrink-0 text-slate-400 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-indigo-500" />
              </div>
              <p className="mt-1.5 text-xs leading-5 text-slate-600 dark:text-zinc-400">
                {card.description}
              </p>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-1.5 pt-2 border-t border-slate-100 dark:border-zinc-800/80">
              {card.is_recommended && (
                <span className="rounded-md bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
                  推荐方向
                </span>
              )}
              {card.prerequisite_gap && (
                <span className="inline-flex items-center gap-1 rounded-md bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950/40 dark:text-amber-300 truncate max-w-full">
                  <AlertCircle className="h-3 w-3 shrink-0" />
                  <span className="truncate">{card.prerequisite_gap}</span>
                </span>
              )}
            </div>
          </button>
        ))}
      </div>

      <p className="mt-3 text-center text-xs text-slate-500 dark:text-zinc-400">
        点击上方卡片快速选定，或在下方输入框自由描述你感兴趣的任何课题与想法。
      </p>
    </div>
  );
}
