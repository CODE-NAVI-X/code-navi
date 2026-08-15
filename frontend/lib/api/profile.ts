/**
 * Learning-portrait (学情画像) API client.
 *
 * Mirrors the backend Pydantic schemas in ``src/code_navi/learning_profile``.
 * The portrait is anonymous and keyed by the unified ``profile_id`` (== the
 * practice ``learner_id`` UUID), aggregating real persisted scores and
 * self-reported confusion marks across sessions.
 *
 * Endpoints:
 *   POST /api/v1/learning/marks   → toggle a 不懂/懂了 mark on one surface
 *   GET  /api/v1/profile?profile_id=… → aggregate the anonymous portrait
 */

import { API_BASE, getLearningSessionId } from "@/lib/api/learning";

// ── Data types (mirrors learning_profile/schemas.py) ──────────────────────────

export type MarkSourceType = "ppt_page" | "explain" | "quiz_question";

export interface MarkRequest {
  session_id: string;
  /** Optional unified profile key (== the practice learner_id UUID). */
  profile_id?: string | null;
  /** Semantic knowledge name — survives PPT regeneration / quiz re-making. */
  knowledge_point: string;
  /** ppt_page | explain | quiz_question. */
  source_type: MarkSourceType;
  /** Entity this mark is attached to (traceability only). */
  source_ref: string;
  /** True → 看不懂 (confused); False → 懂了 (understood). */
  mark: boolean;
}

export interface MarkResponse {
  session_id: string;
  source_type: MarkSourceType;
  source_ref: string;
  status: "confused" | "understood";
}

export interface ProfileMastery {
  knowledge_point: string;
  /** Σscore/Σmax_score over graded attempts; null when none graded. */
  quiz_rate: number | null;
  /** Graded attempt count. */
  sample_size: number;
  /** quiz_rate once sample_size >= MIN_MASTERY_SAMPLE, else null (样本不足). */
  mastery: number | null;
  status: "sufficient" | "insufficient";
}

export interface ConfusionItem {
  knowledge_point: string;
  mark_count: number;
  source_types: MarkSourceType[];
}

export interface ProfileResponse {
  profile_id: string;
  generated_at: string;
  mastery: ProfileMastery[];
  strengths: string[];
  weaknesses: string[];
  confusion: ConfusionItem[];
}

/**
 * Build a stable ``source_ref`` for one learning surface. The ref is truncated
 * so it always fits the backend's 256-char limit; the portrait aggregates by
 * ``knowledge_point`` anyway, so a short ref only loses per-slide fidelity,
 * never data. Embedding the knowledge point keeps refs from different topics
 * from colliding (e.g. two decks' "slide 3").
 */
export function markSourceRef(
  kind: MarkSourceType,
  knowledgePoint: string,
  suffix = "",
): string {
  const base = `${kind}:${knowledgePoint.trim().slice(0, 100)}`;
  return suffix ? `${base}:${suffix}` : base;
}

// ── Client error (typed) ───────────────────────────────────────────────────────

export class ProfileApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ProfileApiError";
  }
}

// ── Toggle a confusion mark ────────────────────────────────────────────────────

/**
 * POST /api/v1/learning/marks — idempotent binary toggle on
 * ``(session_id, source_type, source_ref)``. Returns the effective state after
 * the toggle. Throws ``ProfileApiError`` on non-OK / network failure.
 */
export async function setConfusionMark(
  request: MarkRequest,
): Promise<MarkResponse> {
  const url = `${API_BASE}/api/v1/learning/marks`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: request.session_id ?? getLearningSessionId(),
        profile_id: request.profile_id ?? null,
        knowledge_point: request.knowledge_point,
        source_type: request.source_type,
        source_ref: request.source_ref,
        mark: request.mark,
      }),
    });
  } catch (networkError) {
    throw new ProfileApiError(
      0,
      `Network error while contacting ${url}: ${String(networkError)}`,
    );
  }

  if (!response.ok) {
    const detail = await extractErrorDetail(response);
    throw new ProfileApiError(
      response.status,
      detail ?? `Request failed with status ${response.status}`,
    );
  }

  const body: unknown = await response.json();
  return validateMarkResponse(body);
}

// ── Fetch the aggregated portrait ─────────────────────────────────────────────

/**
 * GET /api/v1/profile?profile_id=… — the anonymous cross-session portrait.
 * An unknown key yields an empty portrait (200, sample_size=0), never 404.
 */
export async function fetchProfile(
  profileId: string,
): Promise<ProfileResponse> {
  const url = `${API_BASE}/api/v1/profile?profile_id=${encodeURIComponent(profileId)}`;

  let response: Response;
  try {
    response = await fetch(url, { headers: { Accept: "application/json" } });
  } catch (networkError) {
    throw new ProfileApiError(
      0,
      `Network error while contacting ${url}: ${String(networkError)}`,
    );
  }

  if (!response.ok) {
    const detail = await extractErrorDetail(response);
    throw new ProfileApiError(
      response.status,
      detail ?? `Request failed with status ${response.status}`,
    );
  }

  const body: unknown = await response.json();
  return validateProfileResponse(body);
}

// ── Internal helpers ───────────────────────────────────────────────────────────

async function extractErrorDetail(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json();
    if (
      body &&
      typeof body === "object" &&
      "detail" in body &&
      typeof (body as Record<string, unknown>).detail === "string"
    ) {
      return (body as Record<string, string>).detail;
    }
  } catch {
    // ignore parse failures — fall back to status text
  }
  return response.statusText || null;
}

function validateMarkResponse(raw: unknown): MarkResponse {
  if (!raw || typeof raw !== "object") {
    throw new ProfileApiError(502, "Server returned a non-object response.");
  }
  const obj = raw as Record<string, unknown>;
  const sourceType: MarkSourceType =
    obj.source_type === "explain"
      ? "explain"
      : obj.source_type === "quiz_question"
        ? "quiz_question"
        : "ppt_page";
  return {
    session_id: typeof obj.session_id === "string" ? (obj.session_id as string) : "",
    source_type: sourceType,
    source_ref: typeof obj.source_ref === "string" ? (obj.source_ref as string) : "",
    status: obj.status === "understood" ? "understood" : "confused",
  };
}

function validateProfileResponse(raw: unknown): ProfileResponse {
  if (!raw || typeof raw !== "object") {
    throw new ProfileApiError(502, "Server returned a non-object response.");
  }
  const obj = raw as Record<string, unknown>;

  const mastery: ProfileMastery[] = [];
  if (Array.isArray(obj.mastery)) {
    for (const item of obj.mastery) {
      if (item && typeof item === "object") {
        const m = item as Record<string, unknown>;
        mastery.push({
          knowledge_point:
            typeof m.knowledge_point === "string" ? (m.knowledge_point as string) : "",
          quiz_rate: typeof m.quiz_rate === "number" ? (m.quiz_rate as number) : null,
          sample_size: typeof m.sample_size === "number" ? (m.sample_size as number) : 0,
          mastery: typeof m.mastery === "number" ? (m.mastery as number) : null,
          status: m.status === "sufficient" ? "sufficient" : "insufficient",
        });
      }
    }
  }

  const confusion: ConfusionItem[] = [];
  if (Array.isArray(obj.confusion)) {
    for (const item of obj.confusion) {
      if (item && typeof item === "object") {
        const c = item as Record<string, unknown>;
        const types: MarkSourceType[] = Array.isArray(c.source_types)
          ? (c.source_types as MarkSourceType[]).filter(
              (t): t is MarkSourceType =>
                t === "ppt_page" || t === "explain" || t === "quiz_question",
            )
          : [];
        confusion.push({
          knowledge_point:
            typeof c.knowledge_point === "string" ? (c.knowledge_point as string) : "",
          mark_count: typeof c.mark_count === "number" ? (c.mark_count as number) : 1,
          source_types: types,
        });
      }
    }
  }

  const strList = (value: unknown): string[] =>
    Array.isArray(value)
      ? value.filter((v): v is string => typeof v === "string")
      : [];

  return {
    profile_id: typeof obj.profile_id === "string" ? (obj.profile_id as string) : "",
    generated_at:
      typeof obj.generated_at === "string" ? (obj.generated_at as string) : "",
    mastery,
    strengths: strList(obj.strengths),
    weaknesses: strList(obj.weaknesses),
    confusion,
  };
}
