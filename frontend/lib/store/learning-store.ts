import { useSyncExternalStore } from "react";

import { getLearningSessionId } from "@/lib/api/learning";
import type {
  PresentationGenerationMode,
  SceneOutline,
  Slide,
} from "@/lib/api/learning";

/**
 * Lightweight external-store snapshot for the learning page.
 *
 * Allows the explain result AND a partially/fully generated PPT deck to survive
 * client-side navigations (e.g. learning → practice → back to learning). The
 * snapshot is in-memory only (module scope), which is exactly what an SPA
 * route switch needs — a full page reload clears it, which is fine.
 */

export interface LearningSnapshot {
  query: string;
  result: unknown; // ExplainResponse
  /** Which of the unified result views the user was on (text | ppt). */
  view?: "text" | "ppt";
  /** PPT deck — set once generation starts, so it survives a route switch. */
  outlines?: SceneOutline[];
  slides?: Slide[];
  currentIndex?: number;
  presentationGenerationMode?: PresentationGenerationMode;
  presentationProviderName?: string;
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
  return useSyncExternalStore(subscribe, () => selector(getSnapshot()), () => selector(null));
}

/**
 * Read this browser's learning session id.
 *
 * The id lives in localStorage, which does not exist while the page is
 * server-rendered, so the server snapshot is empty and the real value arrives
 * on hydration.  ``getLearningSessionId`` is idempotent, so the client snapshot
 * is stable across renders.
 */
export function useLearningSessionId(): string {
  return useSyncExternalStore(
    subscribeToNothing,
    getLearningSessionId,
    () => "",
  );
}

// The id never changes for the lifetime of the tab, so there is nothing to
// subscribe to — React only needs a well-formed unsubscribe function.
function subscribeToNothing(): () => void {
  return () => {};
}
