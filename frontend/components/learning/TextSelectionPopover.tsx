"use client";

import {
  type ExplainResponse,
  explainKnowledgePoint,
  LearningApiError,
} from "@/lib/api/learning";
import {
  type JSX,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { X, Sparkles, Loader2, BookOpen, AlertCircle } from "lucide-react";

// ── Constants ──────────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 300;
const POPOVER_GAP = 8; // px above the selection bounding rect

// ── Types ──────────────────────────────────────────────────────────────────────

interface SelectionRect {
  top: number;
  left: number;
  width: number;
  placeBelow?: boolean;
}

// ── Popover component ──────────────────────────────────────────────────────────

/** Floating bubble that appears when the user selects text on the page. */
export default function TextSelectionPopover(): JSX.Element | null {
  const [selectedText, setSelectedText] = useState<string | null>(null);
  const [position, setPosition] = useState<SelectionRect | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ExplainResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  // ── Hide helpers ────────────────────────────────────────────────────────

  const dismiss = useCallback(() => {
    setSelectedText(null);
    setPosition(null);
    setResult(null);
    setError(null);
    setLoading(false);
  }, []);

  // ── Click-outside handler ───────────────────────────────────────────────

  useEffect(() => {
    if (!selectedText) return;

    function onPointerDown(e: PointerEvent) {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node)
      ) {
        dismiss();
      }
    }

    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [selectedText, dismiss]);

  // ── Scroll handler ──────────────────────────────────────────────────────

  useEffect(() => {
    if (!selectedText) return;

    function onScroll() {
      dismiss();
    }

    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [selectedText, dismiss]);

  // ── Selection listener (debounced) ──────────────────────────────────────

  useEffect(() => {
    function handleSelectionChange() {
      // Clear any pending timer
      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
      }

      debounceTimer.current = setTimeout(() => {
        debounceTimer.current = null;

        const sel = window.getSelection();
        if (!sel || sel.isCollapsed || !sel.toString().trim()) {
          setSelectedText((prev) => (prev ? null : prev)); // no-op if already hidden
          setPosition(null);
          setResult(null);
          setError(null);
          return;
        }

        const text = sel.toString().trim();
        if (!text) {
          setSelectedText((prev) => (prev ? null : prev));
          setPosition(null);
          return;
        }

        // Clamp to 200 chars so the API isn't swamped with huge selections
        const clamped = text.length > 200 ? text.slice(0, 200) + "…" : text;

        // Get bounding rect of the *first* range
        const range = sel.getRangeAt(0);
        const rect = range.getBoundingClientRect();

        // Calculate position with collision padding (16px) & vertical flip
        const padding = 16;
        const estimatedHeight = 180;
        const estimatedWidth = 340;
        const halfWidth = estimatedWidth / 2;

        let left = rect.left + rect.width / 2;
        let top = rect.top - POPOVER_GAP;
        let placeBelow = false;

        // If placing above would overflow top of viewport, flip to place below selection
        if (rect.top - estimatedHeight < padding) {
          top = rect.bottom + POPOVER_GAP;
          placeBelow = true;
        }

        // Clamp horizontal position to prevent overflow off left/right edges
        if (left - halfWidth < padding) {
          left = padding + halfWidth;
        } else if (left + halfWidth > window.innerWidth - padding) {
          left = window.innerWidth - padding - halfWidth;
        }

        setSelectedText(clamped);
        setPosition({
          top,
          left,
          width: rect.width,
          placeBelow,
        });
        setResult(null);
        setError(null);
      }, DEBOUNCE_MS);
    }

    document.addEventListener("selectionchange", handleSelectionChange);
    return () => {
      document.removeEventListener("selectionchange", handleSelectionChange);
      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
        debounceTimer.current = null;
      }
    };
  }, []);

  // ── API call ────────────────────────────────────────────────────────────

  async function handleExplain() {
    if (!selectedText) return;
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await explainKnowledgePoint({
        knowledge_point: selectedText,
        include_citations: true,
      });
      setResult(data);
    } catch (err) {
      setError(
        err instanceof LearningApiError ? err.message : String(err),
      );
    } finally {
      setLoading(false);
    }
  }

  // ── Render gate ─────────────────────────────────────────────────────────

  if (!selectedText || !position) return null;

  const headerSnippet =
    selectedText.length > 10 ? selectedText.slice(0, 10) + "..." : selectedText;

  return (
    <div
      ref={popoverRef}
      role="dialog"
      aria-label="已选中词条解析"
      className="fixed z-50 flex flex-col gap-3 rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-xl backdrop-blur-md transition-opacity dark:border-zinc-800 dark:bg-zinc-900/95"
      style={{
        top: position.top,
        left: position.left,
        minWidth: Math.max(position.width, 220),
        maxWidth: 380,
        transform: position.placeBelow
          ? "translate(-50%, 0%)"
          : "translate(-50%, -100%)",
      }}
      onPointerDown={(e) => e.stopPropagation()}
    >
      {/* Header bar with title and close X */}
      <div className="flex items-center justify-between border-b border-slate-100 pb-2 dark:border-zinc-800">
        <span className="text-[11px] font-semibold text-slate-500 dark:text-zinc-400">
          已选中词条：&ldquo;{headerSnippet}&rdquo;
        </span>
        <button
          type="button"
          onClick={dismiss}
          aria-label="关闭"
          className="flex h-5 w-5 cursor-pointer items-center justify-center rounded text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200 transition-colors"
        >
          <X className="h-3.5 w-3.5" strokeWidth={1.5} />
        </button>
      </div>

      {/* Selected text preview */}
      <p className="max-h-20 overflow-y-auto text-xs leading-relaxed text-slate-600 dark:text-zinc-300">
        &ldquo;{selectedText}&rdquo;
      </p>

      {/* Action button */}
      {!loading && !result && (
        <button
          type="button"
          onClick={handleExplain}
          className="flex cursor-pointer items-center justify-center gap-1.5 rounded-xl bg-slate-900 px-4 py-2 text-xs font-semibold text-white shadow-2xs transition hover:bg-slate-800 active:scale-98 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          <Sparkles className="h-3.5 w-3.5" strokeWidth={1.5} />
          即时解析
        </button>
      )}

      {/* Loading inline spinner */}
      {loading && (
        <div className="flex items-center justify-center gap-2 py-2 text-xs text-slate-500 dark:text-zinc-400">
          <Loader2 className="h-4 w-4 animate-spin text-slate-700 dark:text-zinc-300" strokeWidth={1.5} />
          深度思考中…
        </div>
      )}

      {/* Inline result */}
      {result && (
        <div className="space-y-2.5 rounded-xl bg-slate-50 p-3.5 text-xs border border-slate-100 dark:bg-zinc-800/60 dark:border-zinc-800">
          <p className="font-semibold text-slate-900 dark:text-zinc-100 leading-relaxed">
            {result.summary}
          </p>
          {result.citations.length > 0 && (
            <div className="space-y-1 pt-1 border-t border-slate-200/60 dark:border-zinc-700/50">
              <div className="flex items-center gap-1 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                <BookOpen className="h-3 w-3" strokeWidth={1.5} />
                引用来源
              </div>
              <ul className="space-y-1 text-[11px] text-slate-600 dark:text-zinc-300">
                {result.citations.map((cit, i) => (
                  <li key={`cit-${i}`} className="truncate">
                    • {cit.source_title}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Inline error */}
      {error && (
        <div className="flex items-start gap-2 rounded-xl bg-red-50 p-3 text-xs text-red-800 dark:bg-red-950/30 dark:text-red-300 border border-red-200/60 dark:border-red-900/40">
          <AlertCircle className="h-4 w-4 shrink-0 text-red-600 dark:text-red-400" strokeWidth={1.5} />
          <div className="flex-1">
            <p className="font-medium">{error}</p>
          </div>
        </div>
      )}
    </div>
  );
}