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
    recommendedTopic?: string;
    exerciseIds?: string[];
  };
}

interface FlowState {
  payload: FlowPayload | null;
}

let currentPayload: FlowPayload | null = null;
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot() {
  return currentPayload;
}

export function setFlowPayload(payload: FlowPayload) {
  currentPayload = payload;
  listeners.forEach((listener) => listener());
}

export function clearFlowPayload() {
  currentPayload = null;
  listeners.forEach((listener) => listener());
}

export function useFlowStore<T>(selector: (state: FlowState) => T): T {
  const payload = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  return selector({ payload });
}
