"use client";

import { useState, useEffect, useCallback } from "react";
import { fetchNotebookItems, type NotebookItem } from "@/lib/api/learning";
import {
  Bookmark,
  X,
  Inbox,
  Clock,
  Sparkles,
  AlertTriangle,
  FileText,
  ExternalLink,
} from "lucide-react";

type TabId = "summary" | "note" | "wrong_answer";

interface StructuredNotebookProps {
  open: boolean;
  onDismiss: () => void;
  sessionId?: string;
}

export function StructuredNotebook({
  open,
  onDismiss,
  sessionId,
}: StructuredNotebookProps) {
  const [activeTab, setActiveTab] = useState<TabId>("summary");
  const [items, setItems] = useState<NotebookItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadItems = useCallback(async () => {
    if (!sessionId) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchNotebookItems(sessionId);
      setItems(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "加载笔记失败");
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    let cancelled = false;
    if (open && sessionId) {
      queueMicrotask(() => {
        if (!cancelled) void loadItems();
      });
    }
    return () => {
      cancelled = true;
    };
  }, [open, sessionId, loadItems]);

  if (!open) return null;

  const summaryItems = items.filter((i) => i.kind === "summary");
  const noteItems = items.filter((i) => i.kind === "note");
  const wrongAnswerItems = items.filter((i) => i.kind === "wrong_answer");

  const currentTabItems =
    activeTab === "summary"
      ? summaryItems
      : activeTab === "note"
      ? noteItems
      : wrongAnswerItems;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-xs transition-opacity animate-in fade-in duration-200"
        onClick={onDismiss}
      />

      {/* Slide Drawer */}
      <aside className="fixed right-0 top-0 bottom-0 z-50 flex w-[430px] max-w-[90vw] flex-col border-l border-slate-200/80 bg-white shadow-2xl transition-transform dark:border-zinc-800 dark:bg-zinc-900 animate-in slide-in-from-right duration-300">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-zinc-800">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-100 text-slate-700 dark:bg-zinc-800 dark:text-zinc-300">
              <Bookmark className="h-4 w-4 text-slate-700 dark:text-zinc-300" strokeWidth={1.5} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900 dark:text-zinc-100">
                结构化学术笔记
              </h3>
              <p className="text-[11px] font-mono text-slate-500 dark:text-zinc-400">
                {sessionId ? `会话编号：${sessionId}` : "正在初始化学习会话"}
              </p>
            </div>
          </div>
          <button
            onClick={onDismiss}
            aria-label="关闭"
            className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
          >
            <X className="h-4 w-4" strokeWidth={1.5} />
          </button>
        </div>

        {/* Tab triggers - Shadcn Standard Segmented Control */}
        <div className="p-4 border-b border-slate-100 dark:border-zinc-800/80">
          <div className="flex rounded-xl bg-slate-100/90 p-1 dark:bg-zinc-800/80 border border-slate-200/50 dark:border-zinc-700/40">
            <button
              onClick={() => setActiveTab("summary")}
              className={`flex-1 flex items-center justify-center gap-1.5 rounded-lg py-1.5 text-xs font-medium transition-all cursor-pointer ${
                activeTab === "summary"
                  ? "bg-white text-slate-900 shadow-2xs dark:bg-zinc-900 dark:text-zinc-100 font-semibold"
                  : "text-slate-500 hover:text-slate-700 dark:text-zinc-400 dark:hover:text-zinc-200"
              }`}
            >
              <Sparkles className="h-3 w-3" strokeWidth={1.5} />
              AI 客观摘要 ({summaryItems.length})
            </button>
            <button
              onClick={() => setActiveTab("note")}
              className={`flex-1 flex items-center justify-center gap-1.5 rounded-lg py-1.5 text-xs font-medium transition-all cursor-pointer ${
                activeTab === "note"
                  ? "bg-white text-slate-900 shadow-2xs dark:bg-zinc-900 dark:text-zinc-100 font-semibold"
                  : "text-slate-500 hover:text-slate-700 dark:text-zinc-400 dark:hover:text-zinc-200"
              }`}
            >
              <FileText className="h-3 w-3" strokeWidth={1.5} />
              时间戳手记 ({noteItems.length})
            </button>
            <button
              onClick={() => setActiveTab("wrong_answer")}
              className={`flex-1 flex items-center justify-center gap-1.5 rounded-lg py-1.5 text-xs font-medium transition-all cursor-pointer ${
                activeTab === "wrong_answer"
                  ? "bg-white text-slate-900 shadow-2xs dark:bg-zinc-900 dark:text-zinc-100 font-semibold"
                  : "text-slate-500 hover:text-slate-700 dark:text-zinc-400 dark:hover:text-zinc-200"
              }`}
            >
              <AlertTriangle className="h-3 w-3" strokeWidth={1.5} />
              错题本 ({wrongAnswerItems.length})
            </button>
          </div>
        </div>

        {/* Tab content area */}
        <div className="flex-1 overflow-y-auto p-4">
          {isLoading ? (
            /* High-grade Skeleton Screen Loading state */
            <div className="space-y-3">
              {[1, 2, 3].map((idx) => (
                <div
                  key={idx}
                  className="animate-pulse rounded-xl border border-slate-200/60 bg-slate-50 p-4 dark:border-zinc-800 dark:bg-zinc-800/40"
                >
                  <div className="mb-2 h-3.5 w-1/3 rounded bg-slate-200 dark:bg-zinc-700" />
                  <div className="mb-1.5 h-3 w-full rounded bg-slate-200 dark:bg-zinc-700" />
                  <div className="h-3 w-4/5 rounded bg-slate-200 dark:bg-zinc-700" />
                </div>
              ))}
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-12 text-red-500">
              <p className="text-xs">{error}</p>
            </div>
          ) : currentTabItems.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-slate-400 dark:text-zinc-500">
              <Inbox className="mb-2.5 h-9 w-9 text-slate-300 dark:text-zinc-600" strokeWidth={1.5} />
              <p className="text-xs font-medium">当前知识点暂无归档笔记</p>
            </div>
          ) : (
            <div className="space-y-3">
              {currentTabItems.map((item) => (
                <div
                  key={item.id}
                  className="rounded-xl border border-slate-200/60 bg-slate-50/50 p-4 dark:border-zinc-800 dark:bg-zinc-800/30"
                >
                  {item.timestamp && (
                    <div className="mb-2 flex items-center gap-1.5 text-[11px] text-slate-400 dark:text-zinc-500 font-mono">
                      <Clock className="h-3 w-3 text-slate-400" strokeWidth={1.5} />
                      {new Date(item.timestamp).toLocaleString("zh-CN")}
                    </div>
                  )}
                  <p className="text-xs leading-relaxed text-slate-700 dark:text-zinc-300">
                    {item.content}
                  </p>
                  {item.source_url && (
                    <a
                      href={item.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-2.5 inline-flex items-center gap-1 text-[11px] font-medium text-slate-700 hover:text-slate-900 hover:underline dark:text-zinc-300 dark:hover:text-white"
                    >
                      <span>查看原文</span>
                      <ExternalLink className="h-3 w-3" strokeWidth={1.5} />
                    </a>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}

