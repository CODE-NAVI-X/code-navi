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
  generation_mode: "llm" | "rules" | "rules_fallback";
  run_id: string | null;
  event_count: number;
}

export interface PaperAnalysis {
  schema_version: "paper-analysis.v1";
  title: string;
  paper_url: string;
  information_scope: "metadata_and_abstract_only";
  abstract_available: boolean;
  items: ResearchAnalysisItem[];
  provenance_note: string;
  generation_mode: "llm" | "rules" | "rules_fallback";
  run_id: string | null;
  event_count: number;
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
  generation_mode: "llm" | "rules" | "rules_fallback";
  run_id: string | null;
  event_count: number;
}

export interface ExperimentCodeDraftFile { path: string; content: string; }
export interface ExperimentCodeDraft {
  schema_version: "experiment-code-draft.v1";
  title: string;
  directory_tree: string[];
  dependencies: string[];
  files: ExperimentCodeDraftFile[];
  run_instructions: string[];
  assumptions: string[];
  to_verify_items: string[];
  provenance_note: string;
  generation_mode: "llm" | "rules" | "rules_fallback";
  run_id: string | null;
  event_count: number;
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

export type ExperimentEvidenceCategory =
  | "data_or_sample"
  | "setup"
  | "baseline_or_control"
  | "random_seed_or_reason"
  | "metric_or_result"
  | "result_table"
  | "chart_description"
  | "failure_or_limitation"
  | "ethics_or_data_governance"
  | "pending_item";

export interface ExperimentEvidenceItem {
  category: ExperimentEvidenceCategory;
  content: string;
  classification: AnalysisClassification;
  basis: string;
  source_scope: "user_submitted_text";
  related_plan_item: string | null;
  related_evidence_urls: string[];
}

export interface ExperimentEvidenceBundle {
  schema_version: "experiment-evidence.v1";
  bundle_id: string;
  conversation_id: string;
  experiment_name: ExperimentEvidenceItem;
  goal: ExperimentEvidenceItem;
  items: ExperimentEvidenceItem[];
  submitted_at: string;
  provenance_note: string;
}

export interface CreateExperimentEvidenceBundleRequest {
  experiment_name: string;
  goal: string;
  items: Array<Pick<ExperimentEvidenceItem, "category" | "content" | "classification"> & {
    related_plan_item?: string | null;
    related_evidence_urls?: string[];
  }>;
}

export interface PaperBlueprintReference {
  source_type: "research_profile" | "research_plan" | "academic_evidence" | "experiment_evidence";
  bundle_id: string | null;
  label: string;
  classification: AnalysisClassification;
  source_url: string | null;
  information_scope: string;
}

export interface PaperBlueprintEntry {
  content: string;
  classification: AnalysisClassification;
  basis: string;
}

export interface PaperBlueprintSection {
  section: "引言" | "相关工作" | "方法" | "实验" | "讨论" | "结论";
  writing_goal: PaperBlueprintEntry;
  evidence_references: PaperBlueprintReference[];
  missing_evidence: PaperBlueprintEntry[];
  forbidden_claims: string[];
  citation_placeholders: PaperBlueprintReference[];
}

export interface PaperBlueprint {
  schema_version: "paper-blueprint.v1";
  conversation_id: string;
  candidate_titles: PaperBlueprintEntry[];
  target_submission_direction: PaperBlueprintEntry;
  abstract_requirements: PaperBlueprintEntry[];
  sections: PaperBlueprintSection[];
  submission_readiness: PaperBlueprintEntry;
  gaps: PaperBlueprintEntry[];
  provenance_note: string;
  generation_mode: "llm" | "rules" | "rules_fallback";
  run_id: string | null;
  event_count: number;
}

export interface PaperSection { section_id: string; heading: string; content: string; order: number; }
export interface PaperDraft {
  schema_version: "paper-draft.v1"; draft_id: string; conversation_id: string; title: string;
  content: string; format: "markdown" | "plain_text"; version: number; sections: PaperSection[];
  created_at: string; source_scope: "user_pasted_local_session";
}
export type ReviewSeverity = "blocker" | "major" | "minor" | "suggestion";
export interface ReviewFinding {
  id: string; severity: ReviewSeverity; section: string; issue: string; why_it_matters: string;
  recommended_action: string; classification: AnalysisClassification; basis: string;
  source_scope: string; related_blueprint_item: string | null; can_auto_suggest: boolean;
}
export interface RevisionTask { task_id: string; finding_id: string; status: "pending" | "accepted" | "skipped" | "completed"; finding: ReviewFinding; created_at: string; updated_at: string; }
export interface PaperReview {
  schema_version: "paper-review.v1"; review_id: string; draft_id: string; conversation_id: string;
  findings: ReviewFinding[]; revision_tasks: RevisionTask[]; provenance_note: string;
  generation_mode: "llm" | "rules" | "rules_fallback"; run_id: string | null; event_count: number; created_at: string;
}
export interface PaperRevision {
  schema_version: "paper-revision.v1"; revision_id: string; parent_draft_id: string; review_id: string;
  version: number; content: string; applied_task_ids: string[]; change_summary: string[];
  diff_preview: string; created_at: string; source_scope: "user_pasted_draft_plus_accepted_suggestions";
}
export type SubmissionReadinessStatus = "not_ready" | "needs_review" | "checklist_complete";
export interface SubmissionReadinessItem {
  id: string; category: string; message: string; classification: AnalysisClassification;
  basis: string; source_scope: string;
}
export interface SubmissionReadinessCheck {
  schema_version: "submission-readiness.v1"; check_id: string; draft_id: string;
  revision_id: string | null; conversation_id: string; readiness_status: SubmissionReadinessStatus;
  blockers: SubmissionReadinessItem[]; warnings: SubmissionReadinessItem[];
  manual_checks: SubmissionReadinessItem[]; fact_boundary_notes: SubmissionReadinessItem[];
  recommended_next_actions: SubmissionReadinessItem[]; created_at: string;
  source_scope: "local_saved_research_artifacts";
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
const MODEL_TURN_TIMEOUT_MS = 25_000;

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
    MODEL_TURN_TIMEOUT_MS,
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

export async function generateTopicDifficultyAnalysis(
  conversationId: string,
): Promise<TopicDifficultyAnalysis> {
  return request<TopicDifficultyAnalysis>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/topic-difficulty-analysis`,
    { method: "POST", body: JSON.stringify({ user_confirmed: true }) },
  );
}

export async function generateExperimentDesign(
  conversationId: string,
): Promise<ExperimentDesign> {
  return request<ExperimentDesign>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/experiment-design`,
    { method: "POST", body: JSON.stringify({ user_confirmed: true }) },
  );
}

export async function createExperimentCodeDraft(
  conversationId: string,
): Promise<ExperimentCodeDraft> {
  return request<ExperimentCodeDraft>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/experiment-code-draft`,
    { method: "POST", body: JSON.stringify({ user_confirmed: true }) },
  );
}

export async function createExperimentEvidenceBundle(
  conversationId: string,
  payload: CreateExperimentEvidenceBundleRequest,
): Promise<ExperimentEvidenceBundle> {
  return request<ExperimentEvidenceBundle>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/experiment-evidence-bundles`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function listExperimentEvidenceBundles(
  conversationId: string,
): Promise<ExperimentEvidenceBundle[]> {
  return request<ExperimentEvidenceBundle[]>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/experiment-evidence-bundles`,
  );
}

export async function generatePaperBlueprint(conversationId: string): Promise<PaperBlueprint> {
  return request<PaperBlueprint>(
    `/api/v1/research/conversations/${encodeURIComponent(conversationId)}/paper-blueprint`,
    { method: "POST", body: JSON.stringify({ user_confirmed: true }) },
  );
}

export async function createPaperDraft(conversationId: string, payload: { title: string; content: string; format: "markdown" | "plain_text" }): Promise<PaperDraft> {
  return request<PaperDraft>(`/api/v1/research/conversations/${encodeURIComponent(conversationId)}/paper-drafts`, { method: "POST", body: JSON.stringify(payload) });
}
export async function listPaperDrafts(conversationId: string): Promise<PaperDraft[]> {
  return request<PaperDraft[]>(`/api/v1/research/conversations/${encodeURIComponent(conversationId)}/paper-drafts`);
}
export async function createPaperReview(draftId: string): Promise<PaperReview> {
  return request<PaperReview>(`/api/v1/research/paper-drafts/${encodeURIComponent(draftId)}/reviews`, { method: "POST", body: JSON.stringify({ user_confirmed: true }) }, MODEL_TURN_TIMEOUT_MS);
}
export async function listPaperReviews(draftId: string): Promise<PaperReview[]> {
  return request<PaperReview[]>(`/api/v1/research/paper-drafts/${encodeURIComponent(draftId)}/reviews`);
}
export async function updatePaperRevisionTask(reviewId: string, taskId: string, status: "accepted" | "skipped"): Promise<PaperReview> {
  return request<PaperReview>(`/api/v1/research/paper-reviews/${encodeURIComponent(reviewId)}/revision-tasks/${encodeURIComponent(taskId)}`, { method: "PATCH", body: JSON.stringify({ status }) });
}
export async function createPaperRevision(reviewId: string): Promise<PaperRevision> {
  return request<PaperRevision>(`/api/v1/research/paper-reviews/${encodeURIComponent(reviewId)}/revisions`, { method: "POST" });
}
export async function listPaperRevisions(draftId: string): Promise<PaperRevision[]> {
  return request<PaperRevision[]>(`/api/v1/research/paper-drafts/${encodeURIComponent(draftId)}/revisions`);
}
export async function createSubmissionReadiness(draftId: string): Promise<SubmissionReadinessCheck> {
  return request<SubmissionReadinessCheck>(`/api/v1/research/paper-drafts/${encodeURIComponent(draftId)}/submission-readiness`, { method: "POST", body: JSON.stringify({ user_confirmed: true }) });
}
export async function listSubmissionReadiness(draftId: string): Promise<SubmissionReadinessCheck[]> {
  return request<SubmissionReadinessCheck[]>(`/api/v1/research/paper-drafts/${encodeURIComponent(draftId)}/submission-readiness`);
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
