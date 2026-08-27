import { useSyncExternalStore } from "react";

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
