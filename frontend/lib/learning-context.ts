/**
 * Shared helpers for the learning → practice / learning → research flow.
 *
 * Every entry point that leaves the learning page for a downstream module must
 * carry the same context: a FlowPayload (written to the in-memory flow store so
 * the target page can read it) plus the canonical `/learning/practice` URL with
 * knowledge/session and workspace context query params. Centralising that keeps
 * the three call sites (ExplanationCard, SlideViewer, DownstreamGoCard) from
 * drifting apart.
 */

import { createLearningToResearchContext } from "@/lib/api/context-transfers";
import { setFlowPayload } from "@/lib/store/flow-store";

export const LEARNING_PRACTICE_ROUTE = "/learning/practice";
const LEARNING_CONTEXT_QUERY_KEYS = [
  "workspace_id",
  "task_id",
  "workspace",
  "task",
  "return_to",
] as const;

/** Minimal push shape — accepts the Next `AppRouterInstance` without importing it. */
export interface Navigator {
  push: (href: string) => void;
}

interface SearchParamsLike {
  get: (name: string) => string | null;
}

/**
 * Derive a stable knowledge-point id from its display name.
 *
 * The existing downstream card used a hard-coded stub id; entries built from a
 * real query should get a deterministic id so the practice page sees a
 * consistent `knowledge_id` for the same concept.
 */
export function buildKnowledgeId(name: string): string {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9一-鿿]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return `kp_${slug || "knowledge"}`;
}

export interface PracticeFlowOptions {
  knowledgePoint: string;
  knowledgePointId: string;
  sessionId: string;
  exerciseIds?: string[];
  currentSearchParams?: SearchParamsLike;
}

function currentBrowserSearchParams(): URLSearchParams | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search);
}

function appendLearningContextParams(
  params: URLSearchParams,
  source: SearchParamsLike | null | undefined,
) {
  const current = source ?? currentBrowserSearchParams();
  if (!current) return;
  for (const key of LEARNING_CONTEXT_QUERY_KEYS) {
    const value = current.get(key);
    if (value && !params.has(key)) params.set(key, value);
  }
}

export function buildPracticeHref(options: Partial<PracticeFlowOptions> = {}): string {
  const params = new URLSearchParams();
  if (options.knowledgePointId) params.set("knowledge_id", options.knowledgePointId);
  if (options.knowledgePoint) params.set("knowledge_name", options.knowledgePoint);
  if (options.sessionId) params.set("session_id", options.sessionId);
  appendLearningContextParams(params, options.currentSearchParams);
  const query = params.toString();
  return query ? `${LEARNING_PRACTICE_ROUTE}?${query}` : LEARNING_PRACTICE_ROUTE;
}

/** Leave learning for the practice module, carrying the mastered context. */
export function navigateToPractice(
  navigator: Navigator,
  options: PracticeFlowOptions,
): void {
  const { knowledgePoint, knowledgePointId, sessionId } = options;
  setFlowPayload({
    sessionId,
    masteredKnowledgePoint: { id: knowledgePointId, name: knowledgePoint },
    studentPersona: "software_coursework",
    targetModule: "practice",
    payloadData: {
      exerciseIds: options.exerciseIds,
    },
  });
  navigator.push(buildPracticeHref(options));
}

export interface ResearchFlowOptions {
  notebookItemId: string;
  sessionId: string;
}

/**
 * Leave learning for research through the persisted context-transfer flow.
 *
 * The summary is already archived as a notebook item server-side; this creates
 * a learning → research context draft from that exact item and hands the
 * student to the confirm page.  The research session is thus backed by a real
 * source record rather than a browser-only payload that no module consumes.
 */
export async function navigateToResearch(
  navigator: Navigator,
  options: ResearchFlowOptions,
): Promise<void> {
  const context = await createLearningToResearchContext(
    options.notebookItemId,
    options.sessionId,
  );
  navigator.push(`/student/research/confirm/${encodeURIComponent(context.id)}`);
}
