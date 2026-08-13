/**
 * Shared helpers for the learning → practice / learning → research flow.
 *
 * Every entry point that leaves the learning page for a downstream module must
 * carry the same context: a FlowPayload (written to the in-memory flow store so
 * the target page can read it) plus a canonical `/student/*` URL with
 * knowledge/session query params. Centralising that keeps the three call sites
 * (ExplanationCard, SlideViewer, DownstreamGoCard) from drifting apart.
 */

import { setFlowPayload } from "@/lib/store/flow-store";

/** Minimal push shape — accepts the Next `AppRouterInstance` without importing it. */
export interface Navigator {
  push: (href: string) => void;
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
  const params = new URLSearchParams({
    knowledge_id: knowledgePointId,
    knowledge_name: knowledgePoint,
    session_id: sessionId,
  });
  navigator.push(`/student/practice?${params.toString()}`);
}

export interface ResearchFlowOptions {
  knowledgePoint: string;
  knowledgePointId: string;
  sessionId: string;
  researchTopic?: string;
}

/** Leave learning for the research module, carrying the mastered context. */
export function navigateToResearch(
  navigator: Navigator,
  options: ResearchFlowOptions,
): void {
  const { knowledgePoint, knowledgePointId, sessionId } = options;
  setFlowPayload({
    sessionId,
    masteredKnowledgePoint: { id: knowledgePointId, name: knowledgePoint },
    studentPersona: "academic",
    targetModule: "research",
    payloadData: {
      researchTopic: options.researchTopic ?? knowledgePoint,
    },
  });
  const params = new URLSearchParams({
    knowledge_name: knowledgePoint,
    session_id: sessionId,
  });
  navigator.push(`/student/research?${params.toString()}`);
}
