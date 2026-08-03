/** Browser client for the versioned conversational research API. */

export const RESEARCH_CONVERSATION_SCHEMA = "research-conversation.v1" as const;

export type ResearchStage = "exploring" | "focusing" | "ready_for_plan";
export type GenerationMode = "agent" | "rules" | "rules_fallback";
export type RecommendedAction =
  | "continue_dialogue"
  | "review_profile"
  | "prepare_search";

export interface ResearchProfile {
  topic: string | null;
  motivation: string | null;
  research_questions: string[];
  candidate_questions: string[];
  context: string | null;
  methods: string[];
  data_requirements: string | null;
  evidence_preferences: string[];
  time_scope: string | null;
  constraints: string[];
  expected_output: string | null;
  assumptions: string[];
  uncertainties: string[];
}

export interface ResearchReadiness {
  score: number;
  stage: ResearchStage;
  can_prepare_search: boolean;
  reasons: string[];
}

export type ResearchPlanClassification = "inference" | "to_verify";

export interface ResearchPlanEntry {
  content: string;
  classification: ResearchPlanClassification;
  basis: string;
}

export interface ResearchPlanRisk {
  risk: ResearchPlanEntry;
  mitigation: ResearchPlanEntry;
}

export interface ConversationResearchPlan {
  schema_version: "research-plan.v1";
  research_title: ResearchPlanEntry;
  research_goal: ResearchPlanEntry;
  candidate_methods_or_baselines: ResearchPlanEntry[];
  suggested_datasets_or_metrics: ResearchPlanEntry[];
  two_week_mvp_plan: ResearchPlanEntry[];
  risks_and_mitigations: ResearchPlanRisk[];
  suggested_search_keywords: string[];
  pending_items: ResearchPlanEntry[];
  provenance_note: string;
}

export type ResearchMindMapNodeStatus =
  | "confirmed"
  | "inference"
  | "to_verify"
  | "evidence"
  | "risk";

export interface ResearchMindMapSource {
  label: string;
  url: string;
  accessed_at: string;
}

export interface ResearchMindMapNode {
  id: string;
  label: string;
  status: ResearchMindMapNodeStatus;
  detail: string;
  sources: ResearchMindMapSource[];
}

export interface ResearchMindMapEdge {
  source_id: string;
  target_id: string;
  relation: string;
}

export interface ResearchMindMap {
  schema_version: "research-mindmap.v1";
  root_node_id: string;
  nodes: ResearchMindMapNode[];
  edges: ResearchMindMapEdge[];
  provenance_note: string;
}

export type AnalysisClassification = "fact" | "inference" | "to_verify";

export interface ResearchAnalysisItem {
  area: string;
  content: string;
  classification: AnalysisClassification;
  basis: string;
  source_scope: "profile_and_plan_only" | "metadata_and_abstract_only";
}

export interface TopicDifficultyAnalysis {
  schema_version: "topic-difficulty-analysis.v1";
  title: string;
  information_scope: "profile_and_plan_only" | "metadata_and_abstract_only";
  items: ResearchAnalysisItem[];
  provenance_note: string;
}

export interface PaperAnalysis {
  schema_version: "paper-analysis.v1";
  title: string;
  paper_url: string;
  information_scope: "metadata_and_abstract_only";
  abstract_available: boolean;
  items: ResearchAnalysisItem[];
  provenance_note: string;
}

export interface ExperimentDesign {
  schema_version: "experiment-design.v1";
  hypothesis: ResearchPlanEntry;
  variables: ResearchPlanEntry[];
  data_sources: ResearchPlanEntry[];
  baselines: ResearchPlanEntry[];
  metrics: ResearchPlanEntry[];
  steps: ResearchPlanEntry[];
  resources: ResearchPlanEntry[];
  risks: ResearchPlanEntry[];
  advisor_confirmation_items: ResearchPlanEntry[];
  provenance_note: string;
}

export interface ResearchConversationMessage {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  generation_mode: GenerationMode | null;
  run_id: string | null;
  event_count: number;
  intent: string | null;
  next_question: string | null;
  suggested_answers: string[];
  candidate_questions: string[];
  recommended_action: RecommendedAction | null;
}

export interface ResearchConversationResponse {
  schema_version: typeof RESEARCH_CONVERSATION_SCHEMA;
  active_skill: "research-clarification";
  next_skill: "academic-search" | null;
  conversation_id: string;
  profile: ResearchProfile;
  readiness: ResearchReadiness;
  stage: ResearchStage;
  ready_for_plan: boolean;
  research_plan: ConversationResearchPlan | null;
  research_mindmap: ResearchMindMap;
  topic_difficulty_analysis: TopicDifficultyAnalysis;
  experiment_design: ExperimentDesign | null;
  reply: string;
  generation_mode: GenerationMode;
  recommended_action: RecommendedAction;
  next_question: string | null;
  suggested_answers: string[];
  candidate_questions: string[];
  messages: ResearchConversationMessage[];
  last_run_id: string | null;
}

export interface ProviderStatusResponse {
  schema_version: "research-provider.v1";
  provider: string;
  model: string | null;
  configured: boolean;
  mode: "model" | "rules";
  configuration_method: "local_file" | "server_environment";
  configuration_issue: "invalid_api_key" | "missing_model" | null;
}

export interface ProviderConnectionTestResponse {
  schema_version: "research-provider-test.v1";
  connected: boolean;
  provider: string;
  model: string | null;
  latency_ms: number;
  message: string;
  run_id: string | null;
  failure_code:
    | "invalid_credentials"
    | "model_unavailable"
    | "timeout"
    | "network_error"
    | "invalid_response"
    | "provider_error"
    | null;
}

export interface ConfigureProviderRequest {
  provider: "deepseek" | "openai";
  api_key: string;
  model: string | null;
  base_url: string | null;
}

export type AcademicSourceId = "arxiv" | "openalex" | "crossref";

export interface ResearchSearchSource {
  id: AcademicSourceId;
  display_name: string;
  homepage: string;
  enabled: boolean;
  scope: string;
}

export interface ResearchSearchPlan {
  schema_version: "research-search-plan.v1";
  conversation_id: string;
  query: string;
  alternative_queries: string[];
  sources: ResearchSearchSource[];
  evidence_scope: "metadata_and_abstract_only";
  user_confirmation_required: true;
  provenance_note: string;
}

export interface AcademicPaperResult {
  title: string;
  authors: string[];
  year: number | null;
  source_name: string;
  url: string;
  identifier: string | null;
  abstract_excerpt: string | null;
  information_scope: "metadata_and_abstract_only";
  full_text_available: false;
}

export interface AcademicSourceStatus {
  source: string;
  status:
    | "success"
    | "no_results"
    | "network_error"
    | "timeout"
    | "unavailable"
    | "disabled"
    | "not_allowed"
    | "dependency_missing";
  source_url: string | null;
  accessed_at: string;
  reason: string | null;
  duration_ms: number;
}

export interface ConversationEvidenceBundle {
  schema_version: "academic-evidence.v1";
  bundle_id: string;
  conversation_id: string;
  query: string;
  requested_sources: string[];
  allowed_sources: string[];
  queried_sources: string[];
  source_statuses: AcademicSourceStatus[];
  searched_at: string;
  papers: AcademicPaperResult[];
  source_links: Array<string | null>;
  failure_reasons: string[];
  provenance_note: string;
  tool_audit: Record<string, unknown> | null;
  cache_hit: boolean;
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

const API_BASE = (
  process.env.NEXT_PUBLIC_CODE_NAVI_API_URL ??
  process.env.NEXT_PUBLIC_API_BASE ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const REQUEST_TIMEOUT_MS = 10_000;

export async function createResearchConversation(
  initialMessage?: string,
): Promise<ResearchConversationResponse> {
  const data = await request<unknown>("/api/v1/research/conversations", {
    method: "POST",
    body: JSON.stringify({ initial_message: initialMessage || null }),
  });
  return validateConversationResponse(data);
}

export async function getResearchConversation(
  conversationId: string,
): Promise<ResearchConversationResponse> {
  const data = await request<unknown>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}`,
  );
  return validateConversationResponse(data);
}

export async function sendResearchMessage(
  conversationId: string,
  message: string,
): Promise<ResearchConversationResponse> {
  const data = await request<unknown>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/messages`,
    { method: "POST", body: JSON.stringify({ message }) },
  );
  return validateConversationResponse(data);
}

export async function getResearchProviderStatus(): Promise<ProviderStatusResponse> {
  return request<ProviderStatusResponse>("/api/v1/research/provider/status");
}

export async function testResearchProvider(): Promise<ProviderConnectionTestResponse> {
  return request<ProviderConnectionTestResponse>("/api/v1/research/provider/test", {
    method: "POST",
  }, 20_000);
}

export async function configureResearchProvider(
  configuration: ConfigureProviderRequest,
): Promise<ProviderStatusResponse> {
  return request<ProviderStatusResponse>("/api/v1/research/provider/configuration", {
    method: "PUT",
    body: JSON.stringify(configuration),
  });
}

export async function getResearchSearchPlan(
  conversationId: string,
): Promise<ResearchSearchPlan> {
  return request<ResearchSearchPlan>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/search-plan`,
  );
}

export async function searchResearchEvidence(
  conversationId: string,
  query: string,
  sources: AcademicSourceId[],
): Promise<ConversationEvidenceBundle> {
  return request<ConversationEvidenceBundle>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/evidence-bundles`,
    {
      method: "POST",
      body: JSON.stringify({ query, sources }),
    },
    25_000,
  );
}

export async function listResearchEvidence(
  conversationId: string,
): Promise<ConversationEvidenceBundle[]> {
  return request<ConversationEvidenceBundle[]>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/evidence-bundles`,
  );
}

export async function analyzeResearchPaper(
  conversationId: string,
  paperUrl: string,
): Promise<PaperAnalysis> {
  return request<PaperAnalysis>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/paper-analysis`,
    { method: "POST", body: JSON.stringify({ paper_url: paperUrl }) },
  );
}

function validateConversationResponse(data: unknown): ResearchConversationResponse {
  if (!data || typeof data !== "object") {
    throw new ResearchApiError(502, "科研服务返回了无法识别的数据。请刷新后重试。");
  }
  const candidate = data as Record<string, unknown>;
  if (candidate.schema_version !== RESEARCH_CONVERSATION_SCHEMA) {
    throw new ResearchApiError(
      502,
      `科研服务版本不兼容：需要 ${RESEARCH_CONVERSATION_SCHEMA}。`,
    );
  }
  if (
    typeof candidate.conversation_id !== "string" ||
    !candidate.profile ||
    typeof candidate.profile !== "object" ||
    !Array.isArray(candidate.messages)
  ) {
    throw new ResearchApiError(502, "科研服务响应缺少会话、画像或消息数据。");
  }
  return data as ResearchConversationResponse;
}

async function request<T>(
  path: string,
  init?: RequestInit,
  timeoutMs: number = REQUEST_TIMEOUT_MS,
): Promise<T> {
  let response: Response;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      cache: "no-store",
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ResearchApiError(
        0,
        `科研服务在 ${timeoutMs / 1000} 秒内没有响应。请确认后端已启动后重试。`,
      );
    }
    const reason = error instanceof Error ? error.message : String(error);
    throw new ResearchApiError(
      0,
      `无法连接科研服务（${API_BASE}）。请确认后端已启动。${reason ? ` ${reason}` : ""}`,
    );
  } finally {
    window.clearTimeout(timeout);
  }

  if (!response.ok) {
    throw new ResearchApiError(
      response.status,
      (await errorDetail(response)) ?? `科研服务请求失败（HTTP ${response.status}）。`,
    );
  }
  try {
    return (await response.json()) as T;
  } catch {
    throw new ResearchApiError(502, "科研服务没有返回有效 JSON。");
  }
}

async function errorDetail(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json();
    if (!body || typeof body !== "object" || !("detail" in body)) return null;
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const messages = detail.flatMap((item) => {
        if (!item || typeof item !== "object") return [];
        const validation = item as { loc?: unknown; msg?: unknown };
        if (typeof validation.msg !== "string") return [];
        const location = Array.isArray(validation.loc)
          ? validation.loc.slice(1).join(" → ")
          : "请求内容";
        return [`${location || "请求内容"}：${validation.msg}`];
      });
      return messages.length ? messages.join("；") : null;
    }
  } catch {
    // A proxy may return HTML or an empty body. Keep the status fallback.
  }
  return response.statusText || null;
}
