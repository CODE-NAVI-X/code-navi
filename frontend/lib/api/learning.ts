/**
 * Learning-module API client.
 *
 * TypeScript types mirror the backend Pydantic schemas in
 * ``src/code_navi/learning/schemas.py``.
 *
 * All requests go to ``POST /api/v1/learning/explain``.
 */

// ── Data types (mirrors backend ExplainRequest / Citation / ExplainResponse) ────

export interface ExplainRequest {
  knowledge_point: string;
  session_id?: string;
  persona?: string | null;
  include_citations?: boolean;
}

export interface CitationItem {
  source_title: string;
  uri: string | null;
  snippet: string | null;
}

export interface ExplainResponse {
  knowledge_point: string;
  session_id: string;
  summary: string;
  detail?: string | null;
  citations: CitationItem[];
}

// ── Learning session id ────────────────────────────────────────────────────────

const SESSION_STORAGE_KEY = "code-navi:learning-session-id";

/**
 * Return this browser's learning session id, minting one on first use.
 *
 * Notebook entries are scoped by this value server-side, so it must stay
 * stable across reloads.  Only the opaque id is stored — never any credential.
 */
export function getLearningSessionId(): string {
  if (typeof window === "undefined") return "";
  let sessionId = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (!sessionId) {
    sessionId = `sess-${crypto.randomUUID().replace(/-/g, "").slice(0, 16)}`;
    window.localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  }
  return sessionId;
}

// ── API base URL ───────────────────────────────────────────────────────────────

const API_BASE =
  process.env.NEXT_PUBLIC_CODE_NAVI_API_URL ??
  process.env.NEXT_PUBLIC_API_BASE ??
  "http://localhost:8000";

// ── Client error (typed) ───────────────────────────────────────────────────────

export class LearningApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "LearningApiError";
  }
}

// ── Public request helper ──────────────────────────────────────────────────────

/**
 * Send a knowledge-point explain request to the backend.
 *
 * Returns a strongly-typed ``ExplainResponse`` or throws ``LearningApiError``
 * when the server responds with a non-OK status or the network fails.
 */
export async function explainKnowledgePoint(
  request: ExplainRequest,
): Promise<ExplainResponse> {
  const url = `${API_BASE}/api/v1/learning/explain`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        knowledge_point: request.knowledge_point,
        session_id: request.session_id ?? getLearningSessionId(),
        persona: request.persona ?? "academic",
        include_citations: request.include_citations ?? true,
      }),
    });
  } catch (networkError) {
    throw new LearningApiError(
      0,
      `Network error while contacting ${url}: ${String(networkError)}`,
    );
  }

  if (!response.ok) {
    const detail = await extractErrorDetail(response);
    throw new LearningApiError(
      response.status,
      detail ?? `Request failed with status ${response.status}`,
    );
  }

  const body: unknown = await response.json();
  return validateExplainResponse(body);
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

function validateExplainResponse(raw: unknown): ExplainResponse {
  if (!raw || typeof raw !== "object") {
    throw new LearningApiError(502, "Server returned a non-object response.");
  }

  const obj = raw as Record<string, unknown>;

  if (typeof obj.knowledge_point !== "string") {
    throw new LearningApiError(502, "Response missing 'knowledge_point' field.");
  }
  if (typeof obj.summary !== "string") {
    throw new LearningApiError(502, "Response missing 'summary' field.");
  }
  if (typeof obj.session_id !== "string") {
    throw new LearningApiError(502, "Response missing 'session_id' field.");
  }

  const citations: CitationItem[] = [];
  if (Array.isArray(obj.citations)) {
    for (const cit of obj.citations) {
      if (cit && typeof cit === "object") {
        const c = cit as Record<string, unknown>;
        citations.push({
          source_title:
            typeof c.source_title === "string" ? c.source_title : "",
          uri: typeof c.uri === "string" ? c.uri : null,
          snippet: typeof c.snippet === "string" ? c.snippet : null,
        });
      }
    }
  }

  return {
    knowledge_point: obj.knowledge_point as string,
    session_id: obj.session_id as string,
    summary: obj.summary as string,
    detail:
      typeof obj.detail === "string" ? (obj.detail as string) : undefined,
    citations,
  };
}

// ── Presentation (knowledge PPT) types & SSE client ────────────────────────────
// Mirrors the backend Pydantic models in
// ``src/code_navi/learning/presentation/schemas.py``.

export interface SlideBackground {
  type: "solid";
  color: string;
}

export type SlideElementType = "text" | "shape" | "latex" | "image" | "line";

export interface SlideElementBase {
  type: SlideElementType;
  left: number;
  top: number;
  width: number;
  height: number;
  rotate?: number;
}

export interface TextElement extends SlideElementBase {
  type: "text";
  content: string;
  defaultColor?: string;
  defaultFontName?: string;
  lineHeight?: number;
  fill?: string | null;
  textAlign?: "left" | "center" | "right";
}

export interface ShapeElement extends SlideElementBase {
  type: "shape";
  shapeType: "rect" | "roundRect" | "circle" | "triangle" | "diamond" | "message";
  fill: string;
  strokeColor?: string | null;
  strokeWidth?: number;
}

export interface LatexElement extends SlideElementBase {
  type: "latex";
  latex: string;
}

export interface ImageElement extends SlideElementBase {
  type: "image";
  src: string;
  borderRadius?: number;
}

export interface LineElement extends SlideElementBase {
  type: "line";
  strokeColor?: string;
  strokeWidth?: number;
}

export type SlideElement =
  | TextElement
  | ShapeElement
  | LatexElement
  | ImageElement
  | LineElement;

export interface Slide {
  background: SlideBackground;
  elements: SlideElement[];
}

export interface SceneOutline {
  id: string;
  title: string;
  description: string;
  key_points: string[];
  order: number;
}

export interface Presentation {
  id: string;
  knowledge_point: string;
  session_id: string;
  style: string;
  slides: Slide[];
  created_at?: string | null;
}

export type PresentationStreamEvent =
  | { type: "outlines"; data: SceneOutline[] }
  | { type: "slide"; index: number; total: number; data: Slide }
  | { type: "done"; presentation: Presentation }
  | { type: "error"; error: string };

/**
 * POST /api/v1/learning/presentations/generate and yield one event per SSE
 * message. The backend drives the loop (page-level stream): outlines first,
 * then one slide event per finished page, then done/error.
 *
 * Throws LearningApiError on network failure or non-SSE HTTP status.
 */
export async function* streamPresentation(
  request: {
    knowledge_point: string;
    session_id?: string;
    style?: string;
    context?: string | null;
  },
  signal?: AbortSignal,
): AsyncGenerator<PresentationStreamEvent, void, void> {
  const url = `${API_BASE}/api/v1/learning/presentations/generate`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        knowledge_point: request.knowledge_point,
        session_id: request.session_id ?? getLearningSessionId(),
        style: request.style ?? "professional",
        context: request.context ?? null,
      }),
      signal,
    });
  } catch (networkError) {
    throw new LearningApiError(
      0,
      `Network error while contacting ${url}: ${String(networkError)}`,
    );
  }

  if (!response.ok) {
    const detail = await extractErrorDetail(response);
    throw new LearningApiError(
      response.status,
      detail ?? `Request failed with status ${response.status}`,
    );
  }
  if (!response.body) {
    throw new LearningApiError(502, "Response has no readable body stream.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // SSE events are separated by a blank line.
      let sep = buffer.indexOf("\n\n");
      while (sep !== -1) {
        const chunk = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const dataLine = chunk
          .split("\n")
          .find((line) => line.startsWith("data: "));
        if (dataLine) {
          try {
            const event = JSON.parse(dataLine.slice(6)) as PresentationStreamEvent;
            yield event;
          } catch {
            // Ignore a malformed event; keep consuming the stream.
          }
        }
        sep = buffer.indexOf("\n\n");
      }
    }
    // Flush any trailing data line without a blank line.
    const dataLine = buffer
      .split("\n")
      .find((line) => line.startsWith("data: "));
    if (dataLine) {
      try {
        yield JSON.parse(dataLine.slice(6)) as PresentationStreamEvent;
      } catch {
        // ignore
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// ── Presentation fetch (notebook review) ───────────────────────────────────────

export interface PresentationDetail {
  id: string;
  knowledge_point: string;
  session_id: string;
  style: string;
  slides: Slide[];
  outlines: SceneOutline[];
  created_at?: string | null;
}

export async function fetchPresentation(
  presentationId: string,
): Promise<PresentationDetail> {
  const url = `${API_BASE}/api/v1/learning/presentations/${encodeURIComponent(presentationId)}`;
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    throw new LearningApiError(
      res.status,
      `Failed to load presentation (${res.status})`,
    );
  }
  return (await res.json()) as PresentationDetail;
}

// ── Notebook items API helper ──────────────────────────────────────────────────

export interface NotebookItem {
  id: string;
  session_id: string;
  kind: "summary" | "note" | "wrong_answer" | "presentation";
  content: string;
  timestamp?: string | null;
  source_url?: string | null;
  presentation_id?: string | null;
}

export async function fetchNotebookItems(
  sessionId: string,
): Promise<NotebookItem[]> {
  const url = `${API_BASE}/api/v1/learning/notebook?session_id=${encodeURIComponent(sessionId)}`;
  try {
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}