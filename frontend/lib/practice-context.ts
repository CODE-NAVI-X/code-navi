/**
 * practice-context.v1 (contract §3.1) — the structured hand-off from the
 * learning module to hands-on practice.
 *
 * This module is the single construction point: every entry point leaving the
 * learning page for practice must build the context here (mirrors the
 * backend Pydantic models in ``src/code_navi/practice/schemas.py``).
 * Mastery values may only ever come from the real learning portrait — when
 * the portrait has no sufficient sample the value is ``null``, never invented.
 */

import { fetchProfile } from "@/lib/api/profile";

export const PRACTICE_CONTEXT_VERSION = "practice-context.v1";

/** Field limits mirroring ``PracticeContextV1`` (contract §3.1). */
export const PRACTICE_CONTEXT_LIMITS = {
  sourceSessionId: 64,
  knowledgePointName: 128,
  knowledgePointSourceRef: 256,
  knowledgePointsMin: 1,
  knowledgePointsMax: 8,
  objective: 512,
  notesSummary: 2000,
} as const;

export interface PracticeContextKnowledgePoint {
  name: string;
  /** notebook_item_id / explain reference from the learning side. */
  source_ref: string;
  /** Real portrait mastery (0..1) or null — never a fabricated number. */
  mastery: number | null;
}

export interface PracticeContextV1 {
  source_session_id: string;
  knowledge_points: PracticeContextKnowledgePoint[];
  /** The user's own goal wording, not an inference. */
  objective: string;
  notes_summary: string | null;
}

export interface PracticeContextDraftInput {
  sourceSessionId: string;
  knowledgePoints: Array<{
    name: string;
    sourceRef: string;
    mastery?: number | null;
  }>;
  objective: string;
  notesSummary?: string | null;
}

function clampText(value: string, limit: number): string {
  return value.trim().slice(0, limit);
}

function clampMastery(value: number | null | undefined): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  if (value < 0 || value > 1) return null;
  return value;
}

/**
 * Build a contract-shaped ``practice-context.v1`` payload.
 *
 * Returns ``null`` when nothing real remains to hand over (no session id, no
 * knowledge point, or no objective) — the caller then falls back to the
 * legacy topic-only hand-off instead of sending an empty context.
 */
export function buildPracticeContextV1(
  input: PracticeContextDraftInput,
): PracticeContextV1 | null {
  const sourceSessionId = clampText(
    input.sourceSessionId ?? "",
    PRACTICE_CONTEXT_LIMITS.sourceSessionId,
  );
  const objective = clampText(input.objective ?? "", PRACTICE_CONTEXT_LIMITS.objective);
  if (!sourceSessionId || !objective) return null;

  const seen = new Set<string>();
  const knowledgePoints: PracticeContextKnowledgePoint[] = [];
  for (const point of input.knowledgePoints) {
    const name = clampText(point?.name ?? "", PRACTICE_CONTEXT_LIMITS.knowledgePointName);
    const sourceRef = clampText(
      point?.sourceRef ?? name,
      PRACTICE_CONTEXT_LIMITS.knowledgePointSourceRef,
    );
    if (!name || seen.has(name)) continue;
    seen.add(name);
    knowledgePoints.push({ name, source_ref: sourceRef, mastery: clampMastery(point?.mastery) });
    if (knowledgePoints.length >= PRACTICE_CONTEXT_LIMITS.knowledgePointsMax) break;
  }
  if (knowledgePoints.length < PRACTICE_CONTEXT_LIMITS.knowledgePointsMin) return null;

  const notesSummary = (input.notesSummary ?? "").trim();
  return {
    source_session_id: sourceSessionId,
    knowledge_points: knowledgePoints,
    objective,
    notes_summary: notesSummary
      ? notesSummary.slice(0, PRACTICE_CONTEXT_LIMITS.notesSummary)
      : null,
  };
}

function masteryKey(name: string): string {
  return name.trim().toLowerCase();
}

/**
 * Look up real portrait mastery values for the given knowledge-point names.
 *
 * Only ``mastery`` values the portrait reports as ``sufficient`` pass through;
 * everything else (unknown point, insufficient sample, lookup failure) maps to
 * ``null`` so the red line "real value or null" holds even offline.
 */
export async function fetchKnowledgePointMastery(
  profileId: string,
  names: string[],
): Promise<Record<string, number | null>> {
  const result: Record<string, number | null> = {};
  for (const name of names) result[masteryKey(name)] = null;
  if (!profileId || names.length === 0) return result;

  try {
    const profile = await fetchProfile(profileId);
    const byKey = new Map<string, number | null>();
    for (const item of profile.mastery) {
      byKey.set(masteryKey(item.knowledge_point), item.mastery);
    }
    for (const name of names) {
      const value = byKey.get(masteryKey(name));
      result[masteryKey(name)] = typeof value === "number" ? value : null;
    }
  } catch {
    // Portrait unavailable: every mastery stays null (empty state, no error).
  }
  return result;
}

/** Runtime guard for the refresh fallback cache (old caches have no context). */
export function isPracticeContextV1(value: unknown): value is PracticeContextV1 {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Partial<PracticeContextV1>;
  if (typeof candidate.source_session_id !== "string" || !candidate.source_session_id) {
    return false;
  }
  if (typeof candidate.objective !== "string" || !candidate.objective) return false;
  if (!Array.isArray(candidate.knowledge_points) || candidate.knowledge_points.length === 0) {
    return false;
  }
  return candidate.knowledge_points.every(
    (point) =>
      typeof point?.name === "string" &&
      point.name.length > 0 &&
      typeof point?.source_ref === "string" &&
      point.source_ref.length > 0 &&
      (point?.mastery === null ||
        point?.mastery === undefined ||
        typeof point.mastery === "number"),
  );
}
