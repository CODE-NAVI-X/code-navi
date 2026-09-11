"use client";

import {
  type KeyboardEvent as ReactKeyboardEvent,
  useState,
  useEffect,
  useCallback,
  useRef,
  useSyncExternalStore,
} from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import {
  fetchNotebookItems,
  fetchPresentation,
  type NotebookItem,
  type PresentationDetail,
} from "@/lib/api/learning";
import { createLearningToResearchContext } from "@/lib/api/context-transfers";
import { SlideViewer } from "@/components/learning/presentation/SlideViewer";
import { MathContent } from "@/components/learning/MathContent";
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

export type NotebookTab = "summary" | "note" | "research_note" | "wrong_answer" | "presentation";

export const LEARNING_NOTEBOOK_OPEN_EVENT = "code-navi:open-learning-notebook";

/** Open the shared Learning notebook without coupling callers to its Drawer state. */
export function openLearningNotebook(tab: NotebookTab = "summary"): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent<{ tab: NotebookTab }>(LEARNING_NOTEBOOK_OPEN_EVENT, {
      detail: { tab },
    }),
  );
}

interface StructuredNotebookProps {
  open: boolean;
  onDismiss: () => void;
  sessionId?: string;
  initialTab?: NotebookTab;
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
      className="fixed inset-0 z-[120] flex items-center justify-center bg-black/75 p-4 backdrop-blur-md sm:p-8"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="presentation-preview-title"
        ref={dialogRef}
        className="max-h-[92vh] w-full max-w-5xl overflow-auto rounded-2xl border border-white/15 bg-[#120f20]/95 p-5 text-white shadow-2xl backdrop-blur-2xl sm:p-6"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <div className="mb-4 flex items-center justify-between gap-3 border-b border-white/10 pb-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/10 text-white border border-white/12">
              <Presentation className="h-4 w-4" strokeWidth={1.5} />
            </div>
            <div className="min-w-0">
              <h4 id="presentation-preview-title" className="truncate text-sm font-bold text-white">
                {detail.knowledge_point}
              </h4>
              <p className="text-[11px] text-zinc-400">
                共 {detail.slides.length} 页 · 历史 PPT 预览
              </p>
            </div>
          </div>
          <button
            type="button"
            ref={closeButtonRef}
            onClick={onClose}
            aria-label="关闭预览"
            className="flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-lg border border-white/10 bg-white/5 text-zinc-400 transition hover:bg-white/15 hover:text-white"
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

const emptySubscribe = () => () => {};

function useClientMounted() {
  return useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );
}

export function StructuredNotebook({
  open,
  onDismiss,
  sessionId,
  initialTab = "summary",
}: StructuredNotebookProps) {
  const router = useRouter();
  const mounted = useClientMounted();
  const [activeTab, setActiveTab] = useState<NotebookTab>(initialTab);
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

  if (!open || !mounted) return null;

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

  const tabs: { id: NotebookTab; label: string; icon: typeof Sparkles; count: number }[] = [
    { id: "summary", label: "AI 客观摘要", icon: Sparkles, count: summaryItems.length },
    { id: "note", label: "时间戳手记", icon: FileText, count: noteItems.length },
    { id: "research_note", label: "研究笔记", icon: Microscope, count: researchNoteItems.length },
    { id: "wrong_answer", label: "错题本", icon: AlertTriangle, count: wrongAnswerItems.length },
    { id: "presentation", label: "PPT 课件", icon: Presentation, count: presentationItems.length },
  ];

  return createPortal(
    <>
      {/* Backdrop */}
      <div
        aria-hidden="true"
        className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm transition-opacity animate-in fade-in duration-200"
        onClick={onDismiss}
      />

      {/* Slide Drawer */}
      <aside
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-hidden={preview ? true : undefined}
        aria-labelledby="structured-notebook-title"
        onKeyDown={handleNotebookKeyDown}
        className="fixed right-0 top-0 bottom-0 z-[101] flex h-full max-h-screen w-[490px] max-w-[94vw] flex-col border-l border-white/10 bg-[#0e0c1a]/95 text-white backdrop-blur-2xl shadow-2xl transition-transform animate-in slide-in-from-right duration-300"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/10 px-6 py-4.5 bg-white/[0.02]">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/5 border border-white/10 text-purple-300 shadow-inner">
              <Bookmark className="h-5 w-5" strokeWidth={1.8} />
            </div>
            <div>
              <h3 id="structured-notebook-title" className="text-base font-bold text-white tracking-tight">
                结构化学术笔记
              </h3>
              <p className="text-[11px] font-mono text-zinc-400 mt-0.5">
                {sessionId ? `会话编号：${sessionId}` : "正在初始化学习会话"}
              </p>
            </div>
          </div>
          <button
            ref={closeButtonRef}
            onClick={onDismiss}
            aria-label="关闭"
            className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg border border-white/10 bg-white/5 text-zinc-400 transition hover:bg-white/15 hover:text-white active:scale-95"
          >
            <X className="h-4 w-4" strokeWidth={1.75} />
          </button>
        </div>

        {/* Tab triggers - Galaxy Fluid Capsules */}
        <div className="border-b border-white/10 px-5 py-3 bg-white/[0.01]">
          <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition cursor-pointer ${
                    isActive
                      ? "bg-white text-zinc-950 font-bold shadow-md"
                      : "border border-white/10 bg-white/5 text-zinc-300 hover:bg-white/10 hover:text-white"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" strokeWidth={1.75} />
                  <span>{tab.label}</span>
                  <span className={`rounded-full px-1.5 py-0.2 text-[10px] font-mono ${isActive ? "bg-zinc-900 text-white" : "bg-white/10 text-zinc-400"}`}>
                    {tab.count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Tab content area */}
        <div className="flex-1 overflow-y-auto p-5 space-y-3.5">
          {isLoading ? (
            <div role="status" aria-live="polite" className="space-y-3">
              {[1, 2, 3].map((idx) => (
                <div
                  key={idx}
                  className="animate-pulse rounded-xl border border-white/10 bg-white/5 p-4.5"
                >
                  <div className="mb-2 h-3.5 w-1/3 rounded bg-white/10" />
                  <div className="mb-1.5 h-3 w-full rounded bg-white/10" />
                  <div className="h-3 w-4/5 rounded bg-white/10" />
                </div>
              ))}
            </div>
          ) : error ? (
            <div role="alert" className="flex flex-col items-center justify-center py-12 text-rose-400">
              <p className="text-xs">{error}</p>
            </div>
          ) : currentTabItems.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-zinc-400">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-white/5 border border-white/10 mb-3 text-zinc-400">
                <Inbox className="h-7 w-7" strokeWidth={1.5} />
              </div>
              <p className="text-xs font-medium text-zinc-300">当前分类暂无归档笔记</p>
              <p className="text-[11px] text-zinc-500 mt-1">在学习过程中划词提炼或生成 PPT，内容将自动沉淀于此</p>
            </div>
          ) : (
            <div className="space-y-3.5">
              {currentTabItems.map((item) => (
                <article
                  key={item.id}
                  className="galaxy-card block w-full p-4.5 text-left transition hover:border-white/20"
                >
                  {item.timestamp && (
                    <div className="mb-2 flex items-center gap-1.5 text-[11px] text-zinc-400 font-mono">
                      <Clock className="h-3 w-3 text-zinc-500" strokeWidth={1.5} />
                      {new Date(item.timestamp).toLocaleString("zh-CN")}
                    </div>
                  )}
                  {item.kind === "presentation" && (
                    <div className="mb-2 flex items-center gap-1.5">
                      <Presentation className="h-3.5 w-3.5 text-purple-300" strokeWidth={1.5} />
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-purple-300">
                        PPT 课件 · 点击预览
                      </span>
                    </div>
                  )}
                  {item.kind === "research_note" && (
                    <div className="mb-2 flex items-center gap-1.5">
                      <Microscope className="h-3.5 w-3.5 text-emerald-400" strokeWidth={1.5} />
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-emerald-400">
                        Research Conversation 研究笔记
                      </span>
                    </div>
                  )}
                  {item.kind === "research_note" && item.research_note ? (
                    <div className="space-y-2 text-xs leading-relaxed text-zinc-300">
                      <p className="font-semibold text-white text-sm">{item.research_note.research_topic}</p>
                      <p className="line-clamp-4 text-zinc-300">研究问题：{item.research_note.research_question}</p>
                      <div className="rounded-lg bg-white/[0.03] border border-white/8 p-2.5">
                        <p className="font-semibold text-zinc-200">下一步建议</p>
                        <ol className="mt-1 list-decimal space-y-1 pl-4 text-zinc-400">
                          {item.research_note.next_steps.map((step) => <li key={step}>{step}</li>)}
                        </ol>
                      </div>
                    </div>
                  ) : (
                    <div className="text-xs leading-relaxed text-zinc-200 whitespace-pre-line">
                      <MathContent text={item.content} />
                    </div>
                  )}
                  {item.source_url && (
                    <a
                      href={item.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-3 inline-flex items-center gap-1.5 text-[11px] font-semibold text-purple-300 hover:text-purple-200 transition-colors"
                    >
                      <span>查看原文</span>
                      <ExternalLink className="h-3 w-3" strokeWidth={1.5} />
                    </a>
                  )}
                  {item.kind === "research_note" && item.research_note && (
                    <div className="mt-3 space-y-2 border-t border-white/10 pt-3 text-[11px]">
                      <p className="font-semibold text-zinc-300">Evidence 来源</p>
                      {item.research_note.evidence_refs.map((reference) => (
                        <a
                          key={`${reference.bundle_id}:${reference.paper_url}`}
                          href={reference.paper_url}
                          target="_blank"
                          rel="noreferrer"
                          className="flex items-start justify-between gap-2 text-indigo-300 hover:text-indigo-200 transition"
                        >
                          <span className="truncate">{reference.title}</span>
                          <span className="shrink-0 text-zinc-400">{reference.source_name}</span>
                        </a>
                      ))}
                    </div>
                  )}
                  <div className="mt-3 flex flex-wrap gap-2">
                    {item.kind === "presentation" && (
                      <button
                        type="button"
                        onClick={(event) => void openPresentation(item, event.currentTarget)}
                        className="inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-white/10 px-3.5 py-1.5 text-xs font-semibold text-white transition hover:bg-white/20 active:scale-95 cursor-pointer"
                      >
                        <Presentation className="h-3.5 w-3.5" />
                        <span>预览课件</span>
                      </button>
                    )}
                    {item.kind === "summary" && (
                      <button
                        type="button"
                        onClick={() => void continueToResearch(item)}
                        disabled={transferringItemId !== null}
                        className="inline-flex items-center gap-1.5 rounded-full bg-white px-3.5 py-1.5 text-xs font-bold text-zinc-950 transition hover:bg-zinc-100 hover:scale-105 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
                      >
                        {transferringItemId === item.id ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <GraduationCap className="h-3.5 w-3.5" />
                        )}
                        <span>继续研究</span>
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
        <div role="status" aria-live="polite" className="fixed inset-0 z-[120] flex items-center justify-center bg-black/70 backdrop-blur-md">
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
    </>,
    document.body,
  );
}
