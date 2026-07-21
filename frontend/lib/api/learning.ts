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
  summary: string;
  detail?: string | null;
  citations: CitationItem[];
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
    summary: obj.summary as string,
    detail:
      typeof obj.detail === "string" ? (obj.detail as string) : undefined,
    citations,
  };
}

// ── Notebook items API helper ──────────────────────────────────────────────────

export interface NotebookItem {
  id: string;
  session_id: string;
  kind: "summary" | "note" | "wrong_answer";
  content: string;
  timestamp?: string | null;
  source_url?: string | null;
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