"use client";

import { type KeyboardEvent as ReactKeyboardEvent, useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  fetchNotebookItems,
  fetchPresentation,
  type NotebookItem,
  type PresentationDetail,
} from "@/lib/api/learning";
import { createLearningToResearchContext } from "@/lib/api/context-transfers";
import { SlideViewer } from "@/components/learning/presentation/SlideViewer";
import {
  Bookmark,
  X,
  Inbox,
  Clock,
  Sparkles,
  AlertTriangle,
  FileText,
  ExternalLink,
  Presentation,
  Loader2,
  GraduationCap,
  Microscope,
} from "lucide-react";

type TabId = "summary" | "note" | "research_note" | "wrong_answer" | "presentation";

interface StructuredNotebookProps {
  open: boolean;
  onDismiss: () => void;
  sessionId?: string;
  initialTab?: TabId;
}

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function cycleDialogFocus(
  event: { key: string; shiftKey: boolean; preventDefault: () => void },
  container: HTMLElement | null,
) {
  if (event.key !== "Tab" || !container) return;
  const focusable = Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
  if (focusable.length === 0) {
    event.preventDefault();
    return;
  }

  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  const active = document.activeElement;
  if (event.shiftKey && (active === first || !container.contains(active))) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (active === last || !container.contains(active))) {
    event.preventDefault();
    first.focus();
  }
}

function PresentationPreviewOverlay({
  detail,
  onClose,
  returnFocusTarget,
}: {
  detail: PresentationDetail;
  onClose: () => void;
  returnFocusTarget: HTMLElement | null;
}) {
  const [idx, setIdx] = useState(0);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef(onClose);

  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const fallbackFocusTarget =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const timeoutId = window.setTimeout(() => closeButtonRef.current?.focus(), 0);
    return () => {
      window.clearTimeout(timeoutId);
      const target = returnFocusTarget?.isConnected ? returnFocusTarget : fallbackFocusTarget;
      if (target?.isConnected) target.focus();
    };
  }, [returnFocusTarget]);

  function handleKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closeRef.current();
      return;
    }
    cycleDialogFocus(event, dialogRef.current);
  }

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm sm:p-8"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="presentation-preview-title"
        ref={dialogRef}
        className="app-card max-h-[92vh] w-full max-w-5xl overflow-auto rounded-2xl p-5 shadow-2xl sm:p-6"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-700 dark:bg-zinc-800 dark:text-zinc-200">
              <Presentation className="h-4 w-4" strokeWidth={1.5} />
            </div>
            <div className="min-w-0">
              <h4 id="presentation-preview-title" className="truncate text-sm font-bold text-slate-900 dark:text-zinc-100">
                {detail.knowledge_point}
              </h4>
              <p className="text-[11px] text-slate-400 dark:text-zinc-500">
                共 {detail.slides.length} 页 · 历史 PPT 预览
              </p>
            </div>
          </div>
          <button
            type="button"
            ref={closeButtonRef}
            onClick={onClose}
            aria-label="关闭预览"
            className="flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
          >
            <X className="h-4 w-4" strokeWidth={1.5} />
          </button>
        </div>
        {detail.slides.length > 0 ? (
          <SlideViewer
            knowledgePoint={detail.knowledge_point}
            outlines={detail.outlines.length > 0 ? detail.outlines : detail.slides.map((_, i) => ({
              id: `slide_${i + 1}`,
              title: `第 ${i + 1} 页`,
              description: "",
              key_points: [],
              order: i + 1,
            }))}
            slides={detail.slides}
            generating={false}
            currentIndex={idx}
            onNavigate={setIdx}
            generationMode={detail.generation_mode}
            providerName={detail.provider_name}
          />
        ) : (
          <p className="py-16 text-center text-xs text-slate-400">此 PPT 无内容</p>
        )}
      </div>
    </div>
  );
}

export function StructuredNotebook({
  open,
  onDismiss,
  sessionId,
  initialTab = "summary",
}: StructuredNotebookProps) {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<TabId>(initialTab);
  const [items, setItems] = useState<NotebookItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<PresentationDetail | null>(null);
  const [previewFocusTarget, setPreviewFocusTarget] = useState<HTMLElement | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [transferringItemId, setTransferringItemId] = useState<string | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const drawerRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) return;
    previousFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const timeoutId = window.setTimeout(() => closeButtonRef.current?.focus(), 0);
    return () => {
      window.clearTimeout(timeoutId);
      if (previousFocusRef.current?.isConnected) previousFocusRef.current.focus();
    };
  }, [open]);

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

  async function openPresentation(item: NotebookItem, trigger: HTMLButtonElement) {
    if (!sessionId || !item.presentation_id) return;
    setPreviewFocusTarget(trigger);
    setLoadingPreview(true);
    setError(null);
    try {
      const detail = await fetchPresentation(item.presentation_id, sessionId);
      setPreview(detail);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "加载 PPT 失败");
    } finally {
      setLoadingPreview(false);
    }
  }

  async function continueToResearch(item: NotebookItem) {
    if (!sessionId) return;
    setTransferringItemId(item.id);
    setError(null);
    try {
      const context = await createLearningToResearchContext(item.id, sessionId);
      router.push(`/research/confirm/${encodeURIComponent(context.id)}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "创建待传递上下文失败");
      setTransferringItemId(null);
    }
  }

  if (!open) return null;

  function handleNotebookKeyDown(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      onDismiss();
      return;
    }
    cycleDialogFocus(event, drawerRef.current);
  }

  const summaryItems = items.filter((i) => i.kind === "summary");
  const noteItems = items.filter((i) => i.kind === "note");
  const researchNoteItems = items.filter((i) => i.kind === "research_note");
  const wrongAnswerItems = items.filter((i) => i.kind === "wrong_answer");
  const presentationItems = items.filter((i) => i.kind === "presentation");

  const currentTabItems =
    activeTab === "summary"
      ? summaryItems
      : activeTab === "note"
      ? noteItems
      : activeTab === "research_note"
      ? researchNoteItems
      : activeTab === "wrong_answer"
      ? wrongAnswerItems
      : presentationItems;

  const tabs: { id: TabId; label: string; icon: typeof Sparkles; count: number }[] = [
    { id: "summary", label: "AI 客观摘要", icon: Sparkles, count: summaryItems.length },
    { id: "note", label: "时间戳手记", icon: FileText, count: noteItems.length },
    { id: "research_note", label: "研究笔记", icon: Microscope, count: researchNoteItems.length },
    { id: "wrong_answer", label: "错题本", icon: AlertTriangle, count: wrongAnswerItems.length },
    { id: "presentation", label: "PPT 课件", icon: Presentation, count: presentationItems.length },
  ];

  return (
    <>
      {/* Backdrop */}
      <div
        aria-hidden="true"
        className="fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-xs transition-opacity animate-in fade-in duration-200"
        onClick={onDismiss}
      />

      {/* Slide Drawer */}
      <aside ref={drawerRef} role="dialog" aria-modal="true" aria-hidden={preview ? true : undefined} aria-labelledby="structured-notebook-title" onKeyDown={handleNotebookKeyDown} className="fixed right-0 top-0 bottom-0 z-50 flex w-[430px] max-w-[90vw] flex-col border-l border-[var(--app-border)] bg-[var(--app-card)] shadow-2xl transition-transform animate-in slide-in-from-right duration-300">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-zinc-800">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-100 text-slate-700 dark:bg-zinc-800 dark:text-zinc-300">
              <Bookmark className="h-4 w-4 text-slate-700 dark:text-zinc-300" strokeWidth={1.5} />
            </div>
            <div>
              <h3 id="structured-notebook-title" className="text-sm font-bold text-slate-900 dark:text-zinc-100">
                结构化学术笔记
              </h3>
              <p className="text-[11px] font-mono text-slate-500 dark:text-zinc-400">
                {sessionId ? `会话编号：${sessionId}` : "正在初始化学习会话"}
              </p>
            </div>
          </div>
          <button
            ref={closeButtonRef}
            onClick={onDismiss}
            aria-label="关闭"
            className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
          >
            <X className="h-4 w-4" strokeWidth={1.5} />
          </button>
        </div>

        {/* Tab triggers - Shadcn Standard Segmented Control */}
        <div className="p-4 border-b border-slate-100 dark:border-zinc-800/80">
          <div className="grid grid-cols-5 rounded-xl bg-slate-100/90 p-1 dark:bg-zinc-800/80 border border-slate-200/50 dark:border-zinc-700/40">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex flex-col items-center justify-center gap-1 rounded-lg py-1.5 text-[11px] font-medium transition-all cursor-pointer ${
                    isActive
                      ? "bg-white text-slate-900 shadow-2xs dark:bg-zinc-900 dark:text-zinc-100 font-semibold"
                      : "text-slate-500 hover:text-slate-700 dark:text-zinc-400 dark:hover:text-zinc-200"
                  }`}
                >
                  <Icon className="h-3 w-3" strokeWidth={1.5} />
                  {tab.label}
                  <span className="font-mono text-[10px] opacity-70">{tab.count}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Tab content area */}
        <div className="flex-1 overflow-y-auto p-4">
          {isLoading ? (
            /* High-grade Skeleton Screen Loading state */
            <div role="status" aria-live="polite" className="space-y-3">
              {[1, 2, 3].map((idx) => (
                <div
                  key={idx}
                  className="app-card-subtle animate-pulse rounded-xl p-4"
                >
                  <div className="mb-2 h-3.5 w-1/3 rounded bg-slate-200 dark:bg-zinc-700" />
                  <div className="mb-1.5 h-3 w-full rounded bg-slate-200 dark:bg-zinc-700" />
                  <div className="h-3 w-4/5 rounded bg-slate-200 dark:bg-zinc-700" />
                </div>
              ))}
            </div>
          ) : error ? (
            <div role="alert" className="flex flex-col items-center justify-center py-12 text-red-500">
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
                <article
                  key={item.id}
                  className="app-card-subtle block w-full rounded-xl p-4 text-left"
                >
                  {item.timestamp && (
                    <div className="mb-2 flex items-center gap-1.5 text-[11px] text-slate-400 dark:text-zinc-500 font-mono">
                      <Clock className="h-3 w-3 text-slate-400" strokeWidth={1.5} />
                      {new Date(item.timestamp).toLocaleString("zh-CN")}
                    </div>
                  )}
                  {item.kind === "presentation" && (
                    <div className="mb-1.5 flex items-center gap-1.5">
                      <Presentation className="h-3 w-3 text-slate-500 dark:text-zinc-400" strokeWidth={1.5} />
                      <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-zinc-400">
                        PPT 课件 · 点击预览
                      </span>
                    </div>
                  )}
                  {item.kind === "research_note" && (
                    <div className="mb-2 flex items-center gap-1.5">
                      <Microscope className="h-3 w-3 text-emerald-600" strokeWidth={1.5} />
                      <span className="text-[10px] font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-400">
                        Research Conversation 研究笔记
                      </span>
                    </div>
                  )}
                  {item.kind === "research_note" && item.research_note ? (
                    <div className="space-y-2 text-xs leading-relaxed text-slate-700 dark:text-zinc-300">
                      <p className="font-semibold text-slate-900 dark:text-zinc-100">{item.research_note.research_topic}</p>
                      <p className="line-clamp-4">研究问题：{item.research_note.research_question}</p>
                      <div>
                        <p className="font-semibold">下一步建议</p>
                        <ol className="mt-1 list-decimal space-y-1 pl-4">
                          {item.research_note.next_steps.map((step) => <li key={step}>{step}</li>)}
                        </ol>
                      </div>
                    </div>
                  ) : (
                    <p className="whitespace-pre-line text-xs leading-relaxed text-slate-700 dark:text-zinc-300">
                      {item.content}
                    </p>
                  )}
                  {item.source_url && (
                    <a href={item.source_url} target="_blank" rel="noreferrer" className="mt-2.5 inline-flex items-center gap-1 text-[11px] font-medium text-slate-700 hover:text-slate-900 hover:underline dark:text-zinc-300 dark:hover:text-white">
                      <span>查看原文</span>
                      <ExternalLink className="h-3 w-3" strokeWidth={1.5} />
                    </a>
                  )}
                  {item.kind === "research_note" && item.research_note && (
                    <div className="mt-3 space-y-2 border-t border-slate-200 pt-3 text-[11px] dark:border-zinc-700">
                      <p className="font-semibold text-slate-700 dark:text-zinc-200">Evidence 来源</p>
                      {item.research_note.evidence_refs.map((reference) => (
                        <a key={`${reference.bundle_id}:${reference.paper_url}`} href={reference.paper_url} target="_blank" rel="noreferrer" className="flex items-start justify-between gap-2 text-sky-700 hover:underline dark:text-sky-300">
                          <span>{reference.title}{reference.evidence_summary ? <span className="mt-1 line-clamp-3 font-normal text-slate-500 dark:text-zinc-400">{reference.evidence_summary}</span> : null}</span>
                          <span className="shrink-0 text-slate-400">{reference.source_name} · {reference.evidence_level === "abstract" ? "摘要级" : "元数据级"}</span>
                        </a>
                      ))}
                      <p className="text-slate-500 dark:text-zinc-400">Conversation：{item.research_note.conversation_id}</p>
                    </div>
                  )}
                  <div className="mt-3 flex flex-wrap gap-2">
                    {item.kind === "presentation" && (
                      <button
                        type="button"
                        onClick={(event) => void openPresentation(item, event.currentTarget)}
                        className="app-button-secondary inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-semibold hover:bg-slate-50 dark:hover:bg-zinc-800"
                      >
                        <Presentation className="h-3 w-3" /> 预览课件
                      </button>
                    )}
                    {item.kind === "summary" && (
                      <button
                        type="button"
                        onClick={() => void continueToResearch(item)}
                        disabled={transferringItemId !== null}
                        className="app-button-primary inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-semibold disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {transferringItemId === item.id ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <GraduationCap className="h-3 w-3" />
                        )}
                        继续研究
                      </button>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      </aside>

      {/* Fullscreen presentation preview */}
      {loadingPreview && (
        <div role="status" aria-live="polite" className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/60 backdrop-blur-sm">
          <Loader2 className="h-8 w-8 animate-spin text-white" strokeWidth={1.5} />
        </div>
      )}
      {preview && !loadingPreview && (
        <PresentationPreviewOverlay
          detail={preview}
          onClose={() => setPreview(null)}
          returnFocusTarget={previewFocusTarget}
        />
      )}
    </>
  );
}
