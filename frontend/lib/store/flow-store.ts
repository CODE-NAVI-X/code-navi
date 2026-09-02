import { useSyncExternalStore } from "react";
import { isPracticeContextV1, type PracticeContextV1 } from "@/lib/practice-context";

export interface FlowPayload {
  sessionId: string;
  masteredKnowledgePoint: {
    id: string;
    name: string;
  };
  studentPersona: "academic" | "software_coursework" | "cross_disciplinary";
  targetModule: "practice" | "research";
  payloadData: {
    exerciseIds?: string[];
    /** Seed topic handed to the research conversation, when leaving from learning. */
    researchTopic?: string;
  };
  /**
   * §3.1 practice-context.v1 upgrade of the legacy topic-only hand-off.
   * Optional: payloads written before the upgrade (and payloads for the
   * research target) keep working unchanged.
   */
  practiceContext?: PracticeContextV1;
}

interface FlowState {
  payload: FlowPayload | null;
}

let currentPayload: FlowPayload | null = null;
const listeners = new Set<() => void>();
const PRACTICE_TASK_STORAGE_KEY = "code-navi-current-practice-task";

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot() {
  return currentPayload;
}

export function setFlowPayload(payload: FlowPayload) {
  currentPayload = payload;
  if (typeof window !== "undefined") {
    window.localStorage.setItem(PRACTICE_TASK_STORAGE_KEY, JSON.stringify(payload));
  }
  listeners.forEach((listener) => listener());
}

export function getPersistedFlowPayload(): FlowPayload | null {
  if (typeof window === "undefined") return null;
  const value = window.localStorage.getItem(PRACTICE_TASK_STORAGE_KEY);
  if (!value) return null;
  try {
    const parsed = JSON.parse(value) as Partial<FlowPayload>;
    if (
      parsed.targetModule !== "practice" ||
      typeof parsed.sessionId !== "string" ||
      typeof parsed.masteredKnowledgePoint?.id !== "string" ||
      typeof parsed.masteredKnowledgePoint?.name !== "string"
    ) return null;
    // Backward compat: payloads cached before the practice-context.v1 upgrade
    // have no context block; a corrupted one is dropped without invalidating
    // the rest of the payload.
    if (parsed.practiceContext !== undefined && !isPracticeContextV1(parsed.practiceContext)) {
      delete parsed.practiceContext;
    }
    return parsed as FlowPayload;
  } catch {
    return null;
  }
}

export function clearFlowPayload() {
  currentPayload = null;
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(PRACTICE_TASK_STORAGE_KEY);
  }
  listeners.forEach((listener) => listener());
}

export function useFlowStore<T>(selector: (state: FlowState) => T): T {
  const payload = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  return selector({ payload });
}
