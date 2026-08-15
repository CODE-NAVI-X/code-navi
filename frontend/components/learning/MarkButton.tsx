"use client";

/**
 * Binary 不懂/懂了 self-report toggle on one learning surface.
 *
 * Optimistic UI: the button flips immediately; the server write is debounced
 * (rapid toggles coalesce into one request — the endpoint is idempotent on
 * ``(session_id, source_type, source_ref)``) and serialized so requests never
 * race. If a write fails the button reverts to the last server-confirmed
 * state and flags the failure — the UI never claims a mark that was not
 * persisted.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Check, CircleAlert, HelpCircle, Loader2 } from "lucide-react";
import { getLearningSessionId } from "@/lib/api/learning";
import type { MarkSourceType } from "@/lib/api/profile";
import { setConfusionMark } from "@/lib/api/profile";
import { getOrCreateLearnerId } from "@/lib/learner";

/** Debounce window for coalescing rapid toggles (防抖). */
const FLUSH_MS = 400;
/** How long a failed save is flagged before reverting to confirmed styling. */
const FAIL_HINT_MS = 2500;

export interface MarkButtonProps {
  /** Learning session scope; defaults to this browser's stored session id. */
  sessionId?: string;
  /** Semantic knowledge name — the portrait aggregates by this, not source_ref. */
  knowledgePoint: string;
  sourceType: MarkSourceType;
  /** Entity this mark is attached to (traceability only). */
  sourceRef: string;
  /**
   * Human-readable content of the mark (term text, slide page, question stem).
   * Shown verbatim in the portrait's 待复习 expansion so the student sees
   * *what* was marked 不懂. Falls back to ``sourceRef`` when omitted.
   */
  label?: string;
  className?: string;
}

type MarkState = "idle" | "confused" | "understood";

export function MarkButton({
  sessionId,
  knowledgePoint,
  sourceType,
  sourceRef,
  label,
  className = "",
}: MarkButtonProps) {
  const [markState, setMarkState] = useState<MarkState>("idle");
  const [syncing, setSyncing] = useState(false);
  const [failed, setFailed] = useState(false);
  const debounceTimer = useRef<number | null>(null);
  const failTimer = useRef<number | null>(null);
  /** Last server-confirmed mark (null = never confirmed). */
  const confirmedRef = useRef<boolean | null>(null);
  /** Latest mark waiting to be sent (the debounced value). */
  const queuedRef = useRef<boolean | null>(null);
  const sendingRef = useRef(false);
  /** Latest ``drainQueue``, kept current so callbacks never self-reference. */
  const drainRef = useRef<() => void>(() => {});

  // Serialized, last-write-wins sender: no two requests in flight, and a
  // toggle that lands while one is pending is sent once it settles.
  const drainQueue = useCallback(() => {
    if (sendingRef.current) return;
    const mark = queuedRef.current;
    if (mark === null) return;
    queuedRef.current = null;
    sendingRef.current = true;
    setSyncing(true);
    setConfusionMark({
      session_id: sessionId ?? getLearningSessionId(),
      profile_id: getOrCreateLearnerId(),
      knowledge_point: knowledgePoint,
      source_type: sourceType,
      source_ref: sourceRef,
      label: label ?? sourceRef,
      mark,
    })
      .then(() => {
        confirmedRef.current = mark;
      })
      .catch(() => {
        // Revert to the last confirmed state (or idle) — do not claim a
        // persisted mark that never landed.
        const confirmed = confirmedRef.current;
        setMarkState(confirmed === null ? "idle" : confirmed ? "confused" : "understood");
        setFailed(true);
        if (failTimer.current !== null) window.clearTimeout(failTimer.current);
        failTimer.current = window.setTimeout(() => {
          setFailed(false);
          failTimer.current = null;
        }, FAIL_HINT_MS);
      })
      .finally(() => {
        sendingRef.current = false;
        setSyncing(false);
        // Kick the next queued mark (if any) — via the ref so this callback
        // never references itself before it is declared.
        drainRef.current();
      });
  }, [sessionId, knowledgePoint, sourceType, sourceRef, label]);

  // Keep the ref current outside of render (React Compiler rule).
  useEffect(() => {
    drainRef.current = drainQueue;
  });

  const scheduleToggle = useCallback((mark: boolean) => {
    queuedRef.current = mark;
    if (debounceTimer.current !== null) window.clearTimeout(debounceTimer.current);
    debounceTimer.current = window.setTimeout(() => {
      debounceTimer.current = null;
      drainRef.current();
    }, FLUSH_MS);
  }, []);

  useEffect(() => {
    return () => {
      if (debounceTimer.current !== null) window.clearTimeout(debounceTimer.current);
      if (failTimer.current !== null) window.clearTimeout(failTimer.current);
      // Best-effort flush of an unsent toggle when the surface unmounts.
      if (queuedRef.current !== null) drainRef.current();
    };
  }, []);

  function toggle() {
    // Binary switch: idle/understood → 不懂; confused → 懂了.
    const mark = markState !== "confused";
    setMarkState(mark ? "confused" : "understood");
    scheduleToggle(mark);
  }

  const buttonLabel =
    markState === "confused"
      ? "看不懂"
      : markState === "understood"
        ? "已懂"
        : "标记不懂";

  let cls =
    "border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:text-slate-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-200";
  if (markState === "confused") {
    cls =
      "border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-300";
  } else if (markState === "understood") {
    cls =
      "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300";
  }

  return (
    <button
      type="button"
      onClick={toggle}
      title={
        failed
          ? "保存失败，点击重试"
          : markState === "confused"
            ? "点击标记为已懂"
            : "点击标记为不懂"
      }
      className={`inline-flex cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[11px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 ${cls} ${className}`}
    >
      {syncing ? (
        <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.5} />
      ) : failed ? (
        <CircleAlert className="h-3 w-3" strokeWidth={1.5} />
      ) : markState === "confused" ? (
        <HelpCircle className="h-3 w-3" strokeWidth={1.5} />
      ) : markState === "understood" ? (
        <Check className="h-3 w-3" strokeWidth={1.5} />
      ) : (
        <HelpCircle className="h-3 w-3" strokeWidth={1.5} />
      )}
      {buttonLabel}
    </button>
  );
}
