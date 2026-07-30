/** Client for the rules-driven research clarification API. */

export type PlanClassification = "inference" | "to_verify";
export type EvidenceClassification = "fact" | "inference" | "to_verify";

export interface ResearchState {
  research_domain: string | null;
  core_question: string | null;
  data_and_method: string | null;
  constraints: string | null;
  expected_deliverable: string | null;
}

export interface ClarificationQuestion {
  field: keyof ResearchState;
  label: string;
  question: string;
  options: [string, string, string];
}

export interface ResearchPlanEntry {
  content: string;
  classification: PlanClassification;
  basis: string;
}

export interface ResearchPlanRisk {
  risk: ResearchPlanEntry;
  mitigation: ResearchPlanEntry;
}

export interface ResearchPlan {
  research_title: ResearchPlanEntry;
  research_goal: ResearchPlanEntry;
  candidate_methods_or_baselines: ResearchPlanEntry[];
  suggested_datasets_or_metrics: ResearchPlanEntry[];
  two_week_mvp_plan: ResearchPlanEntry[];
  risks_and_mitigations: ResearchPlanRisk[];
  suggested_search_keywords: string[];
  provenance_note: string;
}

export interface ResearchTurn {
  field: keyof ResearchState;
  value: string;
  input_mode: "initial_description" | "free_text" | "recommended_option" | "llm_suggested";
  recorded_at: string;
}

export interface ResearchSessionResponse {
  session_id: string;
  state: ResearchState;
  missing_fields: (keyof ResearchState)[];
  next_question: ClarificationQuestion | null;
  completed: boolean;
  reply: string;
  generation_mode: "rules" | "llm" | "rules_fallback";
  research_brief: ResearchState | null;
  research_plan: ResearchPlan | null;
  turns: ResearchTurn[];
}

export interface EvidenceStatement {
  content: string;
  classification: EvidenceClassification;
  source_url: string | null;
  basis: string;
}

export interface AcademicSourceStatus {
  source: string;
  status: string;
  source_url: string | null;
  accessed_at: string;
  reason: string | null;
}

export interface AcademicPaperResult {
  title: string;
  authors: string[];
  year: number | null;
  source_name: string;
  url: string;
  identifier: string | null;
  abstract_excerpt: string | null;
  accessed_at: string;
  information_scope: "metadata_and_abstract_only";
  metadata_evidence: EvidenceStatement[];
  supporting_snippets: EvidenceStatement[];
  relevance: EvidenceStatement;
  verification: EvidenceStatement;
  full_text_available: false;
}

export interface EvidenceBundle {
  session_id: string;
  query: string;
  allowed_sources: string[];
  queried_sources: string[];
  source_statuses: AcademicSourceStatus[];
  searched_at: string;
  papers: AcademicPaperResult[];
  source_links: (string | null)[];
  failure_reasons: string[];
  provenance_note: string;
  tool_audit: { required_permissions?: string[]; grant_check?: string } | null;
}

export class ResearchApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ResearchApiError";
  }
}

const API_BASE =
  process.env.NEXT_PUBLIC_CODE_NAVI_API_URL ??
  process.env.NEXT_PUBLIC_API_BASE ??
  "http://localhost:8000";

export async function createResearchSession(): Promise<ResearchSessionResponse> {
  return request<ResearchSessionResponse>("/api/v1/research/sessions", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function getResearchSession(
  sessionId: string,
): Promise<ResearchSessionResponse> {
  return request<ResearchSessionResponse>(
    `/api/v1/research/sessions/${encodeURIComponent(sessionId)}`,
  );
}

export async function submitResearchTurn(
  sessionId: string,
  payload: { answer: string } | { selected_option: string },
): Promise<ResearchSessionResponse> {
  return request<ResearchSessionResponse>(
    `/api/v1/research/sessions/${encodeURIComponent(sessionId)}/turns`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function createEvidenceBundle(
  sessionId: string,
  payload: { query?: string; sources: ["arxiv"] },
): Promise<EvidenceBundle> {
  return request<EvidenceBundle>(
    `/api/v1/research/sessions/${encodeURIComponent(sessionId)}/evidence-bundles`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: { Accept: "application/json", "Content-Type": "application/json" },
    });
  } catch (error) {
    throw new ResearchApiError(0, `无法连接科研服务：${String(error)}`);
  }

  if (!response.ok) {
    throw new ResearchApiError(
      response.status,
      (await errorDetail(response)) ?? `科研服务请求失败（${response.status}）`,
    );
  }
  return (await response.json()) as T;
}

async function errorDetail(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail?: unknown }).detail;
      return typeof detail === "string" ? detail : null;
    }
  } catch {
    // Keep the status-based fallback when a proxy returns a non-JSON response.
  }
  return response.statusText || null;
}
