/**
 * Learning-quiz API client.
 *
 * TypeScript types mirror the backend Pydantic schemas in
 * ``src/code_navi/learning/quiz/schemas.py``, which in turn align with
 * OpenMAIC's ``QuizQuestion`` (``lib/types/stage.ts``).
 *
 * Two endpoints are consumed:
 *   POST /api/v1/learning/quiz/generate      → one exercise set (组卷)
 *   GET  /api/v1/learning/quiz/export-docx   → standard Word paper (.docx)
 */

import { API_BASE, getLearningSessionId } from "@/lib/api/learning";

// ── Data types (mirrors quiz/schemas.py) ───────────────────────────────────────

export type QuizQuestionType = "single" | "fill_blank" | "short_answer";
export type QuizDifficulty = "easy" | "medium" | "hard";
export type QuizSourceType = "generated" | "web" | "local_bank";
export type QuizSourceMode = "generated" | "web";

export interface QuizOption {
  /** Display text; may contain $...$ LaTeX math. */
  label: string;
  /** Selection key, e.g. "A". */
  value: string;
}

export interface QuizQuestionSource {
  type: QuizSourceType;
  /** Human-readable source badge, e.g. "AI 生成". */
  label: string;
  uri?: string | null;
  accessed_at?: string | null;
}

export interface QuizQuestion {
  id: string;
  type: QuizQuestionType;
  /** Stem; may embed $...$ LaTeX math. */
  question: string;
  /** Present for ``single``; absent for the other types. */
  options?: QuizOption[] | null;
  /**
   * single: one option value e.g. ["A"]. fill_blank: one entry per blank, in
   * order. short_answer: null (graded by an LLM / reference answer).
   */
  answer?: string[] | null;
  /** Explanation shown after grading. */
  analysis?: string | null;
  points: number;
  comment_prompt?: string | null;
  source: QuizQuestionSource;
}

export interface QuizAuditScore {
  dimension: "difficulty_fit" | "coverage" | "quality";
  score: number;
  note: string;
}

export interface QuizAuditReport {
  verdict: "pass" | "adjust";
  scores: QuizAuditScore[];
  notes: string[];
  revised: boolean;
  revision_summary?: string | null;
}

export interface QuizGenerateResponse {
  knowledge_point: string;
  session_id: string;
  /** Opaque id addressing this quiz for export. */
  quiz_id: string;
  questions: QuizQuestion[];
  generation_mode: string;
  provider_name: string;
  source_mode: QuizSourceMode;
  total_points: number;
  /**
   * The actual 学情 text injected into the generation prompt (real portrait
   * segment + manual supplement, or just whichever was present). Echoed back so
   * the UI can show what the model saw.
   */
  effective_student_profile?: string | null;
  audit?: QuizAuditReport | null;
}

/** The generate-request fields a user can tune; knowledge/session are added by the caller. */
export interface QuizGenerateParams {
  question_count?: number;
  /** Omit (null) to include all three question types. */
  question_types?: QuizQuestionType[] | null;
  difficulty?: QuizDifficulty;
  with_latex?: boolean;
  source_mode?: QuizSourceMode;
  student_profile?: string | null;
  /**
   * Unified profile key (== the practice learner_id UUID). When set, the server
   * injects that learner's real portrait into the generation prompt.
   */
  profile_id?: string | null;
}

export const DEFAULT_QUIZ_PARAMS: QuizGenerateParams = {
  question_count: 5,
  difficulty: "medium",
  with_latex: true,
  source_mode: "generated",
};

// ── Client error (typed) ───────────────────────────────────────────────────────

export class QuizApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "QuizApiError";
  }
}

// ── Generate (组卷) ────────────────────────────────────────────────────────────

export interface GenerateQuizRequest {
  knowledge_point: string;
  session_id?: string;
  question_count?: number;
  question_types?: QuizQuestionType[] | null;
  difficulty?: QuizDifficulty;
  with_latex?: boolean;
  source_mode?: QuizSourceMode;
  student_profile?: string | null;
  /** Optional profile key → server injects that learner's real portrait. */
  profile_id?: string | null;
}

/**
 * POST /api/v1/learning/quiz/generate. Returns a strongly-typed
 * ``QuizGenerateResponse`` or throws ``QuizApiError`` on non-OK / network
 * failure.
 */
export async function generateQuiz(
  request: GenerateQuizRequest,
): Promise<QuizGenerateResponse> {
  const url = `${API_BASE}/api/v1/learning/quiz/generate`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        knowledge_point: request.knowledge_point,
        session_id: request.session_id ?? getLearningSessionId(),
        question_count: request.question_count,
        question_types: request.question_types ?? null,
        difficulty: request.difficulty,
        with_latex: request.with_latex,
        source_mode: request.source_mode,
        student_profile: request.student_profile ?? null,
        profile_id: request.profile_id ?? null,
      }),
    });
  } catch (networkError) {
    throw new QuizApiError(
      0,
      `Network error while contacting ${url}: ${String(networkError)}`,
    );
  }

  if (!response.ok) {
    const detail = await extractErrorDetail(response);
    throw new QuizApiError(
      response.status,
      detail ?? `Request failed with status ${response.status}`,
    );
  }

  const body: unknown = await response.json();
  return validateGenerateResponse(body);
}

// ── Export Word (.docx) ────────────────────────────────────────────────────────

export interface ExportQuizDocxOptions {
  quizId: string;
  sessionId: string;
  /** Append a 参考答案 section at the end of the same document. */
  withAnswer?: boolean;
}

/**
 * GET /api/v1/learning/quiz/export-docx, download the returned .docx with a
 * browser-native save. Throws ``QuizApiError`` on non-OK / network failure.
 */
export async function exportQuizDocx(
  options: ExportQuizDocxOptions,
): Promise<void> {
  const params = new URLSearchParams({
    quiz_id: options.quizId,
    session_id: options.sessionId,
    with_answer: String(options.withAnswer ?? false),
  });
  const url = `${API_BASE}/api/v1/learning/quiz/export-docx?${params.toString()}`;

  let response: Response;
  try {
    response = await fetch(url, {
      headers: { Accept: "application/octet-stream" },
    });
  } catch (networkError) {
    throw new QuizApiError(
      0,
      `Network error while contacting ${url}: ${String(networkError)}`,
    );
  }

  if (!response.ok) {
    const detail = await extractErrorDetail(response);
    throw new QuizApiError(
      response.status,
      detail ?? `Request failed with status ${response.status}`,
    );
  }

  const blob = await response.blob();
  // Prefer the server's RFC 5987 ``filename*`` Chinese name, fall back to a
  // stable ASCII name for browsers that cannot read the header.
  let fileName = `quiz_${options.quizId.slice(0, 8)}${options.withAnswer ? "-answer" : ""}.docx`;
  const disposition = response.headers.get("Content-Disposition");
  const starMatch = disposition?.match(/filename\*=UTF-8''([^;]+)/i);
  if (starMatch?.[1]) {
    try {
      fileName = decodeURIComponent(starMatch[1]);
    } catch {
      // keep the fallback name on a malformed header
    }
  }

  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

// ── Grade (LLM 判分 for fill_blank / short_answer) ─────────────────────────────
// Mirrors the backend grading schemas in ``quiz/schemas.py``. ``gradeQuizAnswers``
// itself lives in ``learning.ts`` (per the learning-module client contract).

export interface QuizStudentAnswerItem {
  /** Must match an id in the archived quiz being graded. */
  question_id: string;
  /**
   * single: the selected option value e.g. ["B"]. fill_blank: one entry per
   * blank, in order. short_answer: a single entry holding the free-text
   * answer.
   */
  answer: string[];
}

export interface QuizQuestionGradeResult {
  question_id: string;
  type: QuizQuestionType;
  /** Awarded points, clamped to 0..max_score. */
  score: number;
  /** Full points for this item. */
  max_score: number;
  /** True when full points were awarded. */
  is_correct: boolean;
  /** Chinese grading analysis / suggestion from the LLM. */
  comment: string | null;
  /** True when this is deterministic offline grading, not a real LLM verdict. */
  is_mock: boolean;
  /** False only when offline mode cannot grade a short answer. */
  graded: boolean;
  /**
   * How this score was produced: rules (deterministic single-choice), mock
   * (offline deterministic fill-blank), or model (LLM judgment).
   */
  graded_by: "mock" | "rules" | "model";
}

export interface QuizGradeResponse {
  session_id: string;
  /** Echoed idempotency key; addresses the persisted attempts. */
  attempt_id: string;
  results: QuizQuestionGradeResult[];
  generation_mode: string;
  provider_name: string;
  total_score: number;
  total_max_score: number;
}

export interface GradeQuizRequest {
  session_id: string;
  /** The archived quiz to grade (its rubric is loaded server-side). */
  quiz_id: string;
  /**
   * Client-minted UUID v4 idempotency key — a retried request re-uses it so
   * the server upserts instead of double-inserting.
   */
  attempt_id: string;
  /**
   * Optional unified profile key (== the practice ``learner_id`` UUID). When
   * present, this attempt is aggregated into the learning portrait.
   */
  profile_id?: string | null;
  /** The student's answers, one entry per answered question (single included). */
  student_answers: QuizStudentAnswerItem[];
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

function validateGenerateResponse(raw: unknown): QuizGenerateResponse {
  if (!raw || typeof raw !== "object") {
    throw new QuizApiError(502, "Server returned a non-object response.");
  }
  const obj = raw as Record<string, unknown>;
  if (typeof obj.knowledge_point !== "string") {
    throw new QuizApiError(502, "Response missing 'knowledge_point' field.");
  }
  if (typeof obj.session_id !== "string") {
    throw new QuizApiError(502, "Response missing 'session_id' field.");
  }
  if (typeof obj.quiz_id !== "string") {
    throw new QuizApiError(502, "Response missing 'quiz_id' field.");
  }
  if (!Array.isArray(obj.questions)) {
    throw new QuizApiError(502, "Response missing 'questions' array.");
  }

  const questions: QuizQuestion[] = [];
  for (const item of obj.questions) {
    if (item && typeof item === "object") {
      const q = item as Record<string, unknown>;
      const type = typeof q.type === "string" ? (q.type as QuizQuestionType) : "short_answer";
      questions.push({
        id: typeof q.id === "string" ? q.id : "",
        type,
        question: typeof q.question === "string" ? q.question : "",
        options: Array.isArray(q.options)
          ? (q.options as QuizOption[]).filter(
              (o): o is QuizOption =>
                !!o && typeof o === "object" && typeof o.label === "string" && typeof o.value === "string",
            )
          : null,
        answer: Array.isArray(q.answer) ? (q.answer as string[]) : null,
        analysis: typeof q.analysis === "string" ? (q.analysis as string) : null,
        points: typeof q.points === "number" ? q.points : 10,
        comment_prompt:
          typeof q.comment_prompt === "string" ? (q.comment_prompt as string) : null,
        source: normalizeSource(q.source),
      });
    }
  }

  return {
    knowledge_point: obj.knowledge_point as string,
    session_id: obj.session_id as string,
    quiz_id: obj.quiz_id as string,
    questions,
    generation_mode: typeof obj.generation_mode === "string" ? (obj.generation_mode as string) : "mock",
    provider_name: typeof obj.provider_name === "string" ? (obj.provider_name as string) : "mock",
    source_mode: obj.source_mode === "web" ? "web" : "generated",
    total_points: typeof obj.total_points === "number" ? obj.total_points : questions.reduce((sum, q) => sum + q.points, 0),
    effective_student_profile:
      typeof obj.effective_student_profile === "string"
        ? (obj.effective_student_profile as string)
        : null,
    audit: obj.audit && typeof obj.audit === "object" ? (obj.audit as QuizAuditReport) : null,
  };
}

function normalizeSource(raw: unknown): QuizQuestionSource {
  if (raw && typeof raw === "object") {
    const s = raw as Record<string, unknown>;
    return {
      type: s.type === "web" ? "web" : s.type === "local_bank" ? "local_bank" : "generated",
      label: typeof s.label === "string" ? (s.label as string) : "AI 生成",
      uri: typeof s.uri === "string" ? (s.uri as string) : null,
      accessed_at: typeof s.accessed_at === "string" ? (s.accessed_at as string) : null,
    };
  }
  return { type: "generated", label: "AI 生成", uri: null, accessed_at: null };
}
