/**
 * Lightweight external-store snapshot for the learning page.
 *
 * Allows the "explain" result and query to survive client-side navigations
 * (e.g. learning → practice → back to learning).
 */

interface LearningSnapshot {
  query: string;
  result: unknown; // ExplainResponse
}

let currentSnapshot: LearningSnapshot | null = null;
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): LearningSnapshot | null {
  return currentSnapshot;
}

export function setLearningSnapshot(snapshot: LearningSnapshot) {
  currentSnapshot = snapshot;
  listeners.forEach((fn) => fn());
}

export function clearLearningSnapshot() {
  currentSnapshot = null;
  listeners.forEach((fn) => fn());
}

export function useLearningStore<T>(
  selector: (snapshot: LearningSnapshot | null) => T,
): T {
  // useSyncExternalStore is from react
  const { useSyncExternalStore } = require("react");
  return useSyncExternalStore(subscribe, () => selector(getSnapshot()), () => selector(null));
}